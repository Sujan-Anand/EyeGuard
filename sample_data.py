"""
Creates a realistic 60-minute demo session in logs/ so the report
can be shown even before (or without) a long live run.
  python sample_data.py && python report.py

The website imports make_session() / write_demo() from here.
"""

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

DEMO_PATH = os.path.join("logs", "session_00000000_demo.csv")


def make_session(minutes=60, seed=7, start=None,
                 blink_base=17.0, dist_base=62.0, light_base=110.0):
    """One row per second, same columns as the logs written by eyeguard.py."""
    rng = np.random.default_rng(seed)
    N = minutes * 60                               # one row per second
    if start is None:
        start = datetime.now().replace(microsecond=0) - timedelta(seconds=N)
    sec = np.arange(N)
    t = sec / 60                                   # minutes

    # blink rate falls as focus deepens, recovers after each break (every 20 min)
    since_break = t % 20
    blink = np.clip(blink_base - 0.5 * since_break + rng.normal(0, 1.5, N), 3, 25)
    # student slowly leans in, sits back after breaks
    dist = np.clip(dist_base - 1.1 * since_break + rng.normal(0, 2.5, N), 30, 80)
    on_break = (sec >= 20 * 60) & (sec % (20 * 60) < 20)   # 20 s break at 20, 40, ... min
    face = np.where(on_break, 0, 1)
    brightness = np.clip(light_base - t * 0.9 + rng.normal(0, 3, N), 20, 200)   # evening gets darker

    score = (np.clip((15 - blink) * 4, 0, 40) + np.clip((50 - dist) * 1.5, 0, 30)
             + 20 * since_break / 20).round().astype(int)
    blinks_total = np.cumsum(blink / 60).astype(int)

    return pd.DataFrame({
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


def write_demo(path=DEMO_PATH, **kwargs):
    """Writes a demo session CSV and returns its path."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    make_session(**kwargs).to_csv(path, index=False)
    return path


if __name__ == "__main__":
    print("Sample session written to", write_demo())
