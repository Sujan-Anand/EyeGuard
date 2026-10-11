"""EyeGuard stands as its own project: no event or competition wording is left
in the code, the pages or the documentation.

Run all tests with:   py -m unittest discover -s tests -v
"""

import os
import re
import subprocess
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Written in pieces so this file does not contain the words it looks for.
GONE = ["py" + "sustain", "hack" + "athon", "bac" + "se", "track" + " 1", "code to" + " cure",
        "jud" + "ge", r"\bv" + r"it\b", "vell" + "ore", "dark" + " fantasy", "tech" + " stack"]
KEPT = {"README.md": ["SDG 3.4", "SDG 4", "not a medical device", "AI usage disclosure",
                      '--profile "Sujan - glasses"'],
        "app.py": ["SDG 3.4", "SMART EYE STRAIN MONITOR",
                   "Built by Sujan Anand, Dhayanithi S V, Padhmesh N, Akshaith P",
                   "An awareness tool, not a medical device."],
        "pages/about.py": ["AI usage disclosure", "not a medical device", "The formulas",
                           "EyeGuard was built by Sujan Anand, Dhayanithi S V, Padhmesh N "]}


def text_files():
    """Every text file git tracks (or would track): code, docs, settings, launchers."""
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=PROJECT, capture_output=True, text=True).stdout.split("\n")
    wanted = (".py", ".md", ".toml", ".bat", ".txt", ".json")
    return [name for name in listed if name.endswith(wanted)
            and os.path.exists(os.path.join(PROJECT, name))]


def read(name):
    with open(os.path.join(PROJECT, name), encoding="utf-8") as f:
        return f.read()


class WordingTest(unittest.TestCase):
    def test_no_event_wording_is_left(self):
        files = text_files()
        self.assertIn("app.py", files)
        self.assertIn("README.md", files)
        found = [(name, word) for name in files for word in GONE
                 if re.search(word, read(name), re.IGNORECASE)]
        self.assertEqual(found, [])

    def test_what_must_stay_is_still_there(self):
        for name, phrases in KEPT.items():
            text = read(name)
            for phrase in phrases:
                self.assertIn(phrase, text, name)

    def test_the_ai_disclosure_is_the_same_in_both_places(self):
        rest = ("We used AI assistants (Claude) to help write and debug parts of the code and "
                "documentation. The project idea, feature design, testing, calibration and "
                "presentation were done by our team, and every member can explain how the "
                "code works.")
        start = "EyeGuard was built by Sujan Anand, Dhayanithi S V, Padhmesh N and Akshaith P. "
        self.assertIn(start + rest, read("README.md"))
        page = re.sub(r'"\s*\n\s*"', "", read("pages/about.py"))      # join the wrapped string
        self.assertIn(start + rest, page)

    def test_about_starts_with_the_formulas(self):
        headers = re.findall(r'st\.header\("([^"]+)"\)', read("pages/about.py"))
        self.assertEqual(headers, ["The formulas", "Future scope", "AI usage disclosure"])


if __name__ == "__main__":
    unittest.main()
