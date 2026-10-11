"""Profiles on the website: the Live Check tracker with and without a profile.

Run all tests with:   py -m unittest discover -s tests -v
"""

import unittest
from datetime import date, datetime

import cv2
import numpy as np

from fake_desktop import FACE

import eyeguard
import live
import profiles

T0 = 1_800_000_000.0


class Session:
    """Feeds one tracker the landmarks of the test face, 0.1 s per frame."""
    pts = None

    def __init__(self, profile=None):
        if Session.pts is None:
            Session.pts = eyeguard.FaceMeshBackend().process(cv2.flip(FACE, 1))
        self.tracker = live.EyeTracker()
        self.tracker.set_profile(profile)
        self.now = T0

    def run(self, seconds=1.0, pts="face", scale=None):
        state = None
        for i in range(round(seconds / 0.1)):
            self.now += 0.1
            use = Session.pts if pts == "face" else pts
            if scale and use is not None and i % 2:
                centre = use.mean(axis=0)
                use = ((use - centre) * scale + centre).astype(np.float32)
            state = self.tracker.update(use, 120.0, 640, self.now)
        return state


class LiveProfileTest(unittest.TestCase):
    def test_no_profile_is_unchanged(self):
        state = Session().run()
        self.assertAlmostEqual(state["distance_cm"], 61.6, delta=1.0)
        self.assertEqual((state["safe_cm"], state["profile_lines"], state["notes"]), (50, (), []))
        self.assertEqual(state["alert"], "")

    def test_glasses_power_corrects_the_distance(self):
        raw = Session().run()["distance_cm"]
        glasses = profiles.make("Sujan - glasses", "glasses", -7)
        state = Session(glasses).run()
        self.assertAlmostEqual(state["distance_cm"], raw * profiles.lens_magnification("glasses", -7),
                               places=3)
        self.assertEqual(state["profile_lines"], ("Sujan - glasses", "glasses -7.00 D"))
        self.assertEqual(len(state["notes"]), 2)
        self.assertTrue(state["notes"][0].startswith("Estimated for -7.00 D glasses"))

    def test_contacts_are_not_corrected(self):
        raw = Session().run()["distance_cm"]
        state = Session(profiles.make("C", "contacts", -7)).run()
        self.assertAlmostEqual(state["distance_cm"], raw, places=3)
        self.assertEqual(len(state["notes"]), 1)                 # only the calibration help

    def test_the_profile_safe_distance_is_used(self):
        state = Session(profiles.make("Careful", safe_distance_cm=70)).run()
        self.assertTrue(state["alert"].startswith("Too close! 6"))
        self.assertEqual((state["alert_level"], state["safe_cm"]), ("alert", 70))
        self.assertGreater(state["strain_score"], Session().run()["strain_score"])

    def test_calibrating_stores_it_in_the_profile(self):
        session = Session(profiles.make("Sujan - glasses", "glasses", -7))
        session.run()
        session.tracker.request("calibrate")
        state = session.run()
        self.assertAlmostEqual(state["distance_cm"], 50.0, delta=0.3)     # no extra x 0.905
        self.assertEqual(state["notes"], [])
        saved = session.tracker.current_profile()
        self.assertGreater(saved["focal_px"], 100)
        self.assertEqual(saved["calibrated_on"], datetime.fromtimestamp(T0).date().isoformat())
        self.assertEqual(profiles.make(**saved), saved)                   # still a valid profile

    def test_a_calibrated_profile_uses_its_calibration(self):
        first = Session(profiles.make("Sujan - glasses", "glasses", -7))
        first.run()
        first.tracker.request("calibrate")
        first.run()
        calibrated = first.tracker.current_profile()
        state = Session(calibrated).run()                                 # a new visit
        self.assertAlmostEqual(state["distance_cm"], 50.0, delta=0.5)
        self.assertEqual(state["notes"], [])

    def test_switching_profiles_mid_session(self):
        session = Session()
        raw = session.run()["distance_cm"]
        session.tracker.set_profile(profiles.make("G", "glasses", -7))
        self.assertLess(session.run()["distance_cm"], raw - 4)
        session.tracker.set_profile(profiles.make("G", "glasses", -7, focal_px=1152.0,
                                                  calibrated_on=date.today().isoformat()))
        self.assertAlmostEqual(session.run()["distance_cm"], raw * 2, delta=1.0)  # twice the focal
        session.tracker.set_profile(None)                                 # stop using a profile
        state = session.run()
        self.assertAlmostEqual(state["distance_cm"], raw, delta=0.5)
        self.assertEqual((state["safe_cm"], state["profile_lines"]), (50, ()))

    def test_glare_warning_only_with_glasses(self):
        for profile, expected in [(profiles.make("G", "glasses", -2), True),
                                  (profiles.make("C", "contacts", -2), False), (None, False)]:
            state = Session(profile).run(4, scale=1.16)                   # unstable iris size
            self.assertEqual(state["alert"] == eyeguard.GLARE_MESSAGE, expected, profile)
            if expected:
                self.assertEqual(state["alert_level"], "warn")
        self.assertEqual(Session(profiles.make("G", "glasses", -2)).run(4)["alert"], "")   # steady

    def test_the_overlay_draws_with_a_profile(self):
        session = Session(profiles.make("Sujan - glasses", "glasses", -7))
        state = session.run()
        for shape in [(480, 640, 3), (640, 480, 3), (240, 320, 3)]:
            frame = np.full(shape, 90, np.uint8)
            out = live.draw_overlay(frame.copy(), Session.pts, state)
            self.assertEqual(out.shape, shape)
            self.assertFalse(np.array_equal(out, frame))

    def test_explanations(self):
        self.assertEqual(profiles.explain(profiles.make("G", "glasses", -7)),
                         "At -7.00 D your eyes look about 10% smaller to the camera; "
                         "EyeGuard corrects for this.")
        self.assertIn("about 5% bigger", profiles.explain(profiles.make("G", "glasses", 3)))
        self.assertIn("no correction is needed", profiles.explain(profiles.make("C", "contacts", -7)))
        self.assertIn("as it is", profiles.explain(profiles.make("N")))
        self.assertIn("no power", profiles.explain(profiles.make("Z", "glasses", 0)))


if __name__ == "__main__":
    unittest.main()
