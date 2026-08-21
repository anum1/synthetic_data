"""Quote generation, win/loss, and conversion to orders.

The win decision is a function of discount, deal size, segment and region, not a
coin flip. That matters for two of the demo questions: "which reps are
discounting more than their peers" is only interesting if discounting actually
buys volume, and "which customers receive the most quotes but buy the least" is
only real if losing correlates with something.

Quote volume is derived from the target ORDER volume, not configured directly.
Orders are what the business is sized on; quotes are however many it takes to
win them. So when Event 1 halves EMEA's win rate, EMEA's orders fall - the quote
count does not silently inflate to compensate, which is what would happen if
quotes were the configured quantity.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from events import EventPlan
from o2cconfig import Scenario, month_end
from pricing import price_lines


def monthly_order_targets(s: Scenario) -> pd.DataFrame:
    """Expected orders per month: base x compounding growth x seasonality."""
    months = s.timeline.month_starts()
    base = float(s.sizes["orders_per_month_base"])
    g = float(s.demand["annual_growth"])
    seas = s.demand["seasonality_by_month"]
    rows = []
    for i, m in enumerate(months):
        factor = (1.0 + g) ** (i / 12.0)
        rows.append((m, base * factor * float(seas[m.month - 1])))
    return pd.DataFrame(rows, columns=["month_start_date", "expected_orders"])


def draw_documents(s: Scenario, cust: pd.DataFrame, sites: pd.DataFrame,
                   reps: pd.DataFrame, counts_by_month: np.ndarray,
                   months: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    """Customer, rep, site and date for a batch of documents.

    Shared by quotes and by direct orders, so both streams draw customers from
    the same spend-weighted distribution and the concentration story holds
    across the whole book rather than only the quoted part.
    """
    month_idx = np.repeat(np.arange(len(months)), counts_by_month)
    month_start = np.asarray(months)[month_idx]
    day = np.array([rng.integers(0, (month_end(m) - m).days + 1) for m in month_start])
    doc_date = np.array([m + dt.timedelta(days=int(d)) for m, d in zip(month_start, day)])

    w = cust["_spend_weight"].to_numpy()
    pick = rng.choice(len(cust), size=len(doc_date), p=w / w.sum())

    region = cust["region"].to_numpy()[pick]
    rep_by_region = {r: g["sales_rep_id"].to_numpy() for r, g in reps.groupby("region")}
    all_reps = reps["sales_rep_id"].to_numpy()
    sales_rep_id = np.empty(len(pick), dtype=np.int64)
    for r in np.unique(region):
        m = region == r
        pool = rep_by_region.get(r, all_reps)
        sales_rep_id[m] = pool[rng.integers(0, len(pool), int(m.sum()))]

    prim = sites[sites["is_primary_site"] == 1].drop_duplicates("customer_id")
    ship_to = pd.Series(prim["site_id"].to_numpy(),
                        index=prim["customer_id"].to_numpy())
    bill = sites[sites["is_bill_to"] == 1].drop_duplicates("customer_id")
    bill_to = pd.Series(bill["site_id"].to_numpy(), index=bill["customer_id"].to_numpy())
    customer_id = cust["customer_id"].to_numpy()[pick]

    return pd.DataFrame({
        "doc_date": doc_date,
        "customer_id": customer_id,
        "sales_rep_id": sales_rep_id,
        "site_id": ship_to.reindex(customer_id).fillna(0).to_numpy().astype("int64"),
        "bill_to_site_id": bill_to.reindex(customer_id).fillna(0).to_numpy().astype("int64"),
        "region": region,
        "country": cust["country"].to_numpy()[pick],
        "business_unit": cust["business_unit"].to_numpy()[pick],
        "customer_segment": cust["customer_segment"].to_numpy()[pick],
        "currency_code": cust["currency_code"].to_numpy()[pick],
        "channel": cust["preferred_channel"].to_numpy()[pick],
        "payment_terms_code": cust["payment_terms_code"].to_numpy()[pick],
        "billing_rule": cust["billing_rule"].to_numpy()[pick],
    })


def build_quotes(s: Scenario, cust: pd.DataFrame, sites: pd.DataFrame,
                 prod: pd.DataFrame, reps: pd.DataFrame, contracts: pd.DataFrame,
                 ep: EventPlan, rng: np.random.Generator):
    """Return (quotes, quote_lines). Won quotes are the ones orders.py converts."""
    tl = s.timeline
    q = s.quoting
    targets = monthly_order_targets(s)

    n_by_month = np.maximum(1, np.round(
        targets["expected_orders"].to_numpy()
        * (1.0 - float(s.demand["direct_order_share"]))
        * float(q["quotes_per_won_quote"])).astype(int))

    doc = draw_documents(s, cust, sites, reps, n_by_month,
                         targets["month_start_date"].to_numpy(), rng)
    total = len(doc)
    quote_id = np.arange(1, total + 1, dtype=np.int64)

    n_lines = 1 + rng.poisson(float(s.demand["lines_per_order_lambda"]), total)
    lines = price_lines(s, ep, rng, doc["customer_id"].to_numpy(),
                        doc["doc_date"].to_numpy(), doc["sales_rep_id"].to_numpy(),
                        n_lines, cust, prod, contracts)
    lines.insert(0, "quote_id", quote_id[lines["doc_index"].to_numpy()])
    lines.insert(0, "quote_line_id", np.arange(1, len(lines) + 1, dtype="int64"))

    gross = lines["list_price_usd"].to_numpy() * lines["quantity"].to_numpy()
    agg = lines.assign(_gross=gross).groupby("quote_id").agg(
        quote_amount_usd=("_gross", "sum"),
        net_quote_amount_usd=("extended_amount_usd", "sum"),
        estimated_cost_usd=("extended_cost_usd", "sum"),
        line_count=("quote_line_id", "count")).reindex(quote_id).fillna(0.0)
    quote_amount = agg["quote_amount_usd"].to_numpy()
    net_amount = agg["net_quote_amount_usd"].to_numpy()
    est_cost = agg["estimated_cost_usd"].to_numpy()

    validity = int(q["quote_validity_days"])
    quote_date = doc["doc_date"].to_numpy()
    expiration = np.array([d + dt.timedelta(days=validity) for d in quote_date])

    # ---- win / loss ----------------------------------------------------------
    hdr_disc = np.where(quote_amount > 0, 1.0 - net_amount / quote_amount, 0.0)
    p = np.full(total, float(q["base_win_rate"]))
    p += (hdr_disc * 100.0) * float(q["win_lift_per_discount_point"]) / 10.0
    p += np.where(net_amount > np.quantile(net_amount, 0.85),
                  float(q["win_lift_large_deal"]), 0.0)
    p += doc["customer_segment"].map({"Strategic": 0.10, "Enterprise": 0.04,
                                      "Mid-Market": 0.0,
                                      "Small Business": -0.05}).to_numpy()

    # Event 1: one region's win rate collapses, phased in across the window.
    ev = s.event("quote_conversion_collapse")
    if ev is not None:
        mult = 1.0 + (float(ev["win_rate_multiplier"]) - 1.0) * ep.ramp(
            "quote_conversion_collapse", quote_date)
        p = np.where(doc["region"].to_numpy() == ev["region"], p * mult, p)

    p = np.clip(p, 0.02, 0.93)
    decided = expiration <= tl.as_of_date
    won = decided & (rng.random(total) < p)

    status = np.full(total, "Submitted", dtype=object)
    open_mix = q["status_mix_open"]
    status[~decided] = rng.choice(list(open_mix), size=int((~decided).sum()),
                                  p=list(open_mix.values()))
    # Of the quotes that did not convert, some were actively lost, some were
    # rejected on margin or credit, and some simply timed out. Expired pipeline
    # is its own demo question, so it needs its own status rather than a
    # catch-all "Lost".
    lost_pool = decided & ~won
    exp_share = float(q["expired_share_of_open"])
    r2 = rng.random(total)
    status[lost_pool & (r2 < exp_share)] = "Expired"
    status[lost_pool & (r2 >= exp_share) & (r2 < exp_share + 0.06)] = "Rejected"
    status[lost_pool & (r2 >= exp_share + 0.06)] = "Lost"
    status[won] = "Won"

    lost_reason = np.full(total, "Not Applicable", dtype=object)
    is_lost = np.isin(status, ["Lost", "Expired", "Rejected"])
    lost_reason[is_lost] = rng.choice(R.LOST_REASONS, size=int(is_lost.sum()),
                                      p=R.LOST_REASON_MIX)

    quotes = pd.DataFrame({
        "quote_id": quote_id.astype("int32"),
        "quote_number": [f"Q-{i:07d}" for i in quote_id],
        "customer_id": doc["customer_id"].to_numpy().astype("int32"),
        "site_id": doc["site_id"].to_numpy().astype("int32"),
        "sales_rep_id": doc["sales_rep_id"].to_numpy().astype("int32"),
        "quote_date": quote_date,
        "expiration_date": expiration,
        "currency_code": doc["currency_code"].to_numpy(),
        "region": doc["region"].to_numpy(),
        "country": doc["country"].to_numpy(),
        "business_unit": doc["business_unit"].to_numpy(),
        "customer_segment": doc["customer_segment"].to_numpy(),
        "channel": doc["channel"].to_numpy(),
        "line_count": agg["line_count"].to_numpy().astype("int16"),
        "quote_amount_usd": np.round(quote_amount, 2),
        "discount_amount_usd": np.round(quote_amount - net_amount, 2),
        "discount_pct": np.round(hdr_disc, 4),
        "net_quote_amount_usd": np.round(net_amount, 2),
        "estimated_cost_usd": np.round(est_cost, 2),
        "expected_margin_usd": np.round(net_amount - est_cost, 2),
        "expected_margin_pct": np.round(
            np.where(net_amount > 0, (net_amount - est_cost) / net_amount, 0.0), 4),
        "win_probability": np.round(p, 4),
        "quote_status": status,
        "lost_reason": lost_reason,
        "is_won": won.astype("int8"),
        "is_open": (~decided).astype("int8"),
        # filled in by orders.py once the order exists
        "converted_order_id": 0,
        "days_to_convert": 0,
    })

    lines = lines.drop(columns=["doc_index"]).rename(columns={
        "unit_price_usd": "quoted_price_usd",
        "extended_cost_usd": "estimated_cost_usd",
        "margin_usd": "estimated_margin_usd"})
    return quotes, lines, doc
