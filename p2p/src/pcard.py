"""The card and expense channel.

The third spend channel, and the one that completes the total-spend
reconciliation: PO-backed plus non-PO plus card equals total spend (PLAN 2.1).
It is also where the most defensible maverick spend lives - nobody argues that a
$400 card purchase from a contracted supplier went through procurement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario

MERCHANT_TYPES = ["Office Supplies", "Travel", "Software Subscription",
                  "Meals", "Courier", "Training", "Facilities", "Fuel"]


def build_pcard(s: Scenario, inv: pd.DataFrame, sup: pd.DataFrame,
                cats: pd.DataFrame, items: pd.DataFrame, depts: pd.DataFrame,
                ccs: pd.DataFrame, employees: pd.DataFrame,
                contract_price: pd.DataFrame, ep: EventPlan,
                rng: np.random.Generator) -> pd.DataFrame:
    ch = s.channels
    tl = s.timeline

    invoiced = float(inv.loc[inv["invoice_type"] == "Standard Invoice",
                             "gross_amount_usd"].sum())
    invoiced_share = 1.0 - float(ch["pcard_share_of_value"])
    target = invoiced / max(invoiced_share, 0.01) * float(ch["pcard_share_of_value"])

    mu, sigma = ch["pcard_txn_lognorm"]
    mean_txn = float(np.exp(mu + sigma ** 2 / 2))
    n = max(1, int(round(target / mean_txn)))

    span = (tl.as_of_date - tl.start_date).days
    txn_date = pd.to_datetime(tl.start_date) + pd.to_timedelta(
        rng.integers(0, span + 1, size=n), unit="D")
    amount = np.round(np.exp(rng.normal(mu, sigma, size=n)), 2)

    holders = employees[employees["is_active"] == 1]
    ev = s.event("maverick_spend")
    w = holders["department_id"].map(
        depts.set_index("department_id")["_demand_weight"]).fillna(1e-9).to_numpy()
    if ev is not None and len(ep.maverick_departments):
        hot = holders["department_id"].isin(ep.maverick_departments).to_numpy()
        conc = float(ev["concentration"])
        n_hot = max(int(pd.Series(hot).sum()), 1)
        n_cold = max(len(holders) - n_hot, 1)
        ratio = (conc / n_hot) / max((1 - conc) / n_cold, 1e-9)
        w = np.where(hot, w * ratio, w)
    w = w / w.sum()
    pick = rng.choice(len(holders), size=n, p=w)
    holder = holders.iloc[pick].reset_index(drop=True)

    # Card spend lands in the low-value indirect tail, never on direct materials.
    indirect = cats[cats["is_direct_spend"] == 0]
    leaf = indirect.sample(n=n, replace=True, weights=indirect["_spend_weight"],
                           random_state=int(s.seed) + 1001).reset_index(drop=True)
    merchant = sup.sample(n=n, replace=True, weights=sup["_spend_weight"],
                          random_state=int(s.seed) + 1002).reset_index(drop=True)

    df = pd.DataFrame({
        "pcard_transaction_id": np.arange(1, n + 1, dtype=np.int64),
        "transaction_reference": [f"PC-{i:08d}" for i in range(1, n + 1)],
        "transaction_date": txn_date.date,
        "cardholder_employee_id": holder["employee_id"].to_numpy(),
        "department_id": holder["department_id"].to_numpy(),
        "cost_center_id": holder["cost_center_id"].to_numpy(),
        "company_code": holder["company_code"].to_numpy(),
        "supplier_id": merchant["supplier_id"].to_numpy(),
        "merchant_name": merchant["supplier_name"].to_numpy(),
        "merchant_category": rng.choice(MERCHANT_TYPES, size=n),
        "category_id": leaf["category_id"].to_numpy(),
        "segment_name": leaf["segment_name"].to_numpy(),
        "amount_usd": amount,
        "currency_code": "USD",
        "is_receipted": (rng.random(n) > 0.16).astype("int8"),
        "is_policy_exception": (rng.random(n) < 0.043).astype("int8"),
    })
    # Maverick, derived the same way as on the non-PO invoices: a contract with
    # that supplier covered that category and was bypassed.
    cp = set(zip(contract_price["supplier_id"].to_numpy(),
                 contract_price["category_id"].to_numpy()))
    df["is_maverick_spend"] = [int((int(a), int(b)) in cp) for a, b in
                               zip(df["supplier_id"], df["category_id"])]
    return df
