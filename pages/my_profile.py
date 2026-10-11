"""My Profile - what you wear on your eyes, your lens power and your safe distance."""

from urllib.parse import urlparse

import streamlit as st

import profiles

st.title("My Profile")
st.caption("Tell EyeGuard what you wear at the computer so the distance reading is "
           "right for you.")

LABELS = {"none": "Nothing", "glasses": "Glasses", "contacts": "Contact lenses"}


def on_this_laptop():
    """True when the website runs on your own computer (not on the public site),
    so it is safe to read and write the desktop app's profiles.json."""
    try:
        return urlparse(st.context.url).hostname in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


local = on_this_laptop()
active = st.session_state.get("profile")

# ------------------------------------------------ profiles saved by the desktop app
if local:
    try:
        saved = profiles.load_all()
    except ValueError as err:
        saved = []
        st.warning(str(err), icon=":material/warning:")
    if saved:
        with st.container(border=True):
            names = [p["name"] for p in saved]
            pick = st.selectbox("Profiles saved by the desktop app on this laptop", names,
                                index=None, placeholder="Choose one to load")
            if pick and st.button("Use this profile", icon=":material/download:"):
                st.session_state["profile"] = active = profiles.find(pick)
                st.session_state.pop("high_power_shown", None)
                st.toast(f"Loaded {pick}", icon=":material/check_circle:")

# ------------------------------------------------------------------- the form
start = active or profiles.make("My profile")
with st.container(border=True):
    name = st.text_input("Profile name", start["name"], max_chars=60,
                         help='For example "Sujan - glasses". You can keep one profile '
                              "for glasses and another for contact lenses.")
    correction = st.segmented_control(
        "What do you wear at the computer?", list(LABELS), format_func=LABELS.get,
        default=start["correction"]) or "none"
    power = 0.0
    if correction != "none":
        power = st.number_input(
            "Lens power in dioptres (spherical)", profiles.POWER_MIN, profiles.POWER_MAX,
            float(start["power"]), profiles.POWER_STEP, format="%.2f",
            help="The number on your prescription: minus for short sight, plus for long "
                 "sight. One value for both eyes is fine. EyeGuard cannot measure this.")
    safe = st.slider("Safe distance from the screen (cm)", profiles.DEFAULT_SAFE_DISTANCE_CM,
                     profiles.MAX_SAFE_DISTANCE_CM, int(start["safe_distance_cm"]),
                     help="Closer than this counts as too close. 50 cm is about arm's length.")

try:
    same_person = bool(active) and profiles.name_key(name) == profiles.name_key(active["name"])
    keep = same_person and (correction, power) == (active["correction"], active["power"])
    draft = profiles.make(name, correction, power, safe,
                          active["focal_px"] if keep else None,       # a calibration belongs
                          active["calibrated_on"] if keep else None)  # to the lenses it was made with
except ValueError as err:
    st.error(f"Please check the form: {err}.", icon=":material/error:")
    st.stop()

# ----------------------------------------------------------- live explanation
st.subheader("What this means")
st.info(profiles.explain(draft), icon=":material/lightbulb:")
if correction == "glasses" and power:
    m = profiles.lens_magnification("glasses", power)
    with st.container(horizontal=True):
        st.metric("Lens factor m", f"{m:.3f}", border=True,
                  help="m = 1 / (1 - 0.015 x power). Raw distance is multiplied by this.")
        st.metric("A raw reading of 60 cm becomes", f"{60 * m:.0f} cm", border=True)
        st.metric("Too close below", f"{safe} cm", border=True)
if profiles.is_calibrated(draft):
    st.success(f"Calibrated on {draft['calibrated_on']}. Live Check uses this calibration "
               "instead of the formula, because it already includes your lenses.",
               icon=":material/straighten:")
else:
    st.caption("Not calibrated yet. For the best accuracy, open Live Check, wear the "
               "glasses or contacts you normally use at the computer, sit "
               f"{profiles.CALIBRATION_DISTANCE_CM} cm away and click **Calibrate distance**.")
if profiles.high_power_note(draft):
    st.caption(":material/visibility: " + profiles.high_power_note(draft))
if active and not keep and profiles.is_calibrated(active):
    st.caption("Changing the name, what you wear or the power clears the old calibration.")

# -------------------------------------------------------------------- buttons
with st.container(horizontal=True):
    if st.button("Use this profile" if draft != active else "Profile in use", type="primary",
                 icon=":material/check:", disabled=draft == active):
        st.session_state["profile"] = draft
        st.session_state.pop("high_power_shown", None)
        st.toast("Profile set. Live Check will use it.", icon=":material/check_circle:")
        st.rerun()
    if local and st.button("Save for the desktop app", icon=":material/save:",
                           help="Writes this profile to profiles.json on this laptop, for "
                                'py eyeguard.py --profile "name".'):
        try:
            profiles.save(draft)
            st.session_state["profile"] = draft
            st.toast("Saved to profiles.json", icon=":material/check_circle:")
        except (OSError, ValueError) as err:
            st.error(f"Could not save: {err}")
    if active and st.button("Stop using a profile", icon=":material/person_off:"):
        del st.session_state["profile"]
        st.rerun()

if active:
    st.caption(f"In use now: **{active['name']}** · {profiles.describe(active)} · safe "
               f"distance {active['safe_distance_cm']} cm.")
else:
    st.caption("No profile in use: EyeGuard uses the usual 50 cm and no correction.")
st.page_link("pages/live_check.py", label="Go to Live Check", icon=":material/videocam:")

st.divider()
st.caption("Your profile stays in this browser tab" + (" unless you save it to this laptop" if local else "")
           + ". EyeGuard cannot measure or diagnose eye power, and astigmatism is ignored. "
           "This is an awareness tool, not a medical device.")
