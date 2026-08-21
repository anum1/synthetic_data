"""Order booking, the credit-exposure ledger, and cancellations.

`fact_order` is the spine of the dataset: every other fact resolves back to it,
and the booking cohort it defines is what the whole waterfall is measured on.

Two things here are genuinely simulated rather than drawn.

**Credit exposure is a running ledger.** Orders are processed per customer in
date order against a limit that grows with the business. An order that would
take the customer past their limit goes on hold, and comes off hold on the day
enough earlier cash has landed to make room - which is a date the ledger knows,
not a random draw. Orders that never make room inside the cancellation window
are cancelled. Event 9 caps a group of customers' limits while their volume
keeps growing, so their holds emerge from arithmetic rather than a flag.

**The full lifecycle timing is drawn at booking.** Allocation, pick-pack,
transit, billing lag and days-to-pay are all decided here, so the expected cash
date exists before the order is a day old. That is what makes the exposure
ledger computable in one forward pass, and every downstream stage materialises
the dates this module already committed to rather than drawing its own.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from events import EventPlan
from o2cconfig import Scenario
from pricing import price_lines
from quotes import draw_documents, monthly_order_targets

_DAY = np.timedelta64(1, "D")


def build_orders(s: Scenario, quotes: pd.DataFrame, quote_lines: pd.DataFrame,
                 quote_doc: pd.DataFrame, cust: pd.DataFrame, sites: pd.DataFrame,
                 prod: pd.DataFrame, reps: pd.DataFrame, contracts: pd.DataFrame,
                 wh: pd.DataFrame, terms: pd.DataFrame, ep: EventPlan,
                 rng: np.random.Generator):
    """Return (orders, order_lines, quotes) - quotes updated with conversion."""
    won = quotes["is_won"] == 1
    n_won = int(won.sum())

    # ---- direct orders: real business, no quote ------------------------------
    targets = monthly_order_targets(s)
    n_direct = np.maximum(0, np.round(
        targets["expected_orders"].to_numpy()
        * float(s.demand["direct_order_share"])).astype(int))
    direct = draw_documents(s, cust, sites, reps, n_direct,
                            targets["month_start_date"].to_numpy(), rng)

    # ---- headers -------------------------------------------------------------
    lo, hi = s.quoting["quote_to_order_days"]
    convert_days = rng.integers(lo, hi + 1, n_won)
    won_doc = quote_doc[won.to_numpy()].reset_index(drop=True)
    won_q = quotes[won].reset_index(drop=True)
    won_dates = np.array([d + dt.timedelta(days=int(k))
                          for d, k in zip(won_q["quote_date"], convert_days)])

    head = pd.concat([
        won_doc.assign(doc_date=won_dates,
                       quote_id=won_q["quote_id"].to_numpy(),
                       source="Quote"),
        direct.assign(quote_id=0, source="Direct"),
    ], ignore_index=True)

    # Booked in date order. Every id in the dataset ascends with time, which is
    # what makes an id range a usable proxy for a date range in a live demo.
    head = head.sort_values("doc_date", kind="stable").reset_index(drop=True)
    head = head[head["doc_date"] <= s.timeline.as_of_date].reset_index(drop=True)
    n = len(head)
    order_id = np.arange(1, n + 1, dtype=np.int64)

    # ---- lines: inherited from the quote, or freshly priced ------------------
    q_to_order = pd.Series(order_id[head["quote_id"].to_numpy() > 0],
                           index=head.loc[head["quote_id"] > 0, "quote_id"].to_numpy())

    from_quote = quote_lines[quote_lines["quote_id"].isin(q_to_order.index)].copy()
    from_quote["order_id"] = q_to_order.reindex(from_quote["quote_id"]).to_numpy()
    from_quote = from_quote.rename(columns={
        "quoted_price_usd": "unit_price_usd",
        "estimated_cost_usd": "extended_cost_usd",
        "estimated_margin_usd": "margin_usd"})
    from_quote["quote_line_id_src"] = from_quote["quote_line_id"]

    direct_mask = head["quote_id"].to_numpy() == 0
    n_direct_orders = int(direct_mask.sum())
    n_lines = 1 + rng.poisson(float(s.demand["lines_per_order_lambda"]), n_direct_orders)
    fresh = price_lines(s, ep, rng, head.loc[direct_mask, "customer_id"].to_numpy(),
                        head.loc[direct_mask, "doc_date"].to_numpy(),
                        head.loc[direct_mask, "sales_rep_id"].to_numpy(),
                        n_lines, cust, prod, contracts)
    fresh["order_id"] = order_id[direct_mask][fresh["doc_index"].to_numpy()]
    fresh["quote_line_id_src"] = 0
    fresh = fresh.drop(columns=["doc_index"])

    keep = ["order_id", "line_number", "product_id", "quantity", "list_price_usd",
            "unit_price_usd", "discount_pct", "extended_amount_usd",
            "unit_cost_usd", "extended_cost_usd", "margin_usd",
            "contract_price_usd", "is_contract_price", "quote_line_id_src"]
    lines = pd.concat([from_quote[keep], fresh[keep]], ignore_index=True)
    lines = lines.sort_values(["order_id", "line_number"]).reset_index(drop=True)
    lines.insert(0, "order_line_id", np.arange(1, len(lines) + 1, dtype="int64"))

    # ---- header amounts are always the sum of the lines ----------------------
    gross = lines["list_price_usd"].to_numpy() * lines["quantity"].to_numpy()
    agg = lines.assign(_g=gross).groupby("order_id").agg(
        order_amount_usd=("_g", "sum"),
        net_order_amount_usd=("extended_amount_usd", "sum"),
        cost_amount_usd=("extended_cost_usd", "sum"),
        line_count=("order_line_id", "count"),
        total_quantity=("quantity", "sum")).reindex(order_id).fillna(0.0)

    net = agg["net_order_amount_usd"].to_numpy()
    gross_amt = agg["order_amount_usd"].to_numpy()
    cost = agg["cost_amount_usd"].to_numpy()

    tax_rate = head["region"].map(s.billing["tax_rate_by_region"]).fillna(0.08).to_numpy()
    flo, fhi = s.shipping["freight_pct_of_order"]
    freight_pct = rng.uniform(flo, fhi, n)
    tax = np.round(net * tax_rate, 2)
    freight = np.round(net * freight_pct, 2)

    order_date = head["doc_date"].to_numpy()
    priority = rng.choice(R.SHIPPING_PRIORITY, size=n, p=R.SHIPPING_PRIORITY_MIX)

    # ---- lifecycle timing, decided now so exposure is computable -------------
    timing = _draw_lifecycle(s, ep, head, lines, prod, terms, cust,
                             order_date, rng)

    # ---- the credit ledger ---------------------------------------------------
    credit = _run_credit_ledger(s, ep, head, net + tax + freight, order_date,
                                timing["expected_cash_date"], cust, rng)

    # Released orders start their lifecycle on the release date, not the order
    # date: a held order is not being picked. This is why credit holds show up
    # later as late deliveries, which is a chain worth letting the audience find.
    delay = credit["start_delay_days"]
    for col in ("planned_ship_date", "expected_delivery_date", "expected_invoice_date",
                "expected_cash_date"):
        timing[col] = timing[col] + delay.astype("timedelta64[D]")

    po = np.array([f"PO-{int(x):08d}" for x in rng.integers(10_000_000, 99_999_999, n)],
                  dtype=object)
    dq = s.data_quality
    if dq:
        # A deliberate defect with a downstream consequence: these become the
        # "Missing PO" disputes in collections.py, so the data-quality finding
        # and the AR exception are one story rather than two oddities.
        blank = rng.random(n) < float(dq.get("missing_po_share", 0.0))
        po[blank] = ""

    orders = pd.DataFrame({
        "order_id": order_id.astype("int32"),
        "order_number": [f"SO-{i:07d}" for i in order_id],
        "quote_id": head["quote_id"].to_numpy().astype("int32"),
        "customer_id": head["customer_id"].to_numpy().astype("int32"),
        "site_id": head["site_id"].to_numpy().astype("int32"),
        "bill_to_site_id": head["bill_to_site_id"].to_numpy().astype("int32"),
        "sales_rep_id": head["sales_rep_id"].to_numpy().astype("int32"),
        "order_date": order_date,
        "requested_delivery_date": timing["requested_delivery_date"],
        "promised_delivery_date": timing["promised_delivery_date"],
        "planned_ship_date": timing["planned_ship_date"],
        "order_source": head["source"].to_numpy(),
        "channel": head["channel"].to_numpy(),
        "region": head["region"].to_numpy(),
        "country": head["country"].to_numpy(),
        "business_unit": head["business_unit"].to_numpy(),
        "customer_segment": head["customer_segment"].to_numpy(),
        "currency_code": head["currency_code"].to_numpy(),
        "payment_terms_code": head["payment_terms_code"].to_numpy(),
        "billing_rule": head["billing_rule"].to_numpy(),
        "shipping_priority": priority,
        "po_number": po,
        "line_count": agg["line_count"].to_numpy().astype("int16"),
        "total_quantity": agg["total_quantity"].to_numpy().astype("int64"),
        "order_amount_usd": np.round(gross_amt, 2),
        "discount_amount_usd": np.round(gross_amt - net, 2),
        "net_order_amount_usd": np.round(net, 2),
        "tax_amount_usd": tax,
        "freight_amount_usd": freight,
        "total_order_amount_usd": np.round(net + tax + freight, 2),
        "cost_amount_usd": np.round(cost, 2),
        "gross_margin_usd": np.round(net - cost, 2),
        "gross_margin_pct": np.round(np.where(net > 0, (net - cost) / net, 0.0), 4),
        "credit_status": credit["credit_status"],
        "credit_hold_date": credit["hold_date"],
        "credit_release_date": credit["release_date"],
        "credit_limit_at_order_usd": np.round(credit["limit_at_order"], 2),
        "credit_exposure_at_order_usd": np.round(credit["exposure_before"], 2),
        "is_credit_hold": (credit["credit_status"] == "Credit Hold").astype("int8"),
        "cancelled_date": credit["cancelled_date"],
        "cancel_reason": credit["cancel_reason"],
        "is_cancelled": credit["is_cancelled"].astype("int8"),
        # internal: consumed by fulfillment, shipping, billing, collections
        "_expected_delivery_date": timing["expected_delivery_date"],
        "_expected_invoice_date": timing["expected_invoice_date"],
        "_expected_cash_date": timing["expected_cash_date"],
        "_transit_days": timing["transit_days"],
        "_billing_lag_days": timing["billing_lag_days"],
        "_days_to_pay": timing["days_to_pay"],
    })

    # ---- non-credit cancellations -------------------------------------------
    # Ordinary churn: customer changes their mind before anything ships.
    free = (orders["is_cancelled"] == 0).to_numpy()
    plain = free & (rng.random(n) < 0.012)
    cancel_at = np.array([d + dt.timedelta(days=int(k))
                          for d, k in zip(order_date, rng.integers(1, 25, n))])
    plain &= cancel_at <= s.timeline.as_of_date
    orders.loc[plain, "is_cancelled"] = 1
    orders.loc[plain, "cancelled_date"] = cancel_at[plain]
    orders.loc[plain, "cancel_reason"] = rng.choice(
        ["Customer Request", "Duplicate Order", "Superseded by New Order",
         "Lead Time Unacceptable", "Pricing Not Approved"],
        size=int(plain.sum()), p=[0.44, 0.12, 0.16, 0.18, 0.10])

    # ---- line-level shape ----------------------------------------------------
    lines = lines.merge(
        orders[["order_id", "order_date", "promised_delivery_date",
                "requested_delivery_date", "customer_id", "is_cancelled",
                "credit_status", "region", "business_unit"]],
        on="order_id", how="left")
    lines["quantity_ordered"] = lines["quantity"]
    lines = lines.drop(columns=["quantity"])

    # ---- close the loop back to the quote ------------------------------------
    quotes = quotes.copy()
    conv = pd.Series(0, index=quotes.index)
    qid_to_oid = pd.Series(orders["order_id"].to_numpy(),
                           index=orders["quote_id"].to_numpy())
    qid_to_oid = qid_to_oid[qid_to_oid.index > 0]
    mapped = qid_to_oid.reindex(quotes["quote_id"]).fillna(0).to_numpy()
    quotes["converted_order_id"] = mapped.astype("int32")
    o_date = pd.Series(orders["order_date"].to_numpy(),
                       index=orders["order_id"].to_numpy())
    got = quotes["converted_order_id"] > 0
    days = np.zeros(len(quotes), dtype="int32")
    if got.any():
        od = pd.to_datetime(o_date.reindex(quotes.loc[got, "converted_order_id"]).to_numpy())
        qd = pd.to_datetime(quotes.loc[got, "quote_date"]).to_numpy()
        days[got.to_numpy()] = ((od.to_numpy() - qd) / _DAY).astype("int32")
    quotes["days_to_convert"] = days
    # A won quote whose order fell outside the window is still won, but it has
    # no order - so it must not claim one.
    quotes.loc[(quotes["is_won"] == 1) & (quotes["converted_order_id"] == 0),
               "quote_status"] = "Won - Not Yet Booked"

    return orders, lines, quotes


def _draw_lifecycle(s: Scenario, ep: EventPlan, head: pd.DataFrame,
                    lines: pd.DataFrame, prod: pd.DataFrame, terms: pd.DataFrame,
                    cust: pd.DataFrame, order_date: np.ndarray,
                    rng: np.random.Generator) -> dict:
    """Every downstream date the order will need, decided at booking time."""
    n = len(head)
    f, sh = s.fulfillment, s.shipping

    alloc = rng.integers(f["allocation_days"][0], f["allocation_days"][1] + 1, n)
    pick = rng.integers(f["pick_pack_days"][0], f["pick_pack_days"][1] + 1, n)

    # Made-to-order lines set the pace of the whole order.
    mto = prod.set_index("product_id")["is_made_to_order"]
    lead = prod.set_index("product_id")["lead_time_days"]
    per_order = lines.assign(
        _mto=mto.reindex(lines["product_id"]).to_numpy(),
        _lead=lead.reindex(lines["product_id"]).to_numpy()).groupby("order_id").agg(
        max_lead=("_lead", "max"), any_mto=("_mto", "max"))
    max_lead = per_order["max_lead"].reindex(np.arange(1, n + 1)).fillna(5).to_numpy()

    tr = sh["transit_days_by_region"]
    transit = np.array([rng.integers(*tr.get(r, [3, 7])) for r in head["region"]])

    od = pd.to_datetime(order_date).to_numpy().astype("datetime64[D]")
    planned_ship = od + (alloc + pick).astype("timedelta64[D]")
    # Made-to-order product cannot ship before it is made.
    planned_ship = np.maximum(planned_ship, od + max_lead.astype("timedelta64[D]"))
    expected_delivery = planned_ship + transit.astype("timedelta64[D]")

    # The customer asks for a date; the business promises one it can hit. The
    # gap between requested and promised is a real fulfilment KPI.
    requested = od + rng.integers(4, 45, n).astype("timedelta64[D]")
    # The promise carries a safety buffer, as any real promise does. Without it
    # the promised date is the theoretical best case and on-time-to-promise
    # collapses to something no distributor would still be trading with.
    promised = np.maximum(expected_delivery + rng.integers(2, 10, n).astype("timedelta64[D]"),
                          od + np.timedelta64(4, "D"))

    # Billing lag. Event 5 stretches one business unit; Event 15 gives three of
    # them a fat tail, which is where "delivered not invoiced" comes from.
    blo, bhi = s.billing["base_lag_days"]
    billing_lag = rng.uniform(blo, bhi, n)
    bu = head["business_unit"].to_numpy()

    ev = s.event("invoice_lag")
    if ev is not None:
        hit = (bu == ev["business_unit"]) & ep.in_window("invoice_lag", order_date)
        target = ep.blend("invoice_lag", order_date,
                          float(ev["lag_days_from"]), float(ev["lag_days_to"]))
        billing_lag = np.where(hit, target + rng.normal(0, 1.2, n), billing_lag)

    ev = s.event("revenue_trapped")
    if ev is not None:
        hit = (np.isin(bu, list(ev["business_units"]))
               & ep.in_window("revenue_trapped", order_date)
               & (rng.random(n) < float(ev["lag_tail_share"])))
        tlo, thi = ev["lag_tail_days"]
        billing_lag = np.where(hit, rng.uniform(tlo, thi, n), billing_lag)

    billing_lag = np.maximum(0.0, billing_lag)
    expected_invoice = expected_delivery + np.round(billing_lag).astype("timedelta64[D]")

    # Days to pay: the terms, then the customer's own behaviour, then Event 6.
    # Note this is days from INVOICE, not from order - which is what payment
    # terms actually mean, and why a billing delay pushes cash out one-for-one.
    tmap = terms.set_index("payment_terms_code")["due_days"]
    due_days = np.maximum(0.0, tmap.reindex(head["payment_terms_code"])
                          .fillna(30).to_numpy().astype(float))
    behaviour = cust.set_index("customer_id")["_days_to_pay_mult"]
    mult = behaviour.reindex(head["customer_id"]).fillna(1.1).to_numpy()
    noise = np.exp(rng.normal(0.0, float(s.collections["days_to_pay_sigma"]), n))
    # Capped: the lognormal tail on extended terms otherwise reaches 500 days,
    # which is not a slow payer, it is a bad debt, and it belongs in the
    # write-off population rather than in the days-to-pay distribution.
    days_to_pay = np.clip(due_days * mult * noise, 0.0, 240.0)
    # Immediate terms still take a couple of days to clear the bank.
    days_to_pay = np.where(due_days <= 0, rng.uniform(0, 4, n), days_to_pay)

    ev = s.event("customer_payment_slowdown")
    if ev is not None and ep.slow_payer_id:
        hit = ((head["customer_id"].to_numpy() == ep.slow_payer_id)
               & ep.in_window("customer_payment_slowdown", order_date))
        target = ep.blend("customer_payment_slowdown", order_date,
                          float(ev["days_to_pay_from"]), float(ev["days_to_pay_to"]))
        days_to_pay = np.where(hit, np.maximum(1.0, target + rng.normal(0, 4.0, n)),
                               days_to_pay)

    return {
        "requested_delivery_date": requested,
        "promised_delivery_date": promised,
        "planned_ship_date": planned_ship,
        "expected_delivery_date": expected_delivery,
        "expected_invoice_date": expected_invoice,
        "expected_cash_date": expected_invoice + np.round(days_to_pay).astype("timedelta64[D]"),
        "transit_days": transit.astype("int16"),
        "billing_lag_days": np.round(billing_lag).astype("int16"),
        "days_to_pay": np.round(days_to_pay).astype("int16"),
    }


def _run_credit_ledger(s: Scenario, ep: EventPlan, head: pd.DataFrame,
                       total_amount: np.ndarray, order_date: np.ndarray,
                       expected_cash: np.ndarray, cust: pd.DataFrame,
                       rng: np.random.Generator) -> dict:
    """Walk each customer's orders in date order against a running exposure.

    Exposure is open commitment: booked value that has not yet turned into cash.
    An order is held when booking it would breach the limit, and released on the
    day enough earlier cash has landed to make room - a date this ledger already
    knows, because every order's expected cash date was drawn at booking.
    """
    n = len(head)
    tl = s.timeline
    g = float(s.demand["annual_growth"])
    cancel_after = int(s.credit["cancel_after_hold_days"])
    release_prob = float(s.credit["hold_release_prob"])
    rel_lo, rel_hi = s.credit["hold_release_days"]

    limits = cust.set_index("customer_id")["credit_limit_usd"]
    base_limit = limits.reindex(head["customer_id"]).fillna(50_000.0).to_numpy()

    od = pd.to_datetime(order_date).to_numpy().astype("datetime64[D]")
    ecd = pd.to_datetime(expected_cash).to_numpy().astype("datetime64[D]")
    as_of = np.datetime64(tl.as_of_date, "D")

    # The limit grows with the business, so utilisation is roughly flat through
    # history instead of drifting down as volume outgrows a static number.
    years_back = (od - as_of) / np.timedelta64(365, "D")
    limit_at = base_limit * (1.0 + g) ** years_back

    # Event 9: limits capped for a group of customers from the freeze month on.
    # A credit manager can wave through a one-off breach. They cannot wave
    # through a limit that is structurally below the customer's run rate, which
    # is what Event 9 creates - so overrides get refused and the queue builds.
    # That difference is the whole reason the held value is visible at all.
    override_prob = np.full(n, release_prob)
    ev = s.event("credit_hold")
    if ev is not None and len(ep.credit_hold_customers):
        frozen = np.isin(head["customer_id"].to_numpy(), ep.credit_hold_customers)
        in_win = ep.in_window("credit_hold", order_date)
        cap = base_limit * float(ev.get("frozen_limit_factor", 0.6))
        limit_at = np.where(frozen & in_win, np.minimum(limit_at, cap), limit_at)
        override_prob = np.where(frozen & in_win,
                                 float(ev.get("override_prob", 0.30)), override_prob)

    status = np.full(n, "Approved", dtype=object)
    hold_date = np.full(n, None, dtype=object)
    release_date = np.full(n, None, dtype=object)
    cancelled_date = np.full(n, None, dtype=object)
    cancel_reason = np.full(n, "Not Cancelled", dtype=object)
    is_cancelled = np.zeros(n, dtype=bool)
    exposure_before = np.zeros(n, dtype=float)
    start_delay = np.zeros(n, dtype="int64")

    order_of_customer: dict[int, list[int]] = {}
    for i, c in enumerate(head["customer_id"].to_numpy()):
        order_of_customer.setdefault(int(c), []).append(i)

    for cid, idxs in order_of_customer.items():
        # Pending commitments as (cash_date, amount), kept sorted by cash date.
        pend_date: list[np.datetime64] = []
        pend_amt: list[float] = []
        running = 0.0
        head_ptr = 0
        for i in idxs:
            d, amt, lim = od[i], float(total_amount[i]), float(limit_at[i])
            # Expire anything that has turned to cash by now.
            while head_ptr < len(pend_date) and pend_date[head_ptr] <= d:
                running -= pend_amt[head_ptr]
                head_ptr += 1
            exposure_before[i] = max(running, 0.0)

            if running + amt <= lim:
                _push(pend_date, pend_amt, ecd[i], amt, head_ptr)
                running += amt
                continue

            # Over the limit. Two ways off hold: a credit manager overrides it,
            # or enough earlier cash lands to make genuine room. Most holds go
            # the first way within a few weeks - a queue that only ever cleared
            # itself mechanically would cancel far more orders than any real
            # business tolerates.
            status[i] = "Credit Hold"
            hold_date[i] = d.astype("datetime64[D]").astype(dt.date)
            room = running
            rel = None
            for j in range(head_ptr, len(pend_date)):
                room -= pend_amt[j]
                if room + amt <= lim:
                    rel = pend_date[j]
                    break
            if rng.random() < override_prob[i]:
                override = d + np.timedelta64(
                    int(rng.integers(rel_lo, rel_hi + 1)), "D")
                rel = override if rel is None else min(rel, override)
            if rel is not None and rel > as_of:
                # Released, but not until after the as-of date: still on hold
                # today, which is exactly the number the demo quotes.
                continue
            if rel is None or (rel - d) / _DAY > cancel_after:
                # No room inside the cancellation window. If the window closes
                # before as-of the order dies; otherwise it is still sitting on
                # hold today, which is exactly the number the demo quotes.
                deadline = d + np.timedelta64(cancel_after, "D")
                if deadline <= as_of:
                    is_cancelled[i] = True
                    cancelled_date[i] = deadline.astype("datetime64[D]").astype(dt.date)
                    cancel_reason[i] = "Credit Hold Expired"
                    status[i] = "Cancelled - Credit"
                continue

            status[i] = "Released"
            release_date[i] = rel.astype("datetime64[D]").astype(dt.date)
            start_delay[i] = int((rel - d) / _DAY)
            shifted = ecd[i] + np.timedelta64(int(start_delay[i]), "D")
            _push(pend_date, pend_amt, shifted, amt, head_ptr)
            running += amt

    return {"credit_status": status, "hold_date": hold_date,
            "release_date": release_date, "cancelled_date": cancelled_date,
            "cancel_reason": cancel_reason, "is_cancelled": is_cancelled,
            "exposure_before": exposure_before, "limit_at_order": limit_at,
            "start_delay_days": start_delay}


def _push(dates: list, amts: list, when, amount: float, floor: int) -> None:
    """Insert (when, amount) keeping the pending list sorted by cash date."""
    lo, hi = floor, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] < when:
            lo = mid + 1
        else:
            hi = mid
    dates.insert(lo, when)
    amts.insert(lo, amount)
