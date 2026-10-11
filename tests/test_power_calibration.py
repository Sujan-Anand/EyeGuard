"""Power-aware calibration: lens magnification, saved calibration, the
profile's safe distance, the glare warning and the high-power reminder.

Run all tests with:   py -m unittest discover -s tests -v
"""

import os
import shutil
import tempfile
import unittest
from datetime import date

import cv2
import numpy as np

from fake_desktop import FACE, HEIGHT, WIDTH, NEAR, all_text, run_desktop

import eyeguard
import profiles

ESTIMATE = "Estimated for -7.00 D glasses - press c to calibrate for best accuracy"
WEAR = "Sit at arm's length (about 50 cm), wearing what you entered, then press C to calibrate"
WEAR_LINES = ["Sit at arm's length (about 50 cm), wearing what you entered,",
              "then press C to calibrate"]            # how it is drawn on the video
HIGH = "Your glasses power is high. Remember to get a full eye check-up regularly."


def distances(result):
    """The distance column of the session log as numbers."""
    return [float(row[4]) for row in result["rows"] if row[4]]


class MagnificationTest(unittest.TestCase):
    """m = 1 / (1 - d * P) with d = 0.015 m."""

    def test_no_power_means_no_change(self):
        self.assertEqual(profiles.lens_magnification("glasses", 0), 1.0)

    def test_minus_7_makes_the_eye_look_about_10_percent_smaller(self):
        self.assertAlmostEqual(profiles.lens_magnification("glasses", -7), 0.905, places=3)

    def test_plus_3_makes_it_look_bigger(self):
        self.assertAlmostEqual(profiles.lens_magnification("glasses", 3), 1.047, places=3)

    def test_contacts_and_no_correction_are_1(self):
        self.assertEqual(profiles.lens_magnification("contacts", -7), 1.0)
        self.assertEqual(profiles.lens_magnification("none", 0), 1.0)

    def test_corrected_distance_is_raw_times_m(self):
        glasses = profiles.make("G", "glasses", -7)
        m = profiles.lens_magnification("glasses", -7)
        for raw in (30.0, 50.0, 62.5, 80.0):
            self.assertAlmostEqual(profiles.corrected_distance(raw, glasses), raw * m)
        self.assertAlmostEqual(profiles.corrected_distance(60, glasses), 54.3, places=1)
        self.assertEqual(profiles.corrected_distance(60, profiles.make("C", "contacts", -7)), 60)
        self.assertEqual(profiles.corrected_distance(60, None), 60)          # no profile

    def test_a_saved_calibration_wins_over_the_formula(self):
        calibrated = profiles.make("G", "glasses", -7, focal_px=600, calibrated_on="2026-10-11")
        self.assertEqual(profiles.distance_factor(calibrated), 1.0)
        self.assertEqual(profiles.corrected_distance(60, calibrated), 60)

    def test_notes(self):
        glasses = profiles.make("G", "glasses", -7)
        self.assertEqual(profiles.estimate_note(glasses),
                         "Estimated for -7.00 D glasses — press c to calibrate for best accuracy")
        self.assertEqual(profiles.calibration_note(glasses), WEAR)
        self.assertEqual(profiles.high_power_note(glasses), HIGH)
        self.assertEqual(profiles.estimate_note(profiles.make("P", "glasses", 3)),
                         "Estimated for +3.00 D glasses — press c to calibrate for best accuracy")
        # nothing to estimate for contacts, no power, or no profile
        for other in (profiles.make("C", "contacts", -7), profiles.make("Z", "glasses", 0),
                      profiles.make("N"), None):
            self.assertIsNone(profiles.estimate_note(other))
        self.assertEqual(profiles.calibration_note(profiles.make("N")),
                         "Sit at arm's length (about 50 cm), then press C to calibrate")
        # the reminder is for strong lenses only, and never a diagnosis
        self.assertIsNone(profiles.high_power_note(profiles.make("G", "glasses", -5.75)))
        self.assertIsNotNone(profiles.high_power_note(profiles.make("G", "glasses", 6)))
        self.assertEqual(profiles.high_power_note(profiles.make("C", "contacts", -8)),
                         "Your contact lens power is high. Remember to get a full eye "
                         "check-up regularly.")
        self.assertIsNone(profiles.high_power_note(None))
        # once calibrated there is nothing left to say about calibrating
        done = profiles.make("G", "glasses", -7, focal_px=600, calibrated_on="2026-10-11")
        self.assertIsNone(profiles.estimate_note(done))
        self.assertIsNone(profiles.calibration_note(done))


class GlareDetectorTest(unittest.TestCase):
    def feed(self, samples, step=1 / 30):
        """samples: list of (iris width in px, EAR). Returns the result for each frame."""
        detector, now, out = eyeguard.GlareDetector(), 100.0, []
        for iris, ear in samples:
            now += step
            out.append(detector.update(iris, ear, 0.21, now))
        return out

    def test_a_steady_face_is_not_glare(self):
        self.assertFalse(any(self.feed([(20.0 + 0.2 * (i % 3), 0.29) for i in range(120)])))

    def test_normal_blinking_is_not_glare(self):
        samples = [(20.0, 0.12 if i % 60 in (0, 1, 2) else 0.29) for i in range(300)]   # a blink every 2 s
        self.assertFalse(any(self.feed(samples)))

    def test_leaning_in_smoothly_is_not_glare(self):
        samples = [(20.0 * (1 + 0.01 * i), 0.29) for i in range(60)]     # 1% bigger each frame
        self.assertFalse(any(self.feed(samples)))

    def test_jumping_iris_width_is_glare(self):
        samples = [(20.0 if i % 2 else 26.0, 0.29) for i in range(60)]
        self.assertTrue(self.feed(samples)[-1])

    def test_flickering_eye_state_is_glare(self):
        samples = [(20.0, 0.29 if i % 4 < 2 else 0.12) for i in range(60)]   # 15 "blinks" a second
        self.assertTrue(self.feed(samples)[-1])

    def test_it_clears_after_two_steady_seconds(self):
        jumpy = [(20.0 if i % 2 else 26.0, 0.29) for i in range(60)]
        steady = [(20.0, 0.29)] * 70
        result = self.feed(jumpy + steady)
        self.assertTrue(result[59])
        self.assertFalse(result[-1])

    def test_too_few_frames_decide_nothing(self):
        samples = [(20.0 if i % 2 else 26.0, 0.29) for i in range(10)]
        self.assertFalse(any(self.feed(samples, step=1.0)))               # one frame a second


class TempProfilesFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="eyeguard_profiles_")
        self.real_path = profiles.PROFILES_PATH
        profiles.PROFILES_PATH = os.path.join(self.folder, "profiles.json")

    def tearDown(self):
        profiles.PROFILES_PATH = self.real_path
        shutil.rmtree(self.folder, ignore_errors=True)


class DesktopPowerTest(TempProfilesFile):
    """The real main() loop with a simulated camera (face about 62 cm away)."""

    def test_glasses_power_corrects_the_distance_automatically(self):
        plain = run_desktop(frames=6)
        profiles.save(profiles.make("Sujan - glasses", "glasses", -7))
        r = run_desktop(["--profile", "Sujan - glasses"], frames=6)
        m = profiles.lens_magnification("glasses", -7)
        for raw, corrected in zip(distances(plain), distances(r)):
            self.assertAlmostEqual(corrected, raw * m, delta=0.06)        # log has 1 decimal
        self.assertLess(distances(r)[0], distances(plain)[0] - 5)         # about 62 -> 56 cm
        for texts in r["texts"]:
            self.assertIn(ESTIMATE, texts)
            self.assertTrue(set(WEAR_LINES) <= texts)                     # the guide, on two lines
        self.assertIn("Estimated for -7.00 D glasses — press c to calibrate", r["printed"])
        self.assertIn(WEAR, r["printed"])

    def test_contacts_are_not_corrected(self):
        plain = run_desktop(frames=6)
        profiles.save(profiles.make("Sujan - contacts", "contacts", -7))
        r = run_desktop(["--profile", "Sujan - contacts"], frames=6)
        self.assertEqual(distances(r), distances(plain))
        self.assertFalse(any(t.startswith("Estimated") for t in all_text(r)))
        self.assertTrue(set(WEAR_LINES) <= all_text(r))                   # still asked to calibrate

    def test_pressing_c_saves_the_calibration_to_the_profile(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -7))
        r = run_desktop(["--profile", "Sujan - glasses"], frames=8, keys={3: "c"})
        saved = profiles.find("Sujan - glasses")
        self.assertIsNotNone(saved["focal_px"])
        self.assertEqual(saved["calibrated_on"], date.today().isoformat())
        self.assertIn("Calibrated at 50 cm", r["printed"])
        self.assertIn("Calibration saved to profile Sujan - glasses.", r["printed"])
        self.assertAlmostEqual(distances(r)[-1], 50.0, delta=0.3)         # reads 50 where you sat
        self.assertIn(ESTIMATE, r["texts"][3])                            # before pressing c
        for texts in r["texts"][4:]:                                      # after: no more hints
            self.assertFalse(any(t.startswith(("Estimated", "Wear the glasses")) for t in texts))
            self.assertIn("Calibrated - saved to your profile", texts)   # the tick has no video glyph

    def test_a_saved_calibration_is_used_next_time_instead_of_the_formula(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -7))
        run_desktop(["--profile", "Sujan - glasses"], frames=6, keys={2: "c"})
        focal = profiles.find("Sujan - glasses")["focal_px"]
        r = run_desktop(["--profile", "Sujan - glasses"], frames=6)       # a new session
        self.assertIn(f"Using the calibration saved on {date.today().isoformat()}", r["printed"])
        for d in distances(r):
            self.assertAlmostEqual(d, 50.0, delta=0.5)                    # no extra x 0.905
        self.assertFalse(any(t.startswith(("Estimated", "Wear the glasses")) for t in all_text(r)))
        self.assertEqual(profiles.find("Sujan - glasses")["focal_px"], focal)     # untouched

    def test_calibrating_without_a_profile_saves_nothing(self):
        r = run_desktop(frames=6, keys={2: "c"})
        self.assertIn("Calibrated at 50 cm", r["printed"])
        self.assertNotIn("saved to profile", r["printed"])
        self.assertFalse(os.path.exists(profiles.PROFILES_PATH))
        self.assertFalse(any(t.startswith(("Estimated", "Sit at", "then press")) for t in all_text(r)))

    def test_the_profile_safe_distance_sets_the_too_close_alert(self):
        plain = run_desktop(frames=6)                                     # 62 cm, limit 50
        self.assertFalse(any(t.startswith("Too close") for t in all_text(plain)))
        profiles.save(profiles.make("Careful", safe_distance_cm=70))
        r = run_desktop(["--profile", "Careful"], frames=6)               # 62 cm, limit 70
        self.assertTrue(all(any(t.startswith("Too close! 6") and t.endswith("cm - move back")
                                for t in texts) for texts in r["texts"]))
        self.assertEqual(r["beeps"][0], (0, "long"))
        self.assertEqual({b for b in r["banners"]}, {eyeguard.ALERT_RED})
        # the strain score also uses the profile's limit: (70 - distance) x 1.5 more points
        for before, after in zip(plain["rows"], r["rows"]):
            extra = int(after[8]) - int(before[8])
            self.assertAlmostEqual(extra, (70 - float(after[4])) * 1.5, delta=0.51)

    def test_too_close_uses_the_corrected_distance(self):
        # raw 62 cm; with -12 D glasses that is really about 52.5 cm; limit 55 -> too close
        profiles.save(profiles.make("Strong", "glasses", -12, 55))
        r = run_desktop(["--profile", "Strong"], frames=4)
        self.assertTrue(any(t.startswith("Too close! 5") for t in all_text(r)), all_text(r))

    def test_high_power_reminder_once_per_session(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -7))
        r = run_desktop(["--profile", "Sujan - glasses"], frames=30, step=1.0)
        self.assertEqual(r["printed"].count(HIGH), 1)
        shown = [n for n, texts in enumerate(r["texts"]) if HIGH in texts]
        self.assertEqual(shown, list(range(9)))                           # first 10 seconds only
        low = profiles.save(profiles.make("Mild", "glasses", -2))
        r = run_desktop(["--profile", low["name"]], frames=5)
        self.assertNotIn("power is high", r["printed"])
        self.assertFalse(any("power is high" in t for t in all_text(r)))

    def test_the_csv_columns_are_unchanged(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -7, 60))
        r = run_desktop(["--profile", "Sujan - glasses"], frames=5, keys={2: "c"})
        self.assertEqual(r["header"], ["timestamp", "face", "ear", "blinks_total", "blink_rate",
                                       "distance_cm", "looking_away", "brightness", "on_break",
                                       "strain_score", "alert"])
        self.assertEqual(r["files"], sorted(r["files"]))
        self.assertEqual(len(r["files"]), 1)                              # nothing extra written


def wobbly(n):
    """The face, drawn slightly bigger on every other frame: an unstable iris size."""
    if n % 2 == 0:
        return FACE
    big = cv2.resize(FACE, None, fx=1.16, fy=1.16, interpolation=cv2.INTER_LINEAR)
    y, x = (big.shape[0] - HEIGHT) // 2, (big.shape[1] - WIDTH) // 2
    return np.ascontiguousarray(big[y:y + HEIGHT, x:x + WIDTH])


class DesktopGlareTest(TempProfilesFile):
    def test_unstable_readings_with_glasses_show_the_glare_warning(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -2))
        r = run_desktop(["--profile", "Sujan - glasses"], frames=60, step=0.1, frame_for=wobbly)
        self.assertIn(eyeguard.GLARE_MESSAGE, all_text(r))
        first = next(n for n, texts in enumerate(r["texts"]) if eyeguard.GLARE_MESSAGE in texts)
        self.assertEqual(r["banners"][first], eyeguard.AMBER)             # a warning, not red
        self.assertIn((first, "long"), r["beeps"])
        self.assertTrue(any(row[9] == eyeguard.GLARE_MESSAGE for row in r["rows"]))   # logged

    def test_no_glare_warning_without_glasses(self):
        for argv in ([], ["--profile", "Lenses"]):
            profiles.save(profiles.make("Lenses", "contacts", -2))
            r = run_desktop(argv, frames=60, step=0.1, frame_for=wobbly)
            self.assertNotIn(eyeguard.GLARE_MESSAGE, all_text(r))

    def test_a_steady_face_with_glasses_has_no_glare_warning(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -2))
        r = run_desktop(["--profile", "Sujan - glasses"], frames=60, step=0.1)
        self.assertNotIn(eyeguard.GLARE_MESSAGE, all_text(r))


if __name__ == "__main__":
    unittest.main()
