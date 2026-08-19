"""Inbound facts: purchase orders, supplier deliveries, production.

The planned/actual split is the whole supplier-performance story, so it is
modelled explicitly:

    requested_date  what the planner asked for
    promised_date   what the supplier committed to
    actual_receipt_date  what happened

Lateness is ALWAYS actual - promised, never actual - requested. A supplier that
always promises late but delivers on its promise is a planning problem, not a
supplier problem, and the data has to let someone discover that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PO_STATUS = ["Open", "Received", "Partially Received", "Cancelled"]


def allocate_counts(n: int, w: np.ndarray) -> np.ndarray:
    """Split `n` lines across pairs by weight, deterministically.

    Sampling line counts multinomially puts real variance on how many orders
    each pair receives -- a pair expecting 7 might draw 3 and then run short
    for the whole horizon, because open-loop replenishment has no feedback to
    correct it. Real replenishment frequency is a planning parameter, so
    allocate by largest remainder and give every pair its expected count.
    """
    exact = n * w
    base = np.floor(exact).astype(np.int64)
    short = n - int(base.sum())
    if short > 0:
        order = np.argsort(-(exact - base))[:short]
        base[order] += 1
    return base


def build_purchase_orders(s, dim_product, dim_supplier, dim_location,
                          stocking_grid, engine, name_variants, rng):
    """PO lines driven by replenishment need, not uniform random sampling."""
    n_target = int(s.sizes["po_lines"])
    tl = s.timeline

    # Only purchased SKUs are replenished by PO; manufactured ones come from
    # production. One supply path per SKU (see demand.set_planning_params).
    pool = stocking_grid.merge(
        dim_product[["product_id", "primary_supplier_id", "annual_demand_qty",
                     "unit_cost", "lead_time_days", "safety_stock_days",
                     "abc_class", "replenishment_source"]],
        on="product_id", how="left")
    pool = pool[pool["replenishment_source"] == "Purchase"].reset_index(drop=True)
    if pool.empty:
        raise ValueError("no purchased SKUs to raise POs for")

    # A pair's own annual demand -- NOT the product's total. Sizing orders from
    # the product total means every location that stocks a SKU orders the whole
    # SKU's demand, and supply ends up a multiple of demand.
    pair_annual = (pool["annual_demand_qty"].fillna(0).to_numpy()
                   * pool["demand_share"].to_numpy())

    # Lines are sampled proportional to sqrt(demand) so that big SKUs get both
    # more orders AND bigger orders, rather than only more of them.
    w = np.sqrt(np.clip(pair_annual, 1e-6, None))
    w = w / w.sum()

    counts = allocate_counts(n_target, w)
    idx = np.repeat(np.arange(len(pool)), counts)
    rng.shuffle(idx)
    n_target = len(idx)
    rows = pool.iloc[idx].reset_index(drop=True)

    span = (tl.as_of_date - tl.start_date).days
    po_date = pd.to_datetime(tl.start_date) + pd.to_timedelta(
        rng.integers(0, max(span, 1), n_target), unit="D")

    mpos = engine.month_pos(pd.Series(po_date))
    sup_pos = rows["primary_supplier_id"].map(
        {sid: i for i, sid in enumerate(dim_supplier["supplier_id"])}).fillna(0).astype(int).to_numpy()

    contracted = dim_supplier.set_index("supplier_id")["lead_time_days"]
    base_lead = rows["primary_supplier_id"].map(contracted).fillna(14).to_numpy(dtype=float)

    # Supplier events act when an order is being FULFILLED, not when it is
    # placed. Looking the event state up by po_date smears a 3-month
    # disruption across the lead time either side of it and dilutes it below
    # the configured severity. Resolve the event on the expected RECEIPT month.
    expected_receipt = po_date + pd.to_timedelta(np.round(base_lead).astype(int), unit="D")
    mpos_r = engine.month_pos(pd.Series(expected_receipt))

    lead_add = engine.supplier_lead_add[sup_pos, mpos_r]

    # Promised absorbs MOST of a disruption -- a supplier under pressure
    # re-commits to a longer date rather than silently missing every PO. The
    # residual is what turns into lateness, which is why on-time falls to 71%
    # instead of to zero.
    promised_days = base_lead + rng.integers(0, 4, n_target) + 0.85 * lead_add

    # Lateness is drawn from the CONFIGURED on-time rate rather than emerging
    # from noise, so the number in the config is the number in the data.
    p_on_time = np.clip(
        float(s.baseline["base_supplier_on_time"]) * engine.supplier_on_time[sup_pos, mpos_r],
        0.02, 0.995)
    late = rng.random(n_target) > p_on_time
    early = -rng.gamma(1.2, 1.2, n_target)
    late_delay = rng.gamma(1.6, 2.4, n_target) + 0.35 * lead_add
    actual_days = np.clip(promised_days + np.where(late, late_delay, early), 1, None)

    requested_date = po_date + pd.to_timedelta(np.round(base_lead).astype(int), unit="D")
    promised_date = po_date + pd.to_timedelta(np.round(promised_days).astype(int), unit="D")
    actual_date = po_date + pd.to_timedelta(np.round(actual_days).astype(int), unit="D")

    # Size each line so that expected total receipts over the horizon equal
    # expected demand: a pair's demand across the span, divided by how many
    # lines that pair is expected to receive. Balance by construction rather
    # than by a tuned fudge factor.
    span_years = max((tl.as_of_date - tl.start_date).days, 1) / 365.0
    row_pair_annual = pair_annual[idx]
    expected_lines = np.clip(counts[idx].astype(float), 1.0, None)
    over = float(s.inventory.get("replenishment_over_order", 1.0))
    ordered = row_pair_annual * span_years / expected_lines * over

    # Events 3 and 8 raise safety stock, and that has to reach the ORDER
    # quantity or inventory never actually moves. But a safety-stock change is
    # a ONE-TIME LEVEL change -- going from 20 to 25 days of cover buys five
    # days of stock, once. Multiplying every subsequent order by 1.25 instead
    # adds 25% to the flow forever, and inventory grows without bound.
    prod_pos = rows["product_id"].to_numpy() - 1
    ss_now = engine.safety_stock_mult[prod_pos, mpos]
    ss_prev = engine.safety_stock_mult[prod_pos, np.maximum(mpos - 1, 0)]
    step = np.clip(ss_now - ss_prev, 0, None)
    ss_days_row = rows["safety_stock_days"].fillna(7).to_numpy(dtype=float)
    # Spread the step across however many orders that pair places that month.
    orders_per_month = np.clip(expected_lines / max(engine.nm, 1), 1e-6, None)
    ordered = ordered + (step * ss_days_row * row_pair_annual / 365.0) / orders_per_month

    # Replenishment is driven by the FORECAST, so a biased forecast produces
    # biased orders. Event 3 over-forecasts slow movers (stock piles up);
    # Event 7 under-forecasts a category (it runs short). Without this the
    # forecast facts and the inventory facts tell unrelated stories.
    bias = engine.forecast_bias[prod_pos, mpos]
    ordered = ordered * np.clip(1.0 + bias, 0.3, 2.0)

    # Forecasts also LAG a decline. When demand drops away (Events 9 and 14)
    # the plan keeps ordering against the old run rate for a while, which is
    # precisely how obsolete stock accumulates. Planners do notice eventually,
    # hence the exponent and the cap rather than full compensation.
    dm = engine.demand_mult[prod_pos, mpos]
    ordered = ordered * np.clip(np.where(dm < 1.0, dm ** -0.7, 1.0), 1.0, 2.2)

    # Centred noise. rng.uniform(0.85, 1.21) has mean 1.03, which is a silent
    # 3% permanent over-supply once it compounds across a 3-year horizon.
    ordered = np.round(np.clip(ordered * rng.uniform(0.87, 1.13, n_target), 1, None), 3)

    # MOQ applies only where it is not absurd relative to the need. A planner
    # will round up to a pallet; they will not buy three times their
    # requirement, they will consolidate or source elsewhere. At a 3x
    # tolerance MOQ alone inflated total purchases by 11%.
    moq = rows["primary_supplier_id"].map(
        dim_supplier.set_index("supplier_id")["minimum_order_qty"]).fillna(0).to_numpy()
    ordered = np.where(moq <= ordered * 1.5, np.maximum(ordered, moq), ordered)

    cost_mult = engine.unit_cost_mult[rows["product_id"].to_numpy() - 1, mpos]  # cost is set at order time
    unit_cost = np.round(rows["unit_cost"].to_numpy() * cost_mult, 2)

    # Capacity constraint from Event 1: the supplier simply cannot ship it all.
    cap = engine.supplier_capacity[sup_pos, mpos_r]

    dq = s.baseline["data_quality"]
    u = rng.random(n_target)
    cancelled = u < dq["cancelled_po_line_pct"]
    partial = (~cancelled) & (u < dq["cancelled_po_line_pct"] + dq["partial_receipt_pct"])

    received = ordered * cap
    received = np.where(partial, received * rng.uniform(0.35, 0.9, n_target), received)
    received = np.where(cancelled, 0.0, received)
    received = np.round(np.clip(received, 0, ordered), 3)

    open_mask = actual_date > pd.Timestamp(tl.as_of_date)
    received = np.where(open_mask, 0.0, received)

    status = np.where(cancelled, "Cancelled",
             np.where(open_mask, "Open",
             np.where(received < ordered - 1e-9, "Partially Received", "Received")))

    # Suppliers with messy name spellings stamp a RAW name per transaction.
    sup_ids = rows["primary_supplier_id"].to_numpy()
    clean_name = dim_supplier.set_index("supplier_id")["supplier_name_clean"]
    raw = rows["primary_supplier_id"].map(clean_name).to_numpy(dtype=object)
    for sid, spellings in name_variants.items():
        m = sup_ids == sid
        if m.any():
            raw[m] = rng.choice(np.array(spellings, dtype=object), m.sum())

    df = pd.DataFrame({
        "po_line_id": np.arange(1, n_target + 1, dtype="int64"),
        "po_id": (np.arange(n_target) // rng.integers(
            *s.baseline["lines_per_po"]) + 1).astype("int64"),
        "po_date": po_date,
        "supplier_id": sup_ids.astype("int32"),
        "supplier_name_raw": raw,
        "product_id": rows["product_id"].to_numpy().astype("int32"),
        "location_id": rows["location_id"].to_numpy().astype("int32"),
        "ordered_qty": ordered,
        "unit_cost": unit_cost,
        "po_line_value": np.round(ordered * unit_cost, 2),
        "requested_date": requested_date,
        "promised_date": promised_date,
        "actual_receipt_date": pd.Series(actual_date).where(~(cancelled | open_mask)),
        "received_qty": received,
        "cancelled_qty": np.round(np.where(cancelled, ordered, 0.0), 3),
        "status": status,
        "planned_lead_time_days": np.round(promised_days).astype("int32"),
        "actual_lead_time_days": np.where(cancelled | open_mask, np.nan,
                                          np.round(actual_days)),
        "is_late": np.where(cancelled | open_mask, 0,
                            (actual_date > promised_date).astype("int8")),
        "is_expedited": (rng.random(n_target)
                         < 0.04 * engine.expedite_mult[mpos]).astype("int8"),
    })
    df["year_month_key"] = (df["po_date"].dt.year * 100 + df["po_date"].dt.month).astype("int32")
    # The month the supplier events were resolved on -- the month the order was
    # expected to be FULFILLED. Emitting it means analysis groups on the same
    # basis the model applied, instead of approximating it from po_date or
    # promised_date and reading back a diluted number.
    _er = pd.DatetimeIndex(expected_receipt)
    df["fulfilment_month_key"] = (_er.year * 100 + _er.month).astype("int32")

    # Duplicate POs: identical content, new id. Deliberate dirt.
    ndup = int(dq["duplicate_po_count"])
    if ndup > 0:
        dup = df.sample(n=min(ndup, len(df)), random_state=int(s.seed)).copy()
        dup["po_line_id"] = np.arange(len(df) + 1, len(df) + len(dup) + 1)
        df = pd.concat([df, dup], ignore_index=True)
    return df


def build_supplier_deliveries(s, po: pd.DataFrame, dim_supplier, engine, rng):
    """One receipt line per PO line that actually received something."""
    rec = po[po["received_qty"] > 0].copy()
    n = len(rec)
    mpos = engine.month_pos(rec["actual_receipt_date"])
    sup_pos = rec["supplier_id"].map(
        {sid: i for i, sid in enumerate(dim_supplier["supplier_id"])}).fillna(0).astype(int).to_numpy()

    base_defect = float(s.baseline["base_defect_rate"])
    override = engine.supplier_defect_abs[sup_pos, mpos]
    defect_rate = np.where(override > 0, override, base_defect)
    defect_rate = np.clip(defect_rate * rng.uniform(0.7, 1.3, n), 0, 0.35)

    rejected = np.round(rec["received_qty"].to_numpy() * defect_rate, 3)
    accepted = np.round(rec["received_qty"].to_numpy() - rejected, 3)

    out = pd.DataFrame({
        "delivery_id": np.arange(1, n + 1, dtype="int64"),
        "po_line_id": rec["po_line_id"].to_numpy(),
        "supplier_id": rec["supplier_id"].to_numpy(),
        "supplier_name_raw": rec["supplier_name_raw"].to_numpy(),
        "product_id": rec["product_id"].to_numpy(),
        "location_id": rec["location_id"].to_numpy(),
        "promised_date": rec["promised_date"].to_numpy(),
        "actual_receipt_date": rec["actual_receipt_date"].to_numpy(),
        "received_qty": rec["received_qty"].to_numpy(),
        "accepted_qty": accepted,
        "rejected_qty": rejected,
        "defect_rate": np.round(defect_rate, 5),
        "delay_days": (rec["actual_receipt_date"] - rec["promised_date"]).dt.days.to_numpy(),
        "is_on_time": (rec["actual_receipt_date"] <= rec["promised_date"]).astype("int8").to_numpy(),
        "unit_cost": rec["unit_cost"].to_numpy(),
        "fulfilment_month_key": rec["fulfilment_month_key"].to_numpy(),
    })
    out["receipt_value"] = np.round(out["accepted_qty"] * out["unit_cost"], 2)
    out["quality_cost"] = np.round(
        out["rejected_qty"] * float(s.financial["quality_cost_per_defective_unit"]), 2)
    out["year_month_key"] = (pd.to_datetime(out["actual_receipt_date"]).dt.year * 100
                             + pd.to_datetime(out["actual_receipt_date"]).dt.month).astype("int32")
    return out


def build_production(s, dim_product, dim_location, stocking_grid, engine, rng):
    """Work-order completions for manufactured SKUs.

    Output is routed to a DC that actually stocks the SKU, so it lands on the
    same grid the inventory simulation runs on. Production completing into a
    plant that stocks nothing would silently vanish from the balance equation.
    """
    n = int(s.sizes["production_orders"])
    tl = s.timeline

    pool = stocking_grid.merge(
        dim_product[["product_id", "annual_demand_qty", "unit_cost",
                     "replenishment_source"]],
        on="product_id", how="left")
    pool = pool[pool["replenishment_source"] == "Production"].reset_index(drop=True)
    if pool.empty:
        return pd.DataFrame(columns=["production_id", "product_id", "location_id",
                                     "destination_location_id", "start_date",
                                     "completion_date", "planned_qty",
                                     "completed_qty", "scrap_qty", "yield_pct",
                                     "production_cost", "year_month_key"])

    pair_annual = (pool["annual_demand_qty"].fillna(0).to_numpy()
                   * pool["demand_share"].to_numpy())
    w = np.sqrt(np.clip(pair_annual, 1e-6, None))
    w = w / w.sum()
    counts = allocate_counts(n, w)
    idx = np.repeat(np.arange(len(pool)), counts)
    rng.shuffle(idx)
    n = len(idx)
    rows = pool.iloc[idx].reset_index(drop=True)

    plants = dim_location.loc[dim_location["is_plant"] == 1]
    if plants.empty:
        plants = dim_location.head(1)
    loc_region = dim_location.set_index("location_id")["region"]
    plant_by_region = {r: g["location_id"].to_numpy()
                       for r, g in plants.groupby("region", observed=True)}
    all_plants = plants["location_id"].to_numpy()
    dest_region = rows["location_id"].map(loc_region).to_numpy()
    plant_id = np.array([rng.choice(plant_by_region.get(r, all_plants))
                         for r in dest_region], dtype="int32")

    span = (tl.as_of_date - tl.start_date).days
    start = pd.to_datetime(tl.start_date) + pd.to_timedelta(
        rng.integers(0, max(span, 1), n), unit="D")
    end = start + pd.to_timedelta(rng.integers(1, 9, n), unit="D")

    span_years = max(span, 1) / 365.0
    expected_runs = np.clip(counts[idx].astype(float), 1.0, None)
    # Production only loses scrap (~3%), not the cancellations and short
    # receipts a PO loses, so it must NOT use the purchase-side gross-up.
    over = 1.0 / 0.969
    planned = pair_annual[idx] * span_years / expected_runs * over
    planned = np.round(np.clip(planned * rng.uniform(0.87, 1.13, n), 1, None), 3)

    yield_pct = np.clip(rng.normal(0.972, 0.03, n), 0.70, 1.0)
    completed = np.round(planned * yield_pct, 3)

    df = pd.DataFrame({
        "production_id": np.arange(1, n + 1, dtype="int64"),
        "product_id": rows["product_id"].to_numpy().astype("int32"),
        "location_id": plant_id,
        "destination_location_id": rows["location_id"].to_numpy().astype("int32"),
        "start_date": start,
        "completion_date": end,
        "planned_qty": planned,
        "completed_qty": completed,
        "scrap_qty": np.round(planned - completed, 3),
        "yield_pct": np.round(yield_pct, 4),
        "production_cost": np.round(completed * rows["unit_cost"].to_numpy() * 0.82, 2),
    })
    df["year_month_key"] = (df["completion_date"].dt.year * 100
                            + df["completion_date"].dt.month).astype("int32")
    return df
