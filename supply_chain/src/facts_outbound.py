"""Outbound facts: customer order lines and shipments.

Outbound is CONSTRAINED BY the inventory simulation rather than generated
independently -- shipped quantities come from what the snapshot fact actually
served. Generating sales freely and inventory separately is what produces a
dataset where a SKU sells happily through a month it was out of stock.

OTIF is a SHIPMENT-level metric. A late shipment carrying 40 lines counts
once; computing it at line grain inflates it (docs/DATA_MODEL.md section 6).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_sales_order_lines(s, inv: pd.DataFrame, dim_product, dim_location,
                            dim_customer, engine, rng):
    """Sample order lines from what was actually served, by pair and day."""
    n_target = int(s.sizes["sales_order_lines"])
    served = inv.loc[inv["served_current_qty"] > 0,
                     ["snapshot_date", "snapshot_grain", "product_id",
                      "location_id", "served_current_qty", "unmet_qty"]]
    # Weekly rows stand for a whole week; scaling them keeps the sampling
    # weights proportional to real volume across the mixed grain.
    weight = served["served_current_qty"].to_numpy(dtype=float) * np.where(
        served["snapshot_grain"].to_numpy() == "W", 7.0, 1.0)
    weight = np.clip(weight, 1e-9, None)
    weight = weight / weight.sum()

    idx = rng.choice(len(served), size=n_target, p=weight)
    rows = served.iloc[idx].reset_index(drop=True)

    loc_region = dim_location.set_index("location_id")["region"]
    rows["region"] = rows["location_id"].map(loc_region)

    cust_by_region = {r: g["customer_id"].to_numpy()
                      for r, g in dim_customer.groupby("region", observed=True)}
    all_cust = dim_customer["customer_id"].to_numpy()
    customer_id = np.array([rng.choice(cust_by_region.get(r, all_cust))
                            for r in rows["region"].to_numpy()], dtype="int32")

    # A line takes a slice of what that pair served that period.
    frac = rng.uniform(0.05, 0.45, n_target)
    qty = np.round(np.clip(rows["served_current_qty"].to_numpy() * frac, 0.001, None), 3)

    price = rows["product_id"].map(dim_product.set_index("product_id")["standard_price"])
    cost = rows["product_id"].map(dim_product.set_index("product_id")["unit_cost"])
    discount = np.clip(rng.normal(0.06, 0.035, n_target), 0, 0.35)
    revenue = np.round(qty * price.to_numpy() * (1 - discount), 2)

    # A line is short-shipped when its pair had unmet demand that period.
    short = rows["unmet_qty"].to_numpy() > 1e-6
    ordered_qty = np.round(np.where(short, qty * rng.uniform(1.05, 1.6, n_target), qty), 3)

    df = pd.DataFrame({
        "order_line_id": np.arange(1, n_target + 1, dtype="int64"),
        "order_id": 0,          # assigned below
        "order_date": pd.to_datetime(rows["snapshot_date"]),
        "customer_id": customer_id,
        "product_id": rows["product_id"].to_numpy().astype("int32"),
        "location_id": rows["location_id"].to_numpy().astype("int32"),
        "ordered_qty": ordered_qty,
        "shipped_qty": qty,
        "unit_price": price.to_numpy(),
        "discount_pct": np.round(discount, 4),
        "net_revenue": revenue,
        "cost_of_goods": np.round(qty * cost.to_numpy(), 2),
        "is_short_shipped": short.astype("int8"),
        "is_line_filled": (~short).astype("int8"),
    })
    # An order is ONE customer, at ONE location, on ONE day. Chunking
    # consecutive rows into groups of three instead made every order a bundle
    # of unrelated lines, and taking min(order_date) across three independent
    # dates skewed order dates hard toward the start of the timeline -- which
    # silently pushed nearly all shipments outside every event window.
    df["order_id"] = (df.groupby(["customer_id", "order_date", "location_id"])
                        .ngroup() + 1).astype("int64")

    df["gross_profit"] = np.round(df["net_revenue"] - df["cost_of_goods"], 2)
    df["year_month_key"] = (df["order_date"].dt.year * 100
                            + df["order_date"].dt.month).astype("int32")
    return df


def build_shipments(s, order_lines: pd.DataFrame, dim_location, dim_carrier,
                    dim_customer, engine, rng):
    """One shipment per order. OTIF is measured here, not on the lines."""
    g = order_lines.groupby("order_id").agg(
        order_date=("order_date", "first"),
        customer_id=("customer_id", "first"),
        location_id=("location_id", "first"),
        quantity=("shipped_qty", "sum"),
        ordered_qty=("ordered_qty", "sum"),
        lines=("order_line_id", "size"),
        short_lines=("is_short_shipped", "sum"),
        revenue=("net_revenue", "sum")).reset_index()
    n = len(g)

    carriers = dim_carrier["carrier_id"].to_numpy()
    carrier_id = rng.choice(carriers, n)
    cpos = np.array([{c: i for i, c in enumerate(dim_carrier["carrier_id"])}[c]
                     for c in carrier_id])

    loc = dim_location.set_index("location_id")
    g["region"] = g["location_id"].map(loc["region"])
    g["sub_region"] = g["location_id"].map(loc["sub_region"])

    ship_date = pd.to_datetime(g["order_date"]) + pd.to_timedelta(
        rng.integers(0, 3, n), unit="D")
    contracted = dim_carrier.set_index("carrier_id")["contracted_transit_days"]
    base_transit = pd.Series(carrier_id).map(contracted).to_numpy(dtype=float)
    expected = ship_date + pd.to_timedelta(np.round(base_transit).astype(int), unit="D")

    mpos = engine.month_pos(ship_date)
    # Event 4 is geographically concentrated: only shipments in the named
    # sub-region take the degradation, which is what makes the drill from
    # carrier to region to shipment find something.
    add = engine.carrier_transit_add[cpos, mpos].copy()
    cost_mult = engine.carrier_cost_mult[cpos, mpos].copy()
    for ci, (region, sub) in engine.carrier_region.items():
        m = cpos == ci
        if sub:
            m &= (g["sub_region"].to_numpy() != sub)
        elif region:
            m &= (g["region"].to_numpy() != region)
        add[m] = 0.0
        cost_mult[m] = 1.0

    p_on_time = np.clip(float(s.baseline.get("base_shipment_on_time",
                              s.baseline["base_otif"])), 0.02, 0.995)
    late = rng.random(n) > p_on_time
    delay = np.where(late, rng.gamma(1.5, 2.0, n), -rng.gamma(1.1, 0.9, n)) + add
    actual = expected + pd.to_timedelta(np.round(delay).astype(int), unit="D")

    distance = np.round(rng.gamma(2.2, 320, n), 1)
    freight = np.round(distance * pd.Series(carrier_id).map(
        dim_carrier.set_index("carrier_id")["base_cost_per_km"]).to_numpy()
        * cost_mult * (1 + g["quantity"].to_numpy() / 5000), 2)

    expedited = rng.random(n) < 0.04 * engine.expedite_mult[mpos]
    freight = np.round(freight * np.where(
        expedited, float(s.financial["expedite_freight_premium"]), 1.0), 2)

    in_full = g["short_lines"].to_numpy() == 0
    on_time = actual <= expected

    dq = s.baseline["data_quality"]
    null_mask = rng.random(n) < dq["null_delivery_date_pct"]
    actual_out = pd.Series(actual).where(~null_mask)

    df = pd.DataFrame({
        "shipment_id": np.arange(1, n + 1, dtype="int64"),
        "order_id": g["order_id"].to_numpy(),
        "customer_id": g["customer_id"].to_numpy(),
        "location_id": g["location_id"].to_numpy(),
        "carrier_id": carrier_id.astype("int32"),
        "ship_date": ship_date,
        "expected_delivery_date": expected,
        "actual_delivery_date": actual_out,
        "quantity": np.round(g["quantity"].to_numpy(), 3),
        "line_count": g["lines"].to_numpy().astype("int32"),
        "distance_km": distance,
        "freight_cost": freight,
        "is_expedited": expedited.astype("int8"),
        "transit_days": (actual - ship_date).dt.days.to_numpy(),
        "delay_days": np.round(delay).astype("int32"),
        "is_on_time": on_time.astype("int8"),
        "is_in_full": in_full.astype("int8"),
        "is_otif": (on_time & in_full).astype("int8"),
        "damage_flag": (rng.random(n) < 0.006).astype("int8"),
        "shipping_method": np.where(expedited, "Expedited", "Standard"),
    })
    df["year_month_key"] = (df["ship_date"].dt.year * 100
                            + df["ship_date"].dt.month).astype("int32")
    return df
