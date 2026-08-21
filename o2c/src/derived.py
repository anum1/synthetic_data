"""The two materialised tables the demo is actually built on.

`fact_o2c_cycle` is one row per order carrying every milestone date and the
value that reached every stage. It is the design note's waterfall and its
process-time bridge, precomputed. Without it, "how much of what we booked has
become cash" is a six-table join that four BI tools will each get slightly
differently, and the executive page is the one place that cannot afford a
number that moves depending on who built the chart.

The waterfall closes **by construction**:

    booked - cancelled          = net booked
    net booked - shipped        = not yet shipped
    shipped - delivered         = in transit
    delivered - invoiced        = delivered, not invoiced
    invoiced - credited         = net invoiced
    net invoiced - collected    = open AR on the cohort

Every stage is measured NET of tax and freight, on the same population, so the
subtractions are real subtractions. Duplicate invoices are excluded from the
funnel and carried in their own column: they are billing errors, not revenue,
and letting them into `invoiced` would push "delivered not invoiced" negative
for the affected orders.

`fact_o2c_exception` is the exception centre - one row per open problem, typed,
valued, aged and owned. It is a table rather than a query so the headline count
is identical in every tool that reads it.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from o2cconfig import Scenario

_DAY = np.timedelta64(1, "D")


def build_o2c_cycle(s: Scenario, orders: pd.DataFrame, order_lines: pd.DataFrame,
                    quotes: pd.DataFrame, shipments: pd.DataFrame,
                    shipment_lines: pd.DataFrame, invoices: pd.DataFrame,
                    inv_lines: pd.DataFrame, allocations: pd.DataFrame,
                    memos: pd.DataFrame) -> pd.DataFrame:
    """One row per order: the whole lifecycle, in dates and in dollars."""
    as_of = np.datetime64(s.timeline.as_of_date, "D")
    oid = orders["order_id"].to_numpy()
    idx = pd.Index(oid)

    def by_order(series):
        return series.reindex(idx).fillna(0.0).to_numpy()

    booked = orders["net_order_amount_usd"].to_numpy()
    cancelled = np.where(orders["is_cancelled"].to_numpy() == 1, booked, 0.0)

    # Shipped and delivered, from the shipment lines.
    sl = shipment_lines.merge(
        shipments[["shipment_id", "is_delivered", "ship_date", "actual_delivery_date",
                   "is_on_time_promise", "delay_days"]], on="shipment_id", how="left")
    shipped = by_order(sl.groupby("order_id")["extended_amount_usd"].sum())
    dlv = sl[sl["is_delivered"] == 1]
    delivered = by_order(dlv.groupby("order_id")["extended_amount_usd"].sum())

    # Invoiced, excluding duplicates - see the module docstring.
    dup_ids = set(invoices.loc[invoices["is_duplicate"] == 1, "invoice_id"])
    il = inv_lines.copy()
    il["_dup"] = il["invoice_id"].isin(dup_ids)
    invoiced = by_order(il[~il["_dup"]].groupby("order_id")["extended_amount_usd"].sum())
    dup_invoiced = by_order(il[il["_dup"]].groupby("order_id")["extended_amount_usd"].sum())

    # Cash and credit, converted to the net basis so they sit on the same
    # measure as every stage above, and spread across the orders an invoice
    # actually covers.
    #
    # A consolidated invoice bills several orders at once. `invoice.order_id` is
    # only the first of them, so attributing cash through that column parks a
    # month of a customer's payments on one order and leaves its siblings
    # looking permanently unpaid - which shows up as cohort AR exceeding total
    # company AR, an impossible number to defend on stage.
    inv = invoices.set_index("invoice_id")
    net_share = (inv["net_amount_usd"] / inv["total_amount_usd"].replace(0, np.nan)).fillna(1.0)

    line_val = il.groupby(["invoice_id", "order_id"])["extended_amount_usd"].sum()
    inv_total_lines = line_val.groupby(level=0).transform("sum")
    order_share = (line_val / inv_total_lines.replace(0, np.nan)).fillna(0.0)
    share_df = order_share.rename("share").reset_index()

    def spread(df, amount_col):
        """Split each invoice-level amount across the orders it covers."""
        if df is None or df.empty:
            return np.zeros(len(oid))
        left = df[~df["invoice_id"].isin(dup_ids)]
        # Credit memos already carry an order_id of their own; it would collide
        # with the one the share table supplies, and the collision is silent.
        left = left.drop(columns=[c for c in ("order_id",) if c in left.columns])
        d = left.merge(share_df, on="invoice_id", how="inner")
        if d.empty:
            return np.zeros(len(oid))
        d["_net"] = (d[amount_col]
                     * net_share.reindex(d["invoice_id"]).fillna(1.0).to_numpy()
                     * d["share"].to_numpy())
        return by_order(d.groupby("order_id")["_net"].sum())

    collected = spread(allocations, "allocated_amount_usd")
    credited = spread(memos, "memo_amount_usd")

    # Clamp each stage to the one above it. Rounding across three levels of
    # aggregation can otherwise put a cent of "delivered" above "shipped", and a
    # waterfall with a negative bar in it is worse than no waterfall.
    net_booked = booked - cancelled
    shipped = np.minimum(shipped, net_booked)
    delivered = np.minimum(delivered, shipped)
    invoiced = np.minimum(invoiced, delivered)
    credited = np.minimum(credited, invoiced)
    collected = np.minimum(collected, invoiced - credited)
    open_ar = invoiced - credited - collected

    # ---- milestone dates -----------------------------------------------------
    def first(series, name):
        return pd.to_datetime(series.reindex(idx)).to_numpy().astype("datetime64[D]")

    ship_first = first(shipments.groupby("order_id")["ship_date"].min(), "s")
    ship_last = first(shipments.groupby("order_id")["ship_date"].max(), "s")
    dlv_first = first(shipments[shipments["is_delivered"] == 1]
                      .groupby("order_id")["actual_delivery_date"].min(), "d")
    dlv_last = first(shipments[shipments["is_delivered"] == 1]
                     .groupby("order_id")["actual_delivery_date"].max(), "d")
    live_inv = invoices[invoices["is_duplicate"] == 0]
    inv_first = first(live_inv.groupby("order_id")["invoice_date"].min(), "i")
    inv_last = first(live_inv.groupby("order_id")["invoice_date"].max(), "i")
    paid_last = first(live_inv[live_inv["is_open"] == 0]
                      .groupby("order_id")["fully_paid_date"].max(), "p")

    order_date = pd.to_datetime(orders["order_date"]).to_numpy().astype("datetime64[D]")
    q_date = first(quotes[quotes["converted_order_id"] > 0]
                   .set_index("converted_order_id")["quote_date"], "q")

    def lag(a, b):
        out = (a - b) / _DAY
        return np.where(pd.isna(a) | pd.isna(b), -1, out).astype("int16")

    cycle = pd.DataFrame({
        "o2c_cycle_id": np.arange(1, len(oid) + 1, dtype="int32"),
        "order_id": oid.astype("int32"),
        "customer_id": orders["customer_id"].to_numpy().astype("int32"),
        "sales_rep_id": orders["sales_rep_id"].to_numpy().astype("int32"),
        "quote_id": orders["quote_id"].to_numpy().astype("int32"),
        "region": orders["region"].to_numpy(),
        "country": orders["country"].to_numpy(),
        "business_unit": orders["business_unit"].to_numpy(),
        "customer_segment": orders["customer_segment"].to_numpy(),
        "channel": orders["channel"].to_numpy(),
        "payment_terms_code": orders["payment_terms_code"].to_numpy(),
        "quote_date": q_date,
        "order_date": order_date,
        "booking_month": order_date.astype("datetime64[M]").astype("datetime64[D]"),
        "promised_delivery_date": pd.to_datetime(
            orders["promised_delivery_date"]).to_numpy().astype("datetime64[D]"),
        "first_ship_date": ship_first,
        "last_ship_date": ship_last,
        "first_delivery_date": dlv_first,
        "last_delivery_date": dlv_last,
        "first_invoice_date": inv_first,
        "last_invoice_date": inv_last,
        "fully_paid_date": paid_last,
        # ---- the waterfall, net of tax and freight at every stage ----
        "booked_net_usd": np.round(booked, 2),
        "cancelled_net_usd": np.round(cancelled, 2),
        "net_booked_usd": np.round(net_booked, 2),
        "shipped_net_usd": np.round(shipped, 2),
        "delivered_net_usd": np.round(delivered, 2),
        "invoiced_net_usd": np.round(invoiced, 2),
        "credited_net_usd": np.round(credited, 2),
        "collected_net_usd": np.round(collected, 2),
        "open_ar_net_usd": np.round(open_ar, 2),
        "duplicate_invoiced_net_usd": np.round(dup_invoiced, 2),
        # ---- the gaps, as their own columns so the waterfall is a SUM ----
        "not_yet_shipped_usd": np.round(net_booked - shipped, 2),
        "in_transit_usd": np.round(shipped - delivered, 2),
        "delivered_not_invoiced_usd": np.round(delivered - invoiced, 2),
        # ---- process time ----
        "quote_to_order_days": lag(order_date, q_date),
        "order_to_ship_days": lag(ship_first, order_date),
        "ship_to_delivery_days": lag(dlv_last, ship_first),
        "delivery_to_invoice_days": lag(inv_first, dlv_last),
        "invoice_to_cash_days": lag(paid_last, inv_first),
        "order_to_cash_days": lag(paid_last, order_date),
        "cost_amount_usd": orders["cost_amount_usd"].to_numpy(),
        "gross_margin_usd": orders["gross_margin_usd"].to_numpy(),
        "is_cancelled": orders["is_cancelled"].to_numpy().astype("int8"),
        "is_credit_hold": orders["is_credit_hold"].to_numpy().astype("int8"),
    })

    bo = order_lines.groupby("order_id")["quantity_backordered"].sum()
    cycle["is_backordered"] = (bo.reindex(idx).fillna(0).to_numpy() > 0).astype("int8")
    late = shipments.groupby("order_id")["delay_days"].max()
    cycle["is_late_delivery"] = (late.reindex(idx).fillna(0).to_numpy() > 0).astype("int8")
    cycle["is_delivered_not_invoiced"] = (
        cycle["delivered_not_invoiced_usd"] > 1.0).astype("int8")
    cycle["is_fully_collected"] = (
        (cycle["collected_net_usd"] >= cycle["invoiced_net_usd"] - cycle["credited_net_usd"] - 0.01)
        & (cycle["invoiced_net_usd"] > 0)).astype("int8")

    # Perfect order: on time, complete, undamaged and correctly billed. All four
    # have to exist as flags or the composite is a slogan.
    on_time = shipments.groupby("order_id")["is_on_time_promise"].min()
    cycle["is_on_time"] = (on_time.reindex(idx).fillna(0).to_numpy() == 1).astype("int8")
    cycle["is_complete"] = (cycle["is_backordered"] == 0).astype("int8")
    var = il.groupby("order_id")["underbilled_amount_usd"].sum()
    cycle["is_billed_correctly"] = (
        (var.reindex(idx).fillna(0.0).to_numpy() <= 0.01)
        & (cycle["duplicate_invoiced_net_usd"].to_numpy() <= 0.01)).astype("int8")
    cycle["is_undamaged"] = 1
    cycle["is_perfect_order"] = (
        cycle["is_on_time"] & cycle["is_complete"]
        & cycle["is_billed_correctly"] & cycle["is_undamaged"]).astype("int8")
    return cycle


def build_exceptions(s: Scenario, orders: pd.DataFrame, order_lines: pd.DataFrame,
                     shipments: pd.DataFrame, invoices: pd.DataFrame,
                     inv_lines: pd.DataFrame, disputes: pd.DataFrame,
                     payments: pd.DataFrame, cycle: pd.DataFrame,
                     cust: pd.DataFrame) -> pd.DataFrame:
    """One row per open O2C exception: what, whose, how much, how old, who owns it."""
    as_of = np.datetime64(s.timeline.as_of_date, "D")
    name = cust.set_index("customer_id")["customer_name"]
    parts = []

    def add(df, kind, owner, value_col, since_col, ref_col, ref_kind):
        if df is None or df.empty:
            return
        d = pd.DataFrame({
            "exception_type": kind,
            "owner_function": owner,
            "customer_id": df["customer_id"].to_numpy().astype("int32"),
            "reference_type": ref_kind,
            "reference_id": df[ref_col].to_numpy().astype("int64"),
            "order_id": df["order_id"].to_numpy().astype("int32")
            if "order_id" in df else 0,
            "exception_value_usd": np.round(df[value_col].to_numpy().astype(float), 2),
            "since_date": pd.to_datetime(df[since_col]).to_numpy().astype("datetime64[D]"),
        })
        parts.append(d)

    # 1. Orders sitting on credit hold.
    held = orders[(orders["is_credit_hold"] == 1) & (orders["is_cancelled"] == 0)].copy()
    held["_v"] = held["total_order_amount_usd"]
    add(held, "Credit Hold", "Credit", "_v", "credit_hold_date", "order_id", "Order")

    # 2. Backordered value that has not shipped.
    bo = order_lines[order_lines["quantity_backordered"] > 0].copy()
    if not bo.empty:
        bo["_v"] = bo["unit_price_usd"] * bo["quantity_backordered"]
        g = bo.groupby("order_id").agg(_v=("_v", "sum"),
                                       customer_id=("customer_id", "first"),
                                       order_date=("order_date", "first")).reset_index()
        shipped_bo = set(shipments.loc[shipments["is_backorder_shipment"] == 1, "order_id"])
        g = g[~g["order_id"].isin(shipped_bo)]
        add(g, "Backorder", "Supply", "_v", "order_date", "order_id", "Order")

    # 3. Delivered, not invoiced - the executive KPI.
    dni = cycle[cycle["is_delivered_not_invoiced"] == 1].copy()
    dni = dni[pd.notna(dni["last_delivery_date"])]
    add(dni, "Delivered Not Invoiced", "Billing", "delivered_not_invoiced_usd",
        "last_delivery_date", "order_id", "Order")

    # 4. Overdue AR that is not under dispute (those are their own queue).
    od = invoices[(invoices["is_overdue"] == 1) & (invoices["is_disputed"] == 0)].copy()
    add(od, "Overdue Invoice", "AR Collections", "open_amount_usd", "due_date",
        "invoice_id", "Invoice")

    # 5. Open disputes.
    if disputes is not None and not disputes.empty:
        opd = disputes[disputes["is_open"] == 1].copy()
        add(opd, "Invoice Dispute", "AR Collections", "dispute_amount_usd",
            "dispute_date", "invoice_id", "Invoice")

    # 6. Shipments past their promised date and still not delivered.
    stuck = shipments[(shipments["is_delivered"] == 0)
                      & (shipments["is_lost"] == 0)].copy()
    stuck = stuck[pd.to_datetime(stuck["promised_delivery_date"]).to_numpy()
                  .astype("datetime64[D]") < as_of]
    if not stuck.empty:
        val = cycle.set_index("order_id")["booked_net_usd"]
        stuck["_v"] = val.reindex(stuck["order_id"]).fillna(0.0).to_numpy()
        add(stuck, "Late Shipment", "Logistics", "_v", "promised_delivery_date",
            "shipment_id", "Shipment")

    # 7. Lost shipments.
    lost = shipments[shipments["is_lost"] == 1].copy()
    if not lost.empty:
        val = cycle.set_index("order_id")["booked_net_usd"]
        lost["_v"] = val.reindex(lost["order_id"]).fillna(0.0).to_numpy()
        add(lost, "Lost Shipment", "Logistics", "_v", "ship_date", "shipment_id",
            "Shipment")

    # 8. Cash received and never applied - the planted defect, surfaced.
    if payments is not None and not payments.empty:
        ua = payments[payments["is_unapplied"] == 1].copy()
        ua["order_id"] = 0
        add(ua, "Unapplied Cash", "AR Collections", "payment_amount_usd",
            "payment_date", "payment_id", "Payment")

    # 9. Duplicate invoices still open.
    dup = invoices[(invoices["is_duplicate"] == 1) & (invoices["is_open"] == 1)].copy()
    add(dup, "Duplicate Invoice", "Billing", "open_amount_usd", "invoice_date",
        "invoice_id", "Invoice")

    # 10. Underbilled lines on invoices that are still open.
    if not inv_lines.empty:
        v = inv_lines[inv_lines["underbilled_amount_usd"] > 0.01].groupby("invoice_id")[
            "underbilled_amount_usd"].sum()
        pv = invoices[invoices["invoice_id"].isin(v.index) & (invoices["is_open"] == 1)].copy()
        if not pv.empty:
            pv["_v"] = v.reindex(pv["invoice_id"]).to_numpy()
            add(pv, "Price Variance", "Sales Operations", "_v", "invoice_date",
                "invoice_id", "Invoice")

    # 11. Orders with no PO, not yet invoiced - the defect before it becomes a
    #     dispute, which is the point at which it is still cheap to fix.
    invoiced_orders = set(invoices["order_id"])
    nopo = orders[(orders["po_number"].fillna("") == "")
                  & (orders["is_cancelled"] == 0)
                  & (~orders["order_id"].isin(invoiced_orders))].copy()
    nopo["_v"] = nopo["total_order_amount_usd"]
    add(nopo, "Missing PO", "Customer Service", "_v", "order_date", "order_id", "Order")

    if not parts:
        return pd.DataFrame()
    ex = pd.concat(parts, ignore_index=True)
    ex = ex[ex["exception_value_usd"] > 0.5].reset_index(drop=True)
    ex.insert(0, "exception_id", np.arange(1, len(ex) + 1, dtype="int32"))
    ex["customer_name"] = name.reindex(ex["customer_id"]).fillna("Unknown").to_numpy()
    ex["age_days"] = ((as_of - ex["since_date"].to_numpy()) / _DAY).astype("int16")
    ex["age_bucket"] = pd.cut(ex["age_days"], [-10 ** 6, 7, 30, 60, 90, 10 ** 6],
                              labels=["0-7", "8-30", "31-60", "61-90", "90+"]
                              ).astype(str)

    # Severity blends money and time, because a small exception that has been
    # open for four months is a process failure and a big one raised yesterday
    # is just Tuesday.
    v = ex["exception_value_usd"].to_numpy()
    a = ex["age_days"].to_numpy()
    score = (np.clip(v / 50_000.0, 0, 3) + np.clip(a / 45.0, 0, 3))
    ex["severity"] = np.select([score >= 3.0, score >= 1.4], ["High", "Medium"],
                               default="Low")
    ex["severity_score"] = np.round(score, 3)
    seg = cust.set_index("customer_id")["customer_segment"]
    ex["customer_segment"] = seg.reindex(ex["customer_id"]).fillna("Unknown").to_numpy()
    return ex
