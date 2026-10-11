"""Breaks always follow the 20-20-20 rule: one is due every 20 minutes. There
is no quick-break option any more, on the desktop or on the website. The
tests reach a break quickly by setting the interval directly.

Run all tests with:   py -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from fake_desktop import run_desktop

import eyeguard
import live
import sample_data
import sessions

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_FLAG = "--" + "demo"            # written in pieces: this file must not contain it
OLD_WORDS = [OLD_FLAG, "demo" + " mode", "every" + " 60"]


class IntervalTest(unittest.TestCase):
    def test_a_break_is_due_every_20_minutes(self):
        self.assertEqual(eyeguard.BREAK_EVERY_SECONDS, 20 * 60)
        self.assertEqual(live.NORMAL_BREAK_SECONDS, 20 * 60)
        self.assertEqual(live.EyeTracker().break_every_s, 20 * 60)
        self.assertFalse(hasattr(live, "DEMO" + "_BREAK_SECONDS"))

    def test_the_old_option_is_gone(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            sys_argv, sys.argv = sys.argv, ["eyeguard.py", "--help"]
            try:
                eyeguard.main()
            finally:
                sys.argv = sys_argv
        self.assertNotIn(OLD_FLAG, out.getvalue())
        self.assertIn("--background", out.getvalue())
        done = subprocess.run([sys.executable, "eyeguard.py", OLD_FLAG], cwd=PROJECT,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 2)                      # not a known option
        self.assertIn("unrecognized arguments", done.stderr)

    def test_the_desktop_break_comes_at_20_minutes(self):
        r = run_desktop(["--background"], frames=123, step=10.0)            # 10 s per frame
        breaks = [(n, m) for n, _, m in r["toasts"] if m.startswith("Break")]
        self.assertEqual(breaks, [(119, "Break time: look away for 20 s")])   # frame 119 = minute 20
        box = dict(r["mini"])
        self.assertEqual(box[0][3], ("Next break in 19:50", "plain"))
        self.assertEqual(box[59][3], ("Next break in 10:00", "plain"))
        self.assertEqual([row[7] for row in r["rows"]][117:123], ["0", "0", "1", "1", "1", "1"])
        self.assertEqual(box[121][3], ("Break: 0/20 s - look away", "warn"))

    def test_tests_can_set_a_short_interval_and_it_is_put_back(self):
        r = run_desktop(["--background"], frames=35, step=1.0, break_every=30)
        self.assertIn((29, "Break time: look away for 20 s"),
                      [(n, m) for n, _, m in r["toasts"]])
        self.assertEqual(eyeguard.BREAK_EVERY_SECONDS, 20 * 60)

    def test_no_old_wording_outside_the_tests(self):
        listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                cwd=PROJECT, capture_output=True, text=True).stdout.split("\n")
        files = [n for n in listed if n.endswith((".py", ".md", ".toml", ".bat", ".txt"))
                 and os.path.exists(os.path.join(PROJECT, n))]
        self.assertIn("pages/live_check.py", files)
        found = []
        for name in files:
            with open(os.path.join(PROJECT, name), encoding="utf-8") as f:
                text = f.read().lower()
            found += [(name, word) for word in OLD_WORDS if word in text]
        self.assertEqual(found, [])

    def test_live_check_has_no_break_speed_choice(self):
        with open(os.path.join(PROJECT, "pages", "live_check.py"), encoding="utf-8") as f:
            page = f.read()
        self.assertNotIn("break_every_s", page)                   # the page never changes it
        self.assertEqual(len(re.findall(r"segmented_control\(", page)), 1)       # only video / photo
        self.assertIn("every 20 minutes", page)


class SampleDataTest(unittest.TestCase):
    """The website's made-up sessions are called sample data."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="eyeguard_logs_")
        self.real = sessions.LOG_DIR
        sessions.LOG_DIR = self.folder

    def tearDown(self):
        sessions.LOG_DIR = self.real
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_names(self):
        path = sessions.generate_sample()
        self.assertEqual(os.path.basename(path), "session_00000000_sample.csv")
        week = [os.path.basename(p) for p in sessions.generate_sample_week()]
        self.assertEqual(week, [f"session_0000000{i}_sample.csv" for i in range(1, 8)])
        self.assertEqual(os.path.basename(sample_data.SAMPLE_PATH), "session_00000000_sample.csv")
        df = sessions.read_session(path)
        self.assertEqual(list(df.columns), sessions.COLUMNS)      # same columns as a real session
        self.assertTrue(sessions.label("session_00000000_sample.csv", df).startswith("Sample data · "))
        self.assertFalse(sessions.label("session_20261011_120000.csv", df).startswith("Sample"))

    def test_files_from_older_versions_still_count_as_sample_data(self):
        old = os.path.join(self.folder, "session_00000000_" + "demo.csv")
        sample_data.write_sample(old)
        self.assertTrue(sessions.is_sample(os.path.basename(old)))
        self.assertTrue(sessions.is_sample("session_00000003_sample.csv"))
        self.assertFalse(sessions.is_sample("session_20261011_120000.csv"))
        sessions.generate_sample()                                # replaces it, no duplicate
        self.assertEqual(sorted(os.listdir(self.folder)), ["session_00000000_sample.csv"])

    def test_the_session_table_marks_sample_data(self):
        sessions.generate_sample()
        found = {os.path.basename(p): sessions.read_session(p) for p in sessions.saved_paths()}
        table = sessions.session_table(found)
        self.assertEqual(table["sample"].tolist(), [True])
        self.assertNotIn("demo", table.columns)

    def test_button_names(self):
        def text(*parts):
            with open(os.path.join(PROJECT, *parts), encoding="utf-8") as f:
                return f.read()
        self.assertIn('"Load sample session"', text("pages", "session_dashboard.py"))
        self.assertIn('"Load sample week"', text("pages", "insights.py"))
        self.assertIn('"Sample data"', text("pages", "insights.py"))
        self.assertIn('"See a sample session"', text("app.py"))
        for page in (text("pages", "session_dashboard.py"), text("pages", "insights.py"), text("app.py")):
            self.assertNotIn("Generate", page)


if __name__ == "__main__":
    unittest.main()
