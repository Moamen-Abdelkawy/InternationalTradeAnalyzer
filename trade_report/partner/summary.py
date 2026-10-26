"""summary.md of a partner report: the key findings and main tables in plain Markdown."""
from __future__ import annotations

from pathlib import Path

from .. import fmt
from ..analysis import TOP_N, total_of
from ..model import period_label
from ..summary import cell, kind_of, table
from .analysis import PartnerAnalysis
from .findings import Terms, findings, known


def key_figures(pa: PartnerAnalysis) -> list[tuple[str, str]]:
    """The headline figures of a partner report, as (measure, figure) text."""
    q, a, s, m, t = pa.q, pa.a, pa.summary, pa.metric, Terms(pa)
    figures = [(f"Total {m.label.lower()} {t.to} {t.partner}", fmt.amount(s["total"], m))]
    if len(pa.years) >= 2:
        figures += [(f"CAGR {pa.years[0]}–{pa.years[-1]}", fmt.pct(s["cagr"], signed=True)),
                    (f"CAGR {pa.years[0]}–{pa.years[-1]}, all {q.roles}",
                     fmt.pct(a.summary["cagr"], signed=True)),
                    ("Trend growth", fmt.pct(s["trend"], signed=True))]
        if "real_cagr" in s:
            figures.append((f"CAGR in constant {a.real_base} USD",
                            fmt.pct(s["real_cagr"], signed=True)))
    for metric in pa.metrics[1:]:
        figures.append((f"Total {metric.label.lower()}", fmt.amount(s["totals"][metric.key],
                                                                      metric)))
    if "unit_value" in s:
        volume = next(x for x in pa.metrics if x.key == q.unit_value[1])
        unit = f"USD/{volume.unit or 'unit'}"
        figures.append((f"Unit value ({unit}), {t.partner}", cell(s["unit_value"], "unit_value")))
        figures.append((f"Unit value ({unit}), all {q.roles}",
                        cell(a.summary.get("unit_value"), "unit_value")))
    figures.append((f"Share of {t.reporter}'s {t.flow}", fmt.pct(s["share"])))
    figures.append((f"Rank among {s['partners']} {q.roles}",
                    f"#{s['rank']}" if known(s["rank"]) else fmt.gap_text(s["share"]) or "n/a"))
    figures.append((f"{t.reporter}'s {t.flow}, all {q.roles}", fmt.amount(a.summary["total"], m)))
    side = ([r for r in pa.side_position.to_dict("records") if known(r["Share"])]
            if pa.side_position is not None else [])
    if side:
        figures.append((f"{t.reporter}'s share of {t.partner}'s {t.side_flow}, "
                        f"{period_label(side[-1]['Period'], q.monthly)}",
                        fmt.pct(side[-1]["Share"])))
    if pa.balance is not None:
        value = next(x for x in pa.metrics if x.key == "value")
        balance = total_of(pa.balance)
        figures.append((f"Balance of trade with {t.partner} (exports − imports)",
                        fmt.amount(balance, value)))
    return figures


def period_rows(pa: PartnerAnalysis) -> tuple[list[str], list[list[str]], list[bool]]:
    """The by-period table: headers, rows and which columns are numbers."""
    q, a, m, t = pa.q, pa.a, pa.metric, Terms(pa)
    headers = ["Month" if q.monthly else "Year", m.heading, "Growth"]
    headers += [x.heading for x in pa.metrics[1:]]
    if pa.unit_values is not None:
        volume = next(x for x in pa.metrics if x.key == q.unit_value[1])
        headers += [f"Unit value (USD/{volume.unit or 'unit'})", f"Unit value, all {q.roles}"]
    headers += [f"Share of {t.reporter}'s {t.flow}", "Rank"]
    rows = []
    for record in pa.position.to_dict("records"):
        p = record["Period"]
        row = [period_label(p, q.monthly, short=True), cell(record["Figure"], kind_of(m), m),
               cell(record["Growth"], "growth")]
        row += [cell(pa.series[x.key][p], kind_of(x), x) for x in pa.metrics[1:]]
        if pa.unit_values is not None:
            row += [cell(pa.unit_values[p], "unit_value"), cell(a.unit_values[p], "unit_value")]
        row += [cell(record["Share"], "share"), cell(record["Rank"], "text")]
        rows.append(row)
    return headers, rows, [False] + [True] * (len(headers) - 1)


def competitor_rows(pa: PartnerAnalysis, mark=True) -> tuple[list[str], list[list[str]]]:
    """The reporter's largest partners over the whole query; the partner's name in bold
    (Markdown) when mark is set."""
    m = pa.metric
    rows = []
    for r in pa.competitors.head(TOP_N + 1).to_dict("records"):
        name = str(r["Name"])
        rows.append([str(r["Rank"]), f"**{name}**" if mark and r["Code"] == pa.code else name,
                     cell(r[m.heading], kind_of(m), m), cell(r["Share"], "share"),
                     cell(r.get("CAGR", float("nan")), "growth"), str(r["Status"])])
    return ["Rank", pa.q.role.capitalize(), m.heading, "Share", "CAGR", "Status"], rows


def side_rows(pa: PartnerAnalysis) -> tuple[list[str], list[list[str]]] | None:
    if pa.side_position is None:
        return None
    t, m = Terms(pa), pa.side.metric
    headers = ["Month" if pa.q.monthly else "Year", f"{t.partner}'s {t.side_flow}, all "
               f"{t.side_roles}", f"{t.other_to.capitalize()} {t.reporter}",
               f"{t.reporter}'s share", f"{t.reporter}'s rank"]
    rows = [[period_label(r["Period"], pa.q.monthly, short=True),
             cell(r["Total"], kind_of(m), m), cell(r["Figure"], kind_of(m), m),
             cell(r["Share"], "share"), cell(r["Rank"], "text")]
            for r in pa.side_position.to_dict("records")]
    return headers, rows


def mirror_rows(pa: PartnerAnalysis) -> tuple[list[str], list[list[str]]] | None:
    if not pa.mirror or "value" not in pa.mirror:
        return None
    t = Terms(pa)
    value = next(x for x in pa.metrics if x.key == "value")
    headers = ["Month" if pa.q.monthly else "Year", f"As {t.reporter} reports it",
               f"As {t.partner} reports it", "Difference", "Ratio"]
    rows = [[period_label(r["Period"], pa.q.monthly, short=True),
             cell(r["Reporter"], "money", value), cell(r["Partner"], "money", value),
             cell(r["Difference"], "money", value),
             cell(r["Ratio"], "unit_value")] for r in pa.mirror["value"].to_dict("records")]
    return headers, rows


def write_summary(pa: PartnerAnalysis, path: Path, files: dict[str, str]) -> Path:
    q, t = pa.q, Terms(pa)
    lines = [f"# {t.reporter} · {q.flow} {t.to} {t.partner} · {q.product_label} · {q.span}", "",
             f"*{q.source_note}*", "", "## Key findings", ""]
    lines += [f"- {sentence}" for sentence in findings(pa)]
    lines += ["", "## Key figures", "",
              table(["Measure", "Figure"], [list(f) for f in key_figures(pa)], [False, True])]
    headers, rows, numeric = period_rows(pa)
    lines += ["", f"## The trade with {t.partner} by {pa.period_word}", "",
              table(headers, rows, numeric)]
    if not pa.competitors.empty:
        headers, rows = competitor_rows(pa)
        lines += ["", f"## {t.reporter}'s largest {q.roles}", "",
                  table(headers, rows, [True, False, True, True, True, False])]
    side = side_rows(pa)
    if side:
        headers, rows = side
        lines += ["", f"## {t.reporter} in {t.partner}'s {t.side_flow} ({t.reported_as})", "",
                  table(headers, rows, [False, True, True, True, True])]
    mirror = mirror_rows(pa)
    if mirror:
        headers, rows = mirror
        lines += ["", "## The two countries' figures for the same trade (value)", "",
                  table(headers, rows, [False, True, True, True, True])]
    lines += ["", "## Files", ""] + [f"- {label}: `{name}`" for label, name in files.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
