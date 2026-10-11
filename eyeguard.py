"""
EyeGuard - Smart Eye Strain Monitor for Students
PySustain-2026 | Track 1: Code to Cure | SDG 3.4

Uses your webcam + MediaPipe Face Mesh to track:
  * Blink rate (Eye Aspect Ratio)          -> warns below 7/min, strong alert below 5/min
  * Distance from the screen (iris size)   -> alerts when you sit too close
  * Drowsiness (eyes closed > 2 s)
  * Head tilt (posture) and room lighting
  * Profiles for glasses / contact lens wearers: distance corrected for lens
    power, saved calibration, your own safe distance, glare warning
  * 20-20-20 rule with a VERIFIED break (camera checks you really looked away;
    looking back at the screen pauses the 20 s timer)
  * Live Eye Strain Score (0-100), logged to CSV for report.py

Run:   python eyeguard.py            (normal: break every 20 min)
       python eyeguard.py --demo     (break every 60 s - for the judges' demo)
       python eyeguard.py --mute     (start with the sound off)
       python eyeguard.py --test-sound   (play each alert sound once, then exit)
       python eyeguard.py --profile "Sujan - glasses"   (use or create a saved profile)
       python eyeguard.py --background   (no video window: pop-up notifications and a
                                          small always-on-top box; add --no-mini to hide the box)
Keys:  q = quit   c = calibrate distance (sit 50 cm away first)
       b = start a break now   r = reset session counters   m = sound on/off
"""

import argparse
import csv
import math
import os
import signal
import sys
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime

import cv2
import numpy as np
import mediapipe as mp

import profiles

# ---------------------------------------------------------------- settings
CAMERA_INDEX = 0
IRIS_DIAMETER_CM = 1.17          # human iris is ~11.7 mm for almost everyone
MIN_SAFE_DISTANCE_CM = 50        # closer than this -> "too close"
BLINK_WARN_RATE = 7              # blinks/min below this -> warning; normal is ~15-20
BLINK_ALERT_RATE = 5             # blinks/min below this -> strong alert
LOW_BLINK_RATE = BLINK_WARN_RATE # older name for the warning level
DROWSY_SECONDS = 2.0             # eyes closed this long -> drowsy
BREAK_LOOK_AWAY_SECONDS = 20     # the "20 seconds" of 20-20-20
BREAK_GLANCE_SECONDS = 0.5       # looking back for less than this is ignored
MAX_FRAME_GAP = 1.0              # a frozen camera adds at most this much break time
GLARE_SECONDS = 2.0              # glare check looks at this much recent video
GLARE_IRIS_JUMP = 0.08           # iris width changing 8% between two frames is a "jump"
GLARE_IRIS_JUMPS = 4             # this many jumps in that time -> probably glare
GLARE_EAR_FLIPS = 6              # eye "opening/closing" this often -> probably glare
GLARE_MIN_FRAMES = 8             # needs at least this many frames to decide
GLARE_MESSAGE = "Glare on your glasses? Reduce light behind you or tilt the screen."
DARK_BRIGHTNESS = 60             # mean pixel value below this -> room too dark
HEAD_TILT_DEG = 15               # head roll beyond this -> posture warning
ALERT_COOLDOWN = 15              # seconds between repeats of the same alert

# MediaPipe Face Mesh landmark indices
LEFT_EYE = [33, 160, 158, 133, 153, 144]     # p1..p6 for EAR
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
LEFT_IRIS_EDGES = (469, 471)                 # horizontal edges of iris
RIGHT_IRIS_EDGES = (474, 476)
NOSE_TIP = 1
LEFT_EYE_OUTER, RIGHT_EYE_OUTER = 33, 263

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "face_landmarker.task")


# ------------------------------------------------------- landmark backend
class FaceMeshBackend:
    """Returns 478 (x, y) pixel landmarks or None.
    Works with both old MediaPipe (mp.solutions) and new (mp.tasks) versions."""

    def __init__(self):
        self.legacy = hasattr(mp, "solutions")
        if self.legacy:
            self.mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)
        else:
            from mediapipe.tasks.python import BaseOptions, vision
            if not os.path.exists(MODEL_PATH):
                print("Downloading face model (one time, ~4 MB)...")
                urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            opts = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=vision.RunningMode.VIDEO, num_faces=1)
            self.mesh = vision.FaceLandmarker.create_from_options(opts)
            self.t0 = time.time()
            self.last_ts = -1

    def process(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if self.legacy:
            res = self.mesh.process(rgb)
            if not res.multi_face_landmarks:
                return None
            lms = res.multi_face_landmarks[0].landmark
        else:
            ts = int((time.time() - self.t0) * 1000)
            ts = max(ts, self.last_ts + 1)          # timestamps must increase
            self.last_ts = ts
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res = self.mesh.detect_for_video(image, ts)
            if not res.face_landmarks:
                return None
            lms = res.face_landmarks[0]
        return np.array([(p.x * w, p.y * h) for p in lms], dtype=np.float32)


# ------------------------------------------------------------ measurements
def eye_aspect_ratio(pts, idx):
    """EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|). Drops sharply when eye closes."""
    p1, p2, p3, p4, p5, p6 = (pts[i] for i in idx)
    vertical = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    horizontal = np.linalg.norm(p1 - p4)
    return float(vertical / (2.0 * horizontal)) if horizontal > 0 else 0.0


def iris_width_px(pts):
    left = np.linalg.norm(pts[LEFT_IRIS_EDGES[0]] - pts[LEFT_IRIS_EDGES[1]])
    right = np.linalg.norm(pts[RIGHT_IRIS_EDGES[0]] - pts[RIGHT_IRIS_EDGES[1]])
    return float((left + right) / 2.0)


def distance_cm(iris_px, focal_px):
    """Pinhole camera: distance = focal_length * real_size / pixel_size."""
    return focal_px * IRIS_DIAMETER_CM / iris_px if iris_px > 0 else 0.0


def head_pose(pts):
    """Returns (yaw_ratio, roll_deg). yaw_ratio ~0 when facing the screen."""
    le, re, nose = pts[LEFT_EYE_OUTER], pts[RIGHT_EYE_OUTER], pts[NOSE_TIP]
    eye_dist = np.linalg.norm(re - le)
    mid = (le + re) / 2.0
    yaw = float((nose[0] - mid[0]) / eye_dist) if eye_dist > 0 else 0.0
    roll = math.degrees(math.atan2(re[1] - le[1], re[0] - le[0]))
    return yaw, roll


def strain_score(blink_rate, dist, mins_since_break, drowsy_events, break_every_min,
                 safe_cm=MIN_SAFE_DISTANCE_CM):
    """0 = relaxed eyes, 100 = heavy strain. safe_cm is the "too close" limit
    (a profile can raise it above the usual 50 cm)."""
    score = 0.0
    if blink_rate < 15:                                     # up to 40 points
        score += min(40, (15 - blink_rate) * 4)
    if 0 < dist < safe_cm:                                  # up to 30 points
        score += min(30, (safe_cm - dist) * 1.5)
    score += min(20, 20 * mins_since_break / break_every_min)  # up to 20 points
    score += min(10, drowsy_events * 5)                     # up to 10 points
    return int(round(min(100, score)))


def blink_alert(blink_rate):
    """(message, level) when the blink rate is low, else None.
    level is "warn" below BLINK_WARN_RATE and "alert" below BLINK_ALERT_RATE."""
    if blink_rate < BLINK_ALERT_RATE:
        return f"Blink now! Only {blink_rate:.0f}/min", "alert"
    if blink_rate < BLINK_WARN_RATE:
        return f"Blink more! Only {blink_rate:.0f}/min", "warn"
    return None


class GlareDetector:
    """Spots reflections on glasses. Glare makes the eye landmarks jump about,
    so over the last ~2 seconds either the iris width keeps jumping, or the
    eye seems to open and close far faster than anyone blinks."""

    def __init__(self):
        self.frames = deque()            # (time, iris jumped?, eye state flipped?)
        self.last_iris = self.last_closed = None

    def reset(self):
        """Call when the face is lost, so the next frame is not compared with it."""
        self.last_iris = self.last_closed = None

    def update(self, iris_px, ear, ear_threshold, now):
        """Call once per frame with a face in view. Returns True while it looks like glare."""
        jumped = (self.last_iris is not None and self.last_iris > 0
                  and abs(iris_px - self.last_iris) / self.last_iris > GLARE_IRIS_JUMP)
        closed = ear < ear_threshold
        flipped = self.last_closed is not None and closed != self.last_closed
        self.last_iris, self.last_closed = iris_px, closed
        self.frames.append((now, jumped, flipped))
        while self.frames and now - self.frames[0][0] > GLARE_SECONDS:
            self.frames.popleft()
        if len(self.frames) < GLARE_MIN_FRAMES:
            return False
        return (sum(f[1] for f in self.frames) >= GLARE_IRIS_JUMPS
                or sum(f[2] for f in self.frames) >= GLARE_EAR_FLIPS)


class BreakTimer:
    """The 20 seconds of a 20-20-20 break.

    It only counts while you look away. Looking back at the screen PAUSES it
    at its current value, and looking away again continues from there. A
    glance back shorter than BREAK_GLANCE_SECONDS is ignored.
    state is "waiting" (not looked away yet), "counting", "paused" or "done"."""

    def __init__(self, seconds=BREAK_LOOK_AWAY_SECONDS, glance=BREAK_GLANCE_SECONDS):
        self.seconds, self.glance = seconds, glance
        self.reset()

    def reset(self):
        self.done = 0.0              # seconds of looking away so far
        self.state = "waiting"
        self._facing = 0.0           # how long the current look back has lasted
        self._last = None            # time of the previous frame

    def hold(self):
        """Call when frames stopped for a while, so the gap is not counted."""
        self._last, self._facing = None, 0.0

    def update(self, looking_away, now):
        """Call once per frame during a break. Returns "paused" at the moment
        the timer pauses, "done" when the break is complete, otherwise None."""
        step = 0.0 if self._last is None else min(max(now - self._last, 0.0), MAX_FRAME_GAP)
        self._last = now
        if self.state == "done":
            return None
        if looking_away:
            self.done += step + self._facing     # a short glance back still counts
            self._facing = 0.0
            self.state = "counting"
            if self.done >= self.seconds - 1e-6:
                self.done, self.state = float(self.seconds), "done"
                return "done"
        elif self.state == "counting":
            self._facing += step
            if self._facing >= self.glance - 1e-6:
                self._facing, self.state = 0.0, "paused"
                return "paused"
        return None

    def status(self):
        """(text, level) for the break screen: level is "good" while the timer
        is running and "warn" while it is waiting for you to look away."""
        progress = f"({int(self.done + 1e-6)}/{self.seconds} s)"      # whole seconds done
        if self.state in ("counting", "done"):
            return f"Good! Keep looking away {progress}", "good"
        if self.state == "paused":
            return f"Paused - look away to continue {progress}", "warn"
        return f"Look away to start the timer {progress}", "warn"


# The three sounds: (tone in Hz, length in ms, Windows system sound played as well)
SOUNDS = {
    "alert": (1000, 300, "SystemExclamation"),   # an alert, or a break starting
    "pause": (800, 150, "SystemDefault"),        # looked back during a break
    "done": (1200, 300, "SystemAsterisk"),       # break finished
}
_sound_warning_shown = False


def _play(freq, ms, alias):
    """Plays one sound. Runs in its own thread so the video never waits for it."""
    global _sound_warning_shown
    problems = []
    try:
        import winsound
    except ImportError as err:
        problems.append(f"winsound is not available ({err})")
    else:
        heard = False
        try:
            winsound.Beep(freq, ms)                  # a plain tone
            heard = True
        except Exception as err:
            problems.append(f"Beep: {err}")
        try:                                         # some laptops ignore Beep(), so also
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)  # a system sound
            heard = True
        except Exception as err:
            problems.append(f"PlaySound: {err}")
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                heard = True
            except Exception as err2:
                problems.append(f"MessageBeep: {err2}")
        if heard:
            return
    if not _sound_warning_shown:                     # say so once, not on every alert
        _sound_warning_shown = True
        print("Warning: EyeGuard could not play a sound (" + "; ".join(problems) + "). "
              "Alerts still appear on screen.")


def beep(freq=1000, ms=300, alias="SystemExclamation", wait=False):
    """Plays a tone and a Windows system sound without holding up the video.
    wait=True returns only when the tone has finished (used by --test-sound)."""
    if not sys.platform.startswith("win"):
        print("\a", end="", flush=True)
        return
    player = threading.Thread(target=_play, args=(freq, ms, alias), daemon=True)
    player.start()
    if wait:
        player.join()


def test_sound():
    """py eyeguard.py --test-sound: plays each sound once so you can check you hear them."""
    print("EyeGuard sound test. You should hear three sounds, each a tone followed "
          "by a Windows system sound.")
    for number, (kind, what) in enumerate([("alert", "alert / break starting"),
                                           ("pause", "break paused (you looked back)"),
                                           ("done", "break done")], start=1):
        print(f"  {number}. {what}")
        beep(*SOUNDS[kind], wait=True)
        time.sleep(1.0)
    print("Heard nothing? Check the volume is up and not muted, and that the right "
          "speaker or headphones are selected in Windows sound settings.")


# ------------------------------------------------------------- drawing
def put(img, text, pos, color=(255, 255, 255), scale=0.6, thick=2):
    # Black edge first, then the text. The edge is the same text moved one pixel
    # each way: drawing it with a thicker stroke makes it wider than the text
    # in newer OpenCV versions, so the two no longer line up.
    x, y = pos
    for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
        cv2.putText(img, text, (x + dx, y + dy), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


AMBER = (0, 170, 255)                # warnings (OpenCV colours are blue, green, red)
ALERT_RED = (0, 0, 200)              # strong alerts


def level_color(good):
    return (80, 200, 80) if good else (60, 60, 230)


def blink_color(blink_rate):
    """Green when blinking enough, amber at the warning level, red at the alert level."""
    if blink_rate >= BLINK_WARN_RATE:
        return level_color(True)
    return AMBER if blink_rate >= BLINK_ALERT_RATE else level_color(False)


def put_centred(img, text, y, color, scale=0.8, thick=2):
    """put(), centred and shrunk to fit narrow frames."""
    width = img.shape[1]
    text_w = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)[0][0]
    if text_w > width - 20:
        scale *= (width - 20) / text_w
        text_w = width - 20
    put(img, text, ((width - text_w) // 2, y), color, scale, thick)


def put_fit(img, text, pos, max_width, color=(255, 255, 255), scale=0.45, thick=1):
    """put() for one line that must fit in max_width pixels: long text is cut
    short and ends with "..."."""
    def width(t):
        return cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)[0][0]
    if width(text) > max_width:
        while len(text) > 1 and width(text + "...") > max_width:
            text = text[:-1]
        text = text.rstrip() + "..."
    put(img, text, pos, color, scale, thick)


def draw_break_screen(frame, timer):
    """Blue break screen with the timer message and a bar of seconds done out
    of 20. Green while the timer runs, amber while it is paused or waiting."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (120, 60, 0), -1)
    frame = cv2.addWeighted(overlay, 0.45, frame, 0.55, 0)
    text, level = timer.status()
    color = (80, 230, 80) if level == "good" else AMBER
    put_centred(frame, "20-20-20 BREAK", h // 2 - 40, (255, 255, 255), 1.1, 3)
    put_centred(frame, "Look at something 20 feet away", h // 2, (255, 255, 255))
    put_centred(frame, text, h // 2 + 40, color)
    half = min(200, w // 2 - 20)
    x0, x1, y0 = w // 2 - half, w // 2 + half, h // 2 + 58
    filled = x0 + int((x1 - x0) * timer.done / timer.seconds)
    cv2.rectangle(frame, (x0, y0), (x1, y0 + 14), (60, 60, 60), -1)
    cv2.rectangle(frame, (x0, y0), (filled, y0 + 14), color, -1)
    cv2.rectangle(frame, (x0, y0), (x1, y0 + 14), (255, 255, 255), 1)
    return frame


# ------------------------------------------------------------- main app
def main():
    ap = argparse.ArgumentParser(description="EyeGuard eye strain monitor")
    ap.add_argument("--demo", action="store_true", help="break every 60 s instead of 20 min")
    ap.add_argument("--camera", type=int, default=CAMERA_INDEX)
    ap.add_argument("--mute", action="store_true", help="start with the sound off (m toggles it)")
    ap.add_argument("--test-sound", action="store_true",
                    help="play each alert sound once and exit")
    ap.add_argument("--profile", metavar="NAME",
                    help='use a saved profile, or create it with three questions, '
                         'e.g. --profile "Sujan - glasses"')
    ap.add_argument("--background", action="store_true",
                    help="no video window: Windows notifications and a small "
                         "always-on-top box with a Stop button")
    ap.add_argument("--no-mini", action="store_true",
                    help="with --background: do not show the small box (stop with Ctrl+C)")
    args = ap.parse_args()
    break_every_s = 60 if args.demo else 20 * 60
    for stream in (sys.stdout, sys.stderr):      # a name the terminal cannot show
        if hasattr(stream, "reconfigure"):       # prints as "?" instead of stopping
            stream.reconfigure(errors="replace")

    if args.test_sound:
        test_sound()
        return

    profile = None                      # None = no profile: everything works as before
    if args.profile:
        try:
            profile = profiles.load_or_create(args.profile)
        except ValueError as err:
            print(f"Profile not used: {err}")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return
    # two short lines beside the title: who is using it, and what they wear
    profile_lines = ((profiles.to_ascii(profile["name"]) or "Profile", profiles.describe(profile))
                     if profile else ())            # the video font only has plain letters

    # what the profile changes (with no profile these keep their usual values)
    safe_cm = profile["safe_distance_cm"] if profile else MIN_SAFE_DISTANCE_CM
    lens_m = profiles.distance_factor(profile)      # glasses make the iris look bigger/smaller
    glare = GlareDetector() if profile and profile["correction"] == "glasses" else None
    if profiles.is_calibrated(profile):
        print(f"Using the calibration saved on {profile['calibrated_on']} "
              f"(focal = {profile['focal_px']:.0f} px).")
    for note in (profiles.estimate_note(profile), profiles.calibration_note(profile),
                 profiles.high_power_note(profile)):
        if note:
            print(note)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("Could not open webcam. Try --camera 1")
        return
    backend = FaceMeshBackend()

    notifier = mini = None              # only used in background mode
    if args.background:
        import background as bg         # loaded here so the normal mode never needs it
        notifier = bg.Notifier()
        if not args.no_mini:
            try:
                mini = bg.MiniWindow()
            except Exception as err:    # no desktop to draw on: carry on without the box
                print(f"Mini window not shown ({err}). Stop with Ctrl+C.")
    elif args.no_mini:
        print("--no-mini only does something together with --background.")

    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", datetime.now().strftime("session_%Y%m%d_%H%M%S.csv"))
    log_file = open(log_path, "w", newline="")
    log = csv.writer(log_file)
    log.writerow(["timestamp", "face", "ear", "blinks_total", "blink_rate",
                  "distance_cm", "looking_away", "brightness", "on_break",
                  "strain_score", "alert"])

    # state
    focal_px = profile["focal_px"] if profiles.is_calibrated(profile) else None
                                        # else set from frame width, or by calibration
    calib_ears = []                     # first few seconds -> personal EAR threshold
    ear_threshold = 0.21
    closed_frames, closed_since = 0, None
    blink_times = deque()
    blinks_total, drowsy_events = 0, 0
    session_start = time.time()
    last_break_end = session_start
    on_break, break_timer = False, BreakTimer()
    last_alert = {}
    current_alert, alert_level = "", "alert"
    last_log = 0.0
    dist = 0.0
    ear = 0.0
    looking_away = False
    sound_on = not args.mute            # m key toggles this
    notices = []                        # (text, show until this time) small lines on the video
    if profiles.high_power_note(profile):               # once per session, first 10 seconds
        notices.append((profiles.high_power_note(profile), session_start + 10))

    no_face_since = None                # background mode: when the face was last lost
    away_paused = False                 # background mode: nobody in view for 2+ minutes
    stop = {"asked": False}             # set by Ctrl+C so the session is saved properly

    def sound(kind="alert"):
        if sound_on and not away_paused:
            beep(*SOUNDS[kind])

    def notify(message, title=None):
        """Background mode: a pop-up notification (silent, the beep is separate)."""
        if notifier and not away_paused:
            notifier.show(message, *([title] if title else []))

    def alert(key, msg, level="alert"):
        nonlocal current_alert, alert_level
        current_alert, alert_level = msg, level
        now = time.time()
        if now - last_alert.get(key, 0) > ALERT_COOLDOWN:
            last_alert[key] = now
            sound()
            notify(msg)

    def on_ctrl_c(*_):
        stop["asked"] = True

    try:
        old_ctrl_c = signal.signal(signal.SIGINT, on_ctrl_c)
    except ValueError:                  # not the main thread: Ctrl+C keeps its usual meaning
        old_ctrl_c = None

    if args.background:
        print(f"EyeGuard running in the background. Logging to {log_path}.")
        print("Stop with the Stop button on the small EyeGuard box, or Ctrl+C here."
              if mini else "Stop with Ctrl+C in this window.")
        if not profiles.is_calibrated(profile):
            print("Tip: to calibrate the distance, run once without --background and press c.")
    else:
        print(f"EyeGuard running. Logging to {log_path}. Press q to quit.")
    while True:
        if stop["asked"] or (mini and mini.stopped):
            break
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        if focal_px is None:
            focal_px = w * 0.9          # typical laptop webcam (~60 deg FOV)
        now = time.time()
        current_alert = ""

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        pts = backend.process(frame)
        face = pts is not None

        if notifier:                      # background mode: pause while nobody is there
            if face:
                no_face_since = None
                if away_paused:
                    away_paused = False
                    print("Face seen again: EyeGuard continues.")
            else:
                no_face_since = no_face_since or now
                if not away_paused and now - no_face_since >= bg.NO_FACE_PAUSE_SECONDS:
                    notify(bg.PAUSED_MESSAGE, bg.PAUSED_TITLE)     # one message, then quiet
                    away_paused = True

        if face:
            ear = (eye_aspect_ratio(pts, LEFT_EYE) + eye_aspect_ratio(pts, RIGHT_EYE)) / 2
            yaw, roll = head_pose(pts)
            looking_away = abs(yaw) > 0.25
            iris_px = iris_width_px(pts)
            dist = distance_cm(iris_px, focal_px) * lens_m

            # personal threshold: 75% of your normal open-eye EAR (first ~3 s)
            if len(calib_ears) < 90:
                calib_ears.append(ear)
                if len(calib_ears) == 90:
                    ear_threshold = float(np.clip(np.median(calib_ears) * 0.75, 0.15, 0.28))

            # blink & drowsiness
            if ear < ear_threshold:
                closed_frames += 1
                closed_since = closed_since or now
                if now - closed_since > DROWSY_SECONDS:
                    alert("drowsy", "You look drowsy - take a proper break!")
            else:
                if 2 <= closed_frames and (now - (closed_since or now)) < DROWSY_SECONDS:
                    blinks_total += 1
                    blink_times.append(now)
                elif closed_since and now - closed_since >= DROWSY_SECONDS:
                    drowsy_events += 1
                closed_frames, closed_since = 0, None

            glare_now = bool(glare) and glare.update(iris_px, ear, ear_threshold, now)
            for idx in LEFT_EYE + RIGHT_EYE:
                cv2.circle(frame, tuple(int(v) for v in pts[idx]), 1, (0, 255, 255), -1)
        else:
            looking_away = True
            yaw, roll = 0.0, 0.0
            glare_now = False
            if glare:
                glare.reset()

        while blink_times and now - blink_times[0] > 60:
            blink_times.popleft()
        elapsed = now - session_start
        # blinks per minute over the last 60 s (needs ~15 s of data to be meaningful)
        blink_rate = len(blink_times) * 60 / min(60, elapsed) if elapsed >= 15 else 15.0

        # ---------------- 20-20-20 with verified break
        since_break = now - last_break_end
        if not on_break and since_break >= break_every_s:
            on_break = True
            break_timer.reset()
            sound()
            if notifier:
                notify(bg.break_start_message(break_timer.seconds))
        if on_break:
            event = break_timer.update(looking_away, now)
            if event == "paused":         # looked back at the screen: one short beep
                sound("pause")
                if notifier:
                    notify(bg.break_paused_message(break_timer.done, break_timer.seconds))
            elif event == "done":
                on_break, last_break_end = False, now
                sound("done")
                if notifier:
                    notify(bg.BREAK_DONE)

        # ---------------- alerts (only when not on break)
        if not on_break and face:
            low_blink = blink_alert(blink_rate) if elapsed > 30 else None
            if low_blink:
                alert("blink_" + low_blink[1], *low_blink)
            if 0 < dist < safe_cm:
                alert("dist", f"Too close! {dist:.0f} cm - move back")
            if abs(roll) > HEAD_TILT_DEG:
                alert("posture", "Straighten your head / posture")
            if glare_now:                 # readings are unreliable while there is glare
                alert("glare", GLARE_MESSAGE, "warn")
        if brightness < DARK_BRIGHTNESS:
            alert("dark", "Room too dark - turn on a light")

        score = strain_score(blink_rate, dist if face else 0,
                             min(since_break, break_every_s) / 60,
                             drowsy_events, break_every_s / 60, safe_cm)

        # ---------------- HUD
        panel = frame.copy()
        cv2.rectangle(panel, (0, 0), (300, 235), (30, 30, 30), -1)
        frame = cv2.addWeighted(panel, 0.6, frame, 0.4, 0)
        put(frame, "EyeGuard", (10, 28), (255, 200, 0), 0.8)
        for row, text in enumerate(profile_lines):
            put_fit(frame, text, (132, 15 + 16 * row), 163, (220, 220, 220), 0.42)
        put(frame, f"Blinks/min: {blink_rate:4.1f}" if elapsed >= 15 else "Blinks/min: measuring...",
            (10, 60), blink_color(blink_rate))
        put(frame, f"Total blinks: {blinks_total}", (10, 85))
        put(frame, f"Distance: {dist:4.0f} cm" if face else "Distance: --",
            (10, 110), level_color(dist >= safe_cm))
        mins_left = max(0, break_every_s - since_break) / 60
        put(frame, f"Next break: {mins_left:4.1f} min", (10, 135))
        put(frame, f"Strain score: {score}/100", (10, 160), level_color(score < 50))
        put(frame, f"EAR {ear:.2f} (thr {ear_threshold:.2f})", (10, 185), (200, 200, 200), 0.5, 1)
        put(frame, "q quit | c calibrate | b break | r reset", (10, 207), (200, 200, 200), 0.45, 1)
        put(frame, f"m sound {'ON' if sound_on else 'OFF'}", (10, 227), (200, 200, 200), 0.45, 1)

        bar_w = int((w - 20) * score / 100)
        cv2.rectangle(frame, (10, h - 20), (w - 10, h - 8), (60, 60, 60), -1)
        cv2.rectangle(frame, (10, h - 20), (10 + bar_w, h - 8), level_color(score < 50), -1)

        if on_break:
            frame = draw_break_screen(frame, break_timer)
        else:
            # small lines above the alert bar: notices, then calibration help
            lines = [text for text, until in notices if now < until]
            lines += [note for note in (profiles.estimate_note(profile),
                                        profiles.calibration_note(profile)) if note]
            if lines:                     # on a dark strip so they stay readable
                top = h - 76 - 18 * len(lines)
                strip = frame.copy()
                cv2.rectangle(strip, (0, top), (w, h - 72), (30, 30, 30), -1)
                frame = cv2.addWeighted(strip, 0.6, frame, 0.4, 0)
            for row, text in enumerate(reversed(lines)):
                put_centred(frame, profiles.to_ascii(text), h - 80 - 18 * row,
                            (255, 255, 255), 0.5, 1)
        if current_alert and not on_break:
            cv2.rectangle(frame, (0, h - 70), (w, h - 28),
                          AMBER if alert_level == "warn" else ALERT_RED, -1)
            if cv2.getTextSize(current_alert, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0][0] <= w - 30:
                put(frame, current_alert, (15, h - 40), (255, 255, 255), 0.8)
            else:                         # a long message is shrunk to fit
                put_centred(frame, current_alert, h - 40, (255, 255, 255))

        if not args.background:
            cv2.imshow("EyeGuard - Eye Strain Monitor", frame)
        elif mini:
            mini.update(bg.mini_lines(
                blink_rate, elapsed < 15, dist, face, score, on_break, break_timer.done,
                break_timer.seconds, break_every_s - since_break, safe_cm,
                BLINK_WARN_RATE, BLINK_ALERT_RATE, away_paused))

        # ---------------- log once per second
        if now - last_log >= 1:
            last_log = now
            log.writerow([datetime.now().isoformat(timespec="seconds"), int(face),
                          round(ear, 3), blinks_total, round(blink_rate, 1),
                          round(dist, 1) if face else "", int(looking_away),
                          round(brightness, 1), int(on_break), score, current_alert])
            log_file.flush()

        if args.background:               # no window, so no keys; and no need to hurry
            spare = 1 / bg.MAX_FPS - (time.time() - now)
            if spare > 0:
                time.sleep(spare)
            continue
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("c") and face:
            focal_px = iris_width_px(pts) * MIN_SAFE_DISTANCE_CM / IRIS_DIAMETER_CM
            lens_m = 1.0                  # calibrating with your glasses on includes the lens
            print(f"Calibrated at {MIN_SAFE_DISTANCE_CM} cm (focal = {focal_px:.0f} px)")
            if profile:
                try:
                    profile = profiles.save_calibration(profile, focal_px)
                    print(f"Calibration saved to profile {profile['name']}.")
                    notices.append((f"Calibrated at {MIN_SAFE_DISTANCE_CM} cm and saved to "
                                    "your profile", now + 5))
                except (OSError, ValueError) as err:
                    print(f"Calibration not saved: {err}")
        if key == ord("b"):
            on_break = True
            break_timer.reset()
        if key == ord("r"):
            blink_times.clear()
            blinks_total = drowsy_events = 0
            session_start = last_break_end = now
        if key == ord("m"):
            sound_on = not sound_on
            print(f"Sound {'on' if sound_on else 'off'}")

    if old_ctrl_c is not None:
        signal.signal(signal.SIGINT, old_ctrl_c)
    cap.release()
    if mini:
        mini.close()
    if not args.background:
        cv2.destroyAllWindows()
    log_file.close()
    print(f"Session saved to {log_path}. Run: python report.py")


if __name__ == "__main__":
    main()
