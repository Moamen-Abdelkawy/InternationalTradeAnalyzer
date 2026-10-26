"""The Excel workbook of a partner report: the trade with the partner, its place among the
reporter's partners, its competitors, prices and products, the reporter's place in the
partner's trade, the two countries' figures for the same trade (COMTRADE), the trade the other
way, the data gaps and the source rows of each view. Cells the source does not report say
'Missing'; figures that include the source's own estimates are shown in blue."""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from xlsxwriter.utility import xl_col_to_name

from .. import fmt
from ..analysis import Analysis, growth, hhi_band, is_gap, number, ratio, total_of
from ..findings import edition_sentences, edition_summary, figures_note
from ..model import QueryData, period_label
from ..workbook import ACCENT, BLUE, NAVY, NUMBER_FORMATS, SHEET_ROW_LIMIT, Book, Column
from .analysis import PartnerAnalysis
from .findings import Terms, findings, known, other_sentence, side_sentence

HIGHLIGHT = "#FCE4D6"       # the row of the partner (or of the reporter, in the partner's data)
# The Raw data sheet of each other view: sheet, Excel table and CSV file names
RAW_SHEETS = {"side": ("Raw data, partner side", "RawPartnerSide", "raw_partner_side.csv"),
              "other": ("Raw data, other direction", "RawOtherDirection",
                        "raw_other_direction.csv")}


class PartnerBook(Book):
    def __init__(self, path: Path, pa: PartnerAnalysis, data: QueryData, charts: list[Path],
                 files: dict[str, str]):
        super().__init__(path, pa.a, data, charts, files)
        self.pa = pa
        self.t = Terms(pa)
        self.f["highlight"] = self.wb.add_format({"bg_color": HIGHLIGHT})

    def view(self, analysis: Analysis, data: QueryData | None = None) -> PartnerBook:
        """This book seen through another view of the trade, for that view's tables: the same
        workbook and formats, that view's analysis, query and data."""
        other = copy.copy(self)
        other.a, other.q = analysis, analysis.q
        if data is not None:
            other.data = data
        return other

    def views(self):
        """(which, label, query, data, analysis) of each other view of the trade that has
        data: 'side' or 'other' (see PartnerAnalysis)."""
        pa, t, out = self.pa, self.t, []
        pairs = self.data.partner_views
        for which, query, analysis in (("side", pa.side_query, pa.side),
                                       ("other", pa.other_query, pa.other)):
            pair = getattr(pairs, which) if pairs else None
            if query is None or pair is None:
                continue
            label = (f"{t.partner}'s {t.side_flow}, every country" if which == "side" else
                     f"{t.reporter}'s {t.other_flow} {t.other_to} {t.partner}")
            out.append((which, label, query, pair[1], analysis))
        return out

    def highlight(self, ws, first_row, last_row, columns: int, code_col: int, code):
        """Shade the row whose code (in code_col) is the given one."""
        if last_row < first_row:
            return
        letter = xl_col_to_name(code_col)
        ws.conditional_format(first_row, 0, last_row, columns - 1, {
            "type": "formula", "criteria": f"=${letter}{first_row + 1}={code}",
            "format": self.f["highlight"]})

    def note(self, ws, row, text, style="note") -> int:
        ws.write_string(row, 0, text, self.f[style])
        return row + 1

    # -- build ------------------------------------------------------------------------------
    def build(self) -> Path:
        pa, q, t = self.pa, self.q, self.t
        self.wb.set_properties({
            "title": f"{t.reporter} {t.flow} {t.to} {t.partner}: {q.product_label}, {q.span}",
            "subject": "International trade query: one partner",
            "author": "International Trade Analyzer",
            "comments": q.source_note,
        })
        about = self.sheet("About", NAVY)
        summary = self.sheet("Summary", NAVY, "Key figures, key findings, the figures by "
                                              f"{pa.period_word} and the overview chart.")
        self.trade_sheet()
        if q.monthly:
            self.months_annual_sheet()
        self.position_sheet()
        self.competitors_sheet()
        if pa.unit_values is not None and pa.traded:
            self.prices_sheet()
        if pa.products is not None:
            self.products_sheets()
        self.side_sheet()
        if pa.mirror:
            self.mirror_sheet()
        self.other_sheet()
        self.partner_gaps_sheet()
        self.partner_estimates_sheet()
        self.comtrade_check_sheet()
        self.raw_sheet()
        for which, label, query, data, analysis in self.views():
            if len(data.raw):
                name, table, file = RAW_SHEETS[which]
                self.view(analysis or self.a, data).raw_sheet(
                    name, table, file, f"The data on {label} at full detail, as the source "
                                       "delivers it; values the source does not report say "
                                       "Missing.")
        self.charts_sheet()
        self.summary_sheet(summary)
        self.about_sheet(about)
        self.wb.close()
        return self.path

    # -- the trade with the partner ----------------------------------------------------------
    def partner_marks(self, metric) -> list | None:
        """Per period: whether the partner's figure includes the source's own estimates."""
        e = self.a.estimated.get(metric.key)
        if e is None:
            return None
        cells = e.cells("Partner_Code")
        return [(self.pa.code, p) in cells for p in self.pa.periods]

    def trade_columns(self):
        """The partner's figures by period: columns, the total row, and which totals include
        source estimates."""
        pa, a, q, t, s = self.pa, self.a, self.q, self.t, self.pa.summary
        periods = pa.periods
        columns = [Column("Month" if q.monthly else "Year", periods, self.period_kind, 10)]
        totals = {columns[0].header: "Total"}
        marks = {}
        pairs = list(zip(periods, periods[1:]))
        for metric in pa.metrics:
            series = pa.series[metric.key]
            flags = self.partner_marks(metric)
            columns.append(Column(metric.heading, series.tolist(), self.metric_kind(metric),
                                  marks=flags))
            totals[metric.heading] = s["totals"][metric.key]
            marks[metric.heading] = bool(flags and any(flags))
            label = "growth on previous month" if q.monthly else "growth"
            columns.append(Column(f"{metric.label} {label}",
                                  [np.nan] + [growth(series[n], series[b]) for b, n in pairs],
                                  "growth"))
            if q.monthly:
                columns.append(Column(f"{metric.label} growth on same month last year",
                                      [growth(series[p], series[p - 100])
                                       if p - 100 in series.index else np.nan for p in periods],
                                      "growth"))
        if pa.unit_values is not None:
            header = self.entity_header("Unit value")
            columns.append(Column(header, pa.unit_values.tolist(), "unit_value"))
            totals[header] = s.get("unit_value", "")
            columns.append(Column("Unit value growth",
                                  [np.nan] + [growth(pa.unit_values[n], pa.unit_values[b])
                                              for b, n in pairs], "growth"))
            header = f"{header}, all {q.roles}"
            columns.append(Column(header, a.unit_values.tolist(), "unit_value"))
            totals[header] = a.summary.get("unit_value", "")
        if pa.real_values is not None:
            header = f"{pa.metric.label}, constant {a.real_base} prices ({pa.metric.unit})"
            columns.append(Column(header, pa.real_values.tolist(), "money"))
            totals[header] = total_of(pa.real_values)
            columns.append(Column("Real growth",
                                  [np.nan] + [growth(pa.real_values[n], pa.real_values[b])
                                              for b, n in pairs], "growth"))
        header = f"Share of {t.reporter}'s {t.flow}"
        columns += [Column(header, pa.position["Share"].tolist(), "share"),
                    Column("Rank", pa.position["Rank"].tolist(), "int", 7)]
        totals[header] = s["share"]
        totals["Rank"] = s["rank"]
        return columns, totals, marks

    def trade_growth(self) -> list[Column]:
        pa, a, s = self.pa, self.a, self.pa.summary
        if len(pa.years) < 2:
            reason = ("two complete calendar years are needed" if self.q.monthly
                      else "at least two years are needed")
            return [Column("Measure", ["Growth over the whole period"], "text", 34),
                    Column("Rate", [np.nan], "growth", 14),
                    Column("Basis", [f"n/a: {reason}"], "text", 60)]
        y0, y1 = pa.years[0], pa.years[-1]
        span = f"{y0} and {y1}" + (" (complete calendar years)" if self.q.monthly else "")
        measures, values, basis = [], [], []
        for metric in pa.metrics:
            key = "cagr" if metric is pa.metric else f"cagr_{metric.key}"
            measures.append(f"CAGR of {metric.label.lower()}, {self.t.partner}")
            values.append(s.get(key, np.nan))
            basis.append(span)
        measures.append(f"CAGR of {pa.metric.label.lower()}, all {self.q.roles}")
        values.append(a.summary["cagr"])
        basis.append(span)
        measures.append(f"Trend growth of {pa.metric.label.lower()}, {self.t.partner}")
        values.append(s["trend"])
        basis.append("log-linear fit over every year" + (" (complete calendar years)"
                                                         if self.q.monthly else ""))
        if pa.unit_values is not None:
            measures.append(f"CAGR of unit value, {self.t.partner}")
            values.append(s.get("cagr_unit_value", np.nan))
            basis.append(span)
        if "real_cagr" in s:
            measures.append(f"CAGR of {pa.metric.label.lower()}, constant {a.real_base} prices")
            values.append(s["real_cagr"])
            basis.append(f"{span}; {a.cpi_note}")
        return [Column("Measure", measures, "text", 44), Column("Rate", values, "growth", 14),
                Column("Basis", basis, "text", 70)]

    def trade_sheet(self):
        pa, q, t = self.pa, self.q, self.t
        name = "Monthly" if q.monthly else "Yearly"
        ws = self.sheet(name, ACCENT, f"The trade with {t.partner}, one row per "
                                      f"{pa.period_word}: each metric and its growth, unit value, "
                                      f"share of {t.reporter}'s {t.flow} and rank; growth over "
                                      "the whole period below.")
        columns, totals, marks = self.trade_columns()
        last = self.table(ws, columns, total=totals, data_bar=pa.metric.heading,
                          total_marks=marks)
        row = self.estimate_note(ws, last + 2, pa.metrics) + 1
        ws.write_string(row, 0, "Growth over the whole period", self.f["section"])
        block = self.trade_growth()
        self.table(ws, block, row=row + 1, freeze=False, autofilter=False)
        self.native_column_chart(ws, f"{pa.metric.label}, {t.partner}, by {pa.period_word}",
                                 pa.series[pa.metric.key], pa.metric,
                                 anchor=(row + len(block[0].values) + 4, 0))

    def months_annual_sheet(self):
        """Monthly queries: calendar-year totals of the trade with the partner and of all the
        reporter's trade, for years whose twelve months are known."""
        pa, a, t = self.pa, self.a, self.t
        ws = self.sheet("Annual totals", ACCENT, "Calendar-year totals, only for years whose "
                                                 "twelve months are all in the query and "
                                                 "reported.")
        rows = []
        for year in sorted({p // 100 for p in pa.periods}):
            months = [year * 100 + m for m in range(1, 13)]
            inside = [m for m in months if m in pa.periods]
            missing = [m for m in inside if m in a.missing_periods]
            status = (f"Missing: {len(missing)} month(s) not reported" if missing else
                      f"Partial: {len(inside)} of 12 months in the query" if len(inside) < 12
                      else "Complete")
            rows.append((year, status))

        def by_year(series) -> list:
            return [pa.annual(series).get(y, np.nan) if s == "Complete" else
                    ("Missing" if s.startswith("Missing") else np.nan) for y, s in rows]

        columns = [Column("Year", [y for y, _ in rows], "year", 8),
                   Column("Status", [s for _, s in rows], "text", 36)]
        for metric in pa.metrics:
            columns.append(Column(f"{metric.heading}, {t.partner}",
                                  by_year(pa.series[metric.key]), self.metric_kind(metric)))
        key = pa.metric.key
        mine = by_year(pa.series[key])
        every = by_year(a.period_totals[key])
        columns += [Column(f"{pa.metric.heading}, all {self.q.roles}", every,
                           self.metric_kind(pa.metric)),
                    Column(f"Share of {t.reporter}'s {t.flow}",
                           [ratio(x, y) for x, y in zip(mine, every)], "share")]
        self.table(ws, columns)

    # -- the partner among the reporter's partners -----------------------------------------
    def position_sheet(self):
        pa, a, q, t = self.pa, self.a, self.q, self.t
        f = pa.position
        m = pa.metric
        ws = self.sheet("Market position", ACCENT,
                        f"{t.partner} among {t.reporter}'s {q.roles}, {pa.period_word} by "
                        f"{pa.period_word}: its share, rank and growth against the total, and "
                        "how much of the total's change it accounts for.")
        e = a.estimated.get(m.key)
        columns = [
            Column("Month" if q.monthly else "Year", f["Period"].tolist(), self.period_kind, 10),
            Column(f"{m.heading}, {t.partner}", f["Figure"].tolist(), self.metric_kind(m),
                   marks=self.partner_marks(m)),
            Column(f"{m.heading}, all {q.roles}", f["Total"].tolist(), self.metric_kind(m),
                   marks=[p in e.periods for p in f["Period"]] if e else None),
            Column(f"Share of {t.reporter}'s {t.flow}", f["Share"].tolist(), "share"),
            Column("Rank", f["Rank"].tolist(), "int", 7),
            Column(f"Growth, {t.partner}", f["Growth"].tolist(), "growth"),
            Column(f"Growth, all {q.roles}", f["Total growth"].tolist(), "growth"),
            Column("Growth gap (pp)", f["Growth gap (pp)"].tolist(), "pp"),
            Column(q.roles.capitalize(), f["Partners"].tolist(), "count"),
            Column(f"Largest {q.role}", f["Largest"].tolist(), "text", 26),
            Column(f"Largest {q.role}'s share", f["Largest share"].tolist(), "share")]
        last = self.table(ws, columns)
        row = self.estimate_note(ws, last + 2, [m]) + 1
        c = pa.contribution
        if c is not None:
            ws.write_string(row, 0, f"Change from {c['y0']} to {c['y1']}", self.f["section"])
            self.table(ws, [
                Column("Measure", [f"Change in {t.flow}, all {q.roles}",
                                   f"Change in {t.flow} {t.to} {t.partner}",
                                   f"{t.partner}'s part of the change"], "text", 44),
                Column(m.heading, [c["total"], c["partner"], ""], self.metric_kind(m), 18),
                Column("Part", ["", "", c["part"]], "share", 12)],
                row=row + 1, freeze=False, autofilter=False)
            row += 6
        self.note(ws, row, f"{t.partner}'s part of the change is its change divided by the "
                           "change of the total; it is above 100% when the other partners "
                           "together moved the other way, and negative when the partner moved "
                           "against the total.")

    def competitors_sheet(self):
        pa, a, q, t = self.pa, self.a, self.q, self.t
        ws = self.sheet("Competitors", ACCENT,
                        f"{t.reporter}'s largest {q.roles} over the whole query, with "
                        f"{t.partner} shaded: totals, share, growth and status; their shares "
                        f"by {pa.period_word} below.")
        frame = pa.competitors
        if frame.empty:
            self.note(ws, 0, f"{q.source} records no {t.flow} of this product by {t.reporter}.")
            return
        columns = self.entity_columns(frame, "Partner")
        total = {"Partner": f"All {a.summary['partners']} {q.roles}"}
        for metric in pa.metrics:
            total[metric.heading] = a.summary["totals"][metric.key]
        total["Share"] = 1.0 if not is_gap(a.summary["total"]) else a.summary["total"]
        if "CAGR" in frame:
            total["CAGR"] = a.summary["cagr"]
        last = self.table(ws, columns, total=total, data_bar=pa.metric.heading,
                          total_marks={m.heading: True for m in pa.metrics
                                       if m.key in a.estimated})
        self.highlight(ws, 1, len(frame), len(columns), 1, pa.code)
        row = self.estimate_note(ws, last + 2) + 1
        codes = ([pa.code] if pa.traded else []) + pa.rivals
        shares = a.partner_shares
        if codes and not shares.empty:
            ws.write_string(row, 0, f"Shares by {pa.period_word}", self.f["section"])
            rest = [c for c in shares.index if c not in codes]
            names = [a.partner_names.get(c, str(c)) for c in codes] + ["All others"]
            cols = [Column("Partner code", codes + [""], "int", 12),
                    Column("Partner", names, "text", 30)]
            for period in pa.periods:
                values = [shares.loc[c, period] for c in codes]
                values.append(total_of(shares.loc[rest, period]) if rest else 0.0)
                cols.append(Column(period_label(period, q.monthly, short=True), values,
                                   "share", 10))
            end = self.table(ws, cols, row=row + 1, freeze=False, autofilter=False)
            self.highlight(ws, row + 2, end, len(cols), 0, pa.code)

    def prices_sheet(self):
        pa, a, q, t = self.pa, self.a, self.q, self.t
        volume = next(m for m in pa.metrics if m.key == q.unit_value[1])
        unit = f"USD/{volume.unit or 'unit'}"
        ws = self.sheet("Prices", ACCENT,
                        f"Unit values in {unit} by {pa.period_word}: {t.partner}, all "
                        f"{q.roles} together and the largest other {q.roles}.")
        rows = a.partners.set_index("Code") if len(a.partners) else None
        columns = [Column("Month" if q.monthly else "Year", pa.periods, self.period_kind, 10),
                   Column(t.partner, pa.unit_values.tolist(), "unit_value", 16),
                   Column(f"All {q.roles}", a.unit_values.tolist(), "unit_value", 16)]
        totals = {columns[0].header: "Whole period", t.partner: pa.summary.get("unit_value"),
                  f"All {q.roles}": a.summary.get("unit_value")}
        for code in pa.rivals:
            name = a.partner_names.get(code, str(code))
            columns.append(Column(name, pa.rival_prices.loc[code].tolist(), "unit_value", 16))
            if rows is not None and "Unit value" in rows:
                totals[name] = rows.loc[code, "Unit value"]
        last = self.table(ws, columns, total=totals)
        row = self.note(ws, last + 2, f"Unit value: {volume.label.lower()} divides value for the "
                                      f"same rows, in {unit}; where either is missing, so is the "
                                      "unit value. It is an average over the products and "
                                      "shipments in each figure, not a price quoted by the "
                                      "source.")
        self.estimate_note(ws, row, [m for m in pa.metrics if m.key in q.unit_value])

    def products_sheets(self):
        pa, a, q, t = self.pa, self.a, self.q, self.t
        frame = pa.products
        ws = self.sheet("Products", ACCENT,
                        f"The products traded with {t.partner} over the whole query: totals, "
                        f"share of the trade with it, and its share of {t.reporter}'s {t.flow} "
                        "of each.")
        columns = []
        unit = pa.metric.unit
        y1 = pa.years[-1] if len(pa.years) >= 2 else None
        renamed = {"Market total": (f"{t.reporter}'s {t.flow}, all {q.roles}"
                                    + (f" ({unit})" if unit else ""), self.metric_kind(pa.metric)),
                   "Market share": (f"{t.partner}'s share of it", "share")}
        if y1 is not None:
            renamed[f"Market share {y1}"] = (f"{t.partner}'s share of it, {y1}", "share")
        for column in self.entity_columns(frame.drop(columns=list(renamed)), "Product",
                                          partner=pa.code):
            columns.append(column)
        for key, (header, kind) in renamed.items():
            columns.append(Column(header, frame[key].tolist(), kind))
        total = {"Product": f"All {len(frame)} products", pa.metric.heading: pa.summary["total"],
                 "Share": 1.0 if not is_gap(pa.summary["total"]) else pa.summary["total"],
                 renamed["Market total"][0]: a.summary["total"],
                 renamed["Market share"][0]: pa.summary["share"]}
        for metric in pa.metrics[1:]:
            total[metric.heading] = pa.summary["totals"][metric.key]
        last = self.table(ws, columns, total=total,
                          data_bar=pa.metric.heading if len(frame) else None)
        row = self.estimate_note(ws, last + 2)
        self.edition_note(ws, row)

        matrix = pa.product_matrix
        word = pa.period_word
        ws = self.sheet(f"Products by {word}", ACCENT,
                        f"{pa.metric.label} by product and {word}, of the trade with "
                        f"{t.partner}.")
        cols = [Column("HS code", list(matrix.index), "text", 10),
                Column("Product", [a.product_names.get(c, str(c)) for c in matrix.index],
                       "text", 50)]
        for period in pa.periods:
            cols.append(Column(period_label(period, q.monthly, short=True),
                               matrix[period].tolist(), self.metric_kind(pa.metric), 12))
        cols.append(Column("Total", [total_of(matrix.loc[c]) for c in matrix.index],
                           self.metric_kind(pa.metric), 14))
        total = {"Product": f"All, {t.partner}"}
        for period in pa.periods:
            total[period_label(period, q.monthly, short=True)] = pa.series[pa.metric.key][period]
        total["Total"] = pa.summary["total"]
        last = self.table(ws, cols, total=total, heat=(2, 1 + len(pa.periods)))
        self.edition_note(ws, self.estimate_note(ws, last + 2, [pa.metric]))

    # -- the reporter in the partner's trade -----------------------------------------------
    def side_sheet(self):
        pa, t = self.pa, self.t
        ws = self.sheet("Partner side", ACCENT,
                        f"{t.reporter} in {t.partner}'s {t.side_flow}, {t.reported_as}: "
                        f"{t.reporter}'s share and rank by {pa.period_word}, and "
                        f"{t.partner}'s largest {t.side_roles}.")
        side, sq = pa.side, pa.side_query
        if side is None:
            self.note(ws, 0, side_sentence(pa, t) or
                      f"{t.partner}'s side of the trade is not available.")
            return
        f = pa.side_position
        m = side.metric
        e = side.estimated.get(m.key)
        cells = e.cells("Partner_Code") if e else set()
        columns = [
            Column("Month" if self.q.monthly else "Year", f["Period"].tolist(),
                   self.period_kind, 10),
            Column(f"{m.heading}, {t.partner}'s {t.side_flow}, all {sq.roles}",
                   f["Total"].tolist(), self.metric_kind(m),
                   marks=[p in e.periods for p in f["Period"]] if e else None),
            Column(f"{m.heading}, {t.partner}'s {t.side_flow} {t.other_to} {t.reporter}",
                   f["Figure"].tolist(), self.metric_kind(m),
                   marks=[(self.q.reporter_code, p) in cells for p in f["Period"]]
                   if e else None),
            Column(f"{t.reporter}'s share", f["Share"].tolist(), "share"),
            Column(f"{t.reporter}'s rank", f["Rank"].tolist(), "int", 9),
            Column(f"{sq.roles.capitalize()} recorded", f["Partners"].tolist(), "count")]
        mine = total_of(f["Figure"])
        whole = side.summary["total"]
        total = {columns[0].header: "Total", columns[1].header: whole, columns[2].header: mine,
                 columns[3].header: ratio(mine, whole)}
        last = self.table(ws, columns, total=total)
        row = self.view(side).estimate_note(ws, last + 2, [m])
        for reason, periods in unreported(sq).items():
            row = self.note(ws, row, f"No data from {t.partner} for "
                                     f"{', '.join(period_label(p, sq.monthly) for p in periods)}"
                                     f": {reason}.")
        table = pa.side_partners
        if table is not None and len(table):
            row += 1
            period = pa.side_partners_period
            ws.write_string(row, 0, f"{t.partner}'s largest {t.side_roles} over the whole query"
                            if period is None else
                            f"{t.partner}'s largest {t.side_roles} in "
                            f"{period_label(period, self.q.monthly)}, the latest "
                            f"{pa.period_word} with every figure reported: the whole query has "
                            "no total, because some periods are not reported", self.f["section"])
            view = self.view(side)
            cols = view.entity_columns(table, "Partner")
            end = self.table(ws, cols, row=row + 1, freeze=False, autofilter=False)
            self.highlight(ws, row + 2, end, len(cols), 1, self.q.reporter_code)

    def mirror_sheet(self):
        pa, t = self.pa, self.t
        ws = self.sheet("Both reports", ACCENT,
                        f"The same trade as each country reports it: {t.reporter}'s {t.flow} "
                        f"{t.to} {t.partner} beside {t.partner}'s {t.side_flow} {t.other_to} "
                        f"{t.reporter}, with the difference.")
        row = 0
        for key, frame in pa.mirror.items():
            metric = next(m for m in pa.metrics if m.key == key)
            ws.write_string(row, 0, metric.heading, self.f["section"])
            kind = self.metric_kind(metric)
            side = pa.side_estimates(key)
            columns = [
                Column("Month" if self.q.monthly else "Year", frame["Period"].tolist(),
                       self.period_kind, 10),
                Column(f"As {t.reporter} reports it", frame["Reporter"].tolist(), kind, 20,
                       marks=self.partner_marks(metric)),
                Column(f"As {t.partner} reports it", frame["Partner"].tolist(), kind, 20,
                       marks=[p in side for p in frame["Period"]] if side else None),
                Column(f"Difference: {t.reporter} − {t.partner}", frame["Difference"].tolist(),
                       kind, 20),
                Column(f"Ratio: {t.reporter} / {t.partner}", frame["Ratio"].tolist(),
                       "unit_value", 16)]
            last = self.table(ws, columns, row=row + 1, freeze=False, autofilter=False)
            row = last + 2
        notes = [f"Each figure is as its country reports it to COMTRADE, without adjustment: "
                 f"{t.reporter}'s {t.flow} are usually valued CIF (with freight and insurance) "
                 f"and {t.partner}'s {t.side_flow} FOB, and the two countries may record a "
                 "shipment in different periods, under different codes or with a different "
                 "partner. The difference is not corrected or explained by the program."]
        for reason, periods in unreported(pa.side_query).items():
            notes.append(f"No data from {t.partner} for "
                         f"{', '.join(period_label(p, self.q.monthly) for p in periods)}: "
                         f"{reason}.")
        for text in notes:
            row = self.note(ws, row, text)
        row = self.estimate_note(ws, row)
        flagged = [m.label.lower() for m in pa.metrics
                   if m.key in pa.mirror and pa.side_estimates(m.key)]
        if flagged:
            self.note(ws, row, f"Figures in blue in the column 'As {t.partner} reports it' are "
                               f"estimates by {pa.side_query.estimated_by} "
                               f"({', '.join(flagged)}), not figures {t.partner} reported; they "
                               f"are used as {self.q.source} gives them, and the Source estimates "
                               "sheet lists each one.", "estimate_note")

    def other_sheet(self):
        pa, q, t = self.pa, self.q, self.t
        ws = self.sheet("Other direction", ACCENT,
                        f"{t.reporter}'s {t.other_flow} {t.other_to} {t.partner} by "
                        f"{pa.period_word}, the balance of trade with it in value, and the "
                        "products.")
        other, oq = pa.other, pa.other_query
        if other is None:
            self.note(ws, 0, other_sentence(pa, t) or "The trade the other way is not available.")
            return
        periods = pa.periods
        pairs = list(zip(periods, periods[1:]))
        columns = [Column("Month" if q.monthly else "Year", periods, self.period_kind, 10)]
        totals = {columns[0].header: "Total"}
        for metric in oq.metrics:
            series = pa.view_series("other", metric.key)
            header = f"{metric.heading}, {t.other_flow} {t.other_to} {t.partner}"
            e = other.estimated.get(metric.key)
            cells = e.cells("Partner_Code") if e else set()
            columns.append(Column(header, series.tolist(), self.metric_kind(metric),
                                  marks=[(pa.code, p) in cells for p in periods] if e else None))
            totals[header] = total_of(series)
            columns.append(Column(f"{metric.label} growth",
                                  [np.nan] + [growth(series[n], series[b]) for b, n in pairs],
                                  "growth"))
        if pa.balance is not None:
            value = next(m for m in pa.metrics if m.key == "value")
            header = f"Balance, {value.unit}: exports − imports"
            columns.append(Column(header, pa.balance.tolist(), "money", 18))
            totals[header] = total_of(pa.balance)
        last = self.table(ws, columns, total=totals)
        row = self.view(other).estimate_note(ws, last + 2)
        row = self.note(ws, row, f"The balance is {t.reporter}'s exports to {t.partner} minus its "
                                 f"imports from it, in these products, in value as "
                                 f"{t.reporter} reports them (BACI: as BACI records them).")
        if len(other.products) > 1:
            row += 1
            ws.write_string(row, 0, f"Products of {t.reporter}'s {t.other_flow} "
                                    f"{t.other_to} {t.partner}", self.f["section"])
            view = self.view(other)
            self.table(ws, view.entity_columns(other.products, "Product"), row=row + 1,
                       freeze=False, autofilter=False)

    # -- data gaps, estimates ----------------------------------------------------------------
    def partner_gaps_sheet(self):
        t = self.t
        parts = [(f"{t.reporter}'s {t.flow}, all {self.q.roles}", self.q, self.data)]
        parts += [(label, query, data) for _, label, query, data, _ in self.views()]
        frames = []
        for label, query, data in parts:
            rows = [{"Period": p, "Partner": "All", "HS code": "All", "Product": "All",
                     "Metric": "All", "Reason": reason}
                    for p, reason in sorted(query.missing_periods.items())]
            gaps = pd.concat([pd.DataFrame(rows), data.gaps], ignore_index=True) if rows \
                else data.gaps
            if len(gaps):
                frames.append(gaps.assign(Data=label)[["Data"] + list(gaps.columns)])
        if not frames:
            return
        gaps = pd.concat(frames, ignore_index=True)
        ws = self.sheet("Data gaps", "#C55A11", "Every data point the source does not report, "
                                                 "in each view of the trade: the program leaves "
                                                 "each one Missing and never estimates it.")
        if len(gaps) > SHEET_ROW_LIMIT:
            path = self.path.parent / "data_gaps.csv"
            gaps.to_csv(path, index=False, encoding="utf-8-sig")
            self.note(ws, 0, f"{len(gaps):,} data gaps, more than this sheet holds; they are "
                             f"listed in {path.name} next to this workbook.")
            self.files["Data gaps"] = path.name
            return
        columns = [Column(header, gaps[header].tolist(),
                          self.period_kind if header == "Period" else
                          "money" if "USD" in header else "text",
                          {"Data": 34, "Product": 50, "Reason": 60, "Partner": 26}.get(header))
                   for header in gaps.columns]
        self.table(ws, columns)

    def partner_estimates_sheet(self):
        parts = [(f"{self.t.reporter}'s {self.t.flow}, all {self.q.roles}", self.data)]
        parts += [(label, data) for _, label, _, data, _ in self.views()]
        frames = [data.estimates.assign(Data=label)[["Data"] + list(data.estimates.columns)]
                  for label, data in parts if len(data.estimates)]
        if not frames:
            return
        estimates = pd.concat(frames, ignore_index=True)
        q = self.q
        ws = self.sheet("Source estimates", BLUE,
                        f"Every figure {q.estimated_by} estimated rather than the reporting "
                        f"country reported, in each view of the trade. They are part of "
                        f"{q.source}: the analysis uses each one as {q.source} gives it, and the "
                        "tables show the figures that include them in blue.")
        if len(estimates) > SHEET_ROW_LIMIT:
            path = self.path.parent / "source_estimates.csv"
            estimates.to_csv(path, index=False, encoding="utf-8-sig")
            self.note(ws, 0, f"{len(estimates):,} estimated figures, more than this sheet "
                             f"holds; they are listed in {path.name} next to this workbook.")
            self.files["Source estimates"] = path.name
            return
        columns = [Column(header, estimates[header].tolist(),
                          self.period_kind if header == "Period" else
                          "money" if "USD" in header else
                          "volume" if header == "Estimated figure" else "text",
                          {"Data": 34, "Product": 50, "Partner": 26,
                           "Source flag": 20}.get(header))
                   for header in estimates.columns]
        self.table(ws, columns)

    # -- front sheets ---------------------------------------------------------------------
    def summary_sheet(self, ws):
        pa, a, q, t, s = self.pa, self.a, self.q, self.t, self.pa.summary
        widths = [34, 20, 50, 14, 14, 14, 14, 14, 14]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)
        ws.write_string(0, 0, f"{t.reporter} · {q.flow} {t.to} {t.partner} · {q.product_label} "
                              f"· {q.span}", self.f["title"])
        ws.write_string(1, 0, f"{q.source} · the trade with one partner", self.f["subtitle"])

        def section(row, title):
            for col in range(len(widths)):
                ws.write_string(row, col, title if col == 0 else "", self.f["section"])

        section(3, "Key figures")
        m = pa.metric
        growth_fmt = NUMBER_FORMATS["growth"]
        rows = [(f"Total {m.label.lower()} {t.to} {t.partner}, {q.span}", s["total"],
                 self.amount_format(s["total"], m), ""),
                (f"Average per {pa.period_word}", s["average"], self.amount_format(s["average"], m),
                 "")]
        if len(pa.years) >= 2:
            rows.append((f"CAGR of {m.label.lower()}", s["cagr"], growth_fmt,
                         f"{pa.years[0]} to {pa.years[-1]}; all {q.roles}: "
                         f"{fmt.pct(a.summary['cagr'], signed=True)}"))
            rows.append(("Trend growth", s["trend"], growth_fmt, "log-linear fit over every year"))
            if "real_cagr" in s:
                rows.append((f"CAGR at constant {a.real_base} prices", s["real_cagr"], growth_fmt,
                             "deflated by the US consumer price index"))
        peak_period, peak_value = s["peak"]
        if peak_period is not None:
            rows.append((f"Peak {pa.period_word}", period_label(peak_period, q.monthly), None,
                         fmt.amount(peak_value, m)))
        for metric in pa.metrics[1:]:
            rows.append((f"Total {metric.label.lower()}", s["totals"][metric.key],
                         self.amount_format(s["totals"][metric.key], metric),
                         "Missing for part of the data: see Data gaps"
                         if is_gap(s["totals"][metric.key]) else ""))
        if "unit_value" in s:
            every = a.summary.get("unit_value")
            rows.append((self.entity_header("Unit value"), s["unit_value"], "#,##0.00",
                         f"all {q.roles}: {fmt.gap_text(every) or f'{number(every):,.2f}'}"))
        rows.append((f"Share of {t.reporter}'s {t.flow}", s["share"], "0.0%",
                     f"rank #{s['rank']} of {s['partners']} {q.roles}" if known(s["rank"])
                     else f"{s['partners']} {q.roles}"))
        rows.append((f"{t.reporter}'s {t.flow}, all {q.roles}", a.summary["total"],
                     self.amount_format(a.summary["total"], m), ""))
        c = pa.contribution
        if c is not None:
            rows.append((f"Change {c['y0']} to {c['y1']}, {t.partner}", c["partner"],
                         self.amount_format(c["partner"], m),
                         f"all {q.roles}: {fmt.amount(c['total'], m)}"))
        side = [r for r in pa.side_position.to_dict("records") if known(r["Share"])] \
            if pa.side_position is not None else []
        if side:
            rows.append((f"{t.reporter}'s share of {t.partner}'s {t.side_flow}",
                         side[-1]["Share"], "0.0%",
                         f"{period_label(side[-1]['Period'], q.monthly)}, {t.reported_as}"))
        if pa.balance is not None:
            value = next(x for x in pa.metrics if x.key == "value")
            balance = total_of(pa.balance)
            rows.append((f"Balance of trade with {t.partner}, {q.span}", balance,
                         self.amount_format(balance, value),
                         "" if is_gap(balance) else
                         ("surplus" if balance > 0 else "deficit" if balance < 0 else "")
                         + f" for {t.reporter}, in these products"))
        row = 4
        for label, value, number_format, note in rows:
            ws.set_row(row, 22)
            ws.write_string(row, 0, label, self.f["kpi_label"])
            if is_gap(value):
                ws.write_string(row, 1, value, self.fmt("text", gap=True, kpi=True))
            elif value is None or value == "" or (isinstance(value, float) and np.isnan(value)):
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
        for sentence in findings(pa):
            row += 1
            ws.merge_range(row, 0, row, len(widths) - 1, f"•  {sentence}", self.f["wrap"])
            ws.set_row(row, 15 * (len(sentence) // 150 + 1) + 4)
        row += 2
        section(row, f"By {pa.period_word}")
        columns, _, _ = self.trade_columns()
        keep = [c for c in columns if "growth" not in c.header.lower() or
                c.header == f"{m.label} growth"]
        compact = [c._replace(width=widths[i] if i < len(widths) else 14)
                   for i, c in enumerate(keep[:9])]
        last = self.table(ws, compact, row=row + 1, freeze=False, autofilter=False)
        last = self.estimate_note(ws, last + 1, pa.metrics) - 1
        overview = next((c for c in self.charts if c.name.startswith("01_")), None)
        if overview:
            section(last + 2, "Overview")
            self.image(ws, overview, last + 3, 0, 1000)

    def about_sheet(self, ws):
        pa, a, q, t = self.pa, self.a, self.q, self.t
        ws.set_column(0, 0, 26)
        ws.set_column(1, 1, 120)
        ws.write_string(0, 0, "International trade query: one partner", self.f["title"])
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
        item("Partner", f"{t.partner} (code {pa.code}); the report is on the trade between the "
                        "two countries")
        item("Trade flow", f"{q.flow} {t.to} {t.partner}; {t.reporter}'s other partners are its "
                           f"{q.roles}")
        item("Product", f"{q.product_label}; one product row is one {q.product_level}")
        item("Period", f"{q.span}, {len(pa.periods)} {pa.period_word}s"
                       + (", monthly" if q.monthly else ", annual"))
        item("HS edition", edition_summary(a))
        for sentence in edition_sentences(a):
            item("HS editions differ", sentence)
        if pa.side is not None:
            item(f"HS edition, {t.partner}", edition_summary(pa.side))
            for sentence in edition_sentences(pa.side):
                item("HS editions differ", sentence)
        item("Measured by", f"{pa.metric.heading}; also reported: "
                            + (", ".join(m.heading for m in pa.metrics[1:]) or "nothing else"))
        item("Where the figures come from", figures_note(a))
        item(f"{t.partner}'s side", self.side_source())
        item("The other direction", f"{t.reporter}'s {t.other_flow} {t.other_to} {t.partner} "
                                    "of the same products, "
                                    + ("from the same BACI files." if q.source == "BACI" else
                                       f"as {t.reporter} reports them to COMTRADE (its records "
                                       f"with {t.partner} as partner)."))
        if self.data.raw_note:
            item("Raw data", self.data.raw_note)
        for _, label, _, data, _ in self.views():
            if data.raw_note:
                item(f"Raw data: {label}", data.raw_note)
        item("Files", "; ".join(f"{k}: {v}" for k, v in self.files.items()))
        row += 1
        section("Missing data")
        item("Policy", "Figures are shown as the source reports them. Where the source has no "
                       "value, the cell says Missing, and so does every total, share, unit value, "
                       "difference and growth rate that depends on it. The program never "
                       "estimates, interpolates or fills in a missing value.")
        rules = list(q.missing_rules)
        for _, _, query, _, _ in self.views():
            rules += [r for r in query.missing_rules if r not in rules]
        for rule in rules:
            item("Recognised as missing", rule)
        if q.source == "COMTRADE" and q.product_code not in ("TOTAL", "AG2", "AG4", "AG6"):
            item("Recognised as missing", "COMTRADE: a period the partner reported in an HS "
                                          "edition that has no such code, so it could not report "
                                          "trade under it.")
        for _, label, query, _, _ in self.views():
            for reason, periods in unreported(query).items():
                item("Not reported", f"{label}: "
                                     f"{', '.join(period_label(p, q.monthly) for p in periods)}"
                                     f" ({reason})")
        item("n/a", "Not defined, for example growth from a period without trade, a CAGR whose "
                    "first or last year has no trade, or a ratio to zero.")
        if any(m.unit_column for m in pa.metrics):
            item("Mixed units", "Quantities recorded in different units, which cannot be added.")
        estimated = any(len(data.estimates) for _, _, _, data, _ in self.views()) or a.estimated
        if q.estimate_rules or estimated:
            row += 1
            section("Estimates in the source")
            item("Policy", f"A figure {q.source} itself marks as an estimate is part of the "
                           f"database, so the analysis uses it as {q.source} gives it and says "
                           "so: every figure that includes one is shown in blue in the tables, "
                           "and the Source estimates sheet lists each one. The program itself "
                           "never estimates anything.")
            for rule in q.estimate_rules:
                item("Recognised as an estimate", rule)
        row += 1
        section("Definitions")
        for metric in pa.metrics:
            if metric.kind == "money":
                text = f"{metric.heading}, in current US dollars, not adjusted for inflation"
            elif metric.unit_column:
                name = q.unit_names.get(metric.unit)
                text = (f"{metric.heading}" + (f": {metric.unit} is {name.lower()}" if name
                                               else "")
                        + f", as {q.source} reports it. Quantities in different units are "
                          "never added together.")
            else:
                text = metric.heading
            item(metric.label, text)
        if pa.unit_values is not None:
            money, volume = (next(m for m in pa.metrics if m.key == key) for key in q.unit_value)
            item("Unit value", f"{money.label} divided by {volume.label.lower()}, for the same "
                               f"rows, in USD per {volume.unit or 'unit'}: an average over the "
                               "products and shipments in each figure.")
        item("Share", f"{t.partner}'s part of {t.reporter}'s {t.flow} from all {q.roles} in the "
                      f"same {pa.period_word} (or over the whole query).")
        item("Rank", f"{t.partner}'s place among {t.reporter}'s {q.roles} by "
                     f"{pa.metric.label.lower()}; blank in a {pa.period_word} without trade, "
                     "Missing when a partner's figure is.")
        item("Growth", f"Change on the previous {pa.period_word}: this {pa.period_word} / the "
                       "previous one − 1. The growth gap is the partner's growth minus the "
                       "total's, in percentage points.")
        item("Part of the change", f"{t.partner}'s change from the first to the last year divided "
                                   "by the change of the total.")
        item("CAGR", "Compound annual growth rate: (last year / first year)^(1 / years between) − "
                     "1." + (" Monthly data uses complete calendar years." if q.monthly else ""))
        item("Trend growth", "Annual growth of a log-linear trend fitted to every year. Needs "
                             "trade in every year.")
        if a.real_totals is not None:
            item("Constant dollars", f"Values deflated to {a.real_base} prices with the US "
                                     f"consumer price index ({a.cpi_note}).")
        item(f"{t.reporter}'s share of {t.partner}'s {t.side_flow}",
             f"{t.partner}'s {t.side_flow} {t.other_to} {t.reporter} divided by its "
             f"{t.side_flow} {t.other_to} every country, {t.reported_as}.")
        if q.source == "COMTRADE":
            item("The two countries' figures", f"{t.reporter}'s figure minus {t.partner}'s, and "
                                               "the first divided by the second, each as its "
                                               "country reports it.")
        item("Balance", f"{t.reporter}'s exports to {t.partner} minus its imports from it, in "
                        "value, in these products.")
        item("HHI", "Herfindahl-Hirschman index: the sum of squared shares x 10,000; "
                    f"{t.reporter}'s was {fmt.count(a.summary['hhi'])} over the query "
                    f"({hhi_band(a.summary['hhi']) or 'not defined'}).")
        item("Status", "Continuing: trade in the first and last period. New: none in the first. "
                       "Lost: none in the last. Intermittent: trade only in between. Unknown: "
                       "the first or last period is not reported by the source.")
        row += 1
        section("Checks")
        for check, result in self.checks():
            item(check, result)
        for _, label, _, _, analysis in self.views():
            if analysis is not None:
                for check, result in self.view(analysis).checks():
                    item(f"{check} ({label})", result)
        row += 1
        section("Sheets")
        for name, text in self.guide:
            ws.write_url(row, 0, f"internal:'{name}'!A1", self.f["link"], string=name)
            ws.write_string(row, 1, text, self.f["wrap"])
            row += 1

    def side_source(self) -> str:
        q, t = self.q, self.t
        if q.source == "BACI":
            return (f"BACI's rows for {t.partner}'s {t.side_flow} {t.other_to} every country, "
                    "read from the same BACI files. BACI combines the exporter's and the "
                    "importer's reports into one figure per flow and HS 6-digit product, so the "
                    "two countries' figures for the same trade cannot be compared here. Where "
                    "they used different 6-digit codes, BACI keeps both reports, and totals above "
                    "6 digits can count the same trade twice (Usage Guide, section 9.9).")
        code = q.product_code if q.product_code not in ("TOTAL", "AG2", "AG4", "AG6") else "TOTAL"
        return (f"{t.partner}'s own reports to COMTRADE of its {t.side_flow}: its figures for "
                f"{code} by partner and with partner World, its own total. They give "
                f"{t.reporter}'s share of {t.partner}'s {t.side_flow} and {t.partner}'s figures "
                f"for its trade with {t.reporter}, beside {t.reporter}'s own.")


def unreported(query) -> dict[str, list[int]]:
    """A query's unreported periods, grouped by reason."""
    out = {}
    if query is None:
        return out
    for period, reason in sorted(query.missing_periods.items()):
        out.setdefault(reason, []).append(period)
    return out


def write_workbook(path: Path, pa: PartnerAnalysis, data: QueryData, charts: list[Path],
                   files: dict[str, str]) -> Path:
    return PartnerBook(path, pa, data, charts, files).build()
