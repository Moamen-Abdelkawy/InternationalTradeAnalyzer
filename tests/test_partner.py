"""The partner report: the partner in the reporter's trade, the reporter in the partner's
trade, the two countries' figures for the same trade, and the trade the other way."""
import contextlib
import io
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import pandas as pd

import trade_analyzer as ta
from trade_report.analysis import MISSING
from trade_report.model import PartnerViews, QueryData
from trade_report.partner.analysis import PartnerAnalysis
from trade_report.partner.findings import findings
from trade_report.report import build_report

from helpers import query, rows, wheat_like
from test_loading import analyzer, comtrade_answer


def side_query(periods, missing=None, source="BACI"):
    """Alpha (code 1) as the reporter of its exports to every country; Egypt is 818."""
    q = query(periods, partner=818, missing=missing)
    q.reporter_code, q.reporter_name, q.flow, q.partner_name = 1, "Alpha", "Exports", "Egypt"
    q.source = source
    return q


def partner_data(side=None, side_missing=None, source="BACI", other=None):
    """Egypt's imports from Alpha, Beta and Gamma (wheat_like), Alpha's exports to every
    country, and Egypt's exports to Alpha."""
    main = wheat_like()
    side = side if side is not None else rows([
        (2020, 818, "Egypt", "100110", 150.0, 15.0), (2020, 5, "Delta", "100110", 50.0, 5.0),
        (2021, 818, "Egypt", "100110", 120.0, 12.0), (2021, 5, "Delta", "100110", 120.0, 12.0),
        (2022, 818, "Egypt", "100110", 200.0, 20.0), (2022, 6, "Eps", "100110", 600.0, 60.0)])
    other = other if other is not None else rows([(2021, 1, "Alpha", "100110", 5.0, 1.0)])
    other_q = query([2020, 2021, 2022], partner=1)
    other_q.flow, other_q.source = "Exports", source
    data = QueryData(main, main, [], pd.DataFrame())
    data.partner_views = PartnerViews(
        side=(side_query([2020, 2021, 2022], side_missing, source),
              QueryData(side, side, [], pd.DataFrame())),
        other=(other_q, QueryData(other, other, [], pd.DataFrame())))
    return data


class PartnerInTheReportersTrade(unittest.TestCase):
    def setUp(self):
        self.pa = PartnerAnalysis(query([2020, 2021, 2022], partner=1), partner_data())

    def test_share_rank_and_growth_by_year(self):
        f = self.pa.position.set_index("Period")
        self.assertAlmostEqual(f.loc[2020, "Share"], 150 / 200)
        self.assertAlmostEqual(f.loc[2021, "Share"], 120 / 200)
        self.assertEqual(f.loc[2021, "Rank"], 1)
        self.assertAlmostEqual(f.loc[2021, "Growth"], 120 / 150 - 1)
        self.assertAlmostEqual(f.loc[2022, "Total growth"], 240 / 200 - 1)
        self.assertAlmostEqual(f.loc[2022, "Growth gap (pp)"], (200 / 120 - 240 / 200) * 100)

    def test_part_of_the_change(self):
        c = self.pa.contribution
        self.assertEqual((c["total"], c["partner"]), (40.0, 50.0))      # 240 − 200, 200 − 150
        self.assertAlmostEqual(c["part"], 1.25)

    def test_products_and_the_partners_share_of_each(self):
        products = self.pa.products.set_index("Code")
        self.assertAlmostEqual(products.loc["100110", "Market share"], 420 / 530)
        self.assertAlmostEqual(products.loc["100190", "Market share"], 50 / 110)
        self.assertEqual(self.pa.product_matrix.loc["100110", 2022], 200.0)

    def test_unit_value_is_missing_where_the_quantity_is(self):
        self.assertAlmostEqual(self.pa.unit_values[2020], 10.0)       # 150 USD / 15 t
        self.assertEqual(self.pa.unit_values[2022], MISSING)          # Alpha's 2022 t is blank
        self.assertEqual(self.pa.summary["totals"]["quantity"], MISSING)

    def test_competitors_include_the_partner(self):
        self.assertEqual(self.pa.rivals, [2, 3])
        self.assertEqual(list(self.pa.competitors["Code"]), [1, 2, 3])

    def test_findings(self):
        text = " ".join(findings(self.pa))
        self.assertIn("Egypt's imports of wheat and meslin (HS 1001) from Alpha totalled 470.0 "
                      "USD over 2020–2022, 73.4% of its imports from all 3 suppliers", text)
        self.assertIn("those from Alpha rose by 50.0 USD, 125.0% of the change", text)
        self.assertIn("does not report quantity", text)


class ReporterInThePartnersTrade(unittest.TestCase):
    def test_share_and_rank_among_the_partners_markets(self):
        pa = PartnerAnalysis(query([2020, 2021, 2022], partner=1), partner_data())
        f = pa.side_position.set_index("Period")
        self.assertAlmostEqual(f.loc[2020, "Share"], 150 / 200)
        self.assertAlmostEqual(f.loc[2022, "Share"], 200 / 800)
        self.assertEqual(f.loc[2022, "Rank"], 2)                       # Eps took more
        self.assertEqual(pa.side_partners_period, None)                # whole-period totals
        self.assertIn("As recorded in BACI, Egypt's share of Alpha's exports of wheat and meslin "
                      "was 75.0% in 2020 and 25.0% in 2022", " ".join(findings(pa)))

    def test_balance_is_exports_minus_imports(self):
        pa = PartnerAnalysis(query([2020, 2021, 2022], partner=1), partner_data())
        self.assertEqual(pa.balance.tolist(), [-150.0, -115.0, -200.0])
        self.assertIn("a deficit of 465.0 USD", " ".join(findings(pa)))

    def test_no_trade_the_other_way(self):
        data = partner_data(other=rows([]))
        pa = PartnerAnalysis(query([2020, 2021, 2022], partner=1), data)
        self.assertEqual(pa.other_status, "none")
        self.assertEqual(pa.balance.tolist(), [-150.0, -120.0, -200.0])
        self.assertIn("BACI records no exports of wheat and meslin by Egypt to Alpha",
                      " ".join(findings(pa)))

    def test_a_partner_without_trade(self):
        q = query([2020, 2021, 2022], partner=9)
        q.partner_name = "Zeta"
        pa = PartnerAnalysis(q, partner_data())
        self.assertFalse(pa.traded)
        self.assertEqual(pa.position["Figure"].tolist(), [0.0, 0.0, 0.0])
        self.assertEqual(pa.position["Rank"].tolist(), ["", "", ""])
        self.assertEqual(pa.position["Share"].tolist(), [0.0, 0.0, 0.0])
        self.assertIn("BACI records no imports of wheat and meslin (HS 1001) by Egypt from Zeta",
                      " ".join(findings(pa)))
        q.flow = "Exports"
        self.assertIn("Egypt's exports of it went to 3 markets",
                      " ".join(findings(PartnerAnalysis(q, partner_data()))))


class BothCountriesFigures(unittest.TestCase):
    """COMTRADE: the partner's own figures for the same trade, used as reported."""

    def setUp(self):
        side = rows([(2020, 818, "Egypt", "100110", 140.0, 14.0),
                     (2020, 5, "Delta", "100110", 60.0, 6.0),
                     (2021, 818, "Egypt", "100110", 100.0, 10.0),
                     (2021, 5, "Delta", "100110", 80.0, 8.0)])
        q = query([2020, 2021, 2022], partner=1)
        q.source, q.estimated_by = "COMTRADE", "UN Comtrade"
        reason = "Alpha has not reported this year to COMTRADE"
        self.pa = PartnerAnalysis(q, partner_data(side, {2022: reason}, "COMTRADE"))

    def test_the_two_figures_side_by_side(self):
        mirror = self.pa.mirror["value"].set_index("Period")
        self.assertEqual(mirror.loc[2020, "Reporter"], 150.0)
        self.assertEqual(mirror.loc[2020, "Partner"], 140.0)
        self.assertAlmostEqual(mirror.loc[2020, "Difference"], 10.0)
        self.assertAlmostEqual(mirror.loc[2020, "Ratio"], 150 / 140)

    def test_unreported_years_are_missing_never_filled(self):
        mirror = self.pa.mirror["value"].set_index("Period")
        self.assertEqual(mirror.loc[2022, "Partner"], MISSING)
        self.assertEqual(mirror.loc[2022, "Difference"], MISSING)
        self.assertEqual(self.pa.side_position.set_index("Period").loc[2022, "Share"], MISSING)
        text = " ".join(findings(self.pa))
        self.assertIn("No data from Alpha for 2022: Alpha has not reported this year to "
                      "COMTRADE.", text)
        self.assertIn("for 2021, Egypt reported 120.0 USD of imports from Alpha, and Alpha "
                      "reported 100.0 USD of exports to Egypt", text)

    def test_largest_markets_of_the_latest_complete_year(self):
        # No whole-period total can be stated (2022 is not reported): 2021 is shown instead
        self.assertEqual(self.pa.side_partners_period, 2021)
        self.assertEqual(list(self.pa.side_partners["Name"]), ["Egypt", "Delta"])
        self.assertAlmostEqual(self.pa.side_partners["Share"].iloc[0], 100 / 180)

    def test_a_partner_that_reported_nothing(self):
        q = query([2020, 2021], partner=1)
        q.source = "COMTRADE"
        reason = "Alpha has not reported this year to COMTRADE"
        data = partner_data(rows([]), {2020: reason, 2021: reason}, "COMTRADE")
        data.partner_views.side[0].periods = [2020, 2021]
        pa = PartnerAnalysis(q, data)
        self.assertEqual(pa.side_status, "unreported")
        self.assertIsNone(pa.side)
        self.assertEqual(pa.mirror["value"]["Partner"].tolist(), [MISSING, MISSING])
        text = " ".join(findings(pa))
        self.assertIn("No data from Alpha for 2020–2021: Alpha has not reported this year to "
                      "COMTRADE.", text)
        self.assertIn("cannot be stated", text)


class Wording(unittest.TestCase):
    def test_shares_too_small_to_show_are_not_written_as_zero(self):
        from trade_report.partner.findings import share_text
        self.assertEqual(share_text(0.0), "0%")
        self.assertEqual(share_text(0.0003), "less than 0.1%")
        self.assertEqual(share_text(0.0006), "0.1%")
        self.assertEqual(share_text(MISSING), MISSING)

    def test_periods_are_written_as_runs(self):
        from trade_report.partner.findings import period_runs
        self.assertEqual(period_runs([2020, 2022, 2023, 2024], False), "2020, 2022–2024")
        self.assertEqual(period_runs([202311, 202312, 202401, 202403], True),
                         "Nov 2023–Jan 2024, Mar 2024")

    def test_short_product_names(self):
        from trade_report.partner.findings import product_name
        self.assertEqual(product_name("Cereals; wheat and meslin, durum wheat, other than seed",
                                      "100119"), "Wheat and meslin, durum wheat, other than seed")
        self.assertEqual(product_name("Cereals: durum wheat", "100110"), "Durum wheat")
        self.assertEqual(product_name("Nuclear reactors, boilers, machinery and mechanical "
                                      "appliances; parts thereof", "84"),
                         "Nuclear reactors, boilers, machinery and mechanical appliances")


def russia_answer():
    """Russia's own report of its exports of 100199: to the World, Egypt and Türkiye."""
    records = comtrade_answer().iloc[[0, 1, 4]].copy()
    records["partnerCode"] = [0, 818, 792]
    records["partnerDesc"] = ["World", "Egypt", "Türkiye"]
    records["primaryValue"] = [5.0e9, 2.4e9, 1.0e9]
    return records.reset_index(drop=True)


class PartnerLoading(unittest.TestCase):
    def test_views_swap_the_countries(self):
        spec = ta.Spec("COMTRADE", "A", [2023], 818, "Egypt", 818, "1001", "Wheat", "M", 643,
                       "Russian Federation", 643)
        side, other = spec.views()
        self.assertEqual((side.reporter_code, side.partner_code, side.flow_code), (643, 818, "X"))
        self.assertEqual(side.reporter_name, "Russian Federation")
        self.assertEqual((other.reporter_code, other.partner_code, other.flow_code),
                         (818, 643, "X"))

    def test_baci_reads_the_partner_views_in_the_same_pass(self):
        folder = Path(tempfile.mkdtemp())
        (folder / f"country_codes_{ta.BACI_VERSION}.csv").write_text(
            "country_code,country_name,country_iso2,country_iso3\n"
            "818,Egypt,EG,EGY\n643,Russian Federation,RU,RUS\n792,Türkiye,TR,TUR\n",
            encoding="utf-8")
        (folder / f"product_codes_HS92_{ta.BACI_VERSION}.csv").write_text(
            "code,description\n040110,Milk: fat <= 1%\n", encoding="utf-8")
        (folder / f"BACI_HS92_Y2023_{ta.BACI_VERSION}.csv").write_text(
            "t,i,j,k,v,q\n"
            "2023,643,818,040110,10.5,2.0\n"      # milk from Russia to Egypt
            "2023,792,818,040110,4.0,\n"          # milk from Türkiye to Egypt
            "2023,818,643,040110,7.0,1.0\n"       # Egypt's milk to Russia
            "2023,643,792,040110,3.0,1.0\n"       # Russia's milk to Türkiye
            "2023,792,643,040110,9.0,1.0\n",      # Türkiye's milk to Russia: in no view
            encoding="utf-8")
        an = analyzer(folder)
        plain = ta.Spec("BACI", "A", [2023], 818, "Egypt", 818, "0401", "Milk", "M")
        partner = ta.Spec("BACI", "A", [2023], 818, "Egypt", 818, "0401", "Milk", "M", 643,
                          "Russian Federation", 643)
        for _ in ("csv", "parquet"):
            with contextlib.redirect_stdout(io.StringIO()):
                alone, both = an.load_baci(plain), an.load_baci(partner)
            pd.testing.assert_frame_equal(alone.rows, both.rows)          # the same main rows
            self.assertEqual(sorted(both.side.rows["Partner_Code"]), [792, 818])
            self.assertAlmostEqual(both.side.rows["value"].sum(), 0.0135)   # 10.5 + 3.0 thousand
            self.assertEqual(both.other.rows["Partner_Code"].tolist(), [643])
            self.assertAlmostEqual(both.other.rows["value"].iloc[0], 0.007)
            with contextlib.redirect_stdout(io.StringIO()):
                an.build_baci_cache()

    def test_comtrade_fetches_the_partners_own_reports(self):
        an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        an._subscription_key = "test key"
        spec = ta.Spec("COMTRADE", "A", [2023], 818, "Egypt", 818, "100199", "Wheat", "M", 643,
                       "Russian Federation", 643)
        calls = []

        def answer(**request):
            calls.append(request)
            if request["reporterCode"] == "643":
                return russia_answer()
            return pd.DataFrame() if request["partnerCode"] == "643" else comtrade_answer()

        api = ta.comtradeapicall
        with mock.patch.object(api, "_getFinalData", side_effect=answer), \
                mock.patch.object(api, "getFinalDataAvailability",
                                  return_value=pd.DataFrame({"period": [2023]})), \
                mock.patch.object(ta.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            loaded = an.load(spec)
        self.assertEqual([c["reporterCode"] for c in calls], ["818", "643", "818"])
        self.assertEqual((calls[1]["flowCode"], calls[1]["partnerCode"]), ("X", None))
        self.assertEqual((calls[2]["flowCode"], calls[2]["partnerCode"]), ("X", "643"))
        self.assertEqual(sorted(loaded.side.rows["Partner_Code"]), [792, 818])
        self.assertEqual(loaded.side.total_rows["value"].tolist(), [5000.0])
        self.assertEqual(loaded.other.missing_periods, {})               # reported, no trade
        self.assertIsNone(loaded.other.total_rows)
        query_, data = an.assemble(spec, "value", loaded)
        pa = PartnerAnalysis(query_, data)
        self.assertAlmostEqual(pa.side_position["Share"].iloc[0], 2400 / 5000)
        self.assertEqual(pa.mirror["value"]["Partner"].iloc[0], 2400.0)

    def test_a_period_in_an_edition_without_the_code_is_missing(self):
        an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        an.hs_edition_cache = {"100190": ["H0", "H1", "H2", "H3"],
                               "100199": ["H4", "H5", "H6"]}
        an.editions_built = True
        spec = ta.Spec("COMTRADE", "A", [2011, 2012], 643, "Russian Federation", 643, "100190",
                       "Wheat", "X")
        empty = pd.DataFrame()
        loaded = ta.Loaded(rows=empty, raw=empty, raw_metrics=[], gaps=empty,
                           reported={2011: "H3", 2012: "H4"})
        an.mark_missing_codes(spec, loaded)
        self.assertEqual(loaded.missing_periods, {
            2012: "Russian Federation reported this year in HS 2012, which has no code 100190"})


class PartnerOutputs(unittest.TestCase):
    def test_files_sheets_and_sections(self):
        from docx import Document
        folder = Path(tempfile.mkdtemp())
        with contextlib.redirect_stdout(io.StringIO()):
            outputs, pa = build_report(query([2020, 2021, 2022], partner=1), partner_data(),
                                       folder)
        self.assertIsInstance(pa, PartnerAnalysis)
        with zipfile.ZipFile(outputs.workbook) as book:
            names = re.findall(r'<sheet name="([^"]+)"', book.read("xl/workbook.xml").decode())
        for sheet in ("About", "Summary", "Yearly", "Market position", "Competitors", "Prices",
                      "Products", "Partner side", "Other direction", "Raw data",
                      "Raw data, partner side", "Raw data, other direction"):
            self.assertIn(sheet, names)
        self.assertNotIn("Suppliers by year", names)            # not the All-partners report
        headings = [p.text.split(". ", 1)[1] for p in Document(str(outputs.report)).paragraphs
                    if p.style.name == "Heading 1"]
        for heading in ("The trade with Alpha", "Alpha in Egypt's imports", "Competitors",
                        "Egypt in Alpha's exports", "The other direction"):
            self.assertIn(heading, headings)
        summary = outputs.summary.read_text(encoding="utf-8")
        self.assertTrue(summary.startswith("# Egypt · Imports from Alpha · HS 1001 Wheat and "
                                           "meslin · 2020–2022"))
        charts = {path.name for path in outputs.charts}
        self.assertIn("01_trade_with_partner.png", charts)
        self.assertIn("07_partner_side.png", charts)


if __name__ == "__main__":
    unittest.main()
