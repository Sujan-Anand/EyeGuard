"""Background mode (py eyeguard.py --background): no video window, pop-up
notifications, a small always-on-top box, a pause when nobody is there.

The real main() loop runs with a simulated camera; notifications and the
small box are replaced by stand-ins that record what they were given.

Run all tests with:   py -m unittest discover -s tests -v
"""

import os
import shutil
import signal
import tempfile
import unittest

from fake_desktop import AWAY, CLOSED, FACE, NEAR, run_desktop

import background
import eyeguard
import profiles

COLUMNS = ["timestamp", "face", "ear", "blinks_total", "blink_rate", "distance_cm",
           "looking_away", "brightness", "on_break", "strain_score", "alert"]
BREAK_WORDS = ("Break time", "Break paused", "Break done")


def messages(result, starting=None):
    """The notification texts, in order (only those starting with `starting`)."""
    return [m for _, _, m in result["toasts"] if starting is None or m.startswith(starting)]


def blinking_every(seconds, step=0.1):
    period = round(seconds / step)
    middle = period // 2
    return lambda n: CLOSED if n % period in (middle, middle + 1, middle + 2) else FACE


def break_plan(n):
    """Demo mode, 1 s per frame. The break is due at frame 59: look away for
    12 s, look back for 3 s (the timer pauses), look away for the last 8 s."""
    return AWAY if 65 <= n <= 76 or 80 <= n <= 87 else FACE


class MessagesTest(unittest.TestCase):
    def test_break_messages(self):
        self.assertEqual(background.break_start_message(20), "Break time: look away for 20 s")
        self.assertEqual(background.break_paused_message(12.4, 20),
                         "Break paused at 12/20 s — look away to continue")
        self.assertEqual(background.BREAK_DONE, "Break done ✓")

    def test_settings(self):
        self.assertEqual(background.MAX_FPS, 15)
        self.assertEqual(background.NO_FACE_PAUSE_SECONDS, 120)
        self.assertEqual((background.MINI_WIDTH, background.MINI_HEIGHT), (220, 120))

    def lines(self, **changes):
        values = dict(blink_rate=16.0, measuring=False, dist=60.0, face=True, score=20,
                      on_break=False, break_done=0.0, break_seconds=20, seconds_to_break=754,
                      safe_cm=50, warn_rate=7, alert_rate=5)
        return background.mini_lines(**{**values, **changes})

    def test_mini_window_lines(self):
        self.assertEqual(self.lines(), [("Blinks/min: 16.0", "good"), ("Distance: 60 cm", "good"),
                                        ("Strain: 20/100", "good"), ("Next break in 12:34", "plain")])
        self.assertEqual(self.lines(measuring=True)[0], ("Blinks/min: measuring...", "plain"))
        self.assertEqual(self.lines(face=False)[1], ("Distance: -- (no face)", "plain"))
        self.assertEqual(self.lines(dist=41)[1], ("Distance: 41 cm  too close", "alert"))
        self.assertEqual(self.lines(dist=60, safe_cm=70)[1][1], "alert")     # the profile's own limit
        self.assertEqual(self.lines(score=63)[2], ("Strain: 63/100  high", "alert"))
        self.assertEqual(self.lines(on_break=True, break_done=12.7)[3],
                         ("Break: 12/20 s - look away", "warn"))
        self.assertEqual(self.lines(paused=True)[3], ("Paused: nobody in view", "warn"))
        self.assertEqual(self.lines(seconds_to_break=-3)[3], ("Next break in 0:00", "plain"))

    def test_mini_window_keeps_the_blink_levels(self):
        for rate, text, level in [(7.0, "Blinks/min: 7.0", "good"),
                                  (6.9, "Blinks/min: 6.9  low", "warn"),
                                  (5.0, "Blinks/min: 5.0  low", "warn"),
                                  (4.9, "Blinks/min: 4.9  very low", "alert")]:
            self.assertEqual(self.lines(blink_rate=rate)[0], (text, level))

    def test_notifier_never_stops_the_app(self):
        class Broken:
            def __init__(self, **kwargs):
                raise OSError("toasts are switched off")

        notifier = background.Notifier()
        notifier._toast = Broken
        notifier.show("Blink more! Only 6/min")                  # must not raise
        notifier.show("Too close! 41 cm - move back")
        self.assertIsNone(notifier._toast)                       # gave up on pop-ups, quietly
        self.assertEqual([m for _, m in notifier.sent],
                         ["Blink more! Only 6/min", "Too close! 41 cm - move back"])


class WebsiteDoesNotNeedItTest(unittest.TestCase):
    def test_nothing_from_background_mode_is_loaded_by_the_website(self):
        import subprocess
        import sys
        project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = ("import sys, eyeguard, live; "
                "print(sorted(m for m in ('background', 'tkinter', 'winotify') if m in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code], cwd=project, capture_output=True,
                              text=True, timeout=120)
        self.assertEqual(done.stdout.strip().splitlines()[-1], "[]", done.stderr[-500:])
        with open(os.path.join(project, "requirements.txt"), encoding="utf-8") as f:
            self.assertNotIn("winotify", f.read())               # the cloud build stays as it was
        with open(os.path.join(project, "requirements-desktop.txt"), encoding="utf-8") as f:
            self.assertIn('winotify==1.1.0; sys_platform == "win32"', f.read())


class RealMiniWindowTest(unittest.TestCase):
    """The real tkinter box (skipped where there is no desktop to draw on)."""

    def setUp(self):
        try:
            self.box = background.MiniWindow()
        except Exception as err:
            self.skipTest(f"no desktop: {err}")

    def tearDown(self):
        self.box.close()
        self.box.close()                                         # closing twice is harmless

    def test_size_on_top_and_live_numbers(self):
        root = self.box.root
        self.assertEqual((root.winfo_width(), root.winfo_height()), (220, 120))
        self.assertTrue(root.attributes("-topmost"))
        self.assertTrue(root.overrideredirect())                 # no title bar
        self.assertLessEqual(root.winfo_x() + 220, root.winfo_screenwidth())      # on the screen
        self.assertLessEqual(root.winfo_y() + 120, root.winfo_screenheight())
        lines = [("Blinks/min: 6.2  low", "warn"), ("Distance: 41 cm  too close", "alert"),
                 ("Strain: 20/100", "good"), ("Next break in 12:34", "plain")]
        self.box.update(lines)
        self.assertEqual([label.cget("text") for label in self.box.labels], [t for t, _ in lines])
        self.assertEqual([label.cget("fg") for label in self.box.labels],
                         [background.AMBER, background.ALERT, background.GOOD, background.INK])
        root.update_idletasks()
        for label in self.box.labels:                            # nothing cut off or pushed out
            self.assertLessEqual(label.winfo_reqwidth(), 220 - 16, label.cget("text"))
            self.assertLessEqual(label.winfo_y() + label.winfo_height(), 120)

    def test_the_longest_lines_still_fit(self):
        self.box.update([("Blinks/min: measuring...", "plain"),
                         ("Distance: 100 cm  too close", "alert"),
                         ("Strain: 100/100  high", "alert"),
                         ("Break: 19/20 s - look away", "warn")])
        self.box.root.update_idletasks()
        for label in self.box.labels:
            self.assertLessEqual(label.winfo_reqwidth(), 220 - 16, label.cget("text"))

    def test_drag_and_stop(self):
        import types
        root = self.box.root
        x, y = root.winfo_x(), root.winfo_y()
        self.box._grab(types.SimpleNamespace(x_root=x + 10, y_root=y + 10))
        self.box._drag(types.SimpleNamespace(x_root=x - 90, y_root=y - 140))
        root.update()
        self.assertEqual((root.winfo_x(), root.winfo_y()), (x - 100, y - 150))
        self.assertFalse(self.box.stopped)
        button = next(w for w in root.winfo_children()[0].winfo_children() if w.winfo_class() == "Button")
        self.assertEqual(button.cget("text"), "Stop")
        button.invoke()
        self.assertTrue(self.box.stopped)
        self.box.update([("a", "good")] * 4)                     # ignored after Stop, no error

    def test_closing_the_box_another_way_counts_as_stop(self):
        self.box.root.destroy()
        self.box.update([("a", "good")] * 4)
        self.assertTrue(self.box.stopped)


class NormalModeUnchangedTest(unittest.TestCase):
    def test_no_notifications_no_limit_and_a_window(self):
        r = run_desktop(frames=40, step=1.0)
        self.assertEqual((r["toasts"], r["mini"], r["sleeps"]), ([], [], []))
        self.assertEqual(r["shown"], 40)
        self.assertIn("Press q to quit", r["printed"])

    def test_the_session_file_is_the_same_in_both_modes(self):
        plan = lambda n: NEAR if 20 <= n < 30 else AWAY if 40 <= n < 45 else FACE   # noqa: E731
        normal = run_desktop(["--demo"], frames=90, step=1.0, frame_for=plan)
        hidden = run_desktop(["--demo", "--background"], frames=90, step=1.0, frame_for=plan)
        self.assertEqual(normal["header"], COLUMNS)
        self.assertEqual(hidden["header"], COLUMNS)
        self.assertEqual(hidden["rows"], normal["rows"])
        self.assertEqual(hidden["beeps"], normal["beeps"])
        self.assertEqual(len(hidden["files"]), 1)                 # the CSV and nothing else

    def test_no_mini_alone_is_harmless(self):
        r = run_desktop(["--no-mini"], frames=5)
        self.assertIn("--no-mini only does something together with --background", r["printed"])
        self.assertEqual(r["shown"], 5)


class BackgroundModeTest(unittest.TestCase):
    def test_no_window_and_at_most_15_frames_a_second(self):
        r = run_desktop(["--background"], frames=30, step=0.01)
        self.assertEqual(r["shown"], 0)                          # nothing drawn on screen
        self.assertEqual(len(r["sleeps"]), 30)                   # waits after every frame
        self.assertTrue(all(abs(s - 1 / 15) < 1e-9 for s in r["sleeps"]))
        self.assertEqual(len(r["mini"]), 30)
        self.assertIn("running in the background", r["printed"])
        self.assertIn("Stop button", r["printed"])

    def test_too_close_and_blink_notifications_with_the_same_cooldown(self):
        r = run_desktop(["--background"], frames=700, step=0.1,
                        frame_for=lambda n: NEAR if 100 <= n < 500 else FACE)
        close = [(n, m) for n, _, m in r["toasts"] if m.startswith("Too close!")]
        self.assertTrue(close and close[0][0] == 100, close[:1])
        self.assertRegex(close[0][1], r"^Too close! \d+ cm - move back$")
        frames = [n for n, _ in close]
        self.assertTrue(all(b - a > 150 for a, b in zip(frames, frames[1:])))     # 15 s apart
        self.assertEqual(len(close), 3)                                           # 40 s too close
        blink = [n for n, _, m in r["toasts"] if m == "Blink now! Only 0/min"]    # never blinked
        self.assertTrue(blink and blink[0] * 0.1 >= 30)
        # every notification comes with its beep, and nothing beeps without one
        self.assertEqual([n for n, _ in r["beeps"]], [n for n, _, _ in r["toasts"]])

    def test_blink_warning_level(self):
        r = run_desktop(["--background", "--no-mini"], frames=650, step=0.1,
                        frame_for=blinking_every(10))                             # 6 a minute
        blink = messages(r, "Blink")
        self.assertIn("Blink more! Only 6/min", blink)
        self.assertFalse(any(m.startswith("Blink now!") for m in blink))          # warning, not strong
        self.assertEqual(r["mini"], [])

    def test_drowsy_notification(self):
        # The eye-opening reading is forced shut for 4 s (the pretend closed-eye
        # picture is only just closed enough for a blink).
        seen = {"frame": 0}
        real = eyeguard.eye_aspect_ratio

        def plan(n):
            seen["frame"] = n
            return FACE

        eyeguard.eye_aspect_ratio = lambda pts, idx: 0.05 if 100 <= seen["frame"] < 140 else real(pts, idx)
        try:
            r = run_desktop(["--background"], frames=160, step=0.1, frame_for=plan)
        finally:
            eyeguard.eye_aspect_ratio = real
        self.assertEqual(messages(r), ["You look drowsy - take a proper break!"])
        self.assertEqual(len(r["beeps"]), 1)

    def test_break_with_pause_and_continue(self):
        r = run_desktop(["--demo", "--background"], frames=95, step=1.0, frame_for=break_plan)
        breaks = [(n, m) for n, _, m in r["toasts"] if m.startswith(BREAK_WORDS)]
        self.assertEqual(breaks, [(59, "Break time: look away for 20 s"),
                                  (77, "Break paused at 12/20 s — look away to continue"),
                                  (87, "Break done ✓")])
        kinds = dict(r["beeps"])
        self.assertEqual((kinds[59], kinds[77], kinds[87]), ("long", "short", "long"))
        box = dict(r["mini"])
        self.assertEqual(box[58][3], ("Next break in 0:01", "plain"))
        self.assertEqual(box[70][3], ("Break: 6/20 s - look away", "warn"))
        self.assertEqual(box[78][3], ("Break: 12/20 s - look away", "warn"))      # held while paused
        self.assertEqual(box[88][3], ("Next break in 0:59", "plain"))
        on_break = [row[7] for row in r["rows"]]
        self.assertEqual(on_break[58:88], ["0"] + ["1"] * 28 + ["0"])             # logged as before

    def test_mute_silences_the_beeps_but_keeps_the_notifications(self):
        r = run_desktop(["--demo", "--background", "--mute"], frames=95, step=1.0,
                        frame_for=break_plan)
        self.assertEqual(r["beeps"], [])
        self.assertEqual(messages(r, BREAK_WORDS)[-1], "Break done ✓")
        self.assertEqual(len(messages(r, BREAK_WORDS)), 3)

    def test_pauses_when_nobody_is_there_and_continues_by_itself(self):
        r = run_desktop(["--background"], frames=175, step=1.0,
                        frame_for=lambda n: AWAY if 10 <= n < 150 else FACE)
        paused = [(n, t, m) for n, t, m in r["toasts"] if t == background.PAUSED_TITLE]
        self.assertEqual(paused, [(130, "EyeGuard paused", background.PAUSED_MESSAGE)])   # once, at 2 min
        self.assertFalse([n for n, _, _ in r["toasts"] if 130 < n < 150])         # then quiet
        self.assertFalse([n for n, _ in r["beeps"] if 130 <= n < 150])
        box = dict(r["mini"])
        self.assertEqual(box[129][3][0][:10], "Next break")
        self.assertEqual(box[140][3], ("Paused: nobody in view", "warn"))
        self.assertNotEqual(box[150][3][0], "Paused: nobody in view")             # back again
        self.assertIn("Face seen again: EyeGuard continues.", r["printed"])
        self.assertTrue([n for n, _, m in r["toasts"] if n >= 150 and m.startswith("Blink")])
        self.assertEqual(len(r["rows"]), 175)                                     # still logged

    def test_a_short_absence_is_not_a_pause(self):
        r = run_desktop(["--background"], frames=140, step=1.0,
                        frame_for=lambda n: AWAY if 10 <= n < 125 else FACE)      # 115 s away
        self.assertNotIn(background.PAUSED_TITLE, [t for _, t, _ in r["toasts"]])

    def test_the_stop_button_ends_and_saves_the_session(self):
        r = run_desktop(["--background"], frames=60, step=1.0, stop_at=20)
        self.assertEqual(r["frames_read"], 21)
        self.assertEqual(r["mini_closed"], 1)
        self.assertEqual(len(r["rows"]), 21)
        self.assertIn("Session saved to", r["printed"])

    def test_ctrl_c_ends_and_saves_the_session(self):
        before = signal.getsignal(signal.SIGINT)
        for argv in (["--background", "--no-mini"], ["--background"], []):        # normal mode too
            r = run_desktop(argv, frames=60, step=1.0, ctrl_c_at=15)
            self.assertEqual(r["frames_read"], 16, argv)          # finishes the frame, then stops
            self.assertEqual(len(r["rows"]), 16, argv)
            self.assertIn("Session saved to", r["printed"])
            self.assertIs(signal.getsignal(signal.SIGINT), before)                # handed back
        self.assertIn("Stop with Ctrl+C in this window.",
                      run_desktop(["--background", "--no-mini"], frames=2)["printed"])

    def test_carries_on_if_the_small_box_cannot_open(self):
        r = run_desktop(["--background"], frames=20, step=1.0, mini_fails=True)
        self.assertIn("Mini window not shown (no display). Stop with Ctrl+C.", r["printed"])
        self.assertEqual((r["frames_read"], len(r["rows"]), r["mini"]), (21, 20, []))


class BackgroundWithProfileTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="eyeguard_profiles_")
        self.real_path = profiles.PROFILES_PATH
        profiles.PROFILES_PATH = os.path.join(self.folder, "profiles.json")
        profiles.save(profiles.make("Careful", "none", 0.0, 70))

    def tearDown(self):
        profiles.PROFILES_PATH = self.real_path
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_profiles_safe_distance_is_used(self):
        r = run_desktop(["--background", "--profile", "Careful"], frames=12)      # about 60 cm
        close = messages(r, "Too close!")
        self.assertEqual(len(close), 1)                           # under this profile's 70 cm
        self.assertEqual(dict(r["mini"])[5][1][1], "alert")
        self.assertIn("too close", dict(r["mini"])[5][1][0])
        plain = run_desktop(["--background"], frames=12)                          # usual 50 cm limit
        self.assertEqual(messages(plain, "Too close!"), [])


if __name__ == "__main__":
    unittest.main()
