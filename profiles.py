"""
User profiles for EyeGuard: who is using it and what they wear on their eyes.

Each profile is saved in profiles.json next to this file (git-ignored, it
never leaves your laptop):

    name              e.g. "Sujan - glasses"
    correction        "none", "glasses" or "contacts"
    power             spherical lens power in dioptres, -20 to +20 in steps
                      of 0.25 (one value for both eyes); 0 for "none"
    safe_distance_cm  closer than this counts as too close (50 or more)
    focal_px          camera focal length saved by calibration, or null
    calibrated_on     date of that calibration, or null

One person can have several profiles, for example one for glasses and one
for contact lenses. EyeGuard cannot measure eye power: the number comes
from your prescription.

Why the power matters: EyeGuard measures distance from how big your iris
looks to the camera. Glasses change that. A minus lens makes the eye look
smaller (so you seem further away than you are), a plus lens bigger:

    m = 1 / (1 - d * P)      P = lens power in dioptres
                             d = lens-to-eye distance, about 0.015 m
    corrected distance = raw distance * m

Contact lenses sit on the eye, so m = 1. Astigmatism (cylinder) is ignored.
A calibration made while wearing the glasses already includes this effect,
so a profile with a saved calibration does not use the formula.
"""

import json
import os
import tempfile
import unicodedata
from datetime import date

PROFILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json")

CORRECTIONS = ("none", "glasses", "contacts")
CORRECTION_LABELS = {"none": "no glasses or contacts", "glasses": "glasses",
                     "contacts": "contacts"}
POWER_MIN, POWER_MAX, POWER_STEP = -20.0, 20.0, 0.25
DEFAULT_SAFE_DISTANCE_CM = 50        # same as MIN_SAFE_DISTANCE_CM in eyeguard.py
MAX_SAFE_DISTANCE_CM = 100
LENS_DISTANCE_M = 0.015              # glasses sit about 15 mm in front of the eye
HIGH_POWER_D = 6.0                   # at or above this, show the eye check-up reminder
CALIBRATION_DISTANCE_CM = 50         # where you sit when you press c
FOCAL_MIN_PX, FOCAL_MAX_PX = 50, 20000   # any real webcam is well inside this
DASHES = "‐‑‒–—―−"     # hyphens, en/em dashes, minus sign


# ------------------------------------------------------------------- values
def name_key(name):
    """Names match whatever the capitals, spacing or kind of dash:
    "Sujan – glasses", "sujan - glasses" and "SUJAN-glasses" are one profile."""
    text = str(name)
    for dash in DASHES:
        text = text.replace(dash, "-")
    return "".join(text.casefold().split()).replace("-", "")


def to_ascii(text):
    """Plain-ASCII version of a name for the video panel, whose font has no
    long dashes or accents: "Sujan – glasses" becomes "Sujan - glasses"."""
    text = str(text)
    for dash in DASHES:
        text = text.replace(dash, "-")
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(plain.split())           # "" if the name has no such letters at all


def parse_power(text):
    """Turns what the user typed ("-7", "−2,5", "+3.00 D") into dioptres,
    rounded to the nearest 0.25. Raises ValueError with a reason if it cannot."""
    cleaned = str(text).strip().lower().replace(",", ".")
    for dash in DASHES:
        cleaned = cleaned.replace(dash, "-")
    cleaned = cleaned.replace("dioptres", "").replace("diopters", "").replace("d", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError("type a number such as -2.5 or +1.75") from None
    if value != value or not POWER_MIN <= value <= POWER_MAX:
        raise ValueError(f"power must be between {POWER_MIN:g} and +{POWER_MAX:g}")
    return round(value / POWER_STEP) * POWER_STEP + 0.0      # + 0.0 turns -0.0 into 0.0


def parse_safe_distance(text):
    """Safe distance in whole centimetres, DEFAULT_SAFE_DISTANCE_CM or more."""
    try:
        value = float(str(text).strip().lower().replace("cm", "").replace(",", "."))
    except ValueError:
        raise ValueError("type a number of centimetres such as 60") from None
    if value != value or not DEFAULT_SAFE_DISTANCE_CM <= value <= MAX_SAFE_DISTANCE_CM:
        raise ValueError(f"safe distance must be between {DEFAULT_SAFE_DISTANCE_CM} "
                         f"and {MAX_SAFE_DISTANCE_CM} cm")
    return int(round(value))


def make(name, correction="none", power=0.0, safe_distance_cm=DEFAULT_SAFE_DISTANCE_CM,
         focal_px=None, calibrated_on=None):
    """A checked profile dictionary. Raises ValueError if a value is not allowed."""
    name = " ".join(str(name).split())
    if not name:
        raise ValueError("the profile needs a name")
    if correction not in CORRECTIONS:
        raise ValueError("correction must be one of: " + ", ".join(CORRECTIONS))
    power = 0.0 if correction == "none" else parse_power(power)
    if focal_px is not None:
        focal_px = float(focal_px)
        if not FOCAL_MIN_PX <= focal_px <= FOCAL_MAX_PX:
            raise ValueError("the saved focal length must be between "
                             f"{FOCAL_MIN_PX} and {FOCAL_MAX_PX} pixels")
    return {"name": name, "correction": correction, "power": power,
            "safe_distance_cm": parse_safe_distance(safe_distance_cm),
            "focal_px": focal_px, "calibrated_on": calibrated_on if focal_px else None}


def describe(profile):
    """Short text for the on-screen panel: "glasses -7.00 D", "contacts +1.25 D"
    or "no glasses or contacts"."""
    if profile["correction"] == "none":
        return CORRECTION_LABELS["none"]
    return f"{CORRECTION_LABELS[profile['correction']]} {profile['power']:+.2f} D"


def summary(profile):
    """One line for the terminal."""
    return (f"{profile['name']}: {describe(profile)}, safe distance "
            f"{profile['safe_distance_cm']} cm")


# ------------------------------------------------------- glasses and distance
def lens_magnification(correction, power):
    """How big glasses make the eye look to the camera, compared with no
    glasses: m = 1 / (1 - d * P). Below 1 for minus lenses, above 1 for plus
    lenses, exactly 1 for contact lenses or no correction."""
    if correction != "glasses":
        return 1.0
    return 1.0 / (1.0 - LENS_DISTANCE_M * power)


def is_calibrated(profile):
    return bool(profile and profile["focal_px"])


def distance_factor(profile):
    """What to multiply the raw distance by for this profile.
    1 with no profile, and 1 once the profile has a saved calibration
    (calibrating while wearing the glasses already includes the lens)."""
    if not profile or is_calibrated(profile):
        return 1.0
    return lens_magnification(profile["correction"], profile["power"])


def corrected_distance(raw_cm, profile):
    return raw_cm * distance_factor(profile)


def explain(profile):
    """One plain sentence about what this profile changes, for the My Profile page."""
    if not profile or profile["correction"] == "none":
        return "No glasses or contacts, so EyeGuard uses the iris size as it is."
    if profile["correction"] == "contacts":
        return ("Contact lenses sit on the eye and barely change how big it looks, "
                "so no correction is needed.")
    if profile["power"] == 0:
        return "Glasses with no power do not change how big your eyes look to the camera."
    m = lens_magnification("glasses", profile["power"])
    percent = abs(1 - m) * 100
    size = "smaller" if m < 1 else "bigger"
    return (f"At {profile['power']:+.2f} D your eyes look about {percent:.0f}% {size} to the "
            "camera; EyeGuard corrects for this.")


def estimate_note(profile):
    """Shown while the distance is only estimated from the lens power."""
    if (not profile or is_calibrated(profile) or profile["correction"] != "glasses"
            or profile["power"] == 0):
        return None
    return (f"Estimated for {profile['power']:+.2f} D glasses \u2014 press c to calibrate "
            "for best accuracy")


def calibration_note(profile):
    """What to do before pressing c. None once the profile is calibrated."""
    if not profile or is_calibrated(profile):
        return None
    if profile["correction"] == "none":
        return f"Sit {CALIBRATION_DISTANCE_CM} cm away, then press c to calibrate distance."
    return ("Wear the glasses or contacts you normally use at the computer, sit "
            f"{CALIBRATION_DISTANCE_CM} cm away, then press c.")


def high_power_note(profile):
    """A gentle once-per-session reminder for strong lenses. Not a diagnosis."""
    if not profile or profile["correction"] == "none" or abs(profile["power"]) < HIGH_POWER_D:
        return None
    wearing = "glasses" if profile["correction"] == "glasses" else "contact lens"
    return f"Your {wearing} power is high. Remember to get a full eye check-up regularly."


def save_calibration(profile, focal_px, today=None, path=None):
    """Stores a new calibration in the profile and saves it. Returns the profile."""
    updated = dict(profile, focal_px=float(focal_px),
                   calibrated_on=today or date.today().isoformat())
    return save(updated, path)


# ---------------------------------------------------------------- the file
def load_all(path=None):
    """Every saved profile as a list (empty if there is no file yet).
    Raises ValueError with a friendly message if the file is damaged."""
    path = path or PROFILES_PATH
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)["profiles"]
        return [make(**{field: p.get(field) for field in
                        ("name", "correction", "power", "safe_distance_cm",
                         "focal_px", "calibrated_on")})
                for p in saved]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        raise ValueError(f"{os.path.basename(path)} could not be read ({err}). "
                         "Fix the file, or delete it to start again.") from err


def find(name, path=None):
    """The saved profile with this name, or None."""
    for profile in load_all(path):
        if name_key(profile["name"]) == name_key(name):
            return profile
    return None


def save(profile, path=None):
    """Adds the profile, or replaces the saved one with the same name."""
    path = path or PROFILES_PATH
    profile = make(**profile)
    others = [p for p in load_all(path) if name_key(p["name"]) != name_key(profile["name"])]
    everyone = sorted(others + [profile], key=lambda p: p["name"].casefold())
    # write to a temporary file first so a crash never leaves half a file
    handle, part = tempfile.mkstemp(suffix=".json", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "profiles": everyone}, f, indent=2, ensure_ascii=False)
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return profile


# ----------------------------------------------------- terminal questionnaire
def _ask(ask, say, question, default, parse):
    """Asks until the answer is valid. Enter (or no keyboard) gives the default."""
    for _ in range(5):
        try:
            answer = ask(question).strip()
        except EOFError:
            return default
        if not answer:
            return default
        try:
            return parse(answer)
        except ValueError as err:
            say(f"   Sorry, {err}.")
    say("   Using the default.")
    return default


def _parse_correction(answer):
    choice = {"n": "none", "g": "glasses", "c": "contacts"}.get(answer.lower()[:1])
    if choice is None:
        raise ValueError("type n, g or c")
    return choice


def questionnaire(name, ask=input, say=print):
    """Three short questions in the terminal. Returns a new profile (not saved yet)."""
    say(f'\nNew profile "{name}". Three quick questions; press Enter to keep the '
        "answer in [brackets].")
    correction = _ask(
        ask, say, "1. What do you wear at the computer?  n = nothing, g = glasses, "
                  "c = contact lenses [n]: ", "none", _parse_correction)
    power = 0.0
    if correction != "none":
        say("   EyeGuard cannot measure eye power. Use the number on your prescription;")
        say("   it is minus for short sight, plus for long sight. One value for both eyes is fine.")
        power = _ask(ask, say, "2. Lens power in dioptres, for example -2.5 [0]: ", 0.0,
                     parse_power)
    else:
        say("2. Lens power: skipped (no glasses or contacts).")
    safe = _ask(
        ask, say, f"3. Safe distance from the screen in cm, {DEFAULT_SAFE_DISTANCE_CM} or more "
                  f"[{DEFAULT_SAFE_DISTANCE_CM}]: ", DEFAULT_SAFE_DISTANCE_CM, parse_safe_distance)
    return make(name, correction, power, safe)


def load_or_create(name, ask=input, say=print, path=None):
    """The profile for --profile NAME: loads it if it is saved, otherwise asks
    the questions and saves it."""
    name = " ".join(str(name).split())
    if not name:                                 # say so before asking anything
        raise ValueError('the profile needs a name, for example --profile "Sujan - glasses"')
    profile = find(name, path)
    if profile:
        say(f"Profile loaded - {summary(profile)}")
        return profile
    known = [p["name"] for p in load_all(path)]
    if known:
        say("Saved profiles: " + ", ".join(known))
    profile = save(questionnaire(name, ask, say), path)
    say(f"Profile saved - {summary(profile)}\n")
    return profile
