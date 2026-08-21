#!/usr/bin/env python3
"""Vantage Industrial - Order-to-Cash Control Tower : dataset generator.

  python3 src/generate.py --tier small
  python3 src/generate.py --tier full --scenario config/my_scenario.yaml
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import customers as customers_mod
import derived as derived_mod
import dims as dims_mod
import fulfillment as fulfillment_mod
import products as products_mod
import receivables as receivables_mod
import shipping as shipping_mod
import snapshots as snapshots_mod
from billing import build_invoices
from dim_date import build_dim_date
from events import EventPlan
from o2cconfig import PROJECT_ROOT, load_scenario
from orders import build_orders
from pricing import build_contract_pricing
from quotes import build_quotes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--out", default=None, help="output directory (default data/<tier>)")
    ap.add_argument("--formats", default=None, help="comma list: parquet,csv")
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    t0 = time.time()

    # One independent random stream per subsystem, all derived from the single
    # configured seed. Sharing one generator means changing a shipping knob
    # reshuffles every draw downstream of it, so tuning one number moves five
    # unrelated numbers and the dataset never converges.
    def stream(tag: int) -> np.random.Generator:
        return np.random.default_rng([s.seed, tag])

    print(f"{s.company} O2C generator | scenario={s.cfg['meta']['scenario_name']} "
          f"tier={args.tier}")
    print(f"  history {s.timeline.start_date} -> as-of {s.timeline.as_of_date} "
          f"({len(s.timeline.month_starts())} months)")

    t: dict[str, pd.DataFrame] = {}

    print("  building dimensions...")
    t["dim_date"] = build_dim_date(s.timeline.start_date, s.timeline.end_date,
                                   int(s.calendar["fiscal_year_start_month"]))
    cust = customers_mod.build_dim_customer(s, stream(2))
    prod = products_mod.build_dim_product(s, stream(3))
    reps = dims_mod.build_dim_sales_rep(s, stream(7))
    wh = dims_mod.build_dim_warehouse(s, stream(5))
    carriers = dims_mod.build_dim_carrier(s, stream(6))
    terms = dims_mod.build_dim_payment_terms()

    # Events are resolved to concrete targets once, before anything is drawn, so
    # every stage downstream agrees on which rep, which warehouse and which
    # accounts the stories land on.
    ep = EventPlan(s, cust, prod, reps, wh, stream(9))
    cust = customers_mod.pin_event_baselines(s, cust, ep)
    cust = customers_mod.plant_name_variants(s, cust, stream(2))
    sites = customers_mod.build_dim_customer_site(s, cust, stream(4))
    contracts = build_contract_pricing(s, cust, prod, stream(8))

    t["dim_customer"] = cust
    t["dim_customer_site"] = sites
    t["dim_product"] = prod
    t["dim_sales_rep"] = reps
    t["dim_warehouse"] = wh
    t["dim_carrier"] = carriers
    t["dim_payment_terms"] = terms
    t["dim_currency"] = dims_mod.build_dim_currency(s)
    t["dim_exchange_rate"] = dims_mod.build_dim_exchange_rate(s)
    t["contract_pricing"] = contracts
    print(f"    customers={len(cust):,} sites={len(sites):,} products={len(prod):,} "
          f"contracts={len(contracts):,}")

    print("  quoting...")
    quotes, quote_lines, quote_doc = build_quotes(s, cust, sites, prod, reps,
                                                  contracts, ep, stream(10))
    print(f"    quotes={len(quotes):,} lines={len(quote_lines):,} "
          f"win_rate={quotes.loc[quotes['is_open'] == 0, 'is_won'].mean():.1%}")

    print("  booking orders and running the credit ledger...")
    orders, order_lines, quotes = build_orders(
        s, quotes, quote_lines, quote_doc, cust, sites, prod, reps, contracts,
        wh, terms, ep, stream(11))
    print(f"    orders={len(orders):,} lines={len(order_lines):,} "
          f"on_hold={int((orders['credit_status'] == 'Credit Hold').sum()):,} "
          f"cancelled={int(orders['is_cancelled'].sum()):,}")

    print("  allocating against available-to-promise...")
    order_lines, fulfillment, inventory = fulfillment_mod.allocate(
        s, orders, order_lines, wh, prod, ep, stream(12))
    live = order_lines[(order_lines["is_cancelled"] == 0)
                       & (order_lines["credit_status"] != "Credit Hold")]
    fill = live["quantity_allocated"].sum() / max(live["quantity_ordered"].sum(), 1)
    print(f"    fulfillments={len(fulfillment):,} fill_rate={fill:.1%} "
          f"inventory_positions={len(inventory):,}")

    print("  shipping...")
    shipments, shipment_lines, delivery_events = shipping_mod.build_shipments(
        s, orders, order_lines, fulfillment, carriers, wh, prod, ep, stream(13))
    dlv = shipments[shipments["is_delivered"] == 1]
    print(f"    shipments={len(shipments):,} lines={len(shipment_lines):,} "
          f"events={len(delivery_events):,} on_time={dlv['is_on_time_carrier'].mean():.1%}")

    print("  invoicing...")
    invoices, invoice_lines = build_invoices(s, orders, order_lines, shipments,
                                             shipment_lines, contracts, terms,
                                             cust, ep, stream(14))
    print(f"    invoices={len(invoices):,} lines={len(invoice_lines):,} "
          f"lag={invoices['days_delivery_to_invoice'].mean():.1f}d")

    print("  collecting cash, disputes and returns...")
    payments, allocations, disputes, memos, returns, invoices = \
        receivables_mod.build_collections(s, invoices, invoice_lines, orders,
                                          order_lines, shipments, prod, terms,
                                          cust, ep, stream(15))

    print("  deriving the AR ledger and snapshots...")
    invoices = snapshots_mod.compute_invoice_ledger(s, invoices, allocations, memos)
    invoices = snapshots_mod.apply_dispute_status(invoices, disputes)
    aging = snapshots_mod.build_ar_aging_snapshot(s, invoices, allocations, memos)
    exposure = snapshots_mod.build_credit_exposure_snapshot(s, cust, orders,
                                                            invoices, aging)
    open_ar = invoices.loc[invoices["is_open"] == 1, "open_amount_usd"].sum()
    print(f"    payments={len(payments):,} allocations={len(allocations):,} "
          f"open_AR=${open_ar / 1e6:,.1f}M aging_rows={len(aging):,}")

    print("  deriving the O2C cycle and exception centre...")
    cycle = derived_mod.build_o2c_cycle(s, orders, order_lines, quotes, shipments,
                                        shipment_lines, invoices, invoice_lines,
                                        allocations, memos)
    exceptions = derived_mod.build_exceptions(s, orders, order_lines, shipments,
                                              invoices, invoice_lines, disputes,
                                              payments, cycle, cust)

    ttm = cycle[pd.to_datetime(cycle["order_date"])
                >= pd.Timestamp(s.timeline.ttm_start)]
    print(f"    booked=${ttm['booked_net_usd'].sum() / 1e6:,.1f}M -> "
          f"collected=${ttm['collected_net_usd'].sum() / 1e6:,.1f}M "
          f"({len(exceptions):,} exceptions blocking "
          f"${exceptions['exception_value_usd'].sum() / 1e6:,.1f}M)")

    t.update({
        "fact_quote": quotes, "fact_quote_line": quote_lines,
        "fact_order": orders, "fact_order_line": order_lines,
        "fact_fulfillment": fulfillment, "fact_inventory_position": inventory,
        "fact_shipment": shipments, "fact_shipment_line": shipment_lines,
        "fact_delivery_event": delivery_events,
        "fact_invoice": invoices, "fact_invoice_line": invoice_lines,
        "fact_payment": payments, "fact_payment_allocation": allocations,
        "fact_credit_memo": memos, "fact_dispute": disputes, "fact_return": returns,
        "fact_ar_aging_snapshot": aging,
        "fact_credit_exposure_snapshot": exposure,
        "fact_o2c_cycle": cycle, "fact_o2c_exception": exceptions,
    })

    drop_internal(t)
    add_local_currency(s, t)
    normalize_types(t)

    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "data" / args.tier
    formats = (args.formats.split(",") if args.formats else s.output["formats"])
    write_tables(t, out_dir, formats, s, args.tier)
    print(f"  done in {time.time() - t0:,.1f}s -> {out_dir}")
    return 0


def drop_internal(tables: dict[str, pd.DataFrame]) -> None:
    """Remove the generator's own dials.

    Columns like `_spend_weight` and `_days_to_pay` are how the events are
    steered. Publishing them hands the audience the answer key, and an AI asked
    to find the slow-paying customer would simply read the column rather than
    work it out.
    """
    for name, df in tables.items():
        drop = [c for c in df.columns if c.startswith("_")]
        if drop:
            tables[name] = df.drop(columns=drop)


def add_local_currency(s, tables: dict[str, pd.DataFrame]) -> None:
    """Add a local-currency amount beside each USD amount on the money facts.

    Every KPI in the demo is USD; the local amount is what makes the extract
    look like it came from a real ERP. The rate is the fixed budget rate, so no
    FX movement leaks into the bookings-to-cash waterfall.
    """
    rates = s.currency["rates"]
    targets = {
        "fact_quote": ["net_quote_amount_usd", "quote_amount_usd"],
        "fact_order": ["net_order_amount_usd", "total_order_amount_usd"],
        "fact_invoice": ["net_amount_usd", "total_amount_usd"],
        "fact_payment": ["payment_amount_usd"],
    }
    for name, cols in targets.items():
        df = tables.get(name)
        if df is None or df.empty or "currency_code" not in df.columns:
            continue
        rate = df["currency_code"].map(rates).fillna(1.0).to_numpy()
        df["exchange_rate"] = np.round(rate, 6)
        for c in cols:
            if c in df.columns:
                df[c.replace("_usd", "_local")] = np.round(df[c].to_numpy() * rate, 2)
        tables[name] = df


DATE_SUFFIX = ("_date", "date", "_timestamp")


def normalize_types(tables: dict[str, pd.DataFrame]) -> None:
    """Give every written column a deliberate type.

    Without this the output inherits whatever pandas inferred during
    concatenation - int64 surrogate keys, timestamps for plain dates - and the
    generated DDL inherits the same sloppiness.
    """
    id32 = {"customer_id", "site_id", "bill_to_site_id", "product_id", "sales_rep_id",
            "warehouse_id", "carrier_id", "quote_id", "order_id", "shipment_id",
            "invoice_id", "payment_id", "dispute_id", "return_id", "credit_memo_id",
            "fulfillment_id", "contract_price_id", "currency_id", "exchange_rate_id",
            "payment_terms_id", "global_account_id", "duplicate_of_customer_id",
            "duplicate_of_invoice_id", "inventory_position_id", "credit_exposure_id",
            "o2c_cycle_id", "exception_id", "converted_order_id", "date_key",
            "year_month_key", "ar_aging_id"}
    for name, df in tables.items():
        for col in df.columns:
            ser = df[col]
            if col in id32 and pd.api.types.is_numeric_dtype(ser):
                df[col] = ser.fillna(0).astype("int32")
            elif col.startswith("is_") and pd.api.types.is_bool_dtype(ser):
                df[col] = ser.astype("int8")
            elif any(col.endswith(sfx) for sfx in DATE_SUFFIX):
                if pd.api.types.is_datetime64_any_dtype(ser):
                    # Dates, not timestamps: no BI tool benefits from a 00:00:00.
                    df[col] = ser.dt.date
            elif pd.api.types.is_float_dtype(ser) and (
                    col.endswith("_usd") or col.endswith("_local")):
                df[col] = ser.round(2)
        tables[name] = df


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path, formats: list[str],
                 s, tier: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_ok = "csv" in formats and tier == s.output.get("csv_max_tier", "small")
    total = 0
    for name, df in sorted(tables.items()):
        if df is None or df.empty:
            print(f"    WARNING: {name} is empty, not written")
            continue
        if "parquet" in formats:
            df.to_parquet(out_dir / f"{name}.parquet", index=False, compression="snappy")
        if csv_ok:
            df.to_csv(out_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        total += len(df)
    print(f"  wrote {len(tables)} tables, {total:,} rows "
          f"({'parquet' if 'parquet' in formats else ''}{'+csv' if csv_ok else ''})")


if __name__ == "__main__":
    raise SystemExit(main())
