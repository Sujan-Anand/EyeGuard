# EyeGuard – Smart Eye Strain Monitor for Students

PySustain-2026 · Track 1: Code to Cure · SDG 3.4 (primary), SDG 4 (secondary)

EyeGuard uses a webcam and Python to watch for eye strain while you work at a screen. It tracks blink rate, distance from the screen, drowsiness, head tilt and room lighting, enforces the 20-20-20 rule with a break that the camera verifies, and gives a live Eye Strain Score from 0 to 100.

It has two parts:

- **Desktop app** (`eyeguard.py`): the live monitor. It saves one row per second to a CSV in `logs/`.
- **Website** (`app.py`, Streamlit): a live check in the browser, a dashboard for each session, and insights across sessions.

> EyeGuard is an awareness tool, not a medical device.

## Why

People blink about 15-20 times a minute normally, but only about 5-7 times a minute while looking at a screen. Students also lean in closer as they concentrate and skip breaks. The result is dry, tired eyes and headaches, and long hours of close-up work are a known risk factor for myopia. EyeGuard makes these habits visible and nudges you to fix them.

## Setup

You need Python 3.10 or newer (built and tested on 3.14) and a webcam.

```
py -m pip install -r requirements-desktop.txt
py -m pip install streamlit streamlit-webrtc av plotly
```

The first line is enough for the desktop app. The second line adds what the website needs.

Do **not** install `requirements.txt` on your laptop. That file is for Streamlit Community Cloud and uses `opencv-python-headless`, which cannot open the desktop app's video window.

The first run downloads a small face model (`face_landmarker.task`, about 4 MB), so be online once.

## Run the desktop app

```
py eyeguard.py --demo       # break every 60 s (use this in front of judges)
py eyeguard.py              # normal: break every 20 min
py eyeguard.py --camera 1   # if the wrong camera opens
```

Keys: `q` quit · `c` calibrate distance · `b` start a break now · `r` reset

**Calibrate once:** sit exactly 50 cm (about arm's length) from the webcam and press `c`. Distance readings are much more accurate after this.

Each run saves `logs/session_<date>_<time>.csv`. To get a report from the command line:

```
py report.py                # charts, summary and tips for the latest session
py sample_data.py           # create a 60-minute demo session
```

## Run the website on your laptop

```
py -m streamlit run app.py
```

It opens at http://localhost:8501.

| Page | What it does |
|---|---|
| Home | The problem, how EyeGuard works, and the SDGs it supports. |
| Live Check | Webcam check in the browser with the numbers, alerts and 20-20-20 break drawn on the video. Also has a single-photo mode. |
| Session Dashboard | KPI cards, interactive charts, tips and downloads for one session. Pick a CSV from `logs/`, upload one, or generate a demo session. |
| Insights | All sessions together: blink rate by hour of the day, strain trend, best and worst session. |
| About | Tech stack, formulas, future scope and the AI usage disclosure. |

## Deploy the website (Streamlit Community Cloud, free)

1. Push this repository to GitHub.
2. Go to https://share.streamlit.io and sign in with the same GitHub account.
3. Click **Create app**, then **Deploy a public app from GitHub**.
4. Fill in:
   - Repository: `<your-username>/EyeGuard`
   - Branch: `main`
   - Main file path: `app.py`
5. Open **Advanced settings** and set the Python version to **3.12**. (3.11 also works, but pip then installs older versions of numpy and av, because their newest releases need 3.12.)
6. Click **Deploy**. The first build takes several minutes because MediaPipe and OpenCV are large.

Streamlit Cloud reads three files from the repository:

- `requirements.txt`: the Python packages.
- `packages.txt`: two system libraries that OpenCV needs on Linux.
- `.streamlit/config.toml`: the colour theme.

Things to know after deploying:

- If the repository is private, Streamlit asks for permission to read private repositories when you connect GitHub.
- The app sleeps after a period with no visitors. Open the link a few minutes before you present.
- `logs/` on the server starts empty. Use **Generate demo session** and **Generate demo week**, or upload CSVs recorded with the desktop app.
- The cloud server's clock is UTC, so demo sessions made there show UTC hours.

### If Live Check will not connect

Live video uses WebRTC. The app is set up with public STUN servers, which is enough on most home and mobile networks. Some campus and office networks block direct video. Then START keeps spinning and no video appears.

- Quick fix: use a phone hotspot, or switch Live Check to **Single photo**.
- Proper fix: give the app a TURN relay. In the app's **Settings → Secrets** on Streamlit Cloud, add a free Hugging Face access token:

  ```
  HF_TOKEN = "hf_your_token_here"
  ```

  streamlit-webrtc then fetches TURN servers by itself. Cloudflare Realtime TURN also works, with `CLOUDFLARE_TURN_KEY_ID` and `CLOUDFLARE_TURN_KEY_API_TOKEN`.

## How it works

| Feature | Method |
|---|---|
| Blink detection | Eye Aspect Ratio (EAR) from 6 landmark points per eye. The threshold is set to 75% of your own open-eye EAR in the first few seconds. |
| Distance | The iris is about 11.7 mm wide in almost every adult, so distance = focal length × 1.17 cm ÷ iris width in pixels. |
| Verified break | Head turned away (nose offset from the midpoint between the eyes) or face out of the picture for 20 s. Looking back resets the timer. |
| Drowsiness | Eyes closed for more than 2 s. |
| Posture | Head tilted more than 15°, measured between the outer eye corners. |
| Lighting | Average frame brightness below 60 out of 255. |
| Strain score | Low blink rate (up to 40) + too close (up to 30) + time since the last break (up to 20) + drowsy moments (up to 10). |

EAR = (|p2 − p6| + |p3 − p5|) ÷ (2 × |p1 − p4|), where p1 and p4 are the eye corners, p2 and p3 are on the upper lid, and p6 and p5 are on the lower lid.

Video is analysed frame by frame in memory and is never saved. Only the numbers are logged.

## Files

| File | Purpose |
|---|---|
| `eyeguard.py` | Desktop monitor. Also holds the measurement functions (EAR, iris distance, head pose, strain score) that the website imports. |
| `report.py` | Loads a session CSV, works out the summary and tips, draws the matplotlib report. |
| `sample_data.py` | Makes realistic demo sessions. |
| `app.py` | Website entry point and Home page. |
| `pages/` | Live Check, Session Dashboard, Insights and About pages. |
| `live.py` | Keeps the live session between video frames for the Live Check page and draws the overlay. |
| `sessions.py` | Finds, loads and checks session CSVs; combines sessions for Insights. |
| `charts.py` | Plotly charts. |
| `requirements.txt`, `packages.txt` | For Streamlit Cloud. |
| `requirements-desktop.txt` | For your laptop. |

## Future scope

- **Mobile app:** the same checks with a phone's front camera.
- **Browser extension:** reminders inside the pages students already use.
- **Campus analytics:** anonymous, opt-in totals for a class or hostel, to show when screen strain peaks.

## AI usage disclosure

This project was built by our team for PySustain-2026. We used AI assistants (Claude) to help write and debug parts of the code and documentation. The project idea, feature design, testing, calibration and presentation were done by our team, and every member can explain how the code works.

| AI-assisted | Done by the team |
|---|---|
| Code scaffolding | The idea |
| Website pages | SDG mapping |
| Documentation | Feature choices |
| | Real-webcam testing |
| | The demo |

## Disclaimer

EyeGuard is an awareness tool, not a medical device. It does not diagnose or treat any condition. See an eye doctor if you have ongoing eye discomfort, headaches or blurred vision.
