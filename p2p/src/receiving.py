"""Goods receipts, delivery performance, and the open commitment.

Service and blanket lines have no goods receipt at all - they are two-way
matched against the PO. The design note ignored these and applied a three-way
match to every invoice, which is wrong for roughly a third of indirect spend and
would have produced a "missing receipt" exception for every consulting invoice
in the dataset (PLAN 2.3).

What is NOT received matters as much as what is. A PO line whose expected
receipt date has not arrived is open commitment; one that was received but never
invoiced becomes the GR/IR accrual - the headline number the design note left
out entirely (PLAN 2.1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario


def build_receipts(s: Scenario, po: pd.DataFrame, po_lines: pd.DataFrame,
                   items: pd.DataFrame, employees: pd.DataFrame, ep: EventPlan,
                   rng: np.random.Generator):
    """Returns (goods_receipt, goods_receipt_line, po_lines) - lines gain
    received quantities and a receipt state."""
    rc = s.receiving
    tl = s.timeline

    po_idx = po.set_index("purchase_order_id")
    lines = po_lines.copy()
    lines["po_type"] = po_idx.loc[lines["purchase_order_id"], "po_type"].to_numpy()
    lines["company_code"] = po_idx.loc[lines["purchase_order_id"],
                                       "company_code"].to_numpy()
    lines["_cancelled"] = po_idx.loc[lines["purchase_order_id"],
                                     "is_cancelled"].to_numpy()

    # -- who needs a receipt at all -------------------------------------------
    # Service lines are two-way matched. A share of goods lines on blanket POs
    # are too, which is why "no receipt" is not automatically an exception.
    is_service = (lines["is_service_line"].to_numpy() == 1) | \
                 (lines["po_type"].to_numpy() == "Service")
    blanket_2way = (lines["po_type"].to_numpy() == "Blanket") & \
                   (rng.random(len(lines)) < 0.45)
    lines["match_type"] = np.where(is_service | blanket_2way, "2-Way", "3-Way")

    # -- expected and actual receipt dates ------------------------------------
    #
    # Lead time and lateness belong to the DELIVERY, which is per purchase
    # order, not per line. Drawing them per line gives every line its own
    # arrival date, every receipt header collapses to a single line, and the
    # receipt count comes out equal to the line count.
    po_seg = (lines.groupby("purchase_order_id")["segment_name"]
              .agg(lambda x: x.iloc[0]))
    po_sup = lines.groupby("purchase_order_id")["supplier_id"].first()
    po_dt = lines.groupby("purchase_order_id")["po_date"].first()
    n_po = len(po_seg)

    lead_lo = np.full(n_po, 5.0)
    lead_hi = np.full(n_po, 25.0)
    seg_arr = po_seg.to_numpy()
    for segment, (lo, hi) in rc["lead_time_days_by_segment"].items():
        m = seg_arr == segment
        lead_lo[m], lead_hi[m] = float(lo), float(hi)
    po_lead = np.round(rng.uniform(lead_lo, lead_hi))

    # On-time probability carries Event 5: nine suppliers decay from 94% to 79%
    # across the window, and the hero supplier is one of them.
    on_time_p = ep.on_time_target(po_sup.to_numpy(), po_dt.to_numpy())
    po_on_time = rng.random(n_po) < on_time_p
    mu, sd = rc["late_days_lognorm"]
    po_late = np.where(po_on_time, 0.0,
                       np.round(np.exp(rng.normal(mu, sd, n_po))))
    # A little early delivery too, so "on time" is a window rather than a spike.
    po_early = np.where(po_on_time & (rng.random(n_po) < 0.35),
                        -np.round(rng.uniform(0, 4, n_po)), 0.0)

    lead_map = pd.Series(po_lead, index=po_seg.index)
    slip_map = pd.Series(po_late + po_early, index=po_seg.index)
    lead = lines["purchase_order_id"].map(lead_map).to_numpy()
    slip = lines["purchase_order_id"].map(slip_map).to_numpy()

    po_date = pd.to_datetime(lines["po_date"])
    expected = po_date + pd.to_timedelta(lead, unit="D")
    actual = expected + pd.to_timedelta(slip, unit="D")
    # An early delivery on a short-lead category can otherwise land before the
    # PO that ordered it. Goods cannot arrive before they are ordered.
    floor = po_date + pd.Timedelta(days=1)
    actual = pd.Series(np.maximum(actual.to_numpy(), floor.to_numpy()),
                       index=lines.index)
    late_days, early = slip, np.zeros(len(lines))

    # -- what actually arrived -------------------------------------------------
    qty_ordered = lines["quantity_ordered"].to_numpy().astype(float)
    u = rng.random(len(lines))
    p_over = float(rc["over_receipt_share"])
    p_short = p_over + float(rc["short_receipt_share"])
    over_lo, over_hi = rc["over_receipt_pct_range"]
    short_lo, short_hi = rc["short_receipt_pct_range"]
    factor = np.select(
        [u < p_over, u < p_short],
        [1.0 + rng.uniform(over_lo, over_hi, len(lines)),
         1.0 - rng.uniform(short_lo, short_hi, len(lines))],
        default=1.0)

    # -- Event 3: quantity mismatch concentrated in three categories -----------
    ev = s.event("quantity_mismatch")
    if ev is not None and len(ep.qty_mismatch_categories):
        hot = lines["category_id"].isin(ep.qty_mismatch_categories).to_numpy()
        r = ep.ramp_series("quantity_mismatch", lines["po_date"].to_numpy())
        # Inside the hot categories, short deliveries are far more common. The
        # invoice will still be raised for the full ordered quantity, which is
        # the classic three-way-match exception.
        pick = hot & (rng.random(len(lines)) < 0.42 * np.maximum(r, 0.25))
        factor = np.where(pick, 1.0 - rng.uniform(0.10, 0.35, len(lines)), factor)

    qty_received = np.maximum(0.0, np.round(qty_ordered * factor))

    # -- what was never received ----------------------------------------------
    not_due_yet = actual > pd.Timestamp(tl.as_of_date)
    cancelled = lines["_cancelled"].to_numpy() == 1
    # A small share simply stalls: supplier never delivered, PO never closed.
    stalled = (~not_due_yet) & (~cancelled) & (rng.random(len(lines)) < 0.021)
    needs_receipt = lines["match_type"].to_numpy() == "3-Way"
    received = needs_receipt & (~not_due_yet) & (~cancelled) & (~stalled)

    lines["expected_receipt_date"] = expected.dt.date
    lines["quantity_received"] = np.where(received, qty_received, 0.0)
    lines["is_received"] = received.astype("int8")
    lines["receipt_state"] = np.select(
        [cancelled, ~needs_receipt, not_due_yet, stalled, received],
        ["Cancelled", "No Receipt Required", "Open Commitment", "Overdue Receipt",
         "Received"], default="Open Commitment")
    lines["days_late"] = np.where(received, late_days + early, np.nan)
    lines["is_on_time"] = np.where(received, (late_days + early <= 0).astype(int),
                                   np.nan)

    # -- receipt documents -----------------------------------------------------
    ridx = np.where(received)[0]
    if not len(ridx):
        empty = pd.DataFrame()
        return empty, empty, lines

    # Partial delivery: a share of lines arrive in two shipments.
    partial = rng.random(len(ridx)) < float(rc["partial_receipt_share"])
    first_share = np.where(partial, rng.uniform(0.35, 0.75, len(ridx)), 1.0)

    base = lines.iloc[ridx]
    rec_rows = []
    for pass_no, share in ((1, first_share), (2, 1.0 - first_share)):
        take = share > 0.001
        if not take.any():
            continue
        sub = base[take].copy()
        sh = share[take]
        offset = 0 if pass_no == 1 else rng.integers(2, 21, size=int(take.sum()))
        rdate = (pd.to_datetime(actual.to_numpy()[ridx][take])
                 + pd.to_timedelta(offset, unit="D"))
        sub["_receipt_date"] = rdate
        sub["_qty"] = np.round(qty_received[ridx][take] * sh, 2)
        sub["_pass"] = pass_no
        rec_rows.append(sub)
    rec = pd.concat(rec_rows, ignore_index=True)
    rec = rec[rec["_qty"] > 0].reset_index(drop=True)
    # A second shipment landing after as-of has not happened yet.
    rec = rec[rec["_receipt_date"] <= pd.Timestamp(tl.as_of_date)].reset_index(drop=True)

    # Header: one receipt per PO per receipt date.
    rec["_hdr"] = rec.groupby(["purchase_order_id", "_receipt_date"],
                              sort=False).ngroup()
    receivers = employees[employees["function_name"].isin(["Operations", "Facilities"])]
    if not len(receivers):
        receivers = employees
    hdr = (rec.groupby("_hdr")
           .agg(purchase_order_id=("purchase_order_id", "first"),
                supplier_id=("supplier_id", "first"),
                company_code=("company_code", "first"),
                receipt_date=("_receipt_date", "first"),
                line_count=("_qty", "count"))
           .reset_index())
    hdr["goods_receipt_id"] = np.arange(1, len(hdr) + 1, dtype=np.int64)
    hdr["receipt_number"] = [f"GR-{i:07d}" for i in hdr["goods_receipt_id"]]
    hdr["received_by_employee_id"] = receivers.sample(
        n=len(hdr), replace=True,
        random_state=int(s.seed) + 601)["employee_id"].to_numpy()
    hdr["receipt_type"] = "Goods Receipt"

    id_of = dict(zip(hdr["_hdr"], hdr["goods_receipt_id"]))
    rec["goods_receipt_id"] = rec["_hdr"].map(id_of)

    rl = pd.DataFrame({
        "goods_receipt_line_id": np.arange(1, len(rec) + 1, dtype=np.int64),
        "goods_receipt_id": rec["goods_receipt_id"].to_numpy(),
        "purchase_order_id": rec["purchase_order_id"].to_numpy(),
        "purchase_order_line_id": rec["purchase_order_line_id"].to_numpy(),
        "item_id": rec["item_id"].to_numpy(),
        "category_id": rec["category_id"].to_numpy(),
        "supplier_id": rec["supplier_id"].to_numpy(),
        "receipt_date": pd.to_datetime(rec["_receipt_date"]).dt.date,
        "quantity_ordered": rec["quantity_ordered"].to_numpy(),
        "quantity_received": rec["_qty"].to_numpy(),
        "unit_price_usd": rec["unit_price_usd"].to_numpy(),
        "receipt_sequence": rec["_pass"].to_numpy().astype("int8"),
    })
    rl["received_amount_usd"] = np.round(rl["quantity_received"]
                                         * rl["unit_price_usd"], 2)
    rl["is_partial_delivery"] = (rl["receipt_sequence"] > 1).astype("int8")
    # Quality rejections give the QUALITY_HOLD reason something real behind it.
    rej = rng.random(len(rl)) < 0.014
    rl["quantity_rejected"] = np.where(
        rej, np.round(rl["quantity_received"] * rng.uniform(0.05, 0.4, len(rl))), 0.0)

    # Roll the actual received quantity back onto the PO line, since partial and
    # post-as-of shipments mean it is not simply what was drawn above.
    actual_by_line = rl.groupby("purchase_order_line_id")["quantity_received"].sum()
    lines["quantity_received"] = (lines["purchase_order_line_id"]
                                  .map(actual_by_line).fillna(0.0).to_numpy())
    lines["is_received"] = (lines["quantity_received"] > 0).astype("int8")
    lines.loc[(lines["receipt_state"] == "Received")
              & (lines["quantity_received"] <= 0), "receipt_state"] = "Open Commitment"
    lines["is_over_receipt"] = (lines["quantity_received"]
                                > lines["quantity_ordered"] * 1.001).astype("int8")
    lines["is_short_receipt"] = ((lines["is_received"] == 1)
                                 & (lines["quantity_received"]
                                    < lines["quantity_ordered"] * 0.999)).astype("int8")
    # Open commitment is the UNRECEIVED remainder of a live THREE-WAY line - the
    # part not yet delivered plus the shortfall where a line under-delivered. A
    # two-way line has no receipt by design, so counting its full value as
    # undelivered would put most of the commitment in a bucket that is not
    # waiting on anything. Two-way commitment is closed by the invoice instead,
    # and is computed in derived.py once invoicing has run.
    outstanding = np.maximum(
        0.0, lines["quantity_ordered"].to_numpy() - lines["quantity_received"].to_numpy())
    live = ((lines["receipt_state"] != "Cancelled")
            & (lines["match_type"] == "3-Way")).to_numpy()
    lines["open_commitment_usd"] = np.round(
        np.where(live, outstanding * lines["unit_price_usd"].to_numpy(), 0.0), 2)
    lines["received_amount_usd"] = np.round(
        lines["quantity_received"].to_numpy() * lines["unit_price_usd"].to_numpy(), 2)

    hdr["total_received_amount_usd"] = (rl.groupby("goods_receipt_id")
                                        ["received_amount_usd"].sum()
                                        .reindex(hdr["goods_receipt_id"]).to_numpy())
    hdr = hdr.drop(columns=["_hdr"])
    hdr["receipt_date"] = pd.to_datetime(hdr["receipt_date"]).dt.date
    return hdr, rl, lines
