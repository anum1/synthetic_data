"""Supporting facts: returns, inventory, budget, forecast, supplier
performance and rep quota.

These are what turn the sales fact from a sales report into an analysis
dataset: they carry the inventory-shortage and quality-failure stories, and
they supply the plan/actual/forecast comparison the planning demos need.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import catalog as cat
from facts import month_range


# ------------------------------------------------------------------ returns --
def build_returns(scenario, lines: pd.DataFrame, product: pd.DataFrame,
                  supplier: pd.DataFrame, events, rng) -> pd.DataFrame:
    """Returns are sampled from real order lines, so every return traces back
    to the sale that produced it."""
    sup_group = dict(zip(supplier["supplier_id"], supplier["supplier_group"]))
    slim = lines[["order_line_id", "order_date", "customer_id", "product_id",
                  "supplier_id", "location_id", "quantity", "net_sales",
                  "year_month_key"]].copy()
    slim["supplier_group"] = slim["supplier_id"].map(sup_group)

    months = sorted(slim["year_month_key"].unique())
    picks = []
    for ym in months:
        block = slim[slim["year_month_key"] == ym]
        month = dt.date(ym // 100, ym % 100, 1)
        rate = events.return_rate(month, block["supplier_group"].to_numpy())
        hit = rng.random(len(block)) < rate
        if hit.any():
            picks.append(block[hit])
    if not picks:
        return pd.DataFrame()

    r = pd.concat(picks, ignore_index=True)
    n = len(r)

    reasons = list(cat.RETURN_REASONS)
    # Quality-failure returns skew hard toward defects; ordinary returns do not.
    q = scenario.event("quality_failure")
    q_window = scenario.event_window("quality_failure")
    in_q = np.zeros(n, dtype=bool)
    if q and q_window:
        month_start = pd.to_datetime(r["order_date"]).dt.to_period("M").dt.start_time.dt.date
        in_q = ((month_start >= q_window[0]) & (month_start <= q_window[1])
                & (r["supplier_group"] == events.quality_group)).to_numpy()

    base_p = np.array([0.12, 0.10, 0.28, 0.08, 0.14, 0.06, 0.12, 0.10])
    defect_p = np.array([0.08, 0.04, 0.08, 0.05, 0.62, 0.02, 0.07, 0.04])
    reason = np.where(in_q,
                      rng.choice(reasons, size=n, p=defect_p / defect_p.sum()),
                      rng.choice(reasons, size=n, p=base_p / base_p.sum()))

    # Returns lag the sale; a configurable slice arrives late enough to land in
    # a later period than the original order.
    lag_days = rng.integers(2, 46, n)
    late = rng.random(n) < float(scenario.baseline["data_quality"].get("late_return_pct", 0))
    lag_days = np.where(late, lag_days + rng.integers(60, 150, n), lag_days)
    return_date = pd.to_datetime(r["order_date"]) + pd.to_timedelta(lag_days, unit="D")
    as_of = pd.Timestamp(scenario.timeline.as_of_date)
    keep = return_date <= as_of
    r, reason, return_date = r[keep].reset_index(drop=True), reason[keep], return_date[keep]
    n = len(r)

    qty = np.maximum((r["quantity"] * rng.uniform(0.3, 1.0, n)).round(), 1).astype("int32")
    unit_value = r["net_sales"] / r["quantity"].clip(lower=1)
    return_amount = (unit_value * qty).round(2)
    condition = rng.choice(["Resellable", "Refurbish", "Scrap", "Return to Supplier"],
                           size=n, p=[0.34, 0.28, 0.20, 0.18])
    refund_rate = np.where(np.isin(condition, ["Scrap", "Return to Supplier"]), 1.0,
                           rng.uniform(0.80, 1.0, n))

    out = pd.DataFrame({
        "return_id": np.arange(1, n + 1, dtype="int64"),
        "order_line_id": r["order_line_id"].to_numpy(),
        "return_date": return_date.dt.date.to_numpy(),
        "date_key": return_date.dt.strftime("%Y%m%d").astype("int32").to_numpy(),
        "year_month_key": (return_date.dt.year * 100 + return_date.dt.month)
                          .astype("int32").to_numpy(),
        "order_date": r["order_date"].to_numpy(),
        "customer_id": r["customer_id"].to_numpy(),
        "product_id": r["product_id"].to_numpy(),
        "supplier_id": r["supplier_id"].to_numpy(),
        "location_id": r["location_id"].to_numpy(),
        "return_quantity": qty,
        "return_amount": return_amount.to_numpy(),
        "return_reason": reason,
        "return_category": pd.Series(reason).map(cat.RETURN_REASONS).to_numpy(),
        "product_condition": condition,
        "refund_amount": (return_amount * refund_rate).round(2).to_numpy(),
        "days_to_return": lag_days[keep],
        "is_defect_related": (pd.Series(reason).isin(["Product Defect", "Damaged"]))
                             .astype("int8").to_numpy(),
    })
    return out


# ---------------------------------------------------------------- inventory --
def build_inventory(scenario, lines: pd.DataFrame, product: pd.DataFrame,
                    location: pd.DataFrame, events, rng) -> pd.DataFrame:
    """Weekly snapshots for stocked SKUs at stocking locations.

    Carries the inventory-shortage story: demand rises while on-hand falls,
    so the sales shortfall is explained by availability, not by demand.
    """
    t = scenario.timeline
    stocking = location[location["location_type"].isin(
        ["Distribution Center", "Warehouse", "Retail Store"])]
    # Keep the snapshot table to a sane size: top locations x stocked SKUs.
    n_locs = int(scenario.sizes.get("inventory_locations", 20))
    n_skus = int(scenario.sizes.get("inventory_skus", 100))
    # Choose the busiest locations and SKUs, not the lowest ids. A grid built
    # from arbitrary pairs has fractional weekly demand, which makes stockouts
    # and days-of-supply meaningless.
    vol_loc = lines.groupby("location_id")["quantity"].sum()
    vol_sku = lines.groupby("product_id")["quantity"].sum()
    locs = (vol_loc[vol_loc.index.isin(stocking["location_id"])]
            .nlargest(n_locs).index.to_numpy())
    phys = product[product["category"] != "Software & Services"]["product_id"]
    skus = vol_sku[vol_sku.index.isin(phys)].nlargest(n_skus).index.to_numpy()
    # The shortage SKUs must be in the grid or the event has nowhere to show up.
    forced = np.array(sorted(events.shortage_skus), dtype=skus.dtype)
    skus = np.unique(np.concatenate([skus, forced])) if len(forced) else skus
    if len(locs) == 0 or len(skus) == 0:
        return pd.DataFrame()

    weeks = pd.date_range(t.start_date, t.as_of_date, freq="W-MON")
    cost_by_p = dict(zip(product["product_id"], product["standard_cost"]))

    # Observed weekly demand per (location, product) anchors the simulation.
    sold = (lines[lines["location_id"].isin(locs) & lines["product_id"].isin(skus)]
            .groupby(["location_id", "product_id"])["quantity"].sum())
    n_weeks = max(len(weeks), 1)
    base_demand = (sold / n_weeks).to_dict()

    shortage_cfg = scenario.event("inventory_shortage")
    shortage_window = scenario.event_window("inventory_shortage")
    shortage_skus = events.shortage_skus

    grid = [(l, p) for l in locs for p in skus if (l, p) in base_demand]
    if not grid:
        grid = [(int(locs[0]), int(p)) for p in skus[:40]]
    grid_loc = np.array([g[0] for g in grid])
    grid_prod = np.array([g[1] for g in grid])
    k = len(grid)

    demand = np.array([max(float(base_demand.get(g, 0.6)), 0.35) for g in grid])
    unit_cost = np.array([float(cost_by_p.get(p, 100.0)) for p in grid_prod])
    on_hand = demand * rng.uniform(4.0, 9.0, k)

    shortage_mask = np.isin(grid_prod, list(shortage_skus)) if shortage_skus \
        else np.zeros(k, dtype=bool)
    inv_change = float(shortage_cfg["inventory_change"]) if shortage_cfg else 0.0
    dem_change = float(shortage_cfg["demand_change"]) if shortage_cfg else 0.0

    # One vectorised pass per week across the whole grid; the per-pair Python
    # loop this replaces was the dominant cost of the whole generator.
    frames = []
    for w in weeks:
        wd = w.date()
        month_start = wd.replace(day=1)
        in_shortage = shortage_mask & bool(
            shortage_window and shortage_window[0] <= month_start <= shortage_window[1])

        week_demand = demand * rng.uniform(0.6, 1.45, k)
        week_demand = np.where(in_shortage, week_demand * (1 + dem_change), week_demand)

        opening = on_hand
        # Normal replenishment tops the location back up to ~6 weeks of cover.
        received = np.maximum(demand * 6.0 - opening, 0.0) * rng.uniform(0.5, 1.0, k)
        # A shortage is a SUPPLY constraint: the supplier ships only a fraction
        # of what is being sold, so stock draws down week over week. Capping the
        # reorder target instead would let replenishment self-correct and no
        # stockout would ever occur.
        supply_cap = demand * (1 + inv_change) * rng.uniform(0.85, 1.0, k)
        received = np.where(in_shortage, np.minimum(received, supply_cap), received)
        available = opening + received
        sold_qty = np.minimum(week_demand, available)
        lost = np.maximum(week_demand - available, 0.0)
        ending = np.maximum(available - sold_qty, 0.0)
        on_hand = ending
        reserved = ending * rng.uniform(0.03, 0.16, k)

        frames.append(pd.DataFrame({
            "snapshot_date": wd, "location_id": grid_loc, "product_id": grid_prod,
            "opening_inventory": opening.round(), "received_quantity": received.round(),
            "sold_quantity": sold_qty.round(), "ending_inventory": ending.round(),
            "reserved_quantity": reserved.round(),
            "available_inventory": np.maximum(ending - reserved, 0).round(),
            "inventory_value": (ending * unit_cost).round(2),
            "stockout_flag": (lost > 0.01).astype("int8"),
            "lost_sales_units": lost.round(2),
            "days_of_supply": (ending / np.maximum(demand, 0.01)).round(1),
        }))

    inv = pd.concat(frames, ignore_index=True)
    inv["days_of_supply"] = (inv["days_of_supply"] * 7).round(1)
    d = pd.to_datetime(inv["snapshot_date"])
    inv["date_key"] = d.dt.strftime("%Y%m%d").astype("int32")
    inv["year_month_key"] = (d.dt.year * 100 + d.dt.month).astype("int32")
    inv["is_below_safety_stock"] = (inv["days_of_supply"] < 14).astype("int8")
    return inv


# ------------------------------------------------------- supplier performance --
def build_supplier_performance(scenario, lines: pd.DataFrame, product: pd.DataFrame,
                               supplier: pd.DataFrame, events, rng) -> pd.DataFrame:
    """Monthly supplier scorecard, aligned to the cost and quality events."""
    sup_group = dict(zip(supplier["supplier_id"], supplier["supplier_group"]))
    base_lead = dict(zip(supplier["supplier_id"], supplier["default_lead_time_days"]))
    base_quality = dict(zip(supplier["supplier_id"], supplier["quality_rating"]))

    g = (lines.groupby(["year_month_key", "supplier_id", "product_id"])
         .agg(units_ordered=("quantity", "sum"), orders=("order_id", "nunique"),
              supplier_cost=("cost", "sum")).reset_index())
    if g.empty:
        return g
    # Cap the table size by keeping the meaningful supplier-product pairs.
    g = g[g["units_ordered"] >= 3].reset_index(drop=True)
    n = len(g)

    g["supplier_group"] = g["supplier_id"].map(sup_group)
    months = pd.to_datetime(g["year_month_key"].astype(str) + "01", format="%Y%m%d").dt.date

    defect = np.empty(n)
    for ym, idx in g.groupby("year_month_key").groups.items():
        i = np.asarray(idx)
        month = dt.date(ym // 100, ym % 100, 1)
        defect[i] = events.defect_rate(month, g.loc[i, "supplier_group"].to_numpy())
    defect = defect * rng.uniform(0.75, 1.3, n)

    units_received = (g["units_ordered"] * rng.uniform(0.94, 1.0, n)).round().astype("int64")
    units_defective = (units_received * defect).round().astype("int64")

    lead = np.array([base_lead.get(s, 21) for s in g["supplier_id"]], dtype=float)
    lead = lead * rng.normal(1.0, 0.14, n).clip(0.7, 1.6)
    # Late delivery correlates with defects: a struggling supplier struggles broadly.
    on_time_rate = np.clip(rng.normal(0.93, 0.06, n) - defect * 1.8, 0.35, 1.0)
    on_time = (g["orders"] * on_time_rate).round().astype("int64")

    q_base = np.array([base_quality.get(s, 88.0) for s in g["supplier_id"]])
    quality_score = np.clip(q_base - defect * 320, 20, 100).round(1)
    delivery_score = (on_time_rate * 100).round(1)
    lead_penalty = np.clip((lead - 21) * 0.4, -8, 12)

    prev_cost = g.groupby(["supplier_id", "product_id"])["supplier_cost"].shift(1)
    prev_units = g.groupby(["supplier_id", "product_id"])["units_ordered"].shift(1)
    unit_cost = g["supplier_cost"] / g["units_ordered"].clip(lower=1)
    prev_unit_cost = prev_cost / prev_units.clip(lower=1)

    out = pd.DataFrame({
        "year_month_key": g["year_month_key"].astype("int32"),
        "month_start_date": months,
        "supplier_id": g["supplier_id"].astype("int32"),
        "product_id": g["product_id"].astype("int32"),
        "orders": g["orders"].astype("int32"),
        "units_ordered": g["units_ordered"].astype("int64"),
        "units_received": units_received,
        "units_defective": units_defective,
        "defect_rate": defect.round(5),
        "on_time_deliveries": on_time,
        "late_deliveries": (g["orders"] - on_time).clip(lower=0).astype("int64"),
        "average_lead_time_days": lead.round(1),
        "supplier_cost": g["supplier_cost"].round(2),
        "unit_cost": unit_cost.round(4),
        "cost_change_pct": ((unit_cost / prev_unit_cost) - 1).round(5),
        "quality_score": quality_score,
        "delivery_score": delivery_score,
    })
    out["supplier_score"] = (out["quality_score"] * 0.45
                             + out["delivery_score"] * 0.45
                             - lead_penalty).round(1).clip(0, 100)
    return out


# ------------------------------------------------------- budget & forecast ---
def _plan_grain(lines: pd.DataFrame, product: pd.DataFrame,
                location: pd.DataFrame, channel: pd.DataFrame) -> pd.DataFrame:
    """Actuals aggregated to the planning grain: month x region x category x
    subcategory x channel. Budget and forecast join to the same conformed keys,
    which is what keeps the star usable in Power BI without a bridge table."""
    # The line fact already carries country_id / product_category_id, so only
    # the descriptive attributes need to come from the dimensions.
    j = (lines.merge(product[["product_id", "category", "subcategory"]], on="product_id")
              .merge(location[["location_id", "region", "country"]], on="location_id")
              .merge(channel[["channel_id", "sales_channel"]], on="channel_id",
                     suffixes=("", "_dim")))
    return (j.groupby(["year_month_key", "country_id", "region", "country",
                       "product_category_id", "category", "subcategory",
                       "channel_id", "sales_channel"])
             .agg(sales=("net_sales", "sum"), quantity=("quantity", "sum"),
                  cost=("cost", "sum"), profit=("gross_profit", "sum"))
             .reset_index())


def _first_event_month(scenario) -> int | None:
    """YYYYMM of the earliest enabled event, i.e. the last month the plan could
    have been written without knowing anything had gone wrong."""
    starts = []
    for name, key in (("supplier_cost_shock", "start_offset"),
                      ("promotion_surge", "start_offset"),
                      ("product_launch", "launch_offset"),
                      ("region_margin_erosion", "start_offset"),
                      ("customer_contraction", "start_offset"),
                      ("inventory_shortage", "start_offset"),
                      ("quality_failure", "start_offset")):
        m = scenario.event_month(name, key)
        if m:
            starts.append(m.year * 100 + m.month)
    return min(starts) if starts else None


def build_budget(scenario, actuals: pd.DataFrame, rng) -> pd.DataFrame:
    """Budget is set before the year starts, so it knows nothing about the
    events. That gap is exactly what the variance dashboards visualise."""
    t = scenario.timeline
    horizon = month_range(t.start_date, t.end_date)
    ym_keys = [m.year * 100 + m.month for m in horizon]

    # Base the plan on PRE-EVENT actuals only. Averaging over the whole period
    # would fold the events back into the budget, and every region would then
    # miss plan by the same percentage - a variance dashboard with nothing on it.
    cutoff = _first_event_month(scenario)
    baseline = actuals[actuals["year_month_key"] < cutoff] if cutoff else actuals
    if baseline.empty:
        baseline = actuals

    grain = (baseline.groupby(["country_id", "region", "country",
                               "product_category_id", "category", "subcategory",
                               "channel_id", "sales_channel"])
             .agg(sales=("sales", "mean"), quantity=("quantity", "mean"),
                  cost=("cost", "mean"), profit=("profit", "mean")).reset_index())

    seasonality = np.asarray(scenario.baseline["seasonality"], dtype=float)
    growth = 0.09          # the plan assumes a healthy year
    rows = []
    base_year = horizon[0].year
    for m, ym in zip(horizon, ym_keys):
        years = (m.year - base_year) + (m.month - 1) / 12.0
        f = seasonality[m.month - 1] * (1 + growth) ** years
        n = len(grain)
        jitter = rng.normal(1.0, 0.05, n).clip(0.85, 1.15)
        sales = grain["sales"].to_numpy() * f * jitter
        cost = grain["cost"].to_numpy() * f * jitter * rng.normal(0.985, 0.02, n)
        rows.append(pd.DataFrame({
            "year_month_key": np.int32(ym), "budget_month": m,
            "country_id": grain["country_id"], "region": grain["region"],
            "country": grain["country"],
            "product_category_id": grain["product_category_id"],
            "category": grain["category"], "subcategory": grain["subcategory"],
            "channel_id": grain["channel_id"], "sales_channel": grain["sales_channel"],
            "budget_sales": sales.round(2),
            "budget_quantity": (grain["quantity"].to_numpy() * f * jitter).round().astype("int64"),
            "budget_cost": cost.round(2),
        }))
    b = pd.concat(rows, ignore_index=True)
    b["budget_profit"] = (b["budget_sales"] - b["budget_cost"]).round(2)
    b["budget_margin_pct"] = (b["budget_profit"] / b["budget_sales"].replace(0, np.nan)).round(6)
    return b


def build_forecast(scenario, actuals: pd.DataFrame, budget: pd.DataFrame,
                   rng) -> pd.DataFrame:
    """Four forecast versions. Later versions see more of the events, so the
    walk from Original Budget to Latest Forecast tells the deterioration story
    and the recovery scenario tells the what-if story."""
    t = scenario.timeline
    as_of_key = t.as_of_date.year * 100 + t.as_of_date.month

    det = scenario.event("forecast_deterioration")
    det_start = scenario.event_month("forecast_deterioration", "start_offset")
    rec = scenario.event("recovery_scenario")
    rec_start = scenario.event_month("recovery_scenario", "start_offset")

    versions = [
        ("Original Budget", 0.00, 0.00, None),
        ("Forecast v1", -0.01, -0.02, None),
        ("Forecast v2", -0.03, -0.09, None),
        ("Latest Forecast", None, None, "deteriorated"),
        ("Recovery Scenario", None, None, "recovery"),
    ]

    fut = budget[budget["year_month_key"] > as_of_key].copy()
    if fut.empty:
        return pd.DataFrame()

    total_sales = fut["budget_sales"].sum()
    total_profit = fut["budget_profit"].sum()
    rev_short = float(det["revenue_shortfall"]) if det else 0.0
    prof_short = float(det["profit_shortfall"]) if det else 0.0
    prof_recover = float(rec["profit_recovery"]) if rec else 0.0

    out = []
    for version, rev_adj, prof_adj, mode in versions:
        f = fut.copy()
        n = len(f)
        if mode == "deteriorated":
            # Shortfalls land only from the deterioration month onward.
            hit = f["budget_month"] >= det_start if det_start else np.ones(n, dtype=bool)
            share = f["budget_sales"].where(hit, 0)
            share = share / share.sum() if share.sum() else 0
            f["forecast_sales"] = f["budget_sales"] - share * rev_short
            f["forecast_profit"] = f["budget_profit"] - share * prof_short
        elif mode == "recovery":
            hit = f["budget_month"] >= det_start if det_start else np.ones(n, dtype=bool)
            share = f["budget_sales"].where(hit, 0)
            share = share / share.sum() if share.sum() else 0
            rhit = f["budget_month"] >= rec_start if rec_start else np.zeros(n, dtype=bool)
            rshare = f["budget_sales"].where(rhit, 0)
            rshare = rshare / rshare.sum() if rshare.sum() else 0
            f["forecast_sales"] = f["budget_sales"] - share * rev_short + rshare * rev_short * 0.45
            f["forecast_profit"] = (f["budget_profit"] - share * prof_short
                                    + rshare * prof_recover)
        else:
            noise = rng.normal(1.0, 0.03, n)
            f["forecast_sales"] = f["budget_sales"] * (1 + rev_adj) * noise
            f["forecast_profit"] = f["budget_profit"] * (1 + prof_adj) * noise

        f["forecast_version"] = version
        f["forecast_cost"] = (f["forecast_sales"] - f["forecast_profit"]).round(2)
        ratio = (f["forecast_sales"] / f["budget_sales"].replace(0, np.nan)).fillna(1)
        f["forecast_quantity"] = (f["budget_quantity"] * ratio).round().astype("int64")
        spread = 0.06 if version != "Original Budget" else 0.03
        f["confidence_low"] = (f["forecast_sales"] * (1 - spread)).round(2)
        f["confidence_high"] = (f["forecast_sales"] * (1 + spread)).round(2)
        out.append(f)

    fc = pd.concat(out, ignore_index=True)
    fc = fc.rename(columns={"budget_month": "forecast_month"})
    fc["forecast_sales"] = fc["forecast_sales"].round(2)
    fc["forecast_profit"] = fc["forecast_profit"].round(2)
    fc["forecast_margin_pct"] = (fc["forecast_profit"]
                                 / fc["forecast_sales"].replace(0, np.nan)).round(6)
    return fc[["year_month_key", "forecast_month", "forecast_version",
               "country_id", "region", "country",
               "product_category_id", "category", "subcategory",
               "channel_id", "sales_channel",
               "forecast_sales", "forecast_quantity", "forecast_cost",
               "forecast_profit", "forecast_margin_pct",
               "confidence_low", "confidence_high"]]


# --------------------------------------------------------------- rep quota ---
def build_rep_quota(scenario, lines: pd.DataFrame, rep: pd.DataFrame,
                    rng) -> pd.DataFrame:
    """Monthly quota per rep, set from prior-year run rate plus a stretch."""
    t = scenario.timeline
    months = month_range(t.start_date, t.as_of_date)
    actual = (lines.groupby(["year_month_key", "sales_rep_id"])["net_sales"]
              .sum().reset_index(name="actual_sales"))
    avg = actual.groupby("sales_rep_id")["actual_sales"].mean()

    seasonality = np.asarray(scenario.baseline["seasonality"], dtype=float)
    rows = []
    for m in months:
        ym = m.year * 100 + m.month
        stretch = rng.normal(1.08, 0.07, len(rep)).clip(0.9, 1.35)
        base = rep["sales_rep_id"].map(avg).fillna(avg.mean() if len(avg) else 0.0)
        rows.append(pd.DataFrame({
            "year_month_key": np.int32(ym), "quota_month": m,
            "sales_rep_id": rep["sales_rep_id"].to_numpy().astype("int32"),
            "sales_region": rep["sales_region"].to_numpy(),
            "quota_amount": (base.to_numpy() * seasonality[m.month - 1] * stretch).round(2),
        }))
    q = pd.concat(rows, ignore_index=True)
    return q.merge(actual, on=["year_month_key", "sales_rep_id"], how="left") \
            .fillna({"actual_sales": 0.0}) \
            .assign(attainment_pct=lambda x: (x["actual_sales"]
                                              / x["quota_amount"].replace(0, np.nan)).round(6))
