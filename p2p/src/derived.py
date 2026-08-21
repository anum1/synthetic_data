"""The four derived tables that make the demo fast and consistent.

`fact_spend` unifies the three channels into one line-grain table with the
contract and maverick classification carried down, so the executive page is a
single-table scan rather than a six-way join while an audience watches.

`fact_p2p_cycle` carries every milestone date for one chain on one row, so the
seventy-three-day cycle and its six legs are a subtraction rather than a
correlated subquery.

`fact_p2p_exception` is the unified exception centre across every stage - match
variances, holds, GR/IR, overdue invoices and stalled receipts in one list with
a value and an owner, which is the view AP actually works from.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from p2pconfig import Scenario


def build_spend(s: Scenario, inv: pd.DataFrame, inv_lines: pd.DataFrame,
                pcard: pd.DataFrame, po: pd.DataFrame, po_lines: pd.DataFrame,
                cats: pd.DataFrame, sup: pd.DataFrame,
                contract_price: pd.DataFrame) -> pd.DataFrame:
    """One row per unit of spend, across PO, non-PO and card channels."""
    cp = set(zip(contract_price["supplier_id"].to_numpy(),
                 contract_price["category_id"].to_numpy()))

    ih = inv.set_index("invoice_id")
    src = inv_lines[inv_lines["invoice_id"].isin(ih.index)].copy()
    keep = src["invoice_id"].to_numpy()
    std = ih["invoice_type"].reindex(keep).to_numpy() == "Standard Invoice"
    src = src[std]
    keep = src["invoice_id"].to_numpy()

    spend = pd.DataFrame({
        "spend_channel": np.where(src["match_type"].to_numpy() == "Non-PO",
                                  "Non-PO Invoice", "PO Invoice"),
        "source_document": "Invoice",
        "source_id": src["invoice_id"].to_numpy(),
        "source_line_id": src["invoice_line_id"].to_numpy(),
        "purchase_order_id": src["purchase_order_id"].to_numpy(),
        "supplier_id": src["supplier_id"].to_numpy(),
        "category_id": src["category_id"].to_numpy(),
        "item_id": src["item_id"].to_numpy(),
        "department_id": src["department_id"].to_numpy(),
        "cost_center_id": src["cost_center_id"].to_numpy(),
        "gl_account_id": src["gl_account_id"].to_numpy(),
        "segment_name": src["segment_name"].to_numpy(),
        "spend_date": pd.to_datetime(
            ih["invoice_date"].reindex(keep)).dt.date.to_numpy(),
        "company_code": ih["company_code"].reindex(keep).to_numpy(),
        "spend_amount_usd": src["line_amount_usd"].to_numpy(),
        "match_type": src["match_type"].to_numpy(),
    })

    if len(pcard):
        card = pd.DataFrame({
            "spend_channel": "P-Card",
            "source_document": "Card Transaction",
            "source_id": pcard["pcard_transaction_id"].to_numpy(),
            "source_line_id": pcard["pcard_transaction_id"].to_numpy(),
            "purchase_order_id": 0,
            "supplier_id": pcard["supplier_id"].to_numpy(),
            "category_id": pcard["category_id"].to_numpy(),
            "item_id": 0,
            "department_id": pcard["department_id"].to_numpy(),
            "cost_center_id": pcard["cost_center_id"].to_numpy(),
            "gl_account_id": 0,
            "segment_name": pcard["segment_name"].to_numpy(),
            "spend_date": pd.to_datetime(pcard["transaction_date"]).dt.date.to_numpy(),
            "company_code": pcard["company_code"].to_numpy(),
            "spend_amount_usd": pcard["amount_usd"].to_numpy(),
            "match_type": "P-Card",
        })
        spend = pd.concat([spend, card], ignore_index=True)

    # Contract and maverick classification, carried onto every line so the
    # spend-control waterfall is a GROUP BY rather than a chain of joins.
    pairs = list(zip(spend["supplier_id"].to_numpy(), spend["category_id"].to_numpy()))
    spend["is_contract_available"] = [int((int(a), int(b)) in cp) for a, b in pairs]
    on_po = spend["spend_channel"].to_numpy() == "PO Invoice"
    spend["is_maverick_spend"] = (
        (spend["is_contract_available"].to_numpy() == 1) & ~on_po).astype("int8")
    spend["spend_class"] = np.select(
        [spend["is_maverick_spend"].to_numpy() == 1,
         on_po & (spend["is_contract_available"].to_numpy() == 1),
         on_po],
        ["Maverick", "Contracted on PO", "Non-contracted on PO"],
        default="Unmanaged")
    spend["spend_id"] = np.arange(1, len(spend) + 1, dtype=np.int64)
    return spend


def build_budget(s: Scenario, spend: pd.DataFrame, ccs: pd.DataFrame,
                 depts: pd.DataFrame, ep, rng) -> pd.DataFrame:
    """Procurement budget at cost centre x fiscal month.

    Built BACKWARDS from actual spend, so budget variance is a real number
    rather than two unrelated draws subtracted from one another. The departments
    carrying the maverick spend are the ones that overrun, which is the join the
    savings page turns on: unmanaged spend and budget overrun are the same
    problem seen from two sides.
    """
    if spend.empty:
        return pd.DataFrame()
    sp = spend.copy()
    sp["_month"] = pd.to_datetime(sp["spend_date"]).dt.to_period("M")
    actual = (sp.groupby(["cost_center_id", "_month"], as_index=False)
              ["spend_amount_usd"].sum()
              .rename(columns={"spend_amount_usd": "actual_spend_usd"}))
    actual = actual[actual["cost_center_id"] > 0]
    if actual.empty:
        return pd.DataFrame()

    cc_idx = ccs.set_index("cost_center_id")
    actual["department_id"] = actual["cost_center_id"].map(
        cc_idx["department_id"]).fillna(0).astype("int64")
    actual["company_code"] = actual["cost_center_id"].map(cc_idx["company_code"])

    n = len(actual)
    # Most cost centres come in a little under. The maverick departments run over.
    hot = actual["department_id"].isin(getattr(ep, "maverick_departments", [])) \
        .to_numpy()
    ratio = np.where(hot, rng.uniform(0.74, 0.95, size=n),
                     rng.uniform(0.96, 1.22, size=n))
    actual["budget_amount_usd"] = np.round(
        actual["actual_spend_usd"].to_numpy() * ratio, 2)
    actual["variance_usd"] = np.round(
        actual["budget_amount_usd"] - actual["actual_spend_usd"], 2)
    actual["variance_pct"] = np.round(
        actual["variance_usd"] / np.maximum(actual["budget_amount_usd"], 1.0), 4)
    actual["is_over_budget"] = (actual["variance_usd"] < 0).astype("int8")

    actual["fiscal_period_start"] = actual["_month"].dt.start_time.dt.date
    actual["fiscal_period_name"] = actual["_month"].astype(str)
    actual["fiscal_year"] = actual["_month"].dt.year.astype("int16")
    actual["budget_id"] = np.arange(1, n + 1, dtype=np.int64)
    return actual.drop(columns=["_month"])


def build_p2p_cycle(s: Scenario, req: pd.DataFrame, req_lines: pd.DataFrame,
                    po: pd.DataFrame, po_lines: pd.DataFrame,
                    gr_lines: pd.DataFrame, inv: pd.DataFrame,
                    inv_lines: pd.DataFrame, apps: pd.DataFrame) -> pd.DataFrame:
    """One row per invoice, carrying every milestone in its chain.

    The six legs of the cycle, and which side of the relationship owns each, are
    the reframing in PLAN 2.5: of seventy-three days, nineteen are ours.
    """
    if inv.empty:
        return pd.DataFrame()
    base = inv[["invoice_id", "invoice_number", "supplier_id", "purchase_order_id",
                "company_code", "department_id", "match_type", "invoice_date",
                "invoice_received_date", "approval_date", "due_date",
                "gross_amount_usd", "is_non_po"]].copy()
    base = base[inv["invoice_type"].to_numpy() == "Standard Invoice"]

    po_idx = po.set_index("purchase_order_id")
    base["po_date"] = pd.to_datetime(
        base["purchase_order_id"].map(po_idx["po_date"]))

    # Requisition milestones come through the PO's first line.
    first_line = po_lines.drop_duplicates("purchase_order_id").set_index(
        "purchase_order_id")
    req_line_id = base["purchase_order_id"].map(first_line["requisition_line_id"])
    rl_idx = req_lines.set_index("requisition_line_id")
    req_id = req_line_id.map(rl_idx["requisition_id"]) if len(req_lines) else None
    r_idx = req.set_index("requisition_id")
    base["requisition_id"] = req_id.fillna(0).astype("int64") if req_id is not None else 0
    base["requisition_date"] = pd.to_datetime(
        base["requisition_id"].map(r_idx["requisition_date"]))
    base["requisition_approval_date"] = pd.to_datetime(
        base["requisition_id"].map(r_idx["approval_date"]))

    if len(gr_lines):
        # to_datetime before the aggregation: a left merge introduces NaN into a
        # datetime.date column, and min() over the resulting object dtype fails
        # on "'<=' not supported between datetime.date and float".
        recv_by_line = (pd.to_datetime(gr_lines["receipt_date"])
                        .groupby(gr_lines["purchase_order_line_id"]).min()
                        .rename("recv"))
        first_recv = (inv_lines[inv_lines["purchase_order_line_id"] > 0]
                      .merge(recv_by_line, left_on="purchase_order_line_id",
                             right_index=True, how="left")
                      .groupby("invoice_id")["recv"].min())
        base["receipt_date"] = pd.to_datetime(base["invoice_id"].map(first_recv))
    else:
        base["receipt_date"] = pd.NaT

    if len(apps):
        paid = (pd.to_datetime(apps["payment_date"])
                .groupby(apps["invoice_id"]).max())
        base["payment_date"] = pd.to_datetime(base["invoice_id"].map(paid))
    else:
        base["payment_date"] = pd.NaT

    def legs(a, b):
        return (pd.to_datetime(base[b]) - pd.to_datetime(base[a])).dt.days

    base["days_req_to_req_approved"] = legs("requisition_date",
                                            "requisition_approval_date")
    base["days_req_approved_to_po"] = legs("requisition_approval_date", "po_date")
    base["days_po_to_receipt"] = legs("po_date", "receipt_date")
    base["days_receipt_to_invoice"] = legs("receipt_date", "invoice_received_date")
    base["days_invoice_to_approved"] = legs("invoice_received_date", "approval_date")
    base["days_approved_to_paid"] = legs("approval_date", "payment_date")
    base["days_req_to_cash"] = legs("requisition_date", "payment_date")

    # Whose time is it. This split is what makes the cycle-time slide land, so
    # the three components MUST sum to the total.
    #
    # A two-way line has no receipt, so po->receipt and receipt->invoice are both
    # null for it. Filling those with zero drops the entire PO-to-invoice span
    # out of the supplier's column and the three parts stop adding up to the
    # seventy-five days on the tile. Measure the supplier leg end to end instead
    # and let the receipt split it only where a receipt exists.
    base["days_po_to_invoice"] = legs("po_date", "invoice_received_date")
    has_receipt = base["receipt_date"].notna()
    base["days_supplier"] = np.where(
        has_receipt,
        base["days_po_to_receipt"].fillna(0) + base["days_receipt_to_invoice"].fillna(0),
        base["days_po_to_invoice"].fillna(0))
    base["days_controllable"] = (base["days_req_to_req_approved"].fillna(0)
                                 + base["days_req_approved_to_po"].fillna(0)
                                 + base["days_invoice_to_approved"].fillna(0))
    base["days_terms"] = base["days_approved_to_paid"]

    for c in ("requisition_date", "requisition_approval_date", "po_date",
              "receipt_date", "payment_date"):
        base[c] = pd.to_datetime(base[c]).dt.date
    base["p2p_cycle_id"] = np.arange(1, len(base) + 1, dtype=np.int64)
    return base


def build_exceptions(s: Scenario, inv: pd.DataFrame, holds: pd.DataFrame,
                     match: pd.DataFrame, po_lines: pd.DataFrame,
                     sup: pd.DataFrame) -> pd.DataFrame:
    """Every open exception across the process, with a value and an owner."""
    as_of = pd.Timestamp(s.timeline.as_of_date)
    frames = []

    if len(holds):
        open_h = holds[holds["is_open"] == 1]
        frames.append(pd.DataFrame({
            "exception_type": open_h["hold_reason_code"].to_numpy(),
            "exception_stage": "Invoice",
            "entity_type": "Invoice",
            "entity_id": open_h["invoice_id"].to_numpy(),
            "supplier_id": open_h["invoice_id"].map(
                inv.set_index("invoice_id")["supplier_id"]).to_numpy(),
            "exception_value_usd": open_h["blocked_amount_usd"].to_numpy(),
            "age_days": open_h["days_held"].to_numpy(),
            "owning_team": open_h["owning_team"].to_numpy(),
        }))

    if len(po_lines):
        gr_ir = po_lines[po_lines["gr_ir_amount_usd"] > 0]
        if len(gr_ir):
            age = (as_of - pd.to_datetime(gr_ir["po_date"])).dt.days
            frames.append(pd.DataFrame({
                "exception_type": "GR_IR",
                "exception_stage": "Receipt",
                "entity_type": "PO Line",
                "entity_id": gr_ir["purchase_order_line_id"].to_numpy(),
                "supplier_id": gr_ir["supplier_id"].to_numpy(),
                "exception_value_usd": gr_ir["gr_ir_amount_usd"].to_numpy(),
                "age_days": age.to_numpy(),
                "owning_team": "Receiving",
            }))
        stalled = po_lines[po_lines["receipt_state"] == "Overdue Receipt"]
        if len(stalled):
            age = (as_of - pd.to_datetime(stalled["expected_receipt_date"])).dt.days
            frames.append(pd.DataFrame({
                "exception_type": "OVERDUE_RECEIPT",
                "exception_stage": "Receipt",
                "entity_type": "PO Line",
                "entity_id": stalled["purchase_order_line_id"].to_numpy(),
                "supplier_id": stalled["supplier_id"].to_numpy(),
                "exception_value_usd": stalled["open_commitment_usd"].to_numpy(),
                "age_days": age.to_numpy(),
                "owning_team": "Procurement",
            }))

    overdue = inv[(inv["is_overdue"] == 1)]
    if len(overdue):
        frames.append(pd.DataFrame({
            "exception_type": "OVERDUE_INVOICE",
            "exception_stage": "Payment",
            "entity_type": "Invoice",
            "entity_id": overdue["invoice_id"].to_numpy(),
            "supplier_id": overdue["supplier_id"].to_numpy(),
            "exception_value_usd": overdue["open_amount_usd"].to_numpy(),
            "age_days": overdue["days_past_due"].to_numpy(),
            "owning_team": "AP Operations",
        }))

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["age_bucket"] = pd.cut(out["age_days"], [-10**9, 30, 60, 90, 180, 10**9],
                               labels=["0-30", "31-60", "61-90", "91-180", "180+"])
    out["age_bucket"] = out["age_bucket"].astype(str)
    out["p2p_exception_id"] = np.arange(1, len(out) + 1, dtype=np.int64)
    return out
