"""
EyeGuard website - entry point and Home page.
PySustain-2026 | Track 1: Code to Cure | SDG 3.4

Run locally:   py -m streamlit run app.py
"""

import streamlit as st

import ui

st.set_page_config(page_title="EyeGuard", page_icon="👁️", layout="wide")
ui.apply_theme()                     # shared colours, type and card styles (ui.py)

# A little CSS on top of .streamlit/config.toml: the hero banner and the
# numbered step badges. clamp() keeps text readable on a phone and a projector.
st.markdown("""
<style>
.hero {
    background: linear-gradient(135deg, #0F3B3E 0%, #2C6E6A 100%);
    color: white; border-radius: 18px;
    padding: clamp(1.2rem, 4vw, 2.8rem); margin-bottom: 1.2rem;
}
.hero-name  { font-size: clamp(2.2rem, 6vw, 3.8rem); font-weight: 800; line-height: 1.1; }
.hero-pitch { font-size: clamp(1.05rem, 2.2vw, 1.45rem); margin-top: 0.6rem; }
.hero-tag   { font-size: 0.9rem; opacity: 0.9; margin-top: 0.9rem; }
.step-num {
    width: 2.4rem; height: 2.4rem; border-radius: 50%;
    background: #2C6E6A; color: white; font-weight: 700; font-size: 1.2rem;
    display: flex; align-items: center; justify-content: center;
}
</style>
""", unsafe_allow_html=True)


def home():
    st.markdown("""
    <div class="hero">
      <div class="hero-name">👁️ EyeGuard</div>
      <div class="hero-pitch">A smart eye-strain monitor that uses your webcam to
      remind you to blink, sit back and take real breaks.</div>
      <div class="hero-tag">PySustain-2026 · Track 1: Code to Cure · SDG 3.4</div>
    </div>
    """, unsafe_allow_html=True)

    # ------------------------------------------------------------ the problem
    st.header("The problem")
    st.write(
        "Students spend most of the day on screens: classes, assignments, coding "
        "and then entertainment. While we stare at a screen we blink far less, "
        "lean in closer and skip breaks, and our eyes pay for it."
    )
    # A horizontal container (not st.columns) so the cards wrap onto a new row
    # on a narrow screen instead of cutting the numbers off with "...".
    with st.container(horizontal=True):
        st.metric("Normal blink rate", "15-20 / min", "keeps eyes moist",
                  delta_arrow="off", border=True)
        st.metric("Blink rate on a screen", "5-7 / min", "about 60% fewer blinks",
                  delta_color="inverse", delta_arrow="down", border=True)
        st.metric("People with myopia by 2050", "about 1 in 2", "projected",
                  delta_color="off", delta_arrow="off", border=True)
    st.caption("Fewer blinks mean dry, tired, burning eyes and headaches. "
               "Myopia projection: Holden et al., Ophthalmology (2016); long "
               "hours of close-up work are a known risk factor.")

    # ----------------------------------------------------------- how it works
    st.header("How EyeGuard works")
    steps = [
        ("It watches",
         "Your webcam and MediaPipe find 478 landmarks on your face in every "
         "frame. Video is analysed live and never saved."),
        ("It measures",
         "Blink rate from the Eye Aspect Ratio, distance from the size of your "
         "iris, plus drowsiness, head tilt and room lighting. Together these "
         "give an Eye Strain Score from 0 to 100."),
        ("It nudges",
         "Gentle alerts when you blink too little or sit too close, and a "
         "20-20-20 break that only counts when the camera sees you look away."),
    ]
    for col, (num, (title, text)) in zip(st.columns(3), enumerate(steps, start=1)):
        with col, st.container(border=True):
            st.markdown(f'<div class="step-num">{num}</div>', unsafe_allow_html=True)
            st.subheader(title)
            st.write(text)

    st.write("")
    b1, b2, b3 = st.columns(3)
    b1.page_link(live_page, label="Try the Live Check", icon=":material/videocam:")
    b2.page_link(dashboard_page, label="Open a Session Dashboard", icon=":material/monitoring:")
    b3.page_link(insights_page, label="See your Insights", icon=":material/insights:")

    # -------------------------------------------------------------------- SDGs
    st.header("Sustainable Development Goals")
    s1, s2 = st.columns(2)
    with s1, st.container(border=True):
        st.subheader("SDG 3.4 · Good Health and Well-being")
        st.caption("Primary goal")
        st.write(
            "Target 3.4 is about preventing non-communicable disease and "
            "promoting well-being. Digital eye strain and myopia are "
            "non-communicable and largely preventable. EyeGuard works on "
            "prevention: it builds healthy screen habits before damage is done."
        )
    with s2, st.container(border=True):
        st.subheader("SDG 4 · Quality Education")
        st.caption("Secondary goal")
        st.write(
            "Learning now happens on screens. Tired eyes and headaches cut "
            "concentration and study time. Students who look after their eyes "
            "can learn comfortably for longer."
        )

    st.divider()
    st.caption("EyeGuard is an awareness tool, not a medical device. "
               "See an eye doctor if you have ongoing eye discomfort.")


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
    st.caption("EyeGuard · PySustain-2026\n\nAwareness tool, not a medical device.")

page.run()
