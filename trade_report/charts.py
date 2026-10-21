"""Report charts in one house style: a left-aligned headline and subtitle, labelled bars, light
grids, a source line at the foot, saved at 200 dpi. Figures the source does not report are
marked 'Missing', never drawn as zero; a chart showing figures that include the source's own
estimates says so at its foot."""
from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from . import fmt  # noqa: E402
from .analysis import (MISSING, TOP_N, Analysis, hhi_band, is_gap, number,  # noqa: E402
                       total_of)
from .analysis import growth as change_between  # noqa: E402
from .findings import rated_growth  # noqa: E402
from .model import MONTHS, Metric, period_label  # noqa: E402

NAVY, SKY = "#1F4E79", "#7FB8E6"
ACCENT, GREY, LIGHT_GREY = "#E67E22", "#AEB6BF", "#D5D8DC"
TEAL, PURPLE, RED = "#16A085", "#8E44AD", "#C0392B"
GAP_GREY = "#7F7F7F"
SERIES = ["#1F4E79", "#E67E22", "#2E86C1", "#16A085", "#8E44AD", "#C0392B", "#B7950B",
          "#5D6D7E", "#27AE60", "#A04000", "#7FB8E6", "#884EA0"]
MAX_COLUMNS = 24    # periods drawn in a by-period chart; longer monthly queries show the latest
LABEL_LIMIT = 15    # bars labelled one by one up to this many periods

PHRASES = {
    "overview_title": "{reporter}'s {flow} of {product}, {span}",
    "overview_sub": "{code}all {roles}; {measures}",
    "tile_total": "Total {metric}",
    "tile_growth": "Growth (CAGR)",
    "tile_growth_note": "a year; trend {trend}",
    "tile_years": " ({y0}–{y1})",
    "label_cagr": "CAGR {g}",
    "rank": "#{n}",
    "tile_growth_gap": "{metric} missing in an end year",
    "tile_growth_undefined": "no trade in an end year",
    "tile_growth_short": "needs two complete {years}",
    "tile_largest": "Largest {role}",
    "tile_partners": "{roles}",
    "tile_hhi": "HHI {hhi}, {band}",
    "tile_hhi_gap": "HHI {hhi}",
    "panel_main": "{metric} by {period}{total}{change}",
    "panel_total": ", {total} in total",
    "panel_total_gap": "; the total is {gap}",
    "panel_change": "; change on the previous {period} above each bar",
    "panel_companion": "{metric} by {period}",
    "panel_unit_value": "Unit value, {unit}",
    "note_unit_value": "Unit values divide value by {volume} for each {period}; where either is "
                       "missing so is the unit value.",
    "note_latest": "Showing the latest {n} {periods}; every {period} is in the workbook.",
    "partners_title": "{name} was the largest {role}, with {share} of the total",
    "partners_title_plain": "{roles} by {metric}",
    "partners_sub": "{metric} by {role}, {span} total, top {n} of {total}{focus}",
    "partners_sub_order": "{metric} by {role}, {span} total; the {n} largest by {order} of "
                          "{total}{focus}",
    "partners_order_note": "Listed by {order}, not ranked: {metric} is missing for some "
                           "{roles}, so their order by {metric} cannot be known.",
    "partners_focus": "; {name} in orange",
    "partners_other": "Other {n} {roles}",
    "partners_note": "CAGR compares {first} with {last}.",
    "partners_excluded": "Not ranked, because {metric} is missing: {names}.",
    "heatmap_title": "{period} by {period2}, {role} by {role}",
    "heatmap_sub": "{metric}, top 12 {roles} by {span} {order}",
    "heatmap_note": "Blank = no trade recorded; Missing = not reported by the source.",
    "heatmap_other": "Other {n}",
    "total": "Total",
    "shares_title": "{name}'s share went from {first} in {p0} to {last} in {p1}",
    "shares_title_plain": "Shares by {role}, {period} by {period}",
    "shares_sub": "Share of {metric} by {role}: the five largest over the period and the rest",
    "all_others": "All others",
    "growth_title": "{name} grew fastest among the top {n}, {g} a year",
    "growth_title_plain": "Growth among the top {n} {roles}",
    "growth_sub": "The top {n} {roles} by {span} {metric}",
    "growth_cagr": "CAGR of {metric}, {y0} to {y1}",
    "growth_share": "Change in share, {y0} to {y1}, percentage points",
    "growth_none": "No CAGR for {names}: {reason}.",
    "growth_none_reason": "no trade in {y0} or {y1}, or {metric} missing",
    "conc_title_rise": "Concentration rose from HHI {h0} in {p0} to {h1} in {p1}",
    "conc_title_fall": "Concentration fell from HHI {h0} in {p0} to {h1} in {p1}",
    "conc_title_plain": "How concentrated the trade is",
    "conc_sub": "How much of the trade sits with a few {roles}",
    "conc_hhi": "HHI by {period} (0 to 10,000)",
    "conc_shares": "Share of the largest and the three largest",
    "conc_largest": "largest {role}",
    "conc_top3": "three largest {roles}",
    "conc_note": "HHI: sum of squared shares x 10,000. Bands: below 1,500 unconcentrated, "
                 "1,500 to 2,500 moderate, above 2,500 high.",
    "band_low": "unconcentrated", "band_mid": "moderately concentrated",
    "band_high": "highly concentrated",
    "products_title": "{name} ({code}) made up {share} of the {metric}",
    "products_title_plain": "{metric} by product",
    "products_sub": "{metric} by {level} and {period}; {n} in the data",
    "other_products": "Other products",
    "focus_title": "{name}: {first} of {reporter}'s {flow} in {p0}, {last} in {p1}",
    "focus_sub": "{name} against all other {roles}, {metric} by {period}",
    "focus_main": "{metric} by {period}; share and rank above each bar",
    "focus_growth": "Change on the previous {period}",
    "focus_others": "All other {roles}",
    "focus_all": "All {roles}",
    "season_title": "Month by month, {y0}–{y1}",
    "season_sub": "{metric} by month; rows are years",
    "season_note": "Blank = month outside the query; Missing = not reported by the source.",
    "note_estimates": "{metrics} include{s} figures {who} estimated rather than {reporter} "
                      "reported, used as the source gives them; the workbook's Source estimates "
                      "sheet lists them.",
}


class Words:
    """Every piece of chart text: the phrases above, filled in from the analysis."""

    def __init__(self, analysis: Analysis):
        self.a = analysis

    def __call__(self, key, **values) -> str:
        return PHRASES[key].format(**values)

    def partner(self, code) -> str:
        return str(self.a.partner_names.get(code, code))

    def reporter(self) -> str:
        return self.a.q.reporter_name

    def product_name(self, code) -> str:
        return str(self.a.product_names.get(code, code))

    def period(self, period, short=False) -> str:
        return period_label(period, self.a.monthly, short)

    def month(self, number_) -> str:
        return MONTHS[number_ - 1]

    def figure(self, value, metric: Metric) -> str:
        """A bare figure, for labels on a chart whose title gives the unit."""
        return fmt.figure(value, metric)

    def pct(self, value, digits=1, signed=False) -> str:
        return fmt.pct(value, digits, signed)

    def points(self, value) -> str:
        return fmt.points(value)

    def count(self, value) -> str:
        return fmt.count(value)

    def gap(self, value) -> str:
        return str(value)

    def status(self, status) -> str:
        return str(status)

    def source_note(self) -> str:
        return self.a.q.source_note

    def estimate_note(self, metrics) -> str:
        """A footnote naming the metrics shown whose figures include the source's own
        estimates; empty when there are none."""
        marked = [m for m in dict.fromkeys(m for m in metrics if m is not None)
                  if m.key in self.a.estimated]
        if not marked:
            return ""
        names = self.and_list([self.metric(m) for m in marked])
        return self("note_estimates", metrics=names[:1].upper() + names[1:],
                    s="s" if len(marked) == 1 else "", who=self.a.q.estimated_by,
                    reporter=self.reporter())

    def and_list(self, items) -> str:
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

    def context(self) -> str:
        q = self.a.q
        return f"{q.reporter_name} · {q.flow} · {q.product_label} · {q.span}"

    def measures(self) -> str:
        """'value in million USD; quantity in u (number of items)': each metric's unit, with
        COMTRADE's name for a quantity unit."""
        names = self.a.q.unit_names
        return "; ".join(f"{m.label.lower()} in {m.unit or 'source units'}"
                         + (f" ({names[m.unit].lower()})" if names.get(m.unit) else "")
                         for m in self.a.metrics)

    def unit_price(self, value) -> str:
        """A unit value, in the USD per unit of volume its panel title states."""
        return f"{number(value):,.0f}"

    def unit_value_unit(self, metric: Metric) -> str:
        return f"USD per {metric.unit or 'unit'}"

    def metric(self, metric: Metric) -> str:
        """The metric inside a sentence: 'value'."""
        return metric.label.lower()

    def metric_title(self, metric: Metric) -> str:
        """The metric at the start of a title, with its unit: 'Value (million USD)'."""
        return metric.heading

    def flow(self) -> str:
        return self.a.q.flow.lower()

    def role(self, plural=False) -> str:
        return self.a.q.roles if plural else self.a.q.role

    def period_word(self, plural=False) -> str:
        return self.a.period_word + ("s" if plural else "")

    def product_phrase(self) -> str:
        q = self.a.q
        if q.product_code in ("TOTAL", "AG2", "AG4", "AG6"):
            return "all products"
        return fmt.lower_first(q.product_desc)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def setup_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Segoe UI", "Helvetica", "DejaVu Sans"],
        "font.size": 10, "axes.titlesize": 11.5, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.titlepad": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#999999", "axes.labelcolor": "#333333",
        "xtick.color": "#333333", "ytick.color": "#333333",
        "legend.frameon": False, "legend.fontsize": 9,
    })


def y_grid(ax):
    ax.grid(axis="y", color="#E6E6E6", linewidth=0.8)
    ax.set_axisbelow(True)


def x_grid(ax):
    ax.grid(axis="x", color="#E6E6E6", linewidth=0.8)
    ax.set_axisbelow(True)


def axis_amount(axis, vmax):
    """Ticks in the metric's own unit (million USD, metric tons), never rescaled."""
    axis.set_major_formatter(FuncFormatter(lambda v, _: fmt.tick(v, vmax)))


def numbers_of(values) -> np.ndarray:
    return np.array([np.nan if is_gap(v) else number(v) for v in values], dtype=float)


def mark_gaps(ax, xs, values, ymax, words: Words, rotate=False):
    """Write 'Missing' where a bar cannot be drawn."""
    for x, value in zip(xs, values):
        if is_gap(value):
            ax.text(x, ymax * 0.02, words.gap(value), ha="center", va="bottom",
                    fontsize=8, color=GAP_GREY, rotation=90 if rotate else 0, style="italic")


class Charts:
    def __init__(self, a: Analysis, folder: Path):
        self.a, self.q, self.folder = a, a.q, folder
        self.w = Words(a)
        self.files: list[Path] = []
        self.m = a.metric
        periods = a.periods
        self.shown = periods[-MAX_COLUMNS:] if len(periods) > MAX_COLUMNS else periods
        self.cut = len(periods) > MAX_COLUMNS
        self.span = self.q.span

    # -- frame --------------------------------------------------------------------------
    def fitted(self, fig, key, part, **values) -> str:
        """The title PHRASES[key], with its `part` (a long product name) shortened so the
        title fits on one line across the figure."""
        room = int(fig.get_figwidth() * 8.5)        # characters of the 15 pt bold title
        title = self.w(key, **values)
        if len(title) > room:
            text = values[part]
            values[part] = fmt.short(text, max(24, len(text) - (len(title) - room)))
            title = self.w(key, **values)
        return title

    def save(self, fig, name, title, subtitle="", note="", extra_top=0.0, tiles=None,
             metrics=None):
        """Title the figure, add its foot and save it. `metrics` are those the chart shows,
        the analysis metric unless given."""
        w = self.w
        height = fig.get_figheight()
        top_in = 0.5 + (0.3 if subtitle else 0) + extra_top + (1.15 if tiles else 0)
        foot = [w.source_note(), w.estimate_note(metrics or [self.m]), w.context()] + \
            ([note] if note else [])
        foot = [line for line in foot if line]
        fig.tight_layout(rect=(0, (0.1 + 0.16 * len(foot)) / height, 1, 1 - top_in / height))
        fig.text(0.01, 1 - 0.1 / height, title, fontsize=15, fontweight="bold",
                 color="#1A1A1A", va="top", ha="left")
        if subtitle:
            fig.text(0.01, 1 - 0.45 / height, subtitle, fontsize=10, color="#555555",
                     va="top", ha="left")
        if tiles:
            self.tiles(fig, tiles, top=1 - (0.5 + (0.3 if subtitle else 0) + 0.1) / height,
                       height=0.95 / height)
        fig.text(0.01, 0.08 / height, "\n".join(foot), fontsize=7.5,
                 color="#7F7F7F", va="bottom", ha="left", linespacing=1.4)
        path = self.folder / name
        fig.savefig(path, dpi=200, facecolor="white")
        plt.close(fig)
        self.files.append(path)

    def tiles(self, fig, kpis, top, height):
        """Headline figures in a row of tiles under the subtitle."""
        width, gap = 0.235, 0.012
        for i, (label, value, note) in enumerate(kpis):
            x = 0.01 + i * (width + gap)
            fig.add_artist(plt.Rectangle((x, top - height), width, height,
                                         transform=fig.transFigure, facecolor="#F4F7FB",
                                         edgecolor="none"))
            fig.text(x + 0.01, top - height * 0.2, label.upper(),
                     fontsize=8.5, color="#555555", fontweight="bold", va="center", ha="left")
            fig.text(x + 0.01, top - height * 0.55, value, fontsize=21, color=NAVY,
                     fontweight="bold", va="center", ha="left")
            fig.text(x + 0.01, top - height * 0.86, note, fontsize=8.5, color="#555555",
                     va="center", ha="left")

    def period_axis(self, ax, periods, fontsize=9):
        ax.set_xticks(range(len(periods)))
        labels = [self.w.period(p, short=True) for p in periods]
        rotate = len(periods) > 12
        ax.set_xticklabels(labels, fontsize=fontsize, rotation=90 if rotate else 0)

    # -- 1 ------------------------------------------------------------------------------
    def overview(self):
        a, w, m, s = self.a, self.w, self.m, self.a.summary
        periods = self.shown
        xs = np.arange(len(periods))
        companion = a.metrics[1] if len(a.metrics) > 1 else None
        unit_values = a.unit_values
        bottom = companion is not None or unit_values is not None
        fig = plt.figure(figsize=(14, 9.6 if bottom else 6.2))
        grid = fig.add_gridspec(2 if bottom else 1, 2,
                                height_ratios=[3.0, 2.5] if bottom else [1])

        ax = fig.add_subplot(grid[0, :])
        values = a.period_totals[m.key][periods].tolist()
        nums = numbers_of(values)
        top = np.nanmax(nums) if np.any(nums > 0) else 1.0
        ax.bar(xs, np.nan_to_num(nums), 0.68, color=NAVY)
        labelled = len(periods) <= LABEL_LIMIT
        for i, (period, value) in enumerate(zip(periods, values)):
            if is_gap(value) or not labelled:
                continue
            ax.text(i, number(value) + top * 0.02, w.figure(value, m), ha="center",
                    va="bottom", fontsize=9.5, fontweight="bold")
            index = a.periods.index(period)
            if index:
                change = change_between(value, a.period_totals[m.key][a.periods[index - 1]])
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
                values = a.period_totals[companion.key][periods].tolist()
                nums = numbers_of(values)
                ctop = np.nanmax(nums) if np.any(nums > 0) else 1.0
                ax.bar(xs, np.nan_to_num(nums), 0.68, color=SKY)
                if len(periods) <= LABEL_LIMIT:
                    for i, value in enumerate(values):
                        if not is_gap(value):
                            ax.text(i, number(value) + ctop * 0.03,
                                    w.figure(value, companion),
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
                values = unit_values[periods].tolist()
                nums = numbers_of(values)
                utop = np.nanmax(nums) if np.any(nums > 0) else 1.0
                ax.plot(xs, nums, color=NAVY, linewidth=2, marker="o", markersize=5)
                if len(periods) <= LABEL_LIMIT:
                    for i, value in enumerate(values):
                        if not is_gap(value) and value == value:
                            ax.text(i, number(value) + utop * 0.04, w.unit_price(value),
                                    ha="center", va="bottom", fontsize=8.5)
                mark_gaps(ax, xs, values, utop, w, rotate=True)
                ax.set_ylim(0, utop * 1.3)
                self.period_axis(ax, periods, 8.5)
                volume_metric = next(x for x in a.metrics if x.key == self.q.unit_value[1])
                ax.yaxis.set_major_formatter(FuncFormatter(
                    lambda v, _: w.unit_price(v)))
                ax.set_title(w("panel_unit_value", unit=w.unit_value_unit(volume_metric)))
                y_grid(ax)

        growth_years = a.years
        if is_gap(s["cagr"]):
            growth_note = w("tile_growth_gap", metric=w.metric(m).capitalize())
        elif s["cagr"] != s["cagr"]:
            growth_note = (w("tile_growth_undefined") if len(growth_years) >= 2 else
                           w("tile_growth_short",
                             years="calendar years" if a.monthly else "years"))
        else:
            growth_note = w("tile_growth_note", trend=w.pct(s["trend"], signed=True))
            if len(growth_years) >= 2:
                growth_note += w("tile_years", y0=growth_years[0], y1=growth_years[-1])
        largest = (w.partner(s["top"]) if s["top"] is not None else "")
        hhi_note = (w("tile_hhi_gap", hhi=w.gap(s["hhi"])) if is_gap(s["hhi"]) or
                    s["hhi"] != s["hhi"] else
                    w("tile_hhi", hhi=w.count(s["hhi"]), band=self.band(s["hhi"])))
        kpis = [(w("tile_total", metric=w.metric(m)), w.figure(s["total"], m),
                 f"{m.unit}, {self.span}" if m.unit else self.span),
                (w("tile_growth"), w.pct(s["cagr"], signed=True), growth_note),
                (w("tile_largest", role=w.role()), w.pct(s["top_share"], 0),
                 fmt.short(largest, 32)),
                (w("tile_partners", roles=w.role(True).capitalize()), w.count(s["partners"]),
                 hhi_note)]
        notes = []
        if unit_values is not None:
            volume = next(x for x in a.metrics if x.key == self.q.unit_value[1])
            notes.append(w("note_unit_value", period=w.period_word(), volume=w.metric(volume)))
        if self.cut:
            notes.append(w("note_latest", n=len(periods), periods=w.period_word(True),
                           period=w.period_word()))
        code = "" if self.q.product_code in ("TOTAL", "AG2", "AG4", "AG6") else \
            f"HS {self.q.product_code}, "
        shown = [m, companion] + ([x for x in a.metrics if x.key in self.q.unit_value]
                                  if unit_values is not None else [])
        self.save(fig, "01_overview.png",
                  self.fitted(fig, "overview_title", "product", reporter=w.reporter(),
                              flow=w.flow(), product=w.product_phrase(), span=self.span),
                  w("overview_sub", code=code, desc=self.q.product_desc, roles=w.role(True),
                    measures=w.measures()),
                  " ".join(notes), tiles=kpis, metrics=shown)

    def band(self, value) -> str:
        band = hhi_band(value)
        return {"highly concentrated": self.w("band_high"),
                "moderately concentrated": self.w("band_mid"),
                "unconcentrated": self.w("band_low")}.get(band, "")

    # -- 2 ------------------------------------------------------------------------------
    def partners(self):
        a, w, m = self.a, self.w, self.m
        table = a.partners
        if table.empty:
            return
        ordered_by_other = a.partner_order.key != m.key
        if not ordered_by_other:
            table = table[table[m.heading].map(number) > 0]
        if table.empty:
            return
        focus = self.q.partner_code
        top = table.head(TOP_N)
        rest = table.iloc[TOP_N:]
        if all(is_gap(v) for v in top[m.heading]):
            return      # nothing to draw: every total is missing (the findings say so)
        names, values, labels, colours, gaps = [], [], [], [], []
        for row in top.to_dict("records"):
            names.append(w.partner(row["Code"]))
            value = row[m.heading]
            gaps.append(is_gap(value))
            values.append(0.0 if is_gap(value) else number(value))
            growth = row.get("CAGR", np.nan)
            tail = (w("label_cagr", g=w.pct(growth, signed=True))
                    if not is_gap(growth) and growth == growth else w.status(row["Status"]))
            labels.append(w.gap(value) if is_gap(value) else
                          f"{w.figure(value, m)}  |  {w.pct(row['Share'])}  |  {tail}")
            colours.append(ACCENT if row["Code"] == focus else NAVY)
        if len(rest):
            rest_total = total_of(rest[m.heading])
            names.append(w("partners_other", n=len(rest), roles=w.role(True)))
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
        s = a.summary
        if not is_gap(s["top_share"]) and s["top"] is not None:
            title = w("partners_title", name=w.partner(s["top"]), role=w.role(),
                      share=w.pct(s["top_share"]))
        else:
            title = w("partners_title_plain", roles=w.role(True).capitalize(),
                      metric=w.metric(m))
        focus_text = (w("partners_focus", name=w.partner(focus))
                      if focus is not None and focus in a.partner_names else "")
        notes = []
        if len(a.years) >= 2:
            notes.append(w("partners_note", first=a.years[0], last=a.years[-1]))
        if ordered_by_other:
            notes.append(w("partners_order_note", order=w.metric(a.partner_order),
                           metric=w.metric(m), roles=w.role(True)))
            subtitle = w("partners_sub_order", metric=w.metric_title(m), role=w.role(), span=self.span,
                         n=len(top), order=w.metric(a.partner_order), total=len(a.partners),
                         focus=focus_text)
        else:
            subtitle = w("partners_sub", metric=w.metric_title(m), role=w.role(), span=self.span,
                         n=len(top), total=len(a.partners), focus=focus_text)
        self.save(fig, "02_partners.png", title, subtitle, "\n".join(notes))

    # -- 3 ------------------------------------------------------------------------------
    def by_period(self):
        a, w, m = self.a, self.w, self.m
        matrix = a.partner_matrix[m.key][self.shown]
        if matrix.empty:
            return
        top = matrix.head(12)
        frame = top.copy()
        frame.index = [w.partner(c) for c in top.index]
        if len(matrix) > 12:
            rest = matrix.iloc[12:]
            frame.loc[w("heatmap_other", n=len(rest))] = [total_of(rest[c]) for c in
                                                          matrix.columns]
        fig, ax = plt.subplots(figsize=(4.6 + max(0.72, 1.15 if len(self.shown) <= 12 else 0.72)
                                        * len(frame.columns), 2.4 + 0.52 * len(frame)))
        self.heatmap(ax, frame)
        self.save(fig, "03_partners_by_period.png",
                  w("heatmap_title", period=w.period_word().capitalize(), period2=w.period_word(),
                    role=w.role()),
                  w("heatmap_sub", metric=w.metric_title(m), roles=w.role(True), span=self.span,
                    order=w.metric(a.partner_order) if a.partner_order.key != m.key
                    else w("total").lower()),
                  w("heatmap_note") + (" " + w("note_latest", n=len(self.shown),
                                                periods=w.period_word(True),
                                                period=w.period_word()) if self.cut else ""),
                  extra_top=0.3)

    def heatmap(self, ax, frame: pd.DataFrame, column_labels=None, totals=True):
        """Cells in the metric's own unit, which the chart's subtitle states."""
        w = self.w
        cells = frame.to_numpy()
        values = np.array([[np.nan if is_gap(v) else number(v) for v in row]
                           for row in cells], dtype=float)
        shown = np.ma.masked_where(~(values > 0), values)
        palette = matplotlib.colormaps["Blues"].copy()
        palette.set_bad("#F4F6F7")
        vmax = np.nanmax(values) if np.any(values > 0) else 1
        ax.imshow(shown, cmap=palette, aspect="auto", vmin=0, vmax=vmax)
        small = values.shape[1] > 14
        for i in range(values.shape[0]):
            for j in range(values.shape[1]):
                if is_gap(cells[i, j]):
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor="#FBEEE6",
                                               edgecolor="white", hatch="///", linewidth=0))
                    ax.text(j, i, w.gap(cells[i, j]), ha="center", va="center",
                            fontsize=7, color=GAP_GREY, style="italic")
                elif values[i, j] > 0:
                    v = values[i, j]
                    ax.text(j, i, w.figure(v, self.m), ha="center", va="center",
                            fontsize=7.5 if small else 9,
                            color="white" if v > vmax * 0.55 else "#1A1A1A")
            if totals:
                ax.text(values.shape[1] - 0.35, i, w.figure(total_of(cells[i]), self.m),
                        ha="left", va="center", fontsize=9.5, fontweight="bold")
        if totals:
            ax.text(values.shape[1] - 0.35, -0.85, w("total"), ha="left",
                    va="center", fontsize=10, fontweight="bold")
        ax.set_xticks(range(values.shape[1]))
        labels = column_labels or [w.period(c, short=True) for c in frame.columns]
        ax.set_xticklabels(labels, fontsize=8.5 if small else 10,
                           rotation=90 if small else 0)
        ax.xaxis.tick_top()
        ax.set_yticks(range(values.shape[0]))
        ax.set_yticklabels([fmt.short(i, 26) for i in frame.index], fontsize=10)
        ax.set_xticks(np.arange(-0.5, values.shape[1], 1), minor=True)
        ax.set_yticks(np.arange(-0.5, values.shape[0], 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.tick_params(length=0)
        ax.tick_params(which="minor", length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xlim(-0.5, values.shape[1] + (1.3 if totals else -0.5))

    # -- 4 ------------------------------------------------------------------------------
    def shares(self):
        a, w, m = self.a, self.w, self.m
        shares = a.partner_shares[self.shown]
        if shares.empty:
            return
        lead_codes = [c for c in a.partner_matrix[m.key].index[:5]]
        frame = shares.loc[lead_codes]
        others = [total_of(shares.loc[[c for c in shares.index if c not in lead_codes], p])
                  for p in shares.columns]
        xs = np.arange(len(self.shown))
        fig, ax = plt.subplots(figsize=(13.5, 6.4))
        bottom = np.zeros(len(xs))
        gap_columns = [any(is_gap(v) for v in shares[p]) for p in shares.columns]
        series = [(w.partner(c), frame.loc[c].tolist(), SERIES[i]) for i, c in
                  enumerate(lead_codes)] + [(w("all_others"), others, LIGHT_GREY)]
        labelled = len(xs) <= LABEL_LIMIT
        for name, values, colour in series:
            nums = np.array([0 if is_gap(v) or v != v else number(v) for v in values])
            ax.bar(xs, nums, 0.7, bottom=bottom, color=colour, label=fmt.short(name, 24),
                   edgecolor="white", linewidth=0.8)
            if labelled:
                for x, v, b in zip(xs, nums, bottom):
                    if v >= 0.06:
                        ax.text(x, b + v / 2, f"{v:.0%}", ha="center", va="center",
                                fontsize=8.5, fontweight="bold",
                                color="#1A1A1A" if colour in (LIGHT_GREY, SKY) else "white")
            bottom += nums
        for x, gap in zip(xs, gap_columns):
            if gap:
                ax.text(x, 0.02, w.gap(MISSING), ha="center", va="bottom", fontsize=8,
                        color=GAP_GREY, rotation=90, style="italic")
        ax.set_ylim(0, 1)
        self.period_axis(ax, self.shown)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9.5)
        y_grid(ax)
        lead = lead_codes[0] if lead_codes else None
        first, last = (shares.loc[lead].iloc[0], shares.loc[lead].iloc[-1]) if lead is not None \
            else (MISSING, MISSING)
        if lead is not None and not (is_gap(first) or is_gap(last)) and first == first \
                and last == last:
            title = w("shares_title", name=w.partner(lead), first=w.pct(first, 0),
                      last=w.pct(last, 0), p0=w.period(self.shown[0]),
                      p1=w.period(self.shown[-1]))
        else:
            title = w("shares_title_plain", role=w.role(), period=w.period_word())
        self.save(fig, "04_shares.png", title,
                  w("shares_sub", metric=w.metric(m), role=w.role()),
                  w("note_latest", n=len(self.shown), periods=w.period_word(True),
                    period=w.period_word()) if self.cut else "")

    # -- 5 ------------------------------------------------------------------------------
    def growth(self):
        a, w, m = self.a, self.w, self.m
        if len(a.years) < 2 or "CAGR" not in a.partners:
            return
        y0, y1 = a.years[0], a.years[-1]
        top = a.partners.head(TOP_N)        # largest by the listing metric, see Analysis
        rated = top[[not is_gap(v) and v == v for v in top["CAGR"]]].copy()
        if rated.empty:
            return
        rated["_g"] = rated["CAGR"].map(number)
        rated = rated.sort_values("_g")
        unrated = top[~top.index.isin(rated.index)]
        change = top[[not is_gap(v) and v == v for v in top["Share change (pp)"]]].copy()
        change["_c"] = change["Share change (pp)"].map(number)
        change = change.sort_values("_c")
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 2.6 + 0.55 * max(len(top), 3)))
        for ax, frame, col, labeller, title in (
                (a1, rated, "_g", lambda v: w.pct(v, 1, signed=True),
                 w("growth_cagr", metric=w.metric(m), y0=y0, y1=y1)),
                (a2, change, "_c", lambda v: w.points(v),
                 w("growth_share", y0=y0, y1=y1))):
            ys = np.arange(len(frame))
            vals = frame[col].to_numpy(float) if len(frame) else np.array([])
            ax.barh(ys, vals, 0.6, color=[NAVY if v >= 0 else ACCENT for v in vals])
            span = max(np.abs(vals).max() if len(vals) else 0, 0.01 if col == "_g" else 0.1)
            for i, v in enumerate(vals):
                ax.text(v + span * 0.03 * (1 if v >= 0 else -1), i, labeller(v),
                        va="center", ha="left" if v >= 0 else "right", fontsize=9)
            ax.axvline(0, color="#555555", linewidth=1)
            ax.set_yticks(ys)
            ax.set_yticklabels([fmt.short(w.partner(c), 24) for c in frame["Code"]],
                               fontsize=10)
            ax.set_xlim(-span * 1.45, span * 1.45)
            if col == "_g":
                ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt.pct(v, 0)))
            ax.set_title(title)
            x_grid(ax)
        leaders = rated_growth(a)       # headline only among partners with a material base
        if len(leaders):
            fast = leaders.iloc[-1]
            title = w("growth_title", name=w.partner(fast["Code"]), n=TOP_N,
                      g=w.pct(fast["_g"], 1, signed=True))
        else:
            title = w("growth_title_plain", n=TOP_N, roles=w.role(True))
        note = ""
        if len(unrated):
            note = w("growth_none", names=", ".join(w.partner(c) for c in unrated["Code"]),
                     reason=w("growth_none_reason", y0=y0, y1=y1, metric=w.metric(m)))
        self.save(fig, "05_growth.png", title,
                  w("growth_sub", n=TOP_N, roles=w.role(True), span=self.span,
                    metric=w.metric(a.partner_order)), note)

    # -- 6 ------------------------------------------------------------------------------
    def concentration(self):
        a, w = self.a, self.w
        stats = a.period_stats.loc[self.shown]
        xs = np.arange(len(self.shown))
        hhis = numbers_of(stats["HHI"])
        if not np.any(hhis > 0):
            return
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.8))
        top = max(np.nanmax(hhis) * 1.15, 3000)
        a1.axhspan(0, 1500, color="#F2F8F3", zorder=0)
        a1.axhspan(1500, 2500, color="#FEF9E7", zorder=0)
        a1.axhspan(2500, top, color="#FDF2E9", zorder=0)
        for floor, key in ((0, "band_low"), (1500, "band_mid"), (2500, "band_high")):
            a1.text(len(xs) - 0.55, floor + top * 0.015, w(key), fontsize=8,
                    color="#7F7F7F", ha="right", va="bottom")
        a1.plot(xs, hhis, color=NAVY, linewidth=2.2, marker="o", markersize=5)
        if len(xs) <= LABEL_LIMIT:
            for x, v in zip(xs, hhis):
                if v == v:
                    a1.text(x, v + top * 0.035, f"{v:,.0f}", ha="center", fontsize=8.5,
                            bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                      edgecolor="none", alpha=0.85))
        mark_gaps(a1, xs, stats["HHI"].tolist(), top, w, rotate=True)
        a1.set_ylim(0, top)
        a1.set_xlim(-0.5, len(xs) - 0.5)
        self.period_axis(a1, self.shown, 8.5)
        a1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        a1.set_title(w("conc_hhi", period=w.period_word()))
        y_grid(a1)
        for column, colour, label in (("Largest share", ACCENT, w("conc_largest", role=w.role())),
                                      ("Top 3 share", NAVY, w("conc_top3", roles=w.role(True)))):
            vals = numbers_of(stats[column])
            a2.plot(xs, vals, color=colour, linewidth=2.2, marker="o", markersize=5,
                    label=label)
            finite = [(x, v) for x, v in zip(xs, vals) if v == v]
            if finite:
                a2.text(finite[-1][0] + 0.2, finite[-1][1], w.pct(finite[-1][1], 0),
                        color=colour, va="center", fontsize=9.5, fontweight="bold")
        mark_gaps(a2, xs, stats["Top 3 share"].tolist(), 1.0, w, rotate=True)
        a2.set_ylim(0, 1.05)
        self.period_axis(a2, self.shown, 8.5)
        a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
        a2.legend(loc="lower left")
        a2.set_title(w("conc_shares"))
        y_grid(a2)
        finite = [(p, v) for p, v in zip(self.shown, hhis) if v == v]
        if len(finite) >= 2 and finite[0][0] == self.shown[0] and finite[-1][0] == self.shown[-1]:
            (p0, h0), (p1, h1) = finite[0], finite[-1]
            title = w("conc_title_rise" if h1 > h0 else "conc_title_fall", h0=f"{h0:,.0f}",
                      h1=f"{h1:,.0f}", p0=w.period(p0), p1=w.period(p1))
        else:
            title = w("conc_title_plain")
        self.save(fig, "06_concentration.png", title, w("conc_sub", roles=w.role(True)),
                  w("conc_note"))

    # -- 7 ------------------------------------------------------------------------------
    def products(self):
        a, w, m = self.a, self.w, self.m
        matrix = a.product_matrix[m.key][self.shown]
        if len(matrix) < 2:
            return
        top = matrix.head(6)
        rows = [(f"{c} {a.product_names.get(c, '')}", top.loc[c].tolist(), SERIES[i])
                for i, c in enumerate(top.index)]
        if len(matrix) > 6:
            rest = matrix.iloc[6:]
            rows.append((w("other_products"), [total_of(rest[p]) for p in matrix.columns],
                         LIGHT_GREY))
        xs = np.arange(len(self.shown))
        fig, ax = plt.subplots(figsize=(13.5, 6.2))
        bottom = np.zeros(len(xs))
        for name, values, colour in rows:
            nums = np.array([0 if is_gap(v) else number(v) for v in values])
            ax.bar(xs, nums, 0.7, bottom=bottom, color=colour, edgecolor="white", linewidth=0.8,
                   label=textwrap.fill(fmt.short(name, 80), 44))
            bottom += nums
        gap_columns = [any(is_gap(v) for v in matrix[p]) for p in matrix.columns]
        top_value = bottom.max() if bottom.max() > 0 else 1
        for x, gap in zip(xs, gap_columns):
            if gap:
                ax.text(x, top_value * 0.02, w.gap(MISSING), ha="center", va="bottom",
                        fontsize=8, color=GAP_GREY, rotation=90, style="italic")
        axis_amount(ax.yaxis, top_value)
        self.period_axis(ax, self.shown)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9)
        y_grid(ax)
        lead = a.products.iloc[0]
        if not is_gap(lead["Share"]) and lead["Share"] == lead["Share"]:
            name = str(lead["Name"]).split(": ", 1)[-1]
            title = self.fitted(fig, "products_title", "name", name=name[:1].upper() + name[1:],
                                code=lead["Code"], share=w.pct(lead["Share"], 0),
                                metric=w.metric(m))
        else:
            title = w("products_title_plain", metric=w.metric_title(m))
        self.save(fig, "07_products.png", title,
                  w("products_sub", metric=w.metric_title(m), level=self.q.product_level,
                    period=w.period_word(), n=len(a.products)),
                  w("note_latest", n=len(self.shown), periods=w.period_word(True),
                    period=w.period_word()) if self.cut else "")

    # -- 8 ------------------------------------------------------------------------------
    def focus(self):
        a, w, m = self.a, self.w, self.m
        f = a.focus
        if f is None:
            return
        f = f.set_index("Period").loc[self.shown]
        code = self.q.partner_code
        name = w.partner(code)
        mine_col = f"{a.partner_names[code]}: {m.heading}"
        all_col = f"All {self.q.roles}: {m.heading}"
        xs = np.arange(len(self.shown))
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 6.2),
                                     gridspec_kw={"width_ratios": [1.6, 1]})
        mine = numbers_of(f[mine_col])
        world = numbers_of(f[all_col])
        rest = world - mine
        a1.bar(xs, np.nan_to_num(mine), 0.7, color=ACCENT, label=name)
        a1.bar(xs, np.nan_to_num(rest), 0.7, bottom=np.nan_to_num(mine), color=LIGHT_GREY,
               label=w("focus_others", roles=w.role(True)))
        top = np.nanmax(world) if np.any(world > 0) else 1
        if len(xs) <= LABEL_LIMIT:
            for x, total, share, rank in zip(xs, world, f["Share"], f["Rank"]):
                if total == total and not is_gap(share):
                    rank = number(rank)
                    label = w.pct(share, 0) + (f"\n{w('rank', n=int(rank))}"
                                               if rank == rank else "")
                    a1.text(x, total + top * 0.02, label, ha="center", va="bottom",
                            fontsize=8.5)
        mark_gaps(a1, xs, f[all_col].tolist(), top, w, rotate=True)
        a1.set_ylim(0, top * 1.22)
        self.period_axis(a1, self.shown, 8.5)
        axis_amount(a1.yaxis, top)
        a1.legend(loc="upper left", ncol=2)
        a1.set_title(w("focus_main", metric=w.metric_title(m), period=w.period_word()))
        y_grid(a1)
        width = 0.38
        g_mine = numbers_of(f[f"{a.partner_names[code]}: growth"])[1:]
        g_all = numbers_of(f[f"All {self.q.roles}: growth"])[1:]
        x2 = np.arange(len(g_mine))
        a2.bar(x2 - width / 2, np.nan_to_num(g_mine), width, color=ACCENT,
               label=fmt.short(name, 22))
        a2.bar(x2 + width / 2, np.nan_to_num(g_all), width, color=GREY,
               label=w("focus_all", roles=w.role(True)))
        a2.axhline(0, color="#555555", linewidth=1)
        self.period_axis(a2, self.shown[1:], 8.5)
        a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt.pct(v, 0)))
        a2.legend(loc="upper right", fontsize=8.5)
        a2.set_title(w("focus_growth", period=w.period_word()))
        y_grid(a2)
        first, last = f["Share"].iloc[0], f["Share"].iloc[-1]
        self.save(fig, "08_partner_focus.png",
                  w("focus_title", name=name, first=w.pct(first, 0), last=w.pct(last, 0),
                    reporter=w.reporter(), flow=w.flow(), p0=w.period(self.shown[0]),
                    p1=w.period(self.shown[-1])),
                  w("focus_sub", name=name, roles=w.role(True), metric=w.metric(m),
                    period=w.period_word()))

    # -- 9 ------------------------------------------------------------------------------
    def seasonality(self):
        a, w, m = self.a, self.w, self.m
        if not a.monthly:
            return
        years = sorted({p // 100 for p in a.periods})
        if len(years) < 2:
            return
        totals = a.period_totals[m.key]
        frame = pd.DataFrame(index=[str(y) for y in years], columns=range(1, 13), dtype=object)
        for p in a.periods:
            frame.loc[str(p // 100), p % 100] = totals[p]
        frame = frame.where(frame.notna(), 0.0)
        fig, ax = plt.subplots(figsize=(15, 2.6 + 0.6 * len(years)))
        self.heatmap(ax, frame, column_labels=[w.month(i) for i in range(1, 13)])
        self.save(fig, "09_seasonality.png",
                  w("season_title", y0=years[0], y1=years[-1]),
                  w("season_sub", metric=w.metric_title(m)),
                  w("season_note"), extra_top=0.3)

    def make_all(self) -> list[Path]:
        steps = [self.overview, self.partners, self.by_period, self.shares, self.growth,
                 self.concentration, self.products, self.focus, self.seasonality]
        for step in steps:
            try:
                step()
            except Exception as err:          # one chart failing must not stop the others
                plt.close("all")
                print(f"  ⚠ Chart '{step.__name__}' could not be drawn: {err}")
        return self.files
