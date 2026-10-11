"""
EyeGuard design system: the colours, type and the few building blocks every
page uses, so the whole website looks like one product (and like our slides).

    apply_theme()    call once per page run (app.py does it)
    page_header()    page title + one-line description
    kpi_card() / kpi_row()   a number with its unit and a status in words
    status_pill()    small coloured label, always with a word and an icon
    tip_card()       one piece of advice with an icon
    alert_box()      a message: info, good, warning or strong alert

Colours and fonts for Streamlit's own widgets are set in .streamlit/config.toml.
The CSS here only styles the blocks above, where the theme is not enough.
Status is never shown by colour alone: every pill and alert carries a word.
"""

import html

import streamlit as st

# ------------------------------------------------------------------- colours
# Dark theme. The same values are in .streamlit/config.toml.
BACKGROUND = "#0B1F21"       # page
SURFACE = "#12302F"          # cards, sidebar
BORDER = "#1F4A48"           # card borders, chart gridlines
INK = "#E8F1EF"              # main text
MUTED = "#A9C4C0"            # secondary text
AMBER = "#F2A541"            # accent: buttons, highlights, current page; also warnings
TEAL = "#4FB3A9"             # charts, links, icons
ALERT = "#F26B5B"            # strong alerts only
GOOD = "#5CC08A"
ON_AMBER = "#0B1F21"         # text on an amber button

# Each status: (background, text, icon, default word, accent). Text on its
# background is at least 4.5:1 (checked in tests/test_ui.py).
STATUS = {
    "good":    ("#143A2A", "#8FDDB0", "check_circle", "Good", GOOD),
    "warn":    ("#3D2E12", "#F7C47A", "warning", "Warning", AMBER),
    "alert":   ("#40201D", "#FFA599", "error", "Alert", ALERT),
    "info":    ("#173B3A", "#9ADAD2", "info", "Info", TEAL),
    "neutral": ("#1B3B3A", "#C2D6D3", "radio_button_unchecked", "", MUTED),
}

HEADING_FONT = "'Rubik', 'Segoe UI', Arial, sans-serif"
BODY_FONT = "'Nunito Sans', 'Segoe UI', Arial, sans-serif"
ICON_FONT = "'Material Symbols Rounded'"      # the icon font Streamlit already loads

# Type scale (rem) and spacing (rem) used by every block
TYPE = {"display": 2.6, "h1": 2.1, "h2": 1.5, "h3": 1.2, "body": 1.0, "small": 0.86}
SPACE = {"xs": 0.25, "sm": 0.5, "md": 1.0, "lg": 1.5, "xl": 2.5}
RADIUS = "14px"

CSS = f"""
<style>
.eg-header {{ margin: 0 0 {SPACE['lg']}rem 0; }}
.eg-header h1 {{
    font-family: {HEADING_FONT}; font-weight: 700; color: {INK};
    font-size: clamp(1.7rem, 4.5vw, {TYPE['h1']}rem); line-height: 1.15;
    margin: 0; padding: 0; display: flex; align-items: center; gap: {SPACE['sm']}rem;
}}
.eg-header p {{ color: {MUTED}; font-size: 1.05rem; margin: {SPACE['sm']}rem 0 0 0; max-width: 46rem; }}
.eg-header .eg-rule {{ width: 3.5rem; height: 4px; border-radius: 2px; background: {AMBER};
                      margin-top: {SPACE['md']}rem; }}
.eg-icon {{ font-family: {ICON_FONT}; font-weight: 400; font-style: normal; line-height: 1;
            display: inline-block; vertical-align: middle; }}

.eg-card {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS};
    padding: {SPACE['md']}rem {SPACE['lg']}rem; color: {INK};
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}}
.eg-row {{ display: grid; gap: {SPACE['md']}rem; margin-bottom: {SPACE['md']}rem;
           grid-template-columns: repeat(auto-fit, minmax(11.5rem, 1fr)); }}

.eg-kpi .eg-label {{ color: {MUTED}; font-size: {TYPE['small']}rem; font-weight: 600;
                     letter-spacing: 0.02em; }}
.eg-kpi .eg-value {{ font-family: {HEADING_FONT}; font-weight: 700; color: {INK};
                     font-size: clamp(1.6rem, 4vw, 2.1rem); line-height: 1.2;
                     margin: {SPACE['xs']}rem 0 {SPACE['sm']}rem 0; overflow-wrap: anywhere; }}
.eg-kpi .eg-unit {{ font-family: {BODY_FONT}; font-weight: 600; font-size: 1rem; color: {MUTED};
                    margin-left: 0.3rem; }}
.eg-kpi .eg-note {{ color: {MUTED}; font-size: {TYPE['small']}rem; margin-top: {SPACE['sm']}rem; }}

.eg-pill {{ display: inline-flex; align-items: center; gap: 0.3rem; border-radius: 999px;
            padding: 0.2rem 0.7rem; font-size: {TYPE['small']}rem; font-weight: 700;
            line-height: 1.4; white-space: nowrap; }}
.eg-pill .eg-icon {{ font-size: 1.05rem; }}

.eg-tip {{ display: flex; gap: {SPACE['md']}rem; align-items: flex-start;
           margin-bottom: {SPACE['md']}rem; }}
.eg-tip .eg-badge {{ flex: 0 0 auto; width: 2.6rem; height: 2.6rem; border-radius: 50%;
                     display: flex; align-items: center; justify-content: center;
                     font-size: 1.5rem; }}
.eg-tip .eg-title {{ font-family: {HEADING_FONT}; font-weight: 600; color: {INK};
                     margin-bottom: 0.15rem; }}

.eg-alert {{ display: flex; gap: {SPACE['md']}rem; align-items: flex-start;
             border-radius: {RADIUS}; padding: {SPACE['md']}rem {SPACE['lg']}rem;
             margin-bottom: {SPACE['md']}rem; border-left: 6px solid; }}
.eg-alert .eg-icon {{ font-size: 1.6rem; }}
.eg-alert .eg-title {{ font-family: {HEADING_FONT}; font-weight: 700; margin-bottom: 0.1rem; }}
.eg-alert.eg-big {{ font-size: 1.15rem; padding: {SPACE['lg']}rem; }}

/* Streamlit draws white text on the accent colour; amber needs dark text. */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primaryFormSubmit"], [data-testid="stBaseButton-primaryFormSubmit"] p {{
    color: {ON_AMBER} !important; font-weight: 700;
}}
</style>
"""


# -------------------------------------------------------------------- helpers
def _text(value):
    """Text is always escaped, so a name or message can never break the page."""
    return html.escape(str(value))


def _icon(name):
    return f'<span class="eg-icon" aria-hidden="true">{_text(name)}</span>'


def apply_theme():
    """Adds the design-system CSS to the page. Call once at the top of each run."""
    st.html(CSS)


# --------------------------------------------------------------------- blocks
def page_header(title, description, icon=None):
    """Page title, one-line description and a short amber rule under them."""
    mark = _icon(icon) if icon else ""
    st.html(f'<div class="eg-header"><h1>{mark}{_text(title)}</h1>'
            f'<p>{_text(description)}</p><div class="eg-rule"></div></div>')


def pill_html(text, kind="neutral"):
    """The HTML for a status pill, for use inside other blocks."""
    background, colour, icon = STATUS.get(kind, STATUS["neutral"])[:3]
    return (f'<span class="eg-pill" style="background:{background};color:{colour}">'
            f'{_icon(icon)}{_text(text)}</span>')


def status_pill(text, kind="neutral"):
    """A small label such as "Below normal". The word carries the meaning;
    the colour and icon only reinforce it."""
    st.html(pill_html(text, kind))


def kpi_html(label, value, unit="", status=None, kind="neutral", note=None):
    pill = pill_html(status, kind) if status else ""
    unit_html = f'<span class="eg-unit">{_text(unit)}</span>' if unit else ""
    note_html = f'<div class="eg-note">{_text(note)}</div>' if note else ""
    return (f'<div class="eg-card eg-kpi"><div class="eg-label">{_text(label)}</div>'
            f'<div class="eg-value">{_text(value)}{unit_html}</div>{pill}{note_html}</div>')


def kpi_card(label, value, unit="", status=None, kind="neutral", note=None):
    """One number in a card: label, value with its unit, a status in
    words (optional) and a short note (optional)."""
    st.html(kpi_html(label, value, unit, status, kind, note))


def kpi_row(cards):
    """Several KPI cards side by side; they wrap onto new rows on a narrow
    screen. cards is a list of dictionaries with the kpi_card() arguments."""
    st.html('<div class="eg-row">' + "".join(kpi_html(**card) for card in cards) + "</div>")


def tip_card(text, icon="lightbulb", title=None, kind="info"):
    """One piece of advice: a round icon badge, an optional title and the text."""
    background, colour = STATUS.get(kind, STATUS["info"])[:2]
    title_html = f'<div class="eg-title">{_text(title)}</div>' if title else ""
    st.html(f'<div class="eg-card eg-tip"><div class="eg-badge" '
            f'style="background:{background};color:{colour}">{_icon(icon)}</div>'
            f'<div>{title_html}<div>{_text(text)}</div></div></div>')


def alert_box(text, kind="warn", title=None, big=False):
    """A message box. kind is "info", "good", "warn" (amber) or "alert" (red,
    for strong alerts only). The title defaults to the status word, so the
    meaning never depends on colour."""
    background, colour, icon, word, accent = STATUS.get(kind, STATUS["info"])
    heading = title if title is not None else word
    title_html = f'<div class="eg-title">{_text(heading)}</div>' if heading else ""
    role = "alert" if kind == "alert" else "status"
    st.html(f'<div class="eg-alert{" eg-big" if big else ""}" role="{role}" '
            f'style="background:{background};color:{colour};border-color:{accent}">'
            f'{_icon(icon)}<div>{title_html}<div>{_text(text)}</div></div></div>')
