"""
Background mode for eyeguard.py (py eyeguard.py --background).

EyeGuard keeps watching through the webcam with no video window, so you can
get on with your work. Two things replace the window:

  * Notifier    Windows toast notifications for alerts and breaks
  * MiniWindow  a small always-on-top box with the live numbers and a Stop button

Both are only loaded when background mode is used, so the website (which
imports eyeguard.py on a Linux server) never needs them.
"""

import sys

APP_NAME = "EyeGuard"
MINI_WIDTH, MINI_HEIGHT = 220, 120
MAX_FPS = 15                         # background mode reads the camera this often at most
NO_FACE_PAUSE_SECONDS = 120          # nobody in view this long -> "EyeGuard paused"

BREAK_DONE = "Break done ✓"
PAUSED_TITLE = "EyeGuard paused"
PAUSED_MESSAGE = "No face seen for 2 minutes. EyeGuard continues when you are back."

# same colours as the website
BACKGROUND, SURFACE, INK, MUTED = "#0B1F21", "#12302F", "#E8F1EF", "#A9C4C0"
AMBER, ALERT, GOOD = "#F2A541", "#F26B5B", "#5CC08A"


# ------------------------------------------------------------ the messages
def break_start_message(seconds):
    return f"Break time: look away for {seconds} s"


def break_paused_message(done, seconds):
    return f"Break paused at {int(done + 1e-6)}/{seconds} s — look away to continue"


def mini_lines(blink_rate, measuring, dist, face, score, on_break, break_done, break_seconds,
               seconds_to_break, safe_cm, warn_rate, alert_rate, paused=False):
    """The four lines of the mini window as (text, level): level is "good",
    "warn", "alert" or "plain". The words carry the meaning, not just the colour."""
    if measuring:
        blink = ("Blinks/min: measuring...", "plain")
    elif blink_rate < alert_rate:
        blink = (f"Blinks/min: {blink_rate:.1f}  very low", "alert")
    elif blink_rate < warn_rate:
        blink = (f"Blinks/min: {blink_rate:.1f}  low", "warn")
    else:
        blink = (f"Blinks/min: {blink_rate:.1f}", "good")

    if not face:
        distance = ("Distance: -- (no face)", "plain")
    elif dist < safe_cm:
        distance = (f"Distance: {dist:.0f} cm  too close", "alert")
    else:
        distance = (f"Distance: {dist:.0f} cm", "good")

    strain = (f"Strain: {score}/100" + ("  high" if score >= 50 else ""),
              "alert" if score >= 50 else "good")

    if paused:
        last = ("Paused: nobody in view", "warn")
    elif on_break:
        last = (f"Break: {int(break_done + 1e-6)}/{break_seconds} s - look away", "warn")
    else:
        minutes, seconds = divmod(int(max(0, seconds_to_break)), 60)
        last = (f"Next break in {minutes}:{seconds:02d}", "plain")
    return [blink, distance, strain, last]


# ---------------------------------------------------------- notifications
def toast_text(text):
    """Text that is safe to hand to Windows: the pop-up is built by a small
    PowerShell script, where $ and ` have a special meaning."""
    return str(text).replace("`", "'").replace("$", "`$").replace("]]>", "]] >").replace('"', "'")


class Notifier:
    """Shows Windows toast notifications. Every message is also printed, so
    nothing is lost if toasts are switched off or this is not Windows.
    The toasts are silent: EyeGuard plays its own sounds (and --mute stops them)."""

    def __init__(self):
        self.sent = []                   # (title, message) of everything shown
        self._toast = None
        self._warned = False
        if not sys.platform.startswith("win"):
            self._warn("toast notifications need Windows")
            return
        try:
            from winotify import Notification
            self._toast = Notification
        except ImportError:
            self._warn("the winotify package is not installed "
                       "(py -m pip install -r requirements-desktop.txt)")

    def _warn(self, reason):
        if not self._warned:             # say so once, not for every message
            self._warned = True
            print(f"Note: no pop-up notifications ({reason}). "
                  "Messages are printed here instead.")

    def show(self, message, title=APP_NAME):
        self.sent.append((title, message))
        print(f"[{title}] {message}")
        if self._toast is None:
            return
        try:
            self._toast(app_id=APP_NAME, title=toast_text(title), msg=toast_text(message),
                        duration="short").show()
        except Exception as err:         # a failed pop-up must never stop the monitoring
            self._toast = None
            self._warn(str(err) or type(err).__name__)


# ------------------------------------------------------------ mini window
class MiniWindow:
    """A small always-on-top box (about 220 x 120) with the live numbers and a
    Stop button. Drag it anywhere with the mouse. `stopped` turns True when
    Stop is pressed or the box is closed."""

    COLOURS = {"good": GOOD, "warn": AMBER, "alert": ALERT, "plain": INK}

    def __init__(self):
        import tkinter as tk
        self._tk = tk
        self.stopped = False
        self.root = root = tk.Tk()
        root.title(APP_NAME)
        root.overrideredirect(True)                  # no title bar: it stays small
        root.attributes("-topmost", True)
        root.configure(bg=BACKGROUND, highlightthickness=1, highlightbackground=AMBER)
        x = root.winfo_screenwidth() - MINI_WIDTH - 24           # bottom right corner
        y = root.winfo_screenheight() - MINI_HEIGHT - 80
        root.geometry(f"{MINI_WIDTH}x{MINI_HEIGHT}+{x}+{y}")
        root.protocol("WM_DELETE_WINDOW", self.stop)

        top = tk.Frame(root, bg=BACKGROUND)
        top.pack(fill="x", padx=8, pady=(5, 1))
        title = tk.Label(top, text=APP_NAME, bg=BACKGROUND, fg=AMBER,
                         font=("Segoe UI", -14, "bold"))
        title.pack(side="left")
        tk.Button(top, text="Stop", command=self.stop, bg=SURFACE, fg=INK,
                  activebackground=AMBER, activeforeground=BACKGROUND, relief="flat",
                  font=("Segoe UI", -11, "bold"), padx=8, pady=0, cursor="hand2").pack(side="right")
        self.labels = []
        for _ in range(4):
            label = tk.Label(root, text="", bg=BACKGROUND, fg=INK, anchor="w",
                             font=("Segoe UI", -12))     # sizes in pixels: the same
                                                         # at any Windows display scale
            label.pack(fill="x", padx=8)
            self.labels.append(label)

        for widget in (root, top, title, *self.labels):          # drag from anywhere
            widget.bind("<ButtonPress-1>", self._grab)
            widget.bind("<B1-Motion>", self._drag)
        root.update()

    def _grab(self, event):
        self._offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event):
        self.root.geometry(f"+{event.x_root - self._offset[0]}+{event.y_root - self._offset[1]}")

    def stop(self):
        self.stopped = True

    def update(self, lines):
        """Shows the four (text, level) lines and handles mouse clicks."""
        if self.stopped:
            return
        try:
            for label, (text, level) in zip(self.labels, lines):
                label.configure(text=text, fg=self.COLOURS.get(level, INK))
            self.root.update()
        except self._tk.TclError:        # the box was closed some other way
            self.stopped = True

    def close(self):
        try:
            self.root.destroy()
        except self._tk.TclError:
            pass
