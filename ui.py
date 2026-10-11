"""
EyeGuard design system: the colours, type and the few building blocks every
page uses, so the whole website looks like one product (and like our slides).

    apply_theme()    call once per page run (app.py does it)
    page_header()    page title + one-line description
    sidebar_brand()  EyeGuard name and logo at the top of the sidebar
    hero()           the big banner on the Home page
    info_cards()     a row of cards with a number or icon, a title and a sentence
    meter()          a bar for one number out of a maximum (strain, break timer)
    footer()         the small line at the bottom of a page
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
DISABLED = "#8AA5A1"         # text on a greyed-out button: dimmer, but still readable

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
TAP = "44px"                     # smallest comfortable touch target on a phone

CSS = f"""
<style>
.eg-header {{ margin: -0.6rem 0 {SPACE['md']}rem 0; }}
.eg-header p {{ color: {MUTED}; font-size: 1.05rem; margin: 0; max-width: 46rem; }}
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

.eg-row-wide {{ grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); }}

.eg-hero {{
    background: linear-gradient(135deg, {SURFACE} 0%, {BORDER} 100%);
    border: 1px solid {BORDER}; border-radius: 22px;
    padding: clamp(1.4rem, 5vw, 3.2rem); margin-bottom: {SPACE['sm']}rem;
}}
.eg-hero h1 {{ font-family: {HEADING_FONT}; font-weight: 700; color: {INK}; margin: 0; padding: 0;
               font-size: clamp(2rem, 6.5vw, 3.6rem); line-height: 1.08; letter-spacing: -0.01em; }}
.eg-hero p {{ color: {INK}; font-size: clamp(1.02rem, 2.2vw, 1.3rem); max-width: 44rem;
              margin: {SPACE['md']}rem 0 0 0; }}
.eg-hero-tag {{ color: {AMBER}; font-weight: 700; font-size: {TYPE['small']}rem;
                letter-spacing: 0.04em; margin-top: {SPACE['md']}rem; }}

.eg-info .eg-step {{ width: 2.5rem; height: 2.5rem; border-radius: 50%; background: {AMBER};
                     color: {ON_AMBER}; font-family: {HEADING_FONT}; font-weight: 700;
                     font-size: 1.2rem; display: flex; align-items: center;
                     justify-content: center; margin-bottom: {SPACE['sm']}rem; }}
.eg-info .eg-step-icon {{ background: {BORDER}; color: {AMBER}; font-size: 1.4rem; }}
.eg-info .eg-tag {{ color: {AMBER}; font-size: {TYPE['small']}rem; font-weight: 700;
                    letter-spacing: 0.04em; text-transform: uppercase; }}
.eg-info .eg-title {{ font-family: {HEADING_FONT}; font-weight: 600; font-size: {TYPE['h3']}rem;
                      color: {INK}; margin: 0.15rem 0 {SPACE['xs']}rem 0; }}
.eg-info .eg-body {{ color: {MUTED}; }}

.eg-meter {{ margin-bottom: {SPACE['md']}rem; }}
.eg-meter-top {{ display: flex; justify-content: space-between; gap: {SPACE['md']}rem;
                 font-weight: 700; color: {INK}; margin-bottom: 0.3rem; }}
.eg-meter-note {{ color: {MUTED}; font-weight: 600; }}
.eg-meter-track {{ height: 16px; border-radius: 999px; background: {SURFACE};
                   border: 1px solid {BORDER}; overflow: hidden; }}
.eg-meter-fill {{ height: 100%; border-radius: 999px; }}

.eg-footer {{ border-top: 1px solid {BORDER}; margin-top: {SPACE['xl']}rem;
              padding-top: {SPACE['md']}rem; color: {MUTED}; font-size: {TYPE['small']}rem;
              text-align: center; }}

/* Sidebar: the page you are on is highlighted in amber. */
[data-testid="stSidebarNavLink"] {{ border-radius: 10px; }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{ background: {AMBER}; }}
[data-testid="stSidebarNavLink"][aria-current="page"] span,
[data-testid="stSidebarNavLink"][aria-current="page"] p {{ color: {ON_AMBER} !important;
                                                           font-weight: 700; }}

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
/* Greyed-out buttons were too faint to read on the dark page (3.4:1). */
[data-testid="stMain"] button:disabled, [data-testid="stMain"] button:disabled p,
[data-testid="stMain"] button:disabled span {{
    color: {DISABLED} !important; opacity: 1;
}}
[data-testid="stMain"] button:disabled {{ border-style: dashed; }}

/* Phones: everything you tap is at least {TAP} tall (and the icon buttons as wide). */
.stButton button, .stDownloadButton button, .stFormSubmitButton button,
[data-testid="stFileUploaderDropzone"] button, [data-testid="stButtonGroup"] button,
[data-testid="stExpander"] summary, [data-testid="stPageLink-NavLink"],
[data-testid="stCheckbox"] label, [data-testid="stLogoLink"], [data-testid="stSidebarNavLink"],
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"],
[data-testid="stSelectbox"] > div > div, [data-testid="stSlider"] > div {{ min-height: {TAP}; }}
[data-testid="stCheckbox"] label {{ align-items: center; }}
[data-testid="stExpandSidebarButton"], [data-testid="stMainMenuButton"],
[data-testid="stSidebarCollapseButton"] button {{ min-width: {TAP}; min-height: {TAP}; }}
/* The small "?" help icons keep their size but get a finger-sized touch area. */
[data-testid="stTooltipHoverTarget"] button {{ position: relative; }}
[data-testid="stTooltipHoverTarget"] button::after {{ content: ""; position: absolute; inset: -14px; }}
/* The link icon beside each heading is too small to tap and not needed. */
[data-testid="stHeaderActionElements"] {{ display: none; }}
/* Commands such as "py eyeguard.py --demo" stay readable inside small print. */
[data-testid="stMain"] code {{ font-size: 0.875rem; overflow-wrap: anywhere; }}

@media (max-width: 640px) {{
    .eg-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: {SPACE['sm']}rem; }}
    .eg-row-wide {{ grid-template-columns: 1fr; }}
    .eg-row .eg-card {{ padding: {SPACE['md']}rem 0.8rem; }}
    .eg-row-wide .eg-card {{ padding: {SPACE['md']}rem {SPACE['lg']}rem; }}
    .eg-kpi .eg-unit {{ font-size: 0.9rem; margin-left: 0.15rem; }}
    .eg-pill {{ white-space: normal; }}
    .eg-alert, .eg-tip {{ gap: {SPACE['sm']}rem; }}
    .eg-alert {{ padding: {SPACE['md']}rem; }}
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
    """Every page starts the same way: the title, one line saying what the page
    is for, and a short amber rule."""
    st.title(f":material/{icon}: {title}" if icon else title)
    st.html(f'<div class="eg-header"><p>{_text(description)}</p>'
            '<div class="eg-rule"></div></div>')


LOGO = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 230 56" width="230" height="56">
  <path d="M6 28 C16 11 40 11 50 28 C40 45 16 45 6 28 Z" fill="none" stroke="{AMBER}"
        stroke-width="4" stroke-linejoin="round"/>
  <circle cx="28" cy="28" r="8.5" fill="{TEAL}"/><circle cx="28" cy="28" r="3.6" fill="{BACKGROUND}"/>
  <text x="62" y="38" font-family="Rubik, Segoe UI, Arial, sans-serif" font-size="29"
        font-weight="700" fill="{INK}">EyeGuard</text>
</svg>"""


def sidebar_brand():
    """The EyeGuard logo and name at the top of the sidebar, above the page links."""
    st.logo(LOGO, size="large")


def hero(title, text, tag=None):
    """The banner at the top of the Home page."""
    tag_html = f'<div class="eg-hero-tag">{_text(tag)}</div>' if tag else ""
    st.html(f'<div class="eg-hero"><h1>{_text(title)}</h1><p>{_text(text)}</p>{tag_html}</div>')


def info_cards(cards):
    """A row of cards that wraps on a narrow screen. Each card is a dictionary:
    title, text, and optionally badge (a step number), icon or tag (a small label)."""
    parts = []
    for card in cards:
        badge = ""
        if card.get("badge") is not None:
            badge = f'<div class="eg-step">{_text(card["badge"])}</div>'
        elif card.get("icon"):
            badge = f'<div class="eg-step eg-step-icon">{_icon(card["icon"])}</div>'
        tag = f'<div class="eg-tag">{_text(card["tag"])}</div>' if card.get("tag") else ""
        parts.append(f'<div class="eg-card eg-info">{badge}{tag}'
                     f'<div class="eg-title">{_text(card["title"])}</div>'
                     f'<div class="eg-body">{_text(card["text"])}</div></div>')
    st.html('<div class="eg-row eg-row-wide">' + "".join(parts) + "</div>")


def meter(label, value, maximum, kind="info", note=""):
    """A horizontal bar for one number out of a maximum (the strain meter and
    the break timer). The number and the note are written out as text too."""
    accent = STATUS.get(kind, STATUS["info"])[4]
    percent = max(0.0, min(100.0, 100.0 * value / maximum)) if maximum else 0.0
    note_html = f'<span class="eg-meter-note">{_text(note)}</span>' if note else ""
    st.html(f'<div class="eg-meter" role="meter" aria-label="{_text(label)}" aria-valuemin="0" '
            f'aria-valuemax="{_text(maximum)}" aria-valuenow="{_text(round(value, 1))}">'
            f'<div class="eg-meter-top"><span>{_text(label)}</span>{note_html}</div>'
            f'<div class="eg-meter-track"><div class="eg-meter-fill" '
            f'style="width:{percent:.1f}%;background:{accent}"></div></div></div>')


def footer(text):
    st.html(f'<div class="eg-footer">{_text(text)}</div>')


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
