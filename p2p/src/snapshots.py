"""Month-end snapshots: AP ageing, open commitment and GR/IR.

A current-state table cannot answer "was this ageing worse a year ago", and
recomputing an ageing matrix from the ledger inside a BI tool produces a
different answer in each of them. Both snapshots are built here, once, and
validate.py asserts the ageing ties back to the subledger to the cent at every
month end (PLAN 2.4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p2pconfig import Scenario, month_end

BUCKETS = [(-10**9, 0, "Not yet due"), (0, 30, "1-30 days"), (30, 60, "31-60 days"),
           (60, 90, "61-90 days"), (90, 10**9, "90+ days")]


def _bucket(days: np.ndarray) -> np.ndarray:
    out = np.empty(len(days), dtype=object)
    for lo, hi, name in BUCKETS:
        out[(days > lo) & (days <= hi)] = name
    out[days <= 0] = "Not yet due"
    return out


def build_ap_aging_snapshot(s: Scenario, inv: pd.DataFrame,
                            apps: pd.DataFrame) -> pd.DataFrame:
    """One row per open invoice at each month end."""
    if inv.empty:
        return pd.DataFrame()
    std = inv[inv["invoice_type"] == "Standard Invoice"].copy()
    settled = (pd.to_datetime(apps["payment_date"]).groupby(apps["invoice_id"]).max()
               if len(apps) else pd.Series(dtype="datetime64[ns]"))
    std["_settled"] = pd.to_datetime(std["invoice_id"].map(settled))
    std["_received"] = pd.to_datetime(std["invoice_received_date"])
    std["_due"] = pd.to_datetime(std["due_date"])

    frames = []
    for m in s.timeline.month_starts():
        me = pd.Timestamp(month_end(m))
        # Open at that month end: already received, not yet settled.
        open_now = ((std["_received"] <= me)
                    & (std["_settled"].isna() | (std["_settled"] > me))).to_numpy()
        if not open_now.any():
            continue
        sub = std[open_now]
        days = (me - sub["_due"]).dt.days.to_numpy()
        frames.append(pd.DataFrame({
            "snapshot_month_end": me.date(),
            "invoice_id": sub["invoice_id"].to_numpy(),
            "supplier_id": sub["supplier_id"].to_numpy(),
            "company_code": sub["company_code"].to_numpy(),
            "department_id": sub["department_id"].to_numpy(),
            "invoice_date": sub["invoice_date"].to_numpy(),
            "due_date": sub["due_date"].to_numpy(),
            "open_amount_usd": sub["gross_amount_usd"].to_numpy(),
            "days_past_due": days.astype("int32"),
            "aging_bucket": _bucket(days),
            "is_overdue": (days > 0).astype("int8"),
            "has_open_hold": sub["hold_count"].to_numpy() > 0,
        }))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["has_open_hold"] = out["has_open_hold"].astype("int8")
    out["ap_aging_id"] = np.arange(1, len(out) + 1, dtype=np.int64)
    return out


def build_open_commitment_snapshot(s: Scenario, po: pd.DataFrame,
                                   po_lines: pd.DataFrame, gr_lines: pd.DataFrame,
                                   inv_lines: pd.DataFrame,
                                   inv: pd.DataFrame) -> pd.DataFrame:
    """Open PO commitment and the GR/IR balance, by supplier, at each month end.

    GR/IR over time is what turns "we have an $18.7M accrual" into "and it has
    been building for two years", which is a different conversation.
    """
    if po_lines.empty:
        return pd.DataFrame()
    lines = po_lines.copy()
    first_receipt = (pd.to_datetime(gr_lines["receipt_date"])
                     .groupby(gr_lines["purchase_order_line_id"]).min()
                     if len(gr_lines) else pd.Series(dtype="datetime64[ns]"))
    inv_date_by_line = None
    if len(inv_lines) and len(inv):
        d = inv_lines[inv_lines["purchase_order_line_id"] > 0][
            ["purchase_order_line_id", "invoice_id"]].merge(
            inv[["invoice_id", "invoice_date"]], on="invoice_id", how="left")
        inv_date_by_line = (pd.to_datetime(d["invoice_date"])
                            .groupby(d["purchase_order_line_id"]).min())

    lines["_po"] = pd.to_datetime(lines["po_date"])
    lines["_recv"] = pd.to_datetime(lines["purchase_order_line_id"].map(first_receipt))
    lines["_inv"] = pd.to_datetime(
        lines["purchase_order_line_id"].map(inv_date_by_line)) \
        if inv_date_by_line is not None else pd.NaT
    live = lines[lines["receipt_state"] != "Cancelled"]

    frames = []
    for m in s.timeline.month_starts():
        me = pd.Timestamp(month_end(m))
        issued = (live["_po"] <= me).to_numpy()
        if not issued.any():
            continue
        sub = live[issued]
        received_by = (sub["_recv"].notna() & (sub["_recv"] <= me)).to_numpy()
        invoiced_by = (sub["_inv"].notna() & (sub["_inv"] <= me)).to_numpy()
        three = (sub["match_type"].to_numpy() == "3-Way")

        open_amt = np.where(three & ~received_by,
                            sub["line_amount_usd"].to_numpy(), 0.0)
        gr_ir = np.where(three & received_by & ~invoiced_by,
                         sub["received_amount_usd"].to_numpy(), 0.0)
        if not (open_amt.any() or gr_ir.any()):
            continue
        g = pd.DataFrame({
            "supplier_id": sub["supplier_id"].to_numpy(),
            "open_commitment_usd": open_amt,
            "gr_ir_amount_usd": gr_ir,
            "line_count": 1,
        }).groupby("supplier_id", as_index=False).sum()
        g = g[(g["open_commitment_usd"] > 0) | (g["gr_ir_amount_usd"] > 0)]
        g.insert(0, "snapshot_month_end", me.date())
        frames.append(g)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["open_commitment_id"] = np.arange(1, len(out) + 1, dtype=np.int64)
    return out
