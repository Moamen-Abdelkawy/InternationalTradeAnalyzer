"""The Excel workbook of a report: every table of the analysis, the source rows, the data gaps
and the charts. Cells the source does not report say 'Missing'; they are never left as zero.
Figures that include the source's own estimates are shown in blue."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell

from . import fmt
from .analysis import TOP_N, Analysis, cagr, growth, hhi_band, is_gap, number, ratio, total_of
from .findings import (edition_sentences, edition_summary, figures_note, findings,
                       gap_detail)
from .model import Metric, QueryData, period_label

SHEET_ROW_LIMIT = 150_000   # rows written into one sheet; longer tables go to a CSV beside it
NAVY, SKY, ACCENT, GREY = "#1F4E79", "#7FB8E6", "#E67E22", "#AEB6BF"
RED = "#C0392B"
BLUE = "#2E75B6"            # figures that include the source's own estimates
SERIES = ["#1F4E79", "#E67E22", "#2E86C1", "#16A085", "#8E44AD", "#D5D8DC"]

# Money in million USD and weights in metric tons, to the thousand USD and to the kg
NUMBER_FORMATS = {
    "money": "#,##0.000", "volume": "#,##0.000", "unit_value": "#,##0.00", "share": "0.0%",
    "growth": "+0.0%;-0.0%;0.0%", "pp": '+0.0" pp";-0.0" pp";0.0" pp"', "int": "0",
    "count": "#,##0", "hhi": "#,##0", "year": "0", "month": "yyyy-mm",
}
DERIVED = {"growth", "pp", "share", "unit_value", "hhi"}   # NaN here means 'not defined'


class Column(NamedTuple):
    header: str
    values: list
    kind: str               # a NUMBER_FORMATS key, or 'text'
    width: float | None = None
    marks: list | None = None   # per row: True when the figure includes a source estimate


class Book:
    def __init__(self, path: Path, a: Analysis, data: QueryData, charts: list[Path],
                 files: dict[str, str]):
        self.a, self.q, self.data, self.charts, self.files = a, a.q, data, charts, files
        self.path = path
        self.wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False,
                                                  "strings_to_formulas": False,
                                                  "strings_to_urls": False})
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter"}
        self.base = base
        add = self.wb.add_format
        self.f = {
            "title": add({**base, "bold": True, "font_size": 16, "font_color": NAVY}),
            "subtitle": add({**base, "italic": True, "font_color": "#595959"}),
            "section": add({**base, "bold": True, "font_size": 12, "font_color": NAVY,
                            "bottom": 2, "bottom_color": NAVY}),
            "header": add({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": NAVY,
                           "text_wrap": True, "border": 1, "border_color": "#FFFFFF"}),
            "text": add(base),
            "wrap": add({**base, "text_wrap": True, "valign": "top"}),
            "label": add({**base, "bold": True, "valign": "top"}),
            "link": add({**base, "font_color": "#0563C1", "underline": 1}),
            "note": add({**base, "italic": True, "font_color": "#595959", "text_wrap": True,
                         "valign": "top"}),
            "kpi_label": add({**base, "font_color": "#595959"}),
            "neg": add({"font_color": RED}),
            "estimate_note": add({**base, "italic": True, "font_color": BLUE}),
            "line_note": add({**base, "italic": True, "font_color": "#595959"}),
        }
        self._formats = {}
        self.chart_data = None      # hidden sheet holding the native charts' numbers
        self.chart_row = 0
        self.guide: list[tuple[str, str]] = []

    # -- cell formats -----------------------------------------------------------------
    def fmt(self, kind: str, total=False, gap=False, na=False, kpi=False, estimate=False):
        key = (kind, total, gap, na, kpi, estimate)
        if key in self._formats:
            return self._formats[key]
        props = dict(self.base)
        number_format = NUMBER_FORMATS.get(kind)
        if number_format and not (gap or na):
            props["num_format"] = number_format
        if gap:
            props.update({"italic": True, "font_color": "#C55A11", "bg_color": "#FBE5D6",
                          "align": "right"})
        if na:
            props.update({"italic": True, "font_color": "#7F7F7F", "align": "right"})
        if estimate and not (gap or na):
            props["font_color"] = BLUE
        if total:
            props.update({"bold": True, "top": 1, "top_color": NAVY})
            if not gap:
                props["bg_color"] = "#F2F2F2"
        if kpi:
            props.update({"bold": True, "font_size": 14, "font_color": NAVY, "align": "left"})
            if gap:
                props["font_color"] = "#C55A11"
        self._formats[key] = self.wb.add_format(props)
        return self._formats[key]

    def cell(self, ws, row, col, value, kind, total=False, estimate=False):
        """Write one value: a number (blue when it includes a source estimate), a gap stated as
        text, 'n/a' or blank."""
        if is_gap(value):
            ws.write_string(row, col, value, self.fmt(kind, total, gap=True))
            return
        if value is None or (isinstance(value, float) and np.isnan(value)):
            if kind in DERIVED:
                ws.write_string(row, col, fmt.NOT_DEFINED, self.fmt(kind, total, na=True))
            else:
                ws.write_blank(row, col, None, self.fmt(kind, total))
            return
        if isinstance(value, str):
            ws.write_string(row, col, value, self.fmt("text", total))
            return
        if kind == "month":
            year, month = divmod(int(value), 100)
            ws.write_datetime(row, col, dt.datetime(year, month, 1), self.fmt(kind, total))
            return
        if kind == "text":
            ws.write_string(row, col, str(value), self.fmt("text", total))
            return
        ws.write_number(row, col, float(value), self.fmt(kind, total, estimate=estimate))

    # -- tables -----------------------------------------------------------------------
    def table(self, ws, columns: list[Column], row=0, col=0, total: dict | None = None,
              freeze=True, autofilter=True, data_bar: str | None = None,
              heat: tuple[int, int] | None = None, growth_heat=False,
              total_marks: dict | None = None) -> int:
        """Write columns under the house header; returns the last row written."""
        n = max((len(c.values) for c in columns), default=0)
        ws.set_row(row, 32)
        for j, column in enumerate(columns):
            ws.write_string(row, col + j, column.header, self.f["header"])
        for i in range(n):
            for j, column in enumerate(columns):
                self.cell(ws, row + 1 + i, col + j, column.values[i], column.kind,
                          estimate=bool(column.marks and column.marks[i]))
        last = row + n
        if total:
            last += 1
            for j, column in enumerate(columns):
                value = total.get(column.header, "")
                if value == "" or value is None:
                    ws.write_blank(last, col + j, None, self.fmt(column.kind, total=True))
                else:
                    self.cell(ws, last, col + j, value, column.kind, total=True,
                              estimate=bool(total_marks and total_marks.get(column.header)))
        for j, column in enumerate(columns):
            if column.kind in ("growth", "pp"):
                ws.conditional_format(row + 1, col + j, last, col + j,
                                      {"type": "cell", "criteria": "<", "value": 0,
                                       "format": self.f["neg"]})
        if data_bar:
            j = [c.header for c in columns].index(data_bar)
            ws.conditional_format(row + 1, col + j, row + n, col + j,
                                  {"type": "data_bar", "bar_color": SKY, "bar_solid": True,
                                   "bar_no_border": True})
        if heat and n:
            first, last_col = heat
            if growth_heat:
                ws.conditional_format(row + 1, col + first, row + n, col + last_col,
                                      {"type": "3_color_scale", "min_type": "num",
                                       "min_value": -1, "mid_type": "num", "mid_value": 0,
                                       "max_type": "num", "max_value": 1,
                                       "min_color": "#F8CBAD", "mid_color": "#FFFFFF",
                                       "max_color": "#BDD7EE"})
            else:
                ws.conditional_format(row + 1, col + first, row + n, col + last_col,
                                      {"type": "2_color_scale", "min_color": "#FFFFFF",
                                       "max_color": "#9DC3E6"})
        if autofilter and n:
            ws.autofilter(row, col, row + n, col + len(columns) - 1)
        if freeze:
            ws.freeze_panes(row + 1, col + 1)
        for j, column in enumerate(columns):
            width = column.width
            if width is None:
                sample = [str(v) for v in column.values[:500]]
                longest = max((len(s) for s in sample), default=0)
                if column.kind not in ("text",):
                    longest = min(longest, 16)
                width = min(max(len(column.header) * 0.9, longest * 1.1, 8) + 2, 44)
            ws.set_column(col + j, col + j, width)
        return last

    def sheet(self, name: str, tab=None, guide: str = ""):
        ws = self.wb.add_worksheet(name)
        ws.hide_gridlines(2)
        if tab:
            ws.set_tab_color(tab)
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        if guide:
            self.guide.append((name, guide))
        return ws

    # -- the source's own estimates ------------------------------------------------------
    def estimate_note(self, ws, row, metrics: list[Metric] | None = None) -> int:
        """Under a table: what blue figures mean, when a metric shown includes the source's own
        estimates. Returns the row after the note (the same row when there is none)."""
        a, q = self.a, self.q
        marked = [m for m in (a.metrics if metrics is None else metrics) if m.key in a.estimated]
        if not marked:
            return row
        ws.write_string(row, 0, f"Figures in blue include estimates by {q.estimated_by} "
                                f"({', '.join(m.label.lower() for m in marked)}), used as "
                                f"{q.source} gives them; the Source estimates sheet lists each "
                                "one. Shares, growth rates and unit values computed from them "
                                "depend on them too.", self.f["estimate_note"])
        return row + 1

    def edition_note(self, ws, row) -> int:
        """Under a product table: the HS editions of the data, when there is more than one.
        Returns the row after the note (the same row when there is none)."""
        for sentence in edition_sentences(self.a):
            ws.write_string(row, 0, sentence, self.f["line_note"])
            row += 1
        return row

    def estimated_text(self, metric: Metric) -> str:
        """A short note for a total that includes the source's own estimates."""
        e = self.a.estimated.get(metric.key)
        if e is None:
            return ""
        size = (f"{fmt.pct(e.share)} of it" if not is_gap(e.share) and e.share == e.share
                else f"{e.count:,} figure{'' if e.count == 1 else 's'}")
        return f"includes estimates by {self.q.estimated_by} ({size}): see Source estimates"

    # -- kinds --------------------------------------------------------------------------
    @property
    def period_kind(self) -> str:
        return "month" if self.q.monthly else "year"

    def metric_kind(self, metric: Metric) -> str:
        return "money" if metric.kind == "money" else "volume"

    def entity_columns(self, frame: pd.DataFrame, entity: str, partner=None) -> list[Column]:
        """Columns of a partner or product table with the right format each; totals that
        include the source's own estimates are marked (only the given partner's, if one is)."""
        a = self.a
        by_heading = {m.heading: m for m in a.metrics}
        by_label = {m.label: m for m in a.metrics}
        key = "Partner_Code" if entity == "Partner" else "Product_Code"
        columns = []
        for header in frame.columns:
            values = frame[header].tolist()
            if header in by_heading and by_heading[header].key in a.estimated:
                codes = a.estimated[by_heading[header].key].codes(key, partner)
                columns.append(Column(header, values, self.metric_kind(by_heading[header]),
                                      marks=[c in codes for c in frame["Code"]]))
                continue
            if header == "Rank":
                kind = "int"
            elif header == "Code":
                kind = "int" if entity == "Partner" else "text"
                header_text = "Partner code" if entity == "Partner" else "HS code"
                columns.append(Column(header_text, values, kind, 12))
                continue
            elif header == "Name":
                columns.append(Column(entity, values, "text", 30 if entity == "Partner" else 60))
                continue
            elif header in by_heading:
                kind = self.metric_kind(by_heading[header])
            elif header == "Change":
                kind = self.metric_kind(a.metric)
            elif header in ("CAGR", "Real CAGR"):
                kind = "growth"
            elif header == "Share change (pp)":
                kind = "pp"
            elif header == "Share" or header.startswith("Share "):
                kind = "share"
            elif header == "Unit value":
                kind = "unit_value"
            elif header.endswith("with trade"):
                kind = "count"
            elif header.startswith("Peak"):
                kind = self.period_kind
            elif header == "Status":
                kind = "text"
            elif header.rsplit(" ", 1)[0] in by_label:
                kind = self.metric_kind(by_label[header.rsplit(" ", 1)[0]])
            else:
                kind = "text"
            columns.append(Column(self.entity_header(header), values, kind))
        return columns

    def entity_header(self, header: str) -> str:
        if header == "Unit value" and self.q.unit_value:
            volume = next(m for m in self.a.metrics if m.key == self.q.unit_value[1])
            return f"Unit value (USD/{volume.unit or 'unit'})"
        return header

    # -- build ------------------------------------------------------------------------------
    def build(self) -> Path:
        a, q = self.a, self.q
        self.wb.set_properties({
            "title": f"{q.reporter_name} {q.flow.lower()} of {q.product_label}, {q.span}",
            "subject": "International trade query",
            "author": "International Trade Analyzer",
            "comments": q.source_note,
        })
        about = self.sheet("About", NAVY)
        summary = self.sheet("Summary", NAVY, "Key figures, key findings, the totals by "
                                              f"{a.period_word} and the overview chart.")
        self.periodic_sheet()
        if q.monthly:
            self.annual_sheet()
        roles = q.roles.capitalize()
        self.entity_sheet(roles, a.partners, "Partner",
                          f"Every {q.role} over the whole query: totals, share, unit value, "
                          f"growth, change in share and status.", chart=True)
        word = a.period_word
        self.matrix_sheet(f"{roles} by {word}", a.partner_matrix[a.metric.key], "value",
                          "Partner", a.metric,
                          f"{a.metric.label} by {q.role} and {word}, with the total.")
        for metric in a.metrics[1:]:
            self.matrix_sheet(f"{metric.label} by {word}"[:31], a.partner_matrix[metric.key],
                              "value", "Partner", metric,
                              f"{metric.label} by {q.role} and {word}; Missing where the "
                              "source does not report it.")
        self.matrix_sheet(f"Shares by {word}", a.partner_shares, "share", "Partner", a.metric,
                          f"Each {q.role}'s share of the {word}'s total.", chart=True)
        self.matrix_sheet(f"Growth by {word}", a.partner_growth, "growth", "Partner", a.metric,
                          f"Change on the previous {word}, by {q.role}; n/a where the "
                          f"previous {word} had no trade.")
        self.entity_sheet("Products", a.products, "Product",
                          f"Every product over the whole query; one row is one "
                          f"{q.product_level}.")
        self.matrix_sheet(f"Products by {word}", a.product_matrix[a.metric.key], "value",
                          "Product", a.metric, f"{a.metric.label} by product and {word}.")
        if a.focus is not None:
            self.focus_sheets()
        self.gaps_sheet()
        self.estimates_sheet()
        self.raw_sheet()
        self.charts_sheet()
        self.summary_sheet(summary)
        self.about_sheet(about)
        self.wb.close()
        return self.path

    # -- sheets ------------------------------------------------------------------------
    def periodic_sheet(self):
        a, q = self.a, self.q
        name = "Monthly" if q.monthly else "Yearly"
        ws = self.sheet(name, SKY, f"One row per {a.period_word}: totals, growth, unit value, "
                                   f"number of {q.roles}, the largest {q.role} and concentration; "
                                   "growth over the whole period below.")
        columns, totals, marks = self.periodic_columns()
        last = self.table(ws, columns, total=totals, data_bar=a.metric.heading, total_marks=marks)
        block = self.period_growth()
        row = self.estimate_note(ws, last + 2) + 1
        ws.write_string(row, 0, "Growth over the whole period", self.f["section"])
        self.table(ws, block, row=row + 1, freeze=False, autofilter=False)
        self.native_column_chart(ws, f"{a.metric.label} by {a.period_word}",
                                 a.period_totals[a.metric.key], a.metric,
                                 anchor=(row + len(block[0].values) + 4, 0))

    def periodic_columns(self):
        """The by-period table: columns, its total row, and which totals include source
        estimates."""
        a, q, s = self.a, self.q, self.a.summary
        periods = a.periods
        columns = [Column("Month" if q.monthly else "Year", periods, self.period_kind, 10)]
        totals = {columns[0].header: "Total"}
        marks = {}
        for metric in a.metrics:
            series = a.period_totals[metric.key]
            e = a.estimated.get(metric.key)
            columns.append(Column(metric.heading, series.tolist(), self.metric_kind(metric),
                                  marks=[p in e.periods for p in periods] if e else None))
            totals[metric.heading] = s["totals"][metric.key]
            marks[metric.heading] = e is not None
            change = [np.nan] + [growth(series[now], series[before])
                                 for before, now in zip(periods, periods[1:])]
            label = "growth on previous month" if q.monthly else "growth"
            columns.append(Column(f"{metric.label} {label}", change, "growth"))
            if q.monthly:
                same = [growth(series[p], series[p - 100]) if p - 100 in series.index else np.nan
                        for p in periods]
                columns.append(Column(f"{metric.label} growth on same month last year", same,
                                      "growth"))
            if e is not None:
                header = f"{metric.label}: share estimated by {q.estimated_by}"
                columns.append(Column(header, e.by_period.tolist(), "share"))
                totals[header] = e.share
        if a.unit_values is not None:
            header = self.entity_header("Unit value")
            columns.append(Column(header, a.unit_values.tolist(), "unit_value"))
            totals[header] = s.get("unit_value", "")
            change = [np.nan] + [growth(a.unit_values[now], a.unit_values[before])
                                 for before, now in zip(periods, periods[1:])]
            columns.append(Column("Unit value growth", change, "growth"))
        if a.real_totals is not None:
            header = f"{a.metric.label}, constant {a.real_base} prices ({a.metric.unit})"
            columns.append(Column(header, a.real_totals.tolist(), "money"))
            totals[header] = total_of(a.real_totals)
            change = [np.nan] + [growth(a.real_totals[now], a.real_totals[before])
                                 for before, now in zip(periods, periods[1:])]
            columns.append(Column("Real growth", change, "growth"))
        stats = a.period_stats
        role = q.role.capitalize()
        columns += [Column(f"{q.roles.capitalize()}", stats["Partners"].tolist(), "count"),
                    Column(f"Largest {q.role}", stats["Largest"].tolist(), "text", 26),
                    Column(f"{role} share", stats["Largest share"].tolist(), "share"),
                    Column("Top 3 share", stats["Top 3 share"].tolist(), "share"),
                    Column("HHI", stats["HHI"].tolist(), "hhi")]
        totals.update({
            q.roles.capitalize(): s["partners"],
            f"Largest {q.role}": a.partner_names.get(s["top"], "") if s["top"] is not None
            else s["top_share"],
            f"{role} share": s["top_share"], "Top 3 share": s["top3_share"], "HHI": s["hhi"]})
        return columns, totals, marks

    def period_growth(self) -> list[Column]:
        a, s = self.a, self.a.summary
        if len(a.years) < 2:
            reason = ("two complete calendar years are needed" if self.q.monthly
                      else "at least two years are needed")
            return [Column("Measure", ["Growth over the whole period"], "text", 34),
                    Column("Rate", [np.nan], "growth", 14),
                    Column("Basis", [f"n/a: {reason}"], "text", 60)]
        y0, y1 = a.years[0], a.years[-1]
        span = f"{y0} and {y1}" + (" (complete calendar years)" if self.q.monthly else "")
        measures, values, basis = [], [], []
        for metric in a.metrics:
            key = "cagr" if metric is a.metric else f"cagr_{metric.key}"
            measures.append(f"CAGR of {metric.label.lower()}")
            values.append(s.get(key, np.nan))
            basis.append(f"{span}")
        if a.metric is not None:
            measures.append(f"Trend growth of {a.metric.label.lower()}")
            values.append(s["trend"])
            basis.append("log-linear fit over every year" + (" (complete calendar years)"
                                                             if self.q.monthly else ""))
        if a.unit_values is not None:
            measures.append("CAGR of unit value")
            values.append(s.get("cagr_unit_value", np.nan))
            basis.append(span)
        if a.real_totals is not None:
            measures.append(f"CAGR of {a.metric.label.lower()}, constant {a.real_base} prices")
            values.append(s.get("real_cagr", np.nan))
            basis.append(f"{span}; {a.cpi_note}")
        return [Column("Measure", measures, "text", 34), Column("Rate", values, "growth", 14),
                Column("Basis", basis, "text", 70)]

    def annual_sheet(self):
        """Monthly queries: calendar-year totals, for years whose twelve months are known."""
        a, q = self.a, self.q
        ws = self.sheet("Annual totals", SKY, "Calendar-year totals, only for years whose "
                                              "twelve months are all in the query and reported.")
        years = sorted({p // 100 for p in a.periods})
        rows = []
        for year in years:
            months = [year * 100 + m for m in range(1, 13)]
            inside = [m for m in months if m in a.periods]
            missing = [m for m in inside if m in a.missing_periods]
            if missing:
                status = f"Missing: {len(missing)} month(s) not reported"
            elif len(inside) < 12:
                status = f"Partial: {len(inside)} of 12 months in the query"
            else:
                status = "Complete"
            rows.append((year, status))
        columns = [Column("Year", [y for y, _ in rows], "year", 8),
                   Column("Status", [s for _, s in rows], "text", 36)]
        for metric in a.metrics:
            values = []
            for year, status in rows:
                if status == "Complete":
                    values.append(a.annual_totals[metric.key].get(year, np.nan))
                elif status.startswith("Missing"):
                    values.append("Missing")
                else:
                    values.append(np.nan)
            columns.append(Column(metric.heading, values, self.metric_kind(metric)))
        self.table(ws, columns)

    def entity_sheet(self, name, frame: pd.DataFrame, entity: str, guide: str, chart=False):
        a, q, s = self.a, self.q, self.a.summary
        ws = self.sheet(name, SKY, guide)
        columns = self.entity_columns(frame, entity)
        total = {entity: f"All {len(frame)} {q.roles if entity == 'Partner' else 'products'}"}
        for metric in a.metrics:
            total[metric.heading] = s["totals"][metric.key]
        # The rows' part of the total: 100% unless the source's own total holds more
        total["Share"] = ratio(total_of(frame[a.metric.heading]) if len(frame) else 0.0,
                               s["total"])
        if "CAGR" in frame:
            total["CAGR"] = s["cagr"]
        last = self.table(ws, columns, total=total,
                          data_bar=a.metric.heading if len(frame) else None,
                          total_marks={m.heading: True for m in a.metrics
                                       if m.key in a.estimated})
        notes = []
        order = a.partner_order if entity == "Partner" else a.product_order
        if order.key != a.metric.key:
            notes.append(f"Listed by {order.label.lower()}, not ranked: "
                         f"{a.metric.label.lower()} is missing for some rows, so their order by "
                         f"{a.metric.label.lower()} cannot be known.")
        if len(a.years) >= 2:
            notes.append(f"CAGR compares {a.years[0]} with {a.years[-1]}; n/a when either year "
                         "has no trade.")
        for i, note in enumerate(notes):
            ws.write_string(last + 2 + i, 0, note, self.f["note"])
        row = self.estimate_note(ws, last + 2 + len(notes))
        if entity == "Product":
            self.edition_note(ws, row)
        if chart and len(frame):
            self.native_bar_chart(ws, frame, anchor=(1, len(columns) + 1))

    def matrix_sheet(self, name, matrix: pd.DataFrame, kind, entity, metric: Metric, guide,
                     chart=False):
        a = self.a
        ws = self.sheet(name[:31], SKY, guide)
        names = a.partner_names if entity == "Partner" else a.product_names
        columns = []
        if entity == "Product":
            columns.append(Column("HS code", list(matrix.index), "text", 10))
        columns.append(Column(entity, [names.get(c, str(c)) for c in matrix.index], "text",
                              30 if entity == "Partner" else 50))
        first = len(columns)
        prefix = {"share": "Share ", "growth": "Growth "}.get(kind, "")
        cell_kind = {"share": "share", "growth": "growth"}.get(kind, self.metric_kind(metric))
        # Value cells that include the source's own estimates are marked
        e = a.estimated.get(metric.key) if kind == "value" else None
        cells = e.cells("Partner_Code" if entity == "Partner" else "Product_Code") if e else set()
        for period in matrix.columns:
            label = period_label(period, self.q.monthly, short=True)
            columns.append(Column(f"{prefix}{label}", matrix[period].tolist(), cell_kind, 12,
                                  marks=[(c, period) in cells for c in matrix.index]
                                  if cells else None))
        total = None
        total_marks = None
        if kind == "value":
            row_totals = [total_of(matrix.loc[c]) for c in matrix.index]
            columns.append(Column("Total", row_totals, cell_kind, 14,
                                  marks=[any((c, p) in cells for p in matrix.columns)
                                         for c in matrix.index] if cells else None))
            if len(a.years) >= 2:
                columns.append(Column(f"CAGR {a.years[0]}–{a.years[-1]}",
                                      [self.entity_cagr(matrix.loc[c]) for c in matrix.index],
                                      "growth", 13))
            # The total row is the query's total for each period, the source's own where it
            # gives one; the rows above may not add up to it (see the checks on About)
            totals = a.period_totals[metric.key]
            total = {entity: "Total"}
            for i, period in enumerate(matrix.columns):
                total[columns[first + i].header] = totals[period]
            total["Total"] = total_of(totals)
            if e is not None:
                total_marks = {columns[first + i].header: period in e.periods
                               for i, period in enumerate(matrix.columns)}
                total_marks["Total"] = bool(e.periods)
        last = self.table(ws, columns, total=total, heat=(first, first + len(matrix.columns) - 1),
                          growth_heat=(kind == "growth"), total_marks=total_marks)
        row = self.estimate_note(ws, last + 2, [metric]) if e is not None else last + 2
        if entity == "Product":
            self.edition_note(ws, row)
        if chart and kind == "share":
            self.native_share_chart(ws, matrix, anchor=(len(matrix) + 4, 1))

    def entity_cagr(self, row: pd.Series):
        annual = self.a._annual_row(row)
        return cagr(annual[self.a.years[0]], annual[self.a.years[-1]], self.a.span_years)

    def focus_sheets(self):
        a, q = self.a, self.q
        code = q.partner_code
        name = a.partner_names[code]
        ws = self.sheet("Partner focus", ACCENT, f"{name} by {a.period_word}: value, share, "
                                                 f"rank and growth against all {q.roles}.")
        frame = a.focus
        columns = []
        for header in frame.columns:
            values = frame[header].tolist()
            if header == "Period":
                columns.append(Column("Month" if q.monthly else "Year", values, self.period_kind,
                                      10))
            elif header == "Rank":
                columns.append(Column("Rank", values, "int", 7))
            elif header == "Share":
                columns.append(Column("Share", values, "share"))
            elif header.endswith("growth"):
                columns.append(Column(header, values, "growth"))
            elif header == "Growth gap (pp)":
                columns.append(Column(header, values, "pp"))
            elif header.endswith("unit value"):
                columns.append(Column(self.entity_header("Unit value").replace(
                    "Unit value", header), values, "unit_value"))
            else:
                metric = next((m for m in a.metrics if header.endswith(m.heading)), a.metric)
                e = a.estimated.get(metric.key)
                marks = None
                if e is not None:
                    cells = e.cells("Partner_Code")
                    marks = ([(code, p) in cells for p in frame["Period"]]
                             if header.startswith(f"{name}: ") else
                             [p in e.periods for p in frame["Period"]])
                columns.append(Column(header, values, self.metric_kind(metric), marks=marks))
        last = self.table(ws, columns)
        self.estimate_note(ws, last + 2)
        ws = self.sheet("Partner products", ACCENT, f"The products traded with {name}.")
        last = self.table(ws, self.entity_columns(a.focus_products, "Product", partner=code),
                          data_bar=a.metric.heading if len(a.focus_products) else None)
        self.edition_note(ws, self.estimate_note(ws, last + 2))

    def gaps_sheet(self):
        a, q = self.a, self.q
        gaps = self.data.gaps.copy()
        period_rows = [{"Period": p, "Partner": "All", "HS code": "All", "Product": "All",
                        "Metric": "All", "Reason": reason}
                       for p, reason in sorted(a.missing_periods.items())]
        if period_rows:
            gaps = pd.concat([pd.DataFrame(period_rows), gaps], ignore_index=True)
        if gaps.empty:
            return
        ws = self.sheet("Data gaps", "#C55A11", "Every data point the source does not report: "
                                                 "the program leaves each one Missing and never "
                                                 "estimates it.")
        if len(gaps) > SHEET_ROW_LIMIT:
            path = self.path.parent / "data_gaps.csv"
            gaps.to_csv(path, index=False, encoding="utf-8-sig")
            ws.write_string(0, 0, f"{len(gaps):,} data gaps, more than this sheet holds; they "
                                  f"are listed in {path.name} next to this workbook.",
                            self.f["note"])
            self.files["Data gaps"] = path.name
            return
        columns = []
        for header in gaps.columns:
            values = gaps[header].tolist()
            kind = (self.period_kind if header == "Period" else
                    "money" if "USD" in header else "text")
            columns.append(Column(header, values, kind,
                                  {"Product": 50, "Reason": 60, "Partner": 26}.get(header)))
        self.table(ws, columns)

    def estimates_sheet(self):
        """Every figure the source itself estimated: part of the database, used as given."""
        q = self.q
        estimates = self.data.estimates
        if estimates.empty:
            return
        ws = self.sheet("Source estimates", BLUE,
                        f"Every figure {q.estimated_by} estimated rather than {q.reporter_name} "
                        f"reported. They are part of {q.source}: the analysis uses each one as "
                        f"{q.source} gives it, and the tables show the figures that include "
                        "them in blue.")
        if len(estimates) > SHEET_ROW_LIMIT:
            path = self.path.parent / "source_estimates.csv"
            estimates.to_csv(path, index=False, encoding="utf-8-sig")
            ws.write_string(0, 0, f"{len(estimates):,} estimated figures, more than this sheet "
                                  f"holds; they are listed in {path.name} next to this workbook.",
                            self.f["note"])
            self.files["Source estimates"] = path.name
            return
        columns = []
        for header in estimates.columns:
            values = estimates[header].tolist()
            kind = (self.period_kind if header == "Period" else
                    "money" if "USD" in header else
                    "volume" if header == "Estimated figure" else "text")
            columns.append(Column(header, values, kind,
                                  {"Product": 50, "Partner": 26, "Source flag": 20}.get(header)))
        self.table(ws, columns)

    def raw_sheet(self):
        a, q = self.a, self.q
        raw = self.data.raw
        ws = self.sheet("Raw data", GREY, "The query at full detail as the source delivers it; "
                                          "values the source does not report say Missing.")
        if len(raw) > SHEET_ROW_LIMIT:
            path = self.path.parent / "raw_data.csv"
            out = raw.copy()
            for column in self.data.raw_metrics:
                out[column] = out[column].astype(object).where(out[column].notna(), "Missing")
            out.to_csv(path, index=False, encoding="utf-8-sig")
            ws.write_string(0, 0, f"The query returned {len(raw):,} rows, more than one sheet "
                                  f"holds ({SHEET_ROW_LIMIT:,} here). Every row is in "
                                  f"{path.name} next to this workbook.", self.f["note"])
            self.files["Raw data"] = path.name
            return
        headers = [str(c) for c in raw.columns]
        metrics = set(self.data.raw_metrics)
        kinds = []
        for column in raw.columns:
            series = raw[column]
            if column in metrics or pd.api.types.is_float_dtype(series):
                kinds.append("money" if "USD" in str(column) or "value" in str(column).lower()
                             else "volume")
            elif pd.api.types.is_integer_dtype(series):
                kinds.append("int")
            else:
                kinds.append("text")
        ws.add_table(0, 0, max(len(raw), 1), len(headers) - 1, {
            "columns": [{"header": h, "header_format": self.f["header"]} for h in headers],
            "style": "Table Style Light 1", "name": "RawData", "autofilter": True})
        ws.set_row(0, 32)
        for i, record in enumerate(raw.itertuples(index=False), start=1):
            for j, value in enumerate(record):
                column = raw.columns[j]
                if column in metrics and (value is None or (isinstance(value, float)
                                                            and np.isnan(value))):
                    ws.write_string(i, j, "Missing", self.fmt(kinds[j], gap=True))
                elif value is None or (isinstance(value, float) and np.isnan(value)):
                    ws.write_blank(i, j, None)
                elif isinstance(value, (bool, np.bool_)):
                    ws.write_boolean(i, j, bool(value))
                elif isinstance(value, (int, float, np.integer, np.floating)):
                    ws.write_number(i, j, float(value), self.fmt(kinds[j]))
                else:
                    ws.write_string(i, j, str(value))
        ws.freeze_panes(1, 0)
        for j, column in enumerate(raw.columns):
            longest = raw[column].astype(str).str.len().head(2000).max() if len(raw) else 8
            ws.set_column(j, j, min(max(len(str(column)) * 0.95, longest * 1.05, 8) + 2,
                                    60 if longest > 40 else 30))

    def charts_sheet(self):
        if not self.charts:
            return
        ws = self.sheet("Charts", ACCENT, "Every chart of the report; the PNG files are in the "
                                          "charts folder.")
        row = 0
        for path in self.charts:
            ws.write_string(row, 0, path.stem.split("_", 1)[1].replace("_", " ").capitalize(),
                            self.f["section"])
            row += self.image(ws, path, row + 1, 0, 1100) + 3

    def image(self, ws, path: Path, row, col, width_px) -> int:
        import matplotlib.image as mpimg
        height, width = mpimg.imread(path).shape[:2]
        scale = width_px / (width * 96 / 200)          # charts are saved at 200 dpi
        ws.insert_image(row, col, str(path), {"x_scale": scale, "y_scale": scale,
                                              "object_position": 1})
        return int(height * 96 / 200 * scale / 20) + 1   # rows covered, at 20 px a row

    # -- native, editable charts --------------------------------------------------------
    def helper(self):
        """A hidden sheet with the numbers the native charts read; gaps are #N/A."""
        if self.chart_data is None:
            self.chart_data = self.wb.add_worksheet("ChartData")
            self.chart_data.hide()
        return self.chart_data

    def put_series(self, labels, values) -> tuple[int, int, int]:
        """Write labels and values into the helper sheet; returns (first row, last row, col)."""
        ws = self.helper()
        start = self.chart_row
        for i, (label, value) in enumerate(zip(labels, values)):
            ws.write_string(start + i, 0, str(label))
            if is_gap(value) or value is None or (isinstance(value, float) and np.isnan(value)):
                ws.write_formula(start + i, 1, "=NA()", None, "#N/A")
            else:
                ws.write_number(start + i, 1, float(value))
        self.chart_row += len(labels) + 1
        return start, start + len(labels) - 1, 1

    def native_column_chart(self, ws, title, series: pd.Series, metric: Metric, anchor):
        labels = [period_label(p, self.q.monthly, short=True) for p in series.index]
        first, last, col = self.put_series(labels, series.tolist())
        chart = self.wb.add_chart({"type": "column"})
        chart.add_series({"name": title,
                          "categories": ["ChartData", first, 0, last, 0],
                          "values": ["ChartData", first, col, last, col],
                          "fill": {"color": NAVY}, "gap": 60})
        self.style_chart(chart, f"{title} ({metric.unit or 'source units'})")
        chart.show_na_as_empty_cell()
        ws.insert_chart(anchor[0], anchor[1], chart, {"x_scale": 1.6, "y_scale": 1.2})

    def native_bar_chart(self, ws, frame: pd.DataFrame, anchor):
        a = self.a
        top = frame.head(TOP_N)
        labels = top["Name"].tolist()[::-1]
        values = top[a.metric.heading].tolist()[::-1]
        first, last, col = self.put_series(labels, values)
        chart = self.wb.add_chart({"type": "bar"})
        chart.add_series({"name": a.metric.heading,
                          "categories": ["ChartData", first, 0, last, 0],
                          "values": ["ChartData", first, col, last, col],
                          "fill": {"color": NAVY}, "gap": 50})
        self.style_chart(chart, f"Top {len(top)} {self.q.roles}: {a.metric.heading}")
        chart.show_na_as_empty_cell()
        ws.insert_chart(anchor[0], anchor[1], chart, {"x_scale": 1.4, "y_scale": 1.3})

    def native_share_chart(self, ws, shares: pd.DataFrame, anchor):
        a = self.a
        codes = list(shares.index[:5])
        rest = [c for c in shares.index if c not in codes]
        labels = [period_label(p, self.q.monthly, short=True) for p in shares.columns]
        chart = self.wb.add_chart({"type": "column", "subtype": "percent_stacked"})
        rows = [(a.partner_names.get(c, str(c)), shares.loc[c].tolist()) for c in codes]
        if rest:
            rows.append(("All others", [total_of(shares.loc[rest, p]) for p in shares.columns]))
        for (name, values), colour in zip(rows, SERIES):
            first, last, col = self.put_series(labels, values)
            chart.add_series({"name": name, "categories": ["ChartData", first, 0, last, 0],
                              "values": ["ChartData", first, col, last, col],
                              "fill": {"color": colour}, "gap": 50})
        self.style_chart(chart, f"Shares by {self.q.role} and {a.period_word}")
        chart.show_na_as_empty_cell()
        ws.insert_chart(anchor[0], anchor[1], chart, {"x_scale": 1.8, "y_scale": 1.3})

    @staticmethod
    def style_chart(chart, title):
        chart.set_title({"name": title, "name_font": {"size": 11, "bold": True,
                                                      "color": "#1A1A1A"}})
        chart.set_legend({"position": "bottom"})
        chart.set_chartarea({"border": {"none": True}})
        chart.set_x_axis({"num_font": {"size": 9}})
        chart.set_y_axis({"num_font": {"size": 9}, "major_gridlines": {
            "visible": True, "line": {"color": "#E6E6E6"}}})

    # -- front sheets ---------------------------------------------------------------------
    def summary_sheet(self, ws):
        a, q, s = self.a, self.q, self.a.summary
        widths = [30, 20, 46, 14, 14, 14, 14, 14, 14]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)
        ws.write_string(0, 0, f"{q.reporter_name} · {q.flow} · {q.product_label} · {q.span}",
                        self.f["title"])
        focus = f" · focus on {a.partner_names.get(q.partner_code)}" if a.focus is not None \
            else ""
        ws.write_string(1, 0, f"{q.source} · all {q.roles}{focus}", self.f["subtitle"])

        def section(row, title):
            for col in range(len(widths)):
                ws.write_string(row, col, title if col == 0 else "", self.f["section"])

        section(3, "Key figures")
        m = a.metric
        kpis = [(f"Total {m.label.lower()}, {q.span}", s["total"], m),
                (f"Average per {a.period_word}", s["average"], m)]
        rows = []
        for i, (label, value, metric) in enumerate(kpis):
            rows.append((label, value, self.amount_format(value, metric),
                         "" if i or is_gap(value) else self.estimated_text(metric)))
        if len(a.years) >= 2:
            rows.append((f"CAGR of {m.label.lower()}", s["cagr"], NUMBER_FORMATS["growth"],
                         f"{a.years[0]} to {a.years[-1]}"))
            rows.append(("Trend growth", s["trend"], NUMBER_FORMATS["growth"],
                         "log-linear fit over every year"))
            if "real_cagr" in s:
                rows.append((f"CAGR at constant {a.real_base} prices", s["real_cagr"],
                             NUMBER_FORMATS["growth"], "deflated by the US consumer price index"))
        peak_period, peak_value = s["peak"]
        if peak_period is not None:
            rows.append((f"Peak {a.period_word}", period_label(peak_period, q.monthly), None,
                         fmt.amount(peak_value, m)))
        for metric in a.metrics[1:]:
            rows.append((f"Total {metric.label.lower()}", s["totals"][metric.key],
                         self.amount_format(s["totals"][metric.key], metric),
                         "Missing for part of the data: see Data gaps"
                         if is_gap(s["totals"][metric.key]) else self.estimated_text(metric)))
        if "unit_value" in s:
            rows.append((self.entity_header("Unit value"), s["unit_value"], "#,##0.00", ""))
        rows += [(q.roles.capitalize(), s["partners"], "0", ""),
                 (f"Largest {q.role}", a.partner_names.get(s["top"], "") if s["top"] is not None
                  else s["top_share"], None,
                  f"{fmt.pct(s['top_share'])} of the total" if not is_gap(s["top_share"]) else ""),
                 ("Top 3 share", s["top3_share"], "0.0%", ""),
                 ("HHI, whole period", s["hhi"], "#,##0", hhi_band(s["hhi"]))]
        row = 4
        for label, value, number_format, note in rows:
            ws.set_row(row, 22)
            ws.write_string(row, 0, label, self.f["kpi_label"])
            if is_gap(value):
                ws.write_string(row, 1, value, self.fmt("text", gap=True, kpi=True))
            elif value is None or (isinstance(value, float) and np.isnan(value)):
                ws.write_string(row, 1, fmt.NOT_DEFINED, self.fmt("text", na=True, kpi=True))
            elif isinstance(value, str):
                ws.write_string(row, 1, value, self.fmt("text", kpi=True))
            else:
                kpi_format = self.wb.add_format({**self.base, "bold": True, "font_size": 14,
                                                 "font_color": NAVY, "align": "left",
                                                 "num_format": number_format or "General"})
                ws.write_number(row, 1, float(value), kpi_format)
            ws.write_string(row, 2, note, self.f["kpi_label"])
            row += 1
        row += 1
        section(row, "Key findings")
        for sentence in findings(a):
            row += 1
            ws.merge_range(row, 0, row, len(widths) - 1, f"•  {sentence}", self.f["wrap"])
            ws.set_row(row, 15 * (len(sentence) // 150 + 1) + 4)
        row += 2
        section(row, f"Totals by {a.period_word}")
        columns, _, _ = self.periodic_columns()
        keep = [c for c in columns if "growth" not in c.header.lower() or
                c.header == f"{m.label} growth"]
        compact = [c._replace(width=widths[i] if i < len(widths) else 14)
                   for i, c in enumerate(keep[:9])]
        last = self.table(ws, compact, row=row + 1, freeze=False, autofilter=False)
        last = self.estimate_note(ws, last + 1) - 1
        overview = next((c for c in self.charts if c.name.startswith("01_")), None)
        if overview:
            section(last + 2, "Overview")
            self.image(ws, overview, last + 3, 0, 1000)

    @staticmethod
    def amount_format(value, metric: Metric) -> str:
        """A key figure's Excel format: the number in the metric's unit, then the unit."""
        return f'#,##0.000" {metric.unit}"' if metric.unit else "#,##0.000"

    def about_sheet(self, ws):
        a, q = self.a, self.q
        ws.set_column(0, 0, 26)
        ws.set_column(1, 1, 120)
        ws.write_string(0, 0, "International trade query", self.f["title"])
        ws.write_string(1, 0, f"Generated {dt.date.today():%d %B %Y} by the International Trade "
                              "Analyzer", self.f["subtitle"])
        row = 3

        def section(title):
            nonlocal row
            ws.write_string(row, 0, title, self.f["section"])
            ws.write_string(row, 1, "", self.f["section"])
            row += 1

        def item(label, text):
            nonlocal row
            ws.write_string(row, 0, label, self.f["label"])
            ws.write_string(row, 1, str(text), self.f["wrap"])
            ws.set_row(row, 15 * (len(str(text)) // 135 + 1) + 3)
            row += 1

        section("Query")
        item("Data source", q.source_description or q.source)
        item("Reporter", f"{q.reporter_name} (code {q.reporter_code})")
        item("Trade flow", f"{q.flow}; partners are {q.roles}")
        item("Product", f"{q.product_label}; one product row is one {q.product_level}; "
                        f"{a.summary['products']} in the data")
        item("Partners", f"All {q.roles}" + (f"; focus on {a.partner_names[q.partner_code]}"
                                             if a.focus is not None else ""))
        item("Period", f"{q.span}, {len(a.periods)} {a.period_word}s"
                       + (", monthly" if q.monthly else ", annual"))
        item("HS edition", edition_summary(a))
        for sentence in edition_sentences(a):
            item("HS editions differ", sentence)
        item("Measured by", f"{a.metric.heading}; also reported: "
                            + (", ".join(m.heading for m in a.metrics[1:]) or "nothing else"))
        item("Where the figures come from", figures_note(a))
        if self.data.raw_note:
            item("Raw data", self.data.raw_note)
        item("Files", "; ".join(f"{k}: {v}" for k, v in self.files.items()))
        row += 1
        section("Missing data")
        item("Policy", "Figures are shown as the source reports them. Where the source has no "
                       "value, the cell says Missing, and so does every total, share, unit value "
                       "and growth rate that depends on it. The program never estimates, "
                       "interpolates or fills in a missing value.")
        for rule in q.missing_rules:
            item("Recognised as missing", rule)
        item("n/a", "Not defined, for example growth from a period without trade, or a CAGR "
                    "whose first or last year has no trade.")
        if any(m.unit_column for m in a.metrics):
            item("Mixed units", "Quantities recorded in different units, which cannot be added.")
        if q.estimate_rules or a.estimated:
            row += 1
            section("Estimates in the source")
            item("Policy", f"A figure {q.source} itself marks as an estimate is part of the "
                           f"database, so the analysis uses it as {q.source} gives it and says "
                           "so: every figure that includes one is shown in blue in the tables, "
                           f"the {'Monthly' if q.monthly else 'Yearly'} sheet gives the share of "
                           "each total they make up, and the Source estimates sheet lists each "
                           "one. The program itself never estimates anything.")
            for rule in q.estimate_rules:
                item("Recognised as an estimate", rule)
            found = []
            for metric in a.metrics:
                e = a.estimated.get(metric.key)
                if e is not None:
                    found.append(f"{metric.label}: {e.count:,} figure{'' if e.count == 1 else 's'}"
                                 + (f", {fmt.pct(e.share)} of the total"
                                    if not is_gap(e.share) and e.share == e.share else ""))
            item("In this query", "; ".join(found) if found else
                 "None of the figures analysed is marked as an estimate.")
        row += 1
        section("Definitions")
        for metric in a.metrics:
            if metric.kind == "money":
                text = f"{metric.heading}, in current US dollars, not adjusted for inflation"
            elif metric.unit_column:        # a quantity, in the unit the source gives
                name = q.unit_names.get(metric.unit)
                text = (f"{metric.heading}" + (f": {metric.unit} is {name.lower()}" if name
                                               else "")
                        + f", as {q.source} reports it. Quantities in different units are "
                          "never added together.")
            else:
                text = metric.heading
            item(metric.label, text)
        if a.unit_values is not None:
            money, volume = (next(m for m in a.metrics if m.key == key)
                             for key in self.q.unit_value)
            item("Unit value", f"{money.label} divided by {volume.label.lower()}, for the same "
                               f"rows, in USD per {volume.unit or 'unit'}.")
        item("Share", f"A {q.role}'s or product's part of the total of the same {a.period_word} "
                      "(or of the whole query).")
        item("Growth", f"Change on the previous {a.period_word}: this {a.period_word} / the "
                       f"previous one − 1." + (" Monthly data also compares each month with the "
                                               "same month a year earlier." if q.monthly else ""))
        item("CAGR", "Compound annual growth rate: (last year / first year)^(1 / years between) − "
                     "1. It depends on the two end years only."
                     + (" Monthly data uses complete calendar years." if q.monthly else ""))
        item("Trend growth", "Annual growth of a log-linear trend fitted to every year; steadier "
                             "than CAGR when an end year is unusual. Needs trade in every year.")
        if a.real_totals is not None:
            item("Constant dollars", f"Values deflated to {a.real_base} prices with the US "
                                     f"consumer price index ({a.cpi_note}). Years without a "
                                     "published index are Missing.")
        item("HHI", "Herfindahl-Hirschman index: the sum of squared shares x 10,000. Below 1,500 "
                    "unconcentrated, 1,500 to 2,500 moderately concentrated, above 2,500 highly "
                    "concentrated.")
        item("Status", "Continuing: trade in the first and last period. New: none in the first. "
                       "Lost: none in the last. Intermittent: trade only in between. Unknown: "
                       "the first or last period is not reported by the source.")
        row += 1
        section("Checks")
        for check, result in self.checks():
            item(check, result)
        row += 1
        section("Sheets")
        for name, text in self.guide:
            ws.write_url(row, 0, f"internal:'{name}'!A1", self.f["link"], string=name)
            ws.write_string(row, 1, text, self.f["wrap"])
            row += 1

    def checks(self) -> list[tuple[str, str]]:
        a, q, m = self.a, self.q, self.a.metric
        out = list(q.checks)
        total = total_of(a.period_totals[m.key])
        unit = f" {m.unit}" if m.unit else ""
        for label, matrix in ((f"{q.roles.capitalize()} add up to the total",
                               a.partner_matrix[m.key]),
                              ("Products add up to the total", a.product_matrix[m.key])):
            parts = total_of([total_of(matrix.loc[code]) for code in matrix.index])
            if is_gap(parts) or is_gap(total):
                out.append((label, f"Not checked for {m.label.lower()}: it is missing for part "
                                   "of the data."))
            else:
                ok = bool(np.isclose(number(parts), number(total), rtol=1e-6, atol=0.01))
                out.append((label, f"{'Yes' if ok else 'NO'} for {m.label.lower()}: "
                                   f"{number(parts):,.2f}{unit} against a total of "
                                   f"{number(total):,.2f}{unit}"
                                   + ("" if ok or a.total_rows is None else
                                      f", which is {q.source}'s own total")))
        missing = sorted(a.missing_periods)
        out.append((f"{a.period_word.capitalize()}s covered",
                    f"{len(a.periods) - len(missing)} of {len(a.periods)} have data"
                    + (f"; none for {', '.join(period_label(p, q.monthly) for p in missing)}"
                       if missing else "")))
        for metric, levels in a.gap_levels():
            detail = gap_detail(a, metric, levels)
            if detail:
                out.append((f"{metric.label} missing", f"{detail}; see Data gaps."))
        records = f"{len(a.rows):,} product records"
        if a.separate:
            records += f", {len(a.partner_rows):,} records for {q.product_code} by {q.role}"
        if a.total_rows is not None:
            records += f", {len(a.total_rows):,} totals (partner World)"
        out.append(("Records", f"{records}; {a.summary['partners']} {q.roles}; "
                               f"{a.summary['products']} products"))
        return out


def write_workbook(path: Path, a: Analysis, data: QueryData, charts: list[Path],
                   files: dict[str, str]) -> Path:
    return Book(path, a, data, charts, files).build()
