"""Cash application, disputes, credit memos and returns.

(Named `receivables` rather than `collections`: a module called `collections.py`
on the path shadows the standard library for every other module in the package,
and the failure it causes is nowhere near where the mistake is.)

The rule that governs this whole module: **`fact_payment_allocation` is the
source of truth for what has been paid.** Invoice status and AR balance are
computed from it in snapshots.py, never drawn. An invoice marked Paid that still
carries a balance is the fastest way to lose a finance audience, and the only
way to be sure it cannot happen is to never write the status down.

Disputes are generated from their causes, not sampled. An invoice with a price
variance disputes on Pricing Discrepancy; an order raised with no PO number
disputes on Missing PO; a duplicated invoice disputes on Duplicate Invoice; a
late delivery disputes on Late Delivery. The planted data-quality defect and the
AR exception are therefore the same finding seen from two ends, which is a much
better demo than two unrelated oddities.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from events import EventPlan
from o2cconfig import Scenario

_DAY = np.timedelta64(1, "D")


def build_collections(s: Scenario, invoices: pd.DataFrame, inv_lines: pd.DataFrame,
                      orders: pd.DataFrame, order_lines: pd.DataFrame,
                      shipments: pd.DataFrame, prod: pd.DataFrame,
                      terms: pd.DataFrame, cust: pd.DataFrame, ep: EventPlan,
                      rng: np.random.Generator):
    """Return (payments, allocations, disputes, credit_memos, returns)."""
    as_of = np.datetime64(s.timeline.as_of_date, "D")
    col = s.collections
    n = len(invoices)
    inv_date = pd.to_datetime(invoices["invoice_date"]).to_numpy().astype("datetime64[D]")
    due_date = pd.to_datetime(invoices["due_date"]).to_numpy().astype("datetime64[D]")

    disputes = _build_disputes(s, invoices, inv_lines, orders, shipments,
                               inv_date, ep, rng)
    returns, memos_from_returns = _build_returns(s, invoices, inv_lines, orders,
                                                 prod, inv_date, ep, rng)
    # Credit notes are settled before the cash is worked out, not after. Applied
    # afterwards they would push paid invoices into a negative balance, and an
    # AR page full of customers who apparently overpaid is not a demo.
    # The early-payment decision is made before the credit notes are capped,
    # because what an invoice owes is its total LESS any discount taken - cap
    # against the gross and a discounted invoice can still be over-credited.
    disc_days = terms.set_index("payment_terms_code")["discount_days"].reindex(
        invoices["payment_terms_code"]).fillna(0).to_numpy()
    disc_pct = terms.set_index("payment_terms_code")["discount_pct"].reindex(
        invoices["payment_terms_code"]).fillna(0.0).to_numpy()
    takes = (disc_pct > 0) & (rng.random(n) < float(col["early_payment_discount_take_rate"]))
    total = invoices["total_amount_usd"].to_numpy().astype(float)
    early_discount = np.round(np.where(takes, total * disc_pct, 0.0), 2)
    owed = np.round(total - early_discount, 2)

    memos = _build_credit_memos(s, invoices, disputes, memos_from_returns, owed, rng)

    # ---- when does the cash arrive? -----------------------------------------
    dtp = orders.set_index("order_id")["_days_to_pay"]
    days = dtp.reindex(invoices["order_id"]).fillna(35).to_numpy().astype(float)
    pay_date = inv_date + np.round(days).astype("timedelta64[D]")

    # A disputed invoice does not get paid while the argument is running.
    if not disputes.empty:
        open_by_inv = disputes.groupby("invoice_id")["resolved_date"].max()
        raised_by_inv = disputes.groupby("invoice_id")["dispute_date"].min()
        res = pd.to_datetime(open_by_inv.reindex(invoices["invoice_id"])).to_numpy()
        raised = pd.to_datetime(raised_by_inv.reindex(invoices["invoice_id"])).to_numpy()
        has_dispute = ~pd.isna(raised)
        resolved = ~pd.isna(res)
        # Resolved: paid a couple of weeks after settlement. Unresolved: not yet.
        settle = np.where(resolved,
                          res.astype("datetime64[D]")
                          + rng.integers(2, 20, n).astype("timedelta64[D]"),
                          np.datetime64("2999-12-31", "D"))
        pay_date = np.where(has_dispute, np.maximum(pay_date, settle), pay_date)

    # Early-payment discount takers pay on the discount date instead. The
    # discount is taken as a short payment, which is what actually shows up on a
    # remittance - not as a separate credit note.
    pay_date = np.where(takes, inv_date + disc_days.astype("timedelta64[D]"), pay_date)
    expected_cash = owed.copy()

    # Credit memos reduce what is owed before any cash is applied.
    memo_by_inv = (memos.groupby("invoice_id")["memo_amount_usd"].sum()
                   if not memos.empty else pd.Series(dtype=float))
    credited = memo_by_inv.reindex(invoices["invoice_id"]).fillna(0.0).to_numpy()
    expected_cash = np.maximum(0.0, expected_cash - credited)

    # ---- write-offs ----------------------------------------------------------
    # A small share of invoices are never going to be paid. Those become write-
    # offs once they have aged past the policy threshold; until then they sit in
    # AR getting older, which is where the bad-debt exposure story comes from.
    #
    # The trap here is applying the write-off probability to every AGED invoice
    # rather than to the doomed ones: three years of history are all older than
    # the threshold, so a 35% roll would write off a third of the company.
    never_pays = rng.random(n) < float(col["writeoff_rate"])
    age = (as_of - due_date) / _DAY
    written_off = never_pays & (age > int(col["writeoff_days"]))
    unrecoverable = never_pays

    # ---- partial payments ----------------------------------------------------
    partial = (rng.random(n) < float(col["partial_payment_rate"])) & ~unrecoverable
    first_share = np.where(partial, rng.uniform(0.45, 0.85, n), 1.0)
    second_gap = rng.integers(12, 55, n)

    rows = []
    for leg, (share, offset) in enumerate([(first_share, np.zeros(n, dtype=int)),
                                           (1.0 - first_share, second_gap)]):
        amt = np.round(expected_cash * share, 2)
        when = pay_date + offset.astype("timedelta64[D]")
        keep = (amt > 0.005) & (when <= as_of) & ~unrecoverable
        if not keep.any():
            continue
        rows.append(pd.DataFrame({
            "invoice_id": invoices["invoice_id"].to_numpy()[keep],
            "customer_id": invoices["customer_id"].to_numpy()[keep],
            "currency_code": invoices["currency_code"].to_numpy()[keep],
            "allocated_amount_usd": amt[keep],
            "allocation_date": when[keep],
            "leg": leg,
        }))
    if not rows:
        alloc = pd.DataFrame(columns=["invoice_id", "customer_id", "currency_code",
                                      "allocated_amount_usd", "allocation_date", "leg"])
    else:
        alloc = pd.concat(rows, ignore_index=True)

    payments, alloc = _group_into_remittances(s, alloc, rng)

    invoices = invoices.copy()
    invoices["is_written_off"] = written_off.astype("int8")
    invoices["early_discount_taken_usd"] = early_discount
    return payments, alloc, disputes, memos, returns, invoices


def _build_disputes(s: Scenario, invoices: pd.DataFrame, inv_lines: pd.DataFrame,
                    orders: pd.DataFrame, shipments: pd.DataFrame,
                    inv_date: np.ndarray, ep: EventPlan,
                    rng: np.random.Generator) -> pd.DataFrame:
    """Disputes, each with a cause that exists elsewhere in the data."""
    col = s.collections
    n = len(invoices)
    base = float(col["dispute_base_rate"])

    # Causes, strongest first. An invoice can qualify on several; the reason
    # recorded is the strongest one, which is also how a real AR team codes it.
    var_by_inv = inv_lines.groupby("invoice_id")["underbilled_amount_usd"].sum()
    has_variance = (var_by_inv.reindex(invoices["invoice_id"]).fillna(0.0).to_numpy()
                    > 0.005)
    no_po = invoices["po_number"].fillna("").to_numpy() == ""
    is_dup = invoices["is_duplicate"].to_numpy() == 1

    late_by_order = shipments.groupby("order_id")["delay_days"].max()
    was_late = (late_by_order.reindex(invoices["order_id"]).fillna(0).to_numpy() > 3)
    bo_orders = set(shipments.loc[shipments["is_backorder_shipment"] == 1, "order_id"])
    was_short = np.isin(invoices["order_id"].to_numpy(), list(bo_orders))

    p = np.full(n, base)
    p = np.where(has_variance, np.maximum(p, 0.34), p)
    p = np.where(no_po, np.maximum(p, 0.27), p)
    p = np.where(is_dup, np.maximum(p, 0.55), p)
    p = np.where(was_late, np.maximum(p, 0.11), p)
    p = np.where(was_short, np.maximum(p, 0.08), p)

    # Event 10: one account's dispute rate multiplies. It is the same account
    # Event 7 is underbilling, which is the chain the root-cause scene walks.
    ev = s.event("dispute_spike")
    if ev is not None and len(getattr(ep, "dispute_customers", [])):
        hit = (np.isin(invoices["customer_id"].to_numpy(), ep.dispute_customers)
               & ep.in_window("dispute_spike", inv_date))
        mult = 1.0 + (float(ev["dispute_rate_multiplier"]) - 1.0) * ep.ramp(
            "dispute_spike", inv_date)
        p = np.where(hit, np.clip(p * mult, 0, 0.92), p)

    raised = rng.random(n) < p
    if not raised.any():
        return pd.DataFrame()

    idx = np.where(raised)[0]
    reason = np.full(len(idx), "Contract Dispute", dtype=object)
    mix = col["dispute_reason_mix"]
    reason[:] = rng.choice(list(mix), size=len(idx), p=list(mix.values()))
    reason[was_short[idx]] = "Short Shipment"
    reason[was_late[idx]] = "Late Delivery"
    reason[no_po[idx]] = "Missing PO"
    reason[has_variance[idx]] = "Pricing Discrepancy"
    reason[is_dup[idx]] = "Duplicate Invoice"

    total = invoices["total_amount_usd"].to_numpy()[idx]
    # A pricing dispute is for the disputed amount, not the whole invoice.
    share = np.where(np.isin(reason, ["Pricing Discrepancy", "Quantity Discrepancy",
                                      "Short Shipment", "Tax Issue"]),
                     rng.uniform(0.08, 0.55, len(idx)), 1.0)
    amount = np.round(total * share, 2)

    d_date = inv_date[idx] + rng.integers(3, 40, len(idx)).astype("timedelta64[D]")
    lo, hi = col["dispute_resolution_days"]
    dur = rng.integers(lo, hi + 1, len(idx))
    r_date = d_date + dur.astype("timedelta64[D]")
    as_of = np.datetime64(s.timeline.as_of_date, "D")
    keep = d_date <= as_of
    resolved = (r_date <= as_of) & keep

    out = pd.DataFrame({
        "dispute_id": np.arange(1, int(keep.sum()) + 1, dtype="int32"),
        "invoice_id": invoices["invoice_id"].to_numpy()[idx][keep],
        "customer_id": invoices["customer_id"].to_numpy()[idx][keep],
        "order_id": invoices["order_id"].to_numpy()[idx][keep],
        "dispute_date": d_date[keep],
        "dispute_reason": reason[keep],
        "dispute_amount_usd": amount[keep],
        "invoice_amount_usd": total[keep],
        "resolved_date": np.where(resolved[keep], r_date[keep],
                                  np.datetime64("NaT")).astype("datetime64[D]"),
        "resolution_code": np.where(resolved[keep],
                                    rng.choice(R.RESOLUTION_CODES, size=int(keep.sum()),
                                               p=[0.30, 0.16, 0.19, 0.10, 0.14, 0.05, 0.06]),
                                    "Open"),
        "dispute_owner": rng.choice(R.DISPUTE_OWNERS, size=int(keep.sum()),
                                    p=[0.36, 0.26, 0.14, 0.16, 0.08]),
        "business_unit": invoices["business_unit"].to_numpy()[idx][keep],
        "customer_segment": invoices["customer_segment"].to_numpy()[idx][keep],
        "is_open": (~resolved[keep]).astype("int8"),
    })
    out["days_open"] = np.where(
        out["is_open"] == 1,
        (as_of - out["dispute_date"].to_numpy()) / _DAY,
        (pd.to_datetime(out["resolved_date"]).to_numpy().astype("datetime64[D]")
         - out["dispute_date"].to_numpy()) / _DAY).astype("int16")
    return out


def _build_returns(s: Scenario, invoices: pd.DataFrame, inv_lines: pd.DataFrame,
                   orders: pd.DataFrame, prod: pd.DataFrame, inv_date: np.ndarray,
                   ep: EventPlan, rng: np.random.Generator):
    """RMAs, and the credit memos they generate.

    Event 12 lives here. `credit_memos` alone could not carry it - a credit memo
    is the financial consequence of a return, not the return, and "which product
    category has an abnormal return rate" needs the return itself.
    """
    col = s.collections
    cat = prod.set_index("product_id")["product_category"]
    il = inv_lines.assign(_cat=cat.reindex(inv_lines["product_id"]).to_numpy())
    imap = invoices.set_index("invoice_id")
    il["_date"] = pd.to_datetime(
        imap["invoice_date"].reindex(il["invoice_id"])).to_numpy().astype("datetime64[D]")
    il["_customer"] = imap["customer_id"].reindex(il["invoice_id"]).to_numpy()

    rate = np.full(len(il), float(col["return_base_rate"]))
    ev = s.event("returns_spike")
    if ev is not None:
        hit = il["_cat"].to_numpy() == ev["product_category"]
        target = ep.blend("returns_spike", il["_date"].to_numpy(),
                          float(ev["return_rate_from"]), float(ev["return_rate_to"]))
        rate = np.where(hit & ep.in_window("returns_spike", il["_date"].to_numpy()),
                        target, rate)

    hit = rng.random(len(il)) < rate
    if not hit.any():
        return pd.DataFrame(), pd.DataFrame()
    r = il[hit].copy()
    as_of = np.datetime64(s.timeline.as_of_date, "D")
    r_date = r["_date"].to_numpy() + rng.integers(4, 70, len(r)).astype("timedelta64[D]")
    r = r[r_date <= as_of].copy()
    if r.empty:
        return pd.DataFrame(), pd.DataFrame()
    r_date = r["_date"].to_numpy() + rng.integers(4, 70, len(r)).astype("timedelta64[D]")
    r_date = np.minimum(r_date, as_of)

    qty_returned = np.maximum(1, np.round(r["quantity_invoiced"].to_numpy()
                                          * rng.uniform(0.15, 1.0, len(r))))
    value = np.round(qty_returned * r["unit_price_usd"].to_numpy(), 2)
    disp_mix = col["return_disposition_mix"]

    returns = pd.DataFrame({
        "return_id": np.arange(1, len(r) + 1, dtype="int32"),
        "rma_number": [f"RMA-{i:07d}" for i in range(1, len(r) + 1)],
        "invoice_id": r["invoice_id"].to_numpy().astype("int32"),
        "invoice_line_id": r["invoice_line_id"].to_numpy().astype("int64"),
        "order_id": r["order_id"].to_numpy().astype("int32"),
        "customer_id": r["_customer"].to_numpy().astype("int32"),
        "product_id": r["product_id"].to_numpy().astype("int32"),
        "product_category": r["_cat"].to_numpy(),
        "return_date": r_date,
        "quantity_returned": qty_returned.astype("int64"),
        "return_value_usd": value,
        "return_reason": rng.choice(R.RETURN_REASONS, size=len(r),
                                    p=[0.19, 0.15, 0.17, 0.22, 0.08, 0.12, 0.07]),
        "disposition": rng.choice(list(disp_mix), size=len(r),
                                  p=list(disp_mix.values())),
    })
    returns["is_credited"] = (returns["disposition"] != "Return to Vendor").astype("int8")

    memos = returns[returns["is_credited"] == 1][
        ["invoice_id", "customer_id", "order_id", "return_id", "return_date",
         "return_value_usd"]].copy()
    memos = memos.rename(columns={"return_value_usd": "memo_amount_usd",
                                  "return_date": "memo_date"})
    return returns, memos


def _build_credit_memos(s: Scenario, invoices: pd.DataFrame, disputes: pd.DataFrame,
                        from_returns: pd.DataFrame, owed: np.ndarray,
                        rng: np.random.Generator) -> pd.DataFrame:
    """Credit memos from two sources: returns, and disputes settled with credit."""
    parts = []
    if not from_returns.empty:
        f = from_returns.copy()
        f["memo_reason"] = "Goods Returned"
        f["dispute_id"] = 0
        parts.append(f[["invoice_id", "customer_id", "order_id", "memo_date",
                        "memo_amount_usd", "memo_reason", "dispute_id"]])

    if not disputes.empty:
        settled = disputes[disputes["resolution_code"].isin(
            ["Credit Issued", "Partial Credit", "Price Corrected"])].copy()
        if not settled.empty:
            share = np.where(settled["resolution_code"] == "Partial Credit",
                             rng.uniform(0.25, 0.7, len(settled)), 1.0)
            parts.append(pd.DataFrame({
                "invoice_id": settled["invoice_id"].to_numpy(),
                "customer_id": settled["customer_id"].to_numpy(),
                "order_id": settled["order_id"].to_numpy(),
                "memo_date": pd.to_datetime(settled["resolved_date"]
                                            ).to_numpy().astype("datetime64[D]"),
                "memo_amount_usd": np.round(settled["dispute_amount_usd"].to_numpy()
                                            * share, 2),
                "memo_reason": settled["resolution_code"].to_numpy(),
                "dispute_id": settled["dispute_id"].to_numpy(),
            }))
    if not parts:
        return pd.DataFrame()
    memos = pd.concat(parts, ignore_index=True)

    # An invoice can attract both a return credit and a dispute settlement, and
    # nothing stops the two from summing past what was billed. Left uncapped
    # they drive the balance negative, the invoice reads Paid with money still
    # on it, and the ledger check fails - so cap the total credit at the
    # invoice, pro rata across whatever memos it carries.
    owed_by_inv = pd.Series(owed, index=invoices["invoice_id"].to_numpy())
    cap = owed_by_inv.reindex(memos["invoice_id"]).fillna(0.0).to_numpy()
    issued = memos.groupby("invoice_id")["memo_amount_usd"].transform("sum").to_numpy()
    scale = np.where(issued > cap, np.divide(cap, np.maximum(issued, 0.01)), 1.0)
    memos["memo_amount_usd"] = np.round(memos["memo_amount_usd"].to_numpy() * scale, 2)
    memos = memos[memos["memo_amount_usd"] > 0.01].reset_index(drop=True)

    memos.insert(0, "credit_memo_id", np.arange(1, len(memos) + 1, dtype="int32"))
    memos.insert(1, "credit_memo_number",
                 [f"CM-{i:07d}" for i in memos["credit_memo_id"]])
    memos["invoice_id"] = memos["invoice_id"].astype("int32")
    memos["customer_id"] = memos["customer_id"].astype("int32")
    return memos


def _group_into_remittances(s: Scenario, alloc: pd.DataFrame,
                            rng: np.random.Generator):
    """Bundle allocations into customer remittances.

    Customers pay several invoices with one transfer, which is why
    payment-to-invoice is a many-to-many and why `payment_allocations` has to
    exist as a table rather than as an `invoice.paid_amount` column.
    """
    if alloc.empty:
        return pd.DataFrame(), alloc
    lo, hi = s.collections["invoices_per_remittance"]
    alloc = alloc.sort_values(["customer_id", "allocation_date"]).reset_index(drop=True)

    # Same customer, same week, same remittance.
    week = (pd.to_datetime(alloc["allocation_date"]).to_numpy().astype("datetime64[D]")
            .astype("datetime64[W]"))
    alloc["_bucket"] = list(zip(alloc["customer_id"], week))
    codes, _ = pd.factorize(pd.Index(alloc["_bucket"]))
    # Split any bucket that is larger than a plausible remittance.
    within = alloc.groupby(codes).cumcount().to_numpy()
    cap = int(rng.integers(lo, hi + 1))
    payment_key = codes * 1000 + (within // max(cap, 1))
    pcodes, _ = pd.factorize(payment_key)
    alloc["payment_id"] = pcodes + 1

    g = alloc.groupby("payment_id", sort=True)
    pay = g.agg(customer_id=("customer_id", "first"),
                currency_code=("currency_code", "first"),
                payment_date=("allocation_date", "max"),
                payment_amount_usd=("allocated_amount_usd", "sum"),
                invoice_count=("invoice_id", "nunique")).reset_index()
    n = len(pay)
    pay["payment_number"] = [f"PAY-{i:07d}" for i in pay["payment_id"]]
    pay["payment_method"] = rng.choice(R.PAYMENT_METHODS, size=n, p=R.PAYMENT_METHOD_MIX)
    pay["bank_reference"] = [f"BR{int(x):012d}" for x in
                             rng.integers(10 ** 11, 10 ** 12 - 1, n)]
    pay["payment_status"] = "Applied"
    pay["is_unapplied"] = 0
    pay["payment_amount_usd"] = pay["payment_amount_usd"].round(2)
    pay["payment_id"] = pay["payment_id"].astype("int32")
    pay["customer_id"] = pay["customer_id"].astype("int32")

    # A deliberate defect: cash that arrived and was never applied to anything.
    # It inflates the AR balance until someone finds it, which is exactly the
    # kind of thing an exception page should surface.
    dq = s.data_quality
    if dq:
        share = float(dq.get("orphan_remittance_share", 0.0))
        k = int(round(share * n))
        if k > 0:
            pick = rng.choice(n, size=k, replace=False)
            pay.loc[pick, "payment_status"] = "Unapplied"
            pay.loc[pick, "is_unapplied"] = 1
            drop = pay.loc[pick, "payment_id"].to_numpy()
            alloc = alloc[~alloc["payment_id"].isin(drop)].copy()

    allocations = pd.DataFrame({
        "payment_allocation_id": np.arange(1, len(alloc) + 1, dtype="int64"),
        "payment_id": alloc["payment_id"].astype("int32"),
        "invoice_id": alloc["invoice_id"].astype("int32"),
        "customer_id": alloc["customer_id"].astype("int32"),
        "allocated_amount_usd": alloc["allocated_amount_usd"].round(2),
        "allocation_date": alloc["allocation_date"],
        "allocation_sequence": (alloc["leg"] + 1).astype("int8"),
    })
    cols = ["payment_id", "payment_number", "customer_id", "payment_date",
            "payment_amount_usd", "currency_code", "payment_method",
            "bank_reference", "payment_status", "invoice_count", "is_unapplied"]
    return pay[cols], allocations
