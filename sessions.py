"""
Shared helpers for the website: find, load, check and summarise session CSVs.
The CSV reading and the summary/tips logic come from report.py, and the demo
data comes from sample_data.py - nothing is duplicated here.
"""

import glob
import io
import os
import threading
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import report
import sample_data

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
COLUMNS = ["timestamp", "face", "ear", "blinks_total", "blink_rate", "distance_cm",
           "looking_away", "brightness", "on_break", "strain_score", "alert"]
NUMERIC = [c for c in COLUMNS if c not in ("timestamp", "alert")]

# (days ago, start hour, minutes, blink_base, dist_base, light_base)
# A made-up week for the Insights page: later sessions are darker and more tiring.
DEMO_WEEK = [
    (6, 9, 45, 18.5, 66, 160),
    (5, 11, 60, 17.5, 64, 150),
    (4, 14, 50, 17.0, 63, 140),
    (3, 16, 60, 16.0, 61, 125),
    (2, 19, 70, 15.0, 59, 105),
    (1, 21, 80, 14.0, 57, 90),
    (0, 23, 60, 12.5, 55, 75),
]

_plot_lock = threading.Lock()        # matplotlib's pyplot is not thread-safe


# ------------------------------------------------------------------ loading
def clean(df):
    """Checks a session table has the EyeGuard columns and tidies the types."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("this is not an EyeGuard session file (missing columns: "
                         + ", ".join(missing) + ")")
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "strain_score", "blinks_total"])
    if df.empty:
        raise ValueError("the file has no usable rows")
    df["alert"] = df["alert"].fillna("")
    return df.sort_values("timestamp").reset_index(drop=True)


def read_session(source):
    """source is a file path or an uploaded file. Raises ValueError with a
    friendly message if it cannot be used."""
    try:
        df, _ = report.load(source)
    except Exception as err:
        raise ValueError(f"could not read the CSV ({err})") from err
    return clean(df)


@st.cache_data(show_spinner=False, max_entries=50)
def _read_saved(path, modified):
    """Cached by file path + modified time, so a file is only parsed once."""
    return read_session(path)


def saved_paths():
    return sorted(glob.glob(os.path.join(LOG_DIR, "session_*.csv")))


def uploads():
    """Sessions uploaded or recorded in this browser session (not saved to disk)."""
    return st.session_state.setdefault("uploads", {})


def all_sessions():
    """Returns {name: DataFrame} for every session in logs/ plus this
    visitor's uploads. Files that cannot be read are skipped with a warning."""
    found = {}
    for path in saved_paths():
        name = os.path.basename(path)
        try:
            found[name] = _read_saved(path, os.path.getmtime(path))
        except ValueError as err:
            st.warning(f"Skipped {name}: {err}.")
    found.update(uploads())
    return found


def is_demo(name):
    return name.endswith("_demo.csv")


def label(name, df):
    """Readable name for the session picker."""
    start = df["timestamp"].iloc[0]
    text = f"{start:%d %b %Y, %H:%M} · {len(df) / 60:.0f} min · {name}"
    return "Demo · " + text if is_demo(name) else text


# ---------------------------------------------------------------- demo data
def generate_demo():
    """One 60-minute demo session ending now (same as running sample_data.py)."""
    path = os.path.join(LOG_DIR, os.path.basename(sample_data.DEMO_PATH))
    return sample_data.write_demo(path)


def generate_demo_week():
    """Seven demo sessions at different times of day, for the Insights page."""
    today = datetime.now().replace(minute=0, second=0, microsecond=0)
    paths = []
    for i, (days_ago, hour, minutes, blink, dist, light) in enumerate(DEMO_WEEK, start=1):
        start = today.replace(hour=hour) - timedelta(days=days_ago)
        if start + timedelta(minutes=minutes) > datetime.now():
            start -= timedelta(days=1)             # never write a session in the future
        path = os.path.join(LOG_DIR, f"session_0000000{i}_demo.csv")
        paths.append(sample_data.write_demo(
            path, minutes=minutes, seed=100 + i, start=start,
            blink_base=blink, dist_base=dist, light_base=light))
    return paths


# ------------------------------------------------------------- calculations
def summarise(df):
    """(summary dict, tips list) straight from report.py."""
    return report.summarise(df)


def minutes_axis(df):
    """Minutes since the session started, for the x axis of the charts."""
    return (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds() / 60


def break_periods(df):
    """List of (start_minute, end_minute) for every stretch of on_break == 1."""
    t = minutes_axis(df)
    on = df["on_break"] == 1
    block = (on != on.shift()).cumsum()            # new id each time on_break flips
    return [(t[rows.index[0]], t[rows.index[-1]])
            for _, rows in df[on].groupby(block[on])]


@st.cache_data(show_spinner=False, max_entries=20)
def report_png(df):
    """The matplotlib report from report.py as PNG bytes (for the download button)."""
    summary, _ = report.summarise(df)
    buffer = io.BytesIO()
    with _plot_lock:
        report.plot(df, summary, buffer)
        plt.close("all")
    return buffer.getvalue()
