"""Live Check - webcam eye-strain check in the browser (streamlit-webrtc + MediaPipe)."""

import os
import time

import av
import cv2
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

import eyeguard as eg
import live
import sessions

# Public STUN servers let the browser and the server find a route to each other.
STUN_SERVERS = [{"urls": ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]}]
# Optional: on networks that block direct video (some campus Wi-Fi) a TURN relay
# is needed. If one of these keys is set in the app's secrets, streamlit-webrtc
# fetches STUN + TURN servers from that provider by itself (see README.md).
TURN_SECRET_KEYS = ("HF_TOKEN", "CLOUDFLARE_TURN_KEY_ID")
SLOW_CONNECT_SECONDS = 15
MIN_ROWS_TO_SAVE = 5

st.title("Live Check")
st.caption("Check your blink rate, screen distance and eye strain live, in the browser. "
           "Video is analysed frame by frame and never saved.")


def rtc_configuration():
    if any(os.getenv(key) for key in TURN_SECRET_KEYS):
        return None                      # let streamlit-webrtc set up STUN + TURN
    return {"iceServers": STUN_SERVERS}


@st.cache_resource(show_spinner="Downloading the face model (one time, about 4 MB)...")
def model_path():
    return live.ensure_model()


def visitor_clock_shift():
    """Difference between the visitor's clock and the server's clock (a cloud
    server runs in UTC), so saved sessions show the visitor's time of day."""
    try:
        there = pd.Timestamp.now(tz=st.context.timezone).tz_localize(None)
        return (there - pd.Timestamp.now()).round("15min")
    except Exception:
        return pd.Timedelta(0)


def show_alerts(alerts, all_clear):
    for text in alerts:
        st.warning(text, icon=":material/warning:")
    if not alerts:
        st.success(all_clear, icon=":material/check_circle:")


try:
    model_path()
except Exception as err:
    st.error(f"The face model could not be downloaded ({err}). Check the internet "
             "connection and reload this page.", icon=":material/cloud_off:")
    st.stop()

if "tracker" not in st.session_state:
    st.session_state["tracker"] = live.EyeTracker()
tracker = st.session_state["tracker"]

# ------------------------------------------------------------------- settings
with st.container(border=True):
    mode = st.segmented_control(
        "How do you want to check?", ["Live video", "Single photo"], default="Live video",
        help="Live video measures everything. Single photo is a backup for networks "
             "that block live video: it checks distance, head tilt and lighting.")
    if mode != "Single photo":
        pace = st.segmented_control(
            "20-20-20 break", ["Demo: every 60 seconds", "Normal: every 20 minutes"],
            default="Demo: every 60 seconds",
            help="Every 20 minutes, look at something 20 feet away for 20 seconds. "
                 "Demo mode asks for the break after one minute so you can try it.")
        tracker.break_every_s = (live.NORMAL_BREAK_SECONDS if pace and pace.startswith("Normal")
                                 else live.DEMO_BREAK_SECONDS)

# --------------------------------------------------------------- single photo
if mode == "Single photo":
    st.subheader("Single photo check")
    st.write("Sit the way you normally sit at your screen, then take a photo.")
    photo = st.camera_input("Take a photo of yourself at your screen")
    if photo is None:
        st.info("If no camera box appears, allow camera access for this site: click "
                "the lock or camera icon in the address bar, choose **Allow**, and "
                "reload the page.", icon=":material/photo_camera:")
        st.stop()
    image = cv2.imdecode(np.frombuffer(photo.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        st.error("That photo could not be read. Please take it again.")
        st.stop()
    numbers, alerts, marked = live.check_photo(image)
    if not numbers["face"]:
        show_alerts(alerts, "Lighting looks fine.")
        st.warning("No face found in the photo. Face the camera, make sure your "
                   "face is well lit, and try again.", icon=":material/face:")
        st.stop()
    with st.container(horizontal=True):
        st.metric("Distance from screen", f"{numbers['distance_cm']:.0f} cm", border=True,
                  help=f"Keep at least {eg.MIN_SAFE_DISTANCE_CM} cm from the screen. "
                       "This is an estimate from the size of your iris.")
        st.metric("Head tilt", f"{abs(numbers['roll']):.0f}°", border=True,
                  help=f"More than {eg.HEAD_TILT_DEG}° suggests a slumped posture.")
        st.metric("Room brightness", f"{numbers['brightness']:.0f} / 255", border=True,
                  help=f"Below {eg.DARK_BRIGHTNESS} is too dark for screen work.")
    show_alerts(alerts, "Distance, posture and lighting all look good.")
    st.image(cv2.cvtColor(marked, cv2.COLOR_BGR2RGB), width=480,
             caption="Yellow dots: the eye points EyeGuard measures.")
    st.caption("Blink rate and the 20-20-20 break need live video or the desktop app.")
    st.stop()

# ----------------------------------------------------------------- live video
st.subheader("How to start")
st.markdown(
    "1. Click **START** below and choose **Allow** when the browser asks for the camera.\n"
    f"2. Sit at arm's length (about {eg.MIN_SAFE_DISTANCE_CM} cm) with light on your face.\n"
    "3. Work normally for a minute. Numbers and alerts appear on the video.\n"
    "4. When the blue break screen appears, look away from the screen for "
    f"{eg.BREAK_LOOK_AWAY_SECONDS} seconds. Looking back pauses the timer; "
    "looking away again continues from where it stopped.")


def on_frame(frame):
    image = tracker.process(frame.to_ndarray(format="bgr24"))
    return av.VideoFrame.from_ndarray(image, format="bgr24")


ctx = webrtc_streamer(
    key="live-check",
    mode=WebRtcMode.SENDRECV,
    rtc_configuration=rtc_configuration(),
    media_stream_constraints={
        "video": {"width": {"ideal": 640}, "height": {"ideal": 480},
                  "frameRate": {"ideal": 20}},
        "audio": False},
    video_frame_callback=on_frame,
    async_processing=True,
    translations={
        "device_ask_permission": "Please allow camera access for this site.",
        "device_access_denied": "Camera access is blocked. Click the lock or camera "
                                "icon in the address bar, choose Allow, then reload.",
        "device_not_available": "No camera was found on this device.",
        "media_api_not_available": "This browser cannot use the camera here. Open "
                                   "the site with https:// in Chrome, Edge or Firefox.",
    },
)
playing, connecting = ctx.state.playing, ctx.state.signalling and not ctx.state.playing
if not playing:
    st.caption("Seeing **NotAllowedError** or **Permission denied** in the box above? "
               "The browser has blocked the camera. Click the lock or camera icon in "
               "the address bar, set Camera to **Allow**, and reload the page. More "
               "help is under **Camera not working?** below.")

if connecting:
    st.session_state.setdefault("connect_started", time.time())
else:
    st.session_state.pop("connect_started", None)


@st.fragment(run_every=1.0 if (playing or connecting) else None)
def live_numbers():
    """Refreshes once a second while the video is running."""
    started = st.session_state.get("connect_started")
    if started and time.time() - started > SLOW_CONNECT_SECONDS:
        st.warning("Still connecting. This network may be blocking live video "
                   "(common on campus Wi-Fi). Try a phone hotspot, or switch to "
                   "**Single photo** above.", icon=":material/wifi_off:")
    if tracker.error:
        st.error(f"A video frame could not be analysed ({tracker.error}).")
    s = tracker.snapshot()
    if s is None:
        st.caption("Your numbers appear here once the video starts.")
        return
    with st.container(horizontal=True):
        st.metric("Blinks per minute",
                  "measuring…" if s["measuring"] else f"{s['blink_rate']:.1f}", border=True,
                  help="Healthy is about 15-20 blinks per minute.")
        st.metric("Total blinks", s["blinks_total"], border=True)
        st.metric("Distance", f"{s['distance_cm']:.0f} cm" if s["face"] else "–", border=True,
                  help=f"Keep at least {eg.MIN_SAFE_DISTANCE_CM} cm from the screen.")
        st.metric("Strain score", f"{s['strain_score']} / 100", border=True,
                  help="0 = relaxed eyes, 100 = heavy strain.")
        st.metric("Next break", "now" if s["on_break"] else f"{s['next_break_s'] / 60:.1f} min",
                  border=True)
    if not tracker.is_running():
        st.caption("Video stopped. These are the last numbers.")
    elif s["on_break"]:
        total = eg.BREAK_LOOK_AWAY_SECONDS
        done = min(int(s["break_done_s"] + 1e-6), total)      # whole seconds done
        if s["break_state"] == "paused":
            st.warning(f"**Paused — look away to continue ({done}/{total} s)**",
                       icon=":material/pause_circle:")
        elif s["break_state"] == "counting":
            st.success(f"**Good, keep looking away ({done}/{total} s)**",
                       icon=":material/timer:")
        else:
            st.warning(f"**20-20-20 break — look away to start the timer ({done}/{total} s)**",
                       icon=":material/visibility_off:")
        st.progress(done / total, text=f"{done} of {total} seconds looking away")
    elif s["alert"] and s["alert_level"] == "warn":
        st.warning(s["alert"], icon=":material/warning:")
    elif s["alert"]:
        st.error(s["alert"], icon=":material/error:")
    elif not s["face"]:
        st.caption("No face in view.")


live_numbers()

with st.container(horizontal=True):
    if st.button("Start a break now", icon=":material/self_improvement:", disabled=not playing):
        tracker.request("break")
    if st.button("Calibrate distance", icon=":material/straighten:", disabled=not playing,
                 help=f"Sit exactly {eg.MIN_SAFE_DISTANCE_CM} cm from the camera, then "
                      "click. Distance readings are more accurate afterwards."):
        tracker.request("calibrate")
        st.toast(f"Calibrated at {eg.MIN_SAFE_DISTANCE_CM} cm", icon=":material/check_circle:")
    if st.button("Reset counters", icon=":material/restart_alt:", disabled=not playing):
        tracker.request("reset")

# ------------------------------------------------------------ keep the session
recorded = tracker.dataframe()
if not playing and len(recorded) >= MIN_ROWS_TO_SAVE:
    st.subheader("Keep this check")
    st.write(f"You recorded {len(recorded) / 60:.1f} minutes. Open it in the Session "
             "Dashboard to see the charts and tips. It stays in this browser tab only.")
    with st.container(horizontal=True):
        if st.button("Open in Session Dashboard", type="primary",
                     icon=":material/monitoring:"):
            df = sessions.clean(recorded)
            df["timestamp"] = df["timestamp"] + visitor_clock_shift()
            name = f"live_{df['timestamp'].iloc[0]:%Y%m%d_%H%M%S}.csv"
            sessions.uploads()[name] = df
            st.session_state["selected_session"] = name
            st.switch_page("pages/session_dashboard.py")
        if st.button("Discard and start again", icon=":material/delete:"):
            del st.session_state["tracker"]
            st.rerun()

# ------------------------------------------------------------ troubleshooting
with st.expander("Camera not working?", icon=":material/help:"):
    st.markdown(
        "**No camera prompt, or you clicked Block**\n"
        "- Click the lock or camera icon in the address bar, set Camera to "
        "**Allow**, then reload the page.\n"
        "- The page must be opened with `https://` (or `localhost`). Browsers "
        "refuse the camera on plain `http://` sites.\n"
        "- Close other apps that are using the camera (Zoom, Teams, the EyeGuard "
        "desktop app).\n\n"
        "**START keeps spinning and no video appears**\n"
        "- Some networks block live video. Try a phone hotspot or another Wi-Fi.\n"
        "- Switch to **Single photo** at the top of this page. It works on any network.\n\n"
        "**Still stuck?** Run the desktop app instead: `py eyeguard.py --demo`")
