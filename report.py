"""
EyeGuard session report.
  python report.py                 -> report for the latest session in logs/
  python report.py logs/xyz.csv    -> report for a specific session
Saves a PNG next to the CSV and prints a summary with tips.
"""

import glob
import os
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MIN_SAFE_DISTANCE_CM = 50
BLINK_WARN_RATE = 7                  # same two levels as eyeguard.py
BLINK_ALERT_RATE = 5
LOW_BLINK_RATE = BLINK_WARN_RATE     # older name for the warning level


def load(path=None):
    if path is None:
        files = sorted(glob.glob(os.path.join("logs", "session_*.csv")))
        if not files:
            sys.exit("No sessions in logs/. Run eyeguard.py first (or sample_data.py).")
        path = files[-1]
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["distance_cm"] = pd.to_numeric(df["distance_cm"], errors="coerce")
    return df, path


def summarise(df):
    face = df[df["face"] == 1]
    minutes = len(df) / 60
    s = {
        "minutes": minutes,
        "blinks": int(df["blinks_total"].max()),
        "avg_blink_rate": face["blink_rate"].mean(),
        "low_blink_pct": (face["blink_rate"] < LOW_BLINK_RATE).mean() * 100,
        "avg_distance": face["distance_cm"].mean(),
        "too_close_pct": (face["distance_cm"] < MIN_SAFE_DISTANCE_CM).mean() * 100,
        "breaks": int(((df["on_break"].diff() == -1)).sum()),
        "avg_score": df["strain_score"].mean(),
        "peak_score": int(df["strain_score"].max()),
    }
    tips = []
    if s["avg_blink_rate"] < 15:
        tips.append("Your blink rate is below normal (15-20/min). Blink fully and often; "
                    "try lubricating eye drops if eyes feel dry.")
    if s["too_close_pct"] > 20:
        tips.append(f"You sat closer than {MIN_SAFE_DISTANCE_CM} cm for "
                    f"{s['too_close_pct']:.0f}% of the time. Keep the screen at arm's length.")
    if s["minutes"] > 20 and s["breaks"] == 0:
        tips.append("No 20-20-20 breaks completed. Look 20 feet away for 20 s every 20 min.")
    if (df["brightness"] < 60).mean() > 0.2:
        tips.append("Room was dark for much of the session. Avoid using screens in the dark.")
    if not tips:
        tips.append("Great session - healthy blinking, distance and breaks!")
    return s, tips


def plot(df, s, out_png):
    t = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds() / 60
    smooth = lambda col: df[col].rolling(30, min_periods=1).mean()   # 30 s average
    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    fig.suptitle("EyeGuard - Session Report", fontsize=16, fontweight="bold")

    ax[0].plot(t, smooth("blink_rate"), color="#2a7de1")
    ax[0].axhspan(15, 20, color="green", alpha=0.15, label="Normal (15-20/min)")
    ax[0].axhline(BLINK_WARN_RATE, color="orange", ls="--", label=f"Warning ({BLINK_WARN_RATE}/min)")
    ax[0].axhline(BLINK_ALERT_RATE, color="red", ls="--", label=f"Strong alert ({BLINK_ALERT_RATE}/min)")
    ax[0].set_ylabel("Blinks / min")
    ax[0].legend(loc="upper right")

    ax[1].plot(t, smooth("distance_cm"), color="#8a4fd6")
    ax[1].axhline(MIN_SAFE_DISTANCE_CM, color="red", ls="--", label=f"Min safe ({MIN_SAFE_DISTANCE_CM} cm)")
    ax[1].set_ylabel("Distance (cm)")
    ax[1].legend(loc="upper right")

    ax[2].fill_between(t, smooth("strain_score"), color="#e8833a", alpha=0.6)
    ax[2].set_ylim(0, 100)
    ax[2].set_ylabel("Strain score")
    ax[2].set_xlabel("Minutes into session")
    for a in ax:
        brk = df["on_break"] == 1
        a.fill_between(t, 0, 1, where=brk, transform=a.get_xaxis_transform(),
                       color="grey", alpha=0.2, lw=0)
        a.grid(alpha=0.3)

    text = (f"Duration {s['minutes']:.0f} min | Avg blinks {s['avg_blink_rate']:.1f}/min | "
            f"Avg distance {s['avg_distance']:.0f} cm | Breaks {s['breaks']} | "
            f"Avg strain {s['avg_score']:.0f}/100")
    fig.text(0.5, 0.01, text, ha="center", fontsize=10)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(out_png, dpi=120)


def main():
    df, path = load(sys.argv[1] if len(sys.argv) > 1 else None)
    s, tips = summarise(df)
    out_png = path.replace(".csv", "_report.png")
    plot(df, s, out_png)

    print(f"\n=== EyeGuard report: {os.path.basename(path)} ===")
    print(f"Session length      : {s['minutes']:.1f} min")
    print(f"Total blinks        : {s['blinks']}")
    print(f"Average blink rate  : {s['avg_blink_rate']:.1f} /min (low {s['low_blink_pct']:.0f}% of time)")
    print(f"Average distance    : {s['avg_distance']:.0f} cm (too close {s['too_close_pct']:.0f}% of time)")
    print(f"Breaks completed    : {s['breaks']}")
    print(f"Strain score        : avg {s['avg_score']:.0f}, peak {s['peak_score']}")
    print("\nTips:")
    for tip in tips:
        print(" -", tip)
    print(f"\nChart saved: {out_png}")


if __name__ == "__main__":
    main()
