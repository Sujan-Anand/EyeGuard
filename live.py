"""
Live eye tracking for the website (Live Check page).

Every measurement comes from eyeguard.py: the MediaPipe backend, the Eye
Aspect Ratio, iris distance, head pose, strain score and all the thresholds.
This file only remembers the session between frames. It follows the same
steps as the loop in eyeguard.main(), but takes one frame at a time and has
no window, keyboard or beep, so it can run on a web server.
"""

import os
import shutil
import tempfile
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime

import cv2
import numpy as np
import pandas as pd

import eyeguard as eg
import profiles

# The same values eyeguard.main() uses inside its loop.
LOOK_AWAY_YAW = 0.25             # nose this far off-centre -> looking away
CALIBRATION_FRAMES = 90          # frames used to learn your open-eye EAR
DEFAULT_EAR_THRESHOLD = 0.21
MIN_CLOSED_FRAMES = 2            # shorter than this is noise, not a blink
WARMUP_SECONDS = 15              # blink rate needs this much data first
BLINK_ALERT_AFTER = 30           # no "blink more" alert before this
DEMO_BREAK_SECONDS = 60          # same as  py eyeguard.py --demo
NORMAL_BREAK_SECONDS = 20 * 60

# Website only.
PAUSE_SECONDS = 3                # a gap this long means the video was stopped
MAX_ROWS = 4 * 60 * 60           # keep at most 4 hours of per-second rows
OVERLAY_SCALE = 1.3              # the numbers on the video, compared with the desktop app
COLUMNS = ["timestamp", "face", "ear", "blinks_total", "blink_rate", "distance_cm",
           "looking_away", "brightness", "on_break", "strain_score", "alert"]

_download_lock = threading.Lock()


def ensure_model():
    """Downloads face_landmarker.task (about 4 MB) the first time it is needed
    and keeps it for later runs. Returns the path of the file."""
    with _download_lock:
        folder = os.path.dirname(eg.MODEL_PATH)
        if not os.path.exists(eg.MODEL_PATH) and not os.access(folder, os.W_OK):
            # read-only app folder: keep the model in the temp folder instead
            eg.MODEL_PATH = os.path.join(tempfile.gettempdir(),
                                         os.path.basename(eg.MODEL_PATH))
            folder = tempfile.gettempdir()
        if not os.path.exists(eg.MODEL_PATH):
            # download to a temporary name first so a half-finished file is never used
            handle, part = tempfile.mkstemp(suffix=".task", dir=folder)
            try:
                with os.fdopen(handle, "wb") as out, \
                        urllib.request.urlopen(eg.MODEL_URL, timeout=60) as web:
                    shutil.copyfileobj(web, out)
                os.replace(part, eg.MODEL_PATH)
            finally:
                if os.path.exists(part):
                    os.remove(part)
        return eg.MODEL_PATH


def brightness_of(frame_bgr):
    return float(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).mean())


class EyeTracker:
    """Keeps one visitor's live session. Call process() with every webcam frame."""

    def __init__(self, break_every_s=NORMAL_BREAK_SECONDS):
        self.lock = threading.Lock()         # the video runs in its own thread
        self.break_every_s = break_every_s
        self.backend = None                  # MediaPipe, created on the first frame
        self.pending = set()                 # button presses waiting for the next frame
        self.rows = deque(maxlen=MAX_ROWS)   # one row per second, like the desktop CSV
        self.state = None                    # latest numbers, for the page to show
        self.error = ""                      # set if a frame could not be processed
        self.profile = None                  # set_profile(): glasses, safe distance, calibration
        self.safe_cm = eg.MIN_SAFE_DISTANCE_CM
        self.lens_m = 1.0                    # glasses make the iris look bigger or smaller
        self.glare = None                    # GlareDetector for glasses profiles

        self.focal_px = None                 # set from frame width, or by calibration
        self.calib_ears = []                 # first frames -> personal EAR threshold
        self.ear_threshold = DEFAULT_EAR_THRESHOLD
        self.closed_frames, self.closed_since = 0, None
        self.blink_times = deque()
        self.blinks_total, self.drowsy_events = 0, 0
        self.session_start = None            # set when the first frame arrives
        self.last_break_end = None
        self.on_break, self.break_timer = False, eg.BreakTimer()
        self.last_seen = None
        self.last_log = None                 # the clock second of the last saved row
        self.dist, self.ear, self.looking_away = 0.0, 0.0, False

    # ------------------------------------------------------------ profile
    def set_profile(self, profile):
        """Uses a profile from the My Profile page (None = no profile, the usual
        50 cm limit and no correction). Safe to call on every page run."""
        with self.lock:
            if profile == self.profile:
                return
            was_calibrated = profiles.is_calibrated(self.profile)
            self.profile = dict(profile) if profile else None
            self.safe_cm = profile["safe_distance_cm"] if profile else eg.MIN_SAFE_DISTANCE_CM
            self.lens_m = profiles.distance_factor(profile)
            self.glare = (eg.GlareDetector()
                          if profile and profile["correction"] == "glasses" else None)
            if profiles.is_calibrated(profile):
                self.focal_px = profile["focal_px"]      # a saved calibration wins
            elif was_calibrated:
                self.focal_px = None                     # back to the usual estimate

    def current_profile(self):
        """The profile as it is now (it gains a calibration when you calibrate)."""
        with self.lock:
            return dict(self.profile) if self.profile else None

    # ------------------------------------------------------------ buttons
    def request(self, action):
        """Called by the page buttons: "break", "calibrate" or "reset".
        The action is applied when the next frame arrives."""
        with self.lock:
            self.pending.add(action)

    def snapshot(self):
        """A copy of the latest numbers (None before the first frame)."""
        with self.lock:
            return dict(self.state) if self.state else None

    def is_running(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            return self.last_seen is not None and now - self.last_seen < PAUSE_SECONDS

    def dataframe(self):
        """The session so far, in the same format as an eyeguard.py CSV."""
        with self.lock:
            return pd.DataFrame(list(self.rows), columns=COLUMNS)

    # ------------------------------------------------------------- frames
    def process(self, frame_bgr, now=None):
        """One webcam frame in, the same frame out (mirrored) with the numbers,
        alerts and break screen drawn on it."""
        try:
            frame = cv2.flip(frame_bgr, 1)                   # mirror, like the desktop app
            if self.backend is None:
                self.backend = eg.FaceMeshBackend()
            pts = self.backend.process(frame)
            with self.lock:
                state = self.update(pts, brightness_of(frame), frame.shape[1], now)
                self.error = ""
            return draw_overlay(frame, pts, state)
        except Exception as err:                             # never freeze the video
            self.error = f"{type(err).__name__}: {err}"
            return frame_bgr

    def update(self, pts, brightness, frame_width, now=None):
        """The per-frame logic of eyeguard.main(). pts is the 478 x 2 landmark
        array from the backend, or None when no face is visible."""
        now = time.time() if now is None else now
        if self.session_start is None:
            self.session_start = self.last_break_end = now
        elif now - self.last_seen > PAUSE_SECONDS:
            self._skip_pause(now - self.last_seen)           # video was stopped for a while
        self.last_seen = now
        if self.focal_px is None:
            self.focal_px = frame_width * 0.9                # typical laptop webcam (~60 deg FOV)
        alert, alert_level = "", ""
        face = pts is not None
        roll = 0.0

        if "reset" in self.pending:
            self.blink_times.clear()
            self.blinks_total = self.drowsy_events = 0
            self.session_start = self.last_break_end = now
        if "break" in self.pending:
            self.on_break = True
            self.break_timer.reset()
        if "calibrate" in self.pending and face:
            self.focal_px = (eg.iris_width_px(pts) * eg.MIN_SAFE_DISTANCE_CM
                             / eg.IRIS_DIAMETER_CM)
            self.lens_m = 1.0                    # calibrating with glasses on includes the lens
            if self.profile:
                self.profile = dict(self.profile, focal_px=float(self.focal_px),
                                    calibrated_on=datetime.fromtimestamp(now).date().isoformat())
        self.pending.clear()

        if face:
            self.ear = (eg.eye_aspect_ratio(pts, eg.LEFT_EYE)
                        + eg.eye_aspect_ratio(pts, eg.RIGHT_EYE)) / 2
            yaw, roll = eg.head_pose(pts)
            self.looking_away = abs(yaw) > LOOK_AWAY_YAW
            iris_px = eg.iris_width_px(pts)
            self.dist = eg.distance_cm(iris_px, self.focal_px) * self.lens_m

            # personal threshold: 75% of your normal open-eye EAR
            if len(self.calib_ears) < CALIBRATION_FRAMES:
                self.calib_ears.append(self.ear)
                if len(self.calib_ears) == CALIBRATION_FRAMES:
                    self.ear_threshold = float(
                        np.clip(np.median(self.calib_ears) * 0.75, 0.15, 0.28))

            # blink & drowsiness
            if self.ear < self.ear_threshold:
                self.closed_frames += 1
                self.closed_since = self.closed_since or now
                if now - self.closed_since > eg.DROWSY_SECONDS:
                    alert, alert_level = "You look drowsy - take a proper break!", "alert"
            else:
                closed_for = now - (self.closed_since or now)
                if self.closed_frames >= MIN_CLOSED_FRAMES and closed_for < eg.DROWSY_SECONDS:
                    self.blinks_total += 1
                    self.blink_times.append(now)
                elif self.closed_since and closed_for >= eg.DROWSY_SECONDS:
                    self.drowsy_events += 1
                self.closed_frames, self.closed_since = 0, None
        else:
            self.looking_away = True

        while self.blink_times and now - self.blink_times[0] > 60:
            self.blink_times.popleft()
        elapsed = now - self.session_start
        # blinks per minute over the last 60 s (needs ~15 s of data to be meaningful)
        blink_rate = (len(self.blink_times) * 60 / min(60, elapsed)
                      if elapsed >= WARMUP_SECONDS else 15.0)

        # ---------------- 20-20-20 with verified break
        since_break = now - self.last_break_end
        if not self.on_break and since_break >= self.break_every_s:
            self.on_break = True
            self.break_timer.reset()
        if self.on_break:
            # looking back at the screen pauses the timer; it never resets
            if self.break_timer.update(self.looking_away, now) == "done":
                self.on_break, self.last_break_end = False, now
                since_break = 0.0

        # ---------------- alerts (only when not on break)
        if not self.on_break and face:
            low_blink = eg.blink_alert(blink_rate) if elapsed > BLINK_ALERT_AFTER else None
            if low_blink:                        # "warn" below 7/min, "alert" below 5/min
                alert, alert_level = low_blink
            # on the website only blinking below 5/min and drowsiness are strong
            # (red) alerts; everything else is a gentle amber warning
            if 0 < self.dist < self.safe_cm:
                alert, alert_level = f"Too close! {self.dist:.0f} cm - move back", "warn"
            if abs(roll) > eg.HEAD_TILT_DEG:
                alert, alert_level = "Straighten your head / posture", "warn"
            if self.glare and self.glare.update(iris_px, self.ear, self.ear_threshold, now):
                alert, alert_level = eg.GLARE_MESSAGE, "warn"
        if self.glare and not face:
            self.glare.reset()
        if brightness < eg.DARK_BRIGHTNESS:
            alert, alert_level = "Room too dark - turn on a light", "warn"

        score = eg.strain_score(blink_rate, self.dist if face else 0,
                                min(since_break, self.break_every_s) / 60,
                                self.drowsy_events, self.break_every_s / 60, self.safe_cm)

        self.state = {
            "face": face, "ear": self.ear, "ear_threshold": self.ear_threshold,
            "blinks_total": self.blinks_total, "blink_rate": blink_rate,
            "measuring": elapsed < WARMUP_SECONDS,
            "distance_cm": self.dist if face else None,
            "looking_away": self.looking_away, "brightness": brightness,
            "on_break": self.on_break,
            "break_done_s": self.break_timer.done,       # seconds looked away so far
            "break_state": self.break_timer.state,       # waiting / counting / paused / done
            "next_break_s": max(0.0, self.break_every_s - since_break),
            "strain_score": score, "alert": alert, "alert_level": alert_level,
            "elapsed": elapsed, "safe_cm": self.safe_cm,
            # for the video panel: who is using it, and calibration help
            "profile_lines": ((profiles.to_ascii(self.profile["name"]) or "Profile",
                               profiles.describe(self.profile)) if self.profile else ()),
            "notes": [note for note in (profiles.estimate_note(self.profile),
                                        profiles.calibration_note(self.profile)) if note],
        }

        # ---------------- one row per second, same columns as the desktop CSV
        if int(now) != self.last_log:
            self.last_log = int(now)
            self.rows.append([
                datetime.fromtimestamp(now).isoformat(timespec="seconds"), int(face),
                round(self.ear, 3), self.blinks_total, round(blink_rate, 1),
                round(self.dist, 1) if face else None, int(self.looking_away),
                round(brightness, 1), int(self.on_break), score, alert])
        return self.state

    def _skip_pause(self, gap):
        """The video was stopped and started again: do not count the gap as
        screen time, as a long blink or as time looking away."""
        self.session_start += gap
        self.last_break_end += gap
        self.blink_times = deque(t + gap for t in self.blink_times)
        self.closed_frames, self.closed_since = 0, None
        self.break_timer.hold()                  # the break keeps the seconds already done


# ------------------------------------------------------------------ drawing
def draw_overlay(frame, pts, state):
    """Draws the same panel, strain bar, break screen and alert banner as the
    desktop app onto the frame."""
    h, w = frame.shape[:2]
    face, score = state["face"], state["strain_score"]
    if face:
        for idx in eg.LEFT_EYE + eg.RIGHT_EYE:
            cv2.circle(frame, tuple(int(v) for v in pts[idx]), 1, (0, 255, 255), -1)

    if state["on_break"]:                        # the break screen has the picture to itself
        timer = eg.BreakTimer()                  # same break screen as the desktop app
        timer.done, timer.state = state["break_done_s"], state["break_state"]
        return eg.draw_break_screen(frame, timer)

    # The panel is drawn 30% larger than on the desktop so it stays readable
    # when the video is shown small in a browser or on a projector.
    k = OVERLAY_SCALE if w >= 600 else 1.0

    def at(x, y):
        return int(x * k), int(y * k)

    panel = frame.copy()
    cv2.rectangle(panel, (0, 0), at(300, 190), (30, 30, 30), -1)
    frame = cv2.addWeighted(panel, 0.6, frame, 0.4, 0)
    eg.put(frame, "EyeGuard", at(10, 28), (255, 200, 0), 0.8 * k)
    for row, text in enumerate(state["profile_lines"]):
        eg.put_fit(frame, text, at(132, 15 + 16 * row), int(163 * k), (220, 220, 220), 0.42 * k)
    eg.put(frame, "Blinks/min: measuring..." if state["measuring"]
           else f"Blinks/min: {state['blink_rate']:4.1f}",
           at(10, 60), eg.blink_color(state["blink_rate"]), 0.6 * k)
    eg.put(frame, f"Total blinks: {state['blinks_total']}", at(10, 85), scale=0.6 * k)
    eg.put(frame, f"Distance: {state['distance_cm']:4.0f} cm" if face else "Distance: --",
           at(10, 110), eg.level_color(not face or state["distance_cm"] >= state["safe_cm"]),
           0.6 * k)
    eg.put(frame, f"Next break: {state['next_break_s'] / 60:4.1f} min", at(10, 135), scale=0.6 * k)
    eg.put(frame, f"Strain score: {score}/100", at(10, 160), eg.level_color(score < 50), 0.6 * k)
    eg.put(frame, f"EAR {state['ear']:.2f} (thr {state['ear_threshold']:.2f})",
           at(10, 182), (200, 200, 200), 0.5 * k, 1)

    bar_w = int((w - 20) * score / 100)                      # strain meter along the bottom
    cv2.rectangle(frame, (10, h - 22), (w - 10, h - 8), (60, 60, 60), -1)
    cv2.rectangle(frame, (10, h - 22), (10 + bar_w, h - 8), eg.level_color(score < 50), -1)

    notes = [n.replace("press c", "click Calibrate distance") for n in state["notes"]]
    if notes:                                    # calibration help, on a dark strip
        strip = frame.copy()
        cv2.rectangle(strip, (0, h - 76 - 18 * len(notes)), (w, h - 72), (30, 30, 30), -1)
        frame = cv2.addWeighted(strip, 0.6, frame, 0.4, 0)
        for row, text in enumerate(reversed(notes)):
            eg.put_centred(frame, profiles.to_ascii(text), h - 80 - 18 * row,
                           (255, 255, 255), 0.5, 1)
    if state["alert"]:
        cv2.rectangle(frame, (0, h - 70), (w, h - 28),
                      eg.AMBER if state["alert_level"] == "warn" else eg.ALERT_RED, -1)
        eg.put_centred(frame, state["alert"], h - 40, (255, 255, 255))
    return frame


# ----------------------------------------------------------- single photo
def check_photo(image_bgr):
    """Everything that can be measured from one photo (no blink rate, which
    needs video). Returns (numbers dict, list of alerts, annotated image)."""
    pts = eg.FaceMeshBackend().process(image_bgr)
    brightness = brightness_of(image_bgr)
    numbers = {"face": pts is not None, "brightness": brightness}
    alerts = []
    if brightness < eg.DARK_BRIGHTNESS:
        alerts.append("Room too dark - turn on a light")
    if pts is None:
        return numbers, alerts, image_bgr

    ear = (eg.eye_aspect_ratio(pts, eg.LEFT_EYE) + eg.eye_aspect_ratio(pts, eg.RIGHT_EYE)) / 2
    yaw, roll = eg.head_pose(pts)
    dist = eg.distance_cm(eg.iris_width_px(pts), image_bgr.shape[1] * 0.9)
    numbers.update(ear=ear, distance_cm=dist, roll=roll,
                   looking_away=abs(yaw) > LOOK_AWAY_YAW)
    if 0 < dist < eg.MIN_SAFE_DISTANCE_CM:
        alerts.append(f"Too close! {dist:.0f} cm - move back")
    if abs(roll) > eg.HEAD_TILT_DEG:
        alerts.append("Straighten your head / posture")

    marked = image_bgr.copy()
    dot = max(1, image_bgr.shape[1] // 400)
    for idx in eg.LEFT_EYE + eg.RIGHT_EYE:
        cv2.circle(marked, tuple(int(v) for v in pts[idx]), dot, (0, 255, 255), -1)
    return numbers, alerts, marked
