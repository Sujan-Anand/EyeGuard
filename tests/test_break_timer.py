"""The 20-20-20 break timer pauses when you look back; it does not reset.

Run all tests with:   py -m unittest discover -s tests -v
"""

import unittest

from fake_desktop import AWAY, FACE, all_text, run_desktop

import eyeguard
import live


def feed(timer, looking_away, seconds, now, step=0.1):
    """Feeds the timer frames for `seconds`. Returns (events, new time)."""
    events = []
    for _ in range(round(seconds / step)):
        now += step
        event = timer.update(looking_away, now)
        if event:
            events.append(event)
    return events, now


class BreakTimerTest(unittest.TestCase):
    def start(self):
        timer = eyeguard.BreakTimer()
        timer.update(False, 100.0)               # break starts, user still at the screen
        return timer, 100.0

    def test_away_8_back_then_away_12_completes_at_20(self):
        timer, now = self.start()
        events, now = feed(timer, True, 8, now)
        self.assertEqual(events, [])
        self.assertAlmostEqual(timer.done, 8.0, places=3)

        events, now = feed(timer, False, 5, now)           # looks back for 5 s
        self.assertEqual(events, ["paused"])               # exactly one pause
        self.assertEqual(timer.state, "paused")
        self.assertAlmostEqual(timer.done, 8.0, places=3)  # stays at 8, no reset

        events, now = feed(timer, True, 11.9, now)         # looks away again
        self.assertEqual(events, [])
        self.assertEqual(timer.state, "counting")
        self.assertAlmostEqual(timer.done, 19.9, places=3)
        events, now = feed(timer, True, 0.1, now)
        self.assertEqual(events, ["done"])                 # 8 + 12 = 20
        self.assertEqual(timer.done, 20.0)

    def test_a_short_glance_does_not_pause(self):
        timer, now = self.start()
        feed(timer, True, 5, now)
        now += 5
        events, now = feed(timer, False, 0.3, now)         # 0.3 s glance at the screen
        self.assertEqual(events, [])
        self.assertEqual(timer.state, "counting")
        events, now = feed(timer, True, 2, now)
        self.assertEqual(events, [])
        self.assertAlmostEqual(timer.done, 7.3, places=3)  # the glance still counted

    def test_looking_back_for_half_a_second_pauses(self):
        timer, now = self.start()
        feed(timer, True, 5, now)
        now += 5
        events, now = feed(timer, False, 0.4, now)
        self.assertEqual(events, [])
        events, now = feed(timer, False, 0.1, now)
        self.assertEqual(events, ["paused"])
        self.assertAlmostEqual(timer.done, 5.0, places=3)  # time facing the screen is not counted

    def test_one_pause_event_each_time_you_look_back(self):
        timer, now = self.start()
        events = []
        for _ in range(3):                                 # away 3 s, back 2 s, three times
            got, now = feed(timer, True, 3, now)
            events += got
            got, now = feed(timer, False, 2, now)
            events += got
        self.assertEqual(events, ["paused", "paused", "paused"])
        self.assertAlmostEqual(timer.done, 9.0, places=3)

    def test_staring_at_the_screen_never_starts_or_finishes_the_timer(self):
        timer, now = self.start()
        events, now = feed(timer, False, 120, now)
        self.assertEqual(events, [])                       # no pause event: it never started
        self.assertEqual((timer.state, timer.done), ("waiting", 0.0))

    def test_a_frozen_camera_cannot_finish_the_break(self):
        timer, now = self.start()
        feed(timer, True, 2, now)
        self.assertIsNone(timer.update(True, now + 2 + 600))   # 10 minute gap between frames
        self.assertLessEqual(timer.done, 2 + eyeguard.MAX_FRAME_GAP + 0.01)

    def test_messages(self):
        timer, now = self.start()
        self.assertEqual(timer.status(), ("Look away to start the timer (0/20 s)", "warn"))
        _, now = feed(timer, True, 12, now)
        self.assertEqual(timer.status(), ("Good! Keep looking away (12/20 s)", "good"))
        feed(timer, False, 1, now)
        self.assertEqual(timer.status(), ("Paused - look away to continue (12/20 s)", "warn"))


def break_plan(n):
    """Half a second per frame. Frames 0-2 at the screen (b pressed at frame 2),
    3-19 looking away (8 s), 20-25 back at the screen (3 s), then away again."""
    return FACE if n < 3 or 20 <= n < 26 else AWAY


class DesktopBreakTest(unittest.TestCase):
    """The real main() loop with a simulated camera, break started with the b key."""

    def run_break(self, argv=()):
        return run_desktop(["--demo", *argv], frames=60, step=0.5, keys={2: "b"},
                           frame_for=break_plan)

    def test_pause_keeps_the_seconds_and_beeps_once(self):
        r = self.run_break()
        paused = [n for n, texts in enumerate(r["texts"])
                  if any(t.startswith("Paused - look away to continue") for t in texts)]
        self.assertEqual(paused, list(range(20, 26)))       # the six frames spent looking back
        for n in paused:
            self.assertIn("Paused - look away to continue (8/20 s)", r["texts"][n])
        self.assertIn("Good! Keep looking away (8/20 s)", r["texts"][19])
        self.assertIn("Good! Keep looking away (9/20 s)", r["texts"][27])   # continues from 8
        # one short beep when it pauses, one normal beep when the break is done (8 + 12 = 20 s)
        self.assertEqual(r["beeps"], [(20, "short"), (49, "long")])
        on_break = [row[7] for row in r["rows"]]            # one row per second
        self.assertEqual(on_break.count("1"), 23)           # 8 s away + 3 s paused + 12 s away
        self.assertEqual(on_break[-1], "0")                 # and it did finish

    def test_no_beep_when_muted(self):
        r = self.run_break(["--mute"])
        self.assertEqual(r["beeps"], [])
        self.assertIn("Paused - look away to continue (8/20 s)", all_text(r))
        self.assertEqual([row[7] for row in r["rows"]][-1], "0")    # break still completes

    def test_a_glance_does_not_pause_or_beep(self):
        def frame_for(n):                                   # 0.1 s per frame
            return FACE if n < 3 or 53 <= n < 56 else AWAY  # a 0.3 s glance after 5 s
        r = run_desktop(["--demo"], frames=120, step=0.1, keys={2: "b"}, frame_for=frame_for)
        self.assertFalse(any(t.startswith("Paused") for t in all_text(r)))
        self.assertEqual([kind for _, kind in r["beeps"]], [])      # not finished yet either
        self.assertIn("Good! Keep looking away (11/20 s)", all_text(r))

    def test_the_csv_columns_are_unchanged(self):
        r = self.run_break()
        self.assertEqual(r["header"], ["timestamp", "face", "ear", "blinks_total", "blink_rate",
                                       "distance_cm", "looking_away", "brightness", "on_break",
                                       "strain_score", "alert"])


class WebsiteBreakTest(unittest.TestCase):
    """The Live Check tracker uses the same BreakTimer."""

    def test_pause_and_continue(self):
        face = eyeguard.FaceMeshBackend().process(FACE)
        tracker = live.EyeTracker(break_every_s=60)
        now = 1_800_000_000.0

        def run(pts, seconds):
            nonlocal now
            state = None
            for _ in range(round(seconds / 0.1)):
                now += 0.1
                state = tracker.update(pts, 120.0, 640, now)
            return state

        run(face, 1)
        tracker.request("break")
        state = run(face, 1)
        self.assertEqual((state["on_break"], state["break_state"]), (True, "waiting"))
        state = run(None, 8)                                # walks away: nobody in view
        self.assertEqual(state["break_state"], "counting")
        self.assertAlmostEqual(state["break_done_s"], 8.0, places=2)
        state = run(face, 4)
        self.assertEqual(state["break_state"], "paused")
        self.assertAlmostEqual(state["break_done_s"], 8.0, places=2)
        state = run(None, 11.8)
        self.assertTrue(state["on_break"])
        state = run(None, 0.4)
        self.assertFalse(state["on_break"])                 # 8 + 12 = 20: break complete


if __name__ == "__main__":
    unittest.main()
