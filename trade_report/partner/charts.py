"""The charts of a partner report, in the house style of the report charts: the partner is in
orange throughout, figures the source does not report are marked 'Missing', never drawn as
zero, and a chart showing figures that include the source's own estimates says so at its foot."""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .. import fmt
from ..analysis import TOP_N, Analysis, is_gap, number, total_of
from ..analysis import growth as change_between
from ..charts import (ACCENT, GAP_GREY, GREY, LABEL_LIMIT, LIGHT_GREY, NAVY, SKY, Charts, Words,
                      axis_amount, mark_gaps, numbers_of, x_grid, y_grid)
from ..model import MONTHS
from .analysis import PartnerAnalysis
from .findings import Terms, known, product_name

RIVAL_COLOURS = ["#1F4E79", "#2E86C1", "#16A085", "#8E44AD", "#C0392B", "#B7950B"]
PRICE_RIVALS = 3    # competitors drawn in the prices chart; the Prices sheet has all of them

PHRASES = {
    "trade_title": "{reporter}'s {flow} of {product} {to} {partner}, {span}",
    "trade_sub": "{code}{measures}",
    "tile_share": "Share of {reporter}'s {flow}",
    "tile_share_note": "#{rank} of {n} {roles}, {span}",
    "tile_share_plain": "{n} {roles}, {span}",
    "tile_side": "In {partner}'s {flow}",
    "tile_side_note": "{reporter}'s share, {period}",
    "tile_periods": "{periods} with trade",
    "tile_periods_note": "of {n} in the query",
    "panel_partner_uv": "Unit value, {unit}: {partner} and all {roles}",
    "all": "All {roles}",
    "others": "All other {roles}",
    "position_title": "{partner}: {first} of {reporter}'s {flow} in {p0}, {last} in {p1}",
    "position_sub": "{partner} against all other {roles}, {metric} by {period}",
    "position_main": "{metric} by {period}; share and rank above each bar",
    "position_growth": "Change on the previous {period}",
    "comp_title_first": "{partner} was {reporter}'s largest {role}, with {share} of the total",
    "comp_title_rank": "{partner} ranked #{rank} among {reporter}'s {n} {roles}, with {share}",
    "comp_title_plain": "{reporter}'s largest {roles}",
    "comp_sub": "{metric} by {role}, {span} total; {partner} in orange",
    "comp_sub_none": "{metric} by {role}, {span} total; no {flow} {to} {partner} recorded",
    "comp_other": "Other {n} {roles}",
    "comp_note": "CAGR compares {first} with {last}.",
    "comp_order_note": "Listed by {order}, not ranked: {metric} is missing for some {roles}, so "
                       "their order by {metric} cannot be known.",
    "shares_title": "{partner}'s share went from {first} in {p0} to {last} in {p1}",
    "shares_title_plain": "{partner} and its largest competitors",
    "shares_sub": "Share of {reporter}'s {flow} by {period}: {partner} and the {n} largest other "
                  "{roles}",
    "prices_title": "{partner}'s unit value: {mine} {unit} in {period}, against {every} for "
                    "all {roles}",
    "prices_title_plain": "Unit values of {partner} and its largest competitors",
    "prices_sub": "Unit value in {unit} by {period}: {partner}, all {roles} together, and the "
                  "{n} largest other {roles}",
    "products_title": "{name} made up {share} of {flow} {to} {partner}",
    "products_title_plain": "Products traded with {partner}",
    "products_sub": "{metric} by {level}, {span} total | share of the trade with {partner} | "
                    "{partner}'s share of {reporter}'s {flow} of it",
    "other_products": "Other {n} {level}",
    "side_title": "{reporter}: {first} of {partner}'s {flow} in {p0}, {last} in {p1}",
    "side_title_plain": "{reporter} in {partner}'s {flow}",
    "side_sub": "{partner}'s {flow} of {product}, {reported}; {reporter} in orange",
    "side_main": "{metric} by {period}; {reporter}'s share and rank above each bar",
    "side_top": "{partner}'s largest {roles}, {span} total",
    "side_top_period": "{partner}'s largest {roles} in {period}",
    "side_others": "Other {roles}",
    "mirror_title": "{period}: {reporter} reported {mine}, {partner} {theirs}",
    "mirror_title_plain": "The two countries' figures for the same trade",
    "mirror_sub": "{reporter}'s {flow} {to} {partner} as {reporter} reports them, beside "
                  "{partner}'s {side_flow} {other_to} {reporter} as {partner} reports them",
    "mirror_panel": "{metric} by {period}",
    "mirror_reporter": "As {reporter} reports them",
    "mirror_partner": "As {partner} reports them",
    "mirror_note": "Each figure as its country reports it, without adjustment; imports are "
                   "usually valued CIF and exports FOB.",
    "other_title": "{reporter}'s balance of trade with {partner} in these products: a {kind} "
                   "of {amount} over {span}",
    "other_title_plain": "{reporter}'s trade with {partner} in both directions",
    "other_sub": "{metric} by {period}: {reporter}'s imports from and exports to {partner}, "
                 "and the balance",
    "imports_from": "Imports from {partner}",
    "exports_to": "Exports to {partner}",
    "balance": "Balance: exports − imports",
    "season_title": "{partner}, month by month, {y0}–{y1}",
}


class PartnerWords(Words):
    """Chart text for a partner report: its phrases first, then the report charts' phrases.
    With a partner name, the context line names the partner too."""

    def __init__(self, analysis: Analysis, partner: str | None = None):
        super().__init__(analysis)
        self.partner_name = partner

    def __call__(self, key, **values) -> str:
        return PHRASES[key].format(**values) if key in PHRASES else super().__call__(key, **values)

    def context(self) -> str:
        q = self.a.q
        if not self.partner_name:
            return super().context()
        to = "from" if q.flow == "Imports" else "to"
        return (f"{q.reporter_name} · {q.flow} {to} {self.partner_name} · {q.product_label} · "
                f"{q.span}")


class PartnerCharts(Charts):
    def __init__(self, pa: PartnerAnalysis, folder):
        super().__init__(pa.a, folder)
        self.pa = pa
        self.t = Terms(pa)
        self.w = PartnerWords(pa.a, pa.name)

    def save_view(self, view: Analysis, *args, **kwargs):
        """Save a chart of another view of the trade: its foot gives that view's source line,
        estimates and context."""
        words, self.w = self.w, PartnerWords(view)
        try:
            self.save(*args, **kwargs)
        finally:
            self.w = words

    def common(self) -> dict:
        t = self.t
        return {"reporter": t.reporter, "partner": t.partner, "flow": t.flow, "to": t.to,
                "roles": self.q.roles, "role": self.q.role, "span": self.span,
                "period": self.w.period_word()}

    # -- 1 ------------------------------------------------------------------------------
    def trade(self):
        pa, w, m, s = self.pa, self.w, self.m, self.pa.summary
        if not pa.traded:
            return
        periods = self.shown
        xs = np.arange(len(periods))
        companion = pa.metrics[1] if len(pa.metrics) > 1 else None
        unit_values = pa.unit_values
        bottom = companion is not None or unit_values is not None
        fig = plt.figure(figsize=(14, 9.6 if bottom else 6.2))
        grid = fig.add_gridspec(2 if bottom else 1, 2, height_ratios=[3.0, 2.5] if bottom else [1])

        ax = fig.add_subplot(grid[0, :])
        series = pa.series[m.key]
        values = series[periods].tolist()
        nums = numbers_of(values)
        top = np.nanmax(nums) if np.any(nums > 0) else 1.0
        ax.bar(xs, np.nan_to_num(nums), 0.68, color=ACCENT)
        labelled = len(periods) <= LABEL_LIMIT
        for i, (period, value) in enumerate(zip(periods, values)):
            if is_gap(value) or not labelled:
                continue
            ax.text(i, number(value) + top * 0.02, w.figure(value, m), ha="center",
                    va="bottom", fontsize=9.5, fontweight="bold")
            index = pa.periods.index(period)
            if index:
                change = change_between(value, series[pa.periods[index - 1]])
                if not is_gap(change) and change == change:
                    ax.text(i, number(value) + top * 0.095, w.pct(change, 0, signed=True),
                            ha="center", va="bottom", fontsize=8.5,
                            color=NAVY if change >= 0 else ACCENT)
        mark_gaps(ax, xs, values, top, w, rotate=len(periods) > 12)
        ax.set_ylim(0, top * 1.25)
        self.period_axis(ax, periods)
        axis_amount(ax.yaxis, top)
        change_text = w("panel_change", period=w.period_word()) if labelled else ""
        total_text = (w("panel_total_gap", gap=w.gap(s["total"])) if is_gap(s["total"]) else
                      w("panel_total", total=w.figure(s["total"], m)))
        ax.set_title(w("panel_main", metric=w.metric_title(m), period=w.period_word(),
                       total=total_text, change=change_text))
        y_grid(ax)

        if bottom:
            if companion is not None:
                ax = fig.add_subplot(grid[1, 0] if unit_values is not None else grid[1, :])
                values = pa.series[companion.key][periods].tolist()
                nums = numbers_of(values)
                ctop = np.nanmax(nums) if np.any(nums > 0) else 1.0
                ax.bar(xs, np.nan_to_num(nums), 0.68, color=SKY)
                if len(periods) <= LABEL_LIMIT:
                    for i, value in enumerate(values):
                        if not is_gap(value):
                            ax.text(i, number(value) + ctop * 0.03, w.figure(value, companion),
                                    ha="center", va="bottom", fontsize=8)
                mark_gaps(ax, xs, values, ctop, w, rotate=True)
                ax.set_ylim(0, ctop * 1.3)
                self.period_axis(ax, periods, 8.5)
                axis_amount(ax.yaxis, ctop)
                ax.set_title(w("panel_companion", metric=w.metric_title(companion),
                               period=w.period_word()))
                y_grid(ax)
            if unit_values is not None:
                ax = fig.add_subplot(grid[1, 1] if companion is not None else grid[1, :])
                volume = next(x for x in pa.metrics if x.key == self.q.unit_value[1])
                mine = numbers_of(unit_values[periods].tolist())
                every = numbers_of(self.a.unit_values[periods].tolist())
                utop = max(np.nanmax(mine) if np.any(mine > 0) else 0,
                           np.nanmax(every) if np.any(every > 0) else 0) or 1.0
                ax.plot(xs, every, color=NAVY, linewidth=1.6, linestyle="--", marker="o",
                        markersize=4, label=w("all", roles=w.role(True)))
                ax.plot(xs, mine, color=ACCENT, linewidth=2.2, marker="o", markersize=5,
                        label=fmt.short(pa.name, 26))
                if len(periods) <= LABEL_LIMIT:
                    for i, value in enumerate(mine):
                        if value == value:
                            ax.text(i, value + utop * 0.04, w.unit_price(value), ha="center",
                                    va="bottom", fontsize=8.5, color=ACCENT)
                mark_gaps(ax, xs, unit_values[periods].tolist(), utop, w, rotate=True)
                ax.set_ylim(0, utop * 1.3)
                self.period_axis(ax, periods, 8.5)
                ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: w.unit_price(v)))
                ax.legend(loc="lower left", fontsize=8.5)
                ax.set_title(w("panel_partner_uv", unit=w.unit_value_unit(volume),
                               partner=fmt.short(pa.name, 24), roles=w.role(True)))
                y_grid(ax)

        kpis = [(w("tile_total", metric=w.metric(m)), w.figure(s["total"], m),
                 f"{m.unit}, {self.span}" if m.unit else self.span),
                (w("tile_growth"), w.pct(s["cagr"], signed=True), self.growth_note()),
                (w("tile_share", reporter=self.t.reporter, flow=self.t.flow),
                 w.pct(s["share"], 0),
                 w("tile_share_note", rank=s["rank"], n=s["partners"], roles=w.role(True),
                   span=self.span) if known(s["rank"]) else
                 w("tile_share_plain", n=s["partners"], roles=w.role(True), span=self.span))]
        side = self.latest_side_share()
        if side is not None:
            period, share = side
            kpis.append((w("tile_side", partner=fmt.short(pa.name, 18), flow=self.t.side_flow),
                         w.pct(share, 0), w("tile_side_note", reporter=self.t.reporter,
                                            period=w.period(period))))
        else:
            kpis.append((w("tile_periods", periods=w.period_word(True).capitalize()),
                         str(s["traded"]), w("tile_periods_note", n=len(pa.periods))))
        notes = []
        if unit_values is not None:
            volume = next(x for x in pa.metrics if x.key == self.q.unit_value[1])
            notes.append(w("note_unit_value", period=w.period_word(), volume=w.metric(volume)))
        if self.cut:
            notes.append(w("note_latest", n=len(periods), periods=w.period_word(True),
                           period=w.period_word()))
        code = "" if self.q.product_code in ("TOTAL", "AG2", "AG4", "AG6") else \
            f"HS {self.q.product_code}, "
        shown = [m, companion] + ([x for x in pa.metrics if x.key in self.q.unit_value]
                                  if unit_values is not None else [])
        self.save(fig, "01_trade_with_partner.png",
                  self.fitted(fig, "trade_title", "product", reporter=self.t.reporter,
                              flow=self.t.flow, product=w.product_phrase(), to=self.t.to,
                              partner=pa.name, span=self.span),
                  w("trade_sub", code=code, measures=w.measures()), " ".join(notes),
                  tiles=kpis, metrics=shown)

    def growth_note(self) -> str:
        w, s, years = self.w, self.pa.summary, self.pa.years
        if is_gap(s["cagr"]):
            return w("tile_growth_gap", metric=w.metric(self.m).capitalize())
        if s["cagr"] != s["cagr"]:
            return (w("tile_growth_undefined") if len(years) >= 2 else
                    w("tile_growth_short", years="calendar years" if self.a.monthly else "years"))
        note = w("tile_growth_note", trend=w.pct(s["trend"], signed=True))
        return note + w("tile_years", y0=years[0], y1=years[-1])

    def latest_side_share(self):
        """The latest period with the reporter's share of the partner's trade, and the share."""
        f = self.pa.side_position
        if f is None:
            return None
        rows = [(r["Period"], r["Share"]) for r in f.to_dict("records") if known(r["Share"])]
        return rows[-1] if rows else None

    # -- 2 ------------------------------------------------------------------------------
    def standing(self):
        pa, w, m = self.pa, self.w, self.m
        if not pa.traded:
            return
        f = pa.position.set_index("Period").loc[self.shown]
        xs = np.arange(len(self.shown))
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 6.2),
                                     gridspec_kw={"width_ratios": [1.6, 1]})
        self.stacked(a1, xs, f, pa.name, w("others", roles=w.role(True)))
        a1.set_title(w("position_main", metric=w.metric_title(m), period=w.period_word()))
        width = 0.38
        g_mine = numbers_of(f["Growth"])[1:]
        g_all = numbers_of(f["Total growth"])[1:]
        x2 = np.arange(len(g_mine))
        a2.bar(x2 - width / 2, np.nan_to_num(g_mine), width, color=ACCENT,
               label=fmt.short(pa.name, 22))
        a2.bar(x2 + width / 2, np.nan_to_num(g_all), width, color=GREY,
               label=w("all", roles=w.role(True)))
        a2.axhline(0, color="#555555", linewidth=1)
        self.period_axis(a2, self.shown[1:], 8.5)
        a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt.pct(v, 0)))
        a2.legend(loc="upper right", fontsize=8.5)
        a2.set_title(w("position_growth", period=w.period_word()))
        y_grid(a2)
        first, last = f["Share"].iloc[0], f["Share"].iloc[-1]
        self.save(fig, "02_partner_share.png",
                  w("position_title", partner=pa.name, first=w.pct(first, 0),
                    last=w.pct(last, 0), reporter=self.t.reporter, flow=self.t.flow,
                    p0=w.period(self.shown[0]), p1=w.period(self.shown[-1])),
                  w("position_sub", partner=pa.name, roles=w.role(True), metric=w.metric(m),
                    period=w.period_word()))

    def stacked(self, ax, xs, f: pd.DataFrame, name, rest_label):
        """One country's figure stacked under the rest of the total, by period, with its share
        and rank above each bar; Missing where the total is."""
        w = self.w
        mine = numbers_of(f["Figure"])
        world = numbers_of(f["Total"])
        ax.bar(xs, np.nan_to_num(mine), 0.7, color=ACCENT, label=fmt.short(name, 30))
        ax.bar(xs, np.nan_to_num(world - mine), 0.7, bottom=np.nan_to_num(mine), color=LIGHT_GREY,
               label=rest_label)
        top = np.nanmax(world) if np.any(world > 0) else 1
        if len(xs) <= LABEL_LIMIT:
            for x, total, share, rank in zip(xs, world, f["Share"], f["Rank"]):
                if total == total and not is_gap(share):
                    label = w.pct(share, 0) + (f"\n{w('rank', n=int(number(rank)))}"
                                               if known(rank) else "")
                    ax.text(x, total + top * 0.02, label, ha="center", va="bottom", fontsize=8.5)
        mark_gaps(ax, xs, f["Total"].tolist(), top, w, rotate=True)
        ax.set_ylim(0, top * 1.22)
        self.period_axis(ax, list(f.index), 8.5)
        axis_amount(ax.yaxis, top)
        ax.legend(loc="upper left", ncol=2)
        y_grid(ax)

    # -- 3 ------------------------------------------------------------------------------
    def rivals(self):
        pa, a, w, m = self.pa, self.a, self.w, self.m
        table = pa.competitors
        if table.empty:
            return
        ordered_by_other = a.partner_order.key != m.key
        if not ordered_by_other:
            table = table[table[m.heading].map(number) > 0]
        if table.empty or all(is_gap(v) for v in table[m.heading]):
            return
        names, values, labels, colours, gaps = [], [], [], [], []
        for row in table.to_dict("records"):
            names.append(w.partner(row["Code"]))
            value = row[m.heading]
            gaps.append(is_gap(value))
            values.append(0.0 if is_gap(value) else number(value))
            growth = row.get("CAGR", np.nan)
            tail = (w("label_cagr", g=w.pct(growth, signed=True))
                    if not is_gap(growth) and growth == growth else w.status(row["Status"]))
            labels.append(w.gap(value) if is_gap(value) else
                          f"{w.figure(value, m)}  |  {w.pct(row['Share'])}  |  {tail}")
            colours.append(ACCENT if row["Code"] == pa.code else NAVY)
        rest = a.partners[~a.partners["Code"].isin(table["Code"])]
        if len(rest):
            rest_total = total_of(rest[m.heading])
            names.append(w("comp_other", n=len(rest), roles=w.role(True)))
            gaps.append(is_gap(rest_total))
            values.append(0.0 if is_gap(rest_total) else number(rest_total))
            labels.append(w.gap(rest_total) if is_gap(rest_total) else
                          f"{w.figure(rest_total, m)}  |  {w.pct(total_of(rest['Share']))}")
            colours.append(LIGHT_GREY)
        order = list(range(len(names)))[::-1]
        fig, ax = plt.subplots(figsize=(13, 2.4 + 0.62 * len(names)))
        ax.barh(range(len(names)), [values[i] for i in order], 0.64,
                color=[colours[i] for i in order])
        vmax = max(max(values), 1.0)
        for row_i, i in enumerate(order):
            ax.text(values[i] + vmax * 0.012, row_i, labels[i], va="center",
                    fontsize=9.5, color=GAP_GREY if gaps[i] else "#1A1A1A",
                    style="italic" if gaps[i] else "normal")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels([fmt.short(names[i], 28) for i in order], fontsize=10.5)
        ax.set_xlim(0, vmax * 1.6)
        axis_amount(ax.xaxis, vmax)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        x_grid(ax)
        s, words = pa.summary, self.common()
        if pa.traded and known(s["share"]) and s["rank"] == 1:
            title = w("comp_title_first", share=w.pct(s["share"]), **words)
        elif pa.traded and known(s["share"]) and known(s["rank"]):
            title = w("comp_title_rank", rank=s["rank"], n=s["partners"], share=w.pct(s["share"]),
                      **words)
        else:
            title = w("comp_title_plain", **words)
        subtitle = w("comp_sub" if pa.traded else "comp_sub_none", metric=w.metric_title(m),
                     **words)
        notes = []
        if len(pa.years) >= 2:
            notes.append(w("comp_note", first=pa.years[0], last=pa.years[-1]))
        if ordered_by_other:
            notes.append(w("comp_order_note", order=w.metric(a.partner_order),
                           metric=w.metric(m), roles=w.role(True)))
        self.save(fig, "03_competitors.png", title, subtitle, "\n".join(notes))

    # -- 4 ------------------------------------------------------------------------------
    def rival_shares(self):
        pa, a, w = self.pa, self.a, self.w
        codes = ([pa.code] if pa.traded else []) + pa.rivals
        if not codes or a.partner_shares.empty:
            return
        shares = a.partner_shares[self.shown]
        xs = np.arange(len(self.shown))
        fig, ax = plt.subplots(figsize=(13.5, 6.2))
        top, ends = 0.0, []
        for i, code in enumerate(codes):
            values = numbers_of(shares.loc[code])
            mine = code == pa.code
            colour = ACCENT if mine else RIVAL_COLOURS[(i - (1 if pa.traded else 0))
                                                       % len(RIVAL_COLOURS)]
            ax.plot(xs, values, color=colour, linewidth=3 if mine else 1.6, marker="o",
                    markersize=5 if mine else 3.5, label=fmt.short(w.partner(code), 26),
                    zorder=3 if mine else 2)
            finite = [(x, v) for x, v in zip(xs, values) if v == v]
            if finite:
                top = max(top, max(v for _, v in finite))
                ends.append((mine, finite[-1], colour))
        # The last share of each line at its end; one that would sit on another is left out
        placed = []
        for mine, (x, value), colour in sorted(ends, key=lambda e: (not e[0], -e[1][1])):
            if all(abs(value - other) >= top * 0.035 for other in placed):
                placed.append(value)
                ax.text(x + 0.15, value, w.pct(value, 0), color=colour, va="center",
                        fontsize=9, fontweight="bold" if mine else "normal")
        gaps = [any(is_gap(v) for v in shares[p]) for p in shares.columns]
        for x, gap in zip(xs, gaps):
            if gap:
                ax.text(x, 0.01, w.gap("Missing"), ha="center", va="bottom", fontsize=8,
                        color=GAP_GREY, rotation=90, style="italic")
        ax.set_ylim(0, max(top * 1.15, 0.05))
        ax.set_xlim(-0.5, len(xs) - 0.2)
        self.period_axis(ax, self.shown)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9.5)
        y_grid(ax)
        words = self.common()
        first, last = (shares.loc[pa.code].iloc[0], shares.loc[pa.code].iloc[-1]) \
            if pa.traded else (None, None)
        if pa.traded and known(first) and known(last):
            title = w("shares_title", first=w.pct(first, 0), last=w.pct(last, 0),
                      p0=w.period(self.shown[0]), p1=w.period(self.shown[-1]), **words)
        else:
            title = w("shares_title_plain", **words)
        self.save(fig, "04_competitor_shares.png", title,
                  w("shares_sub", n=len(pa.rivals), **words),
                  w("note_latest", n=len(self.shown), periods=w.period_word(True),
                    period=w.period_word()) if self.cut else "")

    # -- 5 ------------------------------------------------------------------------------
    def prices(self):
        pa, a, w = self.pa, self.a, self.w
        if pa.unit_values is None or not pa.traded:
            return
        mine = numbers_of(pa.unit_values[self.shown].tolist())
        if not np.any(mine > 0):
            return
        xs = np.arange(len(self.shown))
        volume = next(x for x in pa.metrics if x.key == self.q.unit_value[1])
        fig, ax = plt.subplots(figsize=(13.5, 6.2))
        lines = [(w("all", roles=w.role(True)), numbers_of(a.unit_values[self.shown].tolist()),
                  NAVY, 2.0, "--")]
        shown_rivals = pa.rivals[:PRICE_RIVALS]
        for i, code in enumerate(shown_rivals):
            lines.append((w.partner(code), numbers_of(pa.rival_prices.loc[code, self.shown]),
                          RIVAL_COLOURS[(i + 1) % len(RIVAL_COLOURS)], 1.2, "-"))
        top = np.nanmax(mine)
        for name, values, colour, width, style in lines:
            ax.plot(xs, values, color=colour, linewidth=width, linestyle=style, marker="o",
                    markersize=3.5, label=fmt.short(name, 26))
            if np.any(values > 0):
                top = max(top, np.nanmax(values))
        ax.plot(xs, mine, color=ACCENT, linewidth=3, marker="o", markersize=5,
                label=fmt.short(pa.name, 26), zorder=3)
        if len(xs) <= LABEL_LIMIT:
            for x, value in zip(xs, mine):
                if value == value:
                    ax.text(x, value + top * 0.035, w.unit_price(value), ha="center",
                            va="bottom", fontsize=8.5, color=ACCENT, fontweight="bold",
                            zorder=4, bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                                edgecolor="none", alpha=0.85))
        mark_gaps(ax, xs, pa.unit_values[self.shown].tolist(), top, w, rotate=True)
        ax.set_ylim(0, top * 1.2)
        ax.set_xlim(-0.5, len(xs) - 0.5)
        self.period_axis(ax, self.shown)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: w.unit_price(v)))
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9.5)
        y_grid(ax)
        words, unit = self.common(), w.unit_value_unit(volume)
        both = [p for p in self.shown if known(pa.unit_values[p]) and known(a.unit_values[p])]
        if both:
            p = both[-1]
            title = w("prices_title", **{**words, "period": w.period(p)},
                      mine=w.unit_price(pa.unit_values[p]), unit=unit,
                      every=w.unit_price(a.unit_values[p]))
        else:
            title = w("prices_title_plain", **words)
        notes = [w("note_unit_value", period=w.period_word(), volume=w.metric(volume))]
        if self.cut:
            notes.append(w("note_latest", n=len(self.shown), periods=w.period_word(True),
                           period=w.period_word()))
        self.save(fig, "05_prices.png", title,
                  w("prices_sub", unit=unit, n=len(shown_rivals), **words), " ".join(notes),
                  metrics=[x for x in pa.metrics if x.key in self.q.unit_value])

    # -- 6 ------------------------------------------------------------------------------
    def traded_products(self):
        pa, w, m = self.pa, self.w, self.m
        table = pa.products
        if table is None or len(table) < 2:
            return
        top = table.head(TOP_N)
        rest = table.iloc[TOP_N:]
        names, values, labels, gaps = [], [], [], []
        for row in top.to_dict("records"):
            names.append(f"{row['Code']} {product_name(row['Name'], row['Code'])}")
            value = row[m.heading]
            gaps.append(is_gap(value))
            values.append(0.0 if is_gap(value) else number(value))
            labels.append(w.gap(value) if is_gap(value) else
                          f"{w.figure(value, m)}  |  {w.pct(row['Share'])}  |  "
                          f"{w.pct(row['Market share'])}")
        if len(rest):
            rest_total = total_of(rest[m.heading])
            names.append(w("other_products", n=len(rest), level=self.level_plural()))
            gaps.append(is_gap(rest_total))
            values.append(0.0 if is_gap(rest_total) else number(rest_total))
            labels.append(w.gap(rest_total) if is_gap(rest_total) else
                          f"{w.figure(rest_total, m)}  |  {w.pct(total_of(rest['Share']))}")
        order = list(range(len(names)))[::-1]
        fig, ax = plt.subplots(figsize=(13, 2.4 + 0.62 * len(names)))
        ax.barh(range(len(names)), [values[i] for i in order], 0.64,
                color=[LIGHT_GREY if i == len(top) else ACCENT for i in order])
        vmax = max(max(values), 1e-9)
        for row_i, i in enumerate(order):
            ax.text(values[i] + vmax * 0.012, row_i, labels[i], va="center", fontsize=9.5,
                    color=GAP_GREY if gaps[i] else "#1A1A1A",
                    style="italic" if gaps[i] else "normal")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels([fmt.short(names[i], 44) for i in order], fontsize=9.5)
        ax.set_xlim(0, vmax * 1.6)
        axis_amount(ax.xaxis, vmax)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        x_grid(ax)
        words = self.common()
        lead = top.iloc[0]
        if known(lead["Share"]):
            title = self.fitted(fig, "products_title", "name",
                                name=product_name(lead["Name"], lead["Code"]),
                                share=w.pct(lead["Share"], 0), **words)
        else:
            title = w("products_title_plain", **words)
        self.save(fig, "06_products.png", title,
                  w("products_sub", metric=w.metric_title(m), level=self.q.product_level,
                    **words))

    def level_plural(self) -> str:
        """What a product row is, in the plural: 'HS chapters', 'HS 6-digit products'."""
        level = self.q.product_level.split(",")[0].split(" (")[0]
        return level + ("" if level.endswith("s") else "s")

    # -- 7 ------------------------------------------------------------------------------
    def partner_side(self):
        pa = self.pa
        side = pa.side
        if side is None:
            return
        w, m, t = self.w, side.metric, self.t
        f = pa.side_position.set_index("Period").loc[self.shown]
        xs = np.arange(len(self.shown))
        table = pa.side_partners
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 6.4),
                                     gridspec_kw={"width_ratios": [1.5, 1]})
        self.stacked(a1, xs, f, t.reporter, PartnerWords(side)("side_others",
                                                               roles=side.q.roles))
        a1.set_title(w("side_main", metric=w.metric_title(m), period=w.period_word(),
                       reporter=t.reporter))
        rows = table.head(TOP_N + 1).to_dict("records") if table is not None else []
        rows = [r for r in rows if known(r[m.heading]) and number(r[m.heading]) > 0] or rows
        names = [fmt.short(side.partner_names.get(r["Code"], r["Code"]), 24) for r in rows]
        values = [0.0 if is_gap(r[m.heading]) else number(r[m.heading]) for r in rows]
        colours = [ACCENT if r["Code"] == self.q.reporter_code else NAVY for r in rows]
        ys = np.arange(len(rows))[::-1]
        a2.barh(ys, values, 0.64, color=colours)
        vmax = max(values + [1e-9])
        for y, r, v in zip(ys, rows, values):
            a2.text(v + vmax * 0.02, y, w.gap(r[m.heading]) if is_gap(r[m.heading]) else
                    w.pct(r["Share"]), va="center", fontsize=9)
        a2.set_yticks(ys)
        a2.set_yticklabels(names, fontsize=9.5)
        a2.set_xlim(0, vmax * 1.35)
        axis_amount(a2.xaxis, vmax)
        a2.xaxis.set_major_locator(MaxNLocator(4))
        period = pa.side_partners_period
        a2.set_title(w("side_top", partner=fmt.short(t.partner, 22), roles=side.q.roles,
                       span=self.span) if period is None else
                     w("side_top_period", partner=fmt.short(t.partner, 22), roles=side.q.roles,
                       period=w.period(period)))
        x_grid(a2)
        known_rows = [(p, r) for p, r in f.iterrows() if known(r["Share"])]
        words = {"reporter": t.reporter, "partner": t.partner, "flow": t.side_flow}
        if known_rows:
            (p0, r0), (p1, r1) = known_rows[0], known_rows[-1]
            title = w("side_title", first=w.pct(r0["Share"], 0), last=w.pct(r1["Share"], 0),
                      p0=w.period(p0), p1=w.period(p1), **words)
        else:
            title = w("side_title_plain", **words)
        self.save_view(side, fig, "07_partner_side.png", title,
                       w("side_sub", product=w.product_phrase(), reported=t.reported_as, **words))

    # -- 8 ------------------------------------------------------------------------------
    def both_reports(self):
        pa, w, t = self.pa, self.w, self.t
        if not pa.mirror or pa.side_status == "unreported":
            return
        keys = ["value"] + [k for k in pa.mirror if k != "value"][:1]
        keys = [k for k in keys if k in pa.mirror]
        metrics = [next(x for x in pa.metrics if x.key == k) for k in keys]
        xs = np.arange(len(self.shown))
        fig, axes = plt.subplots(1, len(keys), figsize=(14.5, 6.2), squeeze=False)
        width = 0.38
        for ax, metric, key in zip(axes[0], metrics, keys):
            frame = pa.mirror[key].set_index("Period").loc[self.shown]
            mine, theirs = numbers_of(frame["Reporter"]), numbers_of(frame["Partner"])
            top = max(np.nanmax(mine) if np.any(mine > 0) else 0,
                      np.nanmax(theirs) if np.any(theirs > 0) else 0) or 1.0
            ax.bar(xs - width / 2, np.nan_to_num(mine), width, color=NAVY,
                   label=w("mirror_reporter", reporter=fmt.short(t.reporter, 22)))
            ax.bar(xs + width / 2, np.nan_to_num(theirs), width, color=ACCENT,
                   label=w("mirror_partner", partner=fmt.short(t.partner, 22)))
            if len(xs) <= LABEL_LIMIT:
                for x, a_, b_ in zip(xs, mine, theirs):
                    for offset, value in ((-width / 2, a_), (width / 2, b_)):
                        if value == value:
                            ax.text(x + offset, value + top * 0.015, w.figure(value, metric),
                                    ha="center", va="bottom", fontsize=7.5, rotation=90)
            for offset, column in ((-width / 2, "Reporter"), (width / 2, "Partner")):
                mark_gaps(ax, xs + offset, frame[column].tolist(), top, w, rotate=True)
            ax.set_ylim(0, top * 1.3)
            self.period_axis(ax, self.shown, 8.5)
            axis_amount(ax.yaxis, top)
            ax.legend(loc="upper left", fontsize=8.5)
            ax.set_title(w("mirror_panel", metric=w.metric_title(metric),
                           period=w.period_word()))
            y_grid(ax)
        frame = pa.mirror["value"]
        both = [r for r in frame.to_dict("records") if known(r["Reporter"]) and known(r["Partner"])
                and r["Reporter"] > 0 and r["Partner"] > 0]
        value = next(x for x in pa.metrics if x.key == "value")
        if both:
            row = both[-1]
            title = w("mirror_title", period=w.period(row["Period"]), reporter=t.reporter,
                      partner=t.partner, mine=fmt.amount(row["Reporter"], value),
                      theirs=fmt.amount(row["Partner"], value))
        else:
            title = w("mirror_title_plain")
        notes = [w("mirror_note")]
        # The partner's own figures can include the source's estimates too
        marked = [metric for metric in metrics if pa.side_estimates(metric.key) & set(self.shown)]
        if marked:
            notes.append(PartnerWords(pa.side).estimate_note(marked))
        self.save(fig, "08_both_reports.png", title,
                  w("mirror_sub", reporter=t.reporter, partner=t.partner, flow=t.flow, to=t.to,
                    side_flow=t.side_flow, other_to=t.other_to), "\n".join(notes),
                  metrics=metrics)

    # -- 9 ------------------------------------------------------------------------------
    def other_direction(self):
        pa, w, t = self.pa, self.w, self.t
        if pa.other is None or pa.balance is None:
            return
        value = next(x for x in pa.metrics if x.key == "value")
        main, other = pa.series["value"], pa.view_series("other", "value")
        imports, exports = (main, other) if self.q.flow == "Imports" else (other, main)
        xs = np.arange(len(self.shown))
        imp = numbers_of(imports[self.shown].tolist())
        exp = numbers_of(exports[self.shown].tolist())
        bal = numbers_of(pa.balance[self.shown].tolist())
        fig, ax = plt.subplots(figsize=(13.5, 6.2))
        width = 0.38
        ax.bar(xs - width / 2, np.nan_to_num(exp), width, color=NAVY,
               label=w("exports_to", partner=fmt.short(t.partner, 24)))
        ax.bar(xs + width / 2, np.nan_to_num(imp), width, color=SKY,
               label=w("imports_from", partner=fmt.short(t.partner, 24)))
        ax.plot(xs, bal, color=ACCENT, linewidth=2.4, marker="o", markersize=5,
                label=w("balance"))
        ax.axhline(0, color="#555555", linewidth=1)
        span = max(np.nanmax(np.abs(np.concatenate([imp, exp, bal]))) if np.any(
            np.isfinite(np.concatenate([imp, exp, bal]))) else 1.0, 1e-9)
        if len(xs) <= LABEL_LIMIT:
            for x, v in zip(xs, bal):
                if v == v:
                    ax.text(x, v + span * (0.04 if v >= 0 else -0.04), w.figure(v, value),
                            ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5,
                            color=ACCENT, fontweight="bold")
        for column, offset in ((exports, -width / 2), (imports, width / 2)):
            mark_gaps(ax, xs + offset, column[self.shown].tolist(), span, w, rotate=True)
        low = min(0.0, np.nanmin(bal) if np.any(np.isfinite(bal)) else 0.0)
        ax.set_ylim(low * 1.25 - span * 0.05, span * 1.25)
        self.period_axis(ax, self.shown)
        axis_amount(ax.yaxis, span)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9.5)
        y_grid(ax)
        total = total_of(pa.balance)
        words = {"reporter": t.reporter, "partner": t.partner, "span": self.span}
        if known(total) and total != 0:
            title = self.fitted(fig, "other_title", "partner",
                                kind="surplus" if total > 0 else "deficit",
                                amount=fmt.amount(abs(total), value), **words)
        else:
            title = w("other_title_plain", **words)
        self.save(fig, "09_other_direction.png", title,
                  w("other_sub", metric=w.metric_title(value), period=w.period_word(),
                    **words), metrics=[value])

    # -- 10 -----------------------------------------------------------------------------
    def months(self):
        pa, w, m = self.pa, self.w, self.m
        if not pa.monthly or not pa.traded:
            return
        years = sorted({p // 100 for p in pa.periods})
        if len(years) < 2:
            return
        series = pa.series[m.key]
        frame = pd.DataFrame(index=[str(y) for y in years], columns=range(1, 13), dtype=object)
        for p in pa.periods:
            frame.loc[str(p // 100), p % 100] = series[p]
        frame = frame.where(frame.notna(), 0.0)
        fig, ax = plt.subplots(figsize=(15, 2.6 + 0.6 * len(years)))
        self.heatmap(ax, frame, column_labels=[MONTHS[i - 1] for i in range(1, 13)])
        self.save(fig, "10_seasonality.png",
                  w("season_title", partner=pa.name, y0=years[0], y1=years[-1]),
                  w("season_sub", metric=w.metric_title(m)), w("season_note"), extra_top=0.3)

    def make_all(self):
        steps = [self.trade, self.standing, self.rivals, self.rival_shares, self.prices,
                 self.traded_products, self.partner_side, self.both_reports,
                 self.other_direction, self.months]
        for step in steps:
            try:
                step()
            except Exception as err:          # one chart failing must not stop the others
                plt.close("all")
                print(f"  ⚠ Chart '{step.__name__}' could not be drawn: {err}")
        return self.files
