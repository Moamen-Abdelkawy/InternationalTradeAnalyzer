"""What a query asked for, how its metrics are measured, and the data it returned."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


MILLION_USD = "million USD"     # the unit of every amount of money in the analysis
TONS = "t"                      # the unit of every weight, and of quantities given by weight


@dataclass(frozen=True)
class Metric:
    """One measure of trade, e.g. value in million USD or quantity in metric tons."""
    key: str                        # column holding it in the rows
    label: str                      # 'Value', 'Quantity', 'Net weight'
    unit: str                       # 'million USD', 't'; empty when the unit varies by row
    kind: str                       # 'money' or 'volume'
    unit_column: str | None = None  # column with each row's unit, when units vary

    @property
    def heading(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label


@dataclass
class Query:
    """One analysis request and everything the report needs to describe it."""
    source: str                     # 'BACI' or 'COMTRADE'
    freq: str                       # 'A' (annual) or 'M' (monthly)
    periods: list[int]              # years, or months written as YYYYMM
    reporter_code: int
    reporter_name: str
    flow: str                       # 'Imports' or 'Exports'
    product_code: str               # HS code, or TOTAL / AG2 / AG4 / AG6
    product_desc: str
    metric: Metric                  # the metric partners are ranked and measured by
    metrics: list[Metric]           # every metric reported, the analysis metric first
    unit_value: tuple[str, str] | None = None   # keys of the (money, volume) pair
    partner_code: int | None = None             # set for a specific-partner analysis
    partner_name: str | None = None
    source_note: str = ""           # the footer line under every chart
    source_description: str = ""    # what the source is, for the About sheet
    product_level: str = "HS 6-digit product"   # what one product row stands for
    missing_rules: list[str] = field(default_factory=list)      # how gaps are recognised
    estimate_rules: list[str] = field(default_factory=list)     # how the source marks its estimates
    estimated_by: str = ""          # who made the source's own estimates, e.g. 'UN Comtrade'
    hs_editions: dict[int, str] = field(default_factory=dict)   # period -> HS edition of its data
    # When the data is in more than one HS edition: product code -> the editions it exists in,
    # and the codes that are not in every edition the data uses
    product_editions: dict[str, str] = field(default_factory=dict)
    edition_changes: list[str] = field(default_factory=list)
    unit_names: dict[str, str] = field(default_factory=dict)   # quantity unit -> description
    missing_periods: dict[int, str] = field(default_factory=dict)  # period -> why it is missing
    checks: list[tuple[str, str]] = field(default_factory=list)    # (check, result)

    @property
    def monthly(self) -> bool:
        return self.freq == "M"

    @property
    def role(self) -> str:
        return "supplier" if self.flow == "Imports" else "market"

    @property
    def roles(self) -> str:
        return self.role + "s"

    @property
    def span(self) -> str:
        first, last = (period_label(p, self.monthly) for p in (self.periods[0], self.periods[-1]))
        return first if first == last else f"{first}–{last}"

    @property
    def product_label(self) -> str:
        """'HS 1001 Wheat and meslin', or the special code's own description."""
        if self.product_code in ("TOTAL", "AG2", "AG4", "AG6"):
            return self.product_desc
        return f"HS {self.product_code} {self.product_desc}".strip()

    @property
    def folder_name(self) -> str:
        product = (self.product_code if self.product_code in ("TOTAL", "AG2", "AG4", "AG6")
                   else f"HS{self.product_code}")
        parts = [self.reporter_name, self.flow[:3].lower(), product]
        if self.partner_name:
            parts.append(self.partner_name)
        first, last = self.periods[0], self.periods[-1]
        parts += [str(first) if first == last else f"{first}-{last}", self.source]
        return safe_name("_".join(parts))


@dataclass
class QueryData:
    """What the source returned for a query."""
    rows: pd.DataFrame      # one row per period, partner and product, metrics as numbers or NaN;
                            # an estimate_column() flags the figures the source itself estimated
    raw: pd.DataFrame       # the source rows for the Raw data sheet, exactly as delivered
    raw_metrics: list[str]  # Raw data columns where an empty value means the source has none
    gaps: pd.DataFrame      # every data point the source does not report
    raw_note: str = ""      # what one Raw data row is, when it is not one source record
    estimates: pd.DataFrame = field(                # every figure the source itself estimated
        default_factory=lambda: pd.DataFrame(columns=ESTIMATE_COLUMNS))
    # The source's own figures above the product rows, in the same columns, when it has them
    # (COMTRADE): the code asked for by partner, its totals (partner World), each product's totals
    partner_rows: pd.DataFrame | None = None
    total_rows: pd.DataFrame | None = None
    product_total_rows: pd.DataFrame | None = None


ROW_COLUMNS = ["Period", "Partner_Code", "Partner_Name", "Partner_ISO3",
               "Product_Code", "Product_Desc"]
GAP_COLUMNS = ["Period", "Partner", "HS code", "Product", "Metric", "Reason"]
ESTIMATE_COLUMNS = ["Period", "Partner", "HS code", "Product", "Metric", "Estimated figure",
                    "Unit", f"Value ({MILLION_USD})", "Source flag"]


def estimate_column(key: str) -> str:
    """The rows' column flagging a metric's figures that the source itself estimated."""
    return f"{key}_estimated"


def period_label(period: int, monthly: bool, short: bool = False) -> str:
    """2024 -> '2024'; 202403 -> '2024-03', or 'Mar 2024' when short is False."""
    if not monthly:
        return str(period)
    year, month = divmod(int(period), 100)
    if short:
        return f"{year}-{month:02d}"
    return f"{MONTHS[month - 1]} {year}"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# COMTRADE's codes for the HS editions, and the year each came into force
HS_EDITIONS = {"H0": 1992, "H1": 1996, "H2": 2002, "H3": 2007, "H4": 2012, "H5": 2017,
               "H6": 2022, "H7": 2027}


def edition_label(edition: str) -> str:
    """'H4' -> 'HS 2012'."""
    year = HS_EDITIONS.get(edition)
    return f"HS {year}" if year else edition


def editions_text(have, known) -> str:
    """The HS editions a code exists in, out of the editions known: 'all HS editions',
    'HS 1992–2007', 'HS 2012 onwards', 'HS 2017 only' or 'HS 1992, 2002'."""
    order = sorted(set(known), key=lambda e: HS_EDITIONS.get(e, 9999))
    have = [e for e in order if e in set(have)]
    if not have:
        return "in no HS edition list"
    if have == order:
        return "all HS editions"
    first, last = order.index(have[0]), order.index(have[-1])
    if have != order[first:last + 1]:
        return "HS " + ", ".join(str(HS_EDITIONS.get(e, e)) for e in have)
    if have[-1] == order[-1]:
        return f"{edition_label(have[0])} onwards"
    if len(have) == 1:
        return f"{edition_label(have[0])} only"
    return f"HS {HS_EDITIONS.get(have[0], have[0])}–{HS_EDITIONS.get(have[-1], have[-1])}"


def safe_name(text: str, max_length: int = 120) -> str:
    """Text usable as a file or folder name on every system."""
    cleaned = re.sub(r"[^\w\s.-]", "", str(text), flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("_.")
    return cleaned[:max_length].rstrip("_.")
