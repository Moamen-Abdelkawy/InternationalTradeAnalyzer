"""The analysis: growth formulas, and missing data that is stated, never estimated."""
import math
import unittest

import numpy as np

from trade_report.analysis import (MISSING, MIXED_UNITS, Analysis, cagr, growth, hhi,
                                   is_gap, number, ratio, sum_by, total_of, trend_growth)
from trade_report.findings import findings
from trade_report.model import Metric, editions_text

from helpers import QUANTITY, VALUE, query, rows, wheat_like


class Formulas(unittest.TestCase):
    def test_growth(self):
        self.assertAlmostEqual(growth(120, 100), 0.2)
        self.assertTrue(math.isnan(growth(10, 0)))          # from nothing: not defined
        self.assertEqual(growth(MISSING, 100), MISSING)
        self.assertEqual(growth(100, MIXED_UNITS), MIXED_UNITS)

    def test_cagr(self):
        self.assertAlmostEqual(cagr(100, 121, 2), 0.1)
        self.assertTrue(math.isnan(cagr(0, 50, 3)))         # no trade in the first year
        self.assertTrue(math.isnan(cagr(50, 0, 3)))         # none in the last: not -100%
        self.assertEqual(cagr(100, MISSING, 3), MISSING)

    def test_trend(self):
        values = [100 * 1.1 ** i for i in range(5)]
        self.assertAlmostEqual(trend_growth(values, range(5)), 0.1)
        self.assertTrue(math.isnan(trend_growth([1, 0, 2], range(3))))
        self.assertEqual(trend_growth([1, MISSING, 2], range(3)), MISSING)

    def test_hhi_and_ratio(self):
        self.assertAlmostEqual(hhi([50, 50]), 5000)
        self.assertEqual(hhi([10, MISSING]), MISSING)
        self.assertTrue(math.isnan(ratio(5, 0)))
        self.assertEqual(total_of([1, 2, MISSING]), MISSING)

    def test_editions_text(self):
        every = ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]
        self.assertEqual(editions_text(every, every), "all HS editions")
        self.assertEqual(editions_text(["H0", "H1", "H2", "H3"], every), "HS 1992–2007")
        self.assertEqual(editions_text(["H4", "H5", "H6"], every), "HS 2012 onwards")
        self.assertEqual(editions_text(["H6"], every), "HS 2022 onwards")
        self.assertEqual(editions_text(["H3"], every), "HS 2007 only")
        self.assertEqual(editions_text(["H0", "H2"], every), "HS 1992, 2002")

    def test_sum_by_states_gaps(self):
        frame = rows([(2020, 1, "A", "1", 10.0, 1.0), (2020, 1, "A", "2", 5.0, np.nan),
                      (2020, 2, "B", "1", 7.0, 2.0)])
        sums = sum_by(frame, ["Partner_Code"], QUANTITY)
        self.assertEqual(sums[1], MISSING)                   # never 1.0, the partial sum
        self.assertEqual(sums[2], 2.0)
        frame["unit"] = ["kg", "u", "kg"]
        frame["quantity"] = [1.0, 2.0, 3.0]
        mixed = sum_by(frame, ["Partner_Code"],
                       Metric("quantity", "Quantity", "", "volume", unit_column="unit"))
        self.assertEqual(mixed[1], MIXED_UNITS)
        self.assertEqual(mixed[2], 3.0)


class AnnualAnalysis(unittest.TestCase):
    def setUp(self):
        self.a = Analysis(query([2020, 2021, 2022], partner=1), wheat_like())

    def test_totals_and_growth(self):
        totals = self.a.period_totals["value"]
        self.assertEqual([totals[y] for y in (2020, 2021, 2022)], [200.0, 200.0, 240.0])
        self.assertAlmostEqual(self.a.summary["cagr"], (240 / 200) ** 0.5 - 1)
        self.assertEqual(self.a.summary["top"], 1)
        self.assertAlmostEqual(self.a.summary["top_share"], 470 / 640)

    def test_missing_quantity_is_stated(self):
        quantity = self.a.period_totals["quantity"]
        self.assertEqual(quantity[2021], 20.0)               # 12 + 6 + 2
        self.assertEqual(quantity[2022], MISSING)           # Alpha's 2022 quantity is blank
        self.assertEqual(self.a.unit_values[2022], MISSING)
        self.assertEqual(self.a.summary["totals"]["quantity"], MISSING)
        self.assertEqual(self.a.summary["cagr_quantity"], MISSING)
        self.assertEqual(self.a.period_totals["value"][2022], 240.0)   # value unaffected

    def test_shares_by_year(self):
        partners = self.a.partners.set_index("Name")
        self.assertAlmostEqual(partners.loc["Alpha", "Share 2020"], 150 / 200)
        self.assertAlmostEqual(partners.loc["Alpha", "Share 2022"], 200 / 240)
        self.assertAlmostEqual(partners.loc["Alpha", "Share change (pp)"],
                               (200 / 240 - 150 / 200) * 100)
        self.assertAlmostEqual(partners.loc["Beta", "Share 2020"], 50 / 200)

    def test_partners_and_status(self):
        partners = self.a.partners.set_index("Name")
        self.assertEqual(partners.loc["Alpha", "Rank"], 1)
        self.assertEqual(partners.loc["Beta", "Status"], "Lost by 2022")
        self.assertEqual(partners.loc["Gamma", "Status"], "New since 2020")
        self.assertTrue(math.isnan(number(partners.loc["Gamma", "CAGR"])))

    def test_ranks_blank_when_metric_is_missing(self):
        a = Analysis(query([2020, 2021, 2022], metric=QUANTITY), wheat_like())
        self.assertEqual(a.partner_order.key, "value")     # listed by a complete metric
        self.assertTrue(all(r == "" for r in a.partners["Rank"]))
        self.assertEqual(a.partners.iloc[0]["Name"], "Alpha")
        self.assertEqual(a.summary["total"], MISSING)

    def test_focus(self):
        focus = self.a.focus.set_index("Period")
        self.assertAlmostEqual(focus.loc[2020, "Share"], 0.75)
        self.assertEqual(focus.loc[2022, "Rank"], 1)

    def test_findings_state_gaps(self):
        text = " ".join(findings(self.a))
        self.assertIn("does not report quantity", text)
        self.assertIn("nothing is estimated", text)


class SourceEstimates(unittest.TestCase):
    """Figures the source itself estimated are used as given and stated."""

    def setUp(self):
        data = wheat_like()
        data["quantity_estimated"] = (data["Period"] == 2021) & (data["Partner_Code"] == 1)
        q = query([2020, 2021, 2022], metric=QUANTITY)
        q.estimated_by = "UN Comtrade"
        self.a = Analysis(q, data)

    def test_estimates_are_counted_not_dropped(self):
        e = self.a.estimated["quantity"]
        self.assertEqual(self.a.period_totals["quantity"][2021], 20.0)   # 12 of it estimated
        self.assertEqual(e.count, 1)
        self.assertEqual(e.amount, 12.0)
        self.assertAlmostEqual(e.by_period[2021], 0.6)
        self.assertEqual(e.by_period[2020], 0.0)
        self.assertEqual(e.share, MISSING)        # the whole-period total is Missing (2022)
        self.assertEqual(e.cells("Partner_Code"), {(1, 2021)})
        self.assertNotIn("value", self.a.estimated)

    def test_findings_state_estimates(self):
        text = " ".join(findings(self.a))
        self.assertIn("1 quantity figure (12.0 t) is an estimate by UN Comtrade", text)
        self.assertIn("Source estimates sheet", text)


class SourceTotals(unittest.TestCase):
    """A source's own totals are used; only where it gives none are the partners added up."""

    def test_own_totals_then_partners_added_up(self):
        products = rows([(2020, 1, "Alpha", "100110", 10.0, None),
                         (2020, 2, "Beta", "100190", 5.0, 1.0),
                         (2021, 1, "Alpha", "100110", 12.0, 2.0)])
        partners = rows([(2020, 1, "Alpha", "1001", 10.0, 3.0), (2020, 2, "Beta", "1001", 5.0, 1.0),
                         (2021, 1, "Alpha", "1001", 12.0, 2.0)])
        totals = rows([(2020, 0, "World", "1001", 15.0, 4.0),
                       (2021, 0, "World", "1001", 12.0, None)])
        a = Analysis(query([2020, 2021]), products, partner_rows=partners, total_rows=totals)
        self.assertEqual(a.period_totals["quantity"][2020], 4.0)       # the source's own total
        self.assertEqual(a.period_totals["quantity"][2021], 2.0)       # none: partners added up
        self.assertEqual(a.added_up["quantity"], [2021])
        self.assertEqual(a.partner_matrix["quantity"].loc[1, 2020], 3.0)   # the code's own record
        self.assertEqual(a.product_matrix["quantity"].loc["100110", 2020], MISSING)
        text = " ".join(findings(a))
        self.assertIn("gives no total quantity for 1001 (partner World) in 2021; there the "
                      "total is its suppliers added up", text)
        self.assertNotIn("the total for 1001", text)


class MissingPeriods(unittest.TestCase):
    def test_unreported_period(self):
        q = query([2020, 2021, 2022], missing={2022: "not reported"})
        a = Analysis(q, wheat_like()[lambda f: f["Period"] < 2022])
        self.assertEqual(a.period_totals["value"][2022], MISSING)
        self.assertEqual(a.summary["total"], MISSING)
        self.assertTrue(a.partners["Status"].str.startswith("Unknown").all())
        self.assertIn("No data for 2022", " ".join(findings(a)))


class Monthly(unittest.TestCase):
    def test_complete_years_only(self):
        months = [y * 100 + m for y in (2023, 2024) for m in range(1, 13)] + [202501, 202502]
        data = rows([(p, 1, "Alpha", "100110", 10.0, 1.0) for p in months])
        a = Analysis(query(months, freq="M"), data)
        self.assertEqual(a.years, [2023, 2024])            # 2025 has two months only
        self.assertEqual(a.annual_totals["value"][2024], 120.0)
        self.assertAlmostEqual(a.summary["cagr"], 0.0)


if __name__ == "__main__":
    unittest.main()
