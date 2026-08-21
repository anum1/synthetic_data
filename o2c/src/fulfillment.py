"""Warehouse allocation, available-to-promise, and backorders.

Backorders are not drawn. Every order line is allocated against a finite
monthly supply of its SKU at its warehouse, first come first served, and the
lines that arrive after the supply is gone are short. Event 3 takes 45% of one
warehouse's supply away; Event 11 takes almost all of six high-margin SKUs'
supply away. Neither event tags a single order.

That distinction is the whole point. "Show me orders with more than 20% of
quantity backordered" has to return the same set no matter how the audience
slices it, and a flag stamped on a pre-chosen sample does not survive being
sliced by customer, or by month, or by anything else the room asks for.

Inventory position is emitted MONTHLY, and only for SKU x warehouse pairs that
actually transact. The design note's SKU x warehouse x day grain would be 65.7M
rows at full tier, and no O2C question needs it - allocation needs
available-to-promise at the moment of the decision, which is what this is.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from o2cconfig import Scenario

_DAY = np.timedelta64(1, "D")


def allocate(s: Scenario, orders: pd.DataFrame, lines: pd.DataFrame,
             wh: pd.DataFrame, prod: pd.DataFrame, ep: EventPlan,
             rng: np.random.Generator):
    """Return (order_lines, fact_fulfillment, fact_inventory_position)."""
    f = s.fulfillment
    lines = lines.copy()

    # ---- pick a warehouse: per ORDER, prefer the customer's own region -----
    # Assigning per line would scatter a four-line order across three or four
    # warehouses, which is not how anyone picks an order and would inflate both
    # the fulfilment and shipment counts by a factor of three.
    wh_by_region = {r: g["warehouse_id"].to_numpy() for r, g in wh.groupby("region")}
    all_wh = wh["warehouse_id"].to_numpy()
    o_region = orders["region"].to_numpy()
    n_o = len(orders)
    o_wh = np.empty(n_o, dtype=np.int64)
    for r in np.unique(o_region):
        m = o_region == r
        pool = wh_by_region.get(r, all_wh)
        # 88% ship from in-region, the rest from wherever the stock is. That
        # cross-region tail is what makes "which regions have the longest
        # delivery cycle" a question with more than one cause.
        local = rng.random(int(m.sum())) < 0.88
        o_wh[m] = np.where(local, pool[rng.integers(0, len(pool), int(m.sum()))],
                           all_wh[rng.integers(0, len(all_wh), int(m.sum()))])
    primary = pd.Series(o_wh, index=orders["order_id"].to_numpy())
    warehouse_id = primary.reindex(lines["order_id"]).to_numpy()

    # A minority of ORDERS are sourced from a second warehouse as well - the
    # stock is simply somewhere else. This is one of the two roots of a split
    # shipment, and it has to be decided per order: per line it would scatter
    # almost every multi-line order and the baseline split rate would swamp the
    # event that is supposed to move it.
    dual = rng.random(n_o) < 0.04
    dual_of = pd.Series(dual, index=orders["order_id"].to_numpy())
    line_dual = dual_of.reindex(lines["order_id"]).to_numpy()
    second = line_dual & (rng.random(len(lines)) < 0.40)
    warehouse_id = np.where(second, all_wh[rng.integers(0, len(all_wh), len(lines))],
                            warehouse_id)
    lines["warehouse_id"] = warehouse_id.astype("int32")

    # ---- available to promise, per SKU x warehouse x month ------------------
    od = pd.to_datetime(lines["order_date"]).to_numpy().astype("datetime64[D]")
    month = od.astype("datetime64[M]")
    lines["_month"] = month
    qty = lines["quantity_ordered"].to_numpy().astype(float)

    demand = lines.groupby(["product_id", "warehouse_id", "_month"], sort=False)[
        "quantity_ordered"].sum().reset_index(name="demand_qty")

    # Supply is planned against demand with a margin. A planner who got it
    # exactly right every month would never short anybody, and a planner who
    # drew supply independently of demand would short everybody at random -
    # neither looks like a real distributor.
    # Tuned so that roughly one planning cell in ten runs short, rather than one
    # in five. The difference matters more than it looks: a line is short only
    # if its cell ran out, so a 19% short-cell rate puts half of all multi-line
    # orders into a partial shipment and the baseline swamps Event 8.
    n_g = len(demand)
    factor = 1.0 + rng.normal(0.38, 0.30, n_g)
    factor = np.clip(factor, 0.15, 3.0)

    gm = demand["_month"].to_numpy().astype("datetime64[D]")
    ev = s.event("warehouse_bottleneck")
    if ev is not None and ep.bottleneck_warehouse_id:
        hit = (demand["warehouse_id"].to_numpy() == ep.bottleneck_warehouse_id)
        mult = 1.0 + (float(ev["supply_multiplier"]) - 1.0) * ep.ramp(
            "warehouse_bottleneck", gm)
        factor = np.where(hit, factor * mult, factor)

    ev = s.event("product_shortage")
    if ev is not None and len(ep.shortage_products):
        hit = (np.isin(demand["product_id"].to_numpy(), ep.shortage_products)
               & ep.in_window("product_shortage", gm))
        factor = np.where(hit, factor * 0.22, factor)

    demand["supply_qty"] = np.maximum(0.0, np.round(demand["demand_qty"] * factor))

    # ---- consume the supply in date order ----------------------------------
    lines = lines.sort_values(["product_id", "warehouse_id", "_month",
                              "order_date", "order_line_id"], kind="stable")
    grp = ["product_id", "warehouse_id", "_month"]
    prior = lines.groupby(grp, sort=False)["quantity_ordered"].cumsum().to_numpy() \
        - lines["quantity_ordered"].to_numpy()
    supply = lines[grp].merge(demand[grp + ["supply_qty"]], on=grp,
                              how="left")["supply_qty"].to_numpy()
    remaining = np.maximum(0.0, supply - prior)
    allocated = np.minimum(lines["quantity_ordered"].to_numpy(), remaining)

    # Cancelled orders never consume stock and never backorder.
    cancelled = lines["is_cancelled"].to_numpy() == 1
    held = lines["credit_status"].to_numpy() == "Credit Hold"
    allocated = np.where(cancelled | held, 0.0, allocated)

    lines["quantity_allocated"] = allocated.astype("int64")
    lines["quantity_backordered"] = np.where(
        cancelled | held, 0, lines["quantity_ordered"].to_numpy() - allocated
    ).astype("int64")
    lines["quantity_cancelled"] = np.where(
        cancelled, lines["quantity_ordered"].to_numpy(), 0).astype("int64")

    # ---- warehouse throughput: a queue that carries backlog forward --------
    # Work that misses today's capacity is still there tomorrow. Without the
    # carry-forward a capacity cut can only ever delay a line inside its own
    # day, which caps the damage at a few hours and makes Event 3 invisible on
    # any delivery-performance cut.
    lines["_planned_ship"] = pd.to_datetime(
        lines["order_id"].map(orders.set_index("order_id")["planned_ship_date"])
    ).to_numpy().astype("datetime64[D]")
    lines["_queue_delay_days"] = _queue_delays(s, ep, lines, wh)

    lines = lines.sort_values("order_line_id").reset_index(drop=True)

    # ---- backorder recovery -------------------------------------------------
    blo, bhi = f["backorder_recovery_days"]
    recover = rng.integers(blo, bhi + 1, len(lines))
    has_bo = lines["quantity_backordered"].to_numpy() > 0
    bo_date = pd.to_datetime(lines["order_date"]).to_numpy().astype("datetime64[D]") \
        + recover.astype("timedelta64[D]")
    lines["backorder_expected_date"] = np.where(has_bo, bo_date,
                                                np.datetime64("NaT")).astype("datetime64[D]")

    fulfillment = _build_fulfillment(s, orders, lines, rng)
    inventory = _build_inventory_position(s, demand, lines, prod, wh)
    lines = lines.drop(columns=["_month"])
    return lines, fulfillment, inventory


def _queue_delays(s: Scenario, ep: EventPlan, lines: pd.DataFrame,
                   wh: pd.DataFrame) -> np.ndarray:
    """Days each line waits for warehouse capacity, backlog carried day to day.

    Per warehouse: arrivals meet a daily capacity, whatever does not fit joins a
    backlog, and the wait a line experiences is the backlog ahead of it divided
    by the throughput that will clear it.
    """
    start = np.datetime64(s.timeline.start_date, "D")
    end = np.datetime64(s.timeline.as_of_date, "D")
    n_days = int((end - start) / _DAY) + 1
    day_index = ((lines["_planned_ship"].to_numpy() - start) / _DAY).astype(np.int64)
    day_index = np.clip(day_index, 0, n_days - 1)
    wh_ids = lines["warehouse_id"].to_numpy()

    cap_of = wh.set_index("warehouse_id")["daily_line_capacity"].to_dict()
    ev = s.event("warehouse_bottleneck")
    all_days = start + np.arange(n_days).astype("timedelta64[D]")
    ramp = (ep.ramp("warehouse_bottleneck", all_days) if ev is not None
            else np.zeros(n_days))

    out = np.zeros(len(lines), dtype="int64")
    for w in np.unique(wh_ids):
        m = wh_ids == w
        di = day_index[m]
        arrivals = np.bincount(di, minlength=n_days).astype(float)
        run_rate_all = np.maximum(_trailing_mean(arrivals, 60), 1.0)
        # Floor every warehouse's effective capacity at a little above its own
        # run rate. Configured capacity is drawn per warehouse against the
        # NETWORK average, but load is not evenly spread - at full tier the
        # busiest warehouses carry twice the mean, so a low draw leaves them
        # permanently saturated and the network sprouts queues that no event
        # asked for. The one sustained queue in this network is the planted one.
        cap = np.maximum(float(cap_of.get(int(w), 50)), run_rate_all * 1.20)
        if ev is not None and int(w) == ep.bottleneck_warehouse_id:
            # Expressed against the warehouse's OWN arrival rate, not its
            # configured capacity. Capacity is a random draw per warehouse, so a
            # multiplier on it makes the severity of the event depend on the
            # seed - sometimes a crisis, sometimes nothing.
            run_rate = run_rate_all
            # Headroom against its own run rate: comfortable normally, below
            # water at the end of the ramp. Anchoring to the run rate rather
            # than to the configured capacity means the event bites the same
            # way whatever that warehouse's capacity happened to draw.
            headroom = float(ev.get("pick_headroom_normal", 1.6))
            floor_ = float(ev["pick_capacity_vs_demand"])
            cap = np.minimum(cap, run_rate * (headroom + (floor_ - headroom) * ramp))
        cap = np.maximum(cap, 1.0)

        backlog = np.empty(n_days)
        b = 0.0
        for d in range(n_days):
            backlog[d] = b
            b = max(0.0, b + arrivals[d] - cap[d])
        # A line arriving today waits for the backlog ahead of it to clear.
        wait = np.ceil(backlog / cap)
        out[m] = np.clip(wait[di], 0, 25).astype("int64")
    return out


def _trailing_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Centred-back rolling mean, used as a warehouse's current run rate."""
    c = np.concatenate([[0.0], np.cumsum(x)])
    idx = np.arange(len(x))
    lo = np.maximum(0, idx - window + 1)
    return (c[idx + 1] - c[lo]) / np.maximum(idx - lo + 1, 1)


def _build_fulfillment(s: Scenario, orders: pd.DataFrame, lines: pd.DataFrame,
                       rng: np.random.Generator) -> pd.DataFrame:
    """One row per order x warehouse: the allocation the picker works from."""
    g = lines.groupby(["order_id", "warehouse_id"], sort=True).agg(
        planned_quantity=("quantity_ordered", "sum"),
        fulfilled_quantity=("quantity_allocated", "sum"),
        backordered_quantity=("quantity_backordered", "sum"),
        cancelled_quantity=("quantity_cancelled", "sum"),
        line_count=("order_line_id", "count"),
        queue_delay=("_queue_delay_days", "max"),
        allocated_value=("extended_amount_usd", "sum")).reset_index()

    o = orders.set_index("order_id")
    g["order_date"] = o["order_date"].reindex(g["order_id"]).to_numpy()
    g["planned_ship_date"] = o["planned_ship_date"].reindex(g["order_id"]).to_numpy()
    g["credit_status"] = o["credit_status"].reindex(g["order_id"]).to_numpy()
    g["is_cancelled"] = o["is_cancelled"].reindex(g["order_id"]).to_numpy()

    created = pd.to_datetime(g["order_date"]).to_numpy().astype("datetime64[D]")
    planned = pd.to_datetime(g["planned_ship_date"]).to_numpy().astype("datetime64[D]")
    actual = planned + g["queue_delay"].to_numpy().astype("timedelta64[D]")

    as_of = np.datetime64(s.timeline.as_of_date, "D")
    shipped_any = (g["fulfilled_quantity"].to_numpy() > 0) & (actual <= as_of)

    status = np.full(len(g), "Pending", dtype=object)
    full = g["fulfilled_quantity"].to_numpy() >= g["planned_quantity"].to_numpy()
    part = (g["fulfilled_quantity"].to_numpy() > 0) & ~full
    none = g["fulfilled_quantity"].to_numpy() == 0
    status[shipped_any & full] = "Shipped"
    status[shipped_any & part] = "Partially Shipped"
    status[~shipped_any & full] = "Allocated"
    status[~shipped_any & part] = "Picking"
    status[none] = "Backordered"
    status[g["credit_status"].to_numpy() == "Credit Hold"] = "Pending"
    status[g["is_cancelled"].to_numpy() == 1] = "Cancelled"

    out = pd.DataFrame({
        "fulfillment_id": np.arange(1, len(g) + 1, dtype="int32"),
        "fulfillment_number": [f"FO-{i:07d}" for i in range(1, len(g) + 1)],
        "order_id": g["order_id"].astype("int32"),
        "warehouse_id": g["warehouse_id"].astype("int32"),
        "fulfillment_created_date": created,
        "planned_ship_date": planned,
        "actual_ship_date": np.where(shipped_any, actual, np.datetime64("NaT")
                                     ).astype("datetime64[D]"),
        "planned_quantity": g["planned_quantity"].astype("int64"),
        "fulfilled_quantity": g["fulfilled_quantity"].astype("int64"),
        "backordered_quantity": g["backordered_quantity"].astype("int64"),
        "cancelled_quantity": g["cancelled_quantity"].astype("int64"),
        "line_count": g["line_count"].astype("int16"),
        "allocated_value_usd": g["allocated_value"].round(2),
        "ship_delay_days": g["queue_delay"].astype("int16"),
        "fulfillment_status": status,
    })
    out["fill_rate"] = np.round(
        np.where(out["planned_quantity"] > 0,
                 out["fulfilled_quantity"] / out["planned_quantity"], 1.0), 4)
    out["is_backordered"] = (out["backordered_quantity"] > 0).astype("int8")
    return out


def _build_inventory_position(s: Scenario, demand: pd.DataFrame,
                              lines: pd.DataFrame, prod: pd.DataFrame,
                              wh: pd.DataFrame) -> pd.DataFrame:
    """Monthly SKU x warehouse position, restricted to pairs that transact."""
    d = demand.copy()
    d["month_start_date"] = d["_month"].to_numpy().astype("datetime64[D]")
    consumed = lines.groupby(["product_id", "warehouse_id", "_month"], sort=False)[
        "quantity_allocated"].sum().reset_index(name="allocated_qty")
    d = d.merge(consumed, on=["product_id", "warehouse_id", "_month"], how="left")
    d["allocated_qty"] = d["allocated_qty"].fillna(0.0)

    cost = prod.set_index("product_id")["unit_cost_usd"]
    d["unit_cost_usd"] = cost.reindex(d["product_id"]).to_numpy()
    d["closing_qty"] = np.maximum(0.0, d["supply_qty"] - d["allocated_qty"])
    d["available_to_promise_qty"] = d["closing_qty"]
    d["inventory_value_usd"] = np.round(d["closing_qty"] * d["unit_cost_usd"], 2)
    d["shortfall_qty"] = np.maximum(0.0, d["demand_qty"] - d["supply_qty"])
    d["is_stockout"] = (d["shortfall_qty"] > 0).astype("int8")
    d["fill_rate"] = np.round(np.where(d["demand_qty"] > 0,
                                       d["allocated_qty"] / d["demand_qty"], 1.0), 4)
    d["year_month_key"] = (pd.to_datetime(d["month_start_date"]).dt.year * 100
                           + pd.to_datetime(d["month_start_date"]).dt.month).astype("int32")

    out = d[["product_id", "warehouse_id", "month_start_date", "year_month_key",
             "demand_qty", "supply_qty", "allocated_qty", "closing_qty",
             "available_to_promise_qty", "shortfall_qty", "unit_cost_usd",
             "inventory_value_usd", "is_stockout", "fill_rate"]].copy()
    out.insert(0, "inventory_position_id", np.arange(1, len(out) + 1, dtype="int32"))
    for c in ("demand_qty", "supply_qty", "allocated_qty", "closing_qty",
              "available_to_promise_qty", "shortfall_qty"):
        out[c] = out[c].astype("int64")
    out["product_id"] = out["product_id"].astype("int32")
    out["warehouse_id"] = out["warehouse_id"].astype("int32")
    return out
