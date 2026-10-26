"""
International Trade Analyzer

Analyses one reporter's trade in one product with all its partners, or the trade between it and
one partner country, from
  - BACI (CEPII): annual bilateral flows 1995-2024 in which the exporter's and the importer's
    reports are reconciled
  - UN COMTRADE: annual or monthly data as reported by countries, through the COMTRADE API

Each query writes a folder under output/ with an Excel workbook (the raw data, the analysis by
period and for the whole period, growth rates and CAGR), report-ready charts, a Word report and
a Markdown summary. The databases are used as they are: a value the source does not report is
shown as Missing and nothing is estimated, while figures the source itself estimated are used
as given and marked as its estimates.

Usage
    python trade_analyzer.py                         answer the questions one by one
    python trade_analyzer.py --source baci --reporter Egypt --product 1001 --flow M --period 2015-2024
    python trade_analyzer.py --source comtrade --freq M --period 202401-202412 --reporter 818 \\
                             --product 1001 --flow M --partner "Russian Federation"
    python trade_analyzer.py --batch batch_example.csv   one query per row of a CSV file
    python trade_analyzer.py --build-baci-cache      convert the BACI CSV files to Parquet, once
    python trade_analyzer.py --update-cpi            refresh the US CPI table used for constant dollars
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import functools
import os
import sys
import textwrap
import time
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq
from dotenv import load_dotenv
import comtradeapicall

from trade_report import fmt
from trade_report.analysis import MISSING, growth, is_gap, ratio
from trade_report.cpi import update_cpi
from trade_report.findings import findings
from trade_report.model import (ESTIMATE_COLUMNS, GAP_COLUMNS, HS_EDITIONS, MILLION_USD, TONS,
                                Metric, PartnerViews, Query, QueryData, edition_label,
                                editions_text, estimate_column, period_label)
from trade_report.partner.findings import findings as partner_findings, period_runs
from trade_report.report import CPI_FILE, build_report

BACI_VERSION = "V202601"
BACI_YEARS = (1995, 2024)
# Which HS editions each code exists in, built from COMTRADE's code lists
EDITIONS_FILE = Path(__file__).resolve().parent / "data" / "meta" / "hs_editions.csv"
# Copies of the BACI country and product lists, for when the BACI files are not downloaded
META_DIR = Path(__file__).resolve().parent / "data" / "meta"
# Special product codes: digits kept, description, and what one product row then stands for
SPECIAL = {"TOTAL": (0, "All products", "all products together"),
           "AG2": (2, "All products by HS chapter", "HS chapter"),
           "AG4": (4, "All products by HS heading", "HS heading"),
           "AG6": (6, "All products by HS 6-digit product", "HS 6-digit product")}
COMTRADE_MAX_RECORDS = 250_000     # the API's cap per request
COMTRADE_CODES_PER_CALL = 50       # keeps request URLs and answers within the API's limits
COMTRADE_PERIODS_PER_CALL = 12

# The analysis is in million USD and metric tons; Raw data keeps each database's own units
VALUE = Metric("value", "Value", MILLION_USD, "money")
BACI_METRICS = {"value": VALUE, "quantity": Metric("quantity", "Quantity", TONS, "volume")}
COMTRADE_METRICS = {
    "value": VALUE,
    "cif": Metric("cif", "CIF value", MILLION_USD, "money"),
    "fob": Metric("fob", "FOB value", MILLION_USD, "money"),
    "netweight": Metric("netweight", "Net weight", TONS, "volume"),
    "grossweight": Metric("grossweight", "Gross weight", TONS, "volume"),
    # Quantity stays in the unit COMTRADE gives (kg, items, litres...), and quantities in
    # different units are never added, so a query's quantity unit is known only from its data
    "quantity": Metric("quantity", "Quantity", "", "volume", unit_column="Quantity unit"),
}
COMTRADE_COLUMNS = {"value": "primaryValue", "cif": "cifvalue", "fob": "fobvalue",
                    "netweight": "netWgt", "grossweight": "grossWgt", "quantity": "qty"}
# COMTRADE's flags for figures UN Comtrade estimated rather than the country reported; they are
# part of the database, so they are used as given and marked as estimates
COMTRADE_ESTIMATED = {"netweight": "isNetWgtEstimated", "grossweight": "isGrossWgtEstimated",
                      "quantity": "isQtyEstimated"}
BACI_TYPES = {"t": pa.int16(), "i": pa.int32(), "j": pa.int32(), "k": pa.string(),
              "v": pa.float64(), "q": pa.float64()}


@dataclass
class Spec:
    """A query as asked, before any data is loaded."""
    source: str                     # 'BACI' or 'COMTRADE'
    freq: str                       # 'A' or 'M'
    periods: list[int]
    reporter_code: int              # COMTRADE numbering (BACI uses the same codes)
    reporter_name: str
    reporter_baci: int | None
    product_code: str
    product_desc: str
    flow_code: str                  # 'M' imports, 'X' exports
    partner_code: int | None = None
    partner_name: str | None = None
    partner_baci: int | None = None
    metric: str | None = None       # asked after loading for COMTRADE when None

    @property
    def flow(self) -> str:
        return "Imports" if self.flow_code == "M" else "Exports"

    def views(self) -> tuple[Spec, Spec]:
        """A partner query's other two views of the trade: the partner's trade with every
        country in the other direction (when the reporter imports, the partner's exports), and
        the reporter's trade with the partner the other way."""
        other_flow = "X" if self.flow_code == "M" else "M"
        side = replace(self, reporter_code=self.partner_code, reporter_name=self.partner_name,
                       reporter_baci=self.partner_baci, flow_code=other_flow,
                       partner_code=self.reporter_code, partner_name=self.reporter_name,
                       partner_baci=self.reporter_baci)
        return side, replace(self, flow_code=other_flow)


@dataclass
class Loaded:
    """Rows and bookkeeping from one source, ready to become a report. `rows` are the products
    by partner; COMTRADE also gives the code asked for by partner (`partner_rows`, when that
    code is not itself the product), its own totals (`total_rows`, partner World) and each
    product's totals (`product_total_rows`)."""
    rows: pd.DataFrame
    raw: pd.DataFrame
    raw_metrics: list[str]
    gaps: pd.DataFrame
    missing_periods: dict[int, str] = field(default_factory=dict)
    checks: list[tuple[str, str]] = field(default_factory=list)
    product_level: str = "HS 6-digit product"
    raw_note: str = ""
    available: dict[str, int] = field(default_factory=dict)   # metric key -> rows reporting it
    estimates: pd.DataFrame = field(                          # figures the source estimated
        default_factory=lambda: pd.DataFrame(columns=ESTIMATE_COLUMNS))
    estimated: dict[str, int] = field(default_factory=dict)   # metric key -> such figures
    editions: dict[int, list[str]] = field(default_factory=dict)  # period -> its HS editions
    partner_rows: pd.DataFrame | None = None
    total_rows: pd.DataFrame | None = None
    product_total_rows: pd.DataFrame | None = None
    # COMTRADE: quantity unit as given ('kg', 'u', 'N/A') -> its records, products, periods
    quantity_units: dict[str, dict] = field(default_factory=dict)
    # COMTRADE: the periods the reporter reported, each with its HS edition ('H6'), from
    # COMTRADE's data availability list
    reported: dict[int, str] = field(default_factory=dict)
    # A partner query's other two views of the trade (see Spec.views)
    side: Loaded | None = None
    other: Loaded | None = None
    # BACI: its totals beside the reporter's own COMTRADE totals (see check_against_comtrade)
    comtrade_check: pd.DataFrame | None = None


def parse_period(text: str, freq: str, source: str) -> list[int]:
    """'2015-2024', '2023', '202301-202312' or '202306' -> the periods, checked against the source."""
    text = str(text).strip().replace(" ", "")
    if freq == "A":
        low, high = BACI_YEARS if source == "BACI" else (1962, dt.date.today().year + 1)
        parts = text.split("-")
        if len(parts) not in (1, 2) or not all(p.isdigit() and len(p) == 4 for p in parts):
            raise ValueError("Use YYYY or YYYY-YYYY, e.g. 2023 or 2018-2023.")
        first, last = int(parts[0]), int(parts[-1])
        if first > last:
            raise ValueError("The start year must not be after the end year.")
        if not (low <= first and last <= high):
            raise ValueError(f"Years must be between {low} and {high}"
                             + (" (BACI database)." if source == "BACI" else "."))
        return list(range(first, last + 1))
    parts = text.split("-")
    if len(parts) not in (1, 2) or not all(p.isdigit() and len(p) == 6 for p in parts):
        raise ValueError("Use YYYYMM or YYYYMM-YYYYMM, e.g. 202312 or 202301-202312.")
    (y0, m0), (y1, m1) = divmod(int(parts[0]), 100), divmod(int(parts[-1]), 100)
    if not (1 <= m0 <= 12 and 1 <= m1 <= 12):
        raise ValueError("Months must be between 01 and 12.")
    if (y0, m0) > (y1, m1):
        raise ValueError("The start month must not be after the end month.")
    periods, year, month = [], y0, m0
    while (year, month) <= (y1, m1):
        periods.append(year * 100 + month)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return periods


def chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def agreement(parts: pd.Series, whole: pd.Series, word: str, monthly: bool) -> str:
    """Whether parts add up to their whole, period by period: 'Yes in 3 of 3 years', and how
    far apart they are where they do not."""
    differences = ((parts - whole).abs() / whole).replace(np.inf, np.nan).dropna()
    ok = int((differences < 0.001).sum())
    text = f"Yes in {ok} of {len(differences)} {word}s"
    if len(differences) and ok < len(differences):
        worst = differences.idxmax()
        text += (f"; the largest difference is {differences.max():.1%} in "
                 f"{period_label(worst, monthly)}")
    return text


class TradeAnalyzer:
    """Loads a query from BACI or COMTRADE and builds its report."""
    hs_edition_cache = None     # code -> HS editions, read from EDITIONS_FILE when first needed
    editions_built = False      # the edition table is built from COMTRADE at most once a run
    unit_name_cache = None      # COMTRADE's quantity units: abbreviation -> description

    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.baci_dir = self.base_dir / "data" / "BACI" / f"BACI_HS92_{BACI_VERSION}"
        self.cache_dir = self.baci_dir / "parquet"
        self.baci_country_codes = None
        self.baci_product_codes = None
        self._subscription_key = None
        self.comtrade_reporter_cache = None
        self.comtrade_partner_cache = None
        self.comtrade_hs92_cache = None
        self.comtrade_hs_cache = None
        self.load_baci_reference_data()
        print("✓ Trade analyzer initialized\n")

    # -- set-up -----------------------------------------------------------------------
    @property
    def subscription_key(self):
        """The UN COMTRADE API key, read when COMTRADE data is first needed."""
        if self._subscription_key is None:
            env_path = self.base_dir / "SUBSCRIPTION_KEY.env"
            if not env_path.exists():
                raise FileNotFoundError(
                    f"SUBSCRIPTION_KEY.env file not found at {env_path}\n"
                    "Please create this file with your PRIMARY_KEY")
            load_dotenv(env_path)
            key = os.getenv("PRIMARY_KEY")
            if not key:
                raise ValueError("PRIMARY_KEY not found in SUBSCRIPTION_KEY.env file")
            self._subscription_key = key
        return self._subscription_key

    def load_baci_reference_data(self):
        """Load BACI country and product code mappings: from the BACI folder, or from their
        copies in data/meta when the BACI files are not downloaded, since COMTRADE queries
        use the country list too."""
        folder = (self.baci_dir if (self.baci_dir / f"country_codes_{BACI_VERSION}.csv").exists()
                  else META_DIR)
        try:
            self.baci_country_codes = pd.read_csv(folder / f"country_codes_{BACI_VERSION}.csv",
                                                  keep_default_na=False)
            # CEPII's file stores some names double-encoded ("TÃ¼rkiye"), so decode them back
            self.baci_country_codes['country_name'] = self.baci_country_codes['country_name'].apply(
                self.fix_double_encoding)
            # Read product codes as text so leading zeros survive ("010111", not 10111)
            self.baci_product_codes = pd.read_csv(
                folder / f"product_codes_HS92_{BACI_VERSION}.csv", dtype={'code': str})
            self.baci_product_codes['code'] = self.baci_product_codes['code'].str.zfill(6)
            print("✓ BACI reference data loaded\n")
        except Exception as e:
            print(f"⚠ Warning: Could not load BACI reference data: {e}")
            print("  BACI data will not be available\n")

    def fix_double_encoding(self, text):
        """Repair text that was UTF-8 encoded twice (e.g., "TÃ¼rkiye" -> "Türkiye")"""
        try:
            return text.encode('latin-1').decode('utf-8')
        except (UnicodeError, AttributeError):
            # Correctly encoded text fails one of the two steps and is kept as is
            return text

    def comtrade_reference(self, role):
        """COMTRADE's reporter or partner list (code, name)."""
        if self.comtrade_reporter_cache is None:
            print("\nLoading COMTRADE country lists...")
            self.comtrade_reporter_cache = comtradeapicall.getReference('reporter')
            self.comtrade_partner_cache = comtradeapicall.getReference('partner')
        return self.comtrade_reporter_cache if role == "reporter" else self.comtrade_partner_cache

    def hs_descriptions(self, source) -> dict[str, str]:
        """Code -> description of every HS chapter, heading and subheading: the HS 1992 edition
        for BACI, every edition for COMTRADE (whose reporters use the edition of their year)."""
        attribute = "comtrade_hs92_cache" if source == "BACI" else "comtrade_hs_cache"
        if getattr(self, attribute) is None:
            try:
                reference = comtradeapicall.getReference("cmd:H0" if source == "BACI" else "cmd:HS")
                # Texts look like "0401 - Milk and cream, ..." or "100110 - -  Durum wheat"
                text = reference["text"].str.split(" - ", n=1).str[1].fillna("")
                text = (text.str.replace(r"^[-\s]+", "", regex=True).str.split().str.join(" ")
                        .str.rstrip("."))
                setattr(self, attribute, dict(zip(reference["id"].astype(str), text)))
            except Exception as err:
                print(f"  ⚠ Warning: could not load HS descriptions from COMTRADE: {err}")
                return {}
        return getattr(self, attribute)

    def hs_editions(self, needed=()) -> dict[str, list[str]]:
        """HS code -> the HS editions it exists in ('H0' is HS 1992 ... 'H6' HS 2022), from
        data/meta/hs_editions.csv. The table is built from COMTRADE's code lists when the file
        is missing or lacks an edition the data uses; it is empty when that fails."""
        if self.hs_edition_cache is None and EDITIONS_FILE.exists():
            with open(EDITIONS_FILE, newline="", encoding="utf-8") as handle:
                self.hs_edition_cache = {row["code"]: row["editions"].split()
                                         for row in csv.DictReader(handle)}
        known = {e for editions in (self.hs_edition_cache or {}).values() for e in editions}
        if (self.hs_edition_cache is None or not set(needed) <= known) and not self.editions_built:
            self.editions_built = True
            self.hs_edition_cache = self.build_hs_editions() or self.hs_edition_cache
        return self.hs_edition_cache or {}

    def build_hs_editions(self) -> dict[str, list[str]]:
        """Read every HS edition's code list from COMTRADE and save which codes each has."""
        print("\nBuilding the table of HS editions from COMTRADE's code lists (once)...")
        try:
            categories = comtradeapicall.listReference()["category"].astype(str)
            editions = sorted((c.split(":", 1)[1] for c in categories
                               if c.startswith("cmd:H") and c[5:].isdigit()),
                              key=lambda e: HS_EDITIONS.get(e, 9999))
            table = {}
            for edition in editions:
                codes = comtradeapicall.getReference(f"cmd:{edition}")["id"].astype(str)
                for code in codes[codes.str.isdigit()]:
                    table.setdefault(code, []).append(edition)
        except Exception as err:
            print(f"  ⚠ Could not read the HS edition lists from COMTRADE: {err}")
            return {}
        EDITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(EDITIONS_FILE, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["code", "editions"])
            for code in sorted(table):
                writer.writerow([code, " ".join(table[code])])
        print(f"  ✓ {len(table):,} codes in {len(editions)} editions, saved to "
              f"{EDITIONS_FILE.name}")
        return table

    def unit_names(self) -> dict[str, str]:
        """COMTRADE's quantity units, abbreviation -> description: 'u' -> 'Number of items'."""
        if self.unit_name_cache is None:
            try:
                units = comtradeapicall.getReference("qtyunit")
                self.unit_name_cache = dict(zip(units["qtyAbbr"].astype(str),
                                                units["qtyDescription"].astype(str).str.rstrip(".")))
            except Exception as err:
                print(f"  ⚠ Could not read COMTRADE's list of quantity units: {err}")
                self.unit_name_cache = {}
        return self.unit_name_cache

    def quantity_refusal(self, units: dict[str, dict]) -> str | None:
        """Why quantity cannot be the metric when the products are measured in different units,
        and which products can be analysed by quantity together; None when it can."""
        real = {unit: info for unit, info in units.items() if unit != "N/A"}
        if len(real) <= 1:
            return None
        names = self.unit_names()

        def listed(products):
            return ", ".join(products[:12]) + (f" and {len(products) - 12} more"
                                               if len(products) > 12 else "")

        lines = [f"Quantities here are in {len(real)} different units ({', '.join(real)}), and "
                 "quantities in different units are never added together. Products in the same "
                 "unit can be analysed by quantity together, in a query of their own:"]
        for unit, info in real.items():
            # Headings or chapters whose products here are all in this unit
            others = {p for u, i in real.items() if u != unit for p in i["products"]}
            groups = sorted({p[:-2] for p in info["products"] if len(p) > 2}
                            - {o[:-2] for o in others})
            lines.append(f"  {unit} ({names.get(unit, 'as COMTRADE gives it')}): "
                         f"{listed(info['products'])}"
                         + (f"; all the products of {', '.join(groups)} here are in {unit}"
                            if groups else ""))
        if "N/A" in units:
            lines.append(f"  N/A (no quantity reported): {listed(units['N/A']['products'])}")
        lines.append("Or choose value or net weight, which can be added across all these "
                     "products.")
        return "\n".join(lines)

    def edition_tags(self, codes) -> dict[str, str]:
        """Code -> the HS editions it exists in, as text; empty without the edition table."""
        table = self.hs_editions()
        known = {e for editions in table.values() for e in editions}
        return {code: editions_text(table.get(code, []), known) for code in codes} if table else {}

    def product_description(self, code: str, source: str) -> str:
        if code in SPECIAL:
            return SPECIAL[code][1]
        if source == "BACI" and len(code) == 6 and self.baci_product_codes is not None:
            match = self.baci_product_codes[self.baci_product_codes["code"] == code]
            if not match.empty:
                return match.iloc[0]["description"]
        return self.hs_descriptions(source).get(code, f"HS {code}")

    def normalize_hs_code(self, code):
        """Return an HS code as text, restoring a leading zero that was dropped.

        HS codes have 2, 4 or 6 digits and chapters 01-09 start with a zero,
        which integer parsing and spreadsheets drop (040110 becomes 40110).
        """
        code = str(code).strip()
        if len(code) in (1, 3, 5) and code.isdigit() and not code.startswith('0'):
            return '0' + code
        return code

    # -- questions --------------------------------------------------------------------
    def get_frequency_input(self):
        """Get frequency (Annual or Monthly) from user"""
        while True:
            print("\n" + "="*60)
            print("DATA FREQUENCY")
            print("="*60)
            print("Select the frequency of data for analysis.")
            print("")
            print("VALID INPUTS:")
            print("  A  or  Annual   :  Yearly data")
            print("  M  or  Monthly  :  Monthly data (COMTRADE only)")
            print("")
            freq = input("Enter frequency: ").strip().upper()
            if freq in ['A', 'ANNUAL']:
                return 'A'
            elif freq in ['M', 'MONTHLY']:
                return 'M'
            else:
                print("✗ Invalid input. Please enter A (Annual) or M (Monthly).")

    def get_data_source_input(self, freq_code):
        """Get data source selection from user"""
        if freq_code == 'M':
            print("\n" + "="*60)
            print("DATA SOURCE")
            print("="*60)
            print("Monthly data is only available via COMTRADE API.")
            print("BACI database contains annual data only.")
            print("")
            return 'COMTRADE'

        while True:
            print("\n" + "="*60)
            print("DATA SOURCE")
            print("="*60)
            print("Select the data source for analysis.")
            print("")
            print("VALID INPUTS:")
            print("  B  or  BACI      :  BACI database (1995-2024, harmonized)")
            print("  C  or  COMTRADE  :  UN COMTRADE API (as reported by countries)")
            print("")
            print("NOTE:")
            print("  BACI provides reconciled bilateral trade flows where")
            print("  discrepancies between exporter and importer reports are harmonized.")
            print("  COMTRADE provides data as reported by individual countries.")
            print("")
            source = input("Enter data source: ").strip().upper()
            if source in ['B', 'BACI']:
                return 'BACI'
            elif source in ['C', 'COMTRADE']:
                return 'COMTRADE'
            else:
                print("✗ Invalid input. Please enter B (BACI) or C (COMTRADE).")

    def get_period_input(self, freq_code, data_source):
        """Get and validate period input from user"""
        while True:
            print("\n" + "="*60)
            print("PERIOD SELECTION")
            print("="*60)
            if freq_code == 'A':
                print("Enter the year or range for analysis.")
                print("")
                print("FORMAT:")
                print("  Single year    :  YYYY        (e.g., 2023)")
                print("  Year range     :  YYYY-YYYY   (e.g., 2018-2023)")
                print("")
                if data_source == 'BACI':
                    print(f"VALID RANGE: {BACI_YEARS[0]}-{BACI_YEARS[1]} (BACI database)")
                else:
                    print("VALID RANGE: 1962-Present (COMTRADE API)")
                    print("NOTE: Data availability depends on reporting by the selected country.")
                print("")
                text = input("Enter year(s): ")
            else:
                print("Enter the month or range for analysis.")
                print("")
                print("FORMAT:")
                print("  Single month   :  YYYYMM         (e.g., 202312 for December 2023)")
                print("  Month range    :  YYYYMM-YYYYMM  (e.g., 202301-202312)")
                print("")
                print("DATA SOURCE: COMTRADE API (monthly data)")
                print("")
                text = input("Enter period(s): ")
            try:
                periods = parse_period(text, freq_code, data_source)
            except ValueError as err:
                print(f"✗ Error: {err}")
                continue
            word = "years" if freq_code == "A" else "months"
            print(f"✓ Period: {period_label(periods[0], freq_code == 'M', True)} to "
                  f"{period_label(periods[-1], freq_code == 'M', True)} ({len(periods)} {word})")
            return periods

    def get_country_input(self, role="reporter"):
        """Get and validate country input - checks both BACI and COMTRADE"""
        comtrade_cache = self.comtrade_reference(role)

        while True:
            print("\n" + "="*60)
            print(f"{role.upper()} COUNTRY SELECTION")
            print("="*60)
            print(f"Enter the {role} country by name or numeric code.")
            print("")
            print("VALID INPUTS:")
            print("  Country name     :  e.g., Egypt, United States, China")
            print("  Country code     :  e.g., 818 (Egypt), 842 (USA), 156 (China)")
            print("")
            print("REFERENCE: Country codes can be found in data/meta/country_codes_V202601.csv")
            print("")
            country_input = input(f"Enter {role} country: ").strip()

            try:
                country_code = int(country_input)

                comtrade_match = comtrade_cache[comtrade_cache['id'] == country_code]
                comtrade_name = comtrade_match.iloc[0]['text'] if not comtrade_match.empty else None
                baci_match = self.baci_country_codes[self.baci_country_codes['country_code'] == country_code]
                baci_name = baci_match.iloc[0]['country_name'] if not baci_match.empty else None

                if comtrade_name or baci_name:
                    if comtrade_name and baci_name:
                        if comtrade_name.lower() == baci_name.lower():
                            print(f"✓ Country found: {comtrade_name} (Code: {country_code})")
                            print("  Available in both BACI and COMTRADE")
                        else:
                            print(f"✓ Country found (Code: {country_code}):")
                            print(f"  COMTRADE: {comtrade_name}")
                            print(f"  BACI: {baci_name}")
                    elif comtrade_name:
                        print(f"✓ Country found: {comtrade_name} (Code: {country_code})")
                        print("  Available in COMTRADE only")
                    else:
                        print(f"✓ Country found: {baci_name} (Code: {country_code})")
                        print("  Available in BACI only")

                    confirm = input("Confirm selection (Y/N): ").strip().upper()
                    if confirm in ['Y', 'YES']:
                        final_name = comtrade_name or baci_name
                        baci_code = int(baci_match.iloc[0]['country_code']) if not baci_match.empty else None
                        return country_code, final_name, baci_code
                else:
                    print(f"✗ Country code {country_code} not found in either database.")

            except ValueError:
                comtrade_matches = comtrade_cache[
                    comtrade_cache['text'].str.contains(country_input, case=False, na=False, regex=False)]
                baci_matches = self.baci_country_codes[
                    self.baci_country_codes['country_name'].str.contains(country_input, case=False,
                                                                         na=False, regex=False)]

                if len(comtrade_matches) == 1 and len(baci_matches) <= 1:
                    comtrade_code = int(comtrade_matches.iloc[0]['id'])
                    comtrade_name = comtrade_matches.iloc[0]['text']
                    baci_code = int(baci_matches.iloc[0]['country_code']) if not baci_matches.empty else None
                    baci_name = baci_matches.iloc[0]['country_name'] if not baci_matches.empty else None

                    if baci_name and comtrade_name.lower() != baci_name.lower():
                        print("✓ Country found:")
                        print(f"  COMTRADE: {comtrade_name} (Code: {comtrade_code})")
                        print(f"  BACI: {baci_name} (Code: {baci_code})")
                    else:
                        print(f"✓ Country found: {comtrade_name} (Code: {comtrade_code})")

                    confirm = input("Confirm selection (Y/N): ").strip().upper()
                    if confirm in ['Y', 'YES']:
                        return comtrade_code, comtrade_name, baci_code

                elif len(comtrade_matches) == 0 and len(baci_matches) == 0:
                    print(f"✗ Error: No country found matching '{country_input}'")
                    all_country_names = set(comtrade_cache['text'].dropna())
                    all_country_names |= set(self.baci_country_codes['country_name'].dropna())
                    similar = difflib.get_close_matches(country_input, list(all_country_names),
                                                        n=5, cutoff=0.6)
                    if similar:
                        print("\nDid you mean one of these?")
                        for suggestion in similar:
                            print(f"  - {suggestion}")
                        print("")
                else:
                    print(f"Multiple countries found matching '{country_input}':")
                    matches = pd.concat([
                        comtrade_matches[['id', 'text']].rename(columns={'id': 'code', 'text': 'name'}),
                        baci_matches[['country_code', 'country_name']].rename(
                            columns={'country_code': 'code', 'country_name': 'name'})]).drop_duplicates()
                    for _, row in matches.head(10).iterrows():
                        print(f"  {row['code']}: {row['name']}")
                    print("\nPlease enter a more specific name or use the country code.")

    def subcategories(self, code: str, source: str) -> pd.DataFrame:
        """The HS 6-digit products under a chapter or heading, from the source's own list."""
        if source == "BACI":
            ref = self.baci_product_codes
        else:
            ref = pd.DataFrame([(c, d) for c, d in self.hs_descriptions("COMTRADE").items()
                                if len(c) == 6], columns=["code", "description"])
        return ref[ref["code"].str.startswith(code) & (ref["code"].str.len() > len(code))]

    def get_product_input(self, source):
        """Get and validate product code input with subcategory details"""
        while True:
            print("\n" + "="*60)
            print("PRODUCT SELECTION")
            print("="*60)
            print("Enter the HS (Harmonized System) product code.")
            print("")
            print("VALID INPUTS:")
            print("  2-digit chapter     :  e.g., 10 (Cereals)")
            print("  4-digit heading     :  e.g., 1001 (Wheat)")
            print("  6-digit subheading  :  e.g., 100190 (Wheat, other)")
            print("")
            print("SPECIAL CODES:")
            print("  TOTAL  :  All products combined")
            print("  AG2    :  All 2-digit chapters")
            print("  AG4    :  All 4-digit headings")
            print("  AG6    :  All 6-digit subheadings")
            print("")
            print("REFERENCE: Product codes can be found in data/meta/product_codes_HS92_V202601.csv")
            print("")
            product_input = input("Enter product code: ").strip().upper()

            if not product_input:
                print("✗ Error: Product code cannot be empty")
                continue
            if product_input in SPECIAL:
                return product_input, SPECIAL[product_input][1]

            # Keep leading zeros: without them, 0401 (milk and cream) would also match 4010-4017 (rubber)
            normalized_input = self.normalize_hs_code(product_input)
            if normalized_input != product_input:
                print(f"⚠ Interpreting '{product_input}' as {normalized_input} (HS codes have 2, 4 or 6 digits)")
                product_input = normalized_input

            description = self.product_description(product_input, source)
            children = self.subcategories(product_input, source)
            if len(children):
                print(f"\n⚠ Product code '{product_input}' ({description}) has {len(children)} subcategories:")
                print("="*60)
                # The end of a description is what sets a code apart from its siblings; for
                # COMTRADE, the HS editions each code exists in are shown in brackets
                tags = self.edition_tags(children["code"]) if source == "COMTRADE" else {}
                for _, row in children.head(20).iterrows():
                    text = str(row["description"]).rsplit("; ", 1)[-1]
                    tag = f"  [{tags[row['code']]}]" if row["code"] in tags else ""
                    print(f"  {row['code']}: {fmt.short_end(text[:1].upper() + text[1:], 72)}{tag}")
                if len(children) > 20:
                    print(f"  ... and {len(children) - 20} more")
                print("="*60)
                if source == "BACI":
                    print("\nThese are HS 1992 codes: BACI converts every year to the 1992 edition.")
                elif any(tag != "all HS editions" for tag in tags.values()):
                    print("\nCOMTRADE keeps each country's data in the HS edition it reported in, so")
                    print("a code that is not in every edition appears only in the years reported")
                    print("in the editions shown in brackets.")
                print("The analysis covers every subcategory, product by product.")
            elif description.startswith("HS "):
                print(f"✓ Using product code: {product_input}")
                print("  (Code not found in the HS reference lists)")
            else:
                print(f"✓ Product: {product_input} - {description}")
            confirm = input("Confirm selection (Y/N): ").strip().upper()
            if confirm in ['Y', 'YES']:
                return product_input, description
            print("Please enter a different code.")

    def get_trade_direction(self):
        """Get trade direction from user"""
        while True:
            print("\n" + "="*60)
            print("TRADE DIRECTION")
            print("="*60)
            print("Select the trade flow direction for analysis.")
            print("")
            print("VALID INPUTS:")
            print("  M  or  Imports  :  Goods imported by the reporter country")
            print("  X  or  Exports  :  Goods exported by the reporter country")
            print("")
            direction = input("Enter trade direction: ").strip().upper()
            if direction in ['M', 'IMPORTS', 'IMPORT']:
                return 'M'
            elif direction in ['X', 'EXPORTS', 'EXPORT']:
                return 'X'
            else:
                print("✗ Invalid input. Please enter M (Imports) or X (Exports).")

    def get_partner_choice(self):
        """Get partner analysis choice from user: (code, name, BACI code) or Nones for all"""
        while True:
            print("\n" + "="*60)
            print("PARTNER SELECTION")
            print("="*60)
            print("Select the type of partner analysis.")
            print("")
            print("VALID INPUTS:")
            print("  A  or  All       :  Analyze trade with all partners (world total)")
            print("  S  or  Specific  :  A report on the trade with one partner country")
            print("")
            choice = input("Enter choice: ").strip().upper()
            if choice in ['A', 'ALL']:
                return None, None, None
            elif choice in ['S', 'SPECIFIC']:
                return self.get_country_input("partner")
            else:
                print("✗ Invalid input. Please enter A (All) or S (Specific).")

    def get_metric_choice_baci(self):
        """Get metric choice for BACI data (only Value and Quantity available)"""
        while True:
            print("\n" + "="*60)
            print("METRIC SELECTION (BACI)")
            print("="*60)
            print("Select the metric to rank trading partners.")
            print("")
            print("VALID INPUTS:")
            print("  V  or  Value     :  Trade value in million USD")
            print("  Q  or  Quantity  :  Quantity in metric tons")
            print("")
            print("NOTE: The selected metric is used to rank partners and measure growth.")
            print("      Value and quantity are both in the workbook either way.")
            print("")
            print("WARNING: BACI leaves the quantity blank for some flows. Those quantities")
            print("         are shown as Missing, and so is everything computed from them.")
            print("")
            choice = input("Enter metric: ").strip().upper()
            if choice in ['V', 'VALUE']:
                return 'value'
            elif choice in ['Q', 'QUANTITY']:
                return 'quantity'
            else:
                print("✗ Invalid input. Please enter V (Value) or Q (Quantity).")

    def get_metric_choice_comtrade(self, available, estimated=None, units=None):
        """Get metric choice for COMTRADE data based on the metrics the answer carries; the
        quantity is shown unit by unit, and refused when its units differ"""
        shortcuts = {"value": "V", "cif": "CIF", "fob": "FOB", "netweight": "NW",
                     "grossweight": "GW", "quantity": "QTY"}
        estimated, units = estimated or {}, units or {}
        names = self.unit_names() if units else {}
        options = [key for key in COMTRADE_METRICS if available.get(key, 0) > 0]
        if not options:
            print("  ⚠ The COMTRADE answer reports no metric at all; using value (all Missing).")
            return "value"
        while True:
            print("\n" + "="*60)
            print("METRIC SELECTION (COMTRADE)")
            print("="*60)
            print("Select the metric to rank trading partners.")
            print("")
            print("AVAILABLE METRICS FROM API RESPONSE:")
            choices = {}
            for number_, key in enumerate(options, start=1):
                metric = COMTRADE_METRICS[key]
                flagged = (f", {estimated[key]:,} of them estimated by UN Comtrade"
                           if estimated.get(key) else "")
                heading = ("Quantity, in the unit COMTRADE gives" if key == "quantity"
                           else metric.heading)
                print(f"  {number_}  or  {shortcuts[key]:4s}:  {heading} "
                      f"({available[key]:,} records{flagged})")
                if key == "quantity":
                    for unit, info in units.items():
                        name = ("no quantity reported" if unit == "N/A"
                                else names.get(unit, "as COMTRADE gives it"))
                        print(f"{'':16s}{unit} ({name}): {info['records']:,} records, "
                              f"{len(info['products'])} product(s)")
                choices[str(number_)] = choices[shortcuts[key]] = key
            if "quantity" not in options and units:
                print(f"  {'':10s}Quantity: not available; COMTRADE reports none "
                      f"(N/A in {sum(i['records'] for i in units.values()):,} records)")
            print("")
            print("NOTE: The selected metric is used to rank partners and measure growth.")
            print("      Every metric is in the workbook's Raw data sheet.")
            print("      Quantities in different units are never added together.")
            if any(estimated.get(key) for key in options):
                print("      Figures UN Comtrade estimated are used as COMTRADE gives them and")
                print("      marked as estimates in every output.")
            print("")
            choice = input("Enter metric: ").strip().upper()
            if choice in choices:
                refusal = (self.quantity_refusal(units) if choices[choice] == "quantity"
                           else None)
                if refusal is None:
                    return choices[choice]
                print("\n✗ " + refusal)
                continue
            print("✗ Invalid input. Please enter a valid metric number or code.")

    def ask_yes_no(self, question) -> bool:
        while True:
            answer = input(f"{question} (Y/N): ").strip().upper()
            if answer in ("Y", "YES"):
                return True
            if answer in ("N", "NO"):
                return False
            print("✗ Please enter Y or N.")

    def ask_query(self) -> Spec:
        freq = self.get_frequency_input()
        source = self.get_data_source_input(freq)
        periods = self.get_period_input(freq, source)
        reporter_code, reporter_name, reporter_baci = self.get_country_input("reporter")
        product_code, product_desc = self.get_product_input(source)
        flow_code = self.get_trade_direction()
        partner_code, partner_name, partner_baci = self.get_partner_choice()
        metric = self.get_metric_choice_baci() if source == "BACI" else None
        return Spec(source, freq, periods, reporter_code, reporter_name, reporter_baci,
                    product_code, product_desc, flow_code, partner_code, partner_name,
                    partner_baci, metric)

    # -- the command line ----------------------------------------------------------------
    def resolve_country(self, text, role):
        """A country given by code or name, without asking: (code, name, BACI code)."""
        text = str(text or "").strip()
        if not text:
            raise ValueError(f"No {role} given.")
        comtrade = self.comtrade_reference(role)
        baci = self.baci_country_codes
        if text.isdigit():
            code = int(text)
            names = comtrade.loc[comtrade["id"] == code, "text"].tolist()
            baci_rows = baci[baci["country_code"] == code]
            if not names and baci_rows.empty:
                raise ValueError(f"Country code {code} is in neither COMTRADE nor BACI.")
            name = names[0] if names else baci_rows.iloc[0]["country_name"]
            return code, name, (code if not baci_rows.empty else None)
        lowered = text.casefold()
        candidates = {}
        for code, name in zip(comtrade["id"], comtrade["text"]):
            candidates.setdefault(int(code), name)
        for code, name in zip(baci["country_code"], baci["country_name"]):
            candidates.setdefault(int(code), name)
        exact = {c: n for c, n in candidates.items() if str(n).casefold() == lowered}
        partial = exact or {c: n for c, n in candidates.items() if lowered in str(n).casefold()}
        if len(partial) != 1:
            listed = "; ".join(f"{c} {n}" for c, n in list(partial.items())[:8])
            raise ValueError(f"'{text}' matches {len(partial)} countries"
                             + (f": {listed}. Use the code." if partial else "."))
        code, name = next(iter(partial.items()))
        return code, name, (code if (baci["country_code"] == code).any() else None)

    def spec_from_values(self, values: dict) -> Spec:
        """A query from command-line options or a batch row."""
        source = (values.get("source") or "").strip().upper()
        if source not in ("BACI", "COMTRADE"):
            raise ValueError("source must be baci or comtrade")
        freq = (values.get("freq") or "A").strip().upper()[:1]
        if freq not in ("A", "M"):
            raise ValueError("freq must be A (annual) or M (monthly)")
        if freq == "M" and source == "BACI":
            raise ValueError("BACI holds annual data only; use freq A or source comtrade")
        periods = parse_period(values.get("period") or "", freq, source)
        reporter = self.resolve_country(values.get("reporter"), "reporter")
        partner_text = (values.get("partner") or "").strip()
        partner = (self.resolve_country(partner_text, "partner")
                   if partner_text and partner_text.casefold() not in ("all", "world", "0")
                   else (None, None, None))
        product = (values.get("product") or "").strip().upper()
        if not product:
            raise ValueError("No product given")
        product = product if product in SPECIAL else self.normalize_hs_code(product)
        flow = (values.get("flow") or "").strip().upper()
        flow = {"M": "M", "IMPORTS": "M", "IMPORT": "M", "X": "X", "EXPORTS": "X",
                "EXPORT": "X"}.get(flow)
        if not flow:
            raise ValueError("flow must be M (imports) or X (exports)")
        metric = (values.get("metric") or "value").strip().lower()
        allowed = BACI_METRICS if source == "BACI" else COMTRADE_METRICS
        if metric not in allowed:
            raise ValueError(f"metric must be one of: {', '.join(allowed)}")
        if source == "BACI" and reporter[2] is None:
            raise ValueError(f"{reporter[1]} is not in BACI")
        return Spec(source, freq, periods, reporter[0], reporter[1], reporter[2], product,
                    self.product_description(product, source), flow, partner[0], partner[1],
                    partner[2], metric)

    # -- BACI ---------------------------------------------------------------------------
    def read_baci_year(self, year, conditions) -> pa.Table | None:
        """One year of BACI rows matching any of the conditions, each a list of (column, code)
        pairs that must all hold; i is the exporter and j the importer, so [[("j", 818)]] is
        everything Egypt imports."""
        cached = self.cache_dir / f"BACI_HS92_Y{year}_{BACI_VERSION}.parquet"
        if cached.exists():
            return pq.read_table(cached, filters=[[(column, "=", int(code))
                                                   for column, code in condition]
                                                  for condition in conditions])
        source = self.baci_dir / f"BACI_HS92_Y{year}_{BACI_VERSION}.csv"
        if not source.exists():
            return None
        reader = pa_csv.open_csv(source,
                                 convert_options=pa_csv.ConvertOptions(column_types=BACI_TYPES),
                                 read_options=pa_csv.ReadOptions(block_size=32 << 20))

        def matching(batch):
            return functools.reduce(pc.or_, [
                functools.reduce(pc.and_, [pc.equal(batch.column(column), int(code))
                                           for column, code in condition])
                for condition in conditions])

        batches = [batch.filter(matching(batch)) for batch in reader]
        return pa.Table.from_batches([b for b in batches if b.num_rows], schema=reader.schema)

    def build_baci_cache(self):
        """Convert every BACI year from CSV to Parquet once; later queries read it in a blink."""
        files = sorted(self.baci_dir.glob(f"BACI_HS92_Y*_{BACI_VERSION}.csv"))
        if not files:
            print(f"✗ No BACI CSV files in {self.baci_dir}")
            return
        self.cache_dir.mkdir(exist_ok=True)
        print(f"Converting {len(files)} BACI files to Parquet in {self.cache_dir}")
        print("(about 5 seconds and 100 MB per year)\n")
        for source in files:
            target = self.cache_dir / f"{source.stem}.parquet"
            if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
                print(f"  {source.name}: already converted")
                continue
            started = time.perf_counter()
            table = pa_csv.read_csv(source, convert_options=pa_csv.ConvertOptions(
                column_types=BACI_TYPES))
            table = table.sort_by([("i", "ascending"), ("j", "ascending")])
            temporary = target.with_suffix(".tmp")
            pq.write_table(table, temporary, compression="zstd", row_group_size=250_000)
            temporary.replace(target)
            print(f"  {source.name}: {table.num_rows:,} rows, "
                  f"{target.stat().st_size / 1e6:,.0f} MB, {time.perf_counter() - started:.1f}s")
        print("\n✓ BACI cache ready; queries now read it instead of the CSV files.")

    def load_baci(self, spec: Spec) -> Loaded:
        """BACI rows for one reporter, product and direction. A quantity BACI leaves blank
        stays empty (Missing); when rows are summed, the sum is Missing if any part is. For a
        partner query, the same pass over each year also reads the partner's trade with every
        country in the other direction and the reporter's trade with the partner the other way
        (see Spec.views)."""
        if spec.reporter_baci is None:
            print(f"\n✗ {spec.reporter_name} is not in BACI; use COMTRADE for this reporter.")
            return None
        if spec.partner_name and spec.partner_baci is None:
            print(f"  ⚠ {spec.partner_name} is not in BACI, so there is no partner report; the "
                  "report covers all partners.")
        country_col, partner_col = ("j", "i") if spec.flow_code == "M" else ("i", "j")
        # The rows of each view: (column, country) pairs that must all hold
        views = {"main": [(country_col, spec.reporter_baci)]}
        if spec.partner_baci is not None:
            views["side"] = [(partner_col, spec.partner_baci)]
            views["other"] = [(partner_col, spec.reporter_baci), (country_col, spec.partner_baci)]
        digits = SPECIAL[spec.product_code][0] if spec.product_code in SPECIAL else None
        reading = "the Parquet cache" if self.cache_dir.exists() else "the CSV files"
        print(f"\nLoading BACI data for {len(spec.periods)} year(s) from {reading}...")
        pieces = {view: [] for view in views}
        source_rows = dict.fromkeys(views, 0)
        missing = {}
        for year in spec.periods:
            print(f"  Loading {year}...", end=" ", flush=True)
            table = self.read_baci_year(year, list(views.values()))
            if table is None:
                missing[year] = f"the BACI file for {year} is not in {self.baci_dir.name}"
                print("✗ file not found")
                continue
            read = table.to_pandas()
            read["k"] = read["k"].str.zfill(6)
            for view, condition in views.items():
                frame = read if len(views) == 1 else read[functools.reduce(
                    np.logical_and, [read[column].to_numpy() == code
                                     for column, code in condition])]
                if digits is None:
                    frame = frame[frame["k"].str.startswith(spec.product_code)]
                source_rows[view] += len(frame)
                if digits is not None and digits < 6:
                    frame = self.sum_baci(frame, digits)
                pieces[view].append(frame)
            print(f"✓ {len(pieces['main'][-1]):,} rows")
        print(f"  ✓ Total: {source_rows['main']:,} BACI rows")
        loaded = self.baci_loaded(spec.product_code, pieces["main"], partner_col,
                                  source_rows["main"], missing)
        if len(views) > 1:
            # Both other views have the partner's partner in the reporter's column
            loaded.side = self.baci_loaded(spec.product_code, pieces["side"], country_col,
                                           source_rows["side"], missing)
            loaded.other = self.baci_loaded(spec.product_code, pieces["other"], country_col,
                                            source_rows["other"], missing)
        return loaded

    def baci_loaded(self, product_code, pieces, partner_col, source_rows, missing) -> Loaded:
        """The BACI rows read for one view, with the partner in partner_col (i or j)."""
        digits = SPECIAL[product_code][0] if product_code in SPECIAL else None
        columns = ["t", "i", "j", "k", "v", "q"]
        frame = (pd.concat(pieces, ignore_index=True) if pieces else
                 pd.DataFrame({c: pd.Series(dtype="float64" if c in "vq" else "object")
                               for c in columns}))

        if digits in (2, 4):
            descriptions = self.hs_descriptions("BACI")
        elif digits == 0:
            descriptions = {"TOTAL": "All products"}
        else:
            descriptions = dict(zip(self.baci_product_codes["code"],
                                    self.baci_product_codes["description"]))
        names = dict(zip(self.baci_country_codes["country_code"],
                         self.baci_country_codes["country_name"]))
        iso3 = dict(zip(self.baci_country_codes["country_code"],
                        self.baci_country_codes["country_iso3"]))
        partner = frame[partner_col].astype(int)
        product_desc = frame["k"].map(descriptions).fillna("Not in the HS 1992 list")
        rows = pd.DataFrame({
            "Period": frame["t"].astype(int),
            "Partner_Code": partner,
            "Partner_Name": partner.map(names).fillna("Unknown (code " + partner.astype(str) + ")"),
            "Partner_ISO3": partner.map(iso3).fillna(""),
            "Product_Code": frame["k"],
            "Product_Desc": product_desc,
            "value": frame["v"] / 1000,          # thousand USD in BACI, million USD here
            "quantity": frame["q"],              # metric tons in BACI and here
        })
        level = SPECIAL[product_code][2] if product_code in SPECIAL else \
            "HS 6-digit product (HS 1992)"
        summed = digits is not None and digits < 6
        raw = pd.DataFrame({
            "Year (t)": frame["t"].astype(int),
            "Exporter code (i)": frame["i"].astype(int),
            "Exporter": frame["i"].astype(int).map(names),
            "Importer code (j)": frame["j"].astype(int),
            "Importer": frame["j"].astype(int).map(names),
            "HS code (k)": frame["k"],
            "Product": product_desc,
            "Value, thousand USD (v)": frame["v"],
            "Quantity, t (q)": frame["q"],
        })
        lacking = rows[rows["quantity"].isna()]
        reason = ("BACI leaves the quantity blank for at least one of the rows summed here"
                  if summed else "BACI leaves the quantity blank")
        gaps = pd.DataFrame({"Period": lacking["Period"], "Partner": lacking["Partner_Name"],
                             "HS code": lacking["Product_Code"], "Product": lacking["Product_Desc"],
                             "Metric": "Quantity", "Reason": reason,
                             f"Value ({MILLION_USD})": lacking["value"]})
        return Loaded(
            rows=rows, raw=raw, raw_metrics=["Value, thousand USD (v)", "Quantity, t (q)"],
            gaps=gaps, missing_periods=dict(missing),
            checks=[("BACI rows", f"{source_rows:,} rows of the BACI files match the query")],
            product_level=level,
            raw_note=(f"BACI rows summed by year, partner and {level}; a summed quantity is "
                      "Missing when any of its rows lacks one." if summed else
                      "One row per BACI record: year, exporter, importer and HS 6-digit "
                      "product, values as in the BACI file (thousand USD, metric tons)."),
            available={"value": int(rows["value"].notna().sum()),
                       "quantity": int(rows["quantity"].notna().sum())})

    @staticmethod
    def sum_baci(frame: pd.DataFrame, digits: int) -> pd.DataFrame:
        """BACI rows summed to chapters, headings or one total; a quantity sum is Missing when
        any row in it has no quantity."""
        frame = frame.assign(k=frame["k"].str[:digits] if digits else "TOTAL",
                             q_missing=frame["q"].isna())
        out = frame.groupby(["t", "i", "j", "k"], as_index=False, sort=False).agg(
            v=("v", "sum"), q=("q", "sum"), q_missing=("q_missing", "any"))
        out.loc[out["q_missing"], "q"] = np.nan
        return out.drop(columns="q_missing")

    # -- COMTRADE -------------------------------------------------------------------------
    def comtrade_product_codes(self, code: str) -> list[str]:
        """The codes to request: the HS 6-digit products under a chapter or heading, so the
        answer has product detail; every HS edition is asked for, COMTRADE answers in the
        reporter's own."""
        if code in SPECIAL or len(code) >= 6:
            return [code]
        children = sorted(c for c in self.hs_descriptions("COMTRADE")
                          if len(c) == 6 and c.startswith(code))
        return children or [code]

    def comtrade_availability(self, spec: Spec) -> dict[int, str] | None:
        """Periods the reporter has reported to COMTRADE, each with the HS edition it reported
        in ('' when the list does not say); None when the list cannot be read."""
        available = {}
        try:
            for part in chunks([str(p) for p in spec.periods], COMTRADE_PERIODS_PER_CALL):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", FutureWarning)
                    answer = comtradeapicall.getFinalDataAvailability(
                        self.subscription_key, typeCode='C', freqCode=spec.freq, clCode='HS',
                        period=",".join(part), reporterCode=str(spec.reporter_code))
                if answer is None:
                    return None
                if len(answer):
                    editions = (answer["classificationCode"].fillna("").astype(str)
                                if "classificationCode" in answer else [""] * len(answer))
                    available.update(zip(answer["period"].astype(int), editions))
        except Exception as err:
            print(f"  ⚠ Could not read COMTRADE's data availability: {err}")
            return None
        return available

    def load_comtrade(self, spec: Spec, product_detail=True, partner=None,
                      required=True) -> Loaded | None:
        """COMTRADE's records for the code asked for and for each of its HS 6-digit products,
        by partner and with partner World, which is COMTRADE's own total. Every figure is taken
        from the records COMTRADE gives for it: the totals from the code's World records, the
        partners from the code's partner records, the products from their own records. Values
        the API leaves empty, weights and quantities it records as 0 on a flow with a value, and
        quantities whose unit is N/A are Missing; so is every period the reporter has not
        reported. Weights and quantities UN Comtrade estimated are used as given and flagged.

        For a partner query's other views: product_detail=False asks for the code alone,
        without its products; a partner code asks for the trade with that partner alone,
        without partner World; required=False gives every period as Missing when there is
        nothing at all, instead of no data."""
        # The code asked for gives the totals and the partners (TOTAL does, for the AG codes);
        # its HS 6-digit products give the product detail
        query_code = "TOTAL" if spec.product_code in SPECIAL else spec.product_code
        products = (self.comtrade_product_codes(spec.product_code) if product_detail
                    else [query_code])
        codes = list(dict.fromkeys(products + [query_code]))
        print("\nFetching COMTRADE data...")
        print(f"  freq={spec.freq}, periods={len(spec.periods)}, reporter={spec.reporter_code}, "
              f"product={spec.product_code} ({len(codes)} code(s)), flow={spec.flow_code}"
              + (f", partner={partner}" if partner is not None else ""))
        available = self.comtrade_availability(spec)
        frames, calls, truncated = [], 0, False
        for part in chunks([str(p) for p in spec.periods], COMTRADE_PERIODS_PER_CALL):
            for group in chunks(codes, COMTRADE_CODES_PER_CALL):
                if calls:
                    time.sleep(1)       # stay within the API's rate limit
                calls += 1
                with warnings.catch_warnings():
                    # comtradeapicall's own pd.concat raises a pandas FutureWarning
                    warnings.simplefilter("ignore", FutureWarning)
                    data = comtradeapicall._getFinalData(
                        subscription_key=self.subscription_key, typeCode='C',
                        freqCode=spec.freq, clCode='HS', period=",".join(part),
                        reporterCode=str(spec.reporter_code), cmdCode=",".join(group),
                        flowCode=spec.flow_code,
                        partnerCode=None if partner is None else str(partner), partner2Code=None,
                        customsCode=None, motCode=None, maxRecords=COMTRADE_MAX_RECORDS,
                        format_output='JSON', aggregateBy=None, breakdownMode='classic',
                        countOnly=False, includeDesc=True)
                if data is None:
                    print("  ✗ COMTRADE did not answer a request (see the message above).")
                    return None
                truncated |= len(data) >= COMTRADE_MAX_RECORDS
                if len(data):
                    frames.append(data)
        data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        print(f"  ✓ {len(data):,} records in {calls} request(s)")
        if data.empty and not available and required:
            print("  ✗ No data returned from COMTRADE API")
            print("")
            print("  Possible reasons:")
            print("    - The country may not have reported data for this period yet")
            print("    - The product code may not have trade for this country/period")
            print("")
            print("  Try checking data availability at: https://comtradeplus.un.org/")
            return None

        if len(data):
            data = data.assign(_period=data["period"].astype(int)).reset_index(drop=True)
        # Which records are which: partner World is COMTRADE's own total; the code asked for and
        # its products are separate records unless they are the same code
        world = data["partnerCode"].eq(0) if len(data) else pd.Series(dtype=bool)
        query = (data["cmdCode"].astype(str).eq(query_code) if len(data)
                 else pd.Series(dtype=bool))
        separate = query_code not in products and bool(query.any())
        product = ~query if separate else pd.Series(True, index=data.index)
        if query_code not in products and not query.any():
            query = pd.Series(True, index=data.index)
        # The HS edition of each period's records: COMTRADE keeps every country's data in the
        # edition it reported in, so product codes can change from one year to the next
        editions = ({int(p): sorted(set(e.dropna().astype(str)),
                                    key=lambda x: HS_EDITIONS.get(x, 9999))
                     for p, e in data.groupby("_period")["classificationCode"]}
                    if len(data) and "classificationCode" in data else {})

        # What the country did not report, metric by metric. A figure UN Comtrade estimated is
        # in the database: it is used as given and flagged, never treated as missing.
        value = pd.to_numeric(data.get("primaryValue"), errors="coerce") if len(data) else \
            pd.Series(dtype=float)
        has_value = value > 0
        masks, reasons, estimated = {}, {}, {}
        for key, column in COMTRADE_COLUMNS.items():
            series = (pd.to_numeric(data[column], errors="coerce") if column in data
                      else pd.Series(np.nan, index=data.index))
            empty = series.isna()
            zero = (series == 0) & has_value & (key in ("netweight", "grossweight", "quantity"))
            no_unit = ((data["qtyUnitCode"] == -1) & ~empty if key == "quantity"
                       and "qtyUnitCode" in data else pd.Series(False, index=data.index))
            masks[key] = empty | zero | no_unit
            reasons[key] = np.select(
                [empty, no_unit, zero],
                ["empty in COMTRADE", "quantity unit is N/A in COMTRADE",
                 "recorded as 0 in COMTRADE although the flow has a value"], "")
            flag = COMTRADE_ESTIMATED.get(key)
            if flag in data:
                estimated[key] = data[flag].eq(True) & ~masks[key]

        def metric(key, scale=1.0):
            """A metric's values, NaN where COMTRADE does not report it."""
            column = COMTRADE_COLUMNS[key]
            series = (pd.to_numeric(data[column], errors="coerce") if column in data
                      else pd.Series(np.nan, index=data.index))
            return (series / scale).where(~masks[key])

        # COMTRADE gives values in USD and weights in kg: here they are in million USD and
        # metric tons. Quantities stay as COMTRADE gives them, each in its own unit.
        unit = (data["qtyUnitAbbr"] if "qtyUnitAbbr" in data
                else pd.Series(np.nan, index=data.index, dtype=object))
        records = pd.DataFrame({
            "Period": data["_period"] if len(data) else pd.Series(dtype=int),
            "Partner_Code": data["partnerCode"].astype(int) if len(data) else pd.Series(dtype=int),
            "Partner_Name": data.get("partnerDesc", pd.Series(dtype=object)),
            "Partner_ISO3": data.get("partnerISO", pd.Series(dtype=object)),
            "Product_Code": data["cmdCode"].astype(str) if len(data) else pd.Series(dtype=object),
            "Product_Desc": data.get("cmdDesc", pd.Series(dtype=object)),
            "value": metric("value", 1e6), "cif": metric("cif", 1e6), "fob": metric("fob", 1e6),
            "netweight": metric("netweight", 1000.0), "grossweight": metric("grossweight", 1000.0),
            "quantity": metric("quantity"),
            "Quantity unit": unit.where(~masks["quantity"]),
            **{estimate_column(key): flags for key, flags in estimated.items()},
        })

        def pick(mask):
            return records[mask.to_numpy()].reset_index(drop=True)

        rows = pick(product & ~world)                     # the products, partner by partner
        partner_rows = pick(query & ~world) if separate else None
        # COMTRADE's own totals; none when one partner was asked for
        total_rows = pick(query & world) if partner is None else None
        product_total_rows = pick(product & world) if separate and partner is None else None

        # The quantity unit of each product's records, N/A included, so that quantities in
        # different units are never added and the user sees which products share one
        quantity_units = {}
        detail = data[(product & ~world).to_numpy()] if len(data) else data
        if len(detail) and "qtyUnitAbbr" in detail:
            units = detail["qtyUnitAbbr"].fillna("N/A").astype(str)
            for unit_, part in detail.groupby(units):
                quantity_units[unit_] = {"records": len(part),
                                         "products": sorted(part["cmdCode"].astype(str).unique()),
                                         "periods": sorted(part["_period"].unique().tolist())}

        # Raw data is exactly what COMTRADE returned, its estimates and flags included
        raw = data.drop(columns=["_period"]).copy() if len(data) else data.copy()
        for column in COMTRADE_COLUMNS.values():
            if column in raw:
                raw[column] = pd.to_numeric(raw[column], errors="coerce")
        estimate_frames = []
        for key, flags in estimated.items():
            if flags.any():
                part = records[flags.to_numpy()]
                metric_ = COMTRADE_METRICS[key]
                estimate_frames.append(pd.DataFrame({
                    "Period": part["Period"], "Partner": part["Partner_Name"],
                    "HS code": part["Product_Code"], "Product": part["Product_Desc"],
                    "Metric": metric_.label, "Estimated figure": part[key],
                    "Unit": part["Quantity unit"] if key == "quantity" else metric_.unit,
                    f"Value ({MILLION_USD})": part["value"],
                    "Source flag": COMTRADE_ESTIMATED[key]}))
        estimates = (pd.concat(estimate_frames, ignore_index=True) if estimate_frames
                     else pd.DataFrame(columns=ESTIMATE_COLUMNS))
        gap_frames = []
        for key, mask in masks.items():
            if mask.any():
                part = records[mask.to_numpy()]
                gap_frames.append(pd.DataFrame({
                    "Period": part["Period"], "Partner": part["Partner_Name"],
                    "HS code": part["Product_Code"], "Product": part["Product_Desc"],
                    "Metric": COMTRADE_METRICS[key].label, "Reason": reasons[key][mask.to_numpy()],
                    f"Value ({MILLION_USD})": part["value"]}))
        gaps = (pd.concat(gap_frames, ignore_index=True) if gap_frames
                else pd.DataFrame(columns=GAP_COLUMNS + [f"Value ({MILLION_USD})"]))

        missing, checks = {}, [("COMTRADE requests", f"{calls} request(s), {len(data):,} records")]
        word = "month" if spec.freq == "M" else "year"
        returned = set(records["Period"].unique()) if len(records) else set()
        for p in spec.periods:
            if available is not None and p not in available:
                missing[p] = f"{spec.reporter_name} has not reported this {word} to COMTRADE"
            elif available is None and p not in returned:
                missing[p] = ("COMTRADE returned no data, and its availability list could not be "
                              f"read to tell whether {spec.reporter_name} reported this {word}")
        if truncated:
            checks.append(("Complete download", "NO: a request returned COMTRADE's maximum of "
                                                f"{COMTRADE_MAX_RECORDS:,} records, so records "
                                                "are missing. Narrow the query."))
            print(f"  ⚠ A request hit the {COMTRADE_MAX_RECORDS:,}-record cap: the data is "
                  "incomplete. Narrow the query.")
        if world.any():
            def values(mask):
                return records[mask.to_numpy()].groupby("Period")["value"].sum(min_count=1)
            totals = values(query & world)
            checks.append(("Partners add up to COMTRADE's total (partner World)",
                           agreement(values(query & ~world), totals, word, spec.freq == "M")))
            if separate:
                checks.append((f"Products add up to COMTRADE's total for {query_code}",
                               agreement(values(product & world), totals, word,
                                         spec.freq == "M")))
        if query_code not in products and not separate and len(data):
            checks.append(("Totals", f"COMTRADE returned no records for {query_code} itself, so "
                                     "its totals are those of its products added up"))
        if "isReported" in data and len(data):
            unreported = int(data["isReported"].eq(False).sum())
            aggregated = int(data["isAggregate"].eq(True).sum()) if "isAggregate" in data else 0
            if unreported or aggregated:
                checks.append(("COMTRADE record flags",
                               f"isReported is false for {unreported:,} and isAggregate is true "
                               f"for {aggregated:,} of the {len(data):,} records. They are used "
                               "as COMTRADE gives them; Raw data shows both flags for each "
                               "record."))
        if product_detail and products == [spec.product_code] and len(spec.product_code) < 6 \
                and spec.product_code not in SPECIAL:
            checks.append(("Product detail", "the HS code list could not be read, so COMTRADE's "
                                             "own records for the code are used, without HS "
                                             "6-digit detail"))
        if not product_detail:
            level = (SPECIAL["TOTAL"][2] if query_code == "TOTAL" else
                     f"HS code {query_code} as a whole, in the HS edition the reporter used")
        else:
            level = SPECIAL[spec.product_code][2] if spec.product_code in SPECIAL else \
                "HS 6-digit product, in the HS edition the reporter used"
        own = (f"the records for {query_code} itself and for each of its "
               f"{level.split(',')[0]}s" if separate else "the records")
        partners = ("by partner and with partner World (COMTRADE's own total)" if partner is None
                    else f"with {spec.partner_name} only")
        return Loaded(
            rows=rows, raw=raw, raw_metrics=[c for c in COMTRADE_COLUMNS.values() if c in raw],
            gaps=gaps, missing_periods=missing, checks=checks, product_level=level,
            raw_note=f"Every record COMTRADE returned, exactly as the API gives it, with every "
                     f"column: {own}, {partners}. An empty field shows as Missing. The "
                     "isNetWgtEstimated, isGrossWgtEstimated and isQtyEstimated columns mark the "
                     "weights and quantities UN Comtrade estimated.",
            # Counted, like the quantity units, over the products' records by partner
            available={key: int((~masks[key] & product & ~world).sum())
                       for key in COMTRADE_METRICS},
            estimates=estimates,
            estimated={key: int((flags & product & ~world).sum())
                       for key, flags in estimated.items()},
            editions=editions, partner_rows=partner_rows, total_rows=total_rows,
            product_total_rows=product_total_rows, quantity_units=quantity_units,
            reported=available or {})

    # -- from data to report -----------------------------------------------------------------
    def load(self, spec: Spec) -> Loaded | None:
        """A query's data; for a partner query also its other two views (see Spec.views),
        which BACI reads in the same pass and COMTRADE fetches with requests of their own."""
        if spec.source == "BACI":
            return self.load_baci(spec)
        loaded = self.load_comtrade(spec)
        if loaded is not None and spec.partner_code is not None:
            side, other = spec.views()
            print(f"\nFor the partner report: {spec.partner_name}'s own reports of its "
                  f"{side.flow.lower()}, to every country")
            loaded.side = self.load_comtrade(side, product_detail=False, required=False)
            self.mark_missing_codes(side, loaded.side)
            print(f"\nFor the partner report: {spec.reporter_name}'s {other.flow.lower()} "
                  f"{'to' if other.flow_code == 'X' else 'from'} {spec.partner_name}")
            loaded.other = self.load_comtrade(other, partner=spec.partner_code, required=False)
        return loaded

    def mark_missing_codes(self, spec: Spec, loaded: Loaded | None):
        """Periods a country reported in an HS edition without the code asked for are Missing:
        it could not report trade under that code then, so no record does not mean no trade."""
        code = spec.product_code
        if loaded is None or code in SPECIAL or not loaded.reported:
            return
        reported = {p: e for p, e in loaded.reported.items() if e}
        editions = self.hs_editions(needed=set(reported.values())).get(code)
        if not editions:
            return
        word = "month" if spec.freq == "M" else "year"
        for period, edition in sorted(reported.items()):
            if period in spec.periods and edition not in editions \
                    and period not in loaded.missing_periods:
                loaded.missing_periods[period] = (
                    f"{spec.reporter_name} reported this {word} in {edition_label(edition)}, "
                    f"which has no code {code}")

    def check_against_comtrade(self, spec: Spec, loaded: Loaded):
        """BACI queries: each year's BACI total beside the reporter's own COMTRADE figure for the
        same code and flow (partner World, and the partner for a partner query), so that a total
        in which BACI counts the same trade twice shows (Usage Guide, section 9.9). The COMTRADE
        figures go to loaded.comtrade_check and one check line per flow; no figure of the report
        uses them. The check line says why when the check cannot be made."""
        code = "TOTAL" if spec.product_code in SPECIAL else spec.product_code
        what = "all products (TOTAL)" if code == "TOTAL" else code
        name, word = spec.reporter_name, "year"
        flows = [(0, None, f"{name}'s {spec.flow.lower()}, all partners")]
        if spec.partner_baci is not None and spec.partner_code is not None:
            to = "from" if spec.flow_code == "M" else "to"
            flows.append((spec.partner_code, spec.partner_baci,
                          f"{name}'s {spec.flow.lower()} {to} {spec.partner_name}"))
        print("\nChecking BACI's totals against the reporter's own COMTRADE report...")
        try:
            key = self.subscription_key
        except (FileNotFoundError, ValueError):
            text = ("Not made: there is no COMTRADE API key (SUBSCRIPTION_KEY.env), so BACI's "
                    "totals were not compared with the reporter's own COMTRADE report (Usage "
                    "Guide, section 9.9).")
            loaded.checks.append(("BACI against COMTRADE", text))
            print(f"  ⚠ {text}")
            return
        frames = []
        try:
            available = self.comtrade_availability(spec)
            for part in chunks([str(p) for p in spec.periods], COMTRADE_PERIODS_PER_CALL):
                if frames:
                    time.sleep(1)       # stay within the API's rate limit
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", FutureWarning)
                    data = comtradeapicall._getFinalData(
                        subscription_key=key, typeCode='C', freqCode=spec.freq, clCode='HS',
                        period=",".join(part), reporterCode=str(spec.reporter_code),
                        cmdCode=code, flowCode=spec.flow_code,
                        partnerCode=",".join(str(p) for p, _, _ in flows), partner2Code=None,
                        customsCode=None, motCode=None, maxRecords=COMTRADE_MAX_RECORDS,
                        format_output='JSON', aggregateBy=None, breakdownMode='classic',
                        countOnly=False, includeDesc=True)
                if data is None:
                    raise RuntimeError("COMTRADE did not answer")
                frames.append(data)
        except Exception as err:
            text = f"Not made: {err}."
            loaded.checks.append(("BACI against COMTRADE", text))
            print(f"  ⚠ {text}")
            return
        data = pd.concat([f for f in frames if len(f)], ignore_index=True) \
            if any(len(f) for f in frames) else pd.DataFrame()
        figures = {}                # (partner, period) -> COMTRADE's value in USD, or NaN
        for record in data.to_dict("records"):
            if record.get("partner2Code", 0) == 0 and record.get("motCode", 0) == 0 \
                    and record.get("customsCode", "C00") == "C00":
                figures.setdefault((int(record["partnerCode"]), int(record["period"])),
                                   pd.to_numeric(record.get("primaryValue"), errors="coerce"))
        reported = {p: e for p, e in (available or {}).items() if e}
        editions = (self.hs_editions(needed=set(reported.values())).get(code)
                    if code != "TOTAL" and reported else None)
        records = []
        for partner, baci_code, label in flows:
            rows = loaded.rows if baci_code is None else \
                loaded.rows[loaded.rows["Partner_Code"] == baci_code]
            sums = rows.groupby("Period")["value"].sum()
            for period in spec.periods:
                baci = MISSING if period in loaded.missing_periods else \
                    float(sums.get(period, 0.0))
                if available is not None and period not in available:
                    value, note = MISSING, f"{name} has not reported this {word} to COMTRADE"
                elif editions and period in reported and reported[period] not in editions:
                    value, note = MISSING, (f"{name} reported this {word} in "
                                            f"{edition_label(reported[period])}, which has no "
                                            f"code {code}")
                elif (partner, period) in figures:
                    raw = figures[(partner, period)]
                    value, note = (MISSING, "empty in COMTRADE") if raw != raw else \
                        (raw / 1e6, "")
                elif available is None:
                    value, note = MISSING, ("no record in COMTRADE, and its availability list "
                                            "could not be read")
                else:
                    value, note = 0.0, "no record in COMTRADE"
                records.append({"Flow": label, "Year": period,
                                f"BACI ({MILLION_USD})": baci,
                                f"COMTRADE, {name}'s own report ({MILLION_USD})": value,
                                "BACI / COMTRADE": ratio(baci, value), "Note": note})
        loaded.comtrade_check = pd.DataFrame.from_records(records)
        for _, _, label in flows:
            part = loaded.comtrade_check[loaded.comtrade_check["Flow"] == label]
            known = [(r["Year"], r["BACI / COMTRADE"]) for r in part.to_dict("records")
                     if not is_gap(r["BACI / COMTRADE"]) and r["BACI / COMTRADE"] == r[
                         "BACI / COMTRADE"]]
            notes = {}
            for r in part.to_dict("records"):
                if r["Note"]:
                    notes.setdefault(r["Note"], []).append(r["Year"])
            if known:
                low, high = min(v for _, v in known), max(v for _, v in known)
                times = f"{low:.2f}" if f"{low:.2f}" == f"{high:.2f}" else \
                    f"{low:.2f} to {high:.2f}"
                text = (f"BACI's value is {times} times {name}'s own COMTRADE figure for {what} "
                        f"in {period_runs([y for y, _ in known], False)}")
            else:
                text = "No year has both a BACI and a COMTRADE figure to compare"
            text += "".join(f"; {period_runs(years, False)}: {note}" for note, years in
                            notes.items())
            text += (". The COMTRADE check sheet gives each year; no figure of the report uses "
                     "these COMTRADE figures (Usage Guide, section 9.9).")
            loaded.checks.append((f"BACI against COMTRADE: {label}", text))
            print(textwrap.fill(f"  {label}: {text}", 100, subsequent_indent="    "))

    def assemble(self, spec: Spec, metric_key: str, loaded: Loaded) -> tuple[Query, QueryData]:
        unit_names = {}         # the quantity unit's description, for the outputs
        if spec.source == "BACI":
            metric = BACI_METRICS[metric_key]
            metrics = [metric] + [m for m in BACI_METRICS.values() if m.key != metric_key]
            source_note = (f"Source: CEPII BACI (HS 1992, version {BACI_VERSION[1:]}). Values in "
                           "million current USD; quantities in metric tons.")
            description = (f"CEPII BACI, HS 1992 nomenclature, version {BACI_VERSION[1:]}: "
                           "bilateral trade flows in which the exporter's and the importer's "
                           "declarations are reconciled. Values are in thousand USD in BACI and "
                           "in million USD here; quantities are in metric tons in both. Raw data "
                           "keeps BACI's own units. Limitation: BACI pairs the two declarations "
                           "product by product, at the HS 6-digit level, and keeps a flow that "
                           "only one country declares, so when the two countries put the same "
                           "trade under different 6-digit codes, BACI keeps both declarations and "
                           "totals above 6 digits count that trade twice. For one country's own "
                           "trade at 4 digits and above, compare with COMTRADE (Usage Guide, "
                           "section 9.9).")
            rules = ["BACI: a quantity left blank in the BACI file. BACI always gives a value."]
            estimate_rules, estimated_by = [], ""
            reporter, partner = spec.reporter_baci, spec.partner_baci
            unit_value = ("value", "quantity")
        else:
            # The quantity's unit, as COMTRADE gives it; a quantity analysis has only one,
            # because quantities in different units are refused before this
            frames = [f for f in (loaded.rows, loaded.partner_rows, loaded.total_rows,
                                  loaded.product_total_rows) if f is not None and len(f)]
            units = (set(pd.concat([f["Quantity unit"] for f in frames]).dropna())
                     if frames else set())
            catalog = {**COMTRADE_METRICS, "quantity": Metric(
                "quantity", "Quantity", units.pop() if len(units) == 1 else "", "volume",
                unit_column="Quantity unit")}
            metric = catalog[metric_key]
            keys = [metric_key] + [k for k in ("value", "netweight") if k != metric_key]
            metrics = [catalog[k] for k in keys]
            if metric_key == "quantity" and metric.unit:
                unit_names = {metric.unit: self.unit_names().get(metric.unit, "")}
            frequency = "monthly" if spec.freq == "M" else "annual"
            quantities = (f"; quantities in {metric.unit or 'the unit COMTRADE gives'}, as "
                          "COMTRADE reports them" if metric_key == "quantity" else "")
            source_note = (f"Source: UN Comtrade, {frequency} data as reported by "
                           f"{spec.reporter_name}. Values in million current USD; weights in "
                           f"metric tons{quantities}.")
            description = (f"UN Comtrade (comtradeplus.un.org), final {frequency} data in the HS "
                           "classification as reported, retrieved "
                           f"{dt.date.today():%d %B %Y} through the COMTRADE API. Value is "
                           "COMTRADE's primary value (usually CIF for imports, FOB for exports). "
                           "COMTRADE gives values in USD and weights in kg; here values are in "
                           "million USD and weights in metric tons. Quantities are as COMTRADE "
                           "reports them, in its own unit, and quantities in different units "
                           "are never added together. Raw data keeps COMTRADE's own units.")
            rules = ["COMTRADE: a value or weight the API leaves empty.",
                     "COMTRADE: a weight or quantity recorded as 0 on a flow that has a value.",
                     "COMTRADE: a quantity whose unit is N/A.",
                     "COMTRADE: a period the reporter has not reported (COMTRADE's data "
                     "availability list)."]
            estimate_rules = ["COMTRADE: a weight or quantity whose isNetWgtEstimated, "
                              "isGrossWgtEstimated or isQtyEstimated flag is true. UN Comtrade "
                              f"estimated it; {spec.reporter_name} did not report it."]
            estimated_by = "UN Comtrade"
            reporter, partner = spec.reporter_code, spec.partner_code
            unit_value = ("value", "netweight")
        # The HS edition of each period; when the data is in more than one edition, the
        # editions of every product code, and the codes that are not in all of them
        if spec.source == "BACI":
            hs_editions = {p: "HS 1992" for p in spec.periods if p not in loaded.missing_periods}
        else:
            hs_editions = {p: " and ".join(edition_label(e) for e in editions)
                           for p, editions in sorted(loaded.editions.items())}
        used = sorted({e for editions in loaded.editions.values() for e in editions},
                      key=lambda e: HS_EDITIONS.get(e, 9999))
        product_editions, edition_changes = {}, []
        if len(used) > 1:
            table = self.hs_editions(needed=used)
            known = {e for editions in table.values() for e in editions}
            for code in sorted(loaded.rows["Product_Code"].astype(str).unique()):
                if code in table:
                    product_editions[code] = editions_text(table[code], known)
                    if not set(used) <= set(table[code]):
                        edition_changes.append(code)
        labels = {m.label for m in metrics}
        gaps = loaded.gaps[loaded.gaps["Metric"].isin(labels)].reset_index(drop=True)
        estimates = loaded.estimates[loaded.estimates["Metric"].isin(labels)].reset_index(drop=True)
        checks = list(loaded.checks)
        if len(estimates):
            counts = estimates["Metric"].value_counts()
            listed = ", ".join(f"{counts[m.label]:,} {m.label.lower()} "
                               f"figure{'' if counts[m.label] == 1 else 's'}"
                               for m in metrics if m.label in counts)
            checks.append(("Estimates in the source",
                           f"{listed} in this analysis are estimates by {estimated_by}, not "
                           f"figures reported by {spec.reporter_name}. They are used as "
                           f"{spec.source} gives them, shown in blue in the workbook's tables "
                           "and listed in the Source estimates sheet."))
        query = Query(
            source=spec.source, freq=spec.freq, periods=spec.periods, reporter_code=reporter,
            reporter_name=spec.reporter_name, flow=spec.flow, product_code=spec.product_code,
            product_desc=spec.product_desc, metric=metric, metrics=metrics, unit_value=unit_value,
            partner_code=partner, partner_name=spec.partner_name, source_note=source_note,
            source_description=description, product_level=loaded.product_level,
            missing_rules=rules, estimate_rules=estimate_rules, estimated_by=estimated_by,
            hs_editions=hs_editions, product_editions=product_editions,
            edition_changes=edition_changes, unit_names=unit_names,
            missing_periods=loaded.missing_periods, checks=checks)
        data = QueryData(loaded.rows, loaded.raw, loaded.raw_metrics, gaps, loaded.raw_note,
                         estimates, loaded.partner_rows, loaded.total_rows,
                         loaded.product_total_rows, comtrade_check=loaded.comtrade_check)
        if loaded.side is not None or loaded.other is not None:
            side, other = spec.views()
            data.partner_views = PartnerViews(
                side=self.assemble(side, metric_key, loaded.side) if loaded.side else None,
                other=self.assemble(other, metric_key, loaded.other) if loaded.other else None)
        return query, data

    @staticmethod
    def nothing_recorded(spec: Spec, loaded: Loaded) -> str:
        """Why a query whose source has no records at all gets no report."""
        if not loaded.missing_periods:
            return "no trade recorded for this query"
        reasons = "; ".join(f"{period_label(p, spec.freq == 'M')}: {reason}"
                            for p, reason in sorted(loaded.missing_periods.items()))
        if len(loaded.missing_periods) == len(spec.periods):
            return f"no data for any period of the query ({reasons})"
        return ("no trade recorded in the periods the source reports, and no data for the others "
                f"({reasons})")

    def run_spec(self, spec: Spec, out_root: Path, metric: str | None = None):
        """Load one query and build its report; returns the outputs, or None without data."""
        loaded = self.load(spec)
        if loaded is None:
            return None
        if loaded.rows.empty:
            print(f"\n✗ Analysis cancelled: {self.nothing_recorded(spec, loaded)}")
            return None
        if spec.source == "BACI":
            self.check_against_comtrade(spec, loaded)
        metric = metric or spec.metric or "value"
        if spec.source == "COMTRADE" and metric == "quantity":
            refusal = self.quantity_refusal(loaded.quantity_units)
            if refusal:
                raise ValueError(refusal)
        if loaded.available.get(metric, 0) == 0:
            print(f"  ⚠ The source reports no {metric} for this query; it will show as Missing.")
        query, data = self.assemble(spec, metric, loaded)
        return self.report(query, data, out_root)

    def report(self, query: Query, data: QueryData, out_root: Path):
        print("\nBuilding the report (charts, workbook, Word report, summary)...")
        outputs, analysis = build_report(query, data, out_root)
        self.print_summary(analysis, outputs)
        return outputs

    def print_summary(self, analysis, outputs):
        q, m = analysis.q, analysis.metric
        print("\n" + "="*60)
        print("KEY FINDINGS")
        print("="*60)
        partner = q.partner_code is not None
        for sentence in (partner_findings(analysis) if partner else findings(analysis)):
            print(textwrap.fill(f"• {sentence}", 100, subsequent_indent="  "))
        if partner and len(analysis.periods) <= 36:
            print("\n" + "-"*60)
            print(f"{'Month' if q.monthly else 'Year':8s} {m.heading:>22s} {'Growth':>10s} "
                  f"{'Share':>8s} {'Rank':>6s}")
            print("-"*60)
            for row in analysis.position.to_dict("records"):
                print(f"{period_label(row['Period'], q.monthly, True):8s} "
                      f"{fmt.figure(row['Figure'], m):>22s} "
                      f"{fmt.pct(row['Growth'], 1, signed=True):>10s} "
                      f"{fmt.pct(row['Share']):>8s} {str(row['Rank']):>6s}")
        elif len(analysis.periods) <= 36:
            print("\n" + "-"*60)
            print(f"{'Month' if q.monthly else 'Year':8s} {m.heading:>22s} {'Growth':>10s} "
                  f"{'Largest share':>14s}")
            print("-"*60)
            totals = analysis.period_totals[m.key]
            for i, period in enumerate(analysis.periods):
                change = (growth(totals[period], totals[analysis.periods[i - 1]])
                          if i else float("nan"))
                print(f"{period_label(period, q.monthly, True):8s} "
                      f"{fmt.figure(totals[period], m):>22s} "
                      f"{fmt.pct(change, 1, signed=True) if i else '':>10s} "
                      f"{fmt.pct(analysis.period_stats.loc[period, 'Largest share']):>14s}")
        print("\n" + "="*60)
        print("FILES")
        print("="*60)
        print(f"  Folder:   {outputs.folder}")
        print(f"  Workbook: {outputs.workbook.name}")
        print(f"  Report:   {outputs.report.name}")
        print(f"  Summary:  {outputs.summary.name}")
        print(f"  Charts:   charts/ ({len(outputs.charts)} PNG files)")
        for label, name in outputs.extra.items():
            print(f"  {label}: {name} (too large for a sheet)")

    # -- ways to run ------------------------------------------------------------------------
    def interactive(self, out_root: Path):
        print("\n" + "="*60)
        print("INTERNATIONAL TRADE DATA ANALYSIS TOOL")
        print("="*60)
        print("Available Data Sources:")
        print(f"  BACI      :  {BACI_YEARS[0]}-{BACI_YEARS[1]} (harmonized bilateral flows, annual)")
        print("  COMTRADE  :  1962-present (as reported, annual and monthly)")
        print("="*60)
        while True:
            spec = self.ask_query()
            loaded = self.load(spec)
            if loaded is not None and len(loaded.rows):
                if spec.source == "BACI":
                    self.check_against_comtrade(spec, loaded)
                metric = spec.metric or self.get_metric_choice_comtrade(
                    loaded.available, loaded.estimated, loaded.quantity_units)
                query, data = self.assemble(spec, metric, loaded)
                try:
                    self.report(query, data, out_root)
                except PermissionError as err:
                    print(f"\n✗ {err}")
            elif loaded is not None:
                print(f"\n✗ Analysis cancelled: {self.nothing_recorded(spec, loaded)}")
            print(f"\n{'='*60}")
            print("ANALYSIS COMPLETE")
            print(f"{'='*60}\n")
            if not self.ask_yes_no("Run another analysis?"):
                break
            print("\n" * 2)

    def run_batch(self, path: Path, out_root: Path) -> int:
        """Run every query of a CSV file (columns: source, freq, period, reporter, partner,
        product, flow, metric); one failing query does not stop the others."""
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    for row in csv.DictReader(handle)]
        results = []
        for number_, row in enumerate(rows, start=1):
            print(f"\n{'='*60}\nQUERY {number_} of {len(rows)}: "
                  + ", ".join(f"{k}={v}" for k, v in row.items() if v) + f"\n{'='*60}")
            try:
                spec = self.spec_from_values(row)
                outputs = self.run_spec(spec, out_root)
                results.append((number_, "✓" if outputs else "✗",
                                outputs.folder.name if outputs else "no data"))
            except Exception as err:
                results.append((number_, "✗", str(err).splitlines()[0]))
                print(f"✗ Query {number_} failed: {err}")
        print(f"\n{'='*60}\nBATCH SUMMARY\n{'='*60}")
        for number_, mark, text in results:
            print(f"  {mark} {number_:3d}  {text}")
        return 0 if all(mark == "✓" for _, mark, _ in results) else 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyse a country's trade in one product, from BACI or UN COMTRADE.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage", 1)[1] if "Usage" in __doc__ else None)
    parser.add_argument("--source", choices=["baci", "comtrade"], type=str.lower,
                        help="data source")
    parser.add_argument("--freq", choices=["A", "M"], type=str.upper, default="A",
                        help="A annual (default) or M monthly (COMTRADE only)")
    parser.add_argument("--period", help="2015-2024, 2023, 202301-202312 or 202306")
    parser.add_argument("--reporter", help="reporter country, by code or name")
    parser.add_argument("--partner", help="one partner country, by code or name, for a report on "
                                          "the trade with it (default: all partners)")
    parser.add_argument("--product", help="HS code (2, 4 or 6 digits) or TOTAL, AG2, AG4, AG6")
    parser.add_argument("--flow", help="M imports or X exports")
    parser.add_argument("--metric", help="BACI: value or quantity; COMTRADE: value, cif, fob, "
                                         "netweight, grossweight or quantity (default value)")
    parser.add_argument("--out", help="output folder (default: output)")
    parser.add_argument("--batch", help="CSV file with one query per row")
    parser.add_argument("--build-baci-cache", action="store_true",
                        help="convert the BACI CSV files to Parquet once, for fast queries")
    parser.add_argument("--update-cpi", action="store_true",
                        help="download the US CPI table again from the World Bank")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    if args.update_cpi:
        print(update_cpi(CPI_FILE))
        return 0
    analyzer = TradeAnalyzer()
    out_root = Path(args.out) if args.out else analyzer.base_dir / "output"
    if args.build_baci_cache:
        analyzer.build_baci_cache()
        return 0
    if args.batch:
        return analyzer.run_batch(Path(args.batch), out_root)
    if any([args.source, args.period, args.reporter, args.product, args.flow]):
        spec = analyzer.spec_from_values(vars(args))
        return 0 if analyzer.run_spec(spec, out_root) else 1
    analyzer.interactive(out_root)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAnalysis cancelled by user.")
    except (ValueError, FileNotFoundError, PermissionError) as e:
        print(f"\n✗ {e}")
        sys.exit(2)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
