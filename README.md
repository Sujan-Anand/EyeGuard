# EyeGuard – Smart Eye Strain Monitor for Students
PySustain-2026 · Track 1: Code to Cure · SDG 3.4

A webcam + Python tool that tracks blink rate, screen distance, drowsiness, posture and lighting, enforces the 20-20-20 rule with a camera-verified break, and gives a live Eye Strain Score.

## Setup (do this tonight)
```
pip install -r requirements.txt
```
The first run downloads a small face model (~4 MB), so be online once. Keep `face_landmarker.task` in the folder after that.

## Run
```
python eyeguard.py          # normal: break every 20 min
python eyeguard.py --demo   # break every 60 s (use this in front of judges)
python eyeguard.py --camera 1   # if the wrong camera opens
```
Keys: `q` quit · `c` calibrate distance · `b` start a break now · `r` reset

**Calibrate once:** sit exactly 50 cm (about arm's length) from the webcam and press `c`. Distance readings are much more accurate after this.

## Report
```
python report.py                                  # latest session
python sample_data.py                             # create a 60-min demo session
python report.py logs/session_00000000_demo.csv   # report for the demo session
```

## How it works
| Feature | Method |
|---|---|
| Blink detection | Eye Aspect Ratio (EAR) from 6 Face Mesh points per eye; threshold auto-set to 75% of your open-eye EAR in the first 3 s |
| Distance | Iris is ~11.7 mm in all adults → distance = focal × 1.17 cm ÷ iris width in pixels |
| Verified break | Head turned away (nose offset from eye midpoint) or face out of frame for 20 s; looking back pauses the timer |
| Drowsiness | Eyes closed > 2 s |
| Posture | Head roll angle > 15° from the eye corners |
| Lighting | Mean frame brightness < 60 |
| Strain score | Low blinks (40) + too close (30) + time since break (20) + drowsy events (10) |

## Files
- `eyeguard.py` – live monitor, logs one row per second to `logs/`
- `report.py` – charts + summary + tips for a session
- `sample_data.py` – realistic 60-min demo session
