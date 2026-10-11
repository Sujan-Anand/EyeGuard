"""Session Dashboard - KPI cards, charts and tips for one EyeGuard session."""

import os

import streamlit as st

import charts
import sessions
from report import BLINK_ALERT_RATE, BLINK_WARN_RATE, MIN_SAFE_DISTANCE_CM
import ui

ui.page_header("Session dashboard", "One session at a glance: blinking, distance, breaks and strain.")


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
        "- run a **Live Check** and open it here when you stop the video, or\n"
        "- upload a CSV saved by the desktop app (`py eyeguard.py --demo`).",
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
ui.kpi_row(sessions.kpi_cards(s))        # every card: a unit and a status in words

# --------------------------------------------------------------------- charts
st.subheader("Over time")
st.caption("Bold line = 30-second average. Grey bars = breaks. Dashed lines = limits: "
           "amber is a warning, red is an alert. Each line is labelled.")
st.plotly_chart(
    charts.timeline(df, "blink_rate", "Blink rate", "Blinks per minute",
                    limits=[(BLINK_WARN_RATE, f"Warning below {BLINK_WARN_RATE}/min", "warn"),
                            (BLINK_ALERT_RATE, f"Strong alert below {BLINK_ALERT_RATE}/min")],
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
for tip in sessions.tip_cards(df, s, tips):          # most important first
    ui.tip_card(tip["text"], icon=tip["icon"], title=tip["title"], kind=tip["kind"])

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
