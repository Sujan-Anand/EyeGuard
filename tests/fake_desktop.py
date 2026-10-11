"""Runs the real eyeguard.main() loop without a webcam, window, sound or clock.

The tests give it a simulated camera: each frame is a picture of a face
looking at the screen (FACE), the same face with closed eyes (CLOSED), the
face up close (NEAR) or an empty grey room (AWAY, nobody in view). A fake
clock moves on by `step` seconds per frame, key presses are scripted, beeps
are counted instead of played, and the text drawn on the video is collected.

The face is a public-domain portrait that ships with matplotlib.
"""

import csv
import glob
import io
import os
import shutil
import signal
import sys
import tempfile

import cv2
import matplotlib.cbook as cbook
import numpy as np

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
import background  # noqa: E402
import eyeguard  # noqa: E402
import profile_window  # noqa: E402
import profiles  # noqa: E402

WIDTH, HEIGHT = 640, 480
REAL_LAST_USED_PATH = profiles.LAST_USED_PATH


def _portrait():
    photo = cv2.imread(str(cbook.get_sample_data("grace_hopper.jpg", asfileobj=False)))
    return cv2.resize(photo, (WIDTH, 750))[:HEIGHT]


def _far(image, scale=0.55):
    """The portrait shrunk onto a grey background: a face about 60 cm away."""
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    canvas = np.full((HEIGHT, WIDTH, 3), 128, np.uint8)
    y, x = (HEIGHT - small.shape[0]) // 2, (WIDTH - small.shape[1]) // 2
    canvas[y:y + small.shape[0], x:x + small.shape[1]] = small
    return canvas


def _closed(image):
    """Paints skin colour over both eyes so they look shut."""
    pts = eyeguard.FaceMeshBackend().process(image)
    out = image.copy()
    for eye in (eyeguard.LEFT_EYE, eyeguard.RIGHT_EYE):
        box = pts[eye]
        x0, x1 = box[:, 0].min(), box[:, 0].max()
        y0, y1 = box[:, 1].min(), box[:, 1].max()
        pad_x, pad_y = 0.25 * (x1 - x0), 0.9 * (y1 - y0) + 2
        x0, x1 = int(x0 - pad_x), int(x1 + pad_x)
        y0, y1 = int(y0 - pad_y), int(y1 + pad_y)
        cheek = image[y1 + 3:y1 + 3 + max(4, y1 - y0), x0:x1].reshape(-1, 3)
        out[y0:y1, x0:x1] = np.median(cheek, axis=0)
        mid = (y0 + y1) // 2 + 1
        cv2.line(out, (x0 + 2, mid), (x1 - 2, mid), (40, 40, 60), 1)
    return out


NEAR = _portrait()                    # about 34 cm: "Too close"
FACE = _far(NEAR)                     # about 60 cm, looking at the screen
CLOSED = _closed(FACE)                # the same, eyes shut
AWAY = np.full((HEIGHT, WIDTH, 3), 128, np.uint8)      # nobody in view


def run_desktop(argv=(), frames=40, step=1.0, keys=None, frame_for=None, typed=(),
                stop_at=None, ctrl_c_at=None, mini_fails=False, break_every=None,
                picks=(), picker_fails=False, picker_takes=0.0):
    """Runs eyeguard.main() for `frames` frames and returns what happened:

    break_every sets how often a break is due, in seconds (normally 20 minutes),
    so a test can reach a break quickly.

    The profile window never really opens. Each time the app asks for it, the
    next entry of `picks` is the answer: ("use", profile), ("none", None) or
    ("cancel", None); when the list runs out the answer is "Continue without
    profile". picker_fails makes the window impossible to open, and
    picker_takes is how many seconds the user spends in it.
    picker   list of (frame number, name of the profile in use when it opened)

    Background mode (--background) gets a pretend notifier and mini window:
    stop_at presses the Stop button at that frame, ctrl_c_at presses Ctrl+C,
    and mini_fails makes the mini window impossible to open.
    toasts   list of (frame number, title, message)
    mini     for each frame the mini window was updated, its four (text, level) lines
    shown    how many frames went to a video window
    sleeps   the pauses asked for between frames (the frame-rate limit)

    beeps    list of (frame number, "short" or "long")
    texts    for each frame, the set of text lines drawn on the video
    banners  for each frame, the colour of the alert bar (None if no bar)
    header, rows   the session CSV (rows without the timestamp column)
    printed  everything printed to the terminal
    """
    keys = keys or {}
    state = {"frame": -1, "t": 1_800_000_000.0}
    beeps, texts, banners = [], [], []
    toasts, mini, sleeps, shown, closed = [], [], [], [], []
    picks, picker = list(picks), []

    def fake_choose(current=None, path=None):
        picker.append((state["frame"], current))
        state["t"] += picker_takes
        if picker_fails:
            raise RuntimeError("no display")
        return picks.pop(0) if picks else ("none", None)

    class FakeCamera:
        def __init__(self, index):
            self.index = index

        def isOpened(self):
            return True

        def read(self):
            state["frame"] += 1
            state["t"] += step
            texts.append(set())
            banners.append(None)
            if state["frame"] >= frames:
                return False, None
            if state["frame"] == ctrl_c_at:
                signal.raise_signal(signal.SIGINT)
            image = frame_for(state["frame"]) if frame_for else FACE
            return True, cv2.flip(image, 1)        # main() mirrors it back

        def release(self):
            pass

    class FakeClock:
        @staticmethod
        def time():
            return state["t"]

        @staticmethod
        def sleep(seconds):
            sleeps.append(seconds)

    class FakeNotifier:
        def show(self, message, title=background.APP_NAME):
            toasts.append((state["frame"], title, message))
            print(f"[{title}] {message}")

    class FakeMini:
        def __init__(self):
            if mini_fails:
                raise RuntimeError("no display")
            self.stopped = False

        def update(self, lines):
            mini.append((state["frame"], lines))
            if state["frame"] == stop_at:
                self.stopped = True

        def close(self):
            closed.append(state["frame"])

    def fake_beep(freq=1000, ms=300, *args, **kwargs):
        beeps.append((state["frame"], "short" if ms < 300 else "long"))

    real_put, real_rectangle = eyeguard.put, cv2.rectangle

    def spy_put(img, text, *args, **kwargs):
        texts[-1].add(text)
        return real_put(img, text, *args, **kwargs)

    def spy_rectangle(img, pt1, pt2, color, *args, **kwargs):
        if tuple(pt1) == (0, img.shape[0] - 70):   # the alert bar
            banners[-1] = tuple(color)
        return real_rectangle(img, pt1, pt2, color, *args, **kwargs)

    saved = (cv2.VideoCapture, cv2.imshow, cv2.waitKey, cv2.destroyAllWindows,
             cv2.rectangle, eyeguard.beep, eyeguard.put, eyeguard.time,
             sys.argv, sys.stdout, sys.stdin, os.getcwd(),
             background.Notifier, background.MiniWindow, eyeguard.BREAK_EVERY_SECONDS,
             profile_window.choose, profiles.LAST_USED_PATH)
    if profiles.LAST_USED_PATH == REAL_LAST_USED_PATH:      # never touch the real note
        profiles.LAST_USED_PATH = os.path.join(tempfile.gettempdir(), "eyeguard_test_last_profile.txt")
    work = tempfile.mkdtemp(prefix="eyeguard_test_")
    out = io.StringIO()
    try:
        cv2.VideoCapture = FakeCamera
        cv2.imshow = lambda *a, **k: shown.append(state["frame"])
        background.Notifier, background.MiniWindow = FakeNotifier, FakeMini
        profile_window.choose = fake_choose
        if break_every is not None:
            eyeguard.BREAK_EVERY_SECONDS = break_every
        cv2.waitKey = lambda *a, **k: ord(keys[state["frame"]]) if state["frame"] in keys else -1
        cv2.destroyAllWindows = lambda *a, **k: None
        cv2.rectangle = spy_rectangle
        eyeguard.beep, eyeguard.put, eyeguard.time = fake_beep, spy_put, FakeClock
        sys.argv, sys.stdout = ["eyeguard.py", *argv], out
        sys.stdin = io.StringIO("".join(line + "\n" for line in typed))
        os.chdir(work)                              # logs/ goes to a temp folder
        eyeguard.main()
    finally:
        (cv2.VideoCapture, cv2.imshow, cv2.waitKey, cv2.destroyAllWindows,
         cv2.rectangle, eyeguard.beep, eyeguard.put, eyeguard.time,
         sys.argv, sys.stdout, sys.stdin) = saved[:11]
        os.chdir(saved[11])
        background.Notifier, background.MiniWindow = saved[12:14]
        eyeguard.BREAK_EVERY_SECONDS = saved[14]
        profile_window.choose = saved[15]
        profiles.LAST_USED_PATH = saved[16]

    header, rows = [], []
    for path in glob.glob(os.path.join(work, "logs", "session_*.csv")):
        with open(path, newline="") as f:
            data = list(csv.reader(f))
        header, rows = data[0], [row[1:] for row in data[1:]]
    files = sorted(os.path.relpath(p, work).replace(os.sep, "/")
                   for p in glob.glob(os.path.join(work, "**", "*"), recursive=True)
                   if os.path.isfile(p))
    shutil.rmtree(work, ignore_errors=True)
    return {"beeps": beeps, "texts": texts[:frames], "banners": banners[:frames],
            "header": header, "rows": rows, "printed": out.getvalue(), "files": files,
            "toasts": toasts, "mini": mini, "shown": len(shown), "sleeps": sleeps,
            "mini_closed": len(closed), "frames_read": state["frame"] + 1, "picker": picker}


def all_text(result):
    """Every different line of text drawn during a run."""
    return set().union(*result["texts"]) if result["texts"] else set()
