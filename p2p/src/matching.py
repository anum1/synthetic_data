"""The match engine, the hold ledger, and invoice approval.

The verdict on every invoice line is COMPUTED here, from the PO price, the
received quantity, the invoiced quantity and the tolerance row that applied. It
is never drawn. That is the whole point: the moment anyone drills from
"exception" to the underlying documents, the numbers have to justify the verdict
or the demo dies at exactly the place it was supposed to land (PLAN 2.3).

Match results and holds are separate tables on purpose. A price variance is a
match outcome; a missing bank account, a duplicate suspicion and an exhausted
budget are not - they are AP holds with their own reason codes and owning teams.
The design note mixed the two taxonomies into one pie chart (PLAN 2.3).

Approval time is computed last because it depends on the holds, and the missed
early-payment discount later depends on approval time. That chain - drift ->
variance -> hold -> slow approval -> missed discount -> late payment - is the
spine of the demo and it has to be generated in that order (PLAN 2.6).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dims import tolerance_lookup
from events import EventPlan
from p2pconfig import Scenario, month_end

# Hold reasons that are raised from the match itself.
MATCH_REASONS = {"price": "PRICE_VAR", "qty": "QTY_VAR", "amount": "AMT_VAR"}


def build_matching(s: Scenario, inv: pd.DataFrame, inv_lines: pd.DataFrame,
                   po: pd.DataFrame, po_lines: pd.DataFrame, sup: pd.DataFrame,
                   banks: pd.DataFrame, contracts: pd.DataFrame,
                   tolerances: pd.DataFrame, hold_reasons: pd.DataFrame,
                   employees: pd.DataFrame, ccs: pd.DataFrame, ep: EventPlan,
                   rng: np.random.Generator):
    """Returns (match_result, invoice_hold, approval_event, invoice)."""
    match = _match_lines(s, inv, inv_lines, tolerances, rng)
    holds = _build_holds(s, inv, inv_lines, match, po, po_lines, sup, banks,
                         contracts, hold_reasons, rng)
    inv, approvals = _approve(s, inv, holds, employees, ep, rng)
    return match, holds, approvals, inv


def _match_lines(s: Scenario, inv: pd.DataFrame, inv_lines: pd.DataFrame,
                 tolerances: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Three-way and two-way match, line by line, against the tolerance policy."""
    src = inv_lines[inv_lines["purchase_order_line_id"] > 0].copy()
    if src.empty:
        return pd.DataFrame()

    tol = tolerance_lookup(tolerances)
    seg = src["segment_name"].to_numpy()

    def tol_col(name: str) -> np.ndarray:
        default = float(tol["*"][name])
        out = np.full(len(src), default)
        for segment, row in tol.items():
            if segment == "*":
                continue
            out[seg == segment] = float(row[name])
        return out

    price_pct = tol_col("price_tolerance_pct")
    price_abs = tol_col("price_tolerance_abs_usd")
    qty_pct = tol_col("qty_tolerance_pct")
    qty_abs = tol_col("qty_tolerance_abs_units")
    cap = tol_col("total_variance_cap_usd")

    tol_id = np.ones(len(src), dtype=np.int64)
    for _, r in tolerances[tolerances["scope_type"] == "Segment"].iterrows():
        tol_id[seg == r["segment_name"]] = int(r["match_tolerance_id"])

    po_price = src["po_unit_price_usd"].to_numpy().astype(float)
    inv_price = src["unit_price_usd"].to_numpy().astype(float)
    qty_inv = src["quantity_invoiced"].to_numpy().astype(float)
    qty_recv = src["quantity_received"].to_numpy().astype(float)
    qty_ord = src["quantity_ordered"].to_numpy().astype(float)
    three = (src["match_type"].to_numpy() == "3-Way")

    # A two-way match has no receipt to compare against, so quantity is checked
    # against what was ordered.
    qty_basis = np.where(three, qty_recv, qty_ord)

    price_var = inv_price - po_price
    price_var_pct = np.divide(price_var, np.maximum(po_price, 1e-9))
    qty_var = qty_inv - qty_basis
    qty_var_pct = np.divide(qty_var, np.maximum(qty_basis, 1e-9))
    amount_var = np.round(qty_inv * inv_price - qty_basis * po_price, 2)

    # Tolerance is the GREATER of the percentage and the absolute allowance -
    # that is how a real ERP is configured, and it is why a $12 variance on a
    # cheap line never raises a hold.
    price_ok = (np.abs(price_var) <= np.maximum(price_pct * np.abs(po_price),
                                                price_abs / np.maximum(qty_inv, 1)))
    qty_ok = np.abs(qty_var) <= np.maximum(qty_pct * np.abs(qty_basis), qty_abs)
    # Under the cap, the difference is written off automatically rather than
    # parked as an exception. AP departments do this constantly and leaving it
    # out inflates the exception rate with rows nobody ever works.
    small = np.abs(amount_var) <= cap
    price_ok = price_ok | small
    qty_ok = qty_ok | small
    amount_ok = np.abs(amount_var) <= np.maximum(cap, 0.02 * np.abs(qty_basis * po_price))

    status = np.select(
        [~price_ok & ~qty_ok, ~price_ok, ~qty_ok, ~amount_ok],
        ["Price and Quantity Variance", "Price Variance", "Quantity Variance",
         "Amount Variance"], default="Matched")
    reason = np.select(
        [~price_ok & ~qty_ok, ~price_ok, ~qty_ok, ~amount_ok],
        ["PRICE_VAR", "PRICE_VAR", "QTY_VAR", "AMT_VAR"], default="")

    out = pd.DataFrame({
        "invoice_id": src["invoice_id"].to_numpy(),
        "invoice_line_id": src["invoice_line_id"].to_numpy(),
        "purchase_order_id": src["purchase_order_id"].to_numpy(),
        "purchase_order_line_id": src["purchase_order_line_id"].to_numpy(),
        "supplier_id": src["supplier_id"].to_numpy(),
        "category_id": src["category_id"].to_numpy(),
        "match_type": src["match_type"].to_numpy(),
        "match_tolerance_id": tol_id,
        "quantity_ordered": qty_ord,
        "quantity_received": qty_recv,
        "quantity_invoiced": qty_inv,
        "po_unit_price_usd": np.round(po_price, 4),
        "invoice_unit_price_usd": np.round(inv_price, 4),
        "price_variance_usd": np.round(price_var * qty_inv, 2),
        "price_variance_pct": np.round(price_var_pct, 5),
        "quantity_variance": np.round(qty_var, 2),
        "quantity_variance_pct": np.round(qty_var_pct, 5),
        "amount_variance_usd": amount_var,
        "is_price_within_tolerance": price_ok.astype("int8"),
        "is_quantity_within_tolerance": qty_ok.astype("int8"),
        "is_amount_within_tolerance": amount_ok.astype("int8"),
        "match_status": status,
        "exception_reason_code": reason,
        "is_auto_write_off": (small & ~(price_ok & qty_ok & amount_ok)).astype("int8"),
    })
    out["is_first_pass_match"] = (out["match_status"] == "Matched").astype("int8")
    out["match_result_id"] = np.arange(1, len(out) + 1, dtype=np.int64)
    return out


def _build_holds(s: Scenario, inv: pd.DataFrame, inv_lines: pd.DataFrame,
                 match: pd.DataFrame, po: pd.DataFrame, po_lines: pd.DataFrame,
                 sup: pd.DataFrame, banks: pd.DataFrame, contracts: pd.DataFrame,
                 hold_reasons: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """The exception ledger. One invoice can carry several holds."""
    reason_id = dict(zip(hold_reasons["hold_reason_code"],
                         hold_reasons["hold_reason_id"]))
    team = dict(zip(hold_reasons["hold_reason_code"], hold_reasons["owning_team"]))
    blocks = dict(zip(hold_reasons["hold_reason_code"], hold_reasons["blocks_payment"]))

    inv_idx = inv.set_index("invoice_id")
    rows: list[pd.DataFrame] = []

    def add(invoice_ids: np.ndarray, code: str) -> None:
        if not len(invoice_ids):
            return
        ids = pd.Index(pd.unique(invoice_ids))
        ids = ids[ids.isin(inv_idx.index)]
        if not len(ids):
            return
        rows.append(pd.DataFrame({
            "invoice_id": ids.to_numpy(),
            "hold_reason_code": code,
            "raised_date": inv_idx.loc[ids, "invoice_received_date"].to_numpy(),
            "blocked_amount_usd": inv_idx.loc[ids, "gross_amount_usd"].to_numpy(),
        }))

    # -- holds that come out of the match -------------------------------------
    if len(match):
        failed = match[match["exception_reason_code"] != ""]
        for code, g in failed.groupby("exception_reason_code"):
            add(g["invoice_id"].to_numpy(), str(code))

        # A three-way invoice with nothing received against the PO line.
        no_recv = match[(match["match_type"] == "3-Way")
                        & (match["quantity_received"] <= 0)]
        add(no_recv["invoice_id"].to_numpy(), "NO_RECEIPT")

    # -- supplier master holds -------------------------------------------------
    no_bank = set(sup["supplier_id"]) - set(banks.loc[banks["is_active"] == 1,
                                                      "supplier_id"])
    # Raised when payment is attempted, not on every invoice received.
    add(inv.loc[inv["supplier_id"].isin(no_bank), "invoice_id"]
        .sample(frac=0.30, random_state=int(s.seed) + 911).to_numpy(),
        "BANK_MISSING")

    blocked_sup = sup.loc[sup["supplier_status"] != "Active", "supplier_id"]
    hit = inv[inv["supplier_id"].isin(blocked_sup)]
    # A supplier being dormant today does not make every invoice it ever raised
    # an exception - only the ones that arrived after it went dormant, and only
    # the share AP actually catches. Flagging a third of all of them put 14,500
    # rows in the hold ledger and pushed the exception rate seven points over.
    hit = hit.sample(frac=0.055, random_state=int(s.seed) + 901)
    add(hit["invoice_id"].to_numpy(), "SUPPLIER_BLOCK")

    no_tax = sup.loc[sup["has_tax_id"] == 0, "supplier_id"]
    hit = inv[inv["supplier_id"].isin(no_tax)].sample(
        frac=0.12, random_state=int(s.seed) + 902)
    add(hit["invoice_id"].to_numpy(), "TAX_ID_MISSING")

    # -- duplicates ------------------------------------------------------------
    dup = inv[inv["is_duplicate_suspect"] == 1]
    # Most are caught; the ones that are not get PAID, and that is the money line.
    caught = dup.sample(frac=0.90, random_state=int(s.seed) + 903)
    add(caught["invoice_id"].to_numpy(), "DUP_SUSPECT")

    # -- coding and approval holds on non-PO invoices --------------------------
    non_po = inv[inv["is_non_po"] == 1]
    add(non_po.sample(frac=0.11, random_state=int(s.seed) + 904)["invoice_id"]
        .to_numpy(), "GL_CODING")
    add(non_po.sample(frac=0.07, random_state=int(s.seed) + 905)["invoice_id"]
        .to_numpy(), "COST_CENTER")
    add(non_po.sample(frac=0.05, random_state=int(s.seed) + 906)["invoice_id"]
        .to_numpy(), "BUDGET")

    # -- contract expired before the invoice date ------------------------------
    if len(contracts):
        last_ctr = (contracts.sort_values("contract_end_date")
                    .drop_duplicates("supplier_id", keep="last")
                    .set_index("supplier_id")["contract_end_date"])
        end = pd.to_datetime(inv["supplier_id"].map(last_ctr))
        expired = (end.notna()
                   & (pd.to_datetime(inv["invoice_date"]) > end)).to_numpy()
        pick = inv[expired].sample(frac=0.22, random_state=int(s.seed) + 907)
        add(pick["invoice_id"].to_numpy(), "CONTRACT_EXP")

    # -- invoice dated before the goods arrived --------------------------------
    if len(match):
        early = inv[inv["invoice_id"].isin(
            match.loc[match["quantity_received"] > 0, "invoice_id"])]
        early = early.sample(frac=0.016, random_state=int(s.seed) + 908)
        add(early["invoice_id"].to_numpy(), "EARLY_INVOICE")

    if not rows:
        return pd.DataFrame()

    holds = pd.concat(rows, ignore_index=True)
    holds = holds.drop_duplicates(["invoice_id", "hold_reason_code"]).reset_index(
        drop=True)

    holds["hold_reason_id"] = holds["hold_reason_code"].map(reason_id).astype("int64")
    holds["owning_team"] = holds["hold_reason_code"].map(team)
    holds["blocks_payment"] = holds["hold_reason_code"].map(blocks).astype("int8")

    # -- resolution ------------------------------------------------------------
    mu, sd = s.approval["hold_resolution_days_lognorm"]
    n = len(holds)
    days = np.round(np.exp(rng.normal(mu, sd, size=n)))
    raised = pd.to_datetime(holds["raised_date"])
    released = raised + pd.to_timedelta(days, unit="D")
    still_open = released > pd.Timestamp(s.timeline.as_of_date)
    # Keep a real datetime column for the arithmetic. Mixing NaT with
    # datetime.date in one object column makes every later max() and comparison
    # fail on "'>=' not supported between float and datetime.date".
    holds["_released_ts"] = released.where(~still_open)
    holds["is_open"] = still_open.astype("int8")
    holds["days_held"] = np.where(
        still_open,
        (pd.Timestamp(s.timeline.as_of_date) - raised).dt.days, days).astype("int32")
    holds["resolution"] = np.where(
        still_open, "Open",
        np.where(rng.random(n) < float(s.approval["hold_write_off_share"]),
                 "Written off", "Corrected and released"))
    holds["invoice_hold_id"] = np.arange(1, n + 1, dtype=np.int64)
    holds["raised_date"] = pd.to_datetime(holds["raised_date"]).dt.date
    holds["released_date"] = holds["_released_ts"].dt.date
    return holds


def _approve(s: Scenario, inv: pd.DataFrame, holds: pd.DataFrame,
             employees: pd.DataFrame, ep: EventPlan, rng: np.random.Generator):
    """Invoice approval time - and therefore the discount window.

    Event 6 lives here. One department's approval time ramps from nine days to
    twenty-four, and because the discount window closes on day ten, that single
    change is what produces most of Event 8's missed discount. Generating them
    independently would leave the demo asserting a causal link the data does not
    contain (PLAN 2.6).
    """
    inv = inv.copy()
    n = len(inv)
    ap = s.approval
    mu, sd = ap["invoice_approval_days_lognorm"]
    days = np.exp(rng.normal(mu, sd, size=n))
    days = days + np.where(inv["is_non_po"].to_numpy() == 1,
                           float(ap["non_po_extra_approval_days"]), 0.0)

    # -- Event 6: one department deteriorates ---------------------------------
    ev = s.event("approval_slowdown")
    if ev is not None and len(ep.slow_approval_departments):
        hot = inv["department_id"].isin(ep.slow_approval_departments).to_numpy()
        r = ep.ramp_series("approval_slowdown", inv["invoice_date"].to_numpy())
        frm, to = float(ev["days_from"]), float(ev["days_to"])
        target = frm + (to - frm) * r
        # Scale the individual draw to the department's current average rather
        # than replacing it, so the spread survives.
        days = np.where(hot, days * (target / max(float(np.exp(mu)), 0.1)) * 0.55,
                        days)

    # -- an approver on leave, which shows up as a seasonal spike --------------
    inv_month = pd.to_datetime(inv["invoice_date"])
    absent = ((inv_month >= pd.Timestamp(ep.absence_start))
              & (inv_month <= pd.Timestamp(ep.absence_end))).to_numpy()
    days = days + np.where(absent & (rng.random(n) < 0.22),
                           rng.uniform(3, 14, size=n), 0.0)

    # -- a held invoice is not approved until the hold is released ------------
    inv["days_to_approve"] = np.round(days, 1)
    received = pd.to_datetime(inv["invoice_received_date"])
    approve_date = received + pd.to_timedelta(np.round(days), unit="D")

    if len(holds):
        blocking = holds[holds["blocks_payment"] == 1]
        last_release = blocking.groupby("invoice_id")["_released_ts"].max()
        open_hold = (blocking.groupby("invoice_id")["is_open"].max())
        rel = pd.to_datetime(inv["invoice_id"].map(last_release))
        has_open = inv["invoice_id"].map(open_hold).fillna(0).to_numpy() == 1
        approve_date = pd.Series(
            np.maximum(approve_date.to_numpy(),
                       rel.fillna(approve_date).to_numpy()))
        inv["has_open_hold"] = has_open.astype("int8")
        hold_ct = holds.groupby("invoice_id").size()
        inv["hold_count"] = inv["invoice_id"].map(hold_ct).fillna(0).astype("int16")
    else:
        inv["has_open_hold"] = 0
        inv["hold_count"] = 0

    # A duplicate that AP caught is killed, not approved late. Leaving it to be
    # approved once its hold releases meant 409 of 412 suspected duplicates were
    # ultimately paid, which inverts the whole point of the story.
    killed = np.zeros(len(inv), dtype=bool)
    if len(holds):
        dup_held = set(holds.loc[holds["hold_reason_code"] == "DUP_SUSPECT",
                                 "invoice_id"])
        is_dup_held = inv["invoice_id"].isin(dup_held).to_numpy()
        killed = is_dup_held & (rng.random(n) < 0.94)

    not_yet = (approve_date > pd.Timestamp(s.timeline.as_of_date)) \
        | (inv["has_open_hold"].to_numpy() == 1) | killed
    inv["approval_date"] = np.where(not_yet, pd.NaT,
                                    pd.to_datetime(approve_date).dt.date)
    inv["approval_status"] = np.where(killed, "Rejected - Duplicate",
                                      np.where(not_yet, "Pending Approval",
                                               "Approved"))
    inv["days_to_approve"] = np.where(
        not_yet, np.nan,
        (pd.to_datetime(inv["approval_date"]) - received).dt.days)
    inv["is_straight_through"] = ((inv["hold_count"].to_numpy() == 0)
                                  & (inv["is_non_po"].to_numpy() == 0)
                                  & (inv["approval_status"].to_numpy() == "Approved")
                                  ).astype("int8")

    approvals = _approval_events(s, inv, holds, employees, rng)
    return inv, approvals


def _approval_events(s: Scenario, inv: pd.DataFrame, holds: pd.DataFrame,
                     employees: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Workflow steps across every document type.

    Polymorphic on purpose: requisitions, POs and invoices all route through the
    same workflow, and "which approver is the bottleneck" is unanswerable if the
    events live in three different tables (PLAN 2.9).
    """
    approvers = employees[employees["is_approver"] == 1]
    if not len(approvers) or inv.empty:
        return pd.DataFrame()
    done = inv[inv["approval_status"] == "Approved"]
    if done.empty:
        return pd.DataFrame()

    # One or two steps per invoice - larger invoices escalate.
    steps = np.where(done["gross_amount_usd"].to_numpy() > 25_000, 2, 1)
    idx = np.repeat(np.arange(len(done)), steps)
    src = done.iloc[idx].reset_index(drop=True)
    step_no = np.concatenate([np.arange(1, k + 1) for k in steps])

    a = approvers.sample(n=len(src), replace=True,
                         random_state=int(s.seed) + 910).reset_index(drop=True)
    received = pd.to_datetime(src["invoice_received_date"])
    total = pd.to_datetime(src["approval_date"]) - received
    frac = np.where(step_no == 1, 0.55, 1.0)
    acted = received + pd.to_timedelta(
        (total.dt.days.to_numpy() * frac).round(), unit="D")

    delegated = rng.random(len(src)) < float(s.approval["delegation_share"])
    out = pd.DataFrame({
        "approval_event_id": np.arange(1, len(src) + 1, dtype=np.int64),
        "document_type": "Invoice",
        "document_id": src["invoice_id"].to_numpy(),
        "document_number": src["invoice_number"].to_numpy(),
        "step_number": step_no.astype("int8"),
        "approver_employee_id": a["employee_id"].to_numpy(),
        "approver_role": a["role_name"].to_numpy(),
        "queue_entered_date": received.dt.date.to_numpy(),
        "action_date": pd.to_datetime(acted).dt.date,
        "action_taken": "Approved",
        "days_in_queue": (pd.to_datetime(acted) - received).dt.days.astype("int32"),
        "is_delegated": delegated.astype("int8"),
        "delegated_from_employee_id": np.where(
            delegated, a["manager_employee_id"].to_numpy(), 0),
        "company_code": src["company_code"].to_numpy(),
        "department_id": src["department_id"].to_numpy(),
        "document_amount_usd": src["gross_amount_usd"].to_numpy(),
    })
    _ = month_end
    return out
