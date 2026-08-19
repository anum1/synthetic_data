"""Demand signal, and the classifications derived from it.

Generation order matters here (docs/DATA_MODEL.md section 7): demand is
generated first, then ABC/XYZ are COMPUTED from it, then the planning
parameters that depend on the classes. Assigning ABC/XYZ randomly is the
standard way this kind of dataset stops surviving questions -- "which AX
products are at stockout risk" has to return products that really are
high-value and really are predictable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _week_starts(start, end) -> pd.DatetimeIndex:
    return pd.date_range(start=pd.Timestamp(start), end=pd.Timestamp(end), freq="W-MON")


def build_fact_demand_signal(s, dim_product, dim_region, engine, rng) -> pd.DataFrame:
    """Weekly demand by product x region, over history through as-of."""
    weeks = _week_starts(s.timeline.start_date, s.timeline.as_of_date)
    P, W = len(dim_product), len(weeks)
    regions = dim_region["region"].to_numpy()
    region_ids = dim_region["region_id"].to_numpy()
    mix = s.baseline["region_mix"]
    share = np.array([mix.get(r, 0.0) for r in regions], dtype=float)
    share = share / share.sum()

    # Baseline weekly volume per SKU. Heavy right tail so a minority of SKUs
    # carry most of the volume, which is what makes ABC meaningful.
    base = np.exp(rng.normal(3.1, 1.25, P)).clip(0.5, 12_000)

    # Per-SKU demand volatility. This is what XYZ will be derived from, so it
    # needs genuine spread rather than one global noise level.
    cv = np.exp(rng.normal(-0.62, 0.70, P)).clip(0.05, 2.6)

    seas = np.array(s.baseline["seasonality"], dtype=float)
    month_of_week = weeks.month.to_numpy() - 1
    season_w = seas[month_of_week]

    growth = float(s.baseline["underlying_demand_growth_yoy"])
    yrs = (weeks - pd.Timestamp(s.timeline.start_date)).days.to_numpy() / 365.25
    growth_w = (1 + growth) ** yrs

    mpos = engine.month_pos(pd.Series(weeks))          # week -> month column
    dmult = engine.demand_mult[:, mpos]                # (P, W)

    lam = base[:, None] * season_w[None, :] * growth_w[None, :] * dmult
    noise = rng.gamma(shape=1.0 / cv[:, None] ** 2,
                      scale=cv[:, None] ** 2, size=(P, W))
    total = np.clip(lam * noise, 0, None)

    # Split across regions multinomially so region totals stay integral.
    parts = []
    for ri, (rid, rshare) in enumerate(zip(region_ids, share)):
        q = total * rshare
        parts.append(q)
    stack = np.stack(parts, axis=1)                    # (P, R, W)

    pid = np.repeat(dim_product["product_id"].to_numpy(), len(regions) * W)
    rid = np.tile(np.repeat(region_ids, W), P)
    wk = np.tile(np.asarray(weeks), P * len(regions))

    df = pd.DataFrame({
        "week_start_date": wk,
        "product_id": pid.astype("int32"),
        "region_id": rid.astype("int32"),
        "demand_qty": np.round(stack.reshape(-1), 3),
    })
    df["year_month_key"] = (pd.to_datetime(df["week_start_date"]).dt.year * 100
                            + pd.to_datetime(df["week_start_date"]).dt.month).astype("int32")
    df = df[df["demand_qty"] > 0].reset_index(drop=True)
    return df


def derive_abc_xyz(fact_demand: pd.DataFrame, dim_product: pd.DataFrame,
                   s) -> pd.DataFrame:
    """ABC by cumulative trailing-12-month extended value; XYZ by demand CV."""
    as_of = pd.Timestamp(s.timeline.as_of_date)
    window = fact_demand[pd.to_datetime(fact_demand["week_start_date"])
                         > as_of - pd.Timedelta(days=365)]

    by_sku = window.groupby("product_id")["demand_qty"]
    annual = by_sku.sum()
    weekly = window.groupby(["product_id", "week_start_date"])["demand_qty"].sum()
    stats = weekly.groupby("product_id").agg(["mean", "std"])
    cv = (stats["std"] / stats["mean"]).replace([np.inf, -np.inf], np.nan)

    out = dim_product.copy()
    cost = out.set_index("product_id")["unit_cost"]
    value = (annual * cost.reindex(annual.index)).sort_values(ascending=False)
    cum = value.cumsum() / value.sum()

    a_cut, b_cut = s.classification["abc_cumulative_value_cutoffs"]
    abc = pd.Series(np.where(cum <= a_cut, "A", np.where(cum <= b_cut, "B", "C")),
                    index=cum.index)

    x_cut, y_cut = s.classification["xyz_demand_cv_cutoffs"]
    xyz = pd.Series(np.where(cv <= x_cut, "X", np.where(cv <= y_cut, "Y", "Z")),
                    index=cv.index)

    out["abc_class"] = out["product_id"].map(abc).fillna("C")
    out["xyz_class"] = out["product_id"].map(xyz).fillna("Z")
    out["annual_demand_qty"] = out["product_id"].map(annual).fillna(0.0).round(3)
    out["demand_cv"] = out["product_id"].map(cv).fillna(0.0).round(4)
    out["annual_demand_value"] = (out["annual_demand_qty"] * out["unit_cost"]).round(2)
    return out


def set_planning_params(dim_product: pd.DataFrame, dim_supplier: pd.DataFrame,
                        s) -> pd.DataFrame:
    """Planning parameters depend on the derived class, so they come last.

    These are the PLANNED values -- what the system thinks. Actual lead times
    come from fact_supplier_delivery and diverge once the events bite. That gap
    is the supplier-performance story.
    """
    out = dim_product.copy()
    sup_lead = dim_supplier.set_index("supplier_id")["lead_time_days"]
    out["lead_time_days"] = (out["primary_supplier_id"].map(sup_lead)
                             .fillna(14).astype("int32"))

    ss = s.inventory["safety_stock_days"]
    out["safety_stock_days"] = out["abc_class"].map(ss).fillna(7).astype("int32")
    # Volatile demand earns more cover regardless of value class.
    bump = out["xyz_class"].map({"X": 0, "Y": 3, "Z": 7}).fillna(0).astype(int)
    out["safety_stock_days"] = (out["safety_stock_days"] + bump).astype("int32")

    # Exactly one supply path per SKU. Manufactured goods are replenished by
    # production, everything else by purchase order. Feeding a SKU from both
    # makes total receipts exceed demand and inventory grows without bound.
    out["replenishment_source"] = np.where(
        out["product_type"] == "Finished Good", "Production", "Purchase")

    weekly = out["annual_demand_qty"] / 52.0
    out["reorder_point_qty"] = np.round(
        weekly / 7.0 * (out["lead_time_days"] + out["safety_stock_days"]), 3)
    out["target_stock_qty"] = np.round(
        weekly / 7.0 * (out["lead_time_days"] + out["safety_stock_days"]
                        + s.inventory["review_period_days"]), 3)
    return out


def build_stocking_grid(dim_product: pd.DataFrame, dim_location: pd.DataFrame,
                        s, rng) -> pd.DataFrame:
    """The sparse SKU x location pairs that actually carry stock.

    A real DC does not stock every SKU. Breadth is driven by ABC class -- see
    docs/DATA_MODEL.md section 3.1. This is what keeps the snapshot fact at
    ~4.3M rows instead of 66M.
    """
    breadth = s.inventory["stocking_breadth"]
    locs = dim_location["location_id"].to_numpy()
    dcs = dim_location.loc[dim_location["node_type"] != "Plant", "location_id"].to_numpy()
    pool = dcs if dcs.size else locs

    rows_p, rows_l = [], []
    for pid, abc in zip(dim_product["product_id"].to_numpy(),
                        dim_product["abc_class"].to_numpy()):
        k = max(1, int(round(len(pool) * float(breadth.get(abc, 0.10)))))
        chosen = rng.choice(pool, size=min(k, pool.size), replace=False)
        rows_p.append(np.full(chosen.size, pid))
        rows_l.append(chosen)

    grid = pd.DataFrame({
        "product_id": np.concatenate(rows_p).astype("int32"),
        "location_id": np.concatenate(rows_l).astype("int32"),
    })
    return add_demand_share(grid, dim_location, s)


def add_demand_share(grid: pd.DataFrame, dim_location: pd.DataFrame,
                     s) -> pd.DataFrame:
    """Each SKU's demand, split across the locations that stock it.

    This lives on the grid rather than in the inventory module because BOTH
    sides of the balance equation need it: replenishment quantities are sized
    from a pair's share, and demand is consumed from the same share. Deriving
    it twice is how supply ends up several times demand.
    """
    mix = s.baseline["region_mix"]
    loc_region = dim_location.set_index("location_id")["region"]
    g = grid.copy()
    g["region"] = g["location_id"].map(loc_region)
    g["_share"] = g["region"].map(mix).fillna(0.01)
    per_pr = g.groupby(["product_id", "region"])["location_id"].transform("size")
    g["_w"] = g["_share"] / per_pr
    g["demand_share"] = g["_w"] / g.groupby("product_id")["_w"].transform("sum")
    return g.drop(columns=["_share", "_w"])
