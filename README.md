# EyeGuard – Smart Eye Strain Monitor for Students

SDG 3.4 (primary), SDG 4 (secondary)

EyeGuard uses a webcam and Python to watch for eye strain while you work at a screen. It tracks blink rate, distance from the screen, drowsiness, head tilt and room lighting, enforces the 20-20-20 rule with a break that the camera verifies, and gives a live Eye Strain Score from 0 to 100.

Blink alerts have two levels: a warning below 7 blinks per minute and a strong alert below 5.

It has two parts:

- **Desktop app** (`eyeguard.py`): the live monitor. It saves one row per second to a CSV in `logs/`.
- **Website** (`app.py`, Streamlit): a live check in the browser, a dashboard for each session, and insights across sessions.

> EyeGuard is an awareness tool, not a medical device.

## Why

People blink about 15-20 times a minute normally, but only about 5-7 times a minute while looking at a screen. Students also lean in closer as they concentrate and skip breaks. The result is dry, tired eyes and headaches, and long hours of close-up work are a known risk factor for myopia. EyeGuard makes these habits visible and nudges you to fix them.

## Getting started in 30 seconds

1. Double-click **`EyeGuard.bat`** in the project folder.
2. In the small window that opens, click **+ New profile**.
3. Type a name, pick what you wear (Nothing, Glasses or Contact lenses), and click **Save & start**.
4. When the video appears, sit at arm's length (about 50 cm) and press C to calibrate.

That is all. Next time, your profile is already selected: just press **Start**. `EyeGuard Background.bat` does the same but runs with no video window (see Background mode below).

If the window says Python was not found, do the Setup below once.

## Setup

You need Python 3.10 or newer (built and tested on 3.14) and a webcam.

```
py -m pip install -r requirements-desktop.txt
py -m pip install streamlit streamlit-webrtc av plotly
```

The first line is enough for the desktop app. The second line adds what the website needs.

Do **not** install `requirements.txt` on your laptop. That file is for Streamlit Community Cloud and uses `opencv-python-headless`, which cannot open the desktop app's video window.

If `py -m streamlit run app.py` says `No module named streamlit`, the second line above has not been run for the Python that `py` starts.

The first run downloads a small face model (`face_landmarker.task`, about 4 MB), so be online once.

## Run the desktop app

```
py eyeguard.py              # opens the profile window, then the video
py eyeguard.py --no-profile # skip the profile window and start without a profile
py eyeguard.py --camera 1   # if the wrong camera opens
py eyeguard.py --mute       # start with the sound off
py eyeguard.py --test-sound # play each alert sound once and exit
py eyeguard.py --profile "Sujan - glasses"   # go straight to a saved profile
py eyeguard.py --background # no video window: notifications and a small box (see below)
```

Keys: `q` quit · `c` calibrate distance · `b` start a break now · `r` reset · `m` sound on/off · `p` switch profile

A break is due every 20 minutes. Double-clicking `EyeGuard.bat` is the same as `py eyeguard.py`.

Alerts and breaks play a sound, with at least 15 seconds between repeats of the same alert. Each sound is a tone followed by a Windows system sound, because some laptops do not play the plain tone. Sounds play in the background, so the video does not pause. If you hear nothing, run `py eyeguard.py --test-sound` and check the Windows volume and output device. On the website, Live Check has an optional **Sound alerts** switch that beeps in the browser. Press `m` to switch the sound off or on at any time. The bottom line of the panel shows `m sound ON` or `m sound OFF`. Muting only silences the beeps: alerts still appear on screen and in the log.

**Calibrate once:** sit exactly 50 cm (about arm's length) from the webcam and press `c`. Distance readings are much more accurate after this.

### Background mode

```
py eyeguard.py --background
py eyeguard.py --background --profile "Sujan - glasses" --mute
py eyeguard.py --background --no-mini
```

Background mode keeps watching through the webcam but shows no video window, so you can get on with your work. It works together with `--profile` and `--mute`.

- **Notifications.** Windows pop-up notifications replace the on-screen alerts: blink warning (below 7/min), strong blink alert (below 5/min), too close, drowsy, and the break. The same 15-second gap between repeats applies. The break still has to be a real one: `Break time: look away for 20 s`, then `Break paused at 12/20 s — look away to continue` if you look back, then `Break done ✓`.
- **Sound.** The notifications themselves are silent. EyeGuard plays its usual beeps with them, and `--mute` switches the beeps off.
- **Mini window.** A small box (about 220 × 120) stays on top of your other windows with blinks/min, distance, strain score, and the break progress or the time to the next break. Drag it anywhere. Press **Stop** to end the session. `--no-mini` hides the box.
- **Nobody there.** If no face is seen for 2 minutes you get one `EyeGuard paused` notification, then nothing more. It continues by itself when you come back.
- **Stopping.** Press Stop on the box, or Ctrl+C in the terminal. Either way the session CSV is saved, with the same columns as always.
- **Light on the laptop.** It reads the camera at most 15 times a second.

Calibrating needs the video window, so run once without `--background` and press `c` (with a profile, the calibration is saved for later). Notifications use the `winotify` package, which is Windows-only and is installed by `requirements-desktop.txt`. Without it, or if Windows notifications are switched off, the messages are printed in the terminal instead.

### Profiles

A profile records who is using EyeGuard and what they wear at the computer.

**The profile window.** When you start EyeGuard without `--profile`, a small window opens before the camera starts:

- It lists your saved profiles, with the one you used last time already selected. Click one and press **Start**.
- **+ New profile** opens a one-screen form: a name, three big buttons (Nothing / Glasses / Contact lenses), the lens power, and a safe-distance slider from 50 to 80 cm. The lens power only appears for glasses and contact lenses; change it with the − and + buttons in steps of 0.25 (it is the number on your prescription, minus for short sight). **Save & start** saves the profile and starts.
- If the name is empty you are told so; if a profile with that name already exists you are asked whether to use it.
- **Continue without profile** starts EyeGuard with the usual 50 cm and no lens correction. Closing the window does not start EyeGuard.

**Guided calibration.** A new profile is not calibrated yet, so the video shows `Sit at arm's length (about 50 cm), wearing what you entered, then press C to calibrate`. After you press C it confirms `Calibrated ✓ — saved to your profile` and does not ask again. In background mode there is no video, so run once normally to calibrate.

**Switching.** Press `p` in the video window to open the profile window again. The profile you pick applies straight away (distance correction, safe distance, saved calibration) without restarting. Closing the window keeps the current profile.

**From the command line.** This still works and skips the window:

```
py eyeguard.py --profile "Sujan - glasses"
```

If the name is new, EyeGuard asks three short questions in the terminal and saves the answers. The name and what you wear appear beside the EyeGuard title on the panel.

| Saved for each profile | Values |
|---|---|
| Name | Anything you like. Capitals, spaces and the kind of dash do not matter when you type it again. |
| Correction | `none`, `glasses` or `contacts` |
| Lens power | Spherical power in dioptres from your prescription, -20 to +20 in steps of 0.25. One value for both eyes. |
| Safe distance | 50 cm by default. You can raise it, up to 100 cm. |
| Calibration | The camera focal length and the date, once you have calibrated. Empty until then. |

One person can have more than one profile, for example `"Sujan - glasses"` and `"Sujan - contacts"`.

### Glasses and eye power

EyeGuard measures distance from how big your iris looks to the camera. Glasses change that: a minus lens (short sight) makes the eye look smaller, so EyeGuard would think you are further away than you are and miss "Too close". A plus lens does the opposite. Contact lenses sit on the eye and change almost nothing. Blink detection is a ratio of eye height to eye width, so it is not affected.

With a profile, EyeGuard corrects for this:

```
m = 1 / (1 - d x P)        P = lens power in dioptres, d = 0.015 m (lens to eye)
corrected distance = raw distance x m
```

At -7.00 D, m is about 0.905: the eye looks about 10% smaller, and a raw reading of 60 cm becomes 54 cm. For contact lenses and for no correction, m = 1.

- **Before you calibrate**, a glasses profile uses the formula and the screen says `Estimated for -7.00 D glasses - press c to calibrate for best accuracy`.
- **To calibrate**, wear the glasses or contacts you normally use at the computer, sit at arm's length (about 50 cm), then press `c`. The result is saved in the profile and used every time after that. A calibration made with your glasses on already includes the lens, so the formula is no longer applied. Calibrate again if you change camera.
- **Safe distance:** the "Too close" alert and the strain score use the profile's safe distance instead of 50 cm.
- **Glare:** with a glasses profile, if the eye readings jump about for about 2 seconds, EyeGuard asks `Glare on your glasses? Reduce light behind you or tilt the screen.`
- **Strong lenses:** at 6 D or more, EyeGuard shows one reminder per session to get a full eye check-up regularly.

On the website, the **My Profile** page has the same simple form: a name, three big buttons, the lens power only when it is needed, and the safe-distance slider, with **Save** and **Delete** (it asks first). A dropdown chooses the active profile, and the page shows `Calibrated on <date>` or `Not calibrated — run the desktop app and press C`. Live Check then corrects the distance, uses your safe distance, shows the glare warning, and its **Calibrate distance** button stores the calibration in the profile. On the public website your profiles stay in that browser tab. When you run the website on your own laptop, the page reads and writes the same `profiles.json` as the desktop app.

Limits: the formula uses the spherical power only and ignores astigmatism (cylinder). It assumes the lens sits 15 mm from the eye. EyeGuard cannot measure or diagnose eye power; it only uses the number you enter, and nothing here is medical advice.

Profiles are stored in `profiles.json` in the project folder, and the name of the one you used last in `last_profile.txt`. To change or delete a profile, use the My Profile page of the website on your laptop. EyeGuard cannot measure or diagnose eye power; it only stores the number you enter. With **Continue without profile** or `--no-profile`, EyeGuard works exactly as it does with no profile.

Each run saves `logs/session_<date>_<time>.csv`. To get a report from the command line:

```
py report.py                # charts, summary and tips for the latest session
py sample_data.py           # create a 60-minute sample session
```

## Run the website on your laptop

```
py -m streamlit run app.py
```

It opens at http://localhost:8501.

| Page | What it does |
|---|---|
| Home | "Blink more. Sit back. Look away." with buttons to start a live check or open a sample session, the problem, how EyeGuard works in three steps, and the SDGs it supports. |
| Live Check | Webcam check in the browser with the numbers, alerts and 20-20-20 break drawn on the video. Also has a single-photo mode. Uses your profile if you have set one. |
| My Profile | Make, edit, choose and delete profiles: what you wear (nothing, glasses or contacts), your lens power and your safe distance, with a plain explanation of what EyeGuard does with them and whether the profile is calibrated. |
| Session Dashboard | Number cards with units and a status in words (for example "Below normal", "One missed"), interactive charts with labelled limit lines, tips as cards with the most important first, and downloads for one session. Pick a CSV from `logs/`, upload one, or load a sample session. |
| Insights | All sessions together: blink rate by hour of the day, strain trend, best and worst session. |
| About | Formulas, future scope and the AI usage disclosure. |

## Deploy the website (Streamlit Community Cloud, free)

1. Push this repository to GitHub.
2. Go to https://share.streamlit.io and sign in with the same GitHub account.
3. Click **Create app**, then **Deploy a public app from GitHub**.
4. Fill in:
   - Repository: `<your-username>/EyeGuard`
   - Branch: `main`
   - Main file path: `app.py`
5. Open **Advanced settings** and set the Python version to **3.12**. This is required: `requirements.txt` pins exact versions, and the pinned numpy does not install on 3.11.
6. Click **Deploy**. The first build takes several minutes because MediaPipe and OpenCV are large.

Streamlit Cloud reads three files from the repository:

- `requirements.txt`: the Python packages, pinned to the exact versions the website was built and tested with.
- `packages.txt`: two system libraries that OpenCV needs on Linux.
- `.streamlit/config.toml`: the colour theme.

Things to know after deploying:

- If the repository is private, Streamlit asks for permission to read private repositories when you connect GitHub.
- The app sleeps after a period with no visitors. Open the link a few minutes before you present.
- `logs/` on the server starts empty. Use **Load sample session** and **Load sample week**, or upload CSVs recorded with the desktop app.
- The cloud server's clock is UTC, so sample sessions made there show UTC hours.

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
| Distance | The iris is about 11.7 mm wide in almost every adult, so distance = focal length × 1.17 cm ÷ iris width in pixels. With a glasses profile it is then multiplied by the lens factor m. |
| Blink alerts | Warning ("Blink more!") below 7 blinks per minute, strong alert ("Blink now!") below 5. Normal is about 15-20. |
| Verified break | Head turned away (nose offset from the midpoint between the eyes) or face out of the picture for a total of 20 s. Looking back at the screen pauses the timer (12 s stays 12 s) with one short beep, and looking away again continues from there. A glance back shorter than 0.5 s is ignored. |
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
| `sample_data.py` | Makes realistic sample sessions. |
| `app.py` | Website entry point and Home page. |
| `pages/` | Live Check, My Profile, Session Dashboard, Insights and About pages. |
| `profiles.py` | Profiles: what is saved, the lens formula, the checks behind the profile form, and the terminal questions. |
| `profile_window.py` | The small profile window of the desktop app: pick a profile, make a new one, or continue without. |
| `EyeGuard.bat`, `EyeGuard Background.bat` | Double-click launchers for Windows: the normal app and background mode. |
| `background.py` | Background mode for the desktop app: the Windows notifications and the small always-on-top box. |
| `live.py` | Keeps the live session between video frames for the Live Check page and draws the overlay. |
| `sessions.py` | Finds, loads and checks session CSVs; combines sessions for Insights. |
| `charts.py` | Plotly charts. |
| `ui.py` | The design system: colours, type and the shared page blocks (page header, hero banner, sidebar logo, KPI card, info cards, status pill, tip card, alert box, meter, footer). The theme for Streamlit's own widgets is in `.streamlit/config.toml`. |
| `requirements.txt`, `packages.txt` | For Streamlit Cloud. |
| `requirements-desktop.txt` | For your laptop. |

`logs/` (your recorded sessions), `profiles.json` (your saved profiles) and `last_profile.txt` (the profile you used last) stay on your laptop. Git ignores them, so they are never uploaded to GitHub.

## Tests

```
py -m unittest discover -s tests -v
```

The tests run the real desktop loop with a simulated camera, clock and keyboard, so they need no webcam. They cover the break timer (pause and continue, glances, one beep per pause, mute), the two blink alert levels, profiles, the glasses correction (lens formula, saved calibration, safe distance, glare warning), background mode (notifications, the break with a pause, the pause when nobody is there, the Stop button and Ctrl+C), and profile setup (the start window's choices, the new-profile form, duplicate names, the last-used profile, switching with `p`, and the launchers). No test opens a real profile window.

## Future scope

- **Mobile app:** the same checks with a phone's front camera.
- **Browser extension:** reminders inside the pages students already use.
- **Campus analytics:** anonymous, opt-in totals for a class or hostel, to show when screen strain peaks.

## AI usage disclosure

EyeGuard was built by Sujan Anand, Dhayanithi S V, Padhmesh N and Akshaith P. We used AI assistants (Claude) to help write and debug parts of the code and documentation. The project idea, feature design, testing, calibration and presentation were done by our team, and every member can explain how the code works.

| AI-assisted | Done by the team |
|---|---|
| Code scaffolding | The idea |
| Website pages | SDG mapping |
| Documentation | Feature choices |
| | Real-webcam testing |
| | The demo |

## Disclaimer

EyeGuard is an awareness tool, not a medical device. It does not diagnose or treat any condition. See an eye doctor if you have ongoing eye discomfort, headaches or blurred vision.
