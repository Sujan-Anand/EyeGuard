"""
EyeGuard - Smart Eye Strain Monitor for Students
PySustain-2026 | Track 1: Code to Cure | SDG 3.4

Uses your webcam + MediaPipe Face Mesh to track:
  * Blink rate (Eye Aspect Ratio)          -> alerts when you blink too little
  * Distance from the screen (iris size)   -> alerts when you sit too close
  * Drowsiness (eyes closed > 2 s)
  * Head tilt (posture) and room lighting
  * 20-20-20 rule with a VERIFIED break (camera checks you really looked away)
  * Live Eye Strain Score (0-100), logged to CSV for report.py

Run:   python eyeguard.py            (normal: break every 20 min)
       python eyeguard.py --demo     (break every 60 s - for the judges' demo)
Keys:  q = quit   c = calibrate distance (sit 50 cm away first)
       b = start a break now   r = reset session counters
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

# ---------------------------------------------------------------- settings
CAMERA_INDEX = 0
IRIS_DIAMETER_CM = 1.17          # human iris is ~11.7 mm for almost everyone
MIN_SAFE_DISTANCE_CM = 50        # closer than this -> "too close"
LOW_BLINK_RATE = 10              # blinks/min; normal is ~15-20
DROWSY_SECONDS = 2.0             # eyes closed this long -> drowsy
BREAK_LOOK_AWAY_SECONDS = 20     # the "20 seconds" of 20-20-20
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


def beep():
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(1000, 300)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


# ------------------------------------------------------------- drawing
def put(img, text, pos, color=(255, 255, 255), scale=0.6, thick=2):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


def level_color(good):
    return (80, 200, 80) if good else (60, 60, 230)


# ------------------------------------------------------------- main app
def main():
    ap = argparse.ArgumentParser(description="EyeGuard eye strain monitor")
    ap.add_argument("--demo", action="store_true", help="break every 60 s instead of 20 min")
    ap.add_argument("--camera", type=int, default=CAMERA_INDEX)
    args = ap.parse_args()
    break_every_s = 60 if args.demo else 20 * 60

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
    on_break, break_look_start = False, None
    last_alert = {}
    current_alert = ""
    last_log = 0.0
    dist = 0.0
    ear = 0.0
    looking_away = False

    def alert(key, msg):
        nonlocal current_alert
        current_alert = msg
        now = time.time()
        if now - last_alert.get(key, 0) > ALERT_COOLDOWN:
            last_alert[key] = now
            beep()

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
            on_break, break_look_start = True, None
            beep()
        if on_break:
            if looking_away:
                break_look_start = break_look_start or now
                if now - break_look_start >= BREAK_LOOK_AWAY_SECONDS:
                    on_break, last_break_end = False, now
                    beep()
            else:
                break_look_start = None   # looked back at screen -> timer resets

        # ---------------- alerts (only when not on break)
        if not on_break and face:
            if elapsed > 30 and blink_rate < LOW_BLINK_RATE:
                alert("blink", f"Blink more! Only {blink_rate:.0f}/min")
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
        cv2.rectangle(panel, (0, 0), (300, 215), (30, 30, 30), -1)
        frame = cv2.addWeighted(panel, 0.6, frame, 0.4, 0)
        put(frame, "EyeGuard", (10, 28), (255, 200, 0), 0.8)
        put(frame, f"Blinks/min: {blink_rate:4.1f}" if elapsed >= 15 else "Blinks/min: measuring...",
            (10, 60), level_color(blink_rate >= LOW_BLINK_RATE))
        put(frame, f"Total blinks: {blinks_total}", (10, 85))
        put(frame, f"Distance: {dist:4.0f} cm" if face else "Distance: --",
            (10, 110), level_color(dist >= MIN_SAFE_DISTANCE_CM))
        mins_left = max(0, break_every_s - since_break) / 60
        put(frame, f"Next break: {mins_left:4.1f} min", (10, 135))
        put(frame, f"Strain score: {score}/100", (10, 160), level_color(score < 50))
        put(frame, f"EAR {ear:.2f} (thr {ear_threshold:.2f})", (10, 185), (200, 200, 200), 0.5, 1)
        put(frame, "q quit | c calibrate | b break | r reset", (10, 207), (200, 200, 200), 0.45, 1)

        bar_w = int((w - 20) * score / 100)
        cv2.rectangle(frame, (10, h - 20), (w - 10, h - 8), (60, 60, 60), -1)
        cv2.rectangle(frame, (10, h - 20), (10 + bar_w, h - 8), level_color(score < 50), -1)

        if on_break:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (120, 60, 0), -1)
            frame = cv2.addWeighted(overlay, 0.45, frame, 0.55, 0)
            done = (now - break_look_start) if break_look_start else 0
            put(frame, "20-20-20 BREAK", (w // 2 - 150, h // 2 - 40), (255, 255, 255), 1.1, 3)
            put(frame, "Look at something 20 feet away", (w // 2 - 210, h // 2), (255, 255, 255), 0.8)
            msg = (f"Good! {BREAK_LOOK_AWAY_SECONDS - done:.0f} s left" if break_look_start
                   else "Still looking at the screen - timer paused")
            put(frame, msg, (w // 2 - 200, h // 2 + 40),
                (80, 230, 80) if break_look_start else (80, 80, 255), 0.8)
        elif current_alert:
            cv2.rectangle(frame, (0, h - 70), (w, h - 28), (0, 0, 200), -1)
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
            on_break, break_look_start = True, None
        if key == ord("r"):
            blink_times.clear()
            blinks_total = drowsy_events = 0
            session_start = last_break_end = now

    cap.release()
    cv2.destroyAllWindows()
    log_file.close()
    print(f"Session saved to {log_path}. Run: python report.py")


if __name__ == "__main__":
    main()
