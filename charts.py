"""Plotly charts for the Session Dashboard and Insights pages."""

import plotly.graph_objects as go

import sessions
import ui

# Dark charts in the site's colours. One data colour (teal) for every chart,
# since each chart shows a single measure. Amber, red and green are kept for
# the "warning", "alert" and "healthy" markers only.
SERIES = ui.TEAL
SERIES_LIGHT = "#2F7F78"             # the faint per-second line
WARNING = ui.AMBER
ALERT = ui.ALERT
HEALTHY = ui.GOOD
BREAK = ui.MUTED
INK = ui.INK
MUTED = ui.MUTED
GRID = ui.BORDER
AXIS = ui.BORDER

CONFIG = {"displayModeBar": False}       # hide the plotly toolbar (cleaner on a phone)


def style(fig, title, x_title, y_title, height=360):
    fig.update_layout(
        title=dict(text=title, font=dict(size=19, color=INK), x=0, xanchor="left"),
        height=height, margin=dict(l=10, r=20, t=70, b=10),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",     # the page shows through
        font=dict(color=INK, size=14),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
                    font=dict(color=INK)),
        hoverlabel=dict(font_size=14, bgcolor=ui.SURFACE, bordercolor=ui.BORDER,
                        font_color=INK),
    )
    fig.update_xaxes(title_text=x_title, showgrid=False, zeroline=False,
                     linecolor=AXIS, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False,
                     linecolor=AXIS, tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    return fig


def add_limits(fig, limits=(), band=None):
    """Dashed limit lines and an optional green healthy band.
    limits is a list of (value, text) for a red alert line, or
    (value, text, "warn") for an amber warning line; band is (low, high, text).
    Use "" as the text to draw the line or band without a label."""
    def label(text, position, colour):
        # plotly writes "new text" if it gets a label position without a text
        if not text:
            return {}
        return dict(annotation_text=text, annotation_position=position,
                    annotation_font=dict(color=colour, size=12))

    if band:
        low, high, text = band
        fig.add_hrect(y0=low, y1=high, fillcolor=HEALTHY, opacity=0.16, line_width=0,
                      layer="below", **label(text, "top left", HEALTHY))
    for value, text, *level in limits:
        colour = WARNING if level == ["warn"] else ALERT
        fig.add_hline(y=value, line=dict(color=colour, width=2, dash="dash"),
                      **label(text, "bottom right", colour))


def label_point(fig, x, y, text):
    """Small text label just above one data point (on a dark patch so it
    stays readable where it crosses a line)."""
    fig.add_annotation(x=x, y=y, text=text, showarrow=False, yshift=15,
                       font=dict(color=INK, size=13), bgcolor="rgba(11,31,33,0.85)")


def hour_label(hour):
    return f"{int(hour):02d}:00"


def hourly(hours, column, title, y_title, unit, limits=(), band=None):
    """One bar per hour of the day (0-23) for one measure, from
    sessions.by_hour(). The lowest hour is labelled. Pass limits and band
    with "" as their text: labels inside the plot would sit on top of bars."""
    fig = go.Figure(go.Bar(
        x=hours["hour"], y=hours[column], width=0.7,
        marker=dict(color=SERIES, cornerradius=4),
        customdata=list(zip(hours["hour"].map(hour_label), hours["minutes"])),
        hovertemplate="<b>%{customdata[0]}</b><br>%{y:.1f} " + unit
                      + "<br>from %{customdata[1]:.0f} min of data<extra></extra>"))
    add_limits(fig, limits, band)
    if len(hours) > 1:
        lowest = hours.loc[hours[column].idxmin()]
        label_point(fig, lowest["hour"], lowest[column], "lowest")

    style(fig, title, "Hour of the day", y_title)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(range=[-0.5, 23.5], tickvals=list(range(0, 24, 3)),
                     ticktext=[hour_label(h) for h in range(0, 24, 3)])
    fig.update_yaxes(range=[0, max(25, hours[column].max() * 1.2)])
    return fig


def trend(table, column, title, y_title, limits=(), y_range=None):
    """One point per session, oldest to newest, from sessions.session_table().
    The highest and lowest sessions are labelled."""
    number = list(range(1, len(table) + 1))
    when = [f"{start:%d %b %Y, %H:%M}" for start in table["start"]]
    fig = go.Figure(go.Scatter(
        x=number, y=table[column], mode="lines+markers",
        line=dict(color=SERIES, width=2),
        marker=dict(size=10, color=SERIES, line=dict(color=ui.BACKGROUND, width=2)),
        customdata=when,
        hovertemplate="<b>%{customdata}</b><br>%{y:.0f}<extra></extra>"))
    add_limits(fig, limits)
    if len(table) > 1 and table[column].max() > table[column].min():
        high, low = table[column].idxmax(), table[column].idxmin()
        label_point(fig, number[high], table[column][high], f"highest {table[column][high]:.0f}")
        label_point(fig, number[low], table[column][low], f"lowest {table[column][low]:.0f}")

    style(fig, title, "Session (oldest to newest)", y_title)
    fig.update_layout(showlegend=False)
    if len(table) <= 8:                  # few sessions: show the date under each point
        fig.update_xaxes(tickvals=number,
                         ticktext=[f"{start:%d %b}<br>{start:%H:%M}" for start in table["start"]])
    else:
        fig.update_xaxes(dtick=max(1, len(table) // 8))
    fig.update_xaxes(range=[0.5, len(table) + 0.5])
    if y_range:
        fig.update_yaxes(range=y_range)
    return fig


def timeline(df, column, title, y_title, limits=(), band=None, y_range=None, fill=False):
    """One measure over the session: faint per-second line, bold 30-s rolling
    average, dashed limit lines, an optional healthy band, grey break periods.
    limits is a list of (value, text); band is (low, high, text)."""
    t = sessions.minutes_axis(df)
    smooth = df[column].rolling(30, min_periods=1).mean()      # 30 s average

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t, y=df[column], name="Every second", mode="lines",
        line=dict(color=SERIES_LIGHT, width=1), hovertemplate="%{y:.1f}"))
    fig.add_trace(go.Scatter(
        x=t, y=smooth, name="30-s average", mode="lines",
        line=dict(color=SERIES, width=2), hovertemplate="%{y:.1f}",
        fill="tozeroy" if fill else None, fillcolor="rgba(79,179,169,0.18)"))

    add_limits(fig, limits, band)
    for start, end in sessions.break_periods(df):
        fig.add_vrect(x0=start, x1=max(end, start + 0.05), fillcolor=BREAK, opacity=0.22,
                      line_width=0, layer="below", annotation_text="break",
                      annotation_position="top left",
                      annotation_font=dict(color=MUTED, size=11))

    style(fig, title, "Minutes into session", y_title)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(hoverformat=".1f", ticksuffix=" min")
    if y_range:
        fig.update_yaxes(range=y_range)
    return fig
