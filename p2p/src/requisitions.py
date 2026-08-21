"""Requisition demand, sourcing suggestion and approval routing.

Eighteen percent of requisitions never become a purchase order. That loss -
rejected, withdrawn, blocked on budget - is a story the design note had no way
to tell, and it is the reason the document funnel narrows before it widens
(PLAN 2.9).

Line amounts are drawn as an AMOUNT and converted to a quantity against the
item's actual unit price, rather than drawing a quantity and multiplying. Doing
it the other way round makes a consulting phase and a kilo of resin land in the
same value band, and the spend distribution stops looking like a company's.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario, month_end

REJECT_REASONS = ["Not budgeted", "Duplicate request", "Insufficient justification",
                  "Use existing contract", "Superseded by another request",
                  "Incorrect cost centre"]


def monthly_volume(s: Scenario) -> pd.DataFrame:
    """Requisition count per month, with growth and seasonality applied."""
    months = s.timeline.month_starts()
    base = float(s.sizes["requisitions_per_month_base"])
    growth = float(s.demand["annual_growth"])
    seas = s.demand["seasonality_by_month"]
    rows = []
    for i, m in enumerate(months):
        # Growth compounds from the start of history, so the +14% YoY headline
        # is a property of the data rather than a claim on a slide.
        factor = (1.0 + growth) ** (i / 12.0)
        rows.append({"month_start": m,
                     "requisitions": int(round(base * factor * seas[m.month - 1]))})
    return pd.DataFrame(rows)


def _expected_line_value(s: Scenario, cats: pd.DataFrame, items: pd.DataFrame,
                         rng: np.random.Generator, draws: int = 400) -> np.ndarray:
    """Roughly what one requisition line in each category leaf is worth.

    Estimated by running the real line formula rather than approximating it. A
    line is `max(1, round(target / price)) * price`, which behaves completely
    differently either side of `price == target`, and the closed-form estimate
    is biased by enough (13% on the expensive leaves, via the contract discount)
    to push the segment mix eight points off target.
    """
    mu, sigma = s.demand["line_amount_lognorm"]
    # Blended effect of contract discount vs spot premium on the list price.
    price_factor = (float(s.sourcing["contract_used_when_available"])
                    * (1 - np.mean(s.sourcing["contract_price_discount_range"]))
                    + (1 - float(s.sourcing["contract_used_when_available"]))
                    * (1 + np.mean(s.sourcing["spot_price_premium_range"])))
    out = np.full(len(cats), float(np.exp(mu)))
    pos = {int(c): i for i, c in enumerate(cats["category_id"].to_numpy())}
    for leaf, g in items.groupby("category_id"):
        i = pos.get(int(leaf))
        if i is None:
            continue
        price = g["list_price_usd"].to_numpy() * price_factor
        w = price ** -0.40                      # matches the item draw below
        w = w / w.sum()
        pick = rng.choice(len(price), size=draws, p=w)
        p_ = price[pick]
        target = np.exp(rng.normal(mu, sigma, size=draws))
        qty = np.minimum(np.maximum(1, np.round(target / np.maximum(p_, 0.01))), 25_000)
        out[i] = float(np.mean(qty * p_))
    return out


def build_requisitions(s: Scenario, employees: pd.DataFrame, depts: pd.DataFrame,
                       ccs: pd.DataFrame, cats: pd.DataFrame, items: pd.DataFrame,
                       contract_price: pd.DataFrame, sampler: dict,
                       ep: EventPlan, rng: np.random.Generator):
    """Returns (requisition, requisition_line)."""
    vol = monthly_volume(s)
    n = int(vol["requisitions"].sum())

    # -- header dates ---------------------------------------------------------
    month_of = np.repeat(vol["month_start"].to_numpy(), vol["requisitions"].to_numpy())
    day_span = np.array([(month_end(m) - m).days + 1 for m in month_of])
    day_off = (rng.random(n) * day_span).astype(int)
    req_date = pd.to_datetime(pd.Series(month_of)) + pd.to_timedelta(day_off, unit="D")

    # -- requester ------------------------------------------------------------
    # Requesters are drawn against department demand weight, so IT and Operations
    # raise far more than Investor Relations.
    dept_w = depts.set_index("department_id")["_demand_weight"]
    emp_pool = employees[employees["is_active"] == 1].copy()
    emp_pool["_w"] = emp_pool["department_id"].map(dept_w).fillna(1e-9)
    emp_pool["_w"] /= emp_pool["_w"].sum()
    pick = rng.choice(len(emp_pool), size=n, p=emp_pool["_w"].to_numpy())
    requester = emp_pool.iloc[pick].reset_index(drop=True)

    req = pd.DataFrame({
        "requisition_id": np.arange(1, n + 1, dtype=np.int64),
        "requisition_number": [f"REQ-{i:07d}" for i in range(1, n + 1)],
        "requisition_date": req_date.dt.date.to_numpy(),
        "requester_employee_id": requester["employee_id"].to_numpy(),
        "department_id": requester["department_id"].to_numpy(),
        "cost_center_id": requester["cost_center_id"].to_numpy(),
        "company_code": requester["company_code"].to_numpy(),
    })

    # -- lines ----------------------------------------------------------------
    lam = float(s.demand["lines_per_requisition_lambda"])
    line_ct = 1 + rng.poisson(lam, size=n)
    total_lines = int(line_ct.sum())
    parent = np.repeat(np.arange(n), line_ct)
    line_no = np.concatenate([np.arange(1, k + 1) for k in line_ct])

    # A requisition is family-coherent: someone raising a request for three IT
    # peripherals raises one request, not three unrelated ones. Drawing the leaf
    # independently per line scatters every requisition across the whole
    # taxonomy, which then makes supplier cohesion impossible - no supplier is
    # qualified for two unrelated categories - and fans every requisition out
    # into one PO per line.
    # `_spend_weight` states how much VALUE a leaf should carry. What the draw
    # actually controls is how many LINES land there, and a line of steel coil
    # is worth a hundredth of a line of consulting. Sampling on the value weight
    # directly therefore delivers a segment mix nothing like the configured one.
    # Convert value share to line share by dividing by the value a line in that
    # leaf is worth.
    exp_line_value = _expected_line_value(s, cats, items, rng)
    count_w = (cats["_spend_weight"].to_numpy()
               / np.maximum(exp_line_value, 1e-6))
    count_w = count_w / count_w.sum()
    cats = cats.assign(_count_weight=count_w)

    fam_names = cats["family_name"].to_numpy()
    fam_unique = cats["family_name"].unique()
    fam_w = (cats.groupby("family_name")["_count_weight"].sum()
             .reindex(fam_unique).to_numpy())
    fam_w = fam_w / fam_w.sum()
    req_family = rng.choice(fam_unique, size=n, p=fam_w)

    leaf_ids = cats["category_id"].to_numpy()
    leaf_w = cats["_count_weight"].to_numpy()
    leaves_of_family = {}
    for f in fam_unique:
        m = fam_names == f
        w = leaf_w[m]
        leaves_of_family[f] = (leaf_ids[m], w / w.sum())

    leaf = np.zeros(total_lines, dtype=np.int64)
    line_family = req_family[parent]
    for f in fam_unique:
        idx = np.where(line_family == f)[0]
        if not len(idx):
            continue
        ids, p_ = leaves_of_family[f]
        leaf[idx] = rng.choice(ids, size=len(idx), p=p_)

    # Tighter still: most lines of a requisition sit in the SAME leaf - three
    # sizes of the same fastener, two seats of the same licence. Family-level
    # coherence alone still leaves ~2.1 suppliers per requisition, because a
    # supplier qualified for one leaf of a family is qualified for only two or
    # three of its fourteen.
    req_leaf = leaf[np.concatenate([[0], np.cumsum(line_ct)[:-1]])]
    same_leaf = rng.random(total_lines) < 0.72
    leaf = np.where(same_leaf, req_leaf[parent], leaf)

    supplier = np.zeros(total_lines, dtype=np.int64)
    item = np.zeros(total_lines, dtype=np.int64)
    # Frequency falls with unit cost: a company requisitions laptops far more
    # often than $78K brand campaigns. Without this the item draw is uniform,
    # every leaf's expensive tail is ordered as often as its staples, and total
    # spend comes out roughly half as large again as a company this size buys.
    items_by_leaf = {}
    for k, g in items.groupby("category_id"):
        w = g["list_price_usd"].to_numpy() ** -0.40
        items_by_leaf[int(k)] = (g["item_id"].to_numpy(), w / w.sum())
    order = np.argsort(leaf, kind="stable")
    leaf_sorted = leaf[order]
    bounds = np.searchsorted(leaf_sorted, np.unique(leaf_sorted), side="left")
    bounds = np.append(bounds, len(leaf_sorted))
    for bi, lf in enumerate(np.unique(leaf_sorted)):
        idx = order[bounds[bi]:bounds[bi + 1]]
        sup_ids, sup_p = sampler[int(lf)]
        supplier[idx] = rng.choice(sup_ids, size=len(idx), p=sup_p)
        pool, pool_p = items_by_leaf.get(int(lf), (None, None))
        if pool is None or len(pool) == 0:
            pool, pool_p = items["item_id"].to_numpy(), None
        item[idx] = rng.choice(pool, size=len(idx), p=pool_p)

    # Supplier cohesion. Drawing a supplier independently per line means a
    # three-line requisition fans out into three purchase orders, which is not
    # how requisitions convert and would inflate the PO count by 2.4x. Lines
    # after the first reuse the requisition's supplier whenever that supplier is
    # qualified for the line's category.
    cov_keys = set()
    for lf, (sids, _p) in sampler.items():
        for sid in sids:
            cov_keys.add(int(sid) * 10_000_000 + int(lf))
    first_of_req = np.zeros(n, dtype=np.int64)
    starts = np.concatenate([[0], np.cumsum(line_ct)[:-1]])
    first_of_req[:] = supplier[starts]
    reuse_roll = rng.random(total_lines)
    parent_first = first_of_req[parent]
    can_reuse = np.array([
        (int(sf) * 10_000_000 + int(lf)) in cov_keys
        for sf, lf in zip(parent_first, leaf)])
    take = can_reuse & (reuse_roll < 0.86)
    supplier = np.where(take, parent_first, supplier)

    # -- price: contract if one covers this supplier x item, else list + premium
    item_idx = items.set_index("item_id")
    list_price = item_idx.loc[item, "list_price_usd"].to_numpy()
    cp_key = (contract_price["supplier_id"].to_numpy().astype(np.int64) * 10_000_000
              + contract_price["item_id"].to_numpy().astype(np.int64))
    cp_price = dict(zip(cp_key, contract_price["contract_unit_price_usd"].to_numpy()))
    cp_contract = dict(zip(cp_key, contract_price["contract_id"].to_numpy()))
    key = supplier.astype(np.int64) * 10_000_000 + item.astype(np.int64)
    contracted_price = np.array([cp_price.get(k, np.nan) for k in key])
    contract_id = np.array([cp_contract.get(k, 0) for k in key], dtype=np.int64)

    lo, hi = s.sourcing["spot_price_premium_range"]
    spot = list_price * (1.0 + rng.uniform(lo, hi, size=total_lines))
    has_contract = ~np.isnan(contracted_price)
    # Even where a contract exists it is not always used - that 14% is the
    # off-contract leakage the savings page is built on.
    use_contract = has_contract & (rng.random(total_lines)
                                   < float(s.sourcing["contract_used_when_available"]))
    unit_price = np.where(use_contract, np.nan_to_num(contracted_price), spot)

    # -- quantity from a target line amount -----------------------------------
    mu, sigma = s.demand["line_amount_lognorm"]
    target_amt = np.exp(rng.normal(mu, sigma, size=total_lines))
    qty = np.maximum(1, np.round(target_amt / np.maximum(unit_price, 0.01)))
    # Cap absurd quantities on cheap items so a $0.14 kWh line does not become
    # 40,000 units of nothing.
    qty = np.minimum(qty, 25_000)

    lines = pd.DataFrame({
        "requisition_line_id": np.arange(1, total_lines + 1, dtype=np.int64),
        "requisition_id": req["requisition_id"].to_numpy()[parent],
        "line_number": line_no.astype("int16"),
        "item_id": item,
        "category_id": leaf,
        "suggested_supplier_id": supplier,
        "contract_id": contract_id,
        "quantity_requested": qty,
        "unit_price_usd": np.round(unit_price, 4),
        "line_amount_usd": np.round(qty * unit_price, 2),
        "is_contract_price": use_contract.astype("int8"),
        "has_contract_available": has_contract.astype("int8"),
    })
    lines["unit_of_measure"] = item_idx.loc[item, "unit_of_measure"].to_numpy()
    lines["gl_account_id"] = item_idx.loc[item, "gl_account_id"].to_numpy()
    lines["segment_name"] = item_idx.loc[item, "segment_name"].to_numpy()
    lines["is_service_item"] = item_idx.loc[item, "is_service_item"].to_numpy()
    lines["requisition_date"] = req["requisition_date"].to_numpy()[parent]

    # -- header roll-up and approval ------------------------------------------
    agg = lines.groupby("requisition_id").agg(
        total_amount_usd=("line_amount_usd", "sum"),
        line_count=("line_number", "count")).reset_index()
    req = req.merge(agg, on="requisition_id", how="left")

    rq = s.requisitioning
    mu_a, sd_a = rq["approval_days_lognorm"]
    approval_days = np.round(np.exp(rng.normal(mu_a, sd_a, size=n)), 1)
    # Big requisitions climb further up the approval chain and take longer.
    big = req["total_amount_usd"].to_numpy() > 50_000
    approval_days = approval_days + np.where(big, rng.uniform(1.5, 6.0, size=n), 0.0)

    u = rng.random(n)
    p_rej = float(rq["rejected_share"])
    p_wd = p_rej + float(rq["withdrawn_share"])
    p_bb = p_wd + float(rq["budget_blocked_share"])
    status = np.select(
        [u < p_rej, u < p_wd, u < p_bb],
        ["Rejected", "Withdrawn", "Budget Blocked"], default="Approved")
    req["requisition_status"] = status
    req["approval_days"] = np.where(status == "Withdrawn", np.nan, approval_days)
    req["approval_date"] = [
        (d + dt.timedelta(days=float(x))) if np.isfinite(x) else pd.NaT
        for d, x in zip(pd.to_datetime(req["requisition_date"]), req["approval_days"])]
    req["approval_date"] = pd.to_datetime(req["approval_date"]).dt.date
    req["rejection_reason"] = np.where(
        status == "Rejected",
        rng.choice(REJECT_REASONS, size=n), "")
    req["is_urgent"] = (rng.random(n) < 0.13).astype("int8")
    req["needed_by_date"] = [d + dt.timedelta(days=int(x)) for d, x in
                             zip(pd.to_datetime(req["requisition_date"]),
                                 rng.integers(7, 60, size=n))]
    req["needed_by_date"] = pd.to_datetime(req["needed_by_date"]).dt.date
    req["currency_code"] = "USD"
    _ = ep
    return req, lines
