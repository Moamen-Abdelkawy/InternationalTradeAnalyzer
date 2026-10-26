"""Building a whole report: files, the workbook's Missing cells, estimates and HS editions."""
import contextlib
import io
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from trade_report.model import QueryData
from trade_report.report import build_report

from helpers import query, wheat_like


def build(folder, estimates=False, editions=False):
    """A report of the wheat-like rows; with estimates, Alpha's 2021 quantity is one the source
    itself estimated; with editions, 2022 is in a later HS edition that lacks code 100190."""
    rows = wheat_like()
    lacking = rows[rows["quantity"].isna()]
    gaps = pd.DataFrame({"Period": lacking["Period"], "Partner": lacking["Partner_Name"],
                         "HS code": lacking["Product_Code"], "Product": lacking["Product_Desc"],
                         "Metric": "Quantity", "Reason": "blank in the test data"})
    raw = rows.rename(columns={"value": "Value (USD)", "quantity": "Quantity (t)"})
    q = query([2020, 2021, 2022])
    data = QueryData(rows, raw, ["Value (USD)", "Quantity (t)"], gaps)
    if estimates:
        rows["quantity_estimated"] = (rows["Period"] == 2021) & (rows["Partner_Code"] == 1)
        flagged = rows[rows["quantity_estimated"]]
        data.estimates = pd.DataFrame({
            "Period": flagged["Period"], "Partner": flagged["Partner_Name"],
            "HS code": flagged["Product_Code"], "Product": flagged["Product_Desc"],
            "Metric": "Quantity", "Estimated figure": flagged["quantity"], "Unit": "t",
            "Value (USD)": flagged["value"], "Source flag": "isQtyEstimated"})
        q.estimated_by = "UN Comtrade"
        q.estimate_rules = ["A quantity the test marks as estimated."]
    if editions:
        q.hs_editions = {2020: "HS 2007", 2021: "HS 2007", 2022: "HS 2012"}
        q.product_editions = {"100110": "all HS editions", "100190": "HS 1992–2007"}
        q.edition_changes = ["100190"]
    with contextlib.redirect_stdout(io.StringIO()):
        return build_report(q, data, folder)


class Report(unittest.TestCase):
    def test_files_and_missing_cells(self):
        outputs, _ = build(Path(tempfile.mkdtemp()))
        for path in (outputs.workbook, outputs.summary, outputs.report):
            self.assertTrue(path.exists(), path)
        self.assertGreaterEqual(len(outputs.charts), 6)
        with zipfile.ZipFile(outputs.workbook) as book:
            names = re.findall(r'<sheet name="([^"]+)"', book.read("xl/workbook.xml").decode())
            strings = book.read("xl/sharedStrings.xml").decode()
        for sheet in ("About", "Summary", "Yearly", "Suppliers", "Data gaps", "Raw data"):
            self.assertIn(sheet, names)
        self.assertIn(">Missing<", strings)                 # stated, not left blank or zero
        summary = outputs.summary.read_text(encoding="utf-8")
        self.assertIn("nothing is estimated", summary)

    def test_source_estimates_are_stated_everywhere(self):
        outputs, analysis = build(Path(tempfile.mkdtemp()), estimates=True)
        self.assertEqual(analysis.period_totals["quantity"][2021], 20.0)   # used, not dropped
        with zipfile.ZipFile(outputs.workbook) as book:
            names = re.findall(r'<sheet name="([^"]+)"', book.read("xl/workbook.xml").decode())
            strings = book.read("xl/sharedStrings.xml").decode()
            styles = book.read("xl/styles.xml").decode()
        self.assertIn("Source estimates", names)
        self.assertIn("Estimates in the source", strings)
        self.assertIn("Figures in blue include estimates by UN Comtrade", strings)
        self.assertIn("Quantity: share estimated by UN Comtrade", strings)
        self.assertIn("FF2E75B6", styles)                       # the blue of estimated figures
        summary = outputs.summary.read_text(encoding="utf-8")
        self.assertIn("is an estimate by UN Comtrade", summary)
        self.assertIn("Quantity: estimated by UN Comtrade", summary)

    def test_word_main_sections_start_on_new_pages_and_pages_are_numbered(self):
        from docx import Document
        outputs, _ = build(Path(tempfile.mkdtemp()))
        breaks = {p.text.split(". ", 1)[1]: bool(p.paragraph_format.page_break_before)
                  for p in Document(str(outputs.report)).paragraphs
                  if p.style.name == "Heading 1"}
        self.assertFalse(breaks["Summary"])
        for title in ("Scope, data and method", "The trend", "Suppliers", "Year by year",
                      "Data gaps and checks"):
            self.assertTrue(breaks[title], title)
        for title in ("Shares", "Growth", "Concentration", "Products"):
            self.assertFalse(breaks[title], title)              # small: on the same page
        with zipfile.ZipFile(outputs.report) as report:
            footers = "".join(report.read(name).decode() for name in report.namelist()
                              if name.startswith("word/footer"))
        self.assertIn("PAGE", footers)
        self.assertIn("NUMPAGES", footers)

    def test_no_estimates_no_estimate_sheet(self):
        outputs, _ = build(Path(tempfile.mkdtemp()))
        with zipfile.ZipFile(outputs.workbook) as book:
            names = re.findall(r'<sheet name="([^"]+)"', book.read("xl/workbook.xml").decode())
        self.assertNotIn("Source estimates", names)

    def test_hs_editions_are_noted(self):
        outputs, analysis = build(Path(tempfile.mkdtemp()), editions=True)
        self.assertEqual(list(analysis.products.columns[:4]), ["Rank", "Code", "Name",
                                                                "HS editions"])
        with zipfile.ZipFile(outputs.workbook) as book:
            strings = book.read("xl/sharedStrings.xml").decode()
        self.assertIn("HS editions differ", strings)                 # the About sheet
        self.assertIn("2020–2021 in HS 2007 and 2022 in HS 2012", strings)
        self.assertIn("1 product code of the 2 here is not in every one", strings)
        self.assertIn("HS 1992–2007", strings)                       # the Products column


if __name__ == "__main__":
    unittest.main()
