"""Insights - patterns across all sessions: time of day, strain trend, best and worst."""

import math

import streamlit as st

import charts
import sessions
from report import BLINK_ALERT_RATE, BLINK_WARN_RATE
import ui

ui.page_header("Insights", "Patterns across all your sessions: time of day, trend, best and worst.")


def show(value, pattern):
    """Formats a number, or shows a dash when there is no data (NaN)."""
    return "–" if value is None or math.isnan(value) else pattern.format(value)


def duration(minutes):
    hours, mins = divmod(int(round(minutes)), 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    return f"{hours} h" if hours else f"{mins} min"


def when(start):
    return f"{start:%a %d %b %Y, %H:%M}"


def points(change):
    """ "1 point" or "3 points"."""
    return f"{change:.0f} point" + ("" if round(change) == 1 else "s")


# ------------------------------------------------------- choose the sessions
controls = st.container(horizontal=True, vertical_alignment="center")
if controls.button("Load sample week", icon=":material/science:",
                   help="Loads 7 sessions of sample data at different times of day "
                        "so you can try this page."):
    sessions.generate_sample_week()
    st.toast("Sample week loaded", icon=":material/check_circle:")

found = sessions.all_sessions()
if not found:
    st.info(
        "**No sessions yet.** You can:\n"
        "- click **Load sample week** to see an example of this page,\n"
        "- run a **Live Check** and open it in the Session Dashboard, or\n"
        "- upload CSVs saved by the desktop app on the Session Dashboard page.",
        icon=":material/info:")
    st.stop()

sample_names = [name for name in found if sessions.is_sample(name)]
if sample_names and len(sample_names) < len(found):        # a mix of sample and real
    if not controls.toggle("Include sample data", value=True,
                           help="Sample sessions are made-up data. Switch this off "
                                "to see only your own sessions."):
        found = {name: df for name, df in found.items() if name not in sample_names}
        sample_names = []
if sample_names:
    count = "1 session" if len(sample_names) == 1 else f"{len(sample_names)} sessions"
    st.caption(f":material/science: Sample data: includes {count} with made-up numbers.")

try:
    table = sessions.session_table(found)
    hours = sessions.by_hour(found)
except Exception as err:
    st.error(f"The sessions could not be combined ({err}). "
             "Try removing the last file you added.")
    st.stop()

# ------------------------------------------------------------------ KPI cards
avg_blink = sessions.weighted_mean(table, "avg_blink_rate")
avg_strain = sessions.weighted_mean(table, "avg_score")
blink_words, blink_kind = sessions.blink_status(avg_blink)
strain_words, strain_kind = sessions.strain_status(avg_strain)
ui.kpi_row([
    dict(label="Sessions", value=len(table)),
    dict(label="Total screen time", value=duration(table["minutes"].sum())),
    dict(label="Average blink rate", value=show(avg_blink, "{:.1f}"),
         unit="/ min" if blink_words else "", status=blink_words, kind=blink_kind,
         note="Healthy is 15-20"),
    dict(label="Average strain score", value=show(avg_strain, "{:.0f}"),
         unit="/ 100" if strain_words else "", status=strain_words, kind=strain_kind),
    dict(label="Breaks completed", value=int(table["breaks"].sum())),
])

# ---------------------------------------------------------------- time of day
st.subheader("Time of day")
if hours.empty:
    st.info("Not enough data yet. The camera needs to see your face for at least "
            f"{sessions.MIN_HOUR_MINUTES} minutes in an hour of the day.",
            icon=":material/info:")
else:
    low = hours.loc[hours["blink_rate"].idxmin()]
    low_hour = charts.hour_label(low["hour"])
    if len(hours) == 1:
        st.markdown(f"#### All your screen time so far is around {low_hour} "
                    f"({low['blink_rate']:.1f} blinks/min)")
        st.caption("Record sessions at other times of day to compare them.")
    else:
        high = hours.loc[hours["blink_rate"].idxmax()]
        st.markdown(f"#### Your blink rate is lowest around {low_hour} "
                    f"({low['blink_rate']:.1f} blinks/min)")
        note = (f"It is highest around {charts.hour_label(high['hour'])} "
                f"({high['blink_rate']:.1f} blinks/min). ")
        if low["blink_rate"] < 15:
            note += (f"Around {low_hour} you are below the healthy 15-20 range, "
                     "so that is the best time to plan a break or stop for the day.")
        else:
            note += "Every hour is inside or above the healthy 15-20 range."
        st.caption(note)
    st.plotly_chart(
        charts.hourly(hours, "blink_rate", "Blink rate by hour",
                      "Blinks per minute", "blinks/min",
                      limits=[(BLINK_WARN_RATE, f"Warning below {BLINK_WARN_RATE}/min", "warn"),
                              (BLINK_ALERT_RATE, f"Strong alert below {BLINK_ALERT_RATE}/min")],
                      band=(15, 20, "Healthy 15-20/min")),
        config=charts.CONFIG, alt="Average blink rate for each hour of the day")
    st.caption("Hours with under "
               f"{sessions.MIN_HOUR_MINUTES} minutes of data are not shown.")

# --------------------------------------------------------------- strain trend
st.subheader("Strain trend")
if len(table) < 2:
    st.info("Record at least two sessions to see how your eye strain changes "
            "over time.", icon=":material/info:")
else:
    slope = sessions.strain_trend(table)
    if slope > 1:
        st.markdown(f"#### Your eye strain is rising: about {points(slope)} "
                    "more each session")
        st.caption("Try shorter sessions, more breaks, or sitting further back.")
    elif slope < -1:
        st.markdown(f"#### Your eye strain is falling: about {points(-slope)} "
                    "less each session")
        st.caption("Your habits are improving. Keep it up.")
    else:
        st.markdown("#### Your eye strain is steady from session to session")
    st.plotly_chart(
        charts.trend(table, "avg_score", "Strain score by session",
                     "Score (0-100)", limits=[(50, "High strain above 50")],
                     y_range=[0, 100]),
        config=charts.CONFIG, alt="Average strain score of each session, oldest to newest")

# ------------------------------------------------------------- best and worst
st.subheader("Best and worst session")
if len(table) < 2:
    st.info("Record at least two sessions to compare them.", icon=":material/info:")
else:
    best = table.loc[table["avg_score"].idxmin()]
    worst = table.loc[table["avg_score"].idxmax()]
    cards = [("Most relaxed", ":material/sentiment_satisfied:", best),
             ("Most strain", ":material/sentiment_stressed:", worst)]
    for col, (title, icon, row) in zip(st.columns(2), cards):
        with col, st.container(border=True):
            st.markdown(f"**{icon} {title}**")
            st.write(f"{when(row['start'])} · {duration(row['minutes'])}")
            st.metric("Average strain score", f"{row['avg_score']:.0f} / 100")
            st.caption("Blink rate " + show(row["avg_blink_rate"], "{:.1f} / min")
                       + " · too close " + show(row["too_close_pct"], "{:.0f}%")
                       + " of the time")
            if st.button("Open in dashboard", key=f"open_{title}",
                         icon=":material/monitoring:"):
                st.session_state["selected_session"] = row["name"]
                st.switch_page("pages/session_dashboard.py")

# ----------------------------------------------------------------- all sessions
with st.expander("View all sessions as a table"):
    st.dataframe(
        table[["start", "minutes", "avg_blink_rate", "avg_distance", "too_close_pct",
               "breaks", "avg_score", "peak_score", "sample"]],
        hide_index=True, alt="One row per session with its summary numbers",
        column_config={
            "start": st.column_config.DatetimeColumn("Started", format="D MMM YYYY, HH:mm"),
            "minutes": st.column_config.NumberColumn("Minutes", format="%.0f"),
            "avg_blink_rate": st.column_config.NumberColumn("Blinks / min", format="%.1f"),
            "avg_distance": st.column_config.NumberColumn("Distance (cm)", format="%.0f"),
            "too_close_pct": st.column_config.NumberColumn("Too close (%)", format="%.0f"),
            "breaks": st.column_config.NumberColumn("Breaks"),
            "avg_score": st.column_config.ProgressColumn(
                "Average strain", format="%.0f", min_value=0, max_value=100),
            "peak_score": st.column_config.NumberColumn("Peak strain"),
            "sample": st.column_config.CheckboxColumn("Sample data"),
        })
