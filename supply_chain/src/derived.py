"""Everything computed FROM the facts: supplier and carrier scorecards, the
risk layer, and financial impact.

None of this is sampled independently. If dim_supplier says SUP-104 is at 71%
on-time and the delivery fact says 88%, the demo is over the moment someone
drills in, so the dimension is back-filled from the fact and the validator
asserts the two agree.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _band(score, bands: dict) -> np.ndarray:
    """Map a 0-100 score onto its named band.

    Thresholds must be applied ASCENDING so the highest band a score qualifies
    for is the one that survives. Iterating descending lets each successive
    (lower) threshold overwrite the band above it, and everything ends up in
    the bottom band -- which is what happened here: risk scores ran up to 77
    while every single supplier was labelled "Low".
    """
    order = sorted(bands.items(), key=lambda kv: kv[1])
    out = np.full(len(score), order[0][0], dtype=object)
    for name, lo in order:
        out = np.where(score >= lo, name, out)
    return out


def backfill_supplier_scorecard(s, dim_supplier, deliveries, dim_product):
    """Trailing-90-day performance, written onto the dimension."""
    asof = pd.Timestamp(s.timeline.as_of_date)
    d = deliveries[pd.to_datetime(deliveries["actual_receipt_date"])
                   > asof - pd.Timedelta(days=90)]
    g = d.groupby("supplier_id").agg(
        on_time_rate=("is_on_time", "mean"),
        defect_rate=("defect_rate", "mean"),
        receipts=("delivery_id", "size"),
        spend=("receipt_value", "sum"))

    out = dim_supplier.copy()
    out["on_time_rate"] = out["supplier_id"].map(g["on_time_rate"]).round(4)
    out["defect_rate"] = out["supplier_id"].map(g["defect_rate"]).round(5)
    out["trailing_90d_spend"] = out["supplier_id"].map(g["spend"]).fillna(0).round(2)
    out["quality_score"] = ((1 - out["defect_rate"].fillna(0.02)) * 100).round(2)

    sourced = dim_product.groupby("primary_supplier_id").agg(
        skus_supplied=("product_id", "size"),
        critical_skus=("criticality", lambda x: int((x == "Critical").sum())),
        single_sourced_skus=("single_source_flag", "sum"))
    out["skus_supplied"] = out["supplier_id"].map(sourced["skus_supplied"]).fillna(0).astype("int32")
    out["critical_skus_supplied"] = out["supplier_id"].map(
        sourced["critical_skus"]).fillna(0).astype("int32")
    out["single_sourced_skus"] = out["supplier_id"].map(
        sourced["single_sourced_skus"]).fillna(0).astype("int32")

    w = s.risk["weights"]
    sup_risk = (1 - out["on_time_rate"].fillna(0.9)) * 220
    qual_risk = out["defect_rate"].fillna(0.02) * 900
    conc_risk = np.clip(out["single_sourced_skus"] * 6, 0, 100)
    fin = out["financial_risk"].astype(float)
    geo = out["geopolitical_risk"].astype(float)
    score = (sup_risk * w["supplier_risk"]
             + qual_risk * w["quality_risk"]
             + conc_risk * w["inventory_risk"]
             + fin * w["demand_risk"] * 0.5
             + geo * w["logistics_risk"] * 0.5)
    score = np.clip(score * float(s.risk.get("score_scale", 1.9)), 0, 100)
    out["risk_score"] = np.round(score, 1)
    out["risk_level"] = _band(out["risk_score"].to_numpy(), s.risk["bands"])
    out.loc[out["supplier_id"] == 0, ["risk_score", "risk_level"]] = [0.0, "None"]
    return out


def backfill_carrier_scorecard(dim_carrier, shipments):
    g = shipments.groupby("carrier_id").agg(
        on_time_rate=("is_on_time", "mean"),
        avg_transit_days=("transit_days", "mean"),
        shipments=("shipment_id", "size"),
        freight_cost=("freight_cost", "sum"))
    out = dim_carrier.copy()
    out["on_time_rate"] = out["carrier_id"].map(g["on_time_rate"]).round(4)
    out["avg_transit_days"] = out["carrier_id"].map(g["avg_transit_days"]).round(2)
    out["shipment_count"] = out["carrier_id"].map(g["shipments"]).fillna(0).astype("int32")
    out["total_freight_cost"] = out["carrier_id"].map(g["freight_cost"]).fillna(0).round(2)
    return out


def build_fact_supply_chain_risk(s, dim_supplier, dim_product, dim_location,
                                 deliveries, inv, forecast, shipments):
    """Monthly risk by entity, every component traced to a fact."""
    w, bands = s.risk["weights"], s.risk["bands"]
    frames = []

    d = deliveries.copy()
    d["year_month_key"] = d["year_month_key"].astype("int32")
    sup = d.groupby(["year_month_key", "supplier_id"]).agg(
        on_time=("is_on_time", "mean"), defect=("defect_rate", "mean")).reset_index()
    sup["supplier_risk"] = np.clip((1 - sup["on_time"]) * 210, 0, 100)
    sup["quality_risk"] = np.clip(sup["defect"] * 900, 0, 100)

    invm = inv[inv["snapshot_grain"] == "W"].groupby(
        ["year_month_key", "product_id"]).agg(
        stockout=("stockout_flag", "mean"), dos=("days_of_supply", "mean")).reset_index()
    invm["inventory_risk"] = np.clip(invm["stockout"] * 320, 0, 100)

    fc = forecast[forecast["forecast_version"] == "ML"].groupby(
        ["year_month_key", "product_id"])["abs_pct_error"].mean().reset_index()
    fc["demand_risk"] = np.clip(fc["abs_pct_error"] * 260, 0, 100)

    ship = shipments.groupby(["year_month_key", "location_id"]).agg(
        otif=("is_otif", "mean")).reset_index()
    ship["logistics_risk"] = np.clip((1 - ship["otif"]) * 240, 0, 100)

    # Suppliers
    a = sup.merge(ship.groupby("year_month_key")["logistics_risk"].mean().rename("log_avg"),
                  on="year_month_key", how="left")
    a["demand_risk"] = fc.groupby("year_month_key")["demand_risk"].mean().reindex(
        a["year_month_key"]).to_numpy()
    a["inventory_risk"] = invm.groupby("year_month_key")["inventory_risk"].mean().reindex(
        a["year_month_key"]).to_numpy()
    frames.append(pd.DataFrame({
        "year_month_key": a["year_month_key"], "entity_type": "Supplier",
        "entity_id": a["supplier_id"], "supplier_risk": a["supplier_risk"],
        "quality_risk": a["quality_risk"], "logistics_risk": a["log_avg"].fillna(30),
        "demand_risk": a["demand_risk"], "inventory_risk": a["inventory_risk"]}))

    # Products
    b = invm.merge(fc, on=["year_month_key", "product_id"], how="left")
    b["supplier_risk"] = sup.groupby("year_month_key")["supplier_risk"].mean().reindex(
        b["year_month_key"]).to_numpy()
    b["quality_risk"] = sup.groupby("year_month_key")["quality_risk"].mean().reindex(
        b["year_month_key"]).to_numpy()
    b["logistics_risk"] = ship.groupby("year_month_key")["logistics_risk"].mean().reindex(
        b["year_month_key"]).to_numpy()
    frames.append(pd.DataFrame({
        "year_month_key": b["year_month_key"], "entity_type": "Product",
        "entity_id": b["product_id"], "supplier_risk": b["supplier_risk"],
        "quality_risk": b["quality_risk"], "logistics_risk": b["logistics_risk"],
        "demand_risk": b["demand_risk"], "inventory_risk": b["inventory_risk"]}))

    # Locations
    c = ship.copy()
    for col, src in (("supplier_risk", sup), ("quality_risk", sup)):
        c[col] = src.groupby("year_month_key")[col].mean().reindex(
            c["year_month_key"]).to_numpy()
    c["demand_risk"] = fc.groupby("year_month_key")["demand_risk"].mean().reindex(
        c["year_month_key"]).to_numpy()
    c["inventory_risk"] = invm.groupby("year_month_key")["inventory_risk"].mean().reindex(
        c["year_month_key"]).to_numpy()
    frames.append(pd.DataFrame({
        "year_month_key": c["year_month_key"], "entity_type": "Location",
        "entity_id": c["location_id"], "supplier_risk": c["supplier_risk"],
        "quality_risk": c["quality_risk"], "logistics_risk": c["logistics_risk"],
        "demand_risk": c["demand_risk"], "inventory_risk": c["inventory_risk"]}))

    out = pd.concat(frames, ignore_index=True)
    for col in ("supplier_risk", "demand_risk", "inventory_risk",
                "logistics_risk", "quality_risk"):
        out[col] = out[col].astype(float).fillna(30.0).clip(0, 100).round(1)
    out["overall_risk_score"] = np.round(
        out["supplier_risk"] * w["supplier_risk"] + out["demand_risk"] * w["demand_risk"]
        + out["inventory_risk"] * w["inventory_risk"]
        + out["logistics_risk"] * w["logistics_risk"]
        + out["quality_risk"] * w["quality_risk"], 1)
    out["risk_level"] = _band(out["overall_risk_score"].to_numpy(), bands)
    out["entity_id"] = out["entity_id"].astype("int32")
    return out.reset_index(drop=True)


def build_fact_financial_impact(s, inv, shipments, deliveries, order_lines,
                                dim_product):
    """Operational failures, priced. This is what turns 'SUP-104 is late' into
    '$3.8M of revenue exposure', which is the difference between an
    operational dashboard and a board slide."""
    f = s.financial
    rows = []

    w = inv[inv["snapshot_grain"] == "W"]
    carry = w.groupby("year_month_key")["inventory_value"].mean() * (
        float(f["inventory_carrying_cost_annual_pct"]) / 12.0)
    rows.append(("Inventory Carrying Cost", carry))

    price = dim_product.set_index("product_id")["standard_price"]
    lost = w.copy()
    lost["lost_value"] = lost["lost_sales_qty"] * lost["product_id"].map(price).fillna(0) * 7
    rows.append(("Stockout Revenue Loss",
                 lost.groupby("year_month_key")["lost_value"].sum()))

    exp = shipments[shipments["is_expedited"] == 1]
    prem = 1 - 1 / float(f["expedite_freight_premium"])
    rows.append(("Expedite Cost",
                 exp.groupby("year_month_key")["freight_cost"].sum() * prem))
    rows.append(("Freight Cost",
                 shipments.groupby("year_month_key")["freight_cost"].sum()))
    rows.append(("Quality Cost",
                 deliveries.groupby("year_month_key")["quality_cost"].sum()))

    late = deliveries[deliveries["is_on_time"] == 0]
    rows.append(("Supplier Penalty",
                 late.groupby("year_month_key")["receipt_value"].sum()
                 * float(f["supplier_penalty_pct_of_late_value"])))
    rows.append(("Warehousing Cost",
                 w.groupby("year_month_key")["on_hand_qty"].mean()
                 * float(f["warehousing_cost_per_unit_month"])))

    out = []
    for name, series in rows:
        t = series.dropna().reset_index()
        t.columns = ["year_month_key", "impact_amount"]
        t["cost_category"] = name
        out.append(t)
    df = pd.concat(out, ignore_index=True)
    df["impact_amount"] = df["impact_amount"].round(2)
    df["year_month_key"] = df["year_month_key"].astype("int32")
    return df[["year_month_key", "cost_category", "impact_amount"]]
