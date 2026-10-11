"""User profiles: profiles.json, the terminal questionnaire and --profile.

Run all tests with:   py -m unittest discover -s tests -v
"""

import json
import os
import shutil
import tempfile
import unittest

from fake_desktop import all_text, run_desktop

import eyeguard
import profiles


def answers(*lines):
    """A stand-in for input(): gives the lines one by one, then acts like a
    terminal with no keyboard."""
    queue = list(lines)

    def ask(question):
        if not queue:
            raise EOFError
        return queue.pop(0)
    return ask


class TempProfilesFile(unittest.TestCase):
    """Every test gets its own empty profiles.json, never the real one."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="eyeguard_profiles_")
        self.real_path = profiles.PROFILES_PATH
        profiles.PROFILES_PATH = os.path.join(self.folder, "profiles.json")
        self.said = []

    def tearDown(self):
        profiles.PROFILES_PATH = self.real_path
        shutil.rmtree(self.folder, ignore_errors=True)

    def say(self, text=""):
        self.said.append(str(text))


class ValuesTest(unittest.TestCase):
    def test_power_is_read_and_rounded_to_quarter_dioptres(self):
        for typed, expected in [("-7", -7.0), ("−7.00 D", -7.0), ("+3", 3.0), ("-2,5", -2.5),
                                ("1.75", 1.75), ("-6.9", -7.0), ("-6.6", -6.5), ("0.1", 0.0),
                                ("-0.1", 0.0), ("20", 20.0), ("-20", -20.0), (-4.25, -4.25)]:
            self.assertEqual(profiles.parse_power(typed), expected, typed)
        self.assertEqual(str(profiles.parse_power("-0.1")), "0.0")      # never "-0.0"

    def test_bad_power_is_refused_with_a_reason(self):
        for typed in ["abc", "", "20.5", "-25", "nan", "--3"]:
            with self.assertRaises(ValueError, msg=typed):
                profiles.parse_power(typed)

    def test_safe_distance_is_50_or_more(self):
        self.assertEqual(profiles.DEFAULT_SAFE_DISTANCE_CM, eyeguard.MIN_SAFE_DISTANCE_CM)
        self.assertEqual(profiles.parse_safe_distance("60"), 60)
        self.assertEqual(profiles.parse_safe_distance("65 cm"), 65)
        self.assertEqual(profiles.parse_safe_distance(50), 50)
        for typed in ["40", "49.4", "150", "far", ""]:
            with self.assertRaises(ValueError, msg=typed):
                profiles.parse_safe_distance(typed)

    def test_make_checks_every_field(self):
        p = profiles.make("  Sujan   -  glasses ", "glasses", "-7")
        self.assertEqual(p, {"name": "Sujan - glasses", "correction": "glasses", "power": -7.0,
                             "safe_distance_cm": 50, "focal_px": None, "calibrated_on": None})
        self.assertEqual(profiles.make("A", "none", -3)["power"], 0.0)   # no lenses, no power
        for bad in [dict(name=""), dict(name="A", correction="lasik"),
                    dict(name="A", correction="glasses", power=30),
                    dict(name="A", safe_distance_cm=20), dict(name="A", focal_px=-5)]:
            with self.assertRaises(ValueError, msg=bad):
                profiles.make(**bad)

    def test_describe(self):
        self.assertEqual(profiles.describe(profiles.make("A", "glasses", -7)), "glasses -7.00 D")
        self.assertEqual(profiles.describe(profiles.make("A", "contacts", 1.25)), "contacts +1.25 D")
        self.assertEqual(profiles.describe(profiles.make("A")), "no glasses or contacts")

    def test_names_match_whatever_the_dash_or_capitals(self):
        key = profiles.name_key
        self.assertEqual(key("Sujan – glasses"), key("sujan - glasses"))
        self.assertEqual(key("Sujan – glasses"), key("SUJAN-glasses"))
        self.assertNotEqual(key("Sujan – glasses"), key("Sujan – contacts"))
        self.assertEqual(profiles.to_ascii("Sujan – glasses"), "Sujan - glasses")
        self.assertEqual(profiles.to_ascii("Renée"), "Renee")
        self.assertEqual(profiles.to_ascii("சுஜன்"), "")              # nothing the video font can draw


class FileTest(TempProfilesFile):
    def test_no_file_means_no_profiles(self):
        self.assertEqual(profiles.load_all(), [])
        self.assertIsNone(profiles.find("Anyone"))

    def test_save_and_load_two_profiles_for_one_person(self):
        profiles.save(profiles.make("Sujan – glasses", "glasses", -7, 55))
        profiles.save(profiles.make("Sujan – contacts", "contacts", -6.5))
        self.assertEqual([p["name"] for p in profiles.load_all()],
                         ["Sujan – contacts", "Sujan – glasses"])
        found = profiles.find("sujan - GLASSES")
        self.assertEqual((found["correction"], found["power"], found["safe_distance_cm"]),
                         ("glasses", -7.0, 55))
        with open(profiles.PROFILES_PATH, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(sorted(on_disk["profiles"][0]),
                         ["calibrated_on", "correction", "focal_px", "name", "power",
                          "safe_distance_cm"])
        self.assertIsNone(on_disk["profiles"][0]["focal_px"])            # null until calibrated
        self.assertEqual(os.listdir(self.folder), ["profiles.json"])     # no temp files left

    def test_saving_the_same_name_replaces_it(self):
        profiles.save(profiles.make("Sujan - glasses", "glasses", -7))
        profiles.save(profiles.make("sujan – glasses", "glasses", -7.5, 60))
        saved = profiles.load_all()
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0]["power"], saved[0]["safe_distance_cm"]), (-7.5, 60))

    def test_calibration_fields_are_kept(self):
        profiles.save(profiles.make("A", "glasses", -2, focal_px=612.5, calibrated_on="2026-10-11"))
        self.assertEqual((profiles.find("A")["focal_px"], profiles.find("A")["calibrated_on"]),
                         (612.5, "2026-10-11"))

    def test_a_damaged_file_gives_a_friendly_error(self):
        for text in ["not json at all", '{"profiles": [{"name": "A", "correction": "x"}]}', "[]"]:
            with open(profiles.PROFILES_PATH, "w", encoding="utf-8") as f:
                f.write(text)
            with self.assertRaises(ValueError) as caught:
                profiles.load_all()
            self.assertIn("profiles.json could not be read", str(caught.exception))


class QuestionnaireTest(TempProfilesFile):
    def test_glasses(self):
        p = profiles.load_or_create("Sujan - glasses", answers("g", "-7", "60"), self.say)
        self.assertEqual((p["correction"], p["power"], p["safe_distance_cm"]), ("glasses", -7.0, 60))
        self.assertEqual(profiles.find("Sujan - glasses"), p)            # it was saved
        self.assertIn("Profile saved - Sujan - glasses: glasses -7.00 D, safe distance 60 cm",
                      " ".join(self.said))
        self.assertIn("cannot measure eye power", " ".join(self.said))

    def test_contacts_and_defaults(self):
        p = profiles.load_or_create("Sujan - contacts", answers("contacts", "-6.5", ""), self.say)
        self.assertEqual((p["correction"], p["power"], p["safe_distance_cm"]), ("contacts", -6.5, 50))

    def test_no_correction_skips_the_power_question(self):
        asked = []

        def ask(question):
            asked.append(question)
            return ["n", "70"][len(asked) - 1]
        p = profiles.load_or_create("Asha", ask, self.say)
        self.assertEqual(len(asked), 2)
        self.assertEqual((p["correction"], p["power"], p["safe_distance_cm"]), ("none", 0.0, 70))

    def test_wrong_answers_are_asked_again(self):
        p = profiles.load_or_create("B", answers("x", "g", "strong", "99", "-3.2", "30", "55"), self.say)
        self.assertEqual((p["correction"], p["power"], p["safe_distance_cm"]), ("glasses", -3.25, 55))
        self.assertEqual(sum(line.strip().startswith("Sorry") for line in self.said), 4)

    def test_no_keyboard_uses_the_defaults(self):
        p = profiles.load_or_create("C", answers(), self.say)             # input() hits end of file
        self.assertEqual((p["correction"], p["power"], p["safe_distance_cm"]), ("none", 0.0, 50))

    def test_the_second_time_it_loads_without_questions(self):
        profiles.load_or_create("Sujan - glasses", answers("g", "-7", ""), self.say)

        def no_questions(question):
            raise AssertionError("asked a question for a saved profile: " + question)
        p = profiles.load_or_create("sujan – GLASSES", no_questions, self.say)
        self.assertEqual(p["power"], -7.0)
        self.assertIn("Profile loaded - Sujan - glasses: glasses -7.00 D, safe distance 50 cm",
                      self.said)

    def test_a_blank_name_is_refused_before_any_question(self):
        def no_questions(question):
            raise AssertionError("asked a question for a blank name")
        for blank in ["   ", "	", ""]:
            with self.assertRaises(ValueError) as caught:
                profiles.load_or_create(blank, no_questions, self.say)
            self.assertIn("needs a name", str(caught.exception))
        self.assertEqual(profiles.load_all(), [])

    def test_creating_a_second_profile_lists_the_first(self):
        profiles.load_or_create("Sujan - glasses", answers("g", "-7", ""), self.say)
        profiles.load_or_create("Sujan - contacts", answers("c", "-6.5", ""), self.say)
        self.assertIn("Saved profiles: Sujan - glasses", self.said)
        self.assertEqual(len(profiles.load_all()), 2)


class DesktopProfileTest(TempProfilesFile):
    """The real main() loop with a simulated camera."""

    def test_new_profile_is_created_and_shown_on_the_panel(self):
        r = run_desktop(["--demo", "--profile", "Sujan – glasses"], frames=5,
                        typed=["g", "-7", ""])
        self.assertIn("Profile saved - Sujan – glasses: glasses -7.00 D, safe distance 50 cm",
                      r["printed"])
        for texts in r["texts"]:                               # on every frame
            self.assertIn("Sujan - glasses", texts)            # the long dash is drawn as "-"
            self.assertIn("glasses -7.00 D", texts)
        self.assertEqual(profiles.find("Sujan - glasses")["power"], -7.0)

    def test_saved_profile_loads_with_no_questions(self):
        profiles.save(profiles.make("Sujan - contacts", "contacts", -6.5))
        r = run_desktop(["--profile", "sujan - contacts"], frames=3)        # nothing typed
        self.assertIn("Profile loaded - Sujan - contacts: contacts -6.50 D", r["printed"])
        self.assertNotIn("New profile", r["printed"])
        self.assertIn("Sujan - contacts", all_text(r))
        self.assertIn("contacts -6.50 D", all_text(r))

    def test_no_profile_means_no_profile_line_and_no_file(self):
        r = run_desktop(["--demo"], frames=5)
        self.assertFalse(any(t.endswith(" D") or "glasses" in t or "contacts" in t
                             for t in all_text(r)))
        self.assertFalse(any("Profile" in line for line in r["printed"].splitlines()))
        self.assertFalse(os.path.exists(profiles.PROFILES_PATH))

    def test_a_plain_profile_changes_no_numbers(self):
        # no glasses, default safe distance: the same log as running with no profile
        plain = run_desktop(["--demo"], frames=70, step=1.0)
        profiles.save(profiles.make("Asha"))
        with_profile = run_desktop(["--demo", "--profile", "Asha"], frames=70, step=1.0)
        self.assertEqual(with_profile["header"], plain["header"])           # same CSV columns
        self.assertEqual(with_profile["rows"], plain["rows"])               # same numbers
        self.assertEqual(with_profile["beeps"], plain["beeps"])
        for run in (plain, with_profile):                                   # only the session log
            self.assertEqual(len(run["files"]), 1)
            self.assertTrue(run["files"][0].startswith("logs/session_"))

    def test_a_long_name_is_cut_to_fit_the_panel(self):
        name = "Padhmesh Narayanan Subramanian - reading glasses for the computer"
        profiles.save(profiles.make(name, "glasses", -1.25))
        r = run_desktop(["--profile", name], frames=2)
        line = next(t for t in all_text(r) if t.startswith("Padhmesh"))
        self.assertTrue(line.endswith("..."))
        self.assertLess(len(line), len(name))

    def test_a_blank_name_runs_without_a_profile(self):
        r = run_desktop(["--profile", "   "], frames=3, typed=["g", "-2", ""])
        self.assertIn("Profile not used: the profile needs a name", r["printed"])
        self.assertNotIn("New profile", r["printed"])                      # no questions asked
        self.assertEqual(len(r["texts"]), 3)
        self.assertFalse(os.path.exists(profiles.PROFILES_PATH))

    def test_a_name_in_another_script_is_saved_and_the_panel_says_profile(self):
        r = run_desktop(["--profile", "சுஜன்"], frames=3, typed=["c", "-1.5", ""])
        saved = profiles.find("சுஜன்")
        self.assertEqual((saved["name"], saved["correction"], saved["power"]),
                         ("சுஜன்", "contacts", -1.5))
        self.assertIn("Profile", all_text(r))                              # the font has no Tamil
        self.assertIn("contacts -1.50 D", all_text(r))

    def test_a_damaged_file_does_not_stop_the_app(self):
        with open(profiles.PROFILES_PATH, "w", encoding="utf-8") as f:
            f.write("{ broken")
        r = run_desktop(["--profile", "Sujan - glasses"], frames=3)
        self.assertIn("Profile not used: profiles.json could not be read", r["printed"])
        self.assertEqual(len(r["texts"]), 3)                                # it still ran
        self.assertFalse(any(t.startswith("Sujan") for t in all_text(r)))   # with no profile


if __name__ == "__main__":
    unittest.main()
