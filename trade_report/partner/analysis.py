"""Analysis of the trade between a reporter and one partner country.

The reporter's data with every partner gives the partner's place in the reporter's trade: its
figures, share, rank, competitors, prices and products. The partner's own data (its reports in
COMTRADE, its rows in BACI) gives the reporter's place in the partner's trade, and in COMTRADE
the two countries' figures for the same trade side by side. The reporter's trade with the
partner the other way gives the balance. Every figure is the database's own or a sum,
difference or ratio of its figures: nothing is estimated, and a figure that needs one the
source does not report is Missing too.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..analysis import (MISSING, TOP_N, Analysis, cagr, gap_of, growth, is_gap, number, ratio,
                        total_of, trend_growth)
from ..model import Metric, Query, QueryData

RIVALS = 5      # the partner's largest competitors followed period by period


def difference(first, second):
    """first − second; a gap when either is."""
    return gap_of(first, second) or number(first) - number(second)


def part_of(part, whole):
    """part / whole, for a whole of either sign; NaN when the whole is 0."""
    gap = gap_of(part, whole)
    if gap:
        return gap
    top, bottom = number(part), number(whole)
    if np.isnan(top) or np.isnan(bottom) or bottom == 0:
        return np.nan
    return top / bottom


def points(first, second):
    """first − second for two shares, in percentage points."""
    gap = gap_of(first, second)
    if gap:
        return gap
    a, b = number(first), number(second)
    return np.nan if np.isnan(a) or np.isnan(b) else (a - b) * 100


def row_of(matrix: pd.DataFrame, code, a: Analysis) -> pd.Series:
    """A partner's figures by period: 0 where it has none, Missing in unreported periods."""
    if code in matrix.index:
        return matrix.loc[code]
    return pd.Series({p: MISSING if p in a.missing_periods else 0.0 for p in a.periods},
                     dtype=object)


def position(a: Analysis, code) -> pd.DataFrame:
    """One partner's figure, the total, its share and its rank among the partners, period by
    period. A rank needs every partner's figure; it is blank where the partner has no trade."""
    key = a.metric.key
    values = a.partner_matrix[key]
    mine = row_of(values, code, a)
    totals = a.period_totals[key]
    records = []
    for period in a.periods:
        column = values[period] if len(values) else pd.Series(dtype=object)
        gap = gap_of(*column, mine[period])
        if gap:
            rank = gap
        elif number(mine[period]) > 0:
            rank = int((column.map(number) > number(mine[period])).sum()) + 1
        else:
            rank = ""
        records.append({"Period": period, "Figure": mine[period], "Total": totals[period],
                        "Share": ratio(mine[period], totals[period]), "Rank": rank,
                        "Partners": a.period_stats.loc[period, "Partners"]})
    return pd.DataFrame.from_records(records)


class PartnerAnalysis:
    """Every table and figure of a partner report, computed once.

    `a` analyses the reporter's trade with every partner, which the partner's share, rank and
    competitors need; `side` the partner's trade with every country in the other direction
    (when the reporter imports, the partner's exports); `other` the reporter's trade with the
    partner the other way. `side` and `other` are None when there is no such data, and their
    status says why: 'unreported' when the country reported none of the periods, 'none' when
    it recorded no such trade, 'unavailable' when the data could not be read."""

    def __init__(self, query: Query, data: QueryData, cpi: dict[int, float] | None = None,
                 cpi_note: str = ""):
        self.q = query
        self.a = a = Analysis.of(query, data, cpi, cpi_note)
        self.code = query.partner_code
        self.metric, self.metrics = a.metric, a.metrics
        self.periods, self.years, self.monthly = a.periods, a.years, a.monthly
        self.period_word = a.period_word
        self.name = str(a.partner_names.get(self.code) or query.partner_name or self.code)
        key = self.metric.key
        self.traded = self.code in a.partner_matrix[key].index
        match = a.partners[a.partners["Code"] == self.code] if len(a.partners) else a.partners
        self.row = match.iloc[0] if len(match) else None   # the partner in the partners table
        # The partner's figures by period, metric by metric
        self.series = {m.key: row_of(a.partner_matrix[m.key], self.code, a) for m in self.metrics}
        self.unit_values = self._unit_values()
        self.real_values = self._real_values()
        self.summary = self._summary()
        self.position = self._position()
        self.contribution = self._contribution()
        # Its largest competitors over the whole period
        self.rivals = [c for c in a.partner_matrix[key].index if c != self.code][:RIVALS]
        self.competitors = self._competitors()
        self.rival_prices = self._rival_prices()
        self.product_matrix, self.products = self._products()
        views = data.partner_views
        self.side, self.side_query, self.side_status = self._view(views.side if views else None)
        self.other, self.other_query, self.other_status = self._view(
            views.other if views else None)
        self.side_position = (position(self.side, query.reporter_code) if self.side is not None
                              else None)
        self.side_partners = self._side_partners()
        self.mirror = self._mirror()
        self.balance = self._balance()

    # -- the partner in the reporter's trade -----------------------------------------------
    def _unit_values(self) -> pd.Series | None:
        if not self.q.unit_value or self.a.unit_values is None:
            return None
        money, volume = self.q.unit_value
        return pd.Series({p: self.a.unit_value(self.series[money][p], self.series[volume][p])
                          for p in self.periods}, dtype=object)

    def _real_values(self) -> pd.Series | None:
        """The partner's values in constant dollars, on the base the reporter's totals use."""
        a = self.a
        if a.real_totals is None:
            return None
        series = self.series[self.metric.key]
        return pd.Series({y: (MISSING if y not in a.cpi else series[y] if is_gap(series[y])
                              else number(series[y]) * a.cpi[a.real_base] / a.cpi[y])
                          for y in self.periods}, dtype=object)

    def annual(self, series: pd.Series) -> dict:
        """Totals by growth year (see Analysis.years)."""
        return self.a._annual_row(series)

    def _summary(self) -> dict:
        a, y = self.a, self.years
        series = self.series[self.metric.key]
        annual = self.annual(series)
        first, last = (annual[y[0]], annual[y[-1]]) if len(y) >= 2 else (np.nan, np.nan)
        numeric = {p: number(v) for p, v in series.items() if not is_gap(v)}
        peak = max(numeric, key=numeric.get) if numeric and max(numeric.values()) > 0 else None
        summary = {
            "total": total_of(series),
            "totals": {m.key: total_of(self.series[m.key]) for m in self.metrics},
            "first": first, "last": last,
            "cagr": cagr(first, last, a.span_years) if len(y) >= 2 else np.nan,
            "trend": (trend_growth([annual[x] for x in y], y) if len(y) >= 3 else np.nan),
            "peak": (peak, numeric[peak]) if peak is not None else (None, np.nan),
            "rank": self.row["Rank"] if self.row is not None else "",
            "status": self.row["Status"] if self.row is not None else "No trade",
            "partners": a.summary["partners"],
            "traded": sum(1 for p in self.periods if p not in a.missing_periods
                          and (is_gap(series[p]) or number(series[p]) > 0)),
        }
        summary["share"] = ratio(summary["total"], a.summary["total"])
        summary["average"] = ratio(summary["total"], len(self.periods))
        if a.real_totals is not None and len(y) >= 2:
            summary["real_cagr"] = a._real_cagr(first, last, y[0], y[-1])
        for metric in self.metrics[1:]:
            values = self.annual(self.series[metric.key])
            summary[f"cagr_{metric.key}"] = (cagr(values[y[0]], values[y[-1]], a.span_years)
                                             if len(y) >= 2 else np.nan)
        if self.unit_values is not None:
            money, volume = self.q.unit_value
            summary["unit_value"] = a.unit_value(summary["totals"][money],
                                                 summary["totals"][volume])
            values = {x: a.unit_value(self.annual(self.series[money])[x],
                                      self.annual(self.series[volume])[x]) for x in y}
            summary["cagr_unit_value"] = (cagr(values[y[0]], values[y[-1]], a.span_years)
                                          if len(y) >= 2 else np.nan)
        return summary

    def _position(self) -> pd.DataFrame:
        """The partner in the reporter's trade by period: its figure, the total, its share and
        rank, its growth against the total's, and the largest partner."""
        a, periods = self.a, self.periods
        frame = position(a, self.code)
        mine, totals = self.series[self.metric.key], a.period_totals[self.metric.key]
        pairs = list(zip(periods, periods[1:]))
        frame["Growth"] = [np.nan] + [growth(mine[now], mine[before]) for before, now in pairs]
        frame["Total growth"] = [np.nan] + [growth(totals[now], totals[before])
                                            for before, now in pairs]
        frame["Growth gap (pp)"] = [points(g, t) for g, t in zip(frame["Growth"],
                                                                 frame["Total growth"])]
        frame["Largest"] = [a.period_stats.loc[p, "Largest"] for p in periods]
        frame["Largest share"] = [a.period_stats.loc[p, "Largest share"] for p in periods]
        return frame

    def _contribution(self) -> dict | None:
        """How the partner's figure and the total changed between the first and last growth
        year, and the partner's part of the total's change."""
        y = self.years
        if len(y) < 2:
            return None
        key = self.metric.key
        mine, whole = self.annual(self.series[key]), self.a.annual_totals[key]
        change_mine = difference(mine[y[-1]], mine[y[0]])
        change_whole = difference(whole[y[-1]], whole[y[0]])
        return {"y0": y[0], "y1": y[-1], "partner": change_mine, "total": change_whole,
                "part": part_of(change_mine, change_whole)}

    def _competitors(self) -> pd.DataFrame:
        """The reporter's largest partners over the whole period, with this partner always
        among them."""
        table = self.a.partners
        if table.empty:
            return table
        top = table.head(TOP_N)
        if self.traded and self.code not in set(top["Code"]):
            top = pd.concat([top, table[table["Code"] == self.code]])
        return top.reset_index(drop=True)

    def _rival_prices(self) -> pd.DataFrame | None:
        """The unit value of each of the largest competitors, by period."""
        if self.unit_values is None:
            return None
        a = self.a
        money, volume = self.q.unit_value
        return pd.DataFrame({p: [a.unit_value(a.partner_matrix[money].loc[c, p],
                                              a.partner_matrix[volume].loc[c, p])
                                 for c in self.rivals] for p in self.periods},
                            index=self.rivals, dtype=object)

    def _products(self):
        """The products traded with the partner by period, and over the whole period with the
        partner's share of the reporter's trade in each."""
        a = self.a
        if not self.traded or a.focus_products is None:
            return None, None
        # In the order of the partner's products table: by the analysis metric
        mine = a.rows[a.rows["Partner_Code"] == self.code]
        by = a._matrix("Product_Code", self.metric, mine)
        matrix = a._order(by, by)
        table = a.focus_products.copy()
        market = a.product_matrix[self.metric.key]
        y1 = self.years[-1] if len(self.years) >= 2 else None
        totals, shares, last = [], [], []
        for code, own in zip(table["Code"], table[self.metric.heading]):
            row = market.loc[code] if code in market.index else None
            total = total_of(row) if row is not None else MISSING
            totals.append(total)
            shares.append(ratio(own, total))
            if y1 is not None:
                own_last = table.loc[table["Code"] == code, f"{self.metric.label} {y1}"].iloc[0]
                market_last = self.annual(row)[y1] if row is not None else MISSING
                last.append(ratio(own_last, market_last))
        table["Market total"] = totals
        table["Market share"] = shares
        if y1 is not None:
            table[f"Market share {y1}"] = last
        return matrix, table

    # -- the other views -------------------------------------------------------------------
    def _view(self, pair):
        """The analysis of another view of the trade, its query, and its status."""
        if pair is None:
            return None, None, "unavailable"
        query, data = pair
        if all(p in query.missing_periods for p in query.periods):
            return None, query, "unreported"
        if data.rows.empty:
            return None, query, "none"
        return Analysis.of(query, data, self.a.cpi, self.a.cpi_note), query, "ok"

    def _side_partners(self) -> pd.DataFrame | None:
        """The partner's largest partners in the other direction, with the reporter always
        among them: over the whole period, or, when the partner did not report every period so
        that no whole-period total can be stated, in the latest period it reported in full
        (self.side_partners_period)."""
        self.side_partners_period = None
        if self.side is None:
            return None
        side, key = self.side, self.metric.key
        table = side.partners
        if is_gap(side.summary["total"]):
            totals = side.period_totals[key]
            complete = [p for p in self.periods if not is_gap(totals[p])
                        and not any(is_gap(v) for v in side.partner_matrix[key][p])]
            if complete:
                period = self.side_partners_period = complete[-1]
                values = side.partner_matrix[key][period].map(number)
                values = values[values > 0].sort_values(ascending=False)
                table = pd.DataFrame({
                    "Rank": range(1, len(values) + 1), "Code": values.index,
                    "Name": [side.partner_names.get(c, str(c)) for c in values.index],
                    side.metric.heading: values.to_numpy(),
                    "Share": [ratio(v, totals[period]) for v in values]})
        top = table.head(TOP_N)
        reporter = self.q.reporter_code
        if reporter in set(table["Code"]) and reporter not in set(top["Code"]):
            top = pd.concat([top, table[table["Code"] == reporter]])
        return top.reset_index(drop=True)

    def view_series(self, which: str, key: str) -> pd.Series:
        """The reporter's figure in another view, by period: its trade with the partner the
        other way ('other'), or the partner's figure for its trade with the reporter ('side').
        0 where the view has none; Missing where its country did not report."""
        analysis = self.other if which == "other" else self.side
        query = self.other_query if which == "other" else self.side_query
        if analysis is not None:
            code = self.code if which == "other" else self.q.reporter_code
            return row_of(analysis.partner_matrix[key], code, analysis)
        missing = query.missing_periods if query is not None else dict.fromkeys(self.periods)
        return pd.Series({p: MISSING if p in missing else 0.0 for p in self.periods},
                         dtype=object)

    def mirror_metrics(self) -> list[Metric]:
        """The metrics both countries' figures can be compared in: quantities only when both
        are in one and the same unit."""
        if self.side_query is None:
            return []
        theirs = {m.key: m for m in self.side_query.metrics}
        return [m for m in self.metrics if m.key in theirs and
                (not m.unit_column or (m.unit and theirs[m.key].unit == m.unit))]

    def side_estimates(self, key: str) -> set:
        """The periods in which the partner's own figure for its trade with the reporter
        includes the source's own estimates, for one metric."""
        e = self.side.estimated.get(key) if self.side is not None else None
        if e is None:
            return set()
        return {p for code, p in e.cells("Partner_Code") if code == self.q.reporter_code}

    def _mirror(self) -> dict[str, pd.DataFrame] | None:
        """COMTRADE: the reporter's figures for its trade with the partner beside the
        partner's own figures for the same trade, metric by metric, as each reports them."""
        if self.q.source != "COMTRADE" or self.side_query is None:
            return None
        out = {}
        for metric in self.mirror_metrics():
            mine = self.series[metric.key]
            theirs = self.view_series("side", metric.key)
            out[metric.key] = pd.DataFrame({
                "Period": self.periods,
                "Reporter": [mine[p] for p in self.periods],
                "Partner": [theirs[p] for p in self.periods],
                "Difference": [difference(mine[p], theirs[p]) for p in self.periods],
                "Ratio": [ratio(mine[p], theirs[p]) for p in self.periods]})
        return out

    def _balance(self) -> pd.Series | None:
        """The reporter's exports to the partner minus its imports from it, by period, in
        value."""
        if self.other_query is None or "value" not in self.series:
            return None
        mine, other = self.series["value"], self.view_series("other", "value")
        exports, imports = (other, mine) if self.q.flow == "Imports" else (mine, other)
        return pd.Series({p: difference(exports[p], imports[p]) for p in self.periods},
                         dtype=object)
