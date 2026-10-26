"""Analysis of one query: by period, by partner, by product and over the whole period.

Totals are built only from values the source reports. Any figure that would need a value the
source does not have is the text 'Missing' (quantities in different units are 'Mixed units');
nothing is estimated or filled in. Figures the source itself estimated are part of the source:
they are used as given, and the analysis keeps track of where they are. Figures that are
mathematically undefined, such as growth from a year without trade, are NaN and shown as 'n/a'.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import Metric, Query, estimate_column, period_label

MISSING = "Missing"
MIXED_UNITS = "Mixed units"
TOP_N = 10
USD_IN = {"million USD": 1e6, "USD": 1.0}   # US dollars in a money unit: unit values are USD


# ---------------------------------------------------------------------------
# Cells: a number, NaN (undefined) or a gap ('Missing' / 'Mixed units')
# ---------------------------------------------------------------------------

def is_gap(value) -> bool:
    return isinstance(value, str) and value in (MISSING, MIXED_UNITS)


def number(value) -> float:
    """A cell as a float; NaN for gaps and empty cells."""
    if value is None or isinstance(value, str):
        return np.nan
    return float(value)


def gap_of(*values):
    """'Missing' if any value is missing, else 'Mixed units' if any is, else None."""
    texts = {v for v in values if isinstance(v, str)}
    if MISSING in texts:
        return MISSING
    if MIXED_UNITS in texts:
        return MIXED_UNITS
    return None


def total_of(values):
    values = list(values)
    gap = gap_of(*values)
    if gap:
        return gap
    numbers = [number(v) for v in values]
    return float(np.nansum(numbers)) if numbers else 0.0


def ratio(numerator, denominator):
    """numerator / denominator; NaN when the denominator is zero."""
    gap = gap_of(numerator, denominator)
    if gap:
        return gap
    top, bottom = number(numerator), number(denominator)
    if np.isnan(top) or not bottom > 0:
        return np.nan
    return top / bottom


def growth(current, previous):
    """Change from previous to current; NaN when the previous period had no trade."""
    gap = gap_of(current, previous)
    if gap:
        return gap
    now, before = number(current), number(previous)
    if np.isnan(now) or not before > 0:
        return np.nan
    return now / before - 1


def cagr(first, last, years):
    """Compound annual growth rate; NaN unless both end years have trade."""
    gap = gap_of(first, last)
    if gap:
        return gap
    start, end = number(first), number(last)
    if years <= 0 or not start > 0 or not end > 0:
        return np.nan
    return (end / start) ** (1 / years) - 1


def trend_growth(values, positions):
    """Annual growth of a log-linear fit; NaN unless every year (3 or more) has trade."""
    values = list(values)
    gap = gap_of(*values)
    if gap:
        return gap
    numbers = np.array([number(v) for v in values], dtype=float)
    if len(numbers) < 3 or not np.all(numbers > 0):
        return np.nan
    slope = np.polyfit(np.asarray(positions, dtype=float), np.log(numbers), 1)[0]
    return math.exp(slope) - 1


def hhi(values):
    """Herfindahl-Hirschman index (0 to 10,000) of the shares in one period."""
    values = list(values)
    gap = gap_of(*values)
    if gap:
        return gap
    numbers = np.array([number(v) for v in values], dtype=float)
    whole = numbers.sum()
    if not whole > 0:
        return np.nan
    return float(((numbers / whole) ** 2).sum() * 10000)


def hhi_band(value) -> str:
    if is_gap(value) or value is None or np.isnan(number(value)):
        return ""
    value = number(value)
    return ("highly concentrated" if value > 2500 else
            "moderately concentrated" if value >= 1500 else "unconcentrated")


def sum_by(rows: pd.DataFrame, keys: list[str], metric: Metric) -> pd.Series:
    """Total of a metric per group: 'Missing' when a row of the group lacks it, 'Mixed units'
    when its rows are measured in different units."""
    if rows.empty:
        return pd.Series(dtype=object)
    values = rows[metric.key]
    frame = rows[keys].assign(_value=values, _missing=values.isna())
    grouped = frame.groupby(keys, sort=False)
    result = grouped["_value"].sum().astype(object)
    if metric.unit_column:
        units = (rows.loc[values.notna(), keys + [metric.unit_column]]
                 .groupby(keys, sort=False)[metric.unit_column].nunique())
        mixed = result.index.intersection(units[units > 1].index)
        result.loc[mixed] = MIXED_UNITS
    missing = grouped["_missing"].any()
    result.loc[missing[missing].index] = MISSING
    return result


def map_cells(frame: pd.DataFrame, function) -> pd.DataFrame:
    return pd.DataFrame([[function(v) for v in row] for row in frame.itertuples(index=False)],
                        index=frame.index, columns=frame.columns, dtype=object)


@dataclass
class Estimated:
    """The figures of one metric that the source itself estimated, used as the source gives
    them: how many, how much of each total they make up, and where they are."""
    count: int                  # partner records holding such a figure
    amount: object              # their sum, or a gap
    share: object               # their share of the whole query's total
    by_period: pd.Series        # their share of each period's total
    flagged: pd.DataFrame       # Period, Partner_Code and Product_Code of each such partner record
    product_flagged: pd.DataFrame   # the same for the records behind the product figures
    detail_flagged: pd.DataFrame    # the same for the products by partner
    total_periods: set          # periods whose total (partner World) is itself flagged

    def cells(self, key: str) -> set:
        """(partner or product code, period) pairs whose figure includes such an estimate."""
        frame = self.flagged if key == "Partner_Code" else self.product_flagged
        return set(zip(frame[key], frame["Period"]))

    def codes(self, key: str, partner=None) -> set:
        """Partners or products with such a figure; a partner's own products if one is given."""
        if partner is not None:
            frame = self.detail_flagged[self.detail_flagged["Partner_Code"] == partner]
        else:
            frame = self.flagged if key == "Partner_Code" else self.product_flagged
        return set(frame[key])

    @property
    def periods(self) -> set:
        return set(self.flagged["Period"]) | self.total_periods


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------

class Analysis:
    """Every table and figure of a report, computed once.

    `rows` are the products by partner. A source with figures of its own above them (COMTRADE)
    also gives the code asked for by partner (`partner_rows`, when that code is not itself the
    product), its totals with partner World (`total_rows`) and each product's totals
    (`product_total_rows`). Each figure is then taken from the records that report it, and
    added up from the level below only where the source leaves it empty; BACI has rows only,
    so its figures are added up from them."""

    def __init__(self, query: Query, rows: pd.DataFrame, cpi: dict[int, float] | None = None,
                 cpi_note: str = "", partner_rows: pd.DataFrame | None = None,
                 total_rows: pd.DataFrame | None = None,
                 product_total_rows: pd.DataFrame | None = None):
        self.q = query
        self.rows = rows
        self.separate = partner_rows is not None      # the products are other records
        self.partner_rows = partner_rows if self.separate else rows
        self.total_rows = total_rows
        self.product_total_rows = product_total_rows if self.separate else total_rows
        self.added_up: dict[str, list[int]] = {}       # periods whose total is the partners'
        self.metric = query.metric
        self.metrics = list(query.metrics)
        self.periods = list(query.periods)
        self.monthly = query.monthly
        self.missing_periods = {p: r for p, r in query.missing_periods.items()
                                if p in self.periods}
        self.cpi = cpi or {}
        self.cpi_note = cpi_note
        self.period_word = "month" if self.monthly else "year"

        named = pd.concat([self.partner_rows, rows])
        self.partner_names = named.groupby("Partner_Code")["Partner_Name"].first().to_dict()
        named = pd.concat([rows] + ([self.product_total_rows]
                                    if self.product_total_rows is not None else []))
        self.product_names = named.groupby("Product_Code")["Product_Desc"].first().to_dict()

        # Years used for growth over the whole period: the query's years, or for monthly data
        # the calendar years whose twelve months are all in the query and all reported
        self.years = self._growth_years()
        self.span_years = (self.years[-1] - self.years[0]) if len(self.years) >= 2 else 0

        # Entities are listed by the analysis metric; when some of their totals are missing,
        # by the first metric that is complete for every one of them, so the order stays real
        self.partner_matrix = {m.key: self._matrix("Partner_Code", m, self.partner_rows)
                               for m in self.metrics}
        self.partner_order = self._order_metric(self.partner_matrix)
        self.partner_matrix = {k: self._order(v, self.partner_matrix[self.partner_order.key])
                               for k, v in self.partner_matrix.items()}
        self.product_matrix = {m.key: self._combined("Product_Code", m, self.product_total_rows,
                                                     rows) for m in self.metrics}
        self.product_order = self._order_metric(self.product_matrix)
        self.product_matrix = {k: self._order(v, self.product_matrix[self.product_order.key])
                               for k, v in self.product_matrix.items()}

        values = self.partner_matrix[self.metric.key]
        self.period_totals = {m.key: self._period_totals(m) for m in self.metrics}
        # Figures the source itself estimated, by metric: used as given, and stated
        self.estimated: dict[str, Estimated] = {}
        for metric in self.metrics:
            estimated = self._estimated(metric)
            if estimated is not None:
                self.estimated[metric.key] = estimated
        self.partner_shares = self._shares(values, self.period_totals[self.metric.key])
        self.partner_growth = self._matrix_growth(values)

        self.real_base, self.real_totals = self._real_values()
        self.unit_values = self._unit_values(self.period_totals)
        self.period_stats = self._period_stats(values)
        self.annual_totals = {m.key: self._annual(self.period_totals[m.key]) for m in self.metrics}

        self.summary = self._summary()
        self.partners = self._entities(self.partner_matrix, "Partner", self.summary["total"])
        self.products = self._entities(self.product_matrix, "Product", self.summary["total"])
        self.focus_products = None
        if query.partner_code is not None and query.partner_code in self.partner_matrix[
                self.metric.key].index:
            code = query.partner_code
            mine = rows[rows["Partner_Code"] == code]
            matrices = {m.key: self._order(self._matrix("Product_Code", m, mine),
                                           self._matrix("Product_Code", self.metric, mine))
                        for m in self.metrics}
            # The partner's products as shares of its own total, from the partner's records
            own = self.partner_matrix[self.metric.key].loc[code]
            self.focus_products = self._entities(matrices, "Product", total_of(own),
                                                 pd.Series(self._annual_row(own), dtype=object))

    @classmethod
    def of(cls, query: Query, data, cpi: dict[int, float] | None = None, cpi_note: str = ""):
        """The analysis of a QueryData, with every level of records it has."""
        return cls(query, data.rows, cpi, cpi_note, data.partner_rows, data.total_rows,
                   data.product_total_rows)

    # -- building blocks --------------------------------------------------------------
    def _growth_years(self) -> list[int]:
        if not self.monthly:
            return list(self.periods)
        years = []
        for year in sorted({p // 100 for p in self.periods}):
            months = [year * 100 + m for m in range(1, 13)]
            if all(m in self.periods and m not in self.missing_periods for m in months):
                years.append(year)
        return years

    def _matrix(self, key: str, metric: Metric, rows: pd.DataFrame | None = None) -> pd.DataFrame:
        """Entity by period: a number, 0 where nothing was traded, or a gap."""
        rows = self.rows if rows is None else rows
        sums = sum_by(rows, [key, "Period"], metric)
        if sums.empty:
            frame = pd.DataFrame(columns=self.periods, dtype=object)
        else:
            frame = sums.unstack("Period")
        frame = frame.reindex(columns=self.periods).astype(object)
        frame = frame.where(frame.notna(), 0.0)
        for period in self.missing_periods:
            frame[period] = MISSING
        return frame

    def _combined(self, key: str, metric: Metric, own_rows: pd.DataFrame | None,
                  part_rows: pd.DataFrame) -> pd.DataFrame:
        """Entity by period from the source's own totals of each entity (partner World), or
        where it has none, from the entity's records added up."""
        parts = self._matrix(key, metric, part_rows)
        if own_rows is None or own_rows.empty:
            return parts
        own = self._matrix(key, metric, own_rows)
        present = set(zip(own_rows[key], own_rows["Period"]))
        combined = parts.reindex(parts.index.union(own.index, sort=False))
        combined = combined.where(combined.notna(), 0.0)
        for code in own.index:
            for period in self.periods:
                value = own.at[code, period]
                if (code, period) in present and not is_gap(value):
                    combined.at[code, period] = value
        return combined

    def _period_totals(self, metric: Metric) -> pd.Series:
        """Each period's total: the source's own (COMTRADE's partner World) where it gives
        one, else the partners added up, which is Missing when any of them lacks the figure.
        A period the source did not report is Missing, even when no partner has any rows."""
        partners = self._column_totals(self.partner_matrix[metric.key])
        for period in self.missing_periods:
            partners[period] = MISSING
        if self.total_rows is None:
            return partners
        own = (sum_by(self.total_rows, ["Period"], metric) if len(self.total_rows)
               else pd.Series(dtype=object))
        totals, added = {}, []
        for period in self.periods:
            if period in own.index and not is_gap(own[period]):
                totals[period] = own[period]
            else:
                totals[period] = partners[period]
                if period not in self.missing_periods and not is_gap(partners[period]):
                    added.append(period)
        self.added_up[metric.key] = added
        return pd.Series(totals, dtype=object)

    def _order_metric(self, matrices: dict[str, pd.DataFrame]) -> Metric:
        """The analysis metric if every entity's total is known, else the first metric that is."""
        for metric in self.metrics:
            frame = matrices[metric.key]
            if not any(is_gap(total_of(row)) for _, row in frame.iterrows()):
                return metric
        return self.metric

    @staticmethod
    def _order(frame: pd.DataFrame, by: pd.DataFrame) -> pd.DataFrame:
        """Rows sorted by their total in `by`, largest first; rows with gaps last."""
        totals = by.apply(lambda row: total_of(row), axis=1) if len(by) else pd.Series(dtype=object)
        keys = totals.map(lambda v: (1, 0.0) if is_gap(v) else (0, -number(v)))
        order = sorted(totals.index, key=lambda i: (keys[i], str(i)))
        return frame.reindex(order)

    @staticmethod
    def _column_totals(frame: pd.DataFrame) -> pd.Series:
        return pd.Series({p: total_of(frame[p]) for p in frame.columns}, dtype=object)

    @staticmethod
    def _shares(values: pd.DataFrame, totals: pd.Series) -> pd.DataFrame:
        """Each entity's share of its period's total."""
        return pd.DataFrame({p: [ratio(v, totals[p]) for v in values[p]] for p in values.columns},
                            index=values.index, dtype=object)

    def _matrix_growth(self, values: pd.DataFrame) -> pd.DataFrame:
        pairs = list(zip(self.periods, self.periods[1:]))
        return pd.DataFrame({now: [growth(a, b) for a, b in zip(values[now], values[before])]
                             for before, now in pairs}, index=values.index, dtype=object)

    def _annual(self, series: pd.Series) -> pd.Series:
        """Totals by growth year: the period itself, or the sum of a complete year's months."""
        if not self.monthly:
            return series.reindex(self.years)
        return pd.Series({y: total_of(series[[y * 100 + m for m in range(1, 13)]])
                          for y in self.years}, dtype=object)

    def _annual_row(self, row: pd.Series) -> dict:
        if not self.monthly:
            return {y: row[y] for y in self.years}
        return {y: total_of(row[[y * 100 + m for m in range(1, 13)]]) for y in self.years}

    def _estimated(self, metric: Metric) -> Estimated | None:
        """Where the source marks this metric's figures as its own estimates, at each level."""
        column = estimate_column(metric.key)
        keys = ["Period", "Partner_Code", "Product_Code"]

        def flagged(frame) -> pd.DataFrame:
            if frame is None or column not in frame:
                return pd.DataFrame(columns=keys)
            return frame[frame[column].eq(True)]

        partners = flagged(self.partner_rows)
        totals = flagged(self.total_rows)
        detail = flagged(self.rows)
        products = pd.concat([flagged(self.product_total_rows)[keys], detail[keys]],
                             ignore_index=True)
        if partners.empty and totals.empty and products.empty:
            return None
        sums = sum_by(partners, ["Period"], metric) if len(partners) else pd.Series(dtype=object)
        period_totals = self.period_totals[metric.key]
        amount = total_of(sums.tolist()) if len(sums) else 0.0
        return Estimated(
            count=len(partners), amount=amount, share=ratio(amount, total_of(period_totals)),
            by_period=pd.Series({p: ratio(sums.get(p, 0.0), period_totals[p])
                                 for p in self.periods}, dtype=object),
            flagged=partners[keys], product_flagged=products, detail_flagged=detail[keys],
            total_periods=set(totals["Period"]))

    def _real_values(self):
        """Constant-dollar totals of a money metric, annual data only."""
        if self.monthly or self.metric.kind != "money" or not self.cpi:
            return None, None
        with_cpi = [y for y in self.periods if y in self.cpi]
        if not with_cpi:
            return None, None
        base = with_cpi[-1]
        totals = self.period_totals[self.metric.key]
        real = pd.Series({y: (MISSING if y not in self.cpi else
                              (totals[y] if is_gap(totals[y]) else
                               number(totals[y]) * self.cpi[base] / self.cpi[y]))
                          for y in self.periods}, dtype=object)
        return base, real

    def unit_value(self, money, volume):
        """Money divided by volume, in US dollars per unit of volume (per metric ton)."""
        value = ratio(money, volume)
        if isinstance(value, float) and value == value:
            money_metric = next(m for m in self.metrics if m.key == self.q.unit_value[0])
            value *= USD_IN.get(money_metric.unit, 1.0)
        return value

    def _unit_values(self, totals: dict) -> pd.Series | None:
        if not self.q.unit_value:
            return None
        money_key, volume_key = self.q.unit_value
        if money_key not in totals or volume_key not in totals:
            return None
        return pd.Series({p: self.unit_value(totals[money_key][p], totals[volume_key][p])
                          for p in self.periods}, dtype=object)

    def _period_stats(self, values: pd.DataFrame) -> pd.DataFrame:
        present = self.partner_rows.groupby("Period")["Partner_Code"].nunique()
        totals = self.period_totals[self.metric.key]
        stats = {}
        for period in self.periods:
            column = values[period]
            gap = gap_of(*column) or gap_of(totals[period])
            if period in self.missing_periods:
                stats[period] = dict.fromkeys(["Partners", "Largest", "Largest share",
                                               "Top 3 share", "HHI"], MISSING)
                continue
            count = int(present.get(period, 0))
            if gap:
                stats[period] = {"Partners": count, "Largest": gap, "Largest share": gap,
                                 "Top 3 share": gap, "HHI": gap}
                continue
            numbers = column.map(number)
            numbers = numbers[numbers > 0].sort_values(ascending=False)
            whole = number(totals[period])          # shares are of the period's total
            stats[period] = {
                "Partners": count,
                "Largest": self.partner_names.get(numbers.index[0], "") if len(numbers) else "",
                "Largest share": numbers.iloc[0] / whole if whole > 0 and len(numbers)
                else np.nan,
                "Top 3 share": numbers.iloc[:3].sum() / whole if whole > 0 else np.nan,
                "HHI": hhi(numbers.tolist()) if numbers.sum() > 0 else np.nan,
            }
        return pd.DataFrame.from_dict(stats, orient="index").astype(object)

    # -- whole period -----------------------------------------------------------------
    def _summary(self) -> dict:
        key = self.metric.key
        series = self.period_totals[key]
        annual = self.annual_totals[key]
        partner_totals = (self.partner_matrix[key].apply(lambda r: total_of(r), axis=1)
                          if len(self.partner_matrix[key]) else pd.Series(dtype=object))
        numeric = series[[not is_gap(v) for v in series]].map(number)
        first, last = (annual.iloc[0], annual.iloc[-1]) if len(annual) >= 2 else (np.nan, np.nan)
        summary = {
            "total": total_of(series),
            "totals": {m.key: total_of(self.period_totals[m.key]) for m in self.metrics},
            "first": first, "last": last,
            "cagr": cagr(first, last, self.span_years) if len(annual) >= 2 else np.nan,
            "trend": (trend_growth(annual.tolist(), list(annual.index))
                      if len(annual) >= 3 else np.nan),
            "peak": (numeric.idxmax(), numeric.max()) if len(numeric) and numeric.max() > 0
            else (None, np.nan),
            "low": (numeric.idxmin(), numeric.min()) if len(numeric) else (None, np.nan),
            "partners": int(self.partner_rows["Partner_Code"].nunique()),
            "products": int(self.product_matrix[key].shape[0]),
        }
        # Shares are of the total; the largest partners are known only if every partner is
        whole = summary["total"]
        gap = gap_of(whole, *partner_totals.tolist())
        if gap:
            summary.update(top=None, top_share=gap, top3_share=gap, hhi=gap)
        else:
            ranked = partner_totals.map(number).sort_values(ascending=False)
            ranked = ranked[ranked > 0]
            whole = number(whole)
            summary.update(
                top=ranked.index[0] if len(ranked) else None,
                top_share=ranked.iloc[0] / whole if whole > 0 and len(ranked) else np.nan,
                top3_share=ranked.iloc[:3].sum() / whole if whole > 0 else np.nan,
                hhi=hhi(ranked.tolist()))
        summary["average"] = ratio(summary["total"], len(self.periods))
        if self.unit_values is not None:
            money_key, volume_key = self.q.unit_value
            summary["unit_value"] = self.unit_value(summary["totals"][money_key],
                                                    summary["totals"][volume_key])
        if self.real_totals is not None:
            real = self.real_totals.reindex(self.years)
            summary["real_cagr"] = (cagr(real.iloc[0], real.iloc[-1], self.span_years)
                                    if len(real) >= 2 else np.nan)
        for metric in self.metrics[1:]:
            annual_m = self.annual_totals[metric.key]
            summary[f"cagr_{metric.key}"] = (cagr(annual_m.iloc[0], annual_m.iloc[-1],
                                                  self.span_years)
                                             if len(annual_m) >= 2 else np.nan)
        if self.unit_values is not None:
            uv = self._annual_unit_values()
            summary["cagr_unit_value"] = (cagr(uv.iloc[0], uv.iloc[-1], self.span_years)
                                          if len(uv) >= 2 else np.nan)
        return summary

    def _annual_unit_values(self) -> pd.Series:
        money_key, volume_key = self.q.unit_value
        return pd.Series({y: self.unit_value(self.annual_totals[money_key][y],
                                             self.annual_totals[volume_key][y])
                          for y in self.years}, dtype=object)

    def _entities(self, matrices: dict[str, pd.DataFrame], kind: str, whole,
                  annual_totals: pd.Series | None = None) -> pd.DataFrame:
        """One row per partner or product over the whole query; shares are of `whole` and, by
        year, of `annual_totals` (the query's annual totals unless given)."""
        key = self.metric.key
        values = matrices[key]
        names = self.partner_names if kind == "Partner" else self.product_names
        if annual_totals is None:
            annual_totals = self.annual_totals[key]
        totals = values.apply(lambda r: total_of(r), axis=1) if len(values) else pd.Series(
            dtype=object)
        y0, y1 = (self.years[0], self.years[-1]) if len(self.years) >= 2 else (None, None)
        first_p, last_p = self.periods[0], self.periods[-1]
        # A rank needs every total: with any of them missing the order cannot be known
        ranked = not any(is_gap(v) for v in totals)
        records = []
        for position, code in enumerate(values.index, start=1):
            row = values.loc[code]
            total = totals[code]
            record = {"Rank": position if ranked else "",
                      "Code": code, "Name": names.get(code, str(code))}
            if kind == "Product" and self.q.product_editions:
                # The data is in more than one HS edition: which editions have this code
                record["HS editions"] = self.q.product_editions.get(str(code), "")
            record.update({self.metric.heading: total, "Share": ratio(total, whole)})
            for metric in self.metrics[1:]:
                record[metric.heading] = total_of(matrices[metric.key].loc[code])
            if self.q.unit_value:
                money_key, volume_key = self.q.unit_value
                record["Unit value"] = self.unit_value(total_of(matrices[money_key].loc[code]),
                                                       total_of(matrices[volume_key].loc[code]))
            if y0 is not None:
                annual = self._annual_row(row)
                first, last = annual[y0], annual[y1]
                record[f"{self.metric.label} {y0}"] = first
                record[f"{self.metric.label} {y1}"] = last
                gap = gap_of(first, last)
                record["Change"] = gap or (number(last) - number(first))
                record["CAGR"] = cagr(first, last, self.span_years)
                if self.real_totals is not None:
                    record["Real CAGR"] = self._real_cagr(first, last, y0, y1)
                share_first = ratio(first, annual_totals[y0])
                share_last = ratio(last, annual_totals[y1])
                record[f"Share {y0}"] = share_first
                record[f"Share {y1}"] = share_last
                gap = gap_of(share_first, share_last)
                record["Share change (pp)"] = gap or (
                    (number(share_last) - number(share_first)) * 100
                    if not (np.isnan(number(share_first)) or np.isnan(number(share_last)))
                    else np.nan)
            # Periods the source did not report at all say nothing about trade either way
            traded = [p for p in self.periods
                      if p not in self.missing_periods and self._traded(row[p])]
            record[f"{self.period_word.capitalize()}s with trade"] = len(traded)
            numeric = {p: number(row[p]) for p in self.periods if not is_gap(row[p])}
            peak = max(numeric, key=numeric.get) if numeric and max(numeric.values()) > 0 else None
            record[f"Peak {self.period_word}"] = peak if peak is not None else ""
            record["Status"] = self._status(row, first_p, last_p, len(traded))
            records.append(record)
        return pd.DataFrame.from_records(records)

    def _real_cagr(self, first, last, y0, y1):
        if y0 not in self.cpi or y1 not in self.cpi:
            return MISSING
        gap = gap_of(first, last)
        if gap:
            return gap
        return cagr(number(first) / self.cpi[y0], number(last) / self.cpi[y1], self.span_years)

    @staticmethod
    def _traded(cell) -> bool:
        return is_gap(cell) or number(cell) > 0

    def _status(self, row, first_p, last_p, traded) -> str:
        start_l = period_label(first_p, self.monthly)
        end_l = period_label(last_p, self.monthly)
        unreported = [label for p, label in ((first_p, start_l), (last_p, end_l))
                      if p in self.missing_periods]
        if unreported:
            return f"Unknown: {' and '.join(unreported)} not reported"
        a, b = self._traded(row[first_p]), self._traded(row[last_p])
        if a and b:
            return "Continuing"
        if b:
            return f"New since {start_l}"
        if a:
            return f"Lost by {end_l}"
        return "Intermittent" if traded else "No trade"

    # -- what is missing ----------------------------------------------------------------
    def gap_levels(self) -> list[tuple[Metric, list[tuple[str, int, int, list[int]]]]]:
        """For each metric with gaps: (level, records lacking it, records, periods) for each
        level of the source's records. A source without totals of its own (BACI) has one level,
        'rows'; COMTRADE has 'total' (partner World) and 'partners', and when the products are
        other records, 'products' (by partner) and 'product totals'."""
        if self.total_rows is None:
            levels = [("rows", self.rows)]
        else:
            levels = [("total", self.total_rows), ("partners", self.partner_rows)]
            if self.separate:
                levels += [("products", self.rows), ("product totals", self.product_total_rows)]
        out = []
        for metric in self.metrics:
            found = []
            for level, frame in levels:
                if frame is None or frame.empty:
                    continue
                lacking = frame[frame[metric.key].isna()]
                if len(lacking):
                    found.append((level, len(lacking), len(frame),
                                  sorted(lacking["Period"].unique().tolist())))
            if found:
                out.append((metric, found))
        return out
