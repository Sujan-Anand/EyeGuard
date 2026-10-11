"""About - tech stack, formulas, future scope, AI usage disclosure and disclaimer."""

import streamlit as st

import eyeguard as eg
import profiles
import ui

ui.page_header("About EyeGuard", "How it is built, the formulas behind it, and where it goes next.")

st.warning("**EyeGuard is an awareness tool, not a medical device.** It does not "
           "diagnose or treat any condition. See an eye doctor if you have ongoing "
           "eye discomfort, headaches or blurred vision.", icon=":material/health_and_safety:")

# ------------------------------------------------------------------ tech stack
st.header("Tech stack")
st.write("Everything is written in Python.")
st.table({
    "Part": ["Camera and drawing", "Face landmarks", "Maths", "Session logs and reports",
             "Website", "Live video in the browser", "Interactive charts"],
    "Library": ["OpenCV", "MediaPipe Face Landmarker", "NumPy", "pandas, matplotlib",
                "Streamlit", "streamlit-webrtc (WebRTC)", "Plotly"],
    "What it does here": [
        "Reads webcam frames, measures brightness, draws the numbers on the video.",
        "Finds 478 points on the face in every frame, including each eyelid and iris.",
        "Distances and angles between those points.",
        "One row per second is saved to a CSV; reports and tips are built from it.",
        "These pages: Home, Live Check, My Profile, Session Dashboard, Insights, About.",
        "Sends webcam video from the browser to Python and back with the overlay.",
        "The dashboard and insights charts.",
    ],
})
st.caption("Privacy: video is analysed frame by frame in memory and is never saved "
           "or uploaded anywhere else. Only the numbers are kept.")

# -------------------------------------------------------------------- formulas
st.header("The formulas")

st.subheader("1. Blinks: Eye Aspect Ratio (EAR)")
st.write("Six points are taken around each eye: the two corners (p1, p4), two on "
         "the upper lid (p2, p3) and two on the lower lid (p6, p5).")
st.latex(r"EAR = \frac{|p_2 - p_6| + |p_3 - p_5|}{2 \times |p_1 - p_4|}")
st.write(
    "EAR is the eye's height divided by its width. It stays steady while the eye "
    "is open and drops sharply when it closes. EyeGuard learns your normal "
    "open-eye EAR in the first few seconds and sets your personal threshold at "
    "75% of it. A blink is the EAR going below the threshold for at least 2 "
    f"frames and less than {eg.DROWSY_SECONDS:.0f} seconds. Closed for longer "
    "than that counts as drowsiness, not a blink.")

st.subheader("2. Distance from the screen: iris size")
st.write(f"The human iris is about {eg.IRIS_DIAMETER_CM * 10:.1f} mm wide in almost "
         "every adult, so it works as a ruler that is always in the picture. "
         "The closer you sit, the more pixels it covers.")
st.latex(r"distance = \frac{focal \times " + f"{eg.IRIS_DIAMETER_CM}" + r"\ cm}{iris\ px}")
st.write(
    "Here *focal* is the camera's focal length in pixels and *iris px* is the "
    "width of your iris in the picture, in pixels. "
    "The focal length starts as 0.9 × the frame width, which suits a typical "
    f"laptop webcam. Pressing calibrate while sitting {eg.MIN_SAFE_DISTANCE_CM} cm "
    "away measures it for your own camera. Anything closer than "
    f"{eg.MIN_SAFE_DISTANCE_CM} cm counts as too close.")

st.subheader("Glasses and eye power")
st.write(
    "Glasses change how big the iris looks to the camera. A minus lens (short "
    "sight) makes the eye look smaller, so the plain formula would think you are "
    "further away than you are and miss \"Too close\". A plus lens does the "
    "opposite. Contact lenses sit on the eye and change almost nothing. Blink "
    "detection is a ratio, so it is not affected.")
st.latex(r"m = \frac{1}{1 - d \times P}")
st.write(
    "The raw distance is multiplied by *m* to get the corrected distance. "
    f"*P* is the lens power in dioptres and *d* is the lens-to-eye distance, about "
    f"{profiles.LENS_DISTANCE_M * 1000:.0f} mm. At -7.00 D, m is about "
    f"{profiles.lens_magnification('glasses', -7):.3f}: the eye looks about 10% smaller. "
    "You enter your power on the My Profile page.")
st.markdown(
    "- **Calibrating is more accurate than the formula.** Wear the glasses or "
    f"contacts you normally use at the computer, sit {profiles.CALIBRATION_DISTANCE_CM} cm "
    "away and calibrate. That measurement already includes your lenses, so the "
    "formula is no longer needed.\n"
    "- **Astigmatism is ignored.** Only the spherical power is used.\n"
    "- **Glare:** with a glasses profile, EyeGuard warns when reflections make the "
    "eye readings jump about.\n"
    "- **EyeGuard cannot measure or diagnose eye power.** It only uses the number "
    "from your prescription that you type in.")

st.subheader("3. Eye Strain Score (0-100)")
st.write("Four parts are added together. 0 means relaxed eyes, 100 means heavy strain.")
st.table({
    "Part": ["Low blink rate", "Sitting too close", "Time since the last break",
             "Drowsiness"],
    "Points": ["up to 40", "up to 30", "up to 20", "up to 10"],
    "How it is worked out": [
        "4 points for every blink per minute below 15.",
        f"1.5 points for every cm closer than {eg.MIN_SAFE_DISTANCE_CM} cm.",
        "Grows steadily and reaches 20 when the next break is due.",
        "5 points for each time the eyes stayed closed for over "
        f"{eg.DROWSY_SECONDS:.0f} seconds.",
    ],
})

with st.container(border=True):
    st.markdown("**Try the formula**")
    left, right = st.columns(2)
    blink_rate = left.slider("Blinks per minute", 0, 25, 8)
    distance = left.slider("Distance from screen (cm)", 25, 90, 40)
    minutes = right.slider("Minutes since the last break", 0, 20, 15)
    drowsy = right.slider("Drowsy moments so far", 0, 3, 0)
    score = eg.strain_score(blink_rate, distance, minutes, drowsy, break_every_min=20)
    st.metric("Eye Strain Score", f"{score} / 100",
              "high strain" if score >= 50 else "fine",
              delta_color="inverse" if score >= 50 else "normal", delta_arrow="off")
    st.caption("This calls the same `strain_score()` function as the desktop app "
               "and the Live Check page.")

st.subheader("4. The other checks")
st.table({
    "Check": ["20-20-20 verified break", "Head tilt (posture)", "Room lighting",
              "Too few blinks"],
    "Rule": [
        f"Every 20 minutes, look away for {eg.BREAK_LOOK_AWAY_SECONDS} seconds. "
        "Looking away means the nose is well off the midpoint between the eyes, or "
        "the face has left the picture. Looking back pauses the timer where it "
        "is, and looking away again continues it. A glance back shorter than "
        f"{eg.BREAK_GLANCE_SECONDS} seconds is ignored.",
        f"The line between the outer eye corners is tilted more than {eg.HEAD_TILT_DEG}°.",
        f"The average brightness of the frame is below {eg.DARK_BRIGHTNESS} out of 255.",
        f"Warning below {eg.BLINK_WARN_RATE} blinks per minute, strong alert below "
        f"{eg.BLINK_ALERT_RATE}. Normal is about 15-20.",
    ],
})

st.subheader("5. Background mode (desktop app)")
st.write(
    "`py eyeguard.py --background` runs the same checks with no video window, so "
    "EyeGuard can stay on while you study. Alerts arrive as Windows notifications "
    f"(blink warning below {eg.BLINK_WARN_RATE}/min, strong alert below "
    f"{eg.BLINK_ALERT_RATE}/min, too close, drowsy, break time) with the same "
    f"{eg.ALERT_COOLDOWN}-second gap between repeats. The break is still verified: "
    "looking back pauses it and you are told how far you got. A small box that "
    "stays on top shows blinks per minute, distance, strain score and the break "
    "timer, and has a Stop button.")
st.caption("If nobody is in view for 2 minutes it sends one \"EyeGuard paused\" "
           "notification and continues by itself when you return. It reads the camera "
           "at most 15 times a second, and the session CSV is the same as in the "
           "normal mode. It works with `--profile`, `--demo` and `--mute`.")

st.subheader("Known limits")
st.markdown(
    "- Distance is an estimate. It is most accurate after calibrating and when you "
    "face the camera.\n"
    "- Glasses with strong reflections, very dim rooms and low video frame rates "
    "make blink counting less reliable.\n"
    "- The thresholds are sensible starting values for awareness, not clinical limits.")

# ---------------------------------------------------------------- future scope
st.header("Future scope")
f1, f2, f3 = st.columns(3)
with f1, st.container(border=True):
    st.markdown("**:material/smartphone: Mobile app**")
    st.write("Phones are held closer than laptops and used for longer. The same "
             "checks could run with the front camera.")
with f2, st.container(border=True):
    st.markdown("**:material/extension: Browser extension**")
    st.write("Gentle reminders inside the pages students already use, without "
             "keeping a separate window open.")
with f3, st.container(border=True):
    st.markdown("**:material/school: Campus analytics**")
    st.write("Anonymous, opt-in totals for a class or hostel, so a college can see "
             "when screen strain peaks and plan timetables or awareness drives.")

# ---------------------------------------------------------- AI usage disclosure
st.header("AI usage disclosure")
st.info(
    "This project was built by our team for PySustain-2026. We used AI assistants "
    "(Claude) to help write and debug parts of the code and documentation. The "
    "project idea, feature design, testing, calibration and presentation were done "
    "by our team, and every member can explain how the code works.",
    icon=":material/smart_toy:")
a1, a2 = st.columns(2)
with a1, st.container(border=True):
    st.markdown("**AI-assisted**")
    st.markdown("- Code scaffolding\n- Website pages\n- Documentation")
with a2, st.container(border=True):
    st.markdown("**Done by the team**")
    st.markdown("- The idea\n- SDG mapping\n- Feature choices\n"
                "- Real-webcam testing\n- The demo")

st.divider()
st.caption("EyeGuard · PySustain-2026 · Track 1: Code to Cure · SDG 3.4 · "
           "Awareness tool, not a medical device.")
