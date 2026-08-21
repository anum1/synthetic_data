#!/usr/bin/env python3
"""Post-generation checks.

Four families:

  INTEGRITY  keys resolve, quantities reconcile across the chain, no money is
             negative where it cannot be.
  LEDGER     the AR ledger is internally consistent - open balance equals total
             less cash less credits less discount taken, invoice status agrees
             with the balance, and the monthly ageing snapshot sums to the same
             number as the ledger at the same date. To the cent.
  WATERFALL  the booking-cohort waterfall closes. Booked, less every stage loss,
             equals collected. This is the number the whole demo hangs off; if
             it does not close, nothing else matters.
  NARRATIVE  every enabled event is VISIBLE in the aggregates, at the magnitude
             the config claims, measured in the window where the ramp has
             actually arrived.

The narrative checks are the ones that earn their keep. Random noise routinely
swamps a planted signal, and the usual way to discover that is live, in front of
an audience, rather than here.

  python3 src/validate.py --tier small
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from o2cconfig import PROJECT_ROOT, load_scenario


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, group, name, ok, detail=""):
        self.rows.append((group, name, bool(ok), detail))

    def between(self, group, name, value, lo, hi, fmt="{:.1%}"):
        ok = value is not None and not pd.isna(value) and lo <= value <= hi
        shown = "n/a" if value is None or pd.isna(value) else fmt.format(value)
        self.check(group, name, ok, f"{shown}  (want {fmt.format(lo)}..{fmt.format(hi)})")

    def at_least(self, group, name, value, floor, fmt="{:.2f}"):
        ok = value is not None and not pd.isna(value) and value >= floor
        shown = "n/a" if value is None or pd.isna(value) else fmt.format(value)
        self.check(group, name, ok, f"{shown}  (want >= {fmt.format(floor)})")

    def at_most(self, group, name, value, cap, fmt="{:.2f}"):
        ok = value is not None and not pd.isna(value) and value <= cap
        shown = "n/a" if value is None or pd.isna(value) else fmt.format(value)
        self.check(group, name, ok, f"{shown}  (want <= {fmt.format(cap)})")

    @property
    def failed(self):
        return [r for r in self.rows if not r[2]]

    def render(self):
        out, cur = [], None
        for g, n, ok, d in self.rows:
            if g != cur:
                out.append(f"\n{g}")
                cur = g
            out.append(f"  [{'PASS' if ok else 'FAIL'}] {n:<52s} {d}")
        out.append(f"\n{len(self.rows) - len(self.failed)}/{len(self.rows)} checks passed")
        return "\n".join(out)


def load(d: Path):
    return {p.stem: pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))}


def _d(df, col):
    return pd.to_datetime(df[col])


def run(s, t, r: Report):
    as_of = pd.Timestamp(s.timeline.as_of_date)
    ttm_start = pd.Timestamp(s.timeline.ttm_start)
    prior_start = pd.Timestamp(s.timeline.prior_ttm_start)
    recent = pd.Timestamp(s.timeline.offset_month(-5))     # last 6 months
    late = pd.Timestamp(s.timeline.offset_month(-2))       # last 3 months

    cust, prod = t["dim_customer"], t["dim_product"]
    orders, ol = t["fact_order"], t["fact_order_line"]
    quotes = t["fact_quote"]
    ship, shl = t["fact_shipment"], t["fact_shipment_line"]
    inv, il = t["fact_invoice"], t["fact_invoice_line"]
    alloc, memos = t["fact_payment_allocation"], t.get("fact_credit_memo", pd.DataFrame())
    cycle, exc = t["fact_o2c_cycle"], t["fact_o2c_exception"]
    aging = t["fact_ar_aging_snapshot"]
    ff = t["fact_fulfillment"]

    # ------------------------------------------------------ INTEGRITY: keys
    g = "INTEGRITY - referential"
    r.check(g, "order -> customer resolves",
            orders["customer_id"].isin(cust["customer_id"]).all())
    r.check(g, "order -> quote resolves (0 = Direct Order)",
            orders.loc[orders["quote_id"] > 0, "quote_id"].isin(quotes["quote_id"]).all())
    r.check(g, "order_line -> order resolves",
            ol["order_id"].isin(orders["order_id"]).all())
    r.check(g, "order_line -> product resolves",
            ol["product_id"].isin(prod["product_id"]).all())
    r.check(g, "shipment -> order resolves",
            ship["order_id"].isin(orders["order_id"]).all())
    r.check(g, "shipment_line -> order_line resolves",
            shl["order_line_id"].isin(ol["order_line_id"]).all())
    r.check(g, "shipment_line -> shipment resolves",
            shl["shipment_id"].isin(ship["shipment_id"]).all())
    r.check(g, "invoice_line -> order_line resolves",
            il["order_line_id"].isin(ol["order_line_id"]).all())
    r.check(g, "invoice_line -> shipment_line resolves",
            il["shipment_line_id"].isin(shl["shipment_line_id"]).all())
    r.check(g, "allocation -> invoice resolves",
            alloc["invoice_id"].isin(inv["invoice_id"]).all())
    r.check(g, "allocation -> payment resolves",
            alloc["payment_id"].isin(t["fact_payment"]["payment_id"]).all())
    r.check(g, "no NULL foreign keys on fact_order",
            orders[["customer_id", "site_id", "sales_rep_id", "quote_id"]].notna().all().all())
    r.check(g, "every customer has a bill-to site",
            t["dim_customer_site"].groupby("customer_id")["is_bill_to"].max().eq(1).all())
    r.check(g, "exception -> customer resolves",
            exc["customer_id"].isin(cust["customer_id"]).all())

    # ------------------------------------------------------ INTEGRITY: amounts
    g = "INTEGRITY - quantities and amounts"
    q_ship = shl.groupby("order_line_id")["quantity_shipped"].sum()
    joined = ol.set_index("order_line_id")
    over = (q_ship.reindex(joined.index).fillna(0)
            > joined["quantity_ordered"] + 0.001)
    r.check(g, "shipped quantity never exceeds ordered", not bool(over.any()),
            f"{int(over.sum())} lines over")
    # Duplicate invoices bill the same shipment lines twice by design, so they
    # are excluded here and checked separately - otherwise the planted defect
    # would read as a generator bug.
    live_inv = set(inv.loc[inv["is_duplicate"] == 0, "invoice_id"])
    il_live = il[il["invoice_id"].isin(live_inv)]
    q_inv = il_live.groupby("shipment_line_id")["quantity_invoiced"].sum()
    sl_idx = shl.set_index("shipment_line_id")
    over_i = (q_inv.reindex(sl_idx.index).fillna(0)
              > sl_idx["quantity_shipped"] + 0.001)
    r.check(g, "invoiced quantity never exceeds shipped (ex duplicates)",
            not bool(over_i.any()), f"{int(over_i.sum())} lines over")
    q_all = il.groupby("shipment_line_id")["quantity_invoiced"].sum()
    r.check(g, "duplicate invoices do double-bill their lines",
            bool((q_all.reindex(sl_idx.index).fillna(0)
                  > sl_idx["quantity_shipped"] + 0.001).any()))
    for col in ("net_order_amount_usd", "total_order_amount_usd", "freight_amount_usd"):
        r.check(g, f"no negative {col}", (orders[col] >= -0.01).all(),
                f"min {orders[col].min():,.2f}")
    r.check(g, "invoice total = net + tax + freight",
            (inv["total_amount_usd"]
             - (inv["net_amount_usd"] + inv["tax_amount_usd"]
                + inv["freight_amount_usd"])).abs().max() < 0.02)
    r.check(g, "order header = sum of its lines",
            (orders.set_index("order_id")["net_order_amount_usd"]
             - ol.groupby("order_id")["extended_amount_usd"].sum()).abs().max() < 0.05)
    r.check(g, "cancelled orders have a cancellation date",
            orders.loc[orders["is_cancelled"] == 1, "cancelled_date"].notna().all())

    # ------------------------------------------------------ LEDGER
    g = "LEDGER - AR reconciliation"
    paid = alloc.groupby("invoice_id")["allocated_amount_usd"].sum()
    cred = (memos.groupby("invoice_id")["memo_amount_usd"].sum()
            if len(memos) else pd.Series(dtype=float))
    expect = (inv["total_amount_usd"].to_numpy()
              - paid.reindex(inv["invoice_id"]).fillna(0).to_numpy()
              - cred.reindex(inv["invoice_id"]).fillna(0).to_numpy()
              - inv["early_discount_taken_usd"].to_numpy())
    expect = np.where(np.abs(expect) < 0.02, 0.0, expect)
    r.check(g, "open = total - cash - credits - discount taken",
            np.abs(expect - inv["open_amount_usd"].to_numpy()).max() < 0.02,
            f"max delta ${np.abs(expect - inv['open_amount_usd'].to_numpy()).max():.4f}")
    r.check(g, "no invoice is overpaid",
            (inv["open_amount_usd"] >= -0.02).all(),
            f"min ${inv['open_amount_usd'].min():,.2f}")
    r.check(g, "status Paid implies zero balance",
            (inv.loc[inv["invoice_status"] == "Paid", "open_amount_usd"].abs() < 0.02).all())
    r.check(g, "status Overdue implies an open balance past due",
            (inv.loc[inv["invoice_status"] == "Overdue", "open_amount_usd"] > 0.01).all())
    r.check(g, "written-off invoices are out of open AR",
            int(((inv["is_written_off"] == 1) & (inv["is_open"] == 1)).sum()) == 0)

    open_ar = inv.loc[inv["is_open"] == 1, "open_amount_usd"].sum()
    last_snap = aging["snapshot_date"].max()
    snap_ar = aging.loc[aging["snapshot_date"] == last_snap, "open_amount_usd"].sum()
    r.check(g, "ageing snapshot at as-of = ledger open AR",
            abs(snap_ar - open_ar) < 0.05,
            f"${snap_ar:,.2f} vs ${open_ar:,.2f}")
    bucket_sum = aging.loc[aging["snapshot_date"] == last_snap].groupby(
        "aging_bucket")["open_amount_usd"].sum().sum()
    r.check(g, "ageing buckets sum to open AR", abs(bucket_sum - open_ar) < 0.05)
    r.check(g, "every open invoice appears in the as-of snapshot",
            int(inv.loc[inv["is_open"] == 1, "invoice_id"].isin(
                aging.loc[aging["snapshot_date"] == last_snap, "invoice_id"]).sum())
            == int((inv["is_open"] == 1).sum()))

    # ------------------------------------------------------ WATERFALL
    g = "WATERFALL - booking cohort closes"
    c = cycle[_d(cycle, "order_date") >= ttm_start]
    booked = c["booked_net_usd"].sum()
    resid = (booked - c["cancelled_net_usd"].sum() - c["not_yet_shipped_usd"].sum()
             - c["in_transit_usd"].sum() - c["delivered_not_invoiced_usd"].sum()
             - c["credited_net_usd"].sum() - c["open_ar_net_usd"].sum()
             - c["collected_net_usd"].sum())
    r.check(g, "booked - every stage loss = collected", abs(resid) < 1.0,
            f"residual ${resid:,.2f} on ${booked / 1e6:,.1f}M booked")
    for a, b in [("net_booked_usd", "shipped_net_usd"),
                 ("shipped_net_usd", "delivered_net_usd"),
                 ("delivered_net_usd", "invoiced_net_usd")]:
        r.check(g, f"{b} never exceeds {a}",
                (cycle[b] <= cycle[a] + 0.01).all(),
                f"{int((cycle[b] > cycle[a] + 0.01).sum())} orders inverted")
    r.check(g, "no negative stage values",
            (cycle[["not_yet_shipped_usd", "in_transit_usd",
                    "delivered_not_invoiced_usd"]] >= -0.01).all().all())
    mono = cycle[cycle["first_invoice_date"].notna() & cycle["first_ship_date"].notna()]
    r.check(g, "milestone dates are monotonic (ship <= invoice)",
            (_d(mono, "first_ship_date") <= _d(mono, "first_invoice_date")).all())
    cohort_ar = c["open_ar_net_usd"].sum()
    r.check(g, "cohort AR does not exceed company open AR", cohort_ar <= open_ar + 1.0,
            f"${cohort_ar / 1e6:,.2f}M vs ${open_ar / 1e6:,.2f}M")

    # ------------------------------------------------------ HEADLINE
    g = "HEADLINE"
    h = s.headline
    prior = cycle[(_d(cycle, "order_date") >= prior_start)
                  & (_d(cycle, "order_date") < ttm_start)]
    r.between(g, "TTM bookings", booked, *s.money_range(h["bookings_ttm_usd"]),
              fmt="${:,.0f}")
    growth = booked / max(prior["booked_net_usd"].sum(), 1) - 1
    r.between(g, "bookings growth YoY", growth, *h["bookings_growth"])
    ttm_inv = inv[_d(inv, "invoice_date") >= ttm_start]
    dso = open_ar / max(ttm_inv["total_amount_usd"].sum(), 1) * 365
    r.between(g, "DSO (days)", dso, *h["dso_days"], fmt="{:.0f}")
    overdue = inv.loc[inv["is_overdue"] == 1, "open_amount_usd"].sum() / max(open_ar, 1)
    r.between(g, "overdue share of AR", overdue, *h["overdue_share_of_ar"])
    r.between(g, "perfect order rate", c["is_perfect_order"].mean(),
              *h["perfect_order_rate"])
    r.at_least(g, "exception centre is populated", len(exc), s.money(800),
               fmt="{:.0f}")

    # ------------------------------------------------------ NARRATIVE
    _narrative(s, t, r, recent, late, ttm_start)


def _narrative(s, t, r: Report, recent, late, ttm_start):
    orders, ol = t["fact_order"], t["fact_order_line"]
    quotes, ql = t["fact_quote"], t["fact_quote_line"]
    ship = t["fact_shipment"]
    inv, il = t["fact_invoice"], t["fact_invoice_line"]
    cycle = t["fact_o2c_cycle"]
    ff = t["fact_fulfillment"]
    cust, prod = t["dim_customer"], t["dim_product"]
    wh = t["dim_warehouse"]

    g = "NARRATIVE - Event 1 quote conversion collapse"
    ev = s.event("quote_conversion_collapse")
    if ev:
        dec = quotes[(quotes["is_open"] == 0) & (_d(quotes, "quote_date") >= recent)]
        hit = dec[dec["region"] == ev["region"]]["is_won"].mean()
        rest = dec[dec["region"] != ev["region"]]["is_won"].mean()
        r.between(g, f"{ev['region']} conversion, last 6 months", hit,
                  *ev["assert_conversion_range"])
        r.at_least(g, "gap vs the rest of the business", rest / max(hit, 1e-9), 1.4,
                   fmt="{:.2f}x")

    g = "NARRATIVE - Event 2 discount explosion"
    ev = s.event("discount_explosion")
    if ev:
        lr = ql.merge(quotes[["quote_id", "sales_rep_id", "quote_date"]], on="quote_id")
        lr = lr[_d(lr, "quote_date") >= recent]
        by_rep = lr.groupby("sales_rep_id")["discount_pct"].mean()
        top = by_rep.nlargest(max(1, int(round(ev["rep_share"] * len(by_rep)))))
        peers = by_rep.drop(top.index).median()
        r.at_least(g, "worst reps vs peer median discount",
                   top.mean() / max(peers, 1e-9), float(ev["assert_min_lift_vs_peers"]),
                   fmt="{:.2f}x")

    g = "NARRATIVE - Event 3 warehouse bottleneck"
    ev = s.event("warehouse_bottleneck")
    if ev:
        code = ev["warehouse_code"]
        wid = wh.loc[wh["warehouse_code"] == code, "warehouse_id"]
        wid = int(wid.iloc[0]) if len(wid) else -1
        live = ol[(ol["is_cancelled"] == 0) & (ol["credit_status"] != "Credit Hold")
                  & (_d(ol, "order_date") >= recent)]
        hit = live[live["warehouse_id"] == wid]
        rate = hit["quantity_backordered"].sum() / max(hit["quantity_ordered"].sum(), 1)
        r.between(g, f"{code} backorder rate, last 6 months", rate,
                  *ev["assert_backorder_rate"])
        f_recent = ff[_d(ff, "fulfillment_created_date") >= late]
        delay = f_recent[f_recent["warehouse_id"] == wid]["ship_delay_days"].mean()
        r.at_least(g, f"{code} ship delay, last 3 months", delay,
                   float(ev["assert_min_ship_delay_days"]), fmt="{:.2f}d")
        others = f_recent[f_recent["warehouse_id"] != wid]["ship_delay_days"].mean()
        r.at_most(g, "the rest of the network is not queueing", others, 0.6, fmt="{:.2f}d")

    g = "NARRATIVE - Event 4 carrier deterioration"
    ev = s.event("carrier_deterioration")
    if ev:
        d = ship[(ship["is_delivered"] == 1) & (_d(ship, "ship_date") >= late)]
        hit = d[d["carrier_name"] == ev["carrier_name"]]["is_on_time_carrier"].mean()
        rest = d[d["carrier_name"] != ev["carrier_name"]]["is_on_time_carrier"].mean()
        r.between(g, f"{ev['carrier_name']} on-time, last 3 months", hit,
                  *ev["assert_on_time_range"])
        r.at_least(g, "network on-time is unaffected", rest, 0.88)

    g = "NARRATIVE - Event 5 invoice lag"
    ev = s.event("invoice_lag")
    if ev:
        i = inv[_d(inv, "invoice_date") >= recent]
        hit = i[i["business_unit"] == ev["business_unit"]]["days_delivery_to_invoice"].mean()
        r.at_least(g, f"{ev['business_unit']} delivery-to-invoice days", hit,
                   float(ev["assert_min_lag_days"]), fmt="{:.1f}d")

    g = "NARRATIVE - Event 6 customer payment slowdown"
    ev = s.event("customer_payment_slowdown")
    if ev:
        ranked = cycle.groupby("customer_id")["booked_net_usd"].sum().nlargest(50)
        # The account is identified the way the demo identifies it - by size -
        # rather than by an id the validator was told, so this check fails if the
        # event has drifted onto a different customer.
        paid = inv[(inv["days_to_pay_actual"] >= 0)
                   & (_d(inv, "invoice_date") >= recent)]
        by_cust = paid.groupby("customer_id")["days_to_pay_actual"].mean()
        big = by_cust.reindex(ranked.index).dropna()
        r.at_least(g, "slowest large account, days to pay", big.max(),
                   float(ev["assert_min_days_to_pay"]), fmt="{:.0f}d")
        r.at_least(g, "slowest vs median large account",
                   big.max() / max(big.median(), 1e-9), 1.5, fmt="{:.2f}x")

    g = "NARRATIVE - Event 7 pricing leakage"
    ev = s.event("pricing_leakage")
    if ev:
        var = il["underbilled_amount_usd"].sum()
        r.at_least(g, "total underbilling", var,
                   s.money(ev["assert_min_variance_usd"]), fmt="${:,.0f}")
        by_cust = il.merge(inv[["invoice_id", "customer_id"]], on="invoice_id")
        top = by_cust.groupby("customer_id")["underbilled_amount_usd"].sum().nlargest(3).sum()
        r.at_least(g, "top 3 accounts' share of the leakage",
                   top / max(var, 1e-9), 0.15)

    g = "NARRATIVE - Event 8 partial shipments"
    ev = s.event("partial_shipment_problem")
    if ev:
        fam = prod.set_index("product_id")["product_family"]
        hit_orders = set(ol.loc[fam.reindex(ol["product_id"]).to_numpy()
                                == ev["product_family"], "order_id"])
        s_recent = ship[_d(ship, "ship_date") >= recent]
        per_order = s_recent.groupby("order_id").size()
        a = (per_order[per_order.index.isin(hit_orders)] > 1).mean()
        b = (per_order[~per_order.index.isin(hit_orders)] > 1).mean()
        r.at_least(g, f"{ev['product_family']} split rate vs the rest",
                   a / max(b, 1e-9), float(ev["assert_min_split_lift"]), fmt="{:.2f}x")
        fo = s_recent.groupby("order_id")["freight_cost_usd"].sum()
        ov = orders.set_index("order_id")["net_order_amount_usd"].reindex(fo.index)
        m = fo.index.isin(hit_orders)
        pa = fo[m].sum() / max(ov[m].sum(), 1)
        pb = fo[~m].sum() / max(ov[~m].sum(), 1)
        r.at_least(g, "freight as a share of revenue vs the rest", pa / max(pb, 1e-9),
                   float(ev["assert_min_freight_lift"]), fmt="{:.2f}x")

    g = "NARRATIVE - Event 9 credit holds"
    ev = s.event("credit_hold")
    if ev:
        held = orders[(orders["credit_status"] == "Credit Hold")
                      & (orders["is_cancelled"] == 0)]
        r.between(g, "value on credit hold at as-of",
                  held["total_order_amount_usd"].sum(),
                  *s.money_range(ev["assert_held_value_usd"]), fmt="${:,.0f}")
        expo = t.get("fact_credit_exposure_snapshot")
        if expo is not None and len(expo):
            last = expo[expo["snapshot_date"] == expo["snapshot_date"].max()]
            r.at_least(g, "customers over their limit at as-of",
                       int(last["is_over_limit"].sum()), s.money(40), fmt="{:.0f}")

    g = "NARRATIVE - Event 10 dispute spike"
    ev = s.event("dispute_spike")
    disp = t.get("fact_dispute")
    if ev and disp is not None and len(disp):
        acct = cust.set_index("customer_id")["global_account_id"]
        d = disp.assign(acct=acct.reindex(disp["customer_id"]).to_numpy())
        d = d[_d(d, "dispute_date") >= recent]
        by_acct = d[d["acct"] > 0].groupby("acct")["dispute_amount_usd"].sum() / 6.0
        r.at_least(g, "worst global account, disputes per month",
                   by_acct.max() if len(by_acct) else 0,
                   s.money(ev["assert_min_monthly_usd"]), fmt="${:,.0f}")

    g = "NARRATIVE - Event 11 product shortage"
    ev = s.event("product_shortage")
    if ev:
        win_lo = pd.Timestamp(s.timeline.offset_month(int(ev["start_offset"])))
        win_hi = pd.Timestamp(s.timeline.offset_month(int(ev["end_offset"])))
        live = ol[(ol["is_cancelled"] == 0) & (_d(ol, "order_date") >= win_lo)
                  & (_d(ol, "order_date") <= win_hi)]
        by_p = live.groupby("product_id").agg(a=("quantity_allocated", "sum"),
                                              o=("quantity_ordered", "sum"))
        by_p = by_p[by_p["o"] > 50]
        worst = (by_p["a"] / by_p["o"]).nsmallest(max(1, s.scaled(ev["sku_share"], "products")))
        r.at_most(g, "worst SKUs' fill rate in the window", worst.mean(),
                  float(ev["assert_max_fill_rate"]))

    g = "NARRATIVE - Event 12 returns spike"
    ev = s.event("returns_spike")
    ret = t.get("fact_return")
    if ev and ret is not None and len(ret):
        cat = prod.set_index("product_id")["product_category"]
        lines = il.assign(c=cat.reindex(il["product_id"]).to_numpy())
        lines = lines.merge(inv[["invoice_id", "invoice_date"]], on="invoice_id")
        lines = lines[_d(lines, "invoice_date") >= recent]
        rr = ret[_d(ret, "return_date") >= recent]
        a = len(rr[rr["product_category"] == ev["product_category"]]) / max(
            len(lines[lines["c"] == ev["product_category"]]), 1)
        b = len(rr[rr["product_category"] != ev["product_category"]]) / max(
            len(lines[lines["c"] != ev["product_category"]]), 1)
        r.at_least(g, f"{ev['product_category']} return rate vs the rest",
                   a / max(b, 1e-9), float(ev["assert_min_lift"]), fmt="{:.2f}x")

    g = "NARRATIVE - Event 13 duplicate billing"
    ev = s.event("duplicate_billing")
    if ev:
        r.at_least(g, "duplicate invoice pairs", int((inv["is_duplicate"] == 1).sum()),
                   s.money(ev["assert_min_pairs"]), fmt="{:.0f}")
        d = inv[inv["is_duplicate"] == 1]
        r.check(g, "each duplicate points at its original",
                d["duplicate_of_invoice_id"].isin(inv["invoice_id"]).all())

    g = "NARRATIVE - Event 14 freight leakage"
    ev = s.event("freight_leakage")
    if ev:
        fo = ship.groupby("order_id")["freight_cost_usd"].sum()
        o = orders.set_index("order_id")
        v = o["net_order_amount_usd"].reindex(fo.index)
        d = _d(o.reindex(fo.index).reset_index(), "order_date")
        d.index = fo.index
        base_hi = pd.Timestamp(s.timeline.offset_month(-12))
        a = fo[d >= recent].sum() / max(v[d >= recent].sum(), 1)
        b = fo[d < base_hi].sum() / max(v[d < base_hi].sum(), 1)
        r.at_least(g, "freight as a share of revenue, now vs baseline",
                   a / max(b, 1e-9), float(ev["assert_min_freight_pct_lift"]),
                   fmt="{:.2f}x")
        er = ship[_d(ship, "ship_date") >= recent]["is_expedited"].mean()
        eb = ship[_d(ship, "ship_date") < base_hi]["is_expedited"].mean()
        r.at_least(g, "expedite rate, now vs baseline", er / max(eb, 1e-9), 1.8,
                   fmt="{:.2f}x")

    g = "NARRATIVE - Event 15 revenue trapped"
    ev = s.event("revenue_trapped")
    if ev:
        dni = cycle["delivered_not_invoiced_usd"].sum()
        r.between(g, "delivered but not invoiced at as-of", dni,
                  *s.money_range(ev["assert_unbilled_usd"]), fmt="${:,.0f}")
        top = cycle.groupby("business_unit")["delivered_not_invoiced_usd"].sum()
        r.check(g, "it concentrates in the named business units",
                top.idxmax() in list(ev["business_units"]),
                f"worst is {top.idxmax()}")

    g = "NARRATIVE - planted data-quality defects"
    if s.data_quality:
        r.at_least(g, "orders raised with no PO number",
                   int((orders["po_number"].fillna("") == "").sum()), s.money(200),
                   fmt="{:.0f}")
        r.at_least(g, "duplicate customer name variants",
                   int((cust["duplicate_of_customer_id"] > 0).sum()),
                   float(s.data_quality["customer_name_variants"]), fmt="{:.0f}")
        r.at_least(g, "unapplied cash on the books",
                   int((t["fact_payment"]["is_unapplied"] == 1).sum()), 5, fmt="{:.0f}")
        d = t.get("fact_dispute")
        if d is not None and len(d):
            r.check(g, "missing-PO orders become Missing PO disputes",
                    int((d["dispute_reason"] == "Missing PO").sum()) > 0,
                    f"{int((d['dispute_reason'] == 'Missing PO').sum())} disputes")
            r.check(g, "underbilled invoices become Pricing disputes",
                    int((d["dispute_reason"] == "Pricing Discrepancy").sum()) > 0,
                    f"{int((d['dispute_reason'] == 'Pricing Discrepancy').sum())} disputes")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    d = Path(args.data) if args.data else PROJECT_ROOT / "data" / args.tier
    if not d.exists():
        print(f"no data at {d}; run generate.py first")
        return 2
    t = load(d)
    r = Report()
    run(s, t, r)
    print(f"{s.company} O2C validator | tier={args.tier} | as-of {s.timeline.as_of_date}")
    print(r.render())
    return 1 if r.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
