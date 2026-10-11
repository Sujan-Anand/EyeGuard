"""Two blink alert levels: a warning below 7 blinks/min, a strong alert below 5.

Run all tests with:   py -m unittest discover -s tests -v
"""

import unittest

from fake_desktop import CLOSED, FACE, all_text, run_desktop

import eyeguard

STEP = 0.1                      # seconds per simulated frame
ALERTS = ("Blink more!", "Blink now!")      # the panel also has a "Blinks/min" line


def blinking_every(seconds):
    """A face at a safe distance that shuts its eyes for 0.3 s every `seconds`
    (in the middle of each period, so the first blink comes after seconds / 2)."""
    period = round(seconds / STEP)
    middle = period // 2
    return lambda n: CLOSED if n % period in (middle, middle + 1, middle + 2) else FACE


class BlinkAlertFunctionTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual((eyeguard.BLINK_WARN_RATE, eyeguard.BLINK_ALERT_RATE), (7, 5))
        self.assertIsNone(eyeguard.blink_alert(15))
        self.assertIsNone(eyeguard.blink_alert(7))                    # 7 itself is fine
        self.assertEqual(eyeguard.blink_alert(6.9), ("Blink more! Only 7/min", "warn"))
        self.assertEqual(eyeguard.blink_alert(6), ("Blink more! Only 6/min", "warn"))
        self.assertEqual(eyeguard.blink_alert(5), ("Blink more! Only 5/min", "warn"))
        self.assertEqual(eyeguard.blink_alert(4.9), ("Blink now! Only 5/min", "alert"))
        self.assertEqual(eyeguard.blink_alert(0), ("Blink now! Only 0/min", "alert"))

    def test_colours(self):
        green, red = eyeguard.level_color(True), eyeguard.level_color(False)
        self.assertEqual(eyeguard.blink_color(15), green)
        self.assertEqual(eyeguard.blink_color(7), green)
        self.assertEqual(eyeguard.blink_color(6), eyeguard.AMBER)
        self.assertEqual(eyeguard.blink_color(5), eyeguard.AMBER)
        self.assertEqual(eyeguard.blink_color(4), red)


class DesktopBlinkLevelTest(unittest.TestCase):
    """The real main() loop with a simulated face, 0.1 s per frame."""

    def test_healthy_blinking_gives_no_alert(self):
        r = run_desktop(frames=600, step=STEP, frame_for=blinking_every(3))     # 20/min
        self.assertEqual(r["rows"][-1][2], "20")                    # 20 blinks counted in 60 s
        self.assertFalse(any(t.startswith(ALERTS) for t in all_text(r)))
        self.assertEqual(r["beeps"], [])
        self.assertTrue(all(b is None for b in r["banners"]))

    def test_six_a_minute_is_a_warning(self):
        r = run_desktop(frames=650, step=STEP, frame_for=blinking_every(10))    # 6/min
        blink_text = {t for t in all_text(r) if t.startswith(ALERTS)}
        self.assertTrue(blink_text, "no blink warning was shown")
        self.assertTrue(all(t.startswith("Blink more! Only ") for t in blink_text), blink_text)
        self.assertIn("Blink more! Only 6/min", blink_text)
        shown = {b for b in r["banners"] if b is not None}
        self.assertEqual(shown, {eyeguard.AMBER})                   # amber bar, never red
        first = next(n for n, t in enumerate(r["texts"]) if any(x.startswith(ALERTS) for x in t))
        self.assertGreaterEqual(first * STEP, 30)                   # not in the first 30 s
        beeps = [n for n, _ in r["beeps"]]
        self.assertEqual(beeps[0], first)
        self.assertTrue(all(b - a >= 15 / STEP for a, b in zip(beeps, beeps[1:])))  # 15 s cooldown
        self.assertEqual(r["rows"][-1][9], "Blink more! Only 6/min")            # logged in the CSV

    def test_no_blinking_is_a_strong_alert(self):
        r = run_desktop(frames=400, step=STEP)                                  # never blinks
        blink_text = {t for t in all_text(r) if t.startswith(ALERTS)}
        self.assertEqual(blink_text, {"Blink now! Only 0/min"})
        self.assertEqual({b for b in r["banners"] if b is not None}, {eyeguard.ALERT_RED})
        self.assertEqual(r["rows"][-1][9], "Blink now! Only 0/min")

    def test_dropping_from_warning_to_strong_alert_beeps_again(self):
        # 6/min for 65 s, then no blinks at all: the rate falls through 5/min
        plan = blinking_every(10)
        r = run_desktop(frames=1000, step=STEP,
                        frame_for=lambda n: plan(n) if n < 650 else FACE)
        first_strong = next(n for n, t in enumerate(r["texts"])
                            if any(x.startswith("Blink now!") for x in t))
        self.assertIn(first_strong, [n for n, _ in r["beeps"]])     # beeps at the moment it escalates
        self.assertEqual(r["banners"][first_strong - 1], eyeguard.AMBER)
        self.assertEqual(r["banners"][first_strong], eyeguard.ALERT_RED)


if __name__ == "__main__":
    unittest.main()
