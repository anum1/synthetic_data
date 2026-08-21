"""Derived AR: the invoice ledger, monthly ageing, and credit exposure.

**Nothing in this module is drawn.** Every number here is computed from
`fact_payment_allocation`, `fact_credit_memo` and the invoice itself. That is
deliberate and it is the single most important rule in the dataset: an invoice
marked Paid that still carries a balance, or an ageing matrix that does not add
up to the Open AR tile, ends a finance demo on the spot.

The open balance is:

    open = total_amount
         - allocated cash
         - credit memos
         - early-payment discount taken

The last term is the one that catches people out. A customer taking 2/10 Net 30
short-pays by the discount and the invoice is closed; treating the shortfall as
a receivable leaves a permanent 2% residue on every discounted invoice, and
three years later that residue is the entire 365+ ageing bucket.

Written-off invoices leave the ledger. They are bad debt, reported separately -
carrying them in AR would make every collections metric wrong in the same
direction.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from o2cconfig import Scenario, month_end

_DAY = np.timedelta64(1, "D")

AGING_BUCKETS = ["Current", "1-30", "31-60", "61-90", "90+"]


def compute_invoice_ledger(s: Scenario, invoices: pd.DataFrame,
                           allocations: pd.DataFrame,
                           memos: pd.DataFrame) -> pd.DataFrame:
    """Attach paid / credited / open / status to every invoice."""
    as_of = np.datetime64(s.timeline.as_of_date, "D")
    inv = invoices.copy()

    paid = (allocations.groupby("invoice_id")["allocated_amount_usd"].sum()
            if not allocations.empty else pd.Series(dtype=float))
    credited = (memos.groupby("invoice_id")["memo_amount_usd"].sum()
                if not memos.empty else pd.Series(dtype=float))
    last_pay = (allocations.groupby("invoice_id")["allocation_date"].max()
                if not allocations.empty else pd.Series(dtype="datetime64[ns]"))

    inv["paid_amount_usd"] = paid.reindex(inv["invoice_id"]).fillna(0.0).to_numpy().round(2)
    inv["credited_amount_usd"] = credited.reindex(inv["invoice_id"]).fillna(0.0).to_numpy().round(2)
    disc = inv.get("early_discount_taken_usd", pd.Series(0.0, index=inv.index))
    inv["early_discount_taken_usd"] = np.round(disc.to_numpy(), 2)

    open_amt = (inv["total_amount_usd"].to_numpy()
                - inv["paid_amount_usd"].to_numpy()
                - inv["credited_amount_usd"].to_numpy()
                - inv["early_discount_taken_usd"].to_numpy())
    # Sub-cent residue from rounding two payment legs is noise, not a debt.
    open_amt = np.where(np.abs(open_amt) < 0.02, 0.0, open_amt)
    inv["open_amount_usd"] = np.round(open_amt, 2)

    inv["fully_paid_date"] = pd.to_datetime(
        last_pay.reindex(inv["invoice_id"])).to_numpy().astype("datetime64[D]")
    inv.loc[inv["open_amount_usd"] > 0.01, "fully_paid_date"] = np.datetime64("NaT")

    due = pd.to_datetime(inv["due_date"]).to_numpy().astype("datetime64[D]")
    inv_date = pd.to_datetime(inv["invoice_date"]).to_numpy().astype("datetime64[D]")
    inv["days_overdue"] = np.where(inv["open_amount_usd"].to_numpy() > 0.01,
                                   np.maximum(0, (as_of - due) / _DAY), 0).astype("int16")
    inv["days_to_pay_actual"] = np.where(
        pd.notna(inv["fully_paid_date"]),
        (pd.to_datetime(inv["fully_paid_date"]).to_numpy().astype("datetime64[D]")
         - inv_date) / _DAY, -1).astype("int16")

    written_off = inv.get("is_written_off", pd.Series(0, index=inv.index)).to_numpy() == 1
    inv["is_open"] = ((inv["open_amount_usd"] > 0.01) & ~written_off).astype("int8")
    inv["is_overdue"] = ((inv["is_open"] == 1) & (due < as_of)).astype("int8")
    inv["aging_bucket"] = _bucket((as_of - due) / _DAY)
    inv.loc[inv["is_open"] == 0, "aging_bucket"] = "Not Open"

    # Status is derived last, from everything above, and is never drawn.
    status = np.full(len(inv), "Issued", dtype=object)
    partial = ((inv["paid_amount_usd"].to_numpy() > 0.01)
               & (inv["open_amount_usd"].to_numpy() > 0.01))
    status[partial] = "Partially Paid"
    status[inv["is_overdue"].to_numpy() == 1] = "Overdue"
    status[inv["is_open"].to_numpy() == 0] = "Paid"
    status[written_off] = "Written Off"
    inv["invoice_status"] = status
    return inv


def apply_dispute_status(inv: pd.DataFrame, disputes: pd.DataFrame) -> pd.DataFrame:
    """Mark invoices carrying an open dispute.

    Applied after the payment-derived status so Disputed wins over Overdue: an
    invoice that is late *because it is being argued about* belongs to the
    disputes queue, not to the collections queue, and putting it in both is how
    the same $2.1M gets chased twice.
    """
    inv = inv.copy()
    inv["disputed_amount_usd"] = 0.0
    inv["is_disputed"] = 0
    if disputes is None or disputes.empty:
        return inv
    open_d = disputes[disputes["is_open"] == 1]
    if open_d.empty:
        return inv
    amt = open_d.groupby("invoice_id")["dispute_amount_usd"].sum()
    hit = amt.reindex(inv["invoice_id"]).fillna(0.0).to_numpy()
    inv["disputed_amount_usd"] = np.round(np.minimum(hit, inv["open_amount_usd"].to_numpy()), 2)
    inv["is_disputed"] = ((hit > 0) & (inv["is_open"] == 1)).astype("int8")
    inv.loc[inv["is_disputed"] == 1, "invoice_status"] = "Disputed"
    return inv


def _bucket(days_past_due: np.ndarray) -> np.ndarray:
    d = np.asarray(days_past_due, dtype=float)
    return np.select(
        [d <= 0, d <= 30, d <= 60, d <= 90],
        ["Current", "1-30", "31-60", "61-90"], default="90+")


def build_ar_aging_snapshot(s: Scenario, inv: pd.DataFrame,
                            allocations: pd.DataFrame,
                            memos: pd.DataFrame) -> pd.DataFrame:
    """One row per open invoice per month-end, with its bucket at that date.

    This is what makes "AR ageing in March 2025" a GROUP BY instead of a
    correlated subquery, and it is what the ageing matrix on the collections
    page reads. The as-of month of this table reconciles exactly to the ledger
    above - `validate.py` asserts it to the cent.
    """
    months = [month_end(m) for m in s.timeline.month_starts()]
    inv_date = pd.to_datetime(inv["invoice_date"]).to_numpy().astype("datetime64[D]")
    due = pd.to_datetime(inv["due_date"]).to_numpy().astype("datetime64[D]")
    total = inv["total_amount_usd"].to_numpy()
    disc = inv["early_discount_taken_usd"].to_numpy()
    written = inv.get("is_written_off", pd.Series(0, index=inv.index)).to_numpy() == 1

    # Cash and credit applied on or before each month end, invoice by invoice.
    alloc_d = (pd.to_datetime(allocations["allocation_date"]).to_numpy().astype("datetime64[D]")
               if not allocations.empty else np.array([], dtype="datetime64[D]"))
    memo_d = (pd.to_datetime(memos["memo_date"]).to_numpy().astype("datetime64[D]")
              if not memos.empty else np.array([], dtype="datetime64[D]"))

    inv_pos = pd.Series(np.arange(len(inv)), index=inv["invoice_id"].to_numpy())
    a_idx = (inv_pos.reindex(allocations["invoice_id"]).to_numpy()
             if not allocations.empty else np.array([], dtype=int))
    a_amt = (allocations["allocated_amount_usd"].to_numpy()
             if not allocations.empty else np.array([]))
    m_idx = (inv_pos.reindex(memos["invoice_id"]).to_numpy()
             if not memos.empty else np.array([], dtype=int))
    m_amt = (memos["memo_amount_usd"].to_numpy() if not memos.empty else np.array([]))

    rows = []
    for me in months:
        me64 = np.datetime64(me, "D")
        issued = inv_date <= me64
        if not issued.any():
            continue
        settled = np.zeros(len(inv))
        if len(a_idx):
            sel = (alloc_d <= me64) & pd.notna(a_idx)
            np.add.at(settled, a_idx[sel].astype(int), a_amt[sel])
        if len(m_idx):
            sel = (memo_d <= me64) & pd.notna(m_idx)
            np.add.at(settled, m_idx[sel].astype(int), m_amt[sel])

        # Written-off invoices leave the ledger on the month they are written
        # off, not retroactively - the AR balance was real until then.
        gone = written & (due + np.timedelta64(int(s.collections["writeoff_days"]), "D") <= me64)
        open_amt = np.round(total - settled - disc, 2)
        keep = issued & (open_amt > 0.01) & ~gone
        if not keep.any():
            continue

        k = np.where(keep)[0]
        dpd = (me64 - due[k]) / _DAY
        rows.append(pd.DataFrame({
            "invoice_id": inv["invoice_id"].to_numpy()[k],
            "customer_id": inv["customer_id"].to_numpy()[k],
            "snapshot_date": me,
            "year_month_key": me.year * 100 + me.month,
            "open_amount_usd": open_amt[k],
            "days_past_due": dpd.astype("int16"),
            "aging_bucket": _bucket(dpd),
            "business_unit": inv["business_unit"].to_numpy()[k],
            "region": inv["region"].to_numpy()[k],
            "customer_segment": inv["customer_segment"].to_numpy()[k],
            "payment_terms_code": inv["payment_terms_code"].to_numpy()[k],
        }))
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out.insert(0, "ar_aging_id", np.arange(1, len(out) + 1, dtype="int64"))
    out["year_month_key"] = out["year_month_key"].astype("int32")
    out["invoice_id"] = out["invoice_id"].astype("int32")
    out["customer_id"] = out["customer_id"].astype("int32")
    out["is_overdue"] = (out["days_past_due"] > 0).astype("int8")
    return out


def build_credit_exposure_snapshot(s: Scenario, cust: pd.DataFrame,
                                   orders: pd.DataFrame, inv: pd.DataFrame,
                                   aging: pd.DataFrame) -> pd.DataFrame:
    """Customer x month-end credit position.

    The design note had credit as current state only - one row per customer with
    today's exposure. That cannot answer "why did exposure spike in March", and
    Event 9 is entirely a question about a trend. Exposure here is open AR plus
    open order backlog, which is what a credit function actually watches.
    """
    months = [month_end(m) for m in s.timeline.month_starts()]
    g = float(s.demand["annual_growth"])
    as_of = np.datetime64(s.timeline.as_of_date, "D")

    ar_by = (aging.groupby(["snapshot_date", "customer_id"])["open_amount_usd"].sum()
             if not aging.empty else pd.Series(dtype=float))

    od = pd.to_datetime(orders["order_date"]).to_numpy().astype("datetime64[D]")
    # Backlog: booked, not cancelled, not yet invoiced at that month end.
    inv_by_order = inv.groupby("order_id")["invoice_date"].min()
    o_inv = pd.to_datetime(inv_by_order.reindex(orders["order_id"])).to_numpy().astype("datetime64[D]")
    o_amt = orders["total_order_amount_usd"].to_numpy()
    o_cust = orders["customer_id"].to_numpy()
    o_cancel = pd.to_datetime(orders["cancelled_date"]).to_numpy().astype("datetime64[D]")
    o_hold = orders["is_credit_hold"].to_numpy() == 1

    limits = cust.set_index("customer_id")["credit_limit_usd"]
    cust_ids = cust["customer_id"].to_numpy()
    pos = pd.Series(np.arange(len(cust_ids)), index=cust_ids)

    rows = []
    for me in months:
        me64 = np.datetime64(me, "D")
        live = (od <= me64) & (pd.isna(o_cancel) | (o_cancel > me64)) \
            & (pd.isna(o_inv) | (o_inv > me64))
        backlog = np.zeros(len(cust_ids))
        if live.any():
            idx = pos.reindex(o_cust[live]).to_numpy()
            ok = pd.notna(idx)
            np.add.at(backlog, idx[ok].astype(int), o_amt[live][ok])

        held = np.zeros(len(cust_ids))
        hm = live & o_hold
        if hm.any():
            idx = pos.reindex(o_cust[hm]).to_numpy()
            ok = pd.notna(idx)
            np.add.at(held, idx[ok].astype(int), o_amt[hm][ok])

        ar = (ar_by.loc[me].reindex(cust_ids).fillna(0.0).to_numpy()
              if (not aging.empty and me in ar_by.index.get_level_values(0)) else
              np.zeros(len(cust_ids)))

        exposure = ar + backlog
        years_back = (me64 - as_of) / np.timedelta64(365, "D")
        limit = limits.reindex(cust_ids).to_numpy() * (1.0 + g) ** years_back

        keep = (exposure > 0.01) | (held > 0.01)
        if not keep.any():
            continue
        k = np.where(keep)[0]
        rows.append(pd.DataFrame({
            "customer_id": cust_ids[k],
            "snapshot_date": me,
            "year_month_key": me.year * 100 + me.month,
            "credit_limit_usd": np.round(limit[k], 2),
            "open_ar_usd": np.round(ar[k], 2),
            "open_order_backlog_usd": np.round(backlog[k], 2),
            "current_exposure_usd": np.round(exposure[k], 2),
            "available_credit_usd": np.round(limit[k] - exposure[k], 2),
            "value_on_credit_hold_usd": np.round(held[k], 2),
        }))
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out.insert(0, "credit_exposure_id", np.arange(1, len(out) + 1, dtype="int32"))
    out["year_month_key"] = out["year_month_key"].astype("int32")
    out["customer_id"] = out["customer_id"].astype("int32")
    out["credit_utilization_pct"] = np.round(
        out["current_exposure_usd"] / np.maximum(out["credit_limit_usd"], 1.0), 4)
    out["is_over_limit"] = (out["current_exposure_usd"] > out["credit_limit_usd"]).astype("int8")
    rating = cust.set_index("customer_id")["credit_rating"]
    out["credit_rating"] = rating.reindex(out["customer_id"]).to_numpy()
    seg = cust.set_index("customer_id")["customer_segment"]
    out["customer_segment"] = seg.reindex(out["customer_id"]).to_numpy()
    return out
