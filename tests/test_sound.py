"""Sound: a tone plus a Windows system sound, played in the background,
with a one-time warning if nothing could be played.

Run all tests with:   py -m unittest discover -s tests -v
"""

import contextlib
import io
import sys
import time
import types
import unittest

from fake_desktop import run_desktop

import eyeguard


class FakeWinsound(types.ModuleType):
    """Stands in for Python's winsound and records what was asked for."""
    SND_ALIAS, SND_ASYNC, MB_ICONEXCLAMATION = 0x10000, 0x1, 0x30

    def __init__(self, beep_fails=False, playsound_fails=False, messagebeep_fails=False,
                 beep_takes=0.0):
        super().__init__("winsound")
        self.calls, self.beep_takes = [], beep_takes
        self.fails = {"Beep": beep_fails, "PlaySound": playsound_fails,
                      "MessageBeep": messagebeep_fails}

    def _call(self, name, *args):
        self.calls.append((name, *args))
        if self.fails[name]:
            raise RuntimeError(f"{name} failed")

    def Beep(self, freq, ms):
        time.sleep(self.beep_takes)
        self._call("Beep", freq, ms)

    def PlaySound(self, sound, flags):
        self._call("PlaySound", sound, flags)

    def MessageBeep(self, kind=-1):
        self._call("MessageBeep", kind)


class SoundTest(unittest.TestCase):
    def setUp(self):
        self.real_module = sys.modules.get("winsound")
        self.real_platform = sys.platform
        sys.platform = "win32"
        eyeguard._sound_warning_shown = False

    def tearDown(self):
        sys.platform = self.real_platform
        if self.real_module is None:
            sys.modules.pop("winsound", None)
        else:
            sys.modules["winsound"] = self.real_module

    def play(self, fake, *args):
        sys.modules["winsound"] = fake
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            eyeguard.beep(*args, wait=True)
        return out.getvalue()

    def test_plays_the_tone_and_also_a_system_sound(self):
        fake = FakeWinsound()
        printed = self.play(fake, *eyeguard.SOUNDS["alert"])
        self.assertEqual(fake.calls, [("Beep", 1000, 300),
                                      ("PlaySound", "SystemExclamation",
                                       fake.SND_ALIAS | fake.SND_ASYNC)])    # asynchronous
        self.assertEqual(printed, "")

    def test_system_sound_still_plays_when_the_tone_is_ignored(self):
        fake = FakeWinsound(beep_fails=True)
        printed = self.play(fake)
        self.assertEqual([c[0] for c in fake.calls], ["Beep", "PlaySound"])
        self.assertEqual(printed, "")                           # something was heard: no warning

    def test_message_beep_is_the_fallback(self):
        fake = FakeWinsound(beep_fails=True, playsound_fails=True)
        printed = self.play(fake)
        self.assertEqual([c[0] for c in fake.calls], ["Beep", "PlaySound", "MessageBeep"])
        self.assertEqual(printed, "")

    def test_one_warning_when_nothing_can_be_played(self):
        fake = FakeWinsound(beep_fails=True, playsound_fails=True, messagebeep_fails=True)
        first = self.play(fake)
        self.assertIn("Warning: EyeGuard could not play a sound", first)
        self.assertIn("Beep failed", first)
        self.assertIn("Alerts still appear on screen", first)
        self.assertEqual(self.play(fake), "")                   # only once
        self.assertEqual(self.play(fake), "")

    def test_the_video_does_not_wait_for_the_sound(self):
        fake = FakeWinsound(beep_takes=0.4)
        sys.modules["winsound"] = fake
        started = time.perf_counter()
        eyeguard.beep()                                         # no wait
        self.assertLess(time.perf_counter() - started, 0.1)
        deadline = time.time() + 3
        while len(fake.calls) < 2 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual([c[0] for c in fake.calls], ["Beep", "PlaySound"])

    def test_the_three_sounds_are_different(self):
        self.assertEqual(set(eyeguard.SOUNDS), {"alert", "pause", "done"})
        self.assertEqual(len({s[0] for s in eyeguard.SOUNDS.values()}), 3)   # three tones
        self.assertLess(eyeguard.SOUNDS["pause"][1], eyeguard.SOUNDS["alert"][1])   # pause is short

    def test_test_sound_plays_each_sound_once(self):
        fake = FakeWinsound()
        sys.modules["winsound"] = fake
        real_sleep, eyeguard.time.sleep = eyeguard.time.sleep, lambda seconds: None
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                eyeguard.test_sound()
        finally:
            eyeguard.time.sleep = real_sleep
        self.assertEqual([c[1] for c in fake.calls if c[0] == "Beep"], [1000, 800, 1200])
        self.assertEqual([c[1] for c in fake.calls if c[0] == "PlaySound"],
                         ["SystemExclamation", "SystemDefault", "SystemAsterisk"])
        for text in ("alert / break starting", "break paused", "break done", "Heard nothing?"):
            self.assertIn(text, out.getvalue())


class TestSoundFlagTest(unittest.TestCase):
    def test_test_sound_exits_without_opening_the_camera(self):
        played = []
        real = eyeguard.test_sound
        eyeguard.test_sound = lambda: played.append("played")
        try:
            r = run_desktop(["--test-sound"], frames=5)
        finally:
            eyeguard.test_sound = real
        self.assertEqual(played, ["played"])
        self.assertEqual(r["texts"], [])                # no frame was read or drawn
        self.assertEqual(r["files"], [])                # no session log
        self.assertNotIn("EyeGuard running", r["printed"])


if __name__ == "__main__":
    unittest.main()
