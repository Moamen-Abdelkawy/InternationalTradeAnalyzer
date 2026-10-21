"""US consumer price index, used to express values in constant dollars.

The table comes from the World Bank (indicator FP.CPI.TOTL, 2010 = 100). A year the World Bank
has not yet published stays empty: values for that year in constant dollars are Missing.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

URL = ("https://api.worldbank.org/v2/country/USA/indicator/FP.CPI.TOTL"
       "?format=json&per_page=200&date=1960:{year}")
SOURCE = "World Bank, consumer price index (2010 = 100), United States, indicator FP.CPI.TOTL"


def load_cpi(path: Path) -> tuple[dict[int, float], str]:
    """Year -> CPI for every published year, and a note naming the source."""
    if not path.exists():
        return {}, ""
    values, retrieved = {}, ""
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            retrieved = row.get("retrieved", retrieved)
            if row.get("cpi"):
                values[int(row["year"])] = float(row["cpi"])
    return values, f"{SOURCE}, retrieved {retrieved}"


def update_cpi(path: Path) -> str:
    """Download the series again and rewrite the table; returns what changed."""
    with urllib.request.urlopen(URL.format(year=dt.date.today().year), timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise RuntimeError(f"Unexpected answer from the World Bank: {str(payload)[:200]}")
    rows = sorted((int(item["date"]), item["value"]) for item in payload[1])
    today = dt.date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["year", "cpi", "source", "retrieved"])
        for year, value in rows:
            writer.writerow([year, "" if value is None else value, SOURCE, today])
    published = [year for year, value in rows if value is not None]
    return f"US CPI {published[0]}-{published[-1]} saved to {path}"
