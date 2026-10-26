"""The key findings of a report, written as plain sentences."""
from __future__ import annotations

from .analysis import TOP_N, Analysis, hhi_band, is_gap, number
from .fmt import amount, lower_first, pct
from .model import period_label


def findings(a: Analysis) -> list[str]:
    q, s, m = a.q, a.summary, a.metric
    flow = q.flow.lower()
    span = q.span
    product = (lower_first(q.product_desc) if q.product_code not in ("TOTAL", "AG2", "AG4", "AG6")
               else "all products")
    code = f" (HS {q.product_code})" if q.product_code not in ("TOTAL", "AG2", "AG4", "AG6") else ""
    out = []

    if is_gap(s["total"]):
        out.append(f"{q.reporter_name}'s {flow} of {product}{code} over {span} involved "
                   f"{_count(s['partners'], q.role)}. The total {m.label.lower()} cannot be "
                   f"stated: {q.source} does not report it for part of the data (see Data gaps).")
    else:
        name = q.unit_names.get(m.unit)            # 'u' -> 'number of items', for a quantity
        out.append(f"{q.reporter_name}'s {flow} of {product}{code} totalled "
                   f"{amount(s['total'], m)}" + (f" ({name.lower()})" if name else "")
                   + f" over {span}, with {_count(s['partners'], q.role)}.")

    out.append(_growth_sentence(a))

    if is_gap(s["top_share"]):
        out.append(f"Shares by {q.role} over the whole period cannot be computed: "
                   f"{m.label.lower()} is missing for part of the data.")
    elif s["top"] is not None:
        out.append(f"{a.partner_names[s['top']]} was the largest {q.role} with "
                   f"{pct(s['top_share'])} of the total; the three largest held "
                   f"{pct(s['top3_share'])} (HHI {number(s['hhi']):,.0f}, "
                   f"{hhi_band(s['hhi'])}).")

    rated = rated_growth(a)
    if len(rated) >= 2:
        fast, slow = rated.iloc[-1], rated.iloc[0]
        slow_text = "shrank fastest" if slow["_g"] < 0 else "grew slowest"
        out.append(f"Among the top {TOP_N} {q.roles} with at least {pct(MATERIAL, 0)} of the "
                   f"{a.years[0]} total, {fast['Name']} grew fastest "
                   f"({pct(fast['_g'], signed=True)} a year) and {slow['Name']} {slow_text} "
                   f"({pct(slow['_g'], signed=True)} a year).")

    first_l = period_label(q.periods[0], q.monthly)
    last_l = period_label(q.periods[-1], q.monthly)
    new = a.partners[a.partners["Status"].str.startswith("New")]
    lost = a.partners[a.partners["Status"].str.startswith("Lost")]
    if len(new) or len(lost):
        out.append(f"{_count(len(new), q.role)} traded in {last_l} but not in {first_l}"
                   + (f" (largest: {new.iloc[0]['Name']})" if len(new) else "")
                   + f"; {len(lost)} traded in {first_l} but not in {last_l}"
                   + (f" (largest: {lost.iloc[0]['Name']})" if len(lost) else "") + ".")

    if a.partner_order.key != m.key:
        out.append(f"{q.roles.capitalize()} are listed by {a.partner_order.label.lower()}, not "
                   f"ranked: {m.label.lower()} is missing for some of them, so their order by "
                   f"{m.label.lower()} cannot be known.")

    out += gap_sentences(a)
    out += estimate_sentences(a)
    out += edition_sentences(a)
    return out


MATERIAL = 0.01     # growth leaders need this share of the first year; tiny bases grow wildly


def rated_growth(a: Analysis):
    """Top partners with a defined CAGR and a material first-year share, slowest first."""
    if "CAGR" not in a.partners or len(a.years) < 2:
        return a.partners.iloc[0:0]
    top = a.partners.head(TOP_N)
    share_first = f"Share {a.years[0]}"
    keep = [not is_gap(g) and g == g and not is_gap(s) and number(s) >= MATERIAL
            for g, s in zip(top["CAGR"], top[share_first])]
    rated = top[keep].assign(_g=lambda f: f["CAGR"].map(number))
    return rated.sort_values("_g")


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _growth_sentence(a: Analysis) -> str:
    q, s, m = a.q, a.summary, a.metric
    if len(a.years) < 2:
        if q.monthly:
            return ("Growth over the period needs two complete calendar years in the query; "
                    "month-on-month and same-month changes are in the Monthly sheet.")
        return "Growth over the period needs at least two years."
    y0, y1 = a.years[0], a.years[-1]
    if is_gap(s["cagr"]):
        annual = a.annual_totals[m.key]
        ends = " and ".join(str(y) for y in (y0, y1) if is_gap(annual[y]))
        return (f"Growth from {y0} to {y1} cannot be stated: {m.label.lower()} is missing for "
                f"{ends}.")
    if s["cagr"] != s["cagr"]:
        return (f"There is no CAGR from {y0} to {y1}: one of the two years has no trade.")
    text = (f"{m.label} moved from {amount(s['first'], m)} in {y0} to {amount(s['last'], m)} in "
            f"{y1}, a compound annual growth rate of {pct(s['cagr'], signed=True)}")
    if not is_gap(s["trend"]) and s["trend"] == s["trend"]:
        text += f"; the trend fitted to every year is {pct(s['trend'], signed=True)} a year"
    peak_period, peak_value = s["peak"]
    if peak_period is not None:
        text += f". The peak was {period_label(peak_period, q.monthly)} ({amount(peak_value, m)})"
    if "real_cagr" in s and not is_gap(s["real_cagr"]) and s["real_cagr"] == s["real_cagr"]:
        text += (f". In constant {a.real_base} dollars the CAGR is "
                 f"{pct(s['real_cagr'], signed=True)}")
    return text + "."


def _periods(periods, monthly: bool) -> str:
    labels = ", ".join(period_label(p, monthly) for p in periods[:12])
    return labels + (f" and {len(periods) - 12} more" if len(periods) > 12 else "")


def gap_detail(a: Analysis, metric, levels) -> str:
    """Where the source lacks a metric: '120 of 1,500 rows (2019, 2023)', or for COMTRADE
    'the total for 2523 (partner World) in 2020; 1 of the 16 records for 2523 by supplier
    (2020); …'. Totals that are the partners added up instead are left out."""
    q = a.q
    what = q.product_code if q.product_code not in ("TOTAL", "AG2", "AG4", "AG6") else \
        "all products"
    products = q.product_level.split(",")[0] + "s"
    parts = []
    for level, lacking, records, periods in levels:
        when = _periods(periods, q.monthly)
        if level == "rows":
            parts.append(f"{lacking:,} of {records:,} rows ({when})")
        elif level == "total":
            missing = [p for p in periods if p not in a.added_up.get(metric.key, [])]
            if missing:
                parts.append(f"the total for {what} (partner World) in "
                             f"{_periods(missing, q.monthly)}")
        elif level == "partners":
            parts.append(f"{lacking:,} of the {records:,} records for {what} by {q.role} "
                         f"({when})")
        elif level == "products":
            parts.append(f"{lacking:,} of the {records:,} records of its {products} by "
                         f"{q.role} ({when})")
        else:
            parts.append(f"{lacking:,} of the {records:,} totals of its {products} "
                         f"(partner World; {when})")
    return "; ".join(parts)


def gap_sentences(a: Analysis) -> list[str]:
    """Plain statements of what the source does not report."""
    q = a.q
    out = []
    for period, reason in sorted(a.missing_periods.items()):
        out.append(f"No data for {period_label(period, q.monthly)}: {reason}. Every figure for "
                   f"that {a.period_word} is shown as Missing.")
    what = q.product_code if q.product_code not in ("TOTAL", "AG2", "AG4", "AG6") else \
        "all products"
    for metric, levels in a.gap_levels():
        label = metric.label.lower()
        detail = gap_detail(a, metric, levels)
        if detail:
            out.append(f"{q.source} does not report {label} for {detail}. Every total, share, "
                       "unit value and growth rate that depends on them is shown as Missing; "
                       "nothing is estimated. The Data gaps sheet lists each one.")
        added = a.added_up.get(metric.key)
        if added:
            out.append(f"{q.source} gives no total {label} for {what} (partner World) in "
                       f"{_periods(added, q.monthly)}; there the total is its {q.roles} "
                       "added up.")
    return out


def figures_note(a: Analysis) -> str:
    """Where the report's figures come from in the source."""
    q = a.q
    if a.total_rows is None:
        return (f"{q.source} gives flows between two countries only, so every total is those "
                "flows added up.")
    what = q.product_code if q.product_code not in ("TOTAL", "AG2", "AG4", "AG6") else \
        "TOTAL (all products)"
    text = (f"Totals are {q.source}'s own figures for {what} with partner World; where it gives "
            f"none, they are the {q.roles} added up. The {q.roles} are its figures for {what} by "
            "partner.")
    if a.separate:
        products = q.product_level.split(",")[0] + "s"
        text += (f" The products are its figures for each of the {products}, with partner World "
                 "for their totals; they may not add up to the totals (see the checks).")
    return text


def edition_spans(a: Analysis) -> str:
    """The HS edition of the data by period: '2021–2022 in HS 2017 and 2023 in HS 2022'."""
    q = a.q
    runs = []
    for period, edition in sorted(q.hs_editions.items()):
        if runs and runs[-1][2] == edition:
            runs[-1][1] = period
        else:
            runs.append([period, period, edition])
    parts = [period_label(first, q.monthly)
             + ("" if first == last else f"–{period_label(last, q.monthly)}") + f" in {edition}"
             for first, last, edition in runs]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def edition_summary(a: Analysis) -> str:
    """The HS edition of the data, for the About sheet and the report."""
    q = a.q
    editions = set(q.hs_editions.values())
    if not editions:
        return "not known: the query has no data"
    if q.source == "BACI":
        return "HS 1992 for every year: BACI converts every year to the HS 1992 edition"
    if len(editions) == 1:
        return f"{editions.pop()} for every {a.period_word} with data, as {q.reporter_name} " \
               "reported it"
    return f"{edition_spans(a)}, as {q.reporter_name} reported them"


def edition_sentences(a: Analysis) -> list[str]:
    """When the data is in more than one HS edition: which, and what it means for its codes."""
    q = a.q
    if len(set(q.hs_editions.values())) < 2:
        return []
    text = (f"The data is in more than one HS edition: {q.reporter_name} reported "
            f"{edition_spans(a)}. ")
    changed = q.edition_changes
    if not q.product_editions:
        text += ("Its product codes could not be checked against COMTRADE's HS edition lists, so "
                 "a product may appear under different codes in different years.")
    elif changed:
        one = len(changed) == 1
        examples = "; ".join(f"{code}: {q.product_editions[code]}" for code in changed[:4])
        text += (f"{_count(len(changed), 'product code')} of the {len(q.product_editions)} here "
                 f"{'is' if one else 'are'} not in every one of these editions ({examples}"
                 f"{'; …' if len(changed) > 4 else ''}), so {'it appears' if one else 'they appear'}"
                 f" only in the years reported in an edition that has {'it' if one else 'them'}. "
                 "Codes are shown as reported, not converted; the Products sheet gives the HS "
                 "editions of each code.")
    else:
        text += "Every product code here exists in all of these editions."
    return [text]


def estimate_sentences(a: Analysis) -> list[str]:
    """Plain statements of the figures the source itself estimated, which are used as given."""
    q = a.q
    out = []
    for metric in a.metrics:
        e = a.estimated.get(metric.key)
        if e is None:
            continue
        label = metric.label.lower()
        text = []
        if e.count:
            size = [] if is_gap(e.amount) else [amount(e.amount, metric)]
            if not is_gap(e.share) and e.share == e.share:
                size.append(f"{pct(e.share)} of the total {label}")
            text.append(f"{_count(e.count, label + ' figure')}"
                        + (f" ({', '.join(size)})" if size else "")
                        + f" {'is an estimate' if e.count == 1 else 'are estimates'} by "
                        f"{q.estimated_by}, not reported by {q.reporter_name}.")
        if e.total_periods:
            text.append(f"{q.source} marks its total {label} (partner World) for "
                        f"{_periods(sorted(e.total_periods), q.monthly)} as an estimate by "
                        f"{q.estimated_by}.")
        if not text:
            text.append(f"Some {label} figures of the products are estimates by "
                        f"{q.estimated_by}, not reported by {q.reporter_name}.")
        text.append(f"These estimates are used as {q.source} gives them, shown in blue in the "
                    "workbook and listed in the Source estimates sheet.")
        out.append(" ".join(text))
    return out
