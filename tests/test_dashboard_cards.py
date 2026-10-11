"""Dashboard polish: number cards with units and a status in words, tips as
cards with the most important first, and charts with labelled limit lines.

Run all tests with:   py -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import charts
import report
import sample_data
import sessions
import ui


def summary(**changes):
    base = {"minutes": 60.0, "blinks": 700, "avg_blink_rate": 16.0, "low_blink_pct": 0.0,
            "avg_distance": 60.0, "too_close_pct": 5.0, "breaks": 3, "avg_score": 20.0,
            "peak_score": 40}
    return {**base, **changes}


def card(s, label):
    return next(c for c in sessions.kpi_cards(s) if c["label"] == label)


class StatusWordsTest(unittest.TestCase):
    def test_blink_rate_words(self):
        for rate, words, kind in [(18, "Healthy", "good"), (15, "Healthy", "good"),
                                  (12, "Below normal", "warn"), (7, "Below normal", "warn"),
                                  (6.9, "Low", "warn"), (5, "Low", "warn"),
                                  (4.9, "Very low", "alert"), (0, "Very low", "alert")]:
            self.assertEqual(sessions.blink_status(rate), (words, kind), rate)
        self.assertEqual(sessions.blink_status(float("nan")), (None, "neutral"))

    def test_breaks_words(self):
        self.assertEqual(sessions.breaks_status(0, 15), ("None due yet", "neutral"))
        self.assertEqual(sessions.breaks_status(3, 60), ("All taken", "good"))
        self.assertEqual(sessions.breaks_status(2, 60), ("One missed", "warn"))
        self.assertEqual(sessions.breaks_status(0, 60), ("3 missed", "alert"))
        self.assertEqual(sessions.breaks_status(4, 60), ("All taken", "good"))     # extra breaks are fine

    def test_strain_words(self):
        self.assertEqual(sessions.strain_status(10), ("Relaxed", "good"))
        self.assertEqual(sessions.strain_status(35), ("Moderate", "warn"))
        self.assertEqual(sessions.strain_status(50), ("High", "alert"))


class KpiCardsTest(unittest.TestCase):
    def test_every_card_has_a_unit_and_words(self):
        cards = sessions.kpi_cards(summary())
        self.assertEqual([c["label"] for c in cards],
                         ["Duration", "Average blink rate", "Average distance", "Time too close",
                          "Breaks completed", "Average strain score", "Peak strain score"])
        self.assertEqual([(c["value"], c["unit"]) for c in cards],
                         [("60", "min"), ("16.0", "/ min"), ("60", "cm"), ("5", "%"), ("3", ""),
                          ("20", "/ 100"), ("40", "/ 100")])
        self.assertEqual([c["status"] for c in cards],
                         [None, "Healthy", "Comfortable", "Rarely", "All taken", "Relaxed", "Moderate"])

    def test_a_poor_session(self):
        s = summary(avg_blink_rate=4.2, avg_distance=41.0, too_close_pct=79.0, breaks=2,
                    avg_score=58.0, peak_score=90)
        self.assertEqual((card(s, "Average blink rate")["status"], card(s, "Average blink rate")["kind"]),
                         ("Very low", "alert"))
        self.assertEqual(card(s, "Average distance")["status"], "Too close")
        self.assertEqual(card(s, "Time too close")["status"], "Often")
        self.assertEqual(card(s, "Breaks completed")["status"], "One missed")
        self.assertEqual(card(s, "Average strain score")["status"], "High")

    def test_no_data_shows_a_dash_and_no_status(self):
        nan = float("nan")
        s = summary(avg_blink_rate=nan, avg_distance=nan, too_close_pct=0.0)
        for label in ("Average blink rate", "Average distance", "Time too close"):
            c = card(s, label)
            self.assertEqual((c["value"], c["unit"], c["status"]), ("–", "", None), label)

    def test_status_kinds_exist_in_the_design_system(self):
        for c in sessions.kpi_cards(summary()) + sessions.kpi_cards(summary(avg_blink_rate=3)):
            self.assertIn(c["kind"], ui.STATUS)
            ui.kpi_html(**c)                                   # renders without error


class TipCardsTest(unittest.TestCase):
    def tips_for(self, **make):
        df = sessions.clean(sample_data.make_session(**make))
        s, tips = report.summarise(df)
        return sessions.tip_cards(df, s, tips), tips

    def test_every_tip_becomes_a_card_with_a_title_and_icon(self):
        cards, tips = self.tips_for(minutes=60, blink_base=12.0, dist_base=52.0, light_base=70.0)
        self.assertEqual(sorted(c["text"] for c in cards), sorted(tips))      # same advice, reworded nowhere
        self.assertGreaterEqual(len(cards), 3)
        for c in cards:
            self.assertTrue(c["title"] and c["icon"])
            self.assertEqual(c["kind"], "warn")

    def test_most_important_first(self):
        cards, _ = self.tips_for(minutes=60, blink_base=12.0, dist_base=52.0, light_base=70.0)
        importance = [c["importance"] for c in cards]
        self.assertEqual(importance, sorted(importance, reverse=True))
        # sitting too close most of the time outranks a slightly low blink rate
        close, _ = self.tips_for(minutes=60, blink_base=19.0, dist_base=45.0)
        self.assertEqual(close[0]["title"], "Sit back")
        blink, _ = self.tips_for(minutes=60, blink_base=8.0, dist_base=75.0)
        self.assertEqual(blink[0]["title"], "Blink more")

    def test_a_great_session(self):
        df = sessions.clean(sample_data.make_session(minutes=10, blink_base=22.0, dist_base=75.0))
        s, tips = report.summarise(df)
        cards = sessions.tip_cards(df, s, tips)
        self.assertEqual([(c["title"], c["kind"], c["icon"]) for c in cards],
                         [("Great session", "good", "thumb_up")])


class ChartPolishTest(unittest.TestCase):
    def test_limit_lines_are_labelled_7_and_5(self):
        df = sessions.clean(sample_data.make_session(minutes=25))
        fig = charts.timeline(df, "blink_rate", "Blink rate", "Blinks per minute",
                              limits=[(7, "Warning below 7/min", "warn"), (5, "Strong alert below 5/min")],
                              band=(15, 20, "Healthy 15-20/min"))
        labels = {a.text: a.font.color for a in fig.layout.annotations}
        self.assertEqual(labels["Warning below 7/min"], ui.AMBER)
        self.assertEqual(labels["Strong alert below 5/min"], ui.ALERT)
        self.assertIn("break", labels)                                        # shaded breaks, labelled
        self.assertEqual(fig.layout.title.text, "Blink rate")
        self.assertGreaterEqual(fig.layout.font.size, 15)                     # projector-sized text
        self.assertGreaterEqual(fig.layout.xaxis.tickfont.size, 14)

    def test_bar_chart_names_its_limits_in_the_legend(self):
        found = {"a.csv": sessions.clean(sample_data.make_session(minutes=30))}
        fig = charts.hourly(sessions.by_hour(found), "blink_rate", "By hour", "Blinks per minute",
                            "blinks/min", limits=[(7, "Warning below 7/min", "warn"),
                                                  (5, "Strong alert below 5/min")],
                            band=(15, 20, "Healthy 15-20/min"))
        self.assertEqual([t.name for t in fig.data[1:]],
                         ["Healthy 15-20/min", "Warning below 7/min", "Strong alert below 5/min"])
        self.assertEqual([t.line.color for t in fig.data[2:]], [ui.AMBER, ui.ALERT])
        self.assertFalse(any(a.text.startswith(("Warning", "Strong", "Healthy"))
                             for a in fig.layout.annotations))                # nothing on top of the bars

    def test_all_charts_share_one_style(self):
        df = sessions.clean(sample_data.make_session(minutes=25))
        found = {"a.csv": df, "b.csv": sessions.clean(sample_data.make_session(minutes=25, seed=2))}
        figs = [charts.timeline(df, "distance_cm", "D", "cm"),
                charts.hourly(sessions.by_hour(found), "blink_rate", "H", "y", "u"),
                charts.trend(sessions.session_table(found), "avg_score", "T", "y")]
        for fig in figs:
            self.assertEqual((fig.layout.font.color, fig.layout.font.size), (ui.INK, 15))
            self.assertEqual(fig.layout.paper_bgcolor, "rgba(0,0,0,0)")
            self.assertEqual(fig.layout.yaxis.gridcolor, ui.BORDER)
            self.assertEqual(fig.layout.title.font.size, 21)


if __name__ == "__main__":
    unittest.main()
