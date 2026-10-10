"""Session Dashboard - KPI cards, charts and tips for one EyeGuard session."""

import math
import os

import streamlit as st

import charts
import sessions
from report import LOW_BLINK_RATE, MIN_SAFE_DISTANCE_CM

st.title("Session dashboard")
st.caption("Explore one EyeGuard session: blink rate, distance, breaks and strain score.")


def show(value, pattern):
    """Formats a number, or shows a dash when there is no data (NaN)."""
    return "–" if value is None or math.isnan(value) else pattern.format(value)


# ---------------------------------------------------------- choose a session
with st.container(border=True):
    pick_col, add_col = st.columns(2)
    uploaded = add_col.file_uploader(
        "Upload a session CSV", type="csv",
        help="The desktop app saves one CSV per session in its logs folder.")
    demo_clicked = add_col.button(
        "Generate demo session", icon=":material/science:",
        help="Creates a realistic 60-minute session so you can try the dashboard.")

if uploaded is not None and uploaded.file_id != st.session_state.get("last_upload_id"):
    st.session_state["last_upload_id"] = uploaded.file_id       # handle each file once
    try:
        sessions.uploads()[uploaded.name] = sessions.read_session(uploaded)
        st.session_state["selected_session"] = uploaded.name
    except ValueError as err:
        st.error(f"Could not use {uploaded.name}: {err}.")

if demo_clicked:
    st.session_state["selected_session"] = os.path.basename(sessions.generate_demo())
    st.toast("Demo session created", icon=":material/check_circle:")

found = sessions.all_sessions()
if not found:
    pick_col.info(
        "**No sessions yet.** You can:\n"
        "- click **Generate demo session** to see an example,\n"
        "- upload a CSV saved by the desktop app, or\n"
        "- record one with `py eyeguard.py --demo` and come back.",
        icon=":material/info:")
    st.stop()

names = list(found)
if st.session_state.get("selected_session") not in names:
    st.session_state["selected_session"] = names[-1]            # newest session
name = pick_col.selectbox("Session", names, key="selected_session",
                          format_func=lambda n: sessions.label(n, found[n]))
df = found[name]
pick_col.caption(f"{len(names)} session(s) available. Uploaded files stay in your "
                 "browser session only.")

try:
    s, tips = sessions.summarise(df)
except Exception as err:
    st.error(f"This session could not be summarised ({err}). Try another file.")
    st.stop()

# ------------------------------------------------------------------ KPI cards
blink, close = s["avg_blink_rate"], s["too_close_pct"]
if math.isnan(s["avg_distance"]):
    close = float("nan")                 # no distance readings -> nothing to report
if math.isnan(blink):
    blink_note, blink_colour = None, "off"
elif blink >= 15:
    blink_note, blink_colour = "healthy", "normal"
elif blink >= LOW_BLINK_RATE:
    blink_note, blink_colour = "below normal", "off"
else:
    blink_note, blink_colour = "too low", "inverse"

with st.container(horizontal=True):
    st.metric("Duration", show(s["minutes"], "{:.0f} min"), border=True)
    st.metric("Average blink rate", show(blink, "{:.1f} / min"), blink_note,
              delta_color=blink_colour, delta_arrow="off", border=True,
              help="Healthy is about 15-20 blinks per minute.")
    st.metric("Average distance", show(s["avg_distance"], "{:.0f} cm"), border=True,
              help=f"Keep at least {MIN_SAFE_DISTANCE_CM} cm from the screen.")
    st.metric("Time too close", show(close, "{:.0f}%"),
              None if math.isnan(close) else ("often" if close > 20 else "fine"),
              delta_color="inverse" if close > 20 else "normal", delta_arrow="off",
              border=True, help=f"Share of the session closer than {MIN_SAFE_DISTANCE_CM} cm.")
with st.container(horizontal=True):
    st.metric("Breaks completed", s["breaks"], border=True,
              help="20-20-20 breaks where the camera saw you look away for 20 seconds.")
    st.metric("Average strain score", show(s["avg_score"], "{:.0f} / 100"), border=True,
              help="0 = relaxed eyes, 100 = heavy strain.")
    st.metric("Peak strain score", f"{s['peak_score']} / 100", border=True)

# --------------------------------------------------------------------- charts
st.subheader("Over time")
st.caption("Bold line = 30-second rolling average. Grey bars = break periods. "
           "Dashed red lines = limits.")
st.plotly_chart(
    charts.timeline(df, "blink_rate", "Blink rate", "Blinks per minute",
                    limits=[(LOW_BLINK_RATE, f"Alert below {LOW_BLINK_RATE}/min")],
                    band=(15, 20, "Healthy 15-20/min")),
    config=charts.CONFIG, alt="Blink rate over the session")
st.plotly_chart(
    charts.timeline(df, "distance_cm", "Distance from screen", "Centimetres",
                    limits=[(MIN_SAFE_DISTANCE_CM, f"Too close below {MIN_SAFE_DISTANCE_CM} cm")]),
    config=charts.CONFIG, alt="Distance from the screen over the session")
st.plotly_chart(
    charts.timeline(df, "strain_score", "Eye strain score", "Score (0-100)",
                    limits=[(50, "High strain above 50")], y_range=[0, 100], fill=True),
    config=charts.CONFIG, alt="Eye strain score over the session")

# ----------------------------------------------------------------------- tips
st.subheader("Tips for you")
for tip in tips:
    if tip.startswith("Great session"):
        st.success(tip, icon=":material/thumb_up:")
    else:
        st.warning(tip, icon=":material/lightbulb:")

# ------------------------------------------------------------------ downloads
st.subheader("Download")
with st.container(horizontal=True):
    st.download_button(
        "Session data (CSV)", df.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S"),
        file_name=name, mime="text/csv", icon=":material/download:")
    st.download_button(
        "Session report (PNG)", sessions.report_png(df),
        file_name=os.path.splitext(name)[0] + "_report.png", mime="image/png",
        icon=":material/image:")

with st.expander("View the data as a table"):
    st.dataframe(df, hide_index=True, alt="Session data, one row per second")
