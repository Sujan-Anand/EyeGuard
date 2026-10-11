"""
EyeGuard - Smart Eye Strain Monitor for Students
PySustain-2026 | Track 1: Code to Cure | SDG 3.4

Uses your webcam + MediaPipe Face Mesh to track:
  * Blink rate (Eye Aspect Ratio)          -> warns below 7/min, strong alert below 5/min
  * Distance from the screen (iris size)   -> alerts when you sit too close
  * Drowsiness (eyes closed > 2 s)
  * Head tilt (posture) and room lighting
  * 20-20-20 rule with a VERIFIED break (camera checks you really looked away;
    looking back at the screen pauses the 20 s timer)
  * Live Eye Strain Score (0-100), logged to CSV for report.py

Run:   python eyeguard.py            (normal: break every 20 min)
       python eyeguard.py --demo     (break every 60 s - for the judges' demo)
       python eyeguard.py --mute     (start with the sound off)
       python eyeguard.py --profile "Sujan - glasses"   (use or create a saved profile)
Keys:  q = quit   c = calibrate distance (sit 50 cm away first)
       b = start a break now   r = reset session counters   m = sound on/off
"""

import argparse
import csv
import math
import os
import sys
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


def strain_score(blink_rate, dist, mins_since_break, drowsy_events, break_every_min):
    """0 = relaxed eyes, 100 = heavy strain."""
    score = 0.0
    if blink_rate < 15:                                     # up to 40 points
        score += min(40, (15 - blink_rate) * 4)
    if 0 < dist < MIN_SAFE_DISTANCE_CM:                     # up to 30 points
        score += min(30, (MIN_SAFE_DISTANCE_CM - dist) * 1.5)
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


def beep(freq=1000, ms=300):
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(freq, ms)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


# ------------------------------------------------------------- drawing
def put(img, text, pos, color=(255, 255, 255), scale=0.6, thick=2):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2)
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
    ap.add_argument("--profile", metavar="NAME",
                    help='use a saved profile, or create it with three questions, '
                         'e.g. --profile "Sujan - glasses"')
    args = ap.parse_args()
    break_every_s = 60 if args.demo else 20 * 60
    for stream in (sys.stdout, sys.stderr):      # a name the terminal cannot show
        if hasattr(stream, "reconfigure"):       # prints as "?" instead of stopping
            stream.reconfigure(errors="replace")

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

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("Could not open webcam. Try --camera 1")
        return
    backend = FaceMeshBackend()

    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", datetime.now().strftime("session_%Y%m%d_%H%M%S.csv"))
    log_file = open(log_path, "w", newline="")
    log = csv.writer(log_file)
    log.writerow(["timestamp", "face", "ear", "blinks_total", "blink_rate",
                  "distance_cm", "looking_away", "brightness", "on_break",
                  "strain_score", "alert"])

    # state
    focal_px = None                     # set from frame width, or by calibration
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

    def sound(short=False):
        if sound_on:
            beep(800, 150) if short else beep()

    def alert(key, msg, level="alert"):
        nonlocal current_alert, alert_level
        current_alert, alert_level = msg, level
        now = time.time()
        if now - last_alert.get(key, 0) > ALERT_COOLDOWN:
            last_alert[key] = now
            sound()

    print(f"EyeGuard running. Logging to {log_path}. Press q to quit.")
    while True:
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

        if face:
            ear = (eye_aspect_ratio(pts, LEFT_EYE) + eye_aspect_ratio(pts, RIGHT_EYE)) / 2
            yaw, roll = head_pose(pts)
            looking_away = abs(yaw) > 0.25
            dist = distance_cm(iris_width_px(pts), focal_px)

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

            for idx in LEFT_EYE + RIGHT_EYE:
                cv2.circle(frame, tuple(int(v) for v in pts[idx]), 1, (0, 255, 255), -1)
        else:
            looking_away = True
            yaw, roll = 0.0, 0.0

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
        if on_break:
            event = break_timer.update(looking_away, now)
            if event == "paused":         # looked back at the screen: one short beep
                sound(short=True)
            elif event == "done":
                on_break, last_break_end = False, now
                sound()

        # ---------------- alerts (only when not on break)
        if not on_break and face:
            low_blink = blink_alert(blink_rate) if elapsed > 30 else None
            if low_blink:
                alert("blink_" + low_blink[1], *low_blink)
            if 0 < dist < MIN_SAFE_DISTANCE_CM:
                alert("dist", f"Too close! {dist:.0f} cm - move back")
            if abs(roll) > HEAD_TILT_DEG:
                alert("posture", "Straighten your head / posture")
        if brightness < DARK_BRIGHTNESS:
            alert("dark", "Room too dark - turn on a light")

        score = strain_score(blink_rate, dist if face else 0,
                             min(since_break, break_every_s) / 60,
                             drowsy_events, break_every_s / 60)

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
            (10, 110), level_color(dist >= MIN_SAFE_DISTANCE_CM))
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
        elif current_alert:
            cv2.rectangle(frame, (0, h - 70), (w, h - 28),
                          AMBER if alert_level == "warn" else ALERT_RED, -1)
            put(frame, current_alert, (15, h - 40), (255, 255, 255), 0.8)

        cv2.imshow("EyeGuard - Eye Strain Monitor", frame)

        # ---------------- log once per second
        if now - last_log >= 1:
            last_log = now
            log.writerow([datetime.now().isoformat(timespec="seconds"), int(face),
                          round(ear, 3), blinks_total, round(blink_rate, 1),
                          round(dist, 1) if face else "", int(looking_away),
                          round(brightness, 1), int(on_break), score, current_alert])
            log_file.flush()

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("c") and face:
            focal_px = iris_width_px(pts) * MIN_SAFE_DISTANCE_CM / IRIS_DIAMETER_CM
            print(f"Calibrated at {MIN_SAFE_DISTANCE_CM} cm (focal = {focal_px:.0f} px)")
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

    cap.release()
    cv2.destroyAllWindows()
    log_file.close()
    print(f"Session saved to {log_path}. Run: python report.py")


if __name__ == "__main__":
    main()
