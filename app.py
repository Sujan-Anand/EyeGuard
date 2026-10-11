"""
EyeGuard website - entry point and Home page.
SDG 3.4

Run locally:   py -m streamlit run app.py
"""

import os

import streamlit as st

import sessions
import ui

st.set_page_config(page_title="EyeGuard", page_icon="👁️", layout="wide")
ui.apply_theme()                     # shared colours, type and card styles (ui.py)
ui.sidebar_brand()                   # EyeGuard logo at the top of the sidebar

TEAM = "Built by Sujan Anand, Dhayanithi S V, Padhmesh N, Akshaith P"


def home():
    ui.hero("Blink more. Sit back. Look away.",
            "EyeGuard uses your webcam to notice when you blink too little, sit too "
            "close or skip your breaks, and nudges you before your eyes get tired.",
            "SMART EYE STRAIN MONITOR \u00b7 SDG 3.4")
    with st.container(horizontal=True):
        if st.button("Start live check", type="primary", icon=":material/videocam:"):
            st.switch_page(live_page)
        if st.button("See a sample session", icon=":material/monitoring:"):
            st.session_state["selected_session"] = os.path.basename(sessions.generate_sample())
            st.switch_page(dashboard_page)

    # ------------------------------------------------------------ the problem
    st.header("The problem")
    st.write("Students are on screens most of the day. While we stare at a screen we "
             "blink far less, lean in closer and skip breaks.")
    ui.kpi_row([
        dict(label="Normal blink rate", value="15-20", unit="/ min",
             status="Keeps eyes moist", kind="good"),
        dict(label="Blink rate on a screen", value="5-7", unit="/ min",
             status="About 60% fewer blinks", kind="alert"),
        dict(label="People with myopia by 2050", value="1 in 2", status="Projected",
             kind="warn"),
    ])
    st.caption("Fewer blinks mean dry, tired, burning eyes and headaches. Myopia "
               "projection: Holden et al., Ophthalmology (2016); long hours of "
               "close-up work are a known risk factor.")

    # ----------------------------------------------------------- how it works
    st.header("How EyeGuard works")
    ui.info_cards([
        dict(badge=1, title="It watches",
             text="Your webcam and MediaPipe find 478 points on your face in every "
                  "frame. Video is analysed live and never saved."),
        dict(badge=2, title="It measures",
             text="Blink rate, distance from the screen, drowsiness, head tilt and "
                  "room lighting, combined into an Eye Strain Score from 0 to 100."),
        dict(badge=3, title="It nudges",
             text="Gentle alerts, and a 20-20-20 break that only counts while the "
                  "camera sees you look away."),
    ])

    # -------------------------------------------------------------------- SDGs
    st.header("Sustainable Development Goals")
    ui.info_cards([
        dict(icon="favorite", tag="Primary goal",
             title="SDG 3.4 \u00b7 Good Health and Well-being",
             text="Digital eye strain and myopia are non-communicable and largely "
                  "preventable. EyeGuard builds healthy screen habits before damage "
                  "is done."),
        dict(icon="school", tag="Secondary goal", title="SDG 4 \u00b7 Quality Education",
             text="Learning now happens on screens. Students who look after their "
                  "eyes can study comfortably for longer."),
    ])

    ui.footer(TEAM + " \u00b7 An awareness tool, not a medical device.")


home_page = st.Page(home, title="Home", icon=":material/home:", default=True)
live_page = st.Page("pages/live_check.py", title="Live Check", icon=":material/videocam:")
profile_page = st.Page("pages/my_profile.py", title="My Profile", icon=":material/person:")
dashboard_page = st.Page("pages/session_dashboard.py", title="Session Dashboard",
                         icon=":material/monitoring:")
insights_page = st.Page("pages/insights.py", title="Insights", icon=":material/insights:")
about_page = st.Page("pages/about.py", title="About", icon=":material/info:")

page = st.navigation([home_page, live_page, profile_page, dashboard_page, insights_page,
                      about_page])

with st.sidebar:
    st.caption("An awareness tool, not a medical device.")

page.run()
