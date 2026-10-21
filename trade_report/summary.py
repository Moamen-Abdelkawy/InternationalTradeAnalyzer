"""summary.md: the key findings and main tables of a report in plain Markdown."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import fmt
from .analysis import TOP_N, Analysis, growth, hhi_band, is_gap
from .findings import findings
from .model import Metric, period_label


def cell(value, kind: str, metric: Metric | None = None) -> str:
    """A table cell; amounts are bare figures, their unit is in the column heading."""
    if kind in ("money", "volume"):
        return fmt.figure(value, metric)
    if kind == "growth":
        return fmt.pct(value, 1, signed=True)
    if kind == "share":
        return fmt.pct(value)
    if kind == "count":
        return fmt.count(value)
    if kind == "unit_value":
        return fmt.gap_text(value) or f"{value:,.2f}"
    if is_gap(value):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return str(value)


def table(headers: list[str], rows: list[list[str]], numeric: list[bool]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---:" if n else ":---" for n in numeric) + "|"]
    out += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(out)


def kind_of(metric: Metric) -> str:
    return "money" if metric.kind == "money" else "volume"


def write_summary(a: Analysis, path: Path, files: dict[str, str]) -> Path:
    q, s, m = a.q, a.summary, a.metric
    lines = [f"# {q.reporter_name} · {q.flow} · {q.product_label} · {q.span}", "",
             f"*{q.source_note}*", "", "## Key findings", ""]
    lines += [f"- {sentence}" for sentence in findings(a)]

    figures = [(f"Total {m.label.lower()}", fmt.amount(s["total"], m))]
    if len(a.years) >= 2:
        figures.append((f"CAGR {a.years[0]}–{a.years[-1]}", fmt.pct(s["cagr"], signed=True)))
        figures.append(("Trend growth", fmt.pct(s["trend"], signed=True)))
        if "real_cagr" in s:
            figures.append((f"CAGR, constant {a.real_base} USD",
                            fmt.pct(s["real_cagr"], signed=True)))
    for metric in a.metrics[1:]:
        figures.append((f"Total {metric.label.lower()}",
                        fmt.amount(s["totals"][metric.key], metric)))
    figures += [(q.roles.capitalize(), str(s["partners"])),
                (f"Largest {q.role}",
                 (a.partner_names.get(s["top"], "") + f" ({fmt.pct(s['top_share'])})")
                 if s["top"] is not None else fmt.gap_text(s["top_share"]) or "n/a"),
                ("HHI", f"{fmt.count(s['hhi'])} {hhi_band(s['hhi'])}".strip())]
    lines += ["", "## Key figures", "",
              table(["Measure", "Figure"], [[k, v] for k, v in figures], [False, True])]

    headers = ["Year" if not q.monthly else "Month", m.heading, "Growth"]
    numeric = [False, True, True]
    for metric in a.metrics[1:]:
        headers.append(metric.heading)
        numeric.append(True)
    estimated = [x for x in a.metrics if x.key in a.estimated]
    for metric in estimated:
        headers.append(f"{metric.label}: estimated by {q.estimated_by}")
        numeric.append(True)
    if a.unit_values is not None:
        volume = next(x for x in a.metrics if x.key == q.unit_value[1])
        headers.append(f"Unit value (USD/{volume.unit or 'unit'})")
        numeric.append(True)
    headers += [q.roles.capitalize(), "Largest share", "HHI"]
    numeric += [True, True, True]
    rows = []
    totals = a.period_totals[m.key]
    for i, period in enumerate(a.periods):
        before = a.periods[i - 1] if i else None
        row = [period_label(period, q.monthly, short=True), cell(totals[period], kind_of(m), m),
               fmt.pct(growth(totals[period], totals[before]), 1, signed=True) if before
               else "n/a"]
        for metric in a.metrics[1:]:
            row.append(cell(a.period_totals[metric.key][period], kind_of(metric), metric))
        for metric in estimated:
            row.append(cell(a.estimated[metric.key].by_period[period], "share"))
        if a.unit_values is not None:
            row.append(cell(a.unit_values[period], "unit_value"))
        stats = a.period_stats.loc[period]
        row += [cell(stats["Partners"], "count"), cell(stats["Largest share"], "share"),
                cell(stats["HHI"], "count")]
        rows.append(row)
    lines += ["", f"## Totals by {a.period_word}", "", table(headers, rows, numeric)]

    top = a.partners.head(TOP_N)
    headers = ["Rank", q.role.capitalize(), m.heading, "Share", "CAGR", "Status"]
    rows = [[str(r["Rank"]), str(r["Name"]), cell(r[m.heading], kind_of(m), m),
             cell(r["Share"], "share"), cell(r.get("CAGR", float("nan")), "growth"),
             str(r["Status"])] for r in top.to_dict("records")]
    lines += ["", f"## Top {len(top)} {q.roles}", "",
              table(headers, rows, [True, False, True, True, True, False])]

    lines += ["", "## Files", ""] + [f"- {label}: `{name}`" for label, name in files.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
