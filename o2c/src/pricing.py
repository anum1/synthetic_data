"""Contract pricing, and the one place a priced line is ever constructed.

`price_lines` is shared by quotes.py (quote lines) and orders.py (lines on
direct orders that never had a quote). Having one implementation is not tidiness
- if quotes and orders priced independently, the quote-to-order value bridge
would show a variance that is a generator artefact rather than a business fact,
and that is exactly the kind of thing an audience notices and cannot unsee.

Order lines converted from a won quote do NOT come through here: they inherit
the quote's prices, because that is what conversion means.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from o2cconfig import Scenario


def build_contract_pricing(s: Scenario, cust: pd.DataFrame, prod: pd.DataFrame,
                           rng: np.random.Generator) -> pd.DataFrame:
    """Negotiated price per customer x product, with validity dates.

    This table is the reason the pricing-leakage story is checkable. Without a
    contracted price there is nothing for an invoice price to be wrong against,
    and "invoice price < contracted price" is an assertion rather than a
    measurement.

    Coverage is deliberately partial: bigger customers have contracts on more of
    the catalogue, small ones buy at list less a standard discount. That gap is
    itself a demo question - "which spend is off-contract?"
    """
    cov = float(s.pricing["contract_coverage"])
    lo, hi = s.pricing["contract_discount_range"]
    term = int(s.pricing["contract_term_months"])
    tl = s.timeline

    n_prod = len(prod)
    # Contract breadth is a COUNT of SKUs per customer, not a fraction of the
    # catalogue. A buyer negotiates the lines they actually consume, so doubling
    # the catalogue does not double every contract - it widens them a little.
    # Expressed as a fraction, this table grows quadratically with tier and ends
    # up larger than the order lines it is supposed to price.
    scale = (n_prod / 600.0) ** 0.5 * (cov / 0.62)
    breadth = cust["customer_segment"].map(
        {"Strategic": 120, "Enterprise": 45, "Mid-Market": 16,
         "Small Business": 4}).to_numpy() * scale

    prices = prod["list_price_usd"].to_numpy()
    rows_c, rows_p = [], []
    for cid, br in zip(cust["customer_id"].to_numpy(), breadth):
        k = int(min(rng.poisson(br), n_prod))
        if k == 0:
            continue
        picks = rng.choice(n_prod, size=k, replace=False)
        rows_c.append(np.full(k, cid, dtype=np.int64))
        rows_p.append(picks)
    if not rows_c:
        return pd.DataFrame()

    cid_arr = np.concatenate(rows_c)
    pidx = np.concatenate(rows_p)
    n = len(cid_arr)

    seg = cust.set_index("customer_id")["customer_segment"].reindex(cid_arr).to_numpy()
    # Bigger customers negotiate harder, which is why margin erodes with size -
    # a genuinely interesting thing for the AI to surface on its own.
    seg_bonus = pd.Series(seg).map(
        {"Strategic": 0.10, "Enterprise": 0.05, "Mid-Market": 0.015,
         "Small Business": 0.0}).to_numpy()
    disc = np.clip(rng.uniform(lo, hi, n) + seg_bonus, 0.01, 0.55)

    list_usd = prices[pidx]
    contract_price = np.round(list_usd * (1.0 - disc), 2)

    # Contracts start staggered across history and run `term` months, so at any
    # as-of date some are current, some expired and some renewed. "Which
    # contracts expire in the next 90 days" is a question this makes answerable.
    start_offset = rng.integers(-int(term * 1.6), 6, n)
    starts = np.array([tl.offset_month(int(o)) for o in start_offset])
    ends = np.array([tl.offset_month(int(o) + term) - dt.timedelta(days=1)
                     for o in start_offset])

    df = pd.DataFrame({
        "contract_price_id": np.arange(1, n + 1, dtype="int32"),
        "contract_id": [f"CON-{int(c):06d}-{int(o) % 97:02d}"
                        for c, o in zip(cid_arr, start_offset)],
        "customer_id": cid_arr.astype("int32"),
        "product_id": prod["product_id"].to_numpy()[pidx].astype("int32"),
        "list_price_usd": list_usd,
        "contract_price_usd": contract_price,
        "contract_discount_pct": np.round(disc, 4),
        "min_price_usd": np.round(contract_price * 0.97, 2),
        "rebate_pct": np.round(np.where(rng.random(n) < 0.22,
                                        rng.uniform(0.005, 0.04, n), 0.0), 4),
        "valid_from_date": starts,
        "valid_to_date": ends,
        "price_basis": np.where(rng.random(n) < 0.14, "Volume Tier", "Standard"),
    })
    df["is_current"] = ((df["valid_from_date"] <= tl.as_of_date)
                        & (df["valid_to_date"] >= tl.as_of_date)).astype("int8")
    return df


def customer_product_index(cust: pd.DataFrame, contracts: pd.DataFrame):
    """Flat (customer -> contracted product) lookup with per-customer offsets.

    Lets a line pick one of its customer's contracted SKUs with pure numpy
    arithmetic instead of a per-row groupby, which is the difference between
    seconds and minutes at 800K lines.
    """
    max_cid = int(cust["customer_id"].max())
    if contracts is None or contracts.empty:
        return (np.zeros(0, dtype=np.int32), np.zeros(max_cid + 2, dtype=np.int64),
                np.zeros(max_cid + 2, dtype=np.int64))
    c = contracts.sort_values("customer_id")
    prods = c["product_id"].to_numpy(dtype=np.int32)
    counts = np.bincount(c["customer_id"].to_numpy(), minlength=max_cid + 2)
    offsets = np.concatenate([[0], np.cumsum(counts)])[: max_cid + 2]
    return prods, offsets, counts[: max_cid + 2]


def lookup_contract_price(contracts: pd.DataFrame, customer_id, product_id,
                          on_date) -> np.ndarray:
    """Contracted price for each (customer, product) as at `on_date`; NaN if none.

    One row per (customer, product) by construction, so this is a plain reindex
    rather than an as-of join.
    """
    n = len(customer_id)
    if contracts is None or contracts.empty:
        return np.full(n, np.nan)
    key = pd.MultiIndex.from_arrays([np.asarray(customer_id), np.asarray(product_id)])
    hit = contracts.set_index(["customer_id", "product_id"]).reindex(key)
    d = pd.to_datetime(pd.Series(on_date)).to_numpy()
    valid = ((pd.to_datetime(hit["valid_from_date"]).to_numpy() <= d)
             & (pd.to_datetime(hit["valid_to_date"]).to_numpy() >= d)
             & hit["contract_price_usd"].notna().to_numpy())
    return np.where(valid, hit["contract_price_usd"].to_numpy(), np.nan)


def price_lines(s: Scenario, ep: EventPlan, rng: np.random.Generator,
                doc_customer_id: np.ndarray, doc_date: np.ndarray,
                doc_rep_id: np.ndarray, n_lines: np.ndarray,
                cust: pd.DataFrame, prod: pd.DataFrame,
                contracts: pd.DataFrame) -> pd.DataFrame:
    """Explode documents into priced lines.

    Returns one row per line with the parent document's ordinal position in
    `doc_index`, so the caller attaches its own key.
    """
    doc_index = np.repeat(np.arange(len(doc_customer_id)), n_lines)
    line_cust = np.asarray(doc_customer_id)[doc_index]
    line_date = np.asarray(doc_date)[doc_index]
    line_rep = np.asarray(doc_rep_id)[doc_index]
    nl = len(doc_index)

    # 65% of lines come off the customer's contracted SKUs, the rest are
    # off-contract buys. That split is what makes "how much spend is
    # off-contract" a question with an answer.
    cp_prod, cp_off, cp_cnt = customer_product_index(cust, contracts)
    has_contract = cp_cnt[line_cust] > 0
    want_contract = (rng.random(nl) < 0.65) & has_contract
    pool = prod["product_id"].to_numpy()
    product_id = pool[rng.integers(0, len(pool), nl)]
    if cp_cnt.sum():
        sel = np.where(want_contract)[0]
        within = (rng.random(len(sel)) * cp_cnt[line_cust[sel]]).astype(np.int64)
        product_id[sel] = cp_prod[cp_off[line_cust[sel]] + within]

    pmap = prod.set_index("product_id")
    list_price = pmap["list_price_usd"].reindex(product_id).to_numpy()
    unit_cost = pmap["unit_cost_usd"].reindex(product_id).to_numpy()

    mu_q, sig_q = s.demand["order_line_qty_lognorm"]
    quantity = np.maximum(1, np.round(np.exp(rng.normal(mu_q, sig_q, nl))))
    # Expensive items are bought in smaller quantities. Without this the line
    # value distribution grows an implausible tail of 200-gearbox orders.
    quantity = np.maximum(
        1, np.round(quantity / np.clip(list_price / 60.0, 1.0, 40.0))).astype(np.int64)

    contract_price = lookup_contract_price(contracts, line_cust, product_id, line_date)

    dlo, dhi = s.pricing["standard_discount_range"]
    std_disc = rng.uniform(dlo, dhi, nl)
    # Volume breaks: bigger lines earn a little more off, which gives the
    # margin-by-order-size cut something real to show.
    std_disc += np.where(quantity >= int(s.pricing["volume_break_qty"]),
                         float(s.pricing["volume_break_extra_discount"]), 0.0)

    # Event 2: a few reps ramp their discounting from 8% to 26%.
    ev = s.event("discount_explosion")
    rep_hit = in_win = None
    if ev is not None and len(ep.discount_reps):
        rep_hit = np.isin(line_rep, ep.discount_reps)
        in_win = ep.in_window("discount_explosion", line_date)
        target = ep.blend("discount_explosion", line_date,
                          float(ev["discount_from"]), float(ev["discount_to"]))
        std_disc = np.where(rep_hit & in_win,
                            np.clip(target + rng.normal(0, 0.02, nl), 0.02, 0.45),
                            std_disc)

    unit_price = np.where(np.isnan(contract_price),
                          list_price * (1.0 - std_disc), contract_price)
    # An over-discounting rep discounts off whatever price applies, including a
    # contracted one - which is precisely the behaviour the event is about, and
    # letting the contract override it would hide the story on the accounts
    # where it matters most.
    if rep_hit is not None:
        forced = list_price * (1.0 - std_disc)
        unit_price = np.where(rep_hit & in_win, np.minimum(unit_price, forced),
                              unit_price)

    unit_price = np.round(np.maximum(unit_price, unit_cost * 1.02), 2)
    extended = np.round(unit_price * quantity, 2)
    ext_cost = np.round(unit_cost * quantity, 2)

    return pd.DataFrame({
        "doc_index": doc_index,
        "line_number": _line_numbers(n_lines),
        "product_id": product_id.astype("int32"),
        "quantity": quantity,
        "list_price_usd": np.round(list_price, 2),
        "unit_price_usd": unit_price,
        "discount_pct": np.round(1.0 - unit_price / np.maximum(list_price, 0.01), 4),
        "extended_amount_usd": extended,
        "unit_cost_usd": np.round(unit_cost, 2),
        "extended_cost_usd": ext_cost,
        "margin_usd": np.round(extended - ext_cost, 2),
        "contract_price_usd": np.round(np.nan_to_num(contract_price, nan=0.0), 2),
        "is_contract_price": (~np.isnan(contract_price)).astype("int8"),
    })


def _line_numbers(n_lines: np.ndarray) -> np.ndarray:
    """1..k within each document, without a groupby."""
    n_lines = np.asarray(n_lines)
    total = int(n_lines.sum())
    starts = np.concatenate([[0], np.cumsum(n_lines)[:-1]])
    return (np.arange(total) - np.repeat(starts, n_lines) + 1).astype("int32")
