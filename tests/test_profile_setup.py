"""Easier profile setup: the start window's choices, the one-screen form,
remembering the last profile, switching with the p key, the guided
calibration, and the Windows launchers.

Only the logic is tested here. No real window is opened: the desktop loop
runs with a simulated camera and a stand-in for the profile window.

Run all tests with:   py -m unittest discover -s tests -v
"""

import os
import shutil
import tempfile
import unittest

from fake_desktop import AWAY, FACE, all_text, run_desktop

import eyeguard
import profiles

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def distances(result):
    return [float(row[4]) for row in result["rows"] if row[4]]


class TempProfiles(unittest.TestCase):
    """Every test gets its own empty profiles.json and last-profile note."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="eyeguard_profiles_")
        self.real = (profiles.PROFILES_PATH, profiles.LAST_USED_PATH)
        profiles.PROFILES_PATH = os.path.join(self.folder, "profiles.json")
        profiles.LAST_USED_PATH = os.path.join(self.folder, "last_profile.txt")

    def tearDown(self):
        profiles.PROFILES_PATH, profiles.LAST_USED_PATH = self.real
        shutil.rmtree(self.folder, ignore_errors=True)


class PickerTest(TempProfiles):
    def test_no_profiles_yet(self):
        self.assertEqual(profiles.picker_choices(), ([], None))
        self.assertIsNone(profiles.last_used())

    def test_lists_saved_profiles_and_preselects_the_first(self):
        profiles.save(profiles.make("Zed"))
        profiles.save(profiles.make("Asha", "contacts", -1.5))
        saved, selected = profiles.picker_choices()
        self.assertEqual([p["name"] for p in saved], ["Asha", "Zed"])      # alphabetical
        self.assertEqual(selected, 0)

    def test_the_last_used_profile_is_remembered_and_preselected(self):
        for name in ("Asha", "Mira", "Zed"):
            profiles.save(profiles.make(name))
        profiles.remember_last("zed")                                      # however it is typed
        self.assertEqual(profiles.last_used(), "zed")
        self.assertEqual(profiles.picker_choices()[1], 2)
        profiles.remember_last("Mira")
        self.assertEqual(profiles.picker_choices()[1], 1)
        profiles.delete("Mira")                                            # it was deleted since
        self.assertEqual(profiles.picker_choices()[1], 0)

    def test_the_note_of_the_last_profile_is_not_uploaded(self):
        with open(os.path.join(PROJECT, ".gitignore"), encoding="utf-8") as f:
            ignored = f.read().split()
        self.assertIn(os.path.basename(self.real[1]), ignored)
        self.assertIn("profiles.json", ignored)

    def test_a_damaged_file_counts_as_no_profiles(self):
        with open(profiles.PROFILES_PATH, "w", encoding="utf-8") as f:
            f.write("{ not json")
        self.assertEqual(profiles.picker_choices(), ([], None))
        result, profile = profiles.create_from_form("Asha", "none")        # and can be replaced
        self.assertEqual((result, profile["name"]), ("ok", "Asha"))
        self.assertEqual([p["name"] for p in profiles.load_all()], ["Asha"])
        self.assertTrue(os.path.exists(profiles.PROFILES_PATH + ".damaged"))   # the old file is kept

    def test_delete(self):
        profiles.save(profiles.make("Asha"))
        profiles.save(profiles.make("Zed"))
        self.assertTrue(profiles.delete("  ASHA "))
        self.assertFalse(profiles.delete("Asha"))                          # already gone
        self.assertEqual([p["name"] for p in profiles.load_all()], ["Zed"])


class FormTest(TempProfiles):
    def test_power_is_only_asked_for_glasses_and_contacts(self):
        self.assertFalse(profiles.needs_power("none"))
        self.assertTrue(profiles.needs_power("glasses"))
        self.assertTrue(profiles.needs_power("contacts"))
        result, profile = profiles.check_form("Plain", "none", power=-7)   # a hidden value is ignored
        self.assertEqual((result, profile["power"]), ("ok", 0.0))

    def test_the_stepper_moves_in_quarters_and_stops_at_20(self):
        self.assertEqual(profiles.step_power(0, -1), -0.25)
        self.assertEqual(profiles.step_power(-0.25, 1), 0.0)
        self.assertEqual(profiles.step_power(-2.25, -1), -2.5)
        self.assertEqual(profiles.step_power(1.1, 1), 1.25)                # snaps to the grid
        self.assertEqual(profiles.step_power(20, 1), 20.0)
        self.assertEqual(profiles.step_power(-20, -1), -20.0)
        self.assertEqual(profiles.step_power(None, 1), 0.25)
        power = 0.0
        for _ in range(28):
            power = profiles.step_power(power, -1)
        self.assertEqual(power, -7.0)
        self.assertEqual([profiles.power_text(p) for p in (0, -7, 1.5)], ["0.00", "-7.00", "+1.50"])
        self.assertEqual(profiles.POWER_HINT, "the number on your prescription, minus for short sight")

    def test_defaults(self):
        result, profile = profiles.check_form("Asha", "glasses")
        self.assertEqual(result, "ok")
        self.assertEqual((profile["power"], profile["safe_distance_cm"]), (0.0, 50))
        self.assertEqual((profiles.DEFAULT_SAFE_DISTANCE_CM, profiles.FORM_MAX_SAFE_DISTANCE_CM), (50, 80))

    def test_friendly_validation(self):
        for name in ("", "   ", "\t"):
            result, message = profiles.check_form(name, "none")
            self.assertEqual(result, "error")
            self.assertIn("Please give the profile a name", message)
        self.assertEqual(profiles.check_form("A", "sunglasses")[0], "error")
        result, message = profiles.check_form("A", "glasses", 25)
        self.assertEqual((result, message),
                         ("error", "Please check the form: power must be between -20 and +20."))
        self.assertEqual(profiles.check_form("A", "none", 0, 40)[0], "error")       # under 50 cm
        self.assertEqual(profiles.load_all(), [])                                   # nothing saved

    def test_creating_a_profile_saves_it_and_remembers_it(self):
        result, profile = profiles.create_from_form("  Sujan  -  glasses ", "glasses", -7, 60)
        self.assertEqual(result, "ok")
        self.assertEqual(profile, profiles.make("Sujan - glasses", "glasses", -7, 60))
        self.assertEqual(profiles.find("sujan-glasses"), profile)
        self.assertEqual(profiles.last_used(), "Sujan - glasses")
        self.assertEqual(profiles.picker_choices(), ([profile], 0))
        self.assertEqual(profiles.calibration_status(profile),
                         "Not calibrated — run the desktop app and press C")

    def test_a_duplicate_name_offers_the_existing_profile(self):
        first = profiles.save(profiles.save_calibration(
            profiles.make("Sujan - glasses", "glasses", -7), 640, today="2026-10-01"))
        for typed in ("Sujan - glasses", "SUJAN – glasses", "sujan-glasses"):
            result, existing = profiles.create_from_form(typed, "contacts", -1)
            self.assertEqual((result, existing), ("duplicate", first), typed)
        self.assertEqual(profiles.load_all(), [first])                     # not overwritten
        self.assertIsNone(profiles.last_used())
        self.assertEqual(profiles.calibration_status(first), "Calibrated on 2026-10-01")

    def test_duplicates_can_be_checked_against_any_list(self):
        mine = [profiles.make("Asha")]                                     # the website's own list
        self.assertEqual(profiles.check_form("asha", "none", saved=mine), ("duplicate", mine[0]))
        self.assertEqual(profiles.check_form("Zed", "none", saved=mine)[0], "ok")


class StartWindowTest(TempProfiles):
    """Which runs open the profile window, and what each answer does."""

    def test_without_a_name_the_window_opens_before_the_camera(self):
        r = run_desktop(frames=4)
        self.assertEqual(r["picker"], [(-1, None)])                        # before the first frame
        self.assertIn("No profile in use", r["printed"])
        self.assertEqual(len(r["rows"]), 4)

    def test_start_with_the_chosen_profile(self):
        chosen = profiles.save(profiles.make("Careful", "none", 0, 70))
        r = run_desktop(frames=6, picks=[("use", chosen)])
        self.assertIn("Profile: Careful: no glasses or contacts, safe distance 70 cm", r["printed"])
        self.assertTrue({"Careful", "no glasses or contacts"} <= all_text(r))
        self.assertTrue(any(t.startswith("Too close!") for t in all_text(r)))      # 62 cm, limit 70

    def test_closing_the_window_does_not_start_eyeguard(self):
        r = run_desktop(frames=4, picks=[("cancel", None)])
        self.assertEqual((r["frames_read"], r["rows"], r["files"]), (0, [], []))
        self.assertIn("EyeGuard did not start", r["printed"])

    def test_a_name_on_the_command_line_skips_the_window_and_is_remembered(self):
        profiles.save(profiles.make("Asha", "contacts", -1.5))
        for argv in (["--profile", "asha"], ["--profile", "asha", "--mute"],
                     ["--profile", "asha", "--background"]):
            profiles.remember_last("someone else")
            r = run_desktop(argv, frames=3)
            self.assertEqual(r["picker"], [], argv)
            self.assertIn("Profile loaded - Asha: contacts -1.50 D", r["printed"])
            self.assertEqual(profiles.last_used(), "Asha")

    def test_no_profile_option_skips_the_window(self):
        r = run_desktop(["--no-profile"], frames=3)
        self.assertEqual((r["picker"], len(r["rows"])), ([], 3))
        plain = run_desktop(frames=3)
        self.assertEqual(r["rows"], plain["rows"])                         # same as "Continue without"

    def test_background_mode_also_asks_and_points_to_calibration(self):
        chosen = profiles.make("Sujan - glasses", "glasses", -7)
        r = run_desktop(["--background"], frames=4, picks=[("use", chosen)])
        self.assertEqual(r["picker"], [(-1, None)])
        self.assertIn("to calibrate the distance, run once without --background and press c",
                      r["printed"])
        self.assertEqual(r["shown"], 0)

    def test_carries_on_without_a_profile_if_the_window_cannot_open(self):
        r = run_desktop(frames=4, picker_fails=True)
        self.assertIn("Profile window not shown (no display).", r["printed"])
        self.assertIn('--profile "Name"', r["printed"])
        self.assertEqual(len(r["rows"]), 4)

    def test_sound_test_does_not_open_the_window(self):
        r = run_desktop(["--test-sound"], frames=2)
        self.assertEqual(r["picker"], [])


class GuidedCalibrationTest(TempProfiles):
    def test_guide_then_confirmation(self):
        fresh = profiles.save(profiles.make("Sujan - glasses", "glasses", -7))
        r = run_desktop(frames=10, picks=[("use", fresh)], keys={4: "c"})
        guide = {"Sit at arm's length (about 50 cm), wearing what you entered,",
                 "then press C to calibrate"}
        for frame in range(0, 5):
            self.assertTrue(guide <= r["texts"][frame], frame)             # until calibrated
        for frame in range(5, 9):                                          # shown for 5 seconds
            self.assertIn("Calibrated - saved to your profile", r["texts"][frame])
            self.assertFalse(guide & r["texts"][frame])
        self.assertEqual(profiles.CALIBRATED_MESSAGE, "Calibrated ✓ — saved to your profile")
        saved = profiles.find("Sujan - glasses")
        self.assertTrue(profiles.is_calibrated(saved))
        self.assertTrue(profiles.calibration_status(saved).startswith("Calibrated on 20"))

    def test_the_guide_wording(self):
        self.assertEqual(profiles.calibration_note(profiles.make("A", "contacts", -1)),
                         "Sit at arm's length (about 50 cm), wearing what you entered, "
                         "then press C to calibrate")
        self.assertEqual(profiles.calibration_note(profiles.make("A")),
                         "Sit at arm's length (about 50 cm), then press C to calibrate")
        self.assertIsNone(profiles.calibration_note(None))                 # no profile: no guide
        self.assertEqual(eyeguard.wrap_note("short"), ["short"])
        self.assertEqual(len(eyeguard.wrap_note("word " * 30)), 2)

    def test_a_calibrated_profile_shows_no_guide(self):
        done = profiles.save(profiles.save_calibration(profiles.make("Zed"), 640, today="2026-10-01"))
        r = run_desktop(frames=4, picks=[("use", done)])
        self.assertFalse(any(t.startswith(("Sit at", "then press")) for t in all_text(r)))
        self.assertIn("Using the calibration saved on 2026-10-01", r["printed"])


class SwitchProfileTest(TempProfiles):
    """The p key reopens the window; the new profile applies straight away."""

    def test_switching_applies_everything_at_once(self):
        glasses = profiles.make("Sujan - glasses", "glasses", -7, 70)      # uncalibrated: formula
        tuned = profiles.make("Zed", "none", 0, 50, focal_px=1152.0, calibrated_on="2026-10-01")
        r = run_desktop(frames=30, keys={5: "p", 11: "p", 17: "p", 23: "p"},
                        picks=[("none", None), ("use", glasses), ("use", tuned),
                               ("cancel", None), ("none", None)])
        self.assertEqual(r["picker"], [(-1, None), (5, None), (11, "Sujan - glasses"),
                                       (17, "Zed"), (23, "Zed")])          # opens showing who is in use
        d = distances(r)
        plain = d[2]
        m = profiles.lens_magnification("glasses", -7)
        self.assertAlmostEqual(d[8], plain * m, delta=0.6)                 # lens correction applied
        self.assertAlmostEqual(d[14], plain * 2, delta=1.2)                # Zed's saved calibration (2x)
        self.assertAlmostEqual(d[20], d[14], delta=0.6)                    # window closed: no change
        self.assertAlmostEqual(d[26], plain, delta=0.6)                    # no profile again

        self.assertFalse(any(t.startswith("Too close!") for t in r["texts"][3]))
        self.assertTrue(any(t.startswith("Too close!") for t in r["texts"][8]))    # 56 cm, limit 70
        self.assertFalse(any(t.startswith("Too close!") for t in r["texts"][14]))  # limit back to 50
        self.assertTrue({"Sujan - glasses", "glasses -7.00 D"} <= r["texts"][8])
        self.assertTrue({"Zed", "no glasses or contacts"} <= r["texts"][14])
        self.assertFalse({"Zed", "Sujan - glasses"} & r["texts"][26])
        self.assertIn("Profile: Sujan - glasses", r["texts"][7])           # a short notice
        self.assertIn("No profile in use", r["texts"][25])
        self.assertIn("then press C to calibrate", r["texts"][8])          # guide for the new profile
        self.assertNotIn("then press C to calibrate", r["texts"][14])
        self.assertEqual(len(r["rows"]), 30)                               # the session carried on
        self.assertIn("m sound ON | p profile", all_text(r))

    def test_switching_with_the_window_unavailable_keeps_the_profile(self):
        profiles.save(profiles.make("Careful", "none", 0, 70))
        r = run_desktop(["--profile", "Careful"], frames=10, keys={4: "p"}, picker_fails=True)
        self.assertEqual(r["picker"], [(4, "Careful")])
        self.assertIn("Careful", r["texts"][8])                            # still in use
        self.assertTrue(any(t.startswith("Too close!") for t in r["texts"][8]))

    def test_time_in_the_window_does_not_count_towards_a_break(self):
        # break started with b, looking away; half a minute is then spent in the window
        r = run_desktop(frames=14, step=0.5, keys={2: "b", 8: "p"}, picker_takes=30.0,
                        frame_for=lambda n: AWAY if n >= 3 else FACE)
        self.assertEqual(r["picker"][1], (8, None))
        before = next(t for t in r["texts"][8] if t.startswith("Good! Keep looking away"))
        after = next(t for t in r["texts"][10] if t.startswith("Good! Keep looking away"))
        self.assertEqual(before, "Good! Keep looking away (2/20 s)")       # 2.5 s done
        self.assertEqual(after, "Good! Keep looking away (3/20 s)")        # only the 0.5 s frame added
        self.assertEqual([row[7] for row in r["rows"]][-1], "1")           # still on the break


class LauncherTest(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(PROJECT, name), "rb") as f:
            return f.read()

    def test_both_launchers_exist_and_start_the_right_thing(self):
        normal = self.read("EyeGuard.bat").decode("ascii")
        hidden = self.read("EyeGuard Background.bat").decode("ascii")
        self.assertIn("call %PYTHON% eyeguard.py\r\n", normal)
        self.assertIn("call %PYTHON% eyeguard.py --background\r\n", hidden)
        for text in (normal, hidden):
            self.assertIn('cd /d "%~dp0"', text)                           # runs from the project folder
            self.assertIn('set "PYTHON=py"', text)
            self.assertIn("Python was not found on this computer.", text)
            self.assertGreaterEqual(text.count("pause"), 2)                # the window stays open
            self.assertIn("requirements-desktop.txt", text)
            self.assertNotIn("--profile", text)                            # the window asks instead

    def test_windows_line_endings(self):
        for name in ("EyeGuard.bat", "EyeGuard Background.bat"):
            data = self.read(name)
            self.assertEqual(data.count(b"\n"), data.count(b"\r\n"), name)
        with open(os.path.join(PROJECT, ".gitattributes"), encoding="utf-8") as f:
            self.assertIn("*.bat text eol=crlf", f.read())

    def test_readme_has_the_30_second_start(self):
        with open(os.path.join(PROJECT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("Getting started in 30 seconds", readme)
        for step in ("EyeGuard.bat", "+ New profile", "Save & start", "press C"):
            self.assertIn(step, readme)


if __name__ == "__main__":
    unittest.main()
