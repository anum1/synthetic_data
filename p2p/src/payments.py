"""Pay runs, discount capture and the invoice-to-payment bridge.

Payments are PAY RUNS. A weekly run covers many invoices, which is why the
payment count is a third of the invoice count and why `fact_payment_application`
has to exist: without an invoice-to-payment bridge there is no partial payment,
no discount taken, no DPO and no answer to "what did this $840K cover" (PLAN 2.4).

The discount logic is the payoff of the whole causal chain. An invoice is only
eligible for its early-payment discount if it was APPROVED before the discount
window closed. Approval takes eleven days on average and the window is ten, so
most of the missed discount is not treasury being slow - it is AP being slow,
and the two events are the same event (PLAN 2.6).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario

METHOD_ORDER = ["ACH", "Wire", "Check", "Card"]


def build_payments(s: Scenario, inv: pd.DataFrame, sup: pd.DataFrame,
                   banks: pd.DataFrame, fx: pd.DataFrame, ep: EventPlan,
                   rng: np.random.Generator):
    """Returns (payment, payment_application, invoice)."""
    pay = s.payment
    tl = s.timeline
    inv = inv.copy()

    payable = inv[(inv["approval_status"] == "Approved")
                  & (inv["invoice_type"] == "Standard Invoice")].copy()
    if payable.empty:
        inv["payment_status"] = "Unpaid"
        return pd.DataFrame(), pd.DataFrame(), inv

    approved = pd.to_datetime(payable["approval_date"])
    due = pd.to_datetime(payable["due_date"])
    disc_due = pd.to_datetime(payable["discount_due_date"])
    n = len(payable)

    # -- when we intend to pay -------------------------------------------------
    #
    # Policy is to pay on the due date. A minority pay early; a minority slip.
    u = rng.random(n)
    early_lo, early_hi = pay["early_days_range"]
    p_on_due = float(pay["pay_on_due_date_share"])
    p_late = float(pay["late_share"])
    mu_l, sd_l = pay["late_days_lognorm"]
    late_days = np.round(np.exp(rng.normal(mu_l, sd_l, size=n)))

    intent = np.where(
        u < p_late, due + pd.to_timedelta(late_days, unit="D"),
        np.where(u < p_late + p_on_due, due,
                 due - pd.to_timedelta(
                     rng.integers(early_lo, early_hi + 1, size=n), unit="D")))
    intent = pd.to_datetime(pd.Series(intent, index=payable.index))

    # -- discount capture ------------------------------------------------------
    #
    # Eligible only if the discount window is still open AND the invoice was
    # approved before it closed. That second condition is the whole story.
    eligible_terms = payable["discount_percent"].to_numpy() > 0
    approved_in_time = (approved <= disc_due).to_numpy()
    take = eligible_terms & approved_in_time & (rng.random(n) < 0.86)
    # Taking the discount pulls the payment date back to the discount due date.
    # pd.to_datetime on an ndarray returns a DatetimeIndex, which has no .dt
    # accessor; keep it a Series so the pay-run snap below works.
    pay_date = pd.Series(pd.to_datetime(np.where(take, disc_due, intent)),
                         index=payable.index)

    # -- Event 9: the suppliers we serve worst pay later still ----------------
    ev = s.event("late_payment")
    if ev is not None and len(ep.late_paid_suppliers):
        hot = payable["supplier_id"].isin(ep.late_paid_suppliers).to_numpy()
        r = ep.ramp_series("late_payment", payable["invoice_date"].to_numpy())
        extra = np.round(float(ev["extra_days_late"]) * r)
        pay_date = pay_date + pd.to_timedelta(np.where(hot, extra, 0), unit="D")
        take = take & ~hot

    # -- the pay run calendar --------------------------------------------------
    #
    # Cash leaves on a run day, not on the day AP would have liked. AP schedules
    # an invoice into the last run that lands ON OR BEFORE its intended date -
    # snapping FORWARD instead pushes every on-due-date invoice up to six days
    # past due and produces a 71% late-payment rate against a target of 11%.
    # Invoices already intended late still slip to the following run.
    weekday = int(pay["pay_run_weekday"])
    cadence_days = max(1, int(round(28 / max(int(pay["pay_runs_per_month"]), 1))))
    epoch = pd.Timestamp(tl.start_date)
    epoch = epoch + pd.Timedelta(days=int((weekday - epoch.weekday() + 7) % 7))
    since = (pay_date - epoch).dt.days
    back = epoch + pd.to_timedelta(
        np.floor(since / cadence_days) * cadence_days, unit="D")
    fwd = back + pd.Timedelta(days=cadence_days)
    intended_late = (pay_date > due).to_numpy()
    run_date = pd.Series(np.where(intended_late, fwd, back), index=payable.index)
    run_date = pd.to_datetime(run_date)
    # Never before the invoice was approved - cash cannot leave first.
    run_date = pd.Series(np.maximum(run_date.to_numpy(), approved.to_numpy()),
                         index=payable.index)

    unpaid = run_date > pd.Timestamp(tl.as_of_date)
    paid = ~unpaid
    payable = payable.assign(_run_date=run_date, _take_discount=take & paid)

    inv["payment_status"] = "Unpaid"
    inv.loc[inv["invoice_id"].isin(payable.loc[paid, "invoice_id"]),
            "payment_status"] = "Paid"
    inv.loc[(inv["approval_status"] != "Approved"), "payment_status"] = \
        "Pending Approval"

    settled = payable[paid].copy()
    if settled.empty:
        return pd.DataFrame(), pd.DataFrame(), inv

    # -- group into runs: one payment per supplier per run date ---------------
    settled["_pay_seq"] = settled.groupby(
        ["supplier_id", "company_code", "_run_date"], sort=False).ngroup()

    disc_pct = settled["discount_percent"].to_numpy()
    gross = settled["gross_amount_usd"].to_numpy()
    discount = np.where(settled["_take_discount"].to_numpy(),
                        np.round(gross * disc_pct, 2), 0.0)

    # A small share are settled in part - the rest stays open on the ledger.
    partial = rng.random(len(settled)) < float(pay["partial_payment_share"])
    applied = np.where(partial, np.round(gross * rng.uniform(0.35, 0.85,
                                                            len(settled)), 2),
                       gross - discount)

    apps = pd.DataFrame({
        "_pay_seq": settled["_pay_seq"].to_numpy(),
        "invoice_id": settled["invoice_id"].to_numpy(),
        "supplier_id": settled["supplier_id"].to_numpy(),
        "invoice_gross_usd": gross,
        "applied_amount_usd": applied,
        "discount_taken_usd": discount,
        "invoice_date": settled["invoice_date"].to_numpy(),
        "due_date": settled["due_date"].to_numpy(),
        "payment_date": settled["_run_date"].to_numpy(),
        "is_partial_settlement": partial.astype("int8"),
    })
    apps["days_from_due"] = (pd.to_datetime(apps["payment_date"])
                             - pd.to_datetime(apps["due_date"])).dt.days.astype("int32")
    apps["is_paid_late"] = (apps["days_from_due"] > 0).astype("int8")
    apps["days_to_pay"] = (pd.to_datetime(apps["payment_date"])
                           - pd.to_datetime(apps["invoice_date"])).dt.days.astype("int32")

    # -- payment headers -------------------------------------------------------
    head = (apps.groupby("_pay_seq")
            .agg(supplier_id=("supplier_id", "first"),
                 payment_date=("payment_date", "first"),
                 invoice_count=("invoice_id", "count"),
                 payment_amount_usd=("applied_amount_usd", "sum"),
                 discount_taken_usd=("discount_taken_usd", "sum"))
            .reset_index())
    head["payment_id"] = np.arange(1, len(head) + 1, dtype=np.int64)
    head["payment_number"] = [f"PAY-{i:07d}" for i in head["payment_id"]]

    meth = pay["methods"]
    codes = [m for m in METHOD_ORDER if m in meth]
    probs = np.array([float(meth[m]) for m in codes])
    probs = probs / probs.sum()
    head["payment_method"] = rng.choice(codes, size=len(head), p=probs)
    head["payment_run_id"] = pd.factorize(
        pd.to_datetime(head["payment_date"]).dt.date)[0] + 1

    sup_idx = sup.set_index("supplier_id")
    head["currency_code"] = sup_idx.loc[head["supplier_id"],
                                        "currency_code"].to_numpy()
    head["company_code"] = (settled.drop_duplicates("_pay_seq")
                            .set_index("_pay_seq")
                            .loc[head["_pay_seq"], "company_code"].to_numpy())
    bank_first = banks.sort_values("is_primary_account", ascending=False) \
        .drop_duplicates("supplier_id").set_index("supplier_id")["bank_account_id"]
    head["bank_account_id"] = (head["supplier_id"].map(bank_first)
                               .fillna(0).astype("int64"))

    head["_rate_date"] = pd.to_datetime(head["payment_date"]).dt.date
    head = head.merge(fx[["currency_code", "rate_date", "rate_to_usd"]],
                      left_on=["currency_code", "_rate_date"],
                      right_on=["currency_code", "rate_date"], how="left")
    head["exchange_rate"] = head["rate_to_usd"].fillna(1.0)
    head["payment_amount_local"] = np.round(
        head["payment_amount_usd"] / head["exchange_rate"], 2)
    head = head.drop(columns=["_rate_date", "rate_date", "rate_to_usd"])

    id_map = dict(zip(head["_pay_seq"], head["payment_id"]))
    apps["payment_id"] = apps["_pay_seq"].map(id_map).astype("int64")
    apps["payment_application_id"] = np.arange(1, len(apps) + 1, dtype=np.int64)
    apps = apps.drop(columns=["_pay_seq"])
    head = head.drop(columns=["_pay_seq"])
    head["payment_date"] = pd.to_datetime(head["payment_date"]).dt.date
    for c in ("invoice_date", "due_date", "payment_date"):
        apps[c] = pd.to_datetime(apps[c]).dt.date

    inv = _close_the_ledger(s, inv, apps)
    _ = dt
    return head, apps, inv


def _close_the_ledger(s: Scenario, inv: pd.DataFrame,
                      apps: pd.DataFrame) -> pd.DataFrame:
    """The AP subledger identity, computed rather than drawn.

        open = gross - applied - discount taken - credit memos

    validate.py asserts this to the cent at every month end. On the Vantage
    build the equivalent check caught three separate bugs (PLAN 2.4).
    """
    inv = inv.copy()
    applied = apps.groupby("invoice_id")["applied_amount_usd"].sum()
    discount = apps.groupby("invoice_id")["discount_taken_usd"].sum()
    inv["amount_paid_usd"] = inv["invoice_id"].map(applied).fillna(0.0)
    inv["discount_taken_usd"] = inv["invoice_id"].map(discount).fillna(0.0)
    inv["open_amount_usd"] = np.round(
        inv["gross_amount_usd"] - inv["amount_paid_usd"]
        - inv["discount_taken_usd"], 2)
    # A credit memo is negative and is settled the same way; it never sits open.
    memo = inv["invoice_type"].to_numpy() == "Credit Memo"
    inv.loc[memo, "open_amount_usd"] = 0.0
    inv["is_open"] = ((inv["open_amount_usd"].abs() > 0.005) & ~memo).astype("int8")
    inv["payment_status"] = np.where(
        memo, "Credit Memo",
        np.where(inv["is_open"] == 0, "Paid",
                 np.where(inv["amount_paid_usd"] > 0, "Partially Paid",
                          inv["payment_status"])))

    as_of = pd.Timestamp(s.timeline.as_of_date)
    due = pd.to_datetime(inv["due_date"])
    inv["days_past_due"] = np.where(inv["is_open"] == 1,
                                    (as_of - due).dt.days, 0).astype("int32")
    inv["is_overdue"] = ((inv["is_open"] == 1)
                         & (inv["days_past_due"] > 0)).astype("int8")

    # Discount left on the table: eligible terms, window closed, never taken.
    eligible = inv["discount_percent"].to_numpy() > 0
    inv["discount_available_usd"] = np.round(
        np.where(eligible, inv["gross_amount_usd"] * inv["discount_percent"], 0.0), 2)
    inv["discount_missed_usd"] = np.round(
        np.where(eligible & (inv["discount_taken_usd"] <= 0),
                 inv["discount_available_usd"], 0.0), 2)
    # Why it was missed: approval landed after the window closed, or it did not.
    approved = pd.to_datetime(inv["approval_date"])
    disc_due = pd.to_datetime(inv["discount_due_date"])
    inv["missed_due_to_approval"] = (
        (inv["discount_missed_usd"] > 0)
        & (approved.isna() | (approved > disc_due))).astype("int8")
    return inv
