"""Requisition-to-PO conversion, sourcing, and three of the fraud events.

Conversion is not one-to-one. Seventy percent of requisition groups become their
own PO, a quarter are aggregated with other requisitions on the same supplier
inside a ten-day window - which is *why* conversion takes days rather than
minutes - and a twentieth are split across POs (PLAN 2.9).

Three events are planted here, and two of them need care:

* **E4 contract price drift** is the root cause of the whole demo. The PO price
  is set ABOVE the contracted price for fourteen suppliers, ramping across the
  window. Everything downstream - invoice variance, holds, approval time, missed
  discounts, late payment - follows from this one gap.
* **E13 PO splitting** and **E14 threshold clustering** are planted against a
  natural base rate. POs already cluster below round numbers for innocent
  reasons; the story is *excess* mass, and it has to be measured against the
  policy row that applied on the day (PLAN 2.7).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario

PO_TYPES = ["Standard", "Blanket", "Service", "Contract Release"]
CHANGE_TYPES = ["Price Change", "Quantity Increase", "Quantity Decrease",
                "Date Change", "Line Cancellation", "Supplier Site Change"]
CHANGE_REASONS = ["Supplier price update", "Demand change", "Delivery reschedule",
                  "Budget reallocation", "Contract renegotiation", "Data entry correction"]


def build_purchase_orders(s: Scenario, req: pd.DataFrame, req_lines: pd.DataFrame,
                          sup: pd.DataFrame, sites: pd.DataFrame,
                          employees: pd.DataFrame, contracts: pd.DataFrame,
                          contract_price: pd.DataFrame, terms: pd.DataFrame,
                          policy: pd.DataFrame, ep: EventPlan,
                          rng: np.random.Generator):
    """Returns (purchase_order, purchase_order_line, po_change)."""
    tl = s.timeline
    rq = s.requisitioning

    approved = req[req["requisition_status"] == "Approved"]
    lines = req_lines[req_lines["requisition_id"].isin(approved["requisition_id"])].copy()
    hdr = approved.set_index("requisition_id")

    lines["_approval_date"] = pd.to_datetime(
        hdr.loc[lines["requisition_id"], "approval_date"].to_numpy())
    lines["_department_id"] = hdr.loc[lines["requisition_id"], "department_id"].to_numpy()
    lines["_cost_center_id"] = hdr.loc[lines["requisition_id"],
                                       "cost_center_id"].to_numpy()
    lines["_company_code"] = hdr.loc[lines["requisition_id"], "company_code"].to_numpy()
    lines["_requester"] = hdr.loc[lines["requisition_id"],
                                  "requester_employee_id"].to_numpy()

    # -- group: one candidate PO per (requisition, supplier) -------------------
    grp = (lines.groupby(["requisition_id", "suggested_supplier_id"], sort=False)
           .ngroup().to_numpy())
    lines["_group"] = grp
    n_groups = int(grp.max()) + 1 if len(grp) else 0

    gi = (lines.groupby("_group")
          .agg(supplier_id=("suggested_supplier_id", "first"),
               requisition_id=("requisition_id", "first"),
               company_code=("_company_code", "first"),
               department_id=("_department_id", "first"),
               cost_center_id=("_cost_center_id", "first"),
               requester_employee_id=("_requester", "first"),
               approval_date=("_approval_date", "max"))
          .reset_index())

    mu, sd = rq["req_to_po_days_lognorm"]
    lag = np.exp(rng.normal(mu, sd, size=len(gi)))
    gi["po_date"] = (gi["approval_date"] + pd.to_timedelta(lag.round(), unit="D"))
    gi = gi[gi["po_date"] <= pd.Timestamp(tl.as_of_date)].reset_index(drop=True)

    # -- aggregation and splitting --------------------------------------------
    mix = rq["conversion_mix"]
    roll = rng.random(len(gi))
    p_one = float(mix["one_to_one"])
    p_agg = p_one + float(mix["aggregated"])
    mode = np.select([roll < p_one, roll < p_agg], ["one", "agg"], default="split")
    gi["_mode"] = mode

    # Aggregate: same supplier, same entity, same ten-day bucket collapse to one
    # PO. This is the mechanism behind the 4.6-day requisition-to-PO leg.
    bucket = ((gi["po_date"] - pd.Timestamp(tl.start_date)).dt.days // 10).to_numpy()
    agg_key = (gi["supplier_id"].astype(np.int64) * 10**9
               + pd.factorize(gi["company_code"])[0].astype(np.int64) * 10**6
               + bucket)
    gi["_agg_key"] = np.where(gi["_mode"] == "agg", agg_key, -np.arange(1, len(gi) + 1))
    gi["_po_seq"] = gi.groupby("_agg_key", sort=False).ngroup()

    po_from_group = dict(zip(gi["_group"], gi["_po_seq"]))
    lines = lines[lines["_group"].isin(po_from_group)].copy()
    lines["_po_seq"] = lines["_group"].map(po_from_group)
    # Carry the group's PO-ready date onto the LINES. `_po_seq` is re-factorised
    # a few lines below, after splitting, so any lookup keyed on the pre-split
    # sequence silently resolves to a different purchase order - which is how
    # 22% of POs ended up dated before the requisition that created them.
    lines["_po_ready"] = lines["_group"].map(dict(zip(gi["_group"], gi["po_date"])))

    # Split: a group marked "split" pushes its later lines onto a second PO.
    split_groups = set(gi.loc[gi["_mode"] == "split", "_group"])
    if split_groups:
        is_split = lines["_group"].isin(split_groups)
        second_half = is_split & (lines.groupby("_group").cumcount() % 2 == 1)
        bump = second_half.to_numpy()
        lines.loc[bump, "_po_seq"] = lines.loc[bump, "_po_seq"] + 10**7

    lines["_po_seq"] = pd.factorize(lines["_po_seq"])[0]
    n_po = int(lines["_po_seq"].max()) + 1

    # -- PO header -------------------------------------------------------------
    seq = np.arange(n_po)
    head = (lines.groupby("_po_seq")
            .agg(supplier_id=("suggested_supplier_id", "first"),
                 company_code=("_company_code", "first"),
                 department_id=("_department_id", "first"),
                 cost_center_id=("_cost_center_id", "first"),
                 requester_employee_id=("_requester", "first"),
                 po_date=("_approval_date", "max"),
                 requisition_count=("requisition_id", "nunique"),
                 line_count=("requisition_line_id", "count"))
            .reindex(seq).reset_index())
    # The PO is raised once every contributing requisition has been approved, so
    # the header date is the LATEST ready date across the lines it aggregates.
    lagged = lines.groupby("_po_seq")["_po_ready"].max().reindex(seq)
    head["po_date"] = pd.to_datetime(lagged.to_numpy())
    fallback = head["po_date"].isna()
    if fallback.any():
        base = lines.groupby("_po_seq")["_approval_date"].max().reindex(seq)
        head.loc[fallback, "po_date"] = (
            pd.to_datetime(base[fallback.to_numpy()].to_numpy())
            + pd.to_timedelta(rng.integers(1, 9, size=int(fallback.sum())), unit="D"))

    head["purchase_order_id"] = np.arange(1, n_po + 1, dtype=np.int64)
    head["po_number"] = [f"PO-{i:07d}" for i in head["purchase_order_id"]]

    # Buyers: the PO is raised by procurement, not by the requester.
    buyers = employees[(employees["is_buyer"] == 1)]
    if not len(buyers):
        buyers = employees
    head["buyer_employee_id"] = buyers.sample(
        n=n_po, replace=True, random_state=int(s.seed) + 501)["employee_id"].to_numpy()

    # Supplier site, currency, terms.
    pay_sites = sites[sites["is_pay_site"] == 1].drop_duplicates("supplier_id")
    site_of = dict(zip(pay_sites["supplier_id"], pay_sites["supplier_site_id"]))
    any_site = sites.drop_duplicates("supplier_id")
    site_of_any = dict(zip(any_site["supplier_id"], any_site["supplier_site_id"]))
    head["supplier_site_id"] = [int(site_of.get(x, site_of_any.get(x, 0)))
                                for x in head["supplier_id"]]
    sup_idx = sup.set_index("supplier_id")
    head["currency_code"] = sup_idx.loc[head["supplier_id"], "currency_code"].to_numpy()

    ctr_terms = (contracts.sort_values("contract_start_date")
                 .drop_duplicates("supplier_id", keep="last")
                 .set_index("supplier_id")["payment_terms_code"])
    tw = terms["_weight"].to_numpy() / terms["_weight"].sum()
    drawn = rng.choice(terms["payment_terms_code"].to_numpy(), size=n_po, p=tw)
    head["payment_terms_code"] = (pd.Series(head["supplier_id"].to_numpy())
                                  .map(ctr_terms).fillna(pd.Series(drawn)).to_numpy())

    # -- PO lines: price, and Event 4 -----------------------------------------
    po_lines = _price_po_lines(s, lines, head, contract_price, ep, rng)

    amt = po_lines.groupby("_po_seq")["line_amount_usd"].sum().reindex(seq).fillna(0.0)
    head["total_amount_usd"] = amt.to_numpy()

    head, po_lines = _plant_threshold_events(s, head, po_lines, policy, ep, rng)

    # Splitting appends headers, so every array below has to be sized against
    # the CURRENT header set, not the pre-split one.
    head = head.reset_index(drop=True)
    seq = head["_po_seq"].to_numpy()
    n_po = len(head)

    head["po_type"] = np.where(
        po_lines.groupby("_po_seq")["is_service_line"].mean()
        .reindex(seq).fillna(0).to_numpy() > 0.5,
        "Service", rng.choice(["Standard", "Blanket", "Contract Release"],
                              size=n_po, p=[0.72, 0.13, 0.15]))

    # Cancellation: the "released" bar of the commitment waterfall.
    cancelled = rng.random(n_po) < 0.035
    head["is_cancelled"] = cancelled.astype("int8")
    head["cancelled_date"] = pd.Series(
        [d + dt.timedelta(days=int(x)) if c else pd.NaT
         for d, x, c in zip(head["po_date"], rng.integers(3, 90, size=n_po), cancelled)])
    head["po_status"] = np.where(cancelled, "Cancelled", "Open")
    head["committed_amount_usd"] = np.where(cancelled, 0.0, head["total_amount_usd"])
    head["needed_by_date"] = (head["po_date"]
                              + pd.to_timedelta(rng.integers(7, 70, size=n_po),
                                                unit="D"))

    head["is_contract_backed"] = (po_lines.groupby("_po_seq")["contract_id"]
                                  .max().reindex(seq).fillna(0).gt(0)
                                  .astype("int8").to_numpy())
    head["contract_id"] = (po_lines.groupby("_po_seq")["contract_id"]
                           .max().reindex(seq).fillna(0).astype("int64").to_numpy())

    changes = _build_po_changes(s, head, po_lines, employees, rng)

    # Publish shape: drop the working columns, keep the keys.
    po_lines["purchase_order_id"] = (head.set_index("_po_seq")
                                     .loc[po_lines["_po_seq"], "purchase_order_id"]
                                     .to_numpy())
    po_lines["po_line_number"] = (po_lines.groupby("_po_seq").cumcount() + 1).astype("int16")
    po_lines["purchase_order_line_id"] = np.arange(1, len(po_lines) + 1, dtype=np.int64)
    po_lines["po_date"] = (head.set_index("_po_seq")
                           .loc[po_lines["_po_seq"], "po_date"].to_numpy())
    po_lines["supplier_id"] = (head.set_index("_po_seq")
                               .loc[po_lines["_po_seq"], "supplier_id"].to_numpy())
    po_lines["is_cancelled"] = (head.set_index("_po_seq")
                                .loc[po_lines["_po_seq"], "is_cancelled"].to_numpy())

    head["po_date"] = pd.to_datetime(head["po_date"]).dt.date
    head["cancelled_date"] = pd.to_datetime(head["cancelled_date"]).dt.date
    head["needed_by_date"] = pd.to_datetime(head["needed_by_date"]).dt.date
    po_lines["po_date"] = pd.to_datetime(po_lines["po_date"]).dt.date
    return head, po_lines, changes


def _price_po_lines(s: Scenario, lines: pd.DataFrame, head: pd.DataFrame,
                    contract_price: pd.DataFrame, ep: EventPlan,
                    rng: np.random.Generator) -> pd.DataFrame:
    """PO price, and the contract-price gap that is Event 4."""
    out = lines[["requisition_line_id", "requisition_id", "item_id", "category_id",
                 "suggested_supplier_id", "contract_id", "quantity_requested",
                 "unit_price_usd", "unit_of_measure", "gl_account_id",
                 "segment_name", "is_service_item", "is_contract_price",
                 "_po_seq", "_department_id", "_cost_center_id"]].copy()
    out = out.rename(columns={"quantity_requested": "quantity_ordered",
                              "is_service_item": "is_service_line",
                              "_department_id": "department_id",
                              "_cost_center_id": "cost_center_id"})

    key = (out["suggested_supplier_id"].to_numpy().astype(np.int64) * 10_000_000
           + out["item_id"].to_numpy().astype(np.int64))
    cp_key = (contract_price["supplier_id"].to_numpy().astype(np.int64) * 10_000_000
              + contract_price["item_id"].to_numpy().astype(np.int64))
    cp_map = dict(zip(cp_key, contract_price["contract_unit_price_usd"].to_numpy()))
    contract_unit = np.array([cp_map.get(k, np.nan) for k in key])

    po_date = (head.set_index("_po_seq")
               .loc[out["_po_seq"], "po_date"].to_numpy())
    price = out["unit_price_usd"].to_numpy().astype(float)

    # -- Event 4: PO price drifts ABOVE the contracted price -------------------
    drift = ep.price_drift_for(out["suggested_supplier_id"].to_numpy())
    ramp = ep.ramp_series("contract_price_drift", po_date)
    has_contract = ~np.isnan(contract_unit)
    lift = 1.0 + drift * ramp
    price = np.where(has_contract & (drift > 0),
                     np.nan_to_num(contract_unit) * lift, price)

    # Ordinary negotiation noise on everything else, so the drifted suppliers do
    # not stand out simply by being the only ones that differ at all.
    noise = rng.normal(0.0, 0.012, size=len(out))
    price = np.where(has_contract & (drift > 0), price, price * (1 + noise))

    out["unit_price_usd"] = np.round(np.maximum(price, 0.01), 4)
    out["contract_unit_price_usd"] = np.round(contract_unit, 4)
    out["line_amount_usd"] = np.round(out["quantity_ordered"] * out["unit_price_usd"], 2)
    gap = np.where(has_contract,
                   (out["unit_price_usd"].to_numpy() - np.nan_to_num(contract_unit))
                   * out["quantity_ordered"].to_numpy(), 0.0)
    # Priced OFF the contract: the buyer used the agreement and then paid above
    # it. This is Event 4 and it belongs to the supplier relationship.
    on_contract_basis = has_contract & (drift > 0)
    used_contract = out["is_contract_price"].to_numpy() == 1
    priced_on_contract = has_contract & (used_contract | on_contract_basis)
    out["contract_price_variance_usd"] = np.round(
        np.where(priced_on_contract, gap, 0.0), 2)
    # Never used the contract at all: spot-priced despite an agreement existing.
    # A different lever, a different owner, and a much bigger number.
    out["off_contract_premium_usd"] = np.round(
        np.where(has_contract & ~priced_on_contract, gap, 0.0), 2)
    out["is_priced_above_contract"] = (
        priced_on_contract & (gap > 0)).astype("int8")
    out["is_off_contract_purchase"] = (
        has_contract & ~priced_on_contract).astype("int8")
    out["has_contract_price"] = has_contract.astype("int8")
    return out


def _plant_threshold_events(s: Scenario, head: pd.DataFrame, po_lines: pd.DataFrame,
                            policy: pd.DataFrame, ep: EventPlan,
                            rng: np.random.Generator):
    """E14 threshold clustering and E13 PO splitting.

    Both are planted as *excess* over a natural base rate. POs already fall just
    below round numbers for innocent reasons, so the demo question is a
    statistical one - is there more mass in the band than the distribution
    predicts - not a filter for POs between $45K and $50K.
    """
    ev = s.event("threshold_clustering")
    if ev is not None and len(ep.threshold_buyers):
        thr = float(ev["threshold_usd"])
        band = float(ev["band_pct"])
        lo = thr * (1 - band)
        # Candidates: POs a little ABOVE the threshold raised by the marked
        # buyers. Shave them to just under it, which is the behaviour being
        # alleged - not POs invented at $49,850 out of nowhere.
        hit = (head["buyer_employee_id"].isin(ep.threshold_buyers)
               & head["total_amount_usd"].between(thr, thr * 1.9)).to_numpy()
        idx = np.where(hit)[0]
        if len(idx):
            take = rng.random(len(idx)) < 0.62
            idx = idx[take]
        for i in idx:
            seq = int(head.loc[i, "_po_seq"])
            target = float(rng.uniform(lo + (thr - lo) * 0.55, thr * 0.998))
            mask = po_lines["_po_seq"].to_numpy() == seq
            cur = po_lines.loc[mask, "line_amount_usd"].sum()
            if cur <= 0:
                continue
            factor = target / cur
            po_lines.loc[mask, "quantity_ordered"] = np.maximum(
                1, np.round(po_lines.loc[mask, "quantity_ordered"] * factor))
            po_lines.loc[mask, "line_amount_usd"] = np.round(
                po_lines.loc[mask, "quantity_ordered"]
                * po_lines.loc[mask, "unit_price_usd"], 2)
            head.loc[i, "total_amount_usd"] = po_lines.loc[mask,
                                                           "line_amount_usd"].sum()

    # -- E13: PO splitting -----------------------------------------------------
    ev = s.event("po_splitting")
    head["split_group_key"] = ""
    if ev is not None and len(ep.splitting_buyers):
        thr = float(s.event("threshold_clustering")["threshold_usd"]) \
            if s.event("threshold_clustering") else 50_000.0
        lo_p, hi_p = ev["parts_range"]
        line_ct = po_lines.groupby("_po_seq").size()
        # Splittable: above the threshold, small enough that a handful of parts
        # each land under it, and with enough lines to distribute.
        cand = head[(head["buyer_employee_id"].isin(ep.splitting_buyers))
                    & (head["total_amount_usd"] > thr)
                    & (head["total_amount_usd"] <= thr * int(hi_p) * 0.92)
                    & (head["_po_seq"].map(line_ct).fillna(0) >= 2)]
        k = min(int(ev["real_cases"] * s.tier_scale), len(cand))
        if k:
            chosen = cand.sample(n=k, random_state=int(s.seed) + 502)
            new_heads, new_lines, drop_pos = [], [], []
            next_seq = int(head["_po_seq"].max()) + 1
            next_po_id = int(head["purchase_order_id"].max())
            for _, r in chosen.iterrows():
                seq = int(r["_po_seq"])
                mask = (po_lines["_po_seq"].to_numpy() == seq)
                sub = po_lines[mask]
                original = float(sub["line_amount_usd"].sum())
                parts = int(np.clip(int(np.ceil(original / (thr * 0.94))),
                                    lo_p, min(hi_p, len(sub))))
                if parts < 2:
                    continue
                key = f"SPLIT-{int(r['purchase_order_id']):07d}"

                # Distribute the LINES across the parts rather than rescaling
                # quantities. Rescaling runs into the quantity-of-one floor: a
                # part meant to carry a third of the value ends up carrying one
                # unit of every line, and the "split" costs more than the
                # purchase it came from.
                order_idx = sub["line_amount_usd"].to_numpy().argsort()[::-1]
                bucket = np.zeros(len(sub), dtype=int)
                running = np.zeros(parts)
                for pos in order_idx:                 # greedy: fill the lightest
                    b = int(np.argmin(running))
                    bucket[pos] = b
                    running[b] += float(sub["line_amount_usd"].iloc[pos])

                sub_idx = np.where(mask)[0]
                head.loc[head["_po_seq"] == seq, "split_group_key"] = key
                keep = sub_idx[bucket == 0]
                head.loc[head["_po_seq"] == seq, "total_amount_usd"] = float(
                    po_lines.iloc[keep]["line_amount_usd"].sum())

                for p_ in range(1, parts):
                    take = sub_idx[bucket == p_]
                    if not len(take):
                        continue
                    nl = po_lines.iloc[take].copy()
                    nl["_po_seq"] = next_seq
                    nh = r.copy()
                    nh["_po_seq"] = next_seq
                    next_po_id += 1
                    nh["purchase_order_id"] = next_po_id
                    nh["po_number"] = f"PO-{next_po_id:07d}"
                    # Days apart, same buyer, same supplier, same category. That
                    # co-occurrence is the signal the analysis has to find.
                    nh["po_date"] = r["po_date"] + pd.Timedelta(
                        days=int(rng.integers(1, int(ev["window_days"]) + 1)))
                    nh["split_group_key"] = key
                    nh["total_amount_usd"] = float(nl["line_amount_usd"].sum())
                    nh["line_count"] = len(nl)
                    new_heads.append(nh)
                    new_lines.append(nl)
                    next_seq += 1
                drop_pos.extend(sub_idx[bucket != 0].tolist())
            if new_heads:
                if drop_pos:
                    po_lines = po_lines.drop(index=po_lines.index[drop_pos])
                head = pd.concat([head, pd.DataFrame(new_heads)], ignore_index=True)
                po_lines = pd.concat([po_lines] + new_lines, ignore_index=True)

    # -- the approval band that applied on the day -----------------------------
    head["approval_threshold_usd"] = _threshold_for(s, head, policy)
    head["is_below_approval_threshold"] = (
        (head["total_amount_usd"] > head["approval_threshold_usd"] * 0.90)
        & (head["total_amount_usd"] <= head["approval_threshold_usd"])).astype("int8")
    return head, po_lines


def _threshold_for(s: Scenario, head: pd.DataFrame, policy: pd.DataFrame) -> np.ndarray:
    """The Senior Manager limit in force in that entity on that PO date.

    Effective-dated on purpose: testing every PO against today's limit is the
    mistake the demo invites the audience to make.
    """
    sm = policy[policy["role_name"] == "Senior Manager"]
    out = np.full(len(head), 50_000.0)
    po_date = pd.to_datetime(head["po_date"])
    for code, g in sm.groupby("company_code"):
        m = (head["company_code"] == code).to_numpy()
        if not m.any():
            continue
        vals = np.full(int(m.sum()), float(g["approval_limit_usd"].iloc[0]))
        dates = po_date[m]
        for _, row in g.sort_values("effective_from_date").iterrows():
            inside = ((dates >= pd.Timestamp(row["effective_from_date"]))
                      & (dates <= pd.Timestamp(row["effective_to_date"]))).to_numpy()
            vals[inside] = float(row["approval_limit_usd"])
        out[m] = vals
    return out


def _build_po_changes(s: Scenario, head: pd.DataFrame, po_lines: pd.DataFrame,
                      employees: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Amendments after issue. The price-change rows are Event 4's paper trail."""
    n = len(head)
    n_change = int(n * 0.17)
    if n_change <= 0:
        return pd.DataFrame(columns=["po_change_id", "purchase_order_id"])
    idx = rng.choice(n, size=n_change, replace=False)
    src = head.iloc[idx]
    k = 1 + rng.poisson(0.4, size=n_change)
    rows = []
    buyers = employees[employees["is_buyer"] == 1]
    if not len(buyers):
        buyers = employees
    buyer_ids = buyers["employee_id"].to_numpy()
    cid = 0
    for (_, r), kk in zip(src.iterrows(), k):
        for _j in range(int(kk)):
            cid += 1
            ctype = str(rng.choice(CHANGE_TYPES, p=[0.31, 0.19, 0.14, 0.22, 0.08, 0.06]))
            old = float(r["total_amount_usd"])
            if ctype == "Price Change":
                new = old * float(rng.uniform(1.01, 1.16))
            elif ctype == "Quantity Increase":
                new = old * float(rng.uniform(1.05, 1.45))
            elif ctype == "Quantity Decrease":
                new = old * float(rng.uniform(0.55, 0.95))
            else:
                new = old
            rows.append({
                "po_change_id": cid,
                "purchase_order_id": int(r["purchase_order_id"]),
                "change_sequence": _j + 1,
                "change_date": r["po_date"] + pd.Timedelta(
                    days=int(rng.integers(1, 60))),
                "change_type": ctype,
                "field_changed": {"Price Change": "unit_price",
                                  "Quantity Increase": "quantity",
                                  "Quantity Decrease": "quantity",
                                  "Date Change": "needed_by_date",
                                  "Line Cancellation": "line_status",
                                  "Supplier Site Change": "supplier_site_id"}[ctype],
                "old_value_usd": round(old, 2),
                "new_value_usd": round(new, 2),
                "changed_by_employee_id": int(rng.choice(buyer_ids)),
                "change_reason": str(rng.choice(CHANGE_REASONS)),
            })
    df = pd.DataFrame(rows)
    df["change_date"] = pd.to_datetime(df["change_date"]).dt.date
    return df
