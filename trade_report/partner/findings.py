"""The key findings of a partner report, written as plain sentences."""
from __future__ import annotations

from ..analysis import is_gap, number, total_of
from ..findings import (_count, edition_sentences, estimate_sentences, gap_detail,
                        gap_sentences)
from ..fmt import amount, lower_first, pct, points
from ..model import period_label
from .analysis import PartnerAnalysis

SPECIAL = ("TOTAL", "AG2", "AG4", "AG6")


class Terms:
    """The words a partner report uses for its two countries, the flows and the product."""

    def __init__(self, pa: PartnerAnalysis):
        q = pa.q
        self.reporter, self.partner = q.reporter_name, pa.name
        self.flow = q.flow.lower()                                    # imports
        self.to = "from" if q.flow == "Imports" else "to"             # imports from
        self.other_flow = "exports" if q.flow == "Imports" else "imports"
        self.other_to = "to" if q.flow == "Imports" else "from"       # exports to
        self.side_flow = pa.side_query.flow.lower() if pa.side_query else self.other_flow
        self.side_roles = pa.side_query.roles if pa.side_query else (
            "markets" if q.flow == "Imports" else "suppliers")
        special = q.product_code in SPECIAL
        self.product = "all products" if special else lower_first(q.product_desc)
        self.code = "" if special else f" (HS {q.product_code})"
        self.reported_as = (f"as {pa.name} reports them" if q.source == "COMTRADE"
                            else "as recorded in BACI")


def known(value) -> bool:
    """A number: not a gap and not undefined."""
    return not is_gap(value) and value == value and value is not None and value != ""


def share_text(value) -> str:
    """A share as text: '0%' for none, 'less than 0.1%' for one that would round to 0.0%."""
    if known(value) and number(value) == 0:
        return "0%"
    if known(value) and 0 < number(value) < 0.0005:
        return "less than 0.1%"
    return pct(value)


def period_runs(periods, monthly: bool) -> str:
    """Periods as runs of consecutive ones: '2020, 2022–2025', 'Jan 2024–Dec 2024'."""
    def following(period):
        if not monthly:
            return period + 1
        year, month = divmod(period, 100)
        return (year + 1) * 100 + 1 if month == 12 else period + 1

    runs = []
    for period in sorted(periods):
        if runs and following(runs[-1][1]) == period:
            runs[-1][1] = period
        else:
            runs.append([period, period])
    return ", ".join(period_label(a, monthly) + ("" if a == b else f"–{period_label(b, monthly)}")
                     for a, b in runs)


def product_name(text, code) -> str:
    """A short name for an HS code, capitalised. For an HS 6-digit product, the part of its
    description that sets it apart from its siblings: 'Cereals; wheat and meslin, durum wheat'
    -> 'Wheat and meslin, durum wheat', 'Cereals: durum wheat' -> 'Durum wheat'. For a chapter
    or heading, the first part of its description: 'Nuclear reactors, boilers, machinery and
    mechanical appliances; parts thereof' -> 'Nuclear reactors, boilers, machinery and
    mechanical appliances'."""
    text = str(text)
    text = (text.rsplit("; ", 1)[-1].split(": ", 1)[-1] if len(str(code)) == 6
            else text.split("; ", 1)[0])
    return text[:1].upper() + text[1:]


def findings(pa: PartnerAnalysis) -> list[str]:
    t = Terms(pa)
    out = [_headline(pa, t)]
    if pa.traded:
        out += [s for s in (_growth(pa, t), _share(pa, t), contribution_sentence(pa, t)) if s]
    out += [s for s in (_competitors(pa, t), _prices(pa, t), _products(pa, t),
                        side_sentence(pa, t), mirror_sentence(pa, t), other_sentence(pa, t)) if s]
    out += gap_sentences(pa.a)
    for analysis, label in ((pa.side, f"{t.partner}'s {t.side_flow}"),
                            (pa.other, f"{t.reporter}'s {t.other_flow} {t.other_to} "
                                       f"{t.partner}")):
        out += view_gap_sentences(analysis, label)
    for analysis in (pa.a, pa.side):
        if analysis is not None:
            out += estimate_sentences(analysis)
            out += edition_sentences(analysis)
    return out


def _headline(pa: PartnerAnalysis, t: Terms) -> str:
    q, s, m, a = pa.q, pa.summary, pa.metric, pa.a
    if not pa.traded:
        text = (f"{q.source} records no {t.flow} of {t.product}{t.code} by {t.reporter} {t.to} "
                f"{t.partner} in {q.span}")
        top = a.summary["top"]
        if top is not None:
            text += (f"; {t.reporter}'s {t.flow} of it "
                     f"{'came from' if q.flow == 'Imports' else 'went to'} "
                     f"{_count(a.summary['partners'], q.role)}, the largest being "
                     f"{a.partner_names[top]} ({pct(a.summary['top_share'])})")
        return text + "."
    if is_gap(s["total"]):
        return (f"{t.reporter}'s {t.flow} of {t.product}{t.code} {t.to} {t.partner} over "
                f"{q.span} cannot be totalled: {q.source} does not report "
                f"{m.label.lower()} for part of them (see Data gaps).")
    text = (f"{t.reporter}'s {t.flow} of {t.product}{t.code} {t.to} {t.partner} totalled "
            f"{amount(s['total'], m)} over {q.span}")
    if is_gap(s["share"]):
        text += (f"; their share of all its {t.flow} cannot be stated: {m.label.lower()} is "
                 "missing for part of the data")
    elif known(s["share"]):
        text += (f", {share_text(s['share'])} of its {t.flow} {t.to} all "
                 f"{_count(s['partners'], q.role)}")
    if known(s["rank"]):
        text += f"; {t.partner} ranked #{s['rank']}"
    return text + "."


def _growth(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, s, m, a, y = pa.q, pa.summary, pa.metric, pa.a, pa.years
    if len(y) < 2:
        return None
    y0, y1 = y[0], y[-1]
    if is_gap(s["cagr"]):
        annual = pa.annual(pa.series[m.key])
        ends = " and ".join(str(x) for x in (y0, y1) if is_gap(annual[x]))
        return (f"Growth from {y0} to {y1} cannot be stated: {m.label.lower()} is missing for "
                f"{ends}.")
    if not known(s["cagr"]):
        return (f"There is no CAGR from {y0} to {y1}: there was no trade with {t.partner} in "
                "one of the two years.")
    text = (f"{m.label} {t.to} {t.partner} moved from {amount(s['first'], m)} in {y0} to "
            f"{amount(s['last'], m)} in {y1}, a compound annual growth rate of "
            f"{pct(s['cagr'], signed=True)}")
    if known(a.summary["cagr"]):
        text += f" (all {q.roles}: {pct(a.summary['cagr'], signed=True)})"
    if known(s["trend"]):
        text += f"; the trend fitted to every year is {pct(s['trend'], signed=True)} a year"
    peak_period, peak_value = s["peak"]
    if peak_period is not None:
        text += (f". The peak was {period_label(peak_period, q.monthly)} "
                 f"({amount(peak_value, m)})")
    if known(s.get("real_cagr")):
        text += (f". In constant {a.real_base} dollars the CAGR is "
                 f"{pct(s['real_cagr'], signed=True)}")
    return text + "."


def _share(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, f = pa.q, pa.position
    labels = [period_label(p, q.monthly) for p in f["Period"]]
    shares, ranks = f["Share"].tolist(), f["Rank"].tolist()
    if len(f) == 1:
        if not known(shares[0]):
            return None
        return (f"{t.partner} held {share_text(shares[0])} of {t.reporter}'s {t.flow} in "
                f"{labels[0]}"
                + (f", ranking #{ranks[0]}" if known(ranks[0]) else "") + ".")
    first, last = shares[0], shares[-1]
    if known(first) and known(last) and first == 0 and last == 0:
        return f"There was no trade with {t.partner} in {labels[0]} or {labels[-1]}."
    if known(first) and known(last):
        change = (last - first) * 100
        text = (f"{t.partner}'s share went from {share_text(first)} in {labels[0]} to "
                f"{share_text(last)} in {labels[-1]}"
                + (f" ({points(change)})" if abs(change) >= 0.05 else ""))
    elif known(last):
        text = (f"{t.partner}'s share was {share_text(last)} in {labels[-1]}; in {labels[0]} it "
                "cannot be stated")
    elif known(first):
        text = (f"{t.partner}'s share was {share_text(first)} in {labels[0]}; in {labels[-1]} "
                "it cannot be stated")
    else:
        return (f"{t.partner}'s share of {t.reporter}'s {t.flow} cannot be stated for "
                f"{labels[0]} or {labels[-1]}: {pa.metric.label.lower()} is missing.")
    if all(known(r) for r in ranks) and set(ranks) == {1}:
        text += f"; it was the largest {q.role} in every {pa.period_word}"
    elif known(ranks[-1]):
        text += f"; it ranked #{ranks[-1]} in {labels[-1]}"
    return text + "."


def contribution_sentence(pa: PartnerAnalysis, t: Terms) -> str | None:
    c, m, q = pa.contribution, pa.metric, pa.q
    if c is None or not (known(c["total"]) and known(c["partner"])):
        return None
    whole, part = number(c["total"]), number(c["partner"])

    def moved(value):
        return ("rose by " + amount(abs(value), m) if value > 0 else
                "fell by " + amount(abs(value), m) if value < 0 else "did not change")

    text = (f"From {c['y0']} to {c['y1']}, {t.reporter}'s {t.flow} {t.to} all {q.roles} "
            f"{moved(whole)}; those {t.to} {t.partner} {moved(part)}")
    if whole and part and (whole > 0) == (part > 0):
        text += f", {pct(part / whole)} of the change"
    return text + "."


def _competitors(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, a = pa.q, pa.a
    rows = a.partners.set_index("Code") if len(a.partners) else None
    if rows is None or not pa.rivals:
        return None
    ordered = a.partner_order.key == pa.metric.key
    named = [a.partner_names[c] + (f" ({share_text(rows.loc[c, 'Share'])})" if ordered else "")
             for c in pa.rivals[:2]]
    by = "" if ordered else f" by {a.partner_order.label.lower()}"
    text = (f"The largest other {q.role}{by} was {named[0]}" if len(named) == 1 else
            f"The largest other {q.roles}{by} were {named[0]} and {named[1]}")
    if not ordered:
        metric = pa.metric.label.lower()
        text += (f" (their shares of {metric} cannot be stated: {metric} is missing for part "
                 "of the data)")
    if len(pa.years) >= 2 and "Share change (pp)" in rows:
        changes = {c: number(rows.loc[c, "Share change (pp)"]) for c in pa.rivals
                   if known(rows.loc[c, "Share change (pp)"])}
        gained = max(changes, key=changes.get) if changes else None
        lost = min(changes, key=changes.get) if changes else None
        parts = []
        if gained is not None and changes[gained] > 0:
            parts.append(f"{a.partner_names[gained]} gained the most share "
                         f"({points(changes[gained])})")
        if lost is not None and changes[lost] < 0:
            parts.append(f"{a.partner_names[lost]} lost the most ({points(changes[lost])})")
        if parts:
            text += (f"; among the {len(pa.rivals)} largest, from {pa.years[0]} to "
                     f"{pa.years[-1]}, " + " and ".join(parts))
    return text + "."


def _prices(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, a = pa.q, pa.a
    if pa.unit_values is None or not pa.traded:
        return None
    volume = next(m for m in pa.metrics if m.key == q.unit_value[1])
    unit = f"USD/{volume.unit or 'unit'}"
    both = [p for p in pa.periods if known(pa.unit_values[p]) and known(a.unit_values[p])]
    if both:
        p = both[-1]
        mine, every = number(pa.unit_values[p]), number(a.unit_values[p])
        text = (f"In {period_label(p, q.monthly)}, {t.partner}'s unit value was {mine:,.2f} "
                f"{unit}, against {every:,.2f} for all {q.roles}")
        gap = mine / every - 1 if every else None
        if gap is not None and round(gap, 3):
            text += f" ({pct(abs(gap))} {'higher' if gap > 0 else 'lower'})"
        return text + "." + _estimated_volume(pa, volume, p)
    mine = [p for p in pa.periods if known(pa.unit_values[p])]
    if mine:
        p = mine[-1]
        return (f"In {period_label(p, q.monthly)}, {t.partner}'s unit value was "
                f"{number(pa.unit_values[p]):,.2f} {unit}; that of all {q.roles} cannot be "
                f"stated: {volume.label.lower()} is missing for part of the data."
                + _estimated_volume(pa, volume, p, partner_only=True))
    return (f"{t.partner}'s unit value cannot be stated for any {pa.period_word}: "
            f"{volume.label.lower()} is missing.")


def _estimated_volume(pa: PartnerAnalysis, volume, period, partner_only=False) -> str:
    """' Both rest on net weights that include figures UN Comtrade estimated.', when the
    volume behind a unit value of that period includes the source's own estimates."""
    e = pa.a.estimated.get(volume.key)
    if e is None:
        return ""
    mine = (pa.code, period) in e.cells("Partner_Code")
    every = period in e.periods and not partner_only
    if not (mine or every):
        return ""
    whose = ("Both rest" if mine and every else f"{pa.name}'s rests" if mine else
             f"That of all {pa.q.roles} rests")
    weights = f"{volume.label.lower()}{'s' if mine and every else ''}"
    return (f" {whose} on {'a ' if not (mine and every) else ''}{weights} that "
            f"include{'s' if not (mine and every) else ''} figures {pa.q.estimated_by} estimated.")


def _products(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, table = pa.q, pa.products
    if table is None or table.empty:
        return None
    if len(table) == 1 and str(table.iloc[0]["Code"]) == q.product_code:
        return None             # the product asked for is the only one
    lead = table.iloc[0]
    if not known(lead["Share"]):
        return None
    text = (f"{product_name(lead['Name'], lead['Code'])} ({lead['Code']}) made up "
            f"{pct(lead['Share'])} of {t.flow} {t.to} {t.partner}")
    if known(lead["Market share"]):
        verb = "supplied" if q.flow == "Imports" else "took"
        text += (f"; {t.partner} {verb} {share_text(lead['Market share'])} of {t.reporter}'s "
                 f"{t.flow} of it")
    return text + f" over {q.span}."


def unreported_text(query, name) -> str:
    """The periods a country did not report, grouped by reason."""
    by_reason = {}
    for period, reason in sorted(query.missing_periods.items()):
        by_reason.setdefault(reason, []).append(period)
    return " ".join(f"No data from {name} for {period_runs(periods, query.monthly)}: {reason}."
                    for reason, periods in by_reason.items())


def side_sentence(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, sq = pa.q, pa.side_query
    if pa.side_status == "unavailable":
        return f"{t.partner}'s side of the trade could not be read."
    if pa.side_status == "unreported":
        what = (f"{t.reporter}'s share of its {t.side_flow}, and its own figures for its trade "
                f"with {t.reporter}," if q.source == "COMTRADE" else
                f"{t.reporter}'s share of its {t.side_flow}")
        return f"{unreported_text(sq, t.partner)} So {what} cannot be stated."
    if pa.side_status == "none":
        return (f"{q.source} records no {t.side_flow} of {t.product} by {t.partner} in "
                f"{q.span}" + (f", {t.reported_as}" if q.source == "COMTRADE" else "") + ".")
    f = pa.side_position
    rows = [r for r in f.to_dict("records") if known(r["Share"])]
    if not rows:
        metric = pa.side.metric.label.lower()
        text = (f"{t.reporter}'s share of {t.partner}'s {t.side_flow} cannot be stated for any "
                f"{pa.period_word}: {metric} is missing for part of the data on "
                f"{t.partner}'s {t.side_flow}.")
    else:
        first, last = rows[0], rows[-1]
        p0, p1 = (period_label(r["Period"], q.monthly) for r in (first, last))
        text = (f"{t.reported_as[:1].upper() + t.reported_as[1:]}, {t.reporter}'s share of "
                f"{t.partner}'s {t.side_flow} of {t.product} was {share_text(first['Share'])} in "
                f"{p0}" + (f" and {share_text(last['Share'])} in {p1}" if p1 != p0 else ""))
        if known(last["Rank"]):
            text += f"; {t.reporter} ranked #{last['Rank']} among its {t.side_roles} in {p1}"
        text += "."
        counts = [r for r in rows if known(r["Partners"])]
        if q.source == "BACI" and len(counts) >= 2:
            c0, c1 = (period_label(r["Period"], q.monthly) for r in (counts[0], counts[-1]))
            text += (f" BACI records {t.partner}'s {t.side_flow} {t.other_to} "
                     f"{counts[0]['Partners']:,} countries in {c0} and "
                     f"{counts[-1]['Partners']:,} in {c1}.")
    if sq is not None and sq.missing_periods:
        text += " " + unreported_text(sq, t.partner)
    return text


def mirror_sentence(pa: PartnerAnalysis, t: Terms) -> str | None:
    q = pa.q
    if not pa.mirror or "value" not in pa.mirror or pa.side_status == "unreported":
        return None
    value = next(m for m in pa.metrics if m.key == "value")
    frame = pa.mirror["value"]
    both = [r for r in frame.to_dict("records")
            if known(r["Reporter"]) and known(r["Partner"]) and r["Reporter"] > 0
            and r["Partner"] > 0]
    if not both:
        return None
    row = both[-1]
    mine, theirs = number(row["Reporter"]), number(row["Partner"])
    gap = mine / theirs - 1
    text = (f"The two countries' figures for the same trade "
            f"{'agree' if abs(gap) < 0.0005 else 'differ'}: for "
            f"{period_label(row['Period'], q.monthly)}, {t.reporter} reported "
            f"{amount(mine, value)} of {t.flow} {t.to} {t.partner}, and {t.partner} reported "
            f"{amount(theirs, value)} of {t.side_flow} {t.other_to} {t.reporter}")
    if abs(gap) >= 0.0005:
        text += f" ({t.reporter}'s figure is {pct(abs(gap))} {'higher' if gap > 0 else 'lower'})"
    return (text + ". Each is shown as its country reports it, without adjustment; imports are "
                   "usually valued CIF and exports FOB.")


def other_sentence(pa: PartnerAnalysis, t: Terms) -> str | None:
    q, m = pa.q, pa.metric
    if pa.other_status == "none":
        return (f"{q.source} records no {t.other_flow} of {t.product} by {t.reporter} "
                f"{t.other_to} {t.partner} in {q.span}.")
    if pa.other_status != "ok":
        return None
    total = total_of(pa.view_series("other", m.key))
    if is_gap(total):
        text = (f"{t.reporter}'s {t.other_flow} of {t.product} {t.other_to} {t.partner} over "
                f"{q.span} cannot be totalled: {m.label.lower()} is missing for part of them")
    else:
        text = (f"{t.reporter}'s {t.other_flow} of {t.product} {t.other_to} {t.partner} "
                f"totalled {amount(total, m)} over {q.span}")
    if pa.balance is not None:
        balance = total_of(pa.balance)
        value = next(x for x in pa.metrics if x.key == "value")
        if known(balance):
            text += (f"; in value, {t.reporter}'s balance of trade with {t.partner} in these "
                     f"products was a {'surplus' if balance > 0 else 'deficit'} of "
                     f"{amount(abs(balance), value)}")
    return text + "."


def view_gap_sentences(analysis, label: str) -> list[str]:
    """What the source does not report in another view of the trade (its unreported periods
    are stated with the view)."""
    if analysis is None:
        return []
    out = []
    for metric, levels in analysis.gap_levels():
        detail = gap_detail(analysis, metric, levels)
        if detail:
            out.append(f"In the data on {label}, {analysis.q.source} does not report "
                       f"{metric.label.lower()} for {detail}. Every figure that depends on them "
                       "is shown as Missing; nothing is estimated.")
    return out
