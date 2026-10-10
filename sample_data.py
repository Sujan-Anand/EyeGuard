"""
Creates a realistic 60-minute demo session in logs/ so the report
can be shown even before (or without) a long live run.
  python sample_data.py && python report.py
"""

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
N = 60 * 60                                   # one row per second, 60 min
start = datetime.now().replace(microsecond=0) - timedelta(seconds=N)
t = np.arange(N) / 60                          # minutes

# blink rate falls as focus deepens, recovers after each break (at 20 and 40 min)
since_break = t % 20
blink = np.clip(17 - 0.5 * since_break + rng.normal(0, 1.5, N), 3, 25)
# student slowly leans in, sits back after breaks
dist = np.clip(62 - 1.1 * since_break + rng.normal(0, 2.5, N), 30, 80)
on_break = ((t >= 20) & (t < 20 + 1/3)) | ((t >= 40) & (t < 40 + 1/3))
face = np.where(on_break, 0, 1)
brightness = np.clip(110 - t * 0.9 + rng.normal(0, 3, N), 20, 200)   # evening gets darker

score = (np.clip((15 - blink) * 4, 0, 40) + np.clip((50 - dist) * 1.5, 0, 30)
         + 20 * since_break / 20).round().astype(int)
blinks_total = np.cumsum(blink / 60).astype(int)

df = pd.DataFrame({
    "timestamp": [(start + timedelta(seconds=i)).isoformat() for i in range(N)],
    "face": face,
    "ear": np.round(rng.normal(0.29, 0.02, N), 3),
    "blinks_total": blinks_total,
    "blink_rate": blink.round(1),
    "distance_cm": np.where(face == 1, dist.round(1), np.nan),
    "looking_away": 1 - face,
    "brightness": brightness.round(1),
    "on_break": on_break.astype(int),
    "strain_score": score,
    "alert": "",
})
os.makedirs("logs", exist_ok=True)
path = os.path.join("logs", "session_00000000_demo.csv")
df.to_csv(path, index=False)
print("Sample session written to", path)
