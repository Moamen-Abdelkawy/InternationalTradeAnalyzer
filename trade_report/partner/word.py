"""report.docx of a partner report: the trade between the two countries written up with the
charts and main tables, in the style of the report."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from ..findings import estimate_sentences, gap_sentences
from ..summary import cell, kind_of
from ..word import GREY, Report
from .analysis import PartnerAnalysis
from .findings import (Terms, contribution_sentence, findings, mirror_sentence,
                       other_sentence, product_name, side_sentence, unreported_text,
                       view_gap_sentences)
from .summary import competitor_rows, key_figures, mirror_rows, period_rows, side_rows

LONG = 24       # tables with more periods than this are left to the workbook


class PartnerReport(Report):
    def __init__(self, pa: PartnerAnalysis, charts: list[Path], files: dict[str, str]):
        super().__init__(pa.a, charts, files)
        self.pa = pa
        self.t = Terms(pa)

    def build(self, path: Path) -> Path:
        pa, a, q, t, m = self.pa, self.a, self.q, self.t, self.pa.metric
        self.doc.add_paragraph(f"{t.reporter}'s {t.flow} of {t.product} {t.to} {t.partner}, "
                               f"{q.span}", style="Title")
        self.paragraph(f"{q.product_label} · {q.source} · generated {dt.date.today():%d %B %Y} "
                       "by the International Trade Analyzer", italic=True, colour=GREY)

        self.heading("Summary")
        self.bullets(findings(pa))
        self.table(["Measure", "Figure"], [list(f) for f in key_figures(pa)], [False, True])

        self.heading("Scope, data and method")
        self.bullets([
            f"Source: {q.source_description or q.source}.",
            f"Reporter: {t.reporter}; partner: {t.partner}; flow: {t.flow} {t.to} {t.partner}. "
            f"{t.reporter}'s other partners are its {q.roles}, which give {t.partner}'s share, "
            "rank and competitors.",
            f"Product: {q.product_label}; one product row is one {q.product_level}.",
            f"Period: {q.span} ({'monthly' if q.monthly else 'annual'}).",
            f"{t.partner}'s side: {t.partner}'s {t.side_flow} {t.other_to} every country, "
            f"{t.reported_as}"
            + ("; BACI combines the two countries' reports into one figure per flow and HS "
               "6-digit product, and keeps both reports when the two countries used different "
               "6-digit codes, so totals above 6 digits can count the same trade twice (Usage "
               "Guide, section 9.9)."
               if q.source == "BACI" else
               f"; its figures for its trade with {t.reporter} are set beside "
               f"{t.reporter}'s own."),
            f"The other direction: {t.reporter}'s {t.other_flow} {t.other_to} {t.partner} of the "
            "same products, and the balance of trade in value.",
            f"Measured by {m.heading}" + (f"; also reported: "
                                          f"{', '.join(x.heading for x in pa.metrics[1:])}."
                                          if len(pa.metrics) > 1 else "."),
        ])
        self.paragraph("Missing data. Figures are shown as the source reports them. Where the "
                       "source has no value the report says Missing, and so does every total, "
                       "share, unit value, difference and growth rate that depends on it. "
                       "Nothing is estimated, interpolated or filled in, and the two countries' "
                       "figures are compared as they stand, without adjustment.")
        if q.missing_rules:
            self.bullets(q.missing_rules)
        if q.estimate_rules:
            self.paragraph(f"Estimates in the source. A figure {q.source} itself marks as an "
                           f"estimate is part of the database: it is used as {q.source} gives it "
                           "and stated as an estimate, in this report and in the workbook (in "
                           "blue, and in the Source estimates sheet). The program itself never "
                           "estimates anything.")
            self.bullets(q.estimate_rules)
        self.paragraph("CAGR is (last year / first year)^(1 / years between) − 1; trend growth is "
                       "the annual growth of a log-linear trend fitted to every year. A share is "
                       f"{t.partner}'s part of {t.reporter}'s {t.flow} in the same period; the "
                       f"rank is its place among {t.reporter}'s {q.roles}."
                       + (f" Constant dollars use the US consumer price index ({a.cpi_note})."
                          if a.real_totals is not None else ""), size=9.5)

        if self.charts.get("01_trade_with_partner"):
            self.heading(f"The trade with {t.partner}")
            self.chart("01_trade_with_partner",
                       f"{m.label} {t.to} {t.partner} by {pa.period_word}, with the headline "
                       "figures.")
            if len(pa.periods) <= LONG:
                headers, rows, numeric = period_rows(pa)
                self.table(headers, rows, numeric)
        if self.chart_section("02_partner_share", f"{t.partner} in {t.reporter}'s {t.flow}",
                              f"{t.partner} against all other {q.roles}, by {pa.period_word}.",
                              new_page=True):
            sentence = contribution_sentence(pa, t)
            if sentence:
                self.paragraph(sentence)
        if self.chart_section("03_competitors", "Competitors",
                              f"{t.reporter}'s largest {q.roles} over {q.span}; "
                              f"{t.partner} in orange.", new_page=True):
            headers, rows = competitor_rows(pa, mark=False)
            bold = {i for i, r in enumerate(pa.competitors.head(len(rows)).to_dict("records"))
                    if r["Code"] == pa.code}
            self.table(headers, rows, [True, False, True, True, True, False], bold_rows=bold)
        self.chart_section("04_competitor_shares", "Shares against the competitors",
                           f"Share of {t.reporter}'s {t.flow} by {pa.period_word}.")
        self.chart_section("05_prices", "Prices", f"Unit values by {pa.period_word}.")
        if self.chart_section("06_products", "Products",
                              f"The products traded with {t.partner}."):
            table = pa.products.head(10)
            self.table(["HS code", "Product", m.heading, "Share", f"{t.partner}'s share of "
                        f"{t.reporter}'s {t.flow}"],
                       [[str(r["Code"]), product_name(r["Name"], r["Code"])[:60],
                         cell(r[m.heading], kind_of(m), m), cell(r["Share"], "share"),
                         cell(r["Market share"], "share")] for r in table.to_dict("records")],
                       [False, False, True, True, True])

        self.heading(f"{t.reporter} in {t.partner}'s {t.side_flow}", new_page=True)
        if not self.chart("07_partner_side", f"{t.partner}'s {t.side_flow}, {t.reported_as}; "
                                             f"{t.reporter} in orange."):
            self.paragraph(side_sentence(pa, t) or f"{t.partner}'s side is not available.")
        side = side_rows(pa)
        if side and len(pa.periods) <= LONG:
            headers, rows = side
            self.table(headers, rows, [False, True, True, True, True])
        if q.source == "COMTRADE":
            self.heading("The two countries' figures", new_page=False)
            if not self.chart("08_both_reports", "The same trade as each country reports it."):
                self.paragraph(mirror_sentence(pa, t) or
                               f"{t.partner}'s own figures for this trade are not available for "
                               f"any {pa.period_word} of {q.span}, so they cannot be set beside "
                               f"{t.reporter}'s (see section {self.number - 1}).")
            mirror = mirror_rows(pa)
            if mirror and self.charts.get("08_both_reports") and len(pa.periods) <= LONG:
                headers, rows = mirror
                self.table(headers, rows, [False, True, True, True, True])
        self.heading("The other direction", new_page=False)
        self.chart("09_other_direction", f"{t.reporter}'s trade with {t.partner} in both "
                                         "directions, in value, and the balance.")
        self.paragraph(other_sentence(pa, t) or "The trade the other way is not available.")
        self.chart_section("10_seasonality", "Seasonality", f"{m.label} {t.to} {t.partner} by "
                                                            "month and year.")

        estimates = estimate_sentences(a) + (estimate_sentences(pa.side) if pa.side else [])
        self.heading("Data gaps, source estimates and checks" if estimates else
                     "Data gaps and checks")
        gaps = gap_sentences(a)
        gaps += view_gap_sentences(pa.side, f"{t.partner}'s {t.side_flow}")
        gaps += view_gap_sentences(pa.other, f"{t.reporter}'s {t.other_flow} {t.other_to} "
                                             f"{t.partner}")
        for query in (pa.side_query, pa.other_query):
            if query is not None and query.missing_periods:
                gaps.append(unreported_text(query, query.reporter_name))
        self.bullets(gaps or ["No figure used in this report is missing from the source."])
        self.bullets(estimates)
        checks = list(q.checks)
        for label, query in ((t.partner, pa.side_query), (f"{t.other_flow} {t.other_to} "
                                                          f"{t.partner}", pa.other_query)):
            if query is not None:
                checks += [(f"{check} ({label})", result) for check, result in query.checks]
        self.bullets([f"{check}: {result}" for check, result in checks])
        self.paragraph("Files: " + "; ".join(f"{k}: {v}" for k, v in self.files.items()),
                       size=9, colour=GREY)
        self.doc.save(str(path))
        return path


def write_report(pa: PartnerAnalysis, charts: list[Path], path: Path,
                 files: dict[str, str]) -> Path:
    return PartnerReport(pa, charts, files).build(path)
