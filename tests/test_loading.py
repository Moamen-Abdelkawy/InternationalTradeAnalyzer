"""Reading BACI and COMTRADE, and parsing what the user types."""
import contextlib
import io
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import trade_analyzer as ta
from trade_report.analysis import MISSING, Analysis
from trade_report.findings import findings


def analyzer(folder: Path) -> ta.TradeAnalyzer:
    """An analyzer on a tiny BACI folder, without COMTRADE or the real data."""
    an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
    an.baci_dir, an.cache_dir = folder, folder / "parquet"
    an.comtrade_hs92_cache = {"04": "Dairy produce", "0401": "Milk and cream",
                              "40": "Rubber", "4011": "New pneumatic tyres"}
    with contextlib.redirect_stdout(io.StringIO()):
        an.load_baci_reference_data()
    return an


class Codes(unittest.TestCase):
    def test_normalize_hs_code(self):
        an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        self.assertEqual(an.normalize_hs_code("401"), "0401")
        self.assertEqual(an.normalize_hs_code("40110"), "040110")
        self.assertEqual(an.normalize_hs_code("0401"), "0401")
        self.assertEqual(an.normalize_hs_code("4011"), "4011")
        self.assertEqual(an.normalize_hs_code("01061"), "01061")   # a zero-led odd code stays

    def test_parse_period(self):
        self.assertEqual(ta.parse_period("2018-2020", "A", "BACI"), [2018, 2019, 2020])
        self.assertEqual(ta.parse_period("202311-202402", "M", "COMTRADE"),
                         [202311, 202312, 202401, 202402])
        for bad in ("1990-1995", "2020-2018", "20xx"):
            with self.assertRaises(ValueError):
                ta.parse_period(bad, "A", "BACI")
        with self.assertRaises(ValueError):
            ta.parse_period("202313", "M", "COMTRADE")


class Baci(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / f"country_codes_{ta.BACI_VERSION}.csv").write_text(
            "country_code,country_name,country_iso2,country_iso3\n"
            "818,Egypt,EG,EGY\n643,Russian Federation,RU,RUS\n792,TÃ¼rkiye,TR,TUR\n",
            encoding="utf-8")
        (self.folder / f"product_codes_HS92_{ta.BACI_VERSION}.csv").write_text(
            "code,description\n040110,Milk: fat <= 1%\n401110,Tyres: for cars\n", encoding="utf-8")
        (self.folder / f"BACI_HS92_Y2023_{ta.BACI_VERSION}.csv").write_text(
            "t,i,j,k,v,q\n"
            "2023,643,818,040110,10.5,2.0\n"      # milk from Russia, with a quantity
            "2023,792,818,040110,4.0,\n"          # milk from Türkiye, quantity left blank
            "2023,643,818,401110,99.0,9.0\n"      # tyres: must not count as 0401
            "2023,818,643,040110,7.0,1.0\n",      # an export: not an import
            encoding="utf-8")
        self.an = analyzer(self.folder)

    def load(self, product):
        spec = ta.Spec("BACI", "A", [2023], 818, "Egypt", 818, product, "x", "M")
        with contextlib.redirect_stdout(io.StringIO()):
            return self.an.load_baci(spec)

    def test_leading_zero_and_blank_quantity(self):
        loaded = self.load("0401")
        rows = loaded.rows.set_index("Partner_Name")
        self.assertEqual(sorted(rows["Product_Code"]), ["040110", "040110"])
        # 10.5 thousand USD in BACI is 0.0105 million USD; Raw data keeps BACI's 10.5
        self.assertAlmostEqual(rows.loc["Russian Federation", "value"], 0.0105)
        self.assertEqual(sorted(loaded.raw["Value, thousand USD (v)"]), [4.0, 10.5])
        self.assertTrue(math.isnan(rows.loc["Türkiye", "quantity"]))   # repaired name, blank kept
        self.assertEqual(list(loaded.gaps["Reason"]), ["BACI leaves the quantity blank"])

    def test_totals_keep_missing(self):
        loaded = self.load("TOTAL")
        rows = loaded.rows.set_index("Partner_Name")
        self.assertAlmostEqual(rows.loc["Russian Federation", "value"], 0.1095)
        self.assertAlmostEqual(rows.loc["Russian Federation", "quantity"], 11.0)    # t, as BACI
        self.assertTrue(math.isnan(rows.loc["Türkiye", "quantity"]))

    def test_missing_year_file(self):
        spec = ta.Spec("BACI", "A", [2022, 2023], 818, "Egypt", 818, "0401", "x", "M")
        with contextlib.redirect_stdout(io.StringIO()):
            loaded = self.an.load_baci(spec)
        self.assertIn(2022, loaded.missing_periods)

    def test_no_record_at_all_gives_no_report_and_says_why(self):
        # 2022 has no file, and the 2023 file has no milk powder (0402)
        reason = f"2022: the BACI file for 2022 is not in {self.folder.name}"
        for periods, expected in (
                ([2022], f"no data for any period of the query ({reason})"),
                ([2022, 2023], "no trade recorded in the periods the source reports, and no data "
                               f"for the others ({reason})")):
            spec = ta.Spec("BACI", "A", periods, 818, "Egypt", 818, "0402", "x", "M")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                self.assertIsNone(self.an.run_spec(spec, Path(tempfile.mkdtemp())))
            self.assertIn(f"Analysis cancelled: {expected}", printed.getvalue())

    def test_check_against_comtrade_without_a_key_says_so(self):
        self.an.base_dir, self.an._subscription_key = self.folder, None
        spec = ta.Spec("BACI", "A", [2023], 818, "Egypt", 818, "0401", "x", "M")
        loaded = self.load("0401")
        with contextlib.redirect_stdout(io.StringIO()):
            self.an.check_against_comtrade(spec, loaded)
        self.assertIsNone(loaded.comtrade_check)
        self.assertIn("Not made: there is no COMTRADE API key", dict(loaded.checks)[
            "BACI against COMTRADE"])

    def test_check_against_comtrade(self):
        # BACI: milk (0401) into Egypt from Russia 10.5 and from Türkiye 4.0 thousand USD.
        # COMTRADE, Egypt's own report: 10,000 USD from the World and 7,000 from Russia in 2023;
        # 2022 not reported
        self.an._subscription_key = "test key"
        answer = pd.DataFrame({"period": ["2023", "2023"], "partnerCode": [0, 643],
                               "primaryValue": [10000.0, 7000.0], "partner2Code": [0, 0],
                               "motCode": [0, 0], "customsCode": ["C00", "C00"]})
        spec = ta.Spec("BACI", "A", [2022, 2023], 818, "Egypt", 818, "0401", "x", "M", 643,
                       "Russian Federation", 643)
        with contextlib.redirect_stdout(io.StringIO()):
            loaded = self.an.load_baci(spec)
        api = ta.comtradeapicall
        with mock.patch.object(api, "_getFinalData", return_value=answer) as request, \
                mock.patch.object(api, "getFinalDataAvailability", return_value=pd.DataFrame(
                    {"period": [2023], "classificationCode": ["H6"]})), \
                contextlib.redirect_stdout(io.StringIO()):
            self.an.check_against_comtrade(spec, loaded)
        sent = request.call_args.kwargs
        self.assertEqual((sent["reporterCode"], sent["cmdCode"], sent["flowCode"],
                          sent["partnerCode"]), ("818", "0401", "M", "0,643"))
        check = loaded.comtrade_check.set_index(["Flow", "Year"])
        world = check.loc[("Egypt's imports, all partners", 2023)]
        self.assertAlmostEqual(world["BACI (million USD)"], 0.0145)        # never changed
        self.assertAlmostEqual(world["BACI / COMTRADE"], 1.45)
        russia = check.loc[("Egypt's imports from Russian Federation", 2023)]
        self.assertAlmostEqual(russia["BACI / COMTRADE"], 1.5)
        missing = check.loc[("Egypt's imports, all partners", 2022)]
        self.assertEqual(missing["BACI (million USD)"], MISSING)          # no BACI file
        self.assertEqual(missing["Note"], "Egypt has not reported this year to COMTRADE")
        lines = dict(loaded.checks)
        self.assertIn("BACI's value is 1.45 times Egypt's own COMTRADE figure for 0401 in 2023; "
                      "2022: Egypt has not reported this year to COMTRADE",
                      lines["BACI against COMTRADE: Egypt's imports, all partners"])
        self.assertIn("1.50 times",
                      lines["BACI against COMTRADE: Egypt's imports from Russian Federation"])

    def test_parquet_cache_gives_the_same_rows(self):
        from_csv = self.load("0401").rows
        with contextlib.redirect_stdout(io.StringIO()):
            self.an.build_baci_cache()
        from_cache = self.load("0401").rows
        pd.testing.assert_frame_equal(from_csv.reset_index(drop=True),
                                      from_cache.reset_index(drop=True), check_dtype=False)


def comtrade_answer():
    """A COMTRADE answer shaped like Egypt's 2023 wheat imports: one weight UN Comtrade
    estimated, one left empty, one recorded as 0 and one quantity whose unit is N/A."""
    def record(code, name, value, weight, weight_estimated, qty, unit_code, unit,
               qty_estimated):
        return {"period": "2023", "partnerCode": code, "partnerDesc": name, "partnerISO": "",
                "cmdCode": "100199", "cmdDesc": "Wheat", "primaryValue": value,
                "cifvalue": value, "fobvalue": None, "netWgt": weight, "grossWgt": None,
                "qty": qty, "qtyUnitCode": unit_code, "qtyUnitAbbr": unit,
                "isNetWgtEstimated": weight_estimated, "isGrossWgtEstimated": False,
                "isQtyEstimated": qty_estimated, "isReported": False, "isAggregate": False,
                "classificationCode": "H6"}
    return pd.DataFrame([
        record(0, "World", 3.6e9, None, False, 0.0, -1, "N/A", False),
        record(643, "Russian Federation", 2.56e9, 6.54e9, True, 6.54e9, 8, "kg", True),
        record(804, "Ukraine", 4.5e8, None, False, 0.0, -1, "N/A", False),
        record(251, "France", 1.2e8, 0.0, False, 3.0e8, 8, "kg", False),
        record(642, "Romania", 4.6e8, 1.2e9, False, 1.2e9, 8, "kg", False),
    ])


class Comtrade(unittest.TestCase):
    def setUp(self):
        self.an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        self.an._subscription_key = "test key"
        self.spec = ta.Spec("COMTRADE", "A", [2023], 818, "Egypt", 818, "100199", "Wheat", "M")
        api = ta.comtradeapicall
        with mock.patch.object(api, "_getFinalData", return_value=comtrade_answer()), \
                mock.patch.object(api, "getFinalDataAvailability",
                                  return_value=pd.DataFrame({"period": [2023]})), \
                contextlib.redirect_stdout(io.StringIO()):
            self.loaded = self.an.load_comtrade(self.spec)
        self.rows = self.loaded.rows.set_index("Partner_Name")

    def test_estimates_are_used_and_flagged(self):
        self.assertAlmostEqual(self.rows.loc["Russian Federation", "netweight"], 6.54e6)
        self.assertTrue(self.rows.loc["Russian Federation", "netweight_estimated"])
        self.assertFalse(self.rows.loc["Romania", "netweight_estimated"])
        estimates = self.loaded.estimates
        self.assertEqual(sorted(estimates["Source flag"]), ["isNetWgtEstimated", "isQtyEstimated"])
        self.assertTrue((estimates["Partner"] == "Russian Federation").all())
        self.assertNotIn("estimated", " ".join(self.loaded.gaps["Reason"]))

    def test_zero_and_unitless_figures_stay_missing(self):
        self.assertTrue(math.isnan(self.rows.loc["Ukraine", "netweight"]))   # empty
        self.assertTrue(math.isnan(self.rows.loc["France", "netweight"]))    # 0 with a value
        self.assertTrue(math.isnan(self.rows.loc["Ukraine", "quantity"]))    # unit N/A
        self.assertAlmostEqual(self.rows.loc["France", "quantity"], 3.0e8)   # kg, as reported
        self.assertEqual(self.rows.loc["France", "Quantity unit"], "kg")
        self.assertAlmostEqual(self.rows.loc["Romania", "netweight"], 1.2e6)  # t, from kg
        reasons = set(self.loaded.gaps["Reason"])
        self.assertIn("recorded as 0 in COMTRADE although the flow has a value", reasons)
        self.assertIn("quantity unit is N/A in COMTRADE", reasons)

    def test_the_edition_of_each_period_is_kept(self):
        self.assertEqual(self.loaded.editions, {2023: ["H6"]})
        query, _ = self.an.assemble(self.spec, "value", self.loaded)
        self.assertEqual(query.hs_editions, {2023: "HS 2022"})
        self.assertEqual(query.product_editions, {})        # one edition: nothing to compare

    def test_raw_data_is_exactly_what_comtrade_returned(self):
        raw = self.loaded.raw.set_index("partnerDesc")
        self.assertEqual(raw.loc["France", "netWgt"], 0.0)
        self.assertEqual(raw.loc["Ukraine", "qty"], 0.0)
        self.assertEqual(raw.loc["Ukraine", "qtyUnitAbbr"], "N/A")
        self.assertEqual(raw.loc["Russian Federation", "netWgt"], 6.54e9)
        self.assertTrue(raw.loc["Russian Federation", "isNetWgtEstimated"])
        self.assertEqual(raw.loc["World", "primaryValue"], 3.6e9)   # COMTRADE's total is kept

    def test_estimates_are_stated(self):
        query, data = self.an.assemble(self.spec, "value", self.loaded)
        self.assertEqual(list(data.estimates["Metric"]), ["Net weight"])   # the metrics analysed
        checks = dict(query.checks)
        self.assertIn("1 net weight figure", checks["Estimates in the source"])
        self.assertIn("isReported is false for 5", checks["COMTRADE record flags"])
        a = Analysis.of(query, data)
        estimated = a.estimated["netweight"]
        self.assertEqual(estimated.count, 1)
        self.assertAlmostEqual(estimated.amount, 6.54e6)
        self.assertEqual(estimated.by_period[2023], MISSING)   # the total itself is Missing
        self.assertEqual(estimated.cells("Partner_Code"), {(643, 2023)})
        self.assertNotIn("value", a.estimated)
        # The total is COMTRADE's own (partner World), not the partners added up (3,590), in
        # million USD
        self.assertTrue(np.isclose(a.period_totals["value"][2023], 3600.0))
        self.assertEqual(query.metric.unit, "million USD")
        self.assertEqual(checks["Partners add up to COMTRADE's total (partner World)"],
                         "Yes in 0 of 1 years; the largest difference is 0.3% in 2023")


def spanning_answer():
    """Milk imports reported in 2011 under HS 2007 and in 2012 under HS 2012, which replaced
    040130 with 040140 and 040150."""
    def record(period, edition, code, value):
        return {"period": str(period), "partnerCode": 250, "partnerDesc": "France",
                "partnerISO": "FRA", "cmdCode": code, "cmdDesc": f"Milk {code}",
                "primaryValue": value, "cifvalue": value, "fobvalue": None, "netWgt": value * 2,
                "grossWgt": None, "qty": value * 2, "qtyUnitCode": 8, "qtyUnitAbbr": "kg",
                "isNetWgtEstimated": False, "isGrossWgtEstimated": False,
                "isQtyEstimated": False, "isReported": True, "isAggregate": False,
                "classificationCode": edition}
    return pd.DataFrame([record(2011, "H3", "040110", 10.0), record(2011, "H3", "040130", 6.0),
                         record(2012, "H4", "040110", 12.0), record(2012, "H4", "040140", 4.0),
                         record(2012, "H4", "040150", 3.0)])


class ComtradeEditions(unittest.TestCase):
    def test_a_query_across_hs_editions_is_noted(self):
        an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        an._subscription_key = "test key"
        an.comtrade_hs_cache = {code: f"Milk {code}" for code in
                                ("0401", "040110", "040120", "040130", "040140", "040150")}
        every = ["H0", "H1", "H2", "H3", "H4", "H5", "H6"]
        an.hs_edition_cache = {"040110": every, "040120": every, "040130": every[:4],
                               "040140": every[4:], "040150": every[4:]}
        an.editions_built = True                            # never read COMTRADE's lists here
        spec = ta.Spec("COMTRADE", "A", [2011, 2012], 818, "Egypt", 818, "0401", "Milk", "M")
        api = ta.comtradeapicall
        with mock.patch.object(api, "_getFinalData", return_value=spanning_answer()), \
                mock.patch.object(api, "getFinalDataAvailability",
                                  return_value=pd.DataFrame({"period": [2011, 2012]})), \
                contextlib.redirect_stdout(io.StringIO()):
            loaded = an.load_comtrade(spec)
        self.assertEqual(loaded.editions, {2011: ["H3"], 2012: ["H4"]})
        query, data = an.assemble(spec, "value", loaded)
        self.assertEqual(query.hs_editions, {2011: "HS 2007", 2012: "HS 2012"})
        self.assertEqual(query.product_editions, {"040110": "all HS editions",
                                                  "040130": "HS 1992–2007",
                                                  "040140": "HS 2012 onwards",
                                                  "040150": "HS 2012 onwards"})
        self.assertEqual(query.edition_changes, ["040130", "040140", "040150"])
        a = Analysis.of(query, data)
        self.assertEqual(a.products.set_index("Code").loc["040130", "HS editions"],
                         "HS 1992–2007")
        text = " ".join(findings(a))
        self.assertIn("Egypt reported 2011 in HS 2007 and 2012 in HS 2012", text)
        self.assertIn("3 product codes of the 4 here are not in every one", text)
        self.assertIn("Codes are shown as reported, not converted", text)


def cement_answer():
    """Egypt's cement exports in 2020 as COMTRADE gives them: 2523 itself by partner and with
    partner World, which holds the total quantity, and its HS 6-digit products, of which
    252390 has no quantity at that level."""
    def record(code, partner, name, value, weight, estimated=False):
        unit_code, unit = (8, "kg") if weight is not None else (-1, "N/A")
        return {"period": "2020", "partnerCode": partner, "partnerDesc": name,
                "partnerISO": "", "cmdCode": code, "cmdDesc": f"Cement {code}",
                "primaryValue": value, "cifvalue": None, "fobvalue": value, "netWgt": weight,
                "grossWgt": None, "qty": 0.0 if weight is None else weight,
                "qtyUnitCode": unit_code, "qtyUnitAbbr": unit, "isNetWgtEstimated": estimated,
                "isGrossWgtEstimated": False, "isQtyEstimated": estimated, "isReported": False,
                "isAggregate": True, "classificationCode": "H5"}
    return pd.DataFrame([
        record("2523", 0, "World", 181.7e6, 3_160_054_613.0, estimated=True),
        record("2523", 400, "Jordan", 120.0e6, 2_000_000_000.0),
        record("2523", 422, "Lebanon", 61.7e6, 1_160_054_613.0, estimated=True),
        record("252329", 0, "World", 120.0e6, 2_000_000_000.0),
        record("252329", 400, "Jordan", 120.0e6, 2_000_000_000.0),
        record("252390", 0, "World", 61.7e6, None),
        record("252390", 422, "Lebanon", 61.7e6, None),
    ])


class ComtradeTotals(unittest.TestCase):
    """Totals, partners and products each come from the records COMTRADE gives for them,
    never added up from a level below where COMTRADE has its own figure."""

    def setUp(self):
        an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        an._subscription_key = "test key"
        an.comtrade_hs_cache = {code: f"Cement {code}" for code in
                                ("2523", "252329", "252390")}
        an.editions_built = True
        spec = ta.Spec("COMTRADE", "A", [2020], 818, "Egypt", 818, "2523", "Cement", "X")
        api = ta.comtradeapicall
        with mock.patch.object(api, "_getFinalData", return_value=cement_answer()), \
                mock.patch.object(api, "getFinalDataAvailability",
                                  return_value=pd.DataFrame({"period": [2020]})), \
                contextlib.redirect_stdout(io.StringIO()):
            loaded = an.load_comtrade(spec)
            self.query, self.data = an.assemble(spec, "quantity", loaded)
        self.a = Analysis.of(self.query, self.data)

    def test_the_total_is_comtrades_own(self):
        # COMTRADE's 3,160,054,613 kg: the quantity as reported, the net weight in metric tons
        self.assertEqual(self.a.period_totals["quantity"][2020], 3_160_054_613.0)
        self.assertAlmostEqual(self.a.period_totals["netweight"][2020], 3_160_054.613)
        self.assertEqual(self.query.metric.heading, "Quantity (kg)")
        self.assertEqual(self.a.summary["total"], 3_160_054_613.0)
        self.assertEqual(self.a.added_up["quantity"], [])
        self.assertAlmostEqual(self.a.period_totals["value"][2020], 181.7)   # million USD
        # Unit values stay in USD per metric ton: 181.7 million USD / 3,160,054.613 t
        self.assertAlmostEqual(self.a.unit_values[2020], 181.7e6 / 3_160_054.613)

    def test_partners_come_from_the_code_itself(self):
        partners = self.a.partner_matrix["quantity"]
        self.assertEqual(partners.loc[422, 2020], 1_160_054_613.0)        # not Missing
        self.assertAlmostEqual(self.a.partner_shares.loc[400, 2020], 2e9 / 3_160_054_613.0)

    def test_products_keep_their_own_gaps(self):
        products = self.a.product_matrix["quantity"]
        self.assertEqual(products.loc["252390", 2020], MISSING)
        self.assertEqual(products.loc["252329", 2020], 2_000_000_000.0)

    def test_checks_and_findings_state_each_level(self):
        checks = dict(self.query.checks)
        self.assertEqual(checks["Partners add up to COMTRADE's total (partner World)"],
                         "Yes in 1 of 1 years")
        self.assertEqual(checks["Products add up to COMTRADE's total for 2523"],
                         "Yes in 1 of 1 years")
        text = " ".join(findings(self.a))
        self.assertNotIn("the total for 2523", text)                   # it is not missing
        self.assertIn("1 of the 2 records of its HS 6-digit products by market (2020)", text)
        self.assertIn("COMTRADE marks its total quantity (partner World) for 2020 as an "
                      "estimate by UN Comtrade", text)
        raw = self.data.raw
        self.assertEqual(len(raw), 7)                                  # every record, as given

    def test_raw_data_keeps_comtrades_units(self):
        raw = self.data.raw.set_index(["cmdCode", "partnerDesc"])
        self.assertEqual(raw.loc[("2523", "World"), "qty"], 3_160_054_613.0)      # kg
        self.assertEqual(raw.loc[("2523", "World"), "primaryValue"], 181.7e6)    # USD


def animals_and_drinks():
    """Live animals counted in items, wine in litres, and one product with no quantity: as
    COMTRADE gives them, for a query whose products are measured in different units."""
    def record(code, partner, name, value, qty, unit_code, unit):
        return {"period": "2023", "partnerCode": partner, "partnerDesc": name,
                "partnerISO": "", "cmdCode": code, "cmdDesc": f"Product {code}",
                "primaryValue": value, "cifvalue": value, "fobvalue": None,
                "netWgt": value / 10, "grossWgt": None, "qty": qty, "qtyUnitCode": unit_code,
                "qtyUnitAbbr": unit, "isNetWgtEstimated": False, "isGrossWgtEstimated": False,
                "isQtyEstimated": False, "isReported": True, "isAggregate": False,
                "classificationCode": "H6"}
    return pd.DataFrame([
        record("010229", 76, "Brazil", 9.0e6, 4000.0, 5, "u"),
        record("010229", 0, "World", 9.0e6, 4000.0, 5, "u"),
        record("010290", 76, "Brazil", 1.0e6, 500.0, 5, "u"),
        record("220421", 250, "France", 2.0e5, 50000.0, 7, "l"),
        record("220410", 250, "France", 1.0e5, 0.0, -1, "N/A"),
    ])


class ComtradeQuantityUnits(unittest.TestCase):
    """Quantities stay in COMTRADE's units, and quantities in different units are never added:
    choosing quantity is refused, with the products that can go together."""

    def setUp(self):
        self.an = ta.TradeAnalyzer.__new__(ta.TradeAnalyzer)
        self.an._subscription_key = "test key"
        self.an.unit_name_cache = {"u": "Number of items", "l": "Volume in liters",
                                   "N/A": "Not available or not specified or no quantity"}
        self.an.comtrade_hs_cache = {"010229": "", "010290": "", "220421": "", "220410": ""}
        self.spec = ta.Spec("COMTRADE", "A", [2023], 818, "Egypt", 818, "AG6", "All",
                            "M", metric="quantity")
        self.api = ta.comtradeapicall

    def load(self):
        with mock.patch.object(self.api, "_getFinalData", return_value=animals_and_drinks()), \
                mock.patch.object(self.api, "getFinalDataAvailability",
                                  return_value=pd.DataFrame({"period": [2023]})), \
                contextlib.redirect_stdout(io.StringIO()):
            return self.an.load_comtrade(self.spec)

    def test_units_are_kept_by_product(self):
        units = self.load().quantity_units
        self.assertEqual(units["u"]["products"], ["010229", "010290"])
        self.assertEqual(units["l"]["products"], ["220421"])
        self.assertEqual(units["N/A"]["products"], ["220410"])

    def test_quantity_in_different_units_is_refused(self):
        refusal = self.an.quantity_refusal(self.load().quantity_units)
        self.assertIn("2 different units (l, u)", refusal)
        self.assertIn("u (Number of items): 010229, 010290; all the products of 0102 here are "
                      "in u", refusal)
        self.assertIn("l (Volume in liters): 220421", refusal)
        self.assertIn("N/A (no quantity reported): 220410", refusal)
        self.assertIn("choose value or net weight", refusal)
        loaded = self.load()
        with mock.patch.object(self.an, "load", return_value=loaded), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                self.an.run_spec(self.spec, Path(tempfile.mkdtemp()))

    def test_menu_shows_units_and_refuses(self):
        loaded = self.load()
        answers = iter(["QTY", "V"])
        out = io.StringIO()
        with mock.patch("builtins.input", lambda prompt="": next(answers)), \
                contextlib.redirect_stdout(out):
            chosen = self.an.get_metric_choice_comtrade(loaded.available, loaded.estimated,
                                                        loaded.quantity_units)
        self.assertEqual(chosen, "value")                   # quantity refused, then value
        text = out.getvalue()
        self.assertIn("u (Number of items): 2 records, 2 product(s)", text)   # World excluded
        self.assertIn("N/A (no quantity reported): 1 records, 1 product(s)", text)
        self.assertIn("✗ Quantities here are in 2 different units", text)

    def test_one_unit_is_used_as_reported(self):
        self.assertIsNone(self.an.quantity_refusal({"u": {"products": ["010229"]},
                                                    "N/A": {"products": ["010290"]}}))


if __name__ == "__main__":
    unittest.main()

