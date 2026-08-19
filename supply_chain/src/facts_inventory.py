"""Daily inventory simulation, emitted at mixed grain.

The balance equation is simulated at DAILY granularity for every stocking pair
so it closes exactly:

    on_hand[t] = on_hand[t-1] + receipts[t] + production[t]
                 - shipped[t] - scrapped[t]

Rows are then EMITTED at weekly grain for history and daily grain for the
trailing window (docs/DATA_MODEL.md section 3.2). Simulating at emit grain
would make the weekly rows an approximation and the drill-down from a stockout
into the receipts that should have prevented it would not reconcile.

`snapshot_grain` distinguishes the two. Summing a measure across mixed grains
is wrong, and the validator asserts every documented query filters on it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_inventory_snapshots(s, dim_product, dim_location, grid,
                              deliveries, production, engine, rng):
    tl = s.timeline
    days = pd.date_range(tl.start_date, tl.as_of_date, freq="D")
    D = len(days)
    day_pos = {d: i for i, d in enumerate(days)}
    n = len(grid)

    pid = grid["product_id"].to_numpy()
    lid = grid["location_id"].to_numpy()
    pair_key = {(p, l): i for i, (p, l) in enumerate(zip(pid, lid))}

    # ---- inbound: receipts and production, by pair and day ----------------
    receipts = np.zeros((n, D), dtype="float32")
    for src, qty_col, date_col in (
            (deliveries, "accepted_qty", "actual_receipt_date"),
            (production, "completed_qty", "completion_date")):   # production lands at its destination DC
        if src is None or src.empty:
            continue
        loc_col = ("destination_location_id" if "destination_location_id" in src.columns
                   else "location_id")
        d = src[["product_id", loc_col, qty_col, date_col]].dropna()
        d = d.rename(columns={loc_col: "location_id"})
        keys = [pair_key.get((p, l), -1)
                for p, l in zip(d["product_id"].to_numpy(), d["location_id"].to_numpy())]
        keys = np.asarray(keys)
        dpos = pd.to_datetime(d[date_col]).dt.normalize().map(day_pos).to_numpy()
        ok = (keys >= 0) & pd.notna(dpos)
        if ok.any():
            np.add.at(receipts, (keys[ok], dpos[ok].astype(int)),
                      d[qty_col].to_numpy()[ok].astype("float32"))

    # ---- demand: regional weekly signal allocated down to the pair --------
    annual = dim_product.set_index("product_id")["annual_demand_qty"]
    base_daily = ((grid["product_id"].map(annual).fillna(0).to_numpy() / 365.0)
                  * grid["demand_share"].to_numpy())

    seas = np.array(s.baseline["seasonality"], dtype=float)[days.month.to_numpy() - 1]
    wd = np.array(s.baseline["weekday_weights"], dtype=float)[days.dayofweek.to_numpy()]
    growth = (1 + float(s.baseline["underlying_demand_growth_yoy"])) ** (
        (days - pd.Timestamp(tl.start_date)).days.to_numpy() / 365.25)

    # Normalise the profile to mean 1 over the horizon. annual_demand_qty is
    # measured on the TRAILING 12 MONTHS, so it already contains the growth to
    # date; multiplying by an unnormalised growth curve on top of it inflates
    # total demand ~8% above the supply that was sized from the same figure,
    # and every pair runs a permanent structural deficit.
    profile = seas * wd * growth
    profile = profile / profile.mean()

    mpos = engine.month_pos(pd.Series(days))
    dmult = engine.demand_mult[pid - 1][:, mpos]
    lpos = np.array([{l: i for i, l in enumerate(dim_location["location_id"])}[x] for x in lid])
    pick_cap = engine.location_pick_capacity[lpos][:, mpos]
    open_mask = engine.location_open[lpos][:, mpos]

    demand = (base_daily[:, None]
              * profile[None, :]
              * dmult
              * rng.gamma(5.0, 1 / 5.0, size=(n, D))).astype("float32")

    # ---- planning parameters, scaled to the pair's share ------------------
    ss_days = grid["product_id"].map(
        dim_product.set_index("product_id")["safety_stock_days"]).fillna(7).to_numpy()
    lt_days = grid["product_id"].map(
        dim_product.set_index("product_id")["lead_time_days"]).fillna(14).to_numpy()
    ss_mult = engine.safety_stock_mult[pid - 1][:, mpos]
    unit_cost = grid["product_id"].map(
        dim_product.set_index("product_id")["unit_cost"]).fillna(1.0).to_numpy()

    # ---- emit schedule ----------------------------------------------------
    weekly_days = set(np.flatnonzero(days.dayofweek.to_numpy() == 0).tolist())
    daily_from = D - int(s.inventory["daily_window_days"])
    emit_at = [t for t in range(D) if t in weekly_days or t >= daily_from]
    grain = {t: ("D" if t >= daily_from else "W") for t in emit_at}

    # ---- the simulation ---------------------------------------------------
    # Open at the planned target cover, not at lead time + safety stock: the
    # latter is the reorder POINT, which is the low-water mark, not the
    # steady-state position.
    on_hand = (base_daily * float(s.inventory["target_days_of_supply"])).astype("float32")
    in_transit = np.zeros(n, dtype="float32")
    backorder = np.zeros(n, dtype="float32")
    out = []

    lost_share = float(s.financial["stockout_revenue_capture_rate"])
    trailing = np.zeros((n, 28), dtype="float32")
    for t in range(D):
        recv = receipts[:, t]
        avail = on_hand + recv
        # Event 13 constrains how much a DC can physically pick.
        pickable = avail * pick_cap[:, t]

        # Backorders are served first, as a real DC would. Current demand gets
        # what is left, and whatever it does not get is this period's shortfall
        # -- tracked separately so fill rate cannot exceed 100% by counting
        # backorder catch-up as if it were current demand served.
        serve_bo = np.minimum(backorder, pickable)
        serve_cur = np.minimum(demand[:, t], pickable - serve_bo)
        unmet = demand[:, t] - serve_cur
        shipped = serve_bo + serve_cur
        # Not all unmet demand waits. `stockout_revenue_capture_rate` is the
        # share that is genuinely lost -- the customer buys elsewhere. Letting
        # 100% of it backorder makes shortfalls compound into a death spiral
        # that no amount of later supply clears.
        backorder = backorder - serve_bo + unmet * (1.0 - lost_share)
        lost_sales = unmet * lost_share
        on_hand = avail - shipped
        trailing[:, t % 28] = demand[:, t]

        if t in grain:
            avg_daily = trailing.mean(axis=1)
            safety = (base_daily * ss_days * ss_mult[:, t]).astype("float32")
            reorder = (base_daily * lt_days + safety).astype("float32")
            dos = np.where(avg_daily > 1e-6, on_hand / np.maximum(avg_daily, 1e-6), np.nan)
            # Allocated to committed customer orders but not yet picked.
            # Deriving this from backorder instead made any lingering
            # backorder zero out available_qty and report a permanent stockout.
            reserved = on_hand * 0.10
            out.append(pd.DataFrame({
                "snapshot_date": days[t],
                "snapshot_grain": grain[t],
                "product_id": pid.astype("int32"),
                "location_id": lid.astype("int32"),
                "on_hand_qty": np.round(on_hand, 3),
                "reserved_qty": np.round(reserved, 3),
                "available_qty": np.round(on_hand - reserved, 3),
                "in_transit_qty": np.round(in_transit, 3),
                "backorder_qty": np.round(backorder, 3),
                "safety_stock_qty": np.round(safety, 3),
                "reorder_point_qty": np.round(reorder, 3),
                "demand_qty": np.round(demand[:, t], 3),
                "shipped_qty": np.round(shipped, 3),
                "served_current_qty": np.round(serve_cur, 3),
                "unmet_qty": np.round(unmet, 3),
                "lost_sales_qty": np.round(lost_sales, 3),
                "receipt_qty": np.round(recv, 3),
                "avg_daily_demand": np.round(avg_daily, 4),
                "inventory_value": np.round(on_hand * unit_cost, 2),
                "days_of_supply": np.round(dos, 2),
                "is_open": open_mask[:, t].astype("int8"),
            }))

    df = pd.concat(out, ignore_index=True)
    df = df[df["is_open"] > 0].drop(columns=["is_open"]).reset_index(drop=True)
    # A stockout is demand that could not be served in the period. Defining it
    # as "available_qty <= 0" counts a pair that ended the day empty but served
    # everyone, and misses a pair that had stock but not enough.
    df["stockout_flag"] = ((df["demand_qty"] > 0)
                           & (df["unmet_qty"] > 1e-6)).astype("int8")
    df["excess_inventory_flag"] = (
        df["days_of_supply"] > float(s.inventory["target_days_of_supply"]) * 2
    ).fillna(False).astype("int8")
    df["below_reorder_flag"] = (df["on_hand_qty"] < df["reorder_point_qty"]).astype("int8")
    df["year_month_key"] = (df["snapshot_date"].dt.year * 100
                            + df["snapshot_date"].dt.month).astype("int32")
    return df
