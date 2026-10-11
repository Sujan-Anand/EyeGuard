"""The design system (ui.py): every block renders, text is escaped, status is
never colour alone, and the colours are readable.

Run all tests with:   py -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest

import ui


def contrast(colour_a, colour_b):
    """WCAG contrast ratio between two "#RRGGBB" colours (1 to 21)."""
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    lighter, darker = sorted([luminance(colour_a), luminance(colour_b)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def showcase():
    import streamlit as st
    import ui
    ui.apply_theme()
    ui.page_header("Session dashboard", "One session at a glance.", icon="monitoring")
    ui.kpi_card("Average blink rate", "6.3", "/ min", status="Below normal", kind="warn",
                note="Healthy is 15-20")
    ui.kpi_row([dict(label="Duration", value="60", unit="min"),
                dict(label="Breaks", value="2", status="One missed", kind="warn"),
                dict(label="Strain", value="27", unit="/ 100", status="Fine", kind="good")])
    ui.status_pill("Very low", "alert")
    ui.tip_card("Blink fully and often.", icon="visibility", title="Blink more")
    ui.alert_box("Blink more! Only 6/min", kind="warn")
    ui.alert_box("Blink now! Only 4/min", kind="alert", big=True)
    ui.alert_box("<script>alert('x')</script> & more", kind="info", title="A <b>title</b>")


class ContrastTest(unittest.TestCase):
    def test_the_dark_palette(self):
        self.assertEqual((ui.BACKGROUND, ui.SURFACE, ui.BORDER, ui.INK, ui.MUTED),
                         ("#0B1F21", "#12302F", "#1F4A48", "#E8F1EF", "#A9C4C0"))
        self.assertEqual((ui.AMBER, ui.TEAL, ui.ALERT, ui.GOOD),
                         ("#F2A541", "#4FB3A9", "#F26B5B", "#5CC08A"))

    def test_text_is_readable_on_every_surface(self):
        pairs = {"text on page": (ui.INK, ui.BACKGROUND), "text on card": (ui.INK, ui.SURFACE),
                 "muted text on page": (ui.MUTED, ui.BACKGROUND),
                 "muted text on card": (ui.MUTED, ui.SURFACE),
                 "dark text on amber button": (ui.ON_AMBER, ui.AMBER),
                 "teal links on page": (ui.TEAL, ui.BACKGROUND), "teal on card": (ui.TEAL, ui.SURFACE),
                 "amber on page": (ui.AMBER, ui.BACKGROUND), "amber on card": (ui.AMBER, ui.SURFACE),
                 "alert red on page": (ui.ALERT, ui.BACKGROUND), "alert red on card": (ui.ALERT, ui.SURFACE),
                 "good green on card": (ui.GOOD, ui.SURFACE),
                 "greyed-out button text on page": (ui.DISABLED, ui.BACKGROUND),
                 "greyed-out button text on card": (ui.DISABLED, ui.SURFACE)}
        for name, (text, background) in pairs.items():
            self.assertGreaterEqual(contrast(text, background), 4.5, name)

    def test_nothing_is_left_light(self):
        for name in ("BACKGROUND", "SURFACE", "BORDER"):
            self.assertLess(contrast(getattr(ui, name), "#000000"), 3.0, name)      # dark surfaces
        for kind, status in ui.STATUS.items():
            self.assertLess(contrast(status[0], "#000000"), 3.0, kind)              # dark pill and alert backgrounds
        self.assertNotIn("#fff", ui.CSS.lower())
        self.assertNotIn("white;", ui.CSS.lower())

    def test_every_status_colour_pair_is_readable(self):
        for kind, (background, text, icon, word, accent) in ui.STATUS.items():
            self.assertGreaterEqual(contrast(text, background), 4.5, kind)
            self.assertTrue(icon, kind)                          # an icon as well as a colour
        self.assertEqual(ui.STATUS["warn"][4], ui.AMBER)         # amber for warnings
        self.assertEqual(ui.STATUS["alert"][4], ui.ALERT)        # red for strong alerts only

    def test_the_theme_file_uses_the_same_colours_and_fonts(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".streamlit", "config.toml")
        config = open(path, encoding="utf-8").read()
        for needed in ('base = "dark"', f'primaryColor = "{ui.AMBER}"',
                       f'backgroundColor = "{ui.BACKGROUND}"',
                       f'secondaryBackgroundColor = "{ui.SURFACE}"', f'textColor = "{ui.INK}"',
                       "Nunito+Sans", "family=Rubik"):
            self.assertIn(needed, config)

    def test_charts_are_dark_with_the_site_colours(self):
        import pandas as pd
        import charts
        import sample_data
        import sessions
        df = sessions.clean(sample_data.make_session(minutes=25))
        fig = charts.timeline(df, "blink_rate", "T", "Y", band=(15, 20, "Healthy"),
                              limits=[(7, "Warning", "warn"), (5, "Strong alert")])
        layout = fig.layout
        self.assertEqual(layout.paper_bgcolor, "rgba(0,0,0,0)")          # transparent
        self.assertEqual(layout.plot_bgcolor, "rgba(0,0,0,0)")
        self.assertEqual(layout.font.color, ui.INK)                      # light text
        self.assertEqual(layout.yaxis.gridcolor, ui.BORDER)              # gridlines #1F4A48
        self.assertEqual(fig.data[1].line.color, ui.TEAL)                # teal series
        lines = {shape.y0: shape.line.color for shape in layout.shapes if shape.type == "line"}
        self.assertEqual(lines, {7: ui.AMBER, 5: ui.ALERT})              # amber warning, red alert
        self.assertTrue(any(shape.type == "rect" and shape.x0 != shape.x1 and shape.fillcolor == ui.MUTED
                            for shape in layout.shapes))                 # shaded breaks
        labels = [a.text for a in layout.annotations]
        for text in ("Healthy", "Warning", "Strong alert", "break"):
            self.assertIn(text, labels)                                  # labelled in words
        for colour in (ui.TEAL, ui.AMBER, ui.ALERT, ui.GOOD, ui.MUTED, ui.INK):
            self.assertGreaterEqual(contrast(colour, ui.BACKGROUND), 4.5, colour)


class BlocksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        at = AppTest.from_function(showcase, default_timeout=60).run()
        cls.exceptions = [e.value for e in at.exception]
        cls.blocks = [h.proto.body for h in at.get("html")]
        cls.page = "\n".join(cls.blocks)

    def block(self, containing):
        """The one rendered block that contains this text."""
        found = [b for b in self.blocks if containing in b]
        self.assertEqual(len(found), 1, containing)
        return found[0]

    def test_everything_renders(self):
        self.assertEqual(self.exceptions, [])
        self.assertEqual(len(self.blocks), 9)                    # the CSS + eight blocks
        self.assertEqual(sum("<style>" in b for b in self.blocks), 1)

    def test_page_header(self):
        header = self.block("eg-header\"")
        self.assertIn("<h1>", header)
        self.assertIn("Session dashboard", header)
        self.assertIn("One session at a glance.", header)

    def test_kpi_cards_show_units_and_a_status_in_words(self):
        card = self.block("Average blink rate")
        for part in ("6.3", "/ min", "Below normal", "Healthy is 15-20"):
            self.assertIn(part, card)
        row = self.block("eg-row\"")
        self.assertEqual(row.count("eg-card eg-kpi"), 3)
        self.assertIn("One missed", row)

    def test_status_is_never_colour_alone(self):
        pill = self.block("Very low")
        self.assertIn("eg-icon", pill)
        warning, strong = self.block("Only 6/min"), self.block("Only 4/min")
        self.assertIn(">Warning<", warning)                     # the title defaults to the word
        self.assertIn(">Alert<", strong)
        self.assertIn('role="status"', warning)
        self.assertIn('role="alert"', strong)                   # only the strong one interrupts
        self.assertIn("border-color:" + ui.AMBER, warning)      # amber for warnings
        self.assertIn("border-color:" + ui.ALERT, strong)       # red for strong alerts only
        self.assertIn("eg-big", strong)

    def test_tip_card(self):
        tip = self.block("Blink fully and often.")
        self.assertIn("Blink more", tip)
        self.assertIn(">visibility<", tip)

    def test_text_is_escaped(self):
        box = self.block("&amp; more")
        self.assertNotIn("<script>", box)
        self.assertIn("&lt;script&gt;", box)
        self.assertIn("A &lt;b&gt;title&lt;/b&gt;", box)

    def test_an_unknown_kind_falls_back_safely(self):
        self.assertIn("eg-pill", ui.pill_html("Hello", "no-such-kind"))


if __name__ == "__main__":
    unittest.main()
