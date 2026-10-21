"""How numbers, gaps and undefined values are written in charts, summaries and reports.

Figures are written in their metric's own unit, money in million USD and weights in metric
tons, never rescaled to thousands or billions, so one unit holds throughout a report."""
from __future__ import annotations

import math

import numpy as np

from .analysis import is_gap, number
from .model import Metric

NOT_DEFINED = "n/a"


def gap_text(value) -> str | None:
    """'Missing' or 'Mixed units' for a gap, 'n/a' for an undefined number, else None."""
    if is_gap(value):
        return value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return NOT_DEFINED
    return None


def figure(value, metric: Metric | None = None) -> str:
    """A figure in its metric's unit: money in million USD to one decimal (27,537.5), weights
    and quantities in whole units from 100 up (3,160,055), and below 1 the decimals it needs
    (0.014), so that a small figure never shows as 0."""
    text = gap_text(value)
    if text:
        return text
    value = number(value)
    size = abs(value)
    if size == 0:
        return "0"
    if size < 1:
        digits = min(6, max(3, 1 - math.floor(math.log10(size))))
    elif metric is not None and metric.kind == "money":
        digits = 1
    else:
        digits = 0 if size >= 100 else 1
    return f"{value:,.{digits}f}"


def amount(value, metric: Metric) -> str:
    """A figure with its metric's unit: '181.7 million USD', '3,160,055 t'."""
    text = figure(value, metric)
    return text if gap_text(value) or not metric.unit else f"{text} {metric.unit}"


def tick(value, top) -> str:
    """An axis label in the metric's unit, as precise as an axis reaching `top` needs."""
    if value == 0:
        return "0"
    digits = 0 if top >= 10 else 1 if top >= 1 else 3
    return f"{value:,.{digits}f}"


def pct(value, digits=1, signed=False) -> str:
    text = gap_text(value)
    if text:
        return text
    value = number(value)
    body = f"{abs(value) * 100:,.{digits}f}%"
    if round(value * 100, digits) == 0:
        return body
    if signed:
        return ("+" if value > 0 else "−") + body
    return ("−" if value < 0 else "") + body


def points(value, digits=1) -> str:
    """A change in share in percentage points, e.g. +4.6 pp."""
    text = gap_text(value)
    if text:
        return text
    value = number(value)
    return f"{'+' if value > 0 else '−' if value < 0 else ''}{abs(value):,.{digits}f} pp"


def count(value) -> str:
    text = gap_text(value)
    return text if text else f"{number(value):,.0f}"


def short(text, width=30) -> str:
    text = str(text)
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def short_end(text, width=30) -> str:
    """The end of a long text, where an HS description says what sets a code apart from its
    siblings: '…of a fat content not exceeding 1% (by weight)'."""
    text = str(text)
    if len(text) <= width:
        return text
    tail = text[-(width - 1):]
    for mark, within in ((", ", width // 2), (" ", width // 3)):   # at a clause, else a word
        cut = tail.find(mark)
        if 0 <= cut < within:
            return "…" + tail[cut + len(mark):]
    return "…" + tail


def lower_first(text: str) -> str:
    """'Wheat and meslin' -> 'wheat and meslin', leaving acronyms such as 'LNG' alone."""
    text = str(text).rstrip(".")
    first = text.split(" ")[0] if text else ""
    return text if first.isupper() and len(first) > 1 else text[:1].lower() + text[1:]
