"""My Profile - what you wear on your eyes, your lens power and your safe distance."""

from urllib.parse import urlparse

import streamlit as st

import profiles
import ui

ui.page_header("My Profile", "Tell EyeGuard what you wear at the computer so the distance reading is right for you.")

WEAR = [("none", "Nothing", ":material/visibility:"),
        ("glasses", "Glasses", ":material/eyeglasses:"),
        ("contacts", "Contact lenses", ":material/lens:")]
NO_PROFILE = "No profile"
state = st.session_state


def on_this_laptop():
    """True when the website runs on your own computer (not on the public site),
    so it is safe to read and write the desktop app's profiles.json."""
    try:
        return urlparse(st.context.url).hostname in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


local = on_this_laptop()


# ------------------------------------------------------- where profiles are kept
# On your own laptop: profiles.json, shared with the desktop app.
# On the public website: only this browser tab, never the server's disk.
def stored():
    if not local:
        return state.setdefault("web_profiles", [])
    try:
        return profiles.load_all()
    except ValueError as err:
        st.warning(str(err), icon=":material/warning:")
        return []


def store(profile):
    if local:
        return profiles.save(profile)
    others = [p for p in stored() if profiles.name_key(p["name"]) != profiles.name_key(profile["name"])]
    state["web_profiles"] = sorted(others + [profile], key=lambda p: p["name"].casefold())
    return profile


def remove(name):
    if local:
        profiles.delete(name)
    else:
        state["web_profiles"] = [p for p in stored()
                                 if profiles.name_key(p["name"]) != profiles.name_key(name)]


def same_name(a, b):
    return profiles.name_key(a) == profiles.name_key(b)


def set_active(profile):
    """Makes this the profile Live Check uses (None = no profile) and resets the form."""
    if profile:
        state["profile"] = profile
    else:
        state.pop("profile", None)
    state.pop("high_power_shown", None)
    state["form_new"] = False
    state["form_version"] = state.get("form_version", 0) + 1
    for flag in ("confirm_delete", "duplicate"):
        state.pop(flag, None)


saved = stored()
active = state.get("profile")

# ------------------------------------------------------------- active profile
with st.container(border=True):
    names = [p["name"] for p in saved]
    if active and not any(same_name(active["name"], n) for n in names):
        names.append(active["name"])                 # in use but not saved yet
    options = [NO_PROFILE] + names
    current = next((n for n in names if active and same_name(n, active["name"])), NO_PROFILE)
    pick_col, new_col = st.columns([3, 1], vertical_alignment="bottom")
    pick = pick_col.selectbox("Active profile", options, index=options.index(current),
                              help="Live Check uses the profile chosen here.")
    if new_col.button("New profile", icon=":material/add:", use_container_width=True):
        state["form_new"] = True
        state["form_version"] = state.get("form_version", 0) + 1
        st.rerun()
    if pick != current:
        chosen = next((p for p in saved if same_name(p["name"], pick)), None)
        set_active(chosen)
        st.rerun()
    if active:
        calibrated = profiles.is_calibrated(active)
        st.caption(f"**{active['name']}** · {profiles.describe(active)} · safe distance "
                   f"{active['safe_distance_cm']} cm")
        (st.success if calibrated else st.info)(
            profiles.calibration_status(active),
            icon=":material/straighten:" if calibrated else ":material/info:")
    else:
        st.caption("No profile in use: EyeGuard uses the usual 50 cm and no correction.")

# ------------------------------------------------------------------- the form
editing = None if state.get("form_new") or not active else active
version = state.get("form_version", 0)
start = editing or profiles.make("New profile")
wear_key = f"wear_{version}"
state.setdefault(wear_key, start["correction"])

with st.container(border=True):
    st.subheader(f"Edit {editing['name']}" if editing else "New profile")
    name = st.text_input("Name", editing["name"] if editing else "", max_chars=60,
                         key=f"name_{version}", placeholder='For example "Sujan - glasses"',
                         help="You can keep one profile for glasses and another for "
                              "contact lenses.")
    st.markdown("**What do you wear at the computer?**")
    for column, (value, label, icon) in zip(st.columns(3), WEAR):
        if column.button(label, icon=icon, key=f"wear_{value}_{version}", use_container_width=True,
                         type="primary" if state[wear_key] == value else "secondary"):
            state[wear_key] = value
            st.rerun()
    correction = state[wear_key]
    power = 0.0
    if profiles.needs_power(correction):             # only asked for glasses and contacts
        power = st.number_input(
            "Lens power (dioptres)", profiles.POWER_MIN, profiles.POWER_MAX,
            float(start["power"]), profiles.POWER_STEP, format="%.2f", key=f"power_{version}",
            help="One value for both eyes is fine. EyeGuard cannot measure this.")
        st.caption(profiles.POWER_HINT.capitalize() + ". Use − and + to change it "
                   "in steps of 0.25.")
    top = max(profiles.FORM_MAX_SAFE_DISTANCE_CM, int(start["safe_distance_cm"]))
    safe = st.slider("Safe distance from the screen (cm)", profiles.DEFAULT_SAFE_DISTANCE_CM,
                     top, int(start["safe_distance_cm"]), key=f"safe_{version}",
                     help="Closer than this counts as too close. 50 cm is about arm's length.")

    # a calibration belongs to the lenses it was made with
    keep = bool(editing) and (correction, power) == (editing["correction"], editing["power"])
    result, value = profiles.check_form(name, correction, power, safe, saved=saved)
    renamed = bool(editing) and result != "error" and not same_name(name, editing["name"])
    updating = bool(editing) and not renamed

    with st.container(horizontal=True):
        save_clicked = st.button("Save", type="primary", icon=":material/save:")
        if editing and st.button("Delete", icon=":material/delete:"):
            state["confirm_delete"] = editing["name"]
        if state.get("form_new") and active and st.button("Cancel", icon=":material/close:"):
            set_active(active)
            st.rerun()

    if save_clicked:
        if result == "error":
            st.error(value, icon=":material/error:")
        elif result == "duplicate" and not updating:
            state["duplicate"] = value["name"]
        else:
            profile = profiles.make(name, correction, power, safe,
                                    editing["focal_px"] if keep else None,
                                    editing["calibrated_on"] if keep else None)
            try:
                if renamed:
                    remove(editing["name"])
                set_active(store(profile))
                st.toast(f"Saved {profile['name']}. Live Check will use it.",
                         icon=":material/check_circle:")
                st.rerun()
            except (OSError, ValueError) as err:
                st.error(f"Could not save: {err}", icon=":material/error:")

    if state.get("duplicate"):
        existing = next((p for p in saved if same_name(p["name"], state["duplicate"])), None)
        if existing:
            st.warning(f"A profile called **{existing['name']}** is already saved "
                       f"({profiles.describe(existing)}). Use it, or choose a different name.",
                       icon=":material/content_copy:")
            if st.button("Use the existing profile", icon=":material/check:"):
                set_active(existing)
                st.rerun()

    if state.get("confirm_delete"):
        doomed = state["confirm_delete"]
        st.warning(f"Delete **{doomed}**? Its saved calibration goes too. This cannot be undone.",
                   icon=":material/delete:")
        with st.container(horizontal=True):
            if st.button("Yes, delete it", icon=":material/delete_forever:"):
                remove(doomed)
                if active and same_name(active["name"], doomed):
                    set_active(None)
                state.pop("confirm_delete", None)
                st.toast(f"Deleted {doomed}", icon=":material/check_circle:")
                st.rerun()
            if st.button("Keep it"):
                state.pop("confirm_delete", None)
                st.rerun()

# ----------------------------------------------------------- live explanation
try:                                             # shown even before the name is typed
    draft = profiles.make(name.strip() or "New profile", correction, power, safe,
                          editing["focal_px"] if keep else None,
                          editing["calibrated_on"] if keep else None)
except ValueError:
    draft = None
if draft:
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
        st.caption(f"Calibrated on {draft['calibrated_on']}: EyeGuard uses this calibration "
                   "instead of the formula, because it already includes your lenses.")
    else:
        st.caption("The best accuracy comes from calibrating: " + profiles.calibration_note(draft)
                   + " in the desktop app, or click **Calibrate distance** in Live Check.")
    if profiles.high_power_note(draft):
        st.caption(":material/visibility: " + profiles.high_power_note(draft))
    if editing and not keep and profiles.is_calibrated(editing):
        st.caption("Changing what you wear or the power clears the old calibration when you save.")

st.page_link("pages/live_check.py", label="Go to Live Check", icon=":material/videocam:")

st.divider()
st.caption(("Profiles are saved in profiles.json on this laptop, shared with the desktop app. "
            if local else "Your profiles stay in this browser tab and are never saved on the server. ")
           + "EyeGuard cannot measure or diagnose eye power, and astigmatism is ignored. "
           "This is an awareness tool, not a medical device.")
