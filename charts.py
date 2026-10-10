"""Plotly charts for the Session Dashboard and Insights pages."""

import plotly.graph_objects as go

import sessions

# One data colour for every chart (each chart shows a single measure).
# Red and green are kept for "alert" and "healthy" markers only.
SERIES = "#2a78d6"
SERIES_LIGHT = "#b7d3f6"
ALERT = "#d03b3b"
HEALTHY = "#0ca30c"
BREAK = "#898781"
INK = "#12343B"
MUTED = "#5f7a7f"
GRID = "#e1e8e8"
AXIS = "#b9c9c9"

CONFIG = {"displayModeBar": False}       # hide the plotly toolbar (cleaner on a phone)


def style(fig, title, x_title, y_title, height=360):
    fig.update_layout(
        title=dict(text=title, font=dict(size=19, color=INK), x=0, xanchor="left"),
        height=height, margin=dict(l=10, r=20, t=70, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff",
        font=dict(color=INK, size=14),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hoverlabel=dict(font_size=14),
    )
    fig.update_xaxes(title_text=x_title, showgrid=False, zeroline=False,
                     linecolor=AXIS, tickfont=dict(color=MUTED))
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False,
                     linecolor=AXIS, tickfont=dict(color=MUTED))
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
        fill="tozeroy" if fill else None, fillcolor="rgba(42,120,214,0.15)"))

    if band:
        low, high, text = band
        fig.add_hrect(y0=low, y1=high, fillcolor=HEALTHY, opacity=0.12, line_width=0,
                      layer="below", annotation_text=text,
                      annotation_position="top left",
                      annotation_font=dict(color=MUTED, size=12))
    for value, text in limits:
        fig.add_hline(y=value, line=dict(color=ALERT, width=1.5, dash="dash"),
                      annotation_text=text, annotation_position="bottom right",
                      annotation_font=dict(color=ALERT, size=12))
    for start, end in sessions.break_periods(df):
        fig.add_vrect(x0=start, x1=max(end, start + 0.05), fillcolor=BREAK, opacity=0.15,
                      line_width=0, layer="below", annotation_text="break",
                      annotation_position="top left",
                      annotation_font=dict(color=MUTED, size=11))

    style(fig, title, "Minutes into session", y_title)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(hoverformat=".1f", ticksuffix=" min")
    if y_range:
        fig.update_yaxes(range=y_range)
    return fig
