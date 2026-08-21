"""Supplier invoices: PO-backed, non-PO, duplicates, credit memos and GR/IR.

Three things here that the design note did not have.

**The document funnel widens on purpose.** A PO can be invoiced several times -
milestone and blanket billing - and a sixth of spend arrives with no PO at all.
That is why 161K purchase orders produce more invoices than orders, and saying
so out loud is the difference between the best scene in the demo and an
unexplained chart (PLAN 2.1).

**GR/IR is generated, not derived as an afterthought.** A share of received lines
are simply never invoiced. They sit as accrual, most of them aged past ninety
days, and they are the headline number the design note left out (PLAN 2.1, E15).

**Duplicates come through four doors, and some of them were paid.** An exact
repeat of an invoice number against the same supplier violates the unique
constraint in every real ERP and an AP audience will not accept it (PLAN 2.8).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario
from dims import parse_terms

SOURCE_CHANNELS = ["Supplier Portal", "Email PDF", "EDI", "Paper", "Scanned"]
TAX_CODES = ["STD", "RED", "ZERO", "EXEMPT", "REV"]
NON_PO_REASONS = ["Utility invoice", "Legal retainer", "Subscription renewal",
                  "Freight surcharge", "Emergency purchase", "Conference fee",
                  "Recruitment fee", "Insurance premium", "Training course",
                  "Facilities call-out"]


def build_invoices(s: Scenario, po: pd.DataFrame, po_lines: pd.DataFrame,
                   gr_lines: pd.DataFrame, sup: pd.DataFrame, sites: pd.DataFrame,
                   terms: pd.DataFrame, fx: pd.DataFrame, cats: pd.DataFrame,
                   items: pd.DataFrame, depts: pd.DataFrame, ccs: pd.DataFrame,
                   gl: pd.DataFrame, contract_price: pd.DataFrame,
                   ep: EventPlan, rng: np.random.Generator):
    """Returns (invoice, invoice_line, invoice_distribution, po_lines)."""
    inv_lines = _po_backed_lines(s, po, po_lines, gr_lines, ep, rng)
    heads, lines = _assemble_invoices(s, po, inv_lines, sup, sites, terms, rng)

    non_po_h, non_po_l = _non_po_invoices(s, heads, sup, sites, terms, cats, items,
                                          depts, ccs, contract_price, ep, rng)
    if len(non_po_h):
        heads = pd.concat([heads, non_po_h], ignore_index=True)
        lines = pd.concat([lines, non_po_l], ignore_index=True)

    heads, lines = _plant_duplicates(s, heads, lines, sup, ep, rng)
    heads, lines = _credit_memos(s, heads, lines, rng)
    heads = _apply_currency_and_terms(s, heads, sup, terms, fx, rng)

    heads["invoice_id"] = np.arange(1, len(heads) + 1, dtype=np.int64)
    id_map = dict(zip(heads["_inv_seq"], heads["invoice_id"]))
    lines["invoice_id"] = lines["_inv_seq"].map(id_map)
    lines = lines[lines["invoice_id"].notna()].reset_index(drop=True)
    lines["invoice_id"] = lines["invoice_id"].astype("int64")
    lines["invoice_line_id"] = np.arange(1, len(lines) + 1, dtype=np.int64)
    lines["line_number"] = (lines.groupby("invoice_id").cumcount() + 1).astype("int16")

    dist = _distributions(s, heads, lines, items, gl, rng)

    # Mark which PO lines were invoiced, so GR/IR is computable on the PO side.
    inv_qty = (lines[lines["purchase_order_line_id"] > 0]
               .groupby("purchase_order_line_id")["quantity_invoiced"].sum())
    inv_amt = (lines[lines["purchase_order_line_id"] > 0]
               .groupby("purchase_order_line_id")["line_amount_usd"].sum())
    po_lines = po_lines.copy()
    po_lines["quantity_invoiced"] = (po_lines["purchase_order_line_id"]
                                     .map(inv_qty).fillna(0.0).to_numpy())
    po_lines["invoiced_amount_usd"] = (po_lines["purchase_order_line_id"]
                                       .map(inv_amt).fillna(0.0).to_numpy())
    po_lines["is_invoiced"] = (po_lines["quantity_invoiced"] > 0).astype("int8")
    # GR/IR: goods received, no invoice against them.
    gr_ir_qty = np.maximum(0.0, po_lines["quantity_received"].to_numpy()
                           - po_lines["quantity_invoiced"].to_numpy())
    po_lines["gr_ir_amount_usd"] = np.round(
        gr_ir_qty * po_lines["unit_price_usd"].to_numpy(), 2)
    return heads, lines, dist, po_lines


def _po_backed_lines(s: Scenario, po: pd.DataFrame, po_lines: pd.DataFrame,
                     gr_lines: pd.DataFrame, ep: EventPlan,
                     rng: np.random.Generator) -> pd.DataFrame:
    """One candidate invoice line per PO line that is billable."""
    iv = s.invoicing
    tl = s.timeline

    live = po_lines[po_lines["receipt_state"] != "Cancelled"].copy()
    three = live["match_type"].to_numpy() == "3-Way"
    billable = np.where(three, live["is_received"].to_numpy() == 1,
                        live["receipt_state"].to_numpy() == "No Receipt Required")
    live = live[billable].copy()
    if live.empty:
        return live

    # Billing lag: from the last receipt for goods, from the PO for services.
    last_receipt = gr_lines.groupby("purchase_order_line_id")["receipt_date"].max() \
        if len(gr_lines) else pd.Series(dtype="object")
    base_date = pd.to_datetime(live["purchase_order_line_id"].map(last_receipt))
    base_date = base_date.fillna(pd.to_datetime(live["po_date"])
                                 + pd.to_timedelta(
                                     rng.integers(5, 40, size=len(live)), unit="D"))
    mu, sd = iv["receipt_to_invoice_days_lognorm"]
    lag = np.round(np.exp(rng.normal(mu, sd, size=len(live))))
    live["_invoice_date"] = base_date + pd.to_timedelta(lag, unit="D")

    # -- Event 15: the GR/IR pile ---------------------------------------------
    #
    # Never invoiced. Weighted towards older receipts so most of the balance is
    # aged past ninety days, which is what makes it a governance problem rather
    # than a timing one.
    ev = s.event("gr_ir_pile")
    never = np.zeros(len(live), dtype=bool)
    if ev is not None:
        age = (pd.Timestamp(tl.as_of_date) - live["_invoice_date"]).dt.days.to_numpy()
        old = age > 90
        p_old = 0.115
        p_new = 0.030
        never = np.where(old, rng.random(len(live)) < p_old,
                         rng.random(len(live)) < p_new)
    live = live[~never].copy()

    # Not yet invoiced simply because the lag has not elapsed.
    live = live[live["_invoice_date"] <= pd.Timestamp(tl.as_of_date)].copy()

    # -- quantity invoiced -----------------------------------------------------
    qty_recv = live["quantity_received"].to_numpy()
    qty_ord = live["quantity_ordered"].to_numpy()
    three = live["match_type"].to_numpy() == "3-Way"
    qty_inv = np.where(three, qty_recv, qty_ord)

    # Event 3: the supplier bills the ORDERED quantity even though it delivered
    # short. This is the classic three-way exception the note asks for.
    short = three & (qty_recv < qty_ord * 0.999)
    bill_full = short & (rng.random(len(live)) < 0.55)
    qty_inv = np.where(bill_full, qty_ord, qty_inv)
    # Ordinary quantity noise on a small share of everything else.
    noise = (rng.random(len(live)) < float(s.matching["qty_noise_share"])) & ~bill_full
    qty_inv = np.where(noise,
                       np.maximum(1, np.round(qty_inv * rng.uniform(0.97, 1.06,
                                                                   len(live)))),
                       qty_inv)

    # -- unit price invoiced ---------------------------------------------------
    po_price = live["unit_price_usd"].to_numpy()
    price_inv = po_price.copy()

    # Event 2: invoice priced above the PO. Concentrated on the same suppliers
    # that are already drifting off contract, so one root cause produces both.
    ev2 = s.event("invoice_amount_variance")
    if ev2 is not None:
        drift_sup = live["supplier_id"].isin(list(ep.price_drift)).to_numpy()
        r = ep.ramp_series("invoice_amount_variance", live["_invoice_date"].to_numpy())
        base_p = float(ev2["share_of_po_invoices"])
        p_hit = np.where(drift_sup, base_p * 4.5, base_p * 0.55) * np.maximum(r, 0.2)
        hit = rng.random(len(live)) < p_hit
        price_inv = np.where(hit, price_inv * (1 + rng.uniform(0.03, 0.19, len(live))),
                             price_inv)

    # Small price noise everywhere - most of it inside tolerance, which is what
    # makes the tolerance policy matter.
    small = rng.random(len(live)) < float(s.matching["price_noise_share"])
    lo, hi = s.matching["price_noise_pct"]
    price_inv = np.where(small, price_inv * (1 + rng.uniform(lo, hi, len(live))),
                         price_inv)

    live["_qty_invoiced"] = qty_inv
    live["_unit_price_invoiced"] = np.round(price_inv, 4)
    live["_line_amount"] = np.round(qty_inv * price_inv, 2)
    return live


def _assemble_invoices(s: Scenario, po: pd.DataFrame, cand: pd.DataFrame,
                       sup: pd.DataFrame, sites: pd.DataFrame, terms: pd.DataFrame,
                       rng: np.random.Generator):
    """Group candidate lines into invoice documents."""
    if cand.empty:
        return pd.DataFrame(), pd.DataFrame()
    iv = s.invoicing

    # Instalment billing: a share of POs are invoiced in several tranches, which
    # is the mechanism behind a funnel that widens from PO to invoice.
    po_ids = cand["purchase_order_id"].unique()
    multi = set(po_ids[rng.random(len(po_ids)) < float(iv["multi_invoice_po_share"])])
    lo, hi = iv["invoices_per_multi_po"]
    tranche = np.where(cand["purchase_order_id"].isin(multi).to_numpy(),
                       rng.integers(0, hi, size=len(cand)), 0)

    cand = cand.copy()
    cand["_tranche"] = tranche
    # Later tranches are billed later.
    cand["_invoice_date"] = (cand["_invoice_date"]
                             + pd.to_timedelta(cand["_tranche"] * 8, unit="D"))
    cand = cand[cand["_invoice_date"] <= pd.Timestamp(s.timeline.as_of_date)]
    if cand.empty:
        return pd.DataFrame(), pd.DataFrame()

    cand["_inv_seq"] = cand.groupby(
        ["purchase_order_id", "_tranche"], sort=False).ngroup()

    heads = (cand.groupby("_inv_seq")
             .agg(purchase_order_id=("purchase_order_id", "first"),
                  supplier_id=("supplier_id", "first"),
                  # MAX, not first: an invoice can carry a two-way line dated
                  # off the PO alongside a three-way line received later, and
                  # taking the first line's date bills goods before they arrive.
                  invoice_date=("_invoice_date", "max"),
                  match_type=("match_type", "first"),
                  department_id=("department_id", "first"),
                  cost_center_id=("cost_center_id", "first"),
                  line_count=("_line_amount", "count"),
                  gross_amount_usd=("_line_amount", "sum"))
             .reset_index())
    po_idx = po.set_index("purchase_order_id")
    heads["company_code"] = po_idx.loc[heads["purchase_order_id"],
                                       "company_code"].to_numpy()
    heads["is_non_po"] = 0
    heads["non_po_reason"] = ""
    heads["source_channel"] = rng.choice(SOURCE_CHANNELS, size=len(heads),
                                         p=[0.34, 0.29, 0.24, 0.06, 0.07])
    # The PO line's own price and amount are renamed alongside the invoiced
    # ones - `line_amount_usd` exists on both sides, and renaming only one of
    # them leaves two columns with the same name.
    lines = cand.rename(columns={
        "_qty_invoiced": "quantity_invoiced",
        "_unit_price_invoiced": "unit_price_usd",
        "_line_amount": "line_amount_usd",
        "unit_price_usd": "po_unit_price_usd",
        "line_amount_usd": "po_line_amount_usd"})[
        ["_inv_seq", "purchase_order_line_id", "purchase_order_id", "item_id",
         "category_id", "supplier_id", "quantity_invoiced", "unit_price_usd",
         "line_amount_usd", "po_unit_price_usd", "po_line_amount_usd",
         "quantity_ordered", "quantity_received", "match_type", "gl_account_id",
         "segment_name", "department_id", "cost_center_id"]].copy()
    lines["tax_code"] = rng.choice(TAX_CODES, size=len(lines),
                                   p=[0.62, 0.14, 0.11, 0.08, 0.05])
    return heads, lines


def _non_po_invoices(s: Scenario, po_heads: pd.DataFrame, sup: pd.DataFrame,
                     sites: pd.DataFrame, terms: pd.DataFrame, cats: pd.DataFrame,
                     items: pd.DataFrame, depts: pd.DataFrame, ccs: pd.DataFrame,
                     contract_price: pd.DataFrame, ep: EventPlan,
                     rng: np.random.Generator):
    """Invoices with no purchase order - where maverick spend lives.

    Maverick is DERIVED, not drawn: an invoice is maverick when a contract with
    that supplier covered that category and was not used. That definition can be
    reproduced by anyone looking at the data, which a flag column cannot.
    """
    if po_heads.empty:
        return pd.DataFrame(), pd.DataFrame()
    share = float(s.channels["non_po_invoice_share_of_value"])
    po_value = float(po_heads["gross_amount_usd"].sum())
    # share is of TOTAL spend; PO-backed is the remainder after non-PO and card.
    po_share = 1.0 - share - float(s.channels["pcard_share_of_value"])
    target_value = po_value / max(po_share, 0.01) * share

    # Size the population off the MEAN of the draw, not its median. These
    # amounts are lognormal with sigma 1.05, whose mean sits exp(sigma^2/2) =
    # 1.74x above the median - dividing the target by the median overshoots the
    # non-PO channel by three quarters.
    sigma = 1.05
    med_inv = float(po_heads["gross_amount_usd"].median()) * 1.15
    mean_inv = med_inv * float(np.exp(sigma ** 2 / 2))
    n = max(1, int(round(target_value / max(mean_inv, 1.0))))

    tl = s.timeline
    span = (tl.as_of_date - tl.start_date).days
    inv_date = pd.to_datetime(tl.start_date) + pd.to_timedelta(
        rng.integers(0, span + 1, size=n), unit="D")

    # Departments: Event 1 concentrates maverick spend in a few of them.
    ev = s.event("maverick_spend")
    w = depts["_demand_weight"].to_numpy().copy()
    if ev is not None and len(ep.maverick_departments):
        hot = depts["department_id"].isin(ep.maverick_departments).to_numpy()
        conc = float(ev["concentration"])
        n_hot = max(int(hot.sum()), 1)
        n_cold = max(len(depts) - n_hot, 1)
        # Solve for the weight ratio that puts `conc` of the value in the hot
        # departments, rather than multiplying by a hand-tuned constant and
        # hoping. Six departments out of ninety-six need a ~30x lift to hold 68%.
        ratio = (conc / n_hot) / max((1 - conc) / n_cold, 1e-9)
        w = np.where(hot, w * ratio, w)
    w = w / w.sum()
    d_pick = rng.choice(len(depts), size=n, p=w)
    dept = depts.iloc[d_pick].reset_index(drop=True)

    cc_by_dept = {int(k): g["cost_center_id"].to_numpy()
                  for k, g in ccs.groupby("department_id")}
    all_cc = ccs["cost_center_id"].to_numpy()
    cost_center = np.array([
        (cc_by_dept.get(int(x), all_cc))[rng.integers(0, len(cc_by_dept.get(int(x), all_cc)))]
        for x in dept["department_id"]])

    # Category and supplier. For most invoices these are drawn independently, so
    # no contract covers them and the spend is simply unmanaged. For a targeted
    # share, the pair is drawn FROM the contracted pairs - a contract existed
    # and the buyer went round it, which is what maverick spend actually means.
    leaf = cats.sample(n=n, replace=True, weights=cats["_spend_weight"],
                       random_state=int(s.seed) + 701).reset_index(drop=True)
    supplier = sup.sample(n=n, replace=True, weights=sup["_spend_weight"],
                          random_state=int(s.seed) + 702)["supplier_id"].to_numpy().copy()

    leaf_cat = leaf["category_id"].to_numpy().copy()
    p_mav = float(ev["contracted_pair_share"]) if ev else 0.0
    if p_mav > 0 and len(contract_price):
        pairs = contract_price[["supplier_id", "category_id"]].drop_duplicates()
        w = sup.set_index("supplier_id")["_spend_weight"]
        pw = pairs["supplier_id"].map(w).fillna(1e-9).to_numpy()
        pw = pw / pw.sum()
        pick_mav = rng.random(n) < p_mav
        k = int(pick_mav.sum())
        if k:
            chosen = rng.choice(len(pairs), size=k, p=pw)
            supplier[pick_mav] = pairs["supplier_id"].to_numpy()[chosen]
            leaf_cat[pick_mav] = pairs["category_id"].to_numpy()[chosen]

    amount = np.round(np.exp(rng.normal(np.log(med_inv), sigma, size=n)), 2)

    seq0 = int(po_heads["_inv_seq"].max()) + 1
    heads = pd.DataFrame({
        "_inv_seq": np.arange(seq0, seq0 + n),
        "purchase_order_id": 0,
        "supplier_id": supplier,
        "invoice_date": inv_date,
        "match_type": "Non-PO",
        "department_id": dept["department_id"].to_numpy(),
        "cost_center_id": cost_center,
        "line_count": 1,
        "gross_amount_usd": amount,
        "company_code": dept["company_code"].to_numpy(),
        "is_non_po": 1,
        "non_po_reason": rng.choice(NON_PO_REASONS, size=n),
        "source_channel": rng.choice(SOURCE_CHANNELS, size=n,
                                     p=[0.12, 0.46, 0.05, 0.22, 0.15]),
    })

    item_by_leaf = {int(k): g["item_id"].to_numpy() for k, g in
                    items.groupby("category_id")}
    all_items = items["item_id"].to_numpy()
    item = np.array([(item_by_leaf.get(int(l), all_items))[
        rng.integers(0, len(item_by_leaf.get(int(l), all_items)))]
        for l in leaf_cat])
    item_idx = items.set_index("item_id")

    lines = pd.DataFrame({
        "_inv_seq": heads["_inv_seq"].to_numpy(),
        "purchase_order_line_id": 0,
        "purchase_order_id": 0,
        "item_id": item,
        "category_id": leaf_cat,
        "supplier_id": supplier,
        "quantity_invoiced": 1.0,
        "unit_price_usd": amount,
        "line_amount_usd": amount,
        "po_unit_price_usd": np.nan,
        "po_line_amount_usd": np.nan,
        "quantity_ordered": np.nan,
        "quantity_received": np.nan,
        "match_type": "Non-PO",
        "gl_account_id": item_idx.loc[item, "gl_account_id"].to_numpy(),
        "segment_name": item_idx.loc[item, "segment_name"].to_numpy(),
        "department_id": heads["department_id"].to_numpy(),
        "cost_center_id": heads["cost_center_id"].to_numpy(),
        "tax_code": rng.choice(TAX_CODES, size=n, p=[0.62, 0.14, 0.11, 0.08, 0.05]),
    })

    # Maverick: a contract with this supplier covered this category, and it was
    # bypassed. Derived from contract_price, never flagged.
    cp = set(zip(contract_price["supplier_id"].to_numpy(),
                 contract_price["category_id"].to_numpy()))
    heads["is_maverick_spend"] = [
        int((int(sid), int(cid)) in cp)
        for sid, cid in zip(supplier, leaf_cat)]
    return heads, lines


def _plant_duplicates(s: Scenario, heads: pd.DataFrame, lines: pd.DataFrame,
                      sup: pd.DataFrame, ep: EventPlan, rng: np.random.Generator):
    """Event 7: four duplicate archetypes, some of them paid."""
    heads = heads.copy()
    heads["duplicate_archetype"] = ""
    heads["duplicate_of_inv_seq"] = 0
    ev = s.event("duplicate_invoices")
    if ev is None or heads.empty:
        return heads, lines

    win = s.event_window("duplicate_invoices")
    lo_d, hi_d = win
    eligible = heads[(heads["invoice_date"] >= pd.Timestamp(lo_d))
                     & (heads["invoice_date"] <= pd.Timestamp(hi_d))
                     & (heads["gross_amount_usd"] > 500)]
    k = min(int(ev["suspected_count"] * s.tier_scale), len(eligible))
    if k <= 0:
        return heads, lines
    src = eligible.sample(n=k, random_state=int(s.seed) + 801)

    mix = ev["archetype_mix"]
    archetypes = list(mix)
    probs = np.array([float(mix[a]) for a in archetypes])
    probs = probs / probs.sum()
    kind = rng.choice(archetypes, size=k, p=probs)

    dup_of_sup = dict(zip(sup["supplier_id"], sup["duplicate_of_supplier_id"]))
    variants = sup[sup["is_duplicate_variant"] == 1]
    variant_by_base: dict[int, list[int]] = {}
    for _, r in variants.iterrows():
        variant_by_base.setdefault(int(r["duplicate_of_supplier_id"]), []).append(
            int(r["supplier_id"]))

    seq0 = int(heads["_inv_seq"].max()) + 1
    new_heads, new_lines = [], []
    line_by_seq = {k_: g for k_, g in lines.groupby("_inv_seq")}
    for i, (_, r) in enumerate(src.iterrows()):
        nh = r.copy()
        nh["_inv_seq"] = seq0 + i
        nh["duplicate_archetype"] = str(kind[i])
        nh["duplicate_of_inv_seq"] = int(r["_inv_seq"])
        if kind[i] == "duplicate_supplier_record":
            # Entered against the OTHER master record for the same vendor. This
            # is where the supplier-duplication story pays off twice.
            alts = variant_by_base.get(int(r["supplier_id"]), [])
            if not alts:
                base = dup_of_sup.get(int(r["supplier_id"]), 0)
                alts = [int(base)] if base else []
            if alts:
                nh["supplier_id"] = int(alts[0])
        if kind[i] == "double_entry_channel":
            # Same invoice arrived twice: once through the portal, once by email.
            nh["source_channel"] = "Email PDF" if r["source_channel"] != "Email PDF" \
                else "Supplier Portal"
        nh["invoice_date"] = r["invoice_date"] + pd.Timedelta(
            days=int(rng.integers(0, 11)))
        if kind[i] == "unapplied_credit_memo":
            # The honest false positive: a rebill that looks like a duplicate.
            nh["gross_amount_usd"] = float(r["gross_amount_usd"])
        new_heads.append(nh)
        sub = line_by_seq.get(int(r["_inv_seq"]))
        if sub is not None:
            nl = sub.copy()
            nl["_inv_seq"] = seq0 + i
            if kind[i] == "duplicate_supplier_record" and alts:
                nl["supplier_id"] = int(alts[0])
            new_lines.append(nl)
    if new_heads:
        heads = pd.concat([heads, pd.DataFrame(new_heads)], ignore_index=True)
        lines = pd.concat([lines] + new_lines, ignore_index=True)
    return heads, lines


def _credit_memos(s: Scenario, heads: pd.DataFrame, lines: pd.DataFrame,
                  rng: np.random.Generator):
    heads = heads.copy()
    heads["invoice_type"] = "Standard Invoice"
    share = float(s.invoicing["credit_memo_share"])
    if heads.empty or share <= 0:
        return heads, lines
    n = int(len(heads) * share)
    src = heads[heads["gross_amount_usd"] > 0].sample(
        n=min(n, len(heads)), random_state=int(s.seed) + 802)
    seq0 = int(heads["_inv_seq"].max()) + 1
    memos = src.copy().reset_index(drop=True)
    memos["_inv_seq"] = np.arange(seq0, seq0 + len(memos))
    memos["invoice_type"] = "Credit Memo"
    memos["gross_amount_usd"] = -np.round(
        memos["gross_amount_usd"].to_numpy()
        * rng.uniform(0.1, 0.9, size=len(memos)), 2)
    memos["invoice_date"] = memos["invoice_date"] + pd.to_timedelta(
        rng.integers(5, 90, size=len(memos)), unit="D")
    memos = memos[memos["invoice_date"] <= pd.Timestamp(s.timeline.as_of_date)]
    memos["duplicate_archetype"] = ""
    memos["duplicate_of_inv_seq"] = 0
    heads = pd.concat([heads, memos], ignore_index=True)
    return heads, lines


def _apply_currency_and_terms(s: Scenario, heads: pd.DataFrame, sup: pd.DataFrame,
                              terms: pd.DataFrame, fx: pd.DataFrame,
                              rng: np.random.Generator) -> pd.DataFrame:
    sup_idx = sup.set_index("supplier_id")
    heads = heads.copy()
    heads["currency_code"] = sup_idx.loc[heads["supplier_id"],
                                         "currency_code"].to_numpy()
    heads["supplier_site_id"] = 0

    heads["_rate_date"] = pd.to_datetime(heads["invoice_date"]).dt.date
    heads = heads.merge(
        fx[["currency_code", "rate_date", "rate_to_usd"]],
        left_on=["currency_code", "_rate_date"],
        right_on=["currency_code", "rate_date"], how="left")
    heads["exchange_rate"] = heads["rate_to_usd"].fillna(1.0)
    heads = heads.drop(columns=["_rate_date", "rate_date", "rate_to_usd"])
    # Amounts are generated in USD; the local amount is what the ERP extract
    # would carry, and is what makes the FX red herring visible.
    heads["gross_amount_local"] = np.round(
        heads["gross_amount_usd"] / heads["exchange_rate"], 2)

    tw = terms["_weight"].to_numpy() / terms["_weight"].sum()
    drawn = rng.choice(terms["payment_terms_code"].to_numpy(), size=len(heads), p=tw)
    heads["payment_terms_code"] = drawn
    parsed = [parse_terms(c) for c in heads["payment_terms_code"]]
    heads["discount_percent"] = [p[0] for p in parsed]
    heads["discount_days"] = [p[1] for p in parsed]
    heads["net_days"] = [p[2] for p in parsed]

    # Invoices arrive after they are dated - post, scanning, portal upload.
    heads["invoice_received_date"] = (pd.to_datetime(heads["invoice_date"])
                                      + pd.to_timedelta(
                                          rng.integers(0, 5, size=len(heads)),
                                          unit="D"))
    heads["due_date"] = (pd.to_datetime(heads["invoice_date"])
                         + pd.to_timedelta(heads["net_days"], unit="D"))
    heads["discount_due_date"] = (pd.to_datetime(heads["invoice_date"])
                                  + pd.to_timedelta(heads["discount_days"], unit="D"))
    heads["tax_amount_usd"] = np.round(heads["gross_amount_usd"] * 0.0, 2)
    heads["net_amount_usd"] = heads["gross_amount_usd"]
    heads["invoice_number"] = _invoice_numbers(heads, rng)
    heads["is_duplicate_suspect"] = (heads["duplicate_archetype"] != "").astype("int8")
    if "is_maverick_spend" not in heads.columns:
        heads["is_maverick_spend"] = 0
    heads["is_maverick_spend"] = heads["is_maverick_spend"].fillna(0).astype("int8")
    return heads


def _invoice_numbers(heads: pd.DataFrame, rng: np.random.Generator) -> list[str]:
    """Supplier-side invoice numbers, with the formatting variants that make
    duplicate detection a fuzzy-match problem rather than a GROUP BY."""
    base = [f"{'INV' if i % 3 else 'SI'}-{int(rng.integers(10000, 999999))}"
            for i in range(len(heads))]
    out = list(base)
    arche = heads["duplicate_archetype"].to_numpy()
    dup_of = heads["duplicate_of_inv_seq"].to_numpy()
    seq_pos = {int(s_): i for i, s_ in enumerate(heads["_inv_seq"].to_numpy())}
    for i in range(len(heads)):
        if arche[i] == "formatting_variant":
            j = seq_pos.get(int(dup_of[i]))
            if j is None:
                continue
            src = out[j]
            style = int(rng.integers(0, 3))
            if style == 0:
                out[i] = src.replace("-", "")
            elif style == 1:
                head_, _, tail = src.partition("-")
                out[i] = f"{head_}-0{tail}"
            else:
                out[i] = src.lower()
        elif arche[i] in ("duplicate_supplier_record", "double_entry_channel"):
            j = seq_pos.get(int(dup_of[i]))
            if j is not None:
                out[i] = out[j]          # genuinely the same number, other record
    return out


def _distributions(s: Scenario, heads: pd.DataFrame, lines: pd.DataFrame,
                   items: pd.DataFrame, gl: pd.DataFrame,
                   rng: np.random.Generator) -> pd.DataFrame:
    """GL coding. For a non-PO invoice this is the ONLY link to a cost centre."""
    if lines.empty:
        return pd.DataFrame()
    # Most lines code to one account; some split across two cost centres.
    split = rng.random(len(lines)) < 0.14
    first = lines.copy()
    first["distribution_percent"] = np.where(split, 0.6, 1.0)
    second = lines[split].copy()
    second["distribution_percent"] = 0.4
    all_cc = None
    if len(second):
        all_cc = second["cost_center_id"].sample(
            frac=1.0, random_state=int(s.seed) + 803).to_numpy()
        second["cost_center_id"] = all_cc
    dist = pd.concat([first, second], ignore_index=True)
    dist["amount_usd"] = np.round(dist["line_amount_usd"]
                                  * dist["distribution_percent"], 2)
    dist["invoice_distribution_id"] = np.arange(1, len(dist) + 1, dtype=np.int64)
    keep = ["invoice_distribution_id", "invoice_id", "invoice_line_id",
            "gl_account_id", "cost_center_id", "department_id", "amount_usd",
            "distribution_percent"]
    return dist[[c for c in keep if c in dist.columns]]
