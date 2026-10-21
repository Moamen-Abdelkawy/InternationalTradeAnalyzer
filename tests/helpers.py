"""Small synthetic queries for the tests."""
import numpy as np
import pandas as pd

from trade_report.model import Metric, Query

VALUE = Metric("value", "Value", "USD", "money")
QUANTITY = Metric("quantity", "Quantity", "t", "volume")


def rows(records):
    """records: (period, partner code, partner name, product code, value, quantity or None)."""
    frame = pd.DataFrame(records, columns=["Period", "Partner_Code", "Partner_Name",
                                           "Product_Code", "value", "quantity"])
    frame["Partner_ISO3"] = ""
    frame["Product_Desc"] = "Product " + frame["Product_Code"]
    frame["quantity"] = frame["quantity"].astype(float)
    return frame


def query(periods, metric=VALUE, freq="A", partner=None, missing=None):
    other = QUANTITY if metric is VALUE else VALUE
    return Query(source="BACI", freq=freq, periods=list(periods), reporter_code=818,
                 reporter_name="Egypt", flow="Imports", product_code="1001",
                 product_desc="Wheat and meslin", metric=metric, metrics=[metric, other],
                 unit_value=("value", "quantity"), partner_code=partner,
                 partner_name="Alpha" if partner else None, source_note="Test data",
                 missing_periods=missing or {})


def wheat_like():
    """Three years, three partners, two products; one quantity missing in 2022."""
    return rows([
        (2020, 1, "Alpha", "100110", 100.0, 10.0), (2020, 2, "Beta", "100110", 50.0, 5.0),
        (2020, 1, "Alpha", "100190", 50.0, 5.0),
        (2021, 1, "Alpha", "100110", 120.0, 12.0), (2021, 2, "Beta", "100110", 60.0, 6.0),
        (2021, 3, "Gamma", "100190", 20.0, 2.0),
        (2022, 1, "Alpha", "100110", 200.0, np.nan), (2022, 3, "Gamma", "100190", 40.0, 4.0),
    ])
