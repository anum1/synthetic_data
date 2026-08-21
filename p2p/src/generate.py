#!/usr/bin/env python3
"""Norvant Group - Procure-to-Pay Control Tower : dataset generator.

  python3 src/generate.py --tier small
  python3 src/generate.py --tier full --scenario config/my_scenario.yaml

The stages run in dependency order because the demo's causal chain runs in that
order too: a contract price is set, a PO drifts above it, the invoice breaches
tolerance, a hold is raised, approval is delayed past the discount window, the
discount is lost and the payment lands late. Reordering any of it breaks the
story that PLAN 2.6 is built on.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog as catalog_mod
import contracts as contracts_mod
import derived as derived_mod
import dims as dims_mod
import invoicing as invoicing_mod
import matching as matching_mod
import orgs as orgs_mod
import payments as payments_mod
import pcard as pcard_mod
import purchasing as purchasing_mod
import receiving as receiving_mod
import requisitions as requisitions_mod
import snapshots as snapshots_mod
import suppliers as suppliers_mod
from dim_date import build_dim_date
from events import EventPlan
from p2pconfig import PROJECT_ROOT, load_scenario


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config"
                                              / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--out", default=None, help="output directory (default data/<tier>)")
    ap.add_argument("--formats", default=None, help="comma list: parquet,csv")
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    t0 = time.time()

    # One independent random stream per subsystem, all derived from the single
    # configured seed. Sharing one generator means changing a receiving knob
    # reshuffles every draw downstream of it, so tuning one number moves five
    # unrelated numbers and the dataset never converges.
    def stream(tag: int) -> np.random.Generator:
        return np.random.default_rng([s.seed, tag])

    print(f"{s.company} P2P generator | scenario={s.cfg['meta']['scenario_name']} "
          f"tier={args.tier}")
    print(f"  history {s.timeline.start_date} -> as-of {s.timeline.as_of_date} "
          f"({len(s.timeline.month_starts())} months)")

    t: dict[str, pd.DataFrame] = {}

    print("  building master data...")
    t["dim_date"] = build_dim_date(s.timeline.start_date, s.timeline.end_date,
                                   int(s.calendar["fiscal_year_start_month"]))
    ent = orgs_mod.build_dim_company_code(s)
    dept = orgs_mod.build_dim_department(s, ent, stream(1))
    ccs = orgs_mod.build_dim_cost_center(s, dept, stream(2))
    emp = orgs_mod.build_dim_employee(s, dept, ccs, stream(3))
    policy = orgs_mod.build_dim_approval_policy(s, ent)
    sup, parents, sites, banks, status_hist = suppliers_mod.build_supplier_master(
        s, ent, emp, stream(4))
    cats = catalog_mod.build_dim_category(s, stream(5))
    gl = catalog_mod.build_dim_gl_account(s, cats, stream(6))
    items = catalog_mod.build_dim_item(s, cats, gl, stream(7))
    terms = dims_mod.build_dim_payment_terms(s)
    fx = dims_mod.build_dim_exchange_rate(s, stream(8))
    tolerances = dims_mod.build_dim_match_tolerance(s)
    hold_reasons = dims_mod.build_dim_hold_reason()
    print(f"    suppliers={len(sup):,} sites={len(sites):,} employees={len(emp):,} "
          f"categories={len(cats):,} items={len(items):,}")

    # Events resolve to concrete targets once, before anything is drawn, so every
    # stage downstream agrees on which supplier, buyer and department the stories
    # land on.
    ep = EventPlan(s, sup, dept, cats, emp, stream(9))
    print(f"    hero supplier: {ep.hero_supplier_name} "
          f"(drift {ep.price_drift.get(ep.hero_supplier_id, 0):.0%}, "
          f"{len(ep.price_drift)} suppliers drifting)")

    print("  sourcing and contracts...")
    coverage, sampler = contracts_mod.build_supplier_coverage(s, sup, cats, ep,
                                                              stream(10))
    contracts, contract_price = contracts_mod.build_contracts(
        s, sup, cats, items, coverage, terms, emp, ep, stream(11))
    print(f"    contracts={len(contracts):,} contract_prices={len(contract_price):,} "
          f"expired={int(contracts['is_expired'].sum()):,}")

    print("  raising requisitions...")
    req, req_lines = requisitions_mod.build_requisitions(
        s, emp, dept, ccs, cats, items, contract_price, sampler, ep, stream(12))
    approved = (req["requisition_status"] == "Approved").mean()
    print(f"    requisitions={len(req):,} lines={len(req_lines):,} "
          f"approved={approved:.1%}")

    print("  converting to purchase orders...")
    po, po_lines, po_changes = purchasing_mod.build_purchase_orders(
        s, req, req_lines, sup, sites, emp, contracts, contract_price, terms,
        policy, ep, stream(13))
    print(f"    POs={len(po):,} lines={len(po_lines):,} changes={len(po_changes):,} "
          f"cancelled={int(po['is_cancelled'].sum()):,}")

    print("  receiving...")
    gr, gr_lines, po_lines = receiving_mod.build_receipts(
        s, po, po_lines, items, emp, ep, stream(14))
    on_time = po_lines.loc[po_lines["is_on_time"].notna(), "is_on_time"].mean()
    print(f"    receipts={len(gr):,} lines={len(gr_lines):,} "
          f"on_time={on_time:.1%}")

    print("  invoicing...")
    inv, inv_lines, dist, po_lines = invoicing_mod.build_invoices(
        s, po, po_lines, gr_lines, sup, sites, terms, fx, cats, items, dept, ccs,
        gl, contract_price, ep, stream(15))
    print(f"    invoices={len(inv):,} lines={len(inv_lines):,} "
          f"distributions={len(dist):,}")

    print("  matching, holds and approval...")
    match, holds, approvals, inv = matching_mod.build_matching(
        s, inv, inv_lines, po, po_lines, sup, banks, contracts, tolerances,
        hold_reasons, emp, ccs, ep, stream(16))
    fpm = match.groupby("invoice_id")["is_first_pass_match"].min().mean() \
        if len(match) else float("nan")
    print(f"    match_results={len(match):,} holds={len(holds):,} "
          f"first_pass={fpm:.1%} exceptions={inv['invoice_id'].isin(holds['invoice_id']).mean():.1%}")

    print("  paying...")
    pay, apps, inv = payments_mod.build_payments(s, inv, sup, banks, fx, ep,
                                                 stream(17))
    open_ap = inv.loc[inv["is_open"] == 1, "open_amount_usd"].sum()
    print(f"    payments={len(pay):,} applications={len(apps):,} "
          f"open_payables=${open_ap / 1e6:,.1f}M")

    print("  card channel...")
    card = pcard_mod.build_pcard(s, inv, sup, cats, items, dept, ccs, emp,
                                 contract_price, ep, stream(18))

    print("  month-end snapshots...")
    aging = snapshots_mod.build_ap_aging_snapshot(s, inv, apps)
    commitment = snapshots_mod.build_open_commitment_snapshot(
        s, po, po_lines, gr_lines, inv_lines, inv)
    risk = suppliers_mod.build_supplier_risk_snapshot(s, sup, stream(19))
    print(f"    aging={len(aging):,} commitment={len(commitment):,} risk={len(risk):,}")

    print("  deriving spend, cycle and the exception centre...")
    spend = derived_mod.build_spend(s, inv, inv_lines, card, po, po_lines, cats,
                                    sup, contract_price)
    cycle = derived_mod.build_p2p_cycle(s, req, req_lines, po, po_lines, gr_lines,
                                        inv, inv_lines, apps)
    exceptions = derived_mod.build_exceptions(s, inv, holds, match, po_lines, sup)
    budget = derived_mod.build_budget(s, spend, ccs, dept, ep, stream(20))

    ttm = spend[pd.to_datetime(spend["spend_date"])
                >= pd.Timestamp(s.timeline.ttm_start)]
    print(f"    spend=${ttm['spend_amount_usd'].sum() / 1e6:,.1f}M TTM | "
          f"{len(exceptions):,} open exceptions blocking "
          f"${exceptions['exception_value_usd'].sum() / 1e6:,.1f}M")

    t.update({
        "dim_company_code": ent, "dim_department": dept, "dim_cost_center": ccs,
        "dim_employee": emp, "dim_approval_policy": policy,
        "dim_supplier": sup, "dim_supplier_parent": parents,
        "dim_supplier_site": sites, "dim_supplier_bank_account": banks,
        "dim_supplier_status_history": status_hist,
        "dim_category": cats, "dim_gl_account": gl, "dim_item": items,
        "dim_payment_terms": terms, "dim_exchange_rate": fx,
        "dim_currency": dims_mod.build_dim_currency(s),
        "dim_match_tolerance": tolerances, "dim_hold_reason": hold_reasons,
        "contract": contracts, "contract_price": contract_price,
        "fact_budget": budget,
        "fact_requisition": req, "fact_requisition_line": req_lines,
        "fact_purchase_order": po, "fact_purchase_order_line": po_lines,
        "fact_po_change": po_changes,
        "fact_goods_receipt": gr, "fact_goods_receipt_line": gr_lines,
        "fact_invoice": inv, "fact_invoice_line": inv_lines,
        "fact_invoice_distribution": dist,
        "fact_match_result": match, "fact_invoice_hold": holds,
        "fact_approval_event": approvals,
        "fact_payment": pay, "fact_payment_application": apps,
        "fact_pcard_transaction": card,
        "fact_ap_aging_snapshot": aging,
        "fact_open_commitment_snapshot": commitment,
        "fact_supplier_risk_snapshot": risk,
        "fact_spend": spend, "fact_p2p_cycle": cycle,
        "fact_p2p_exception": exceptions,
    })

    drop_internal(t)
    normalize_types(t)

    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "data" / args.tier
    formats = (args.formats.split(",") if args.formats else s.output["formats"])
    write_tables(t, out_dir, formats, s, args.tier)
    print(f"  done in {time.time() - t0:,.1f}s -> {out_dir}")
    return 0


def drop_internal(tables: dict[str, pd.DataFrame]) -> None:
    """Remove the generator's own dials.

    Columns like `_spend_weight` and `_released_ts` are how the events are
    steered. Publishing them hands the audience the answer key, and an AI asked
    to find the drifting supplier would read the column rather than work it out.
    """
    for name, df in tables.items():
        if df is None or df.empty:
            continue
        drop = [c for c in df.columns if c.startswith("_")]
        if drop:
            tables[name] = df.drop(columns=drop)


DATE_SUFFIX = ("_date", "date", "_month_end")


def normalize_types(tables: dict[str, pd.DataFrame]) -> None:
    """Give every written column a deliberate type.

    Without this the output inherits whatever pandas inferred during
    concatenation - int64 surrogate keys, timestamps for plain dates - and the
    generated DDL inherits the same sloppiness.
    """
    id32 = {
        "supplier_id", "supplier_parent_id", "supplier_site_id", "bank_account_id",
        "employee_id", "manager_employee_id", "department_id", "cost_center_id",
        "category_id", "item_id", "gl_account_id", "currency_id", "company_code_id",
        "payment_terms_id", "exchange_rate_id", "approval_policy_id",
        "match_tolerance_id", "hold_reason_id", "contract_id", "contract_price_id",
        "requisition_id", "requisition_line_id", "purchase_order_id",
        "purchase_order_line_id", "po_change_id", "goods_receipt_id",
        "goods_receipt_line_id", "invoice_id", "invoice_line_id",
        "invoice_distribution_id", "match_result_id", "invoice_hold_id",
        "approval_event_id", "payment_id", "payment_application_id",
        "pcard_transaction_id", "ap_aging_id", "open_commitment_id",
        "budget_id", "supplier_risk_id", "spend_id", "p2p_cycle_id", "p2p_exception_id",
        "status_history_id", "date_key", "year_month_key", "buyer_employee_id",
        "requester_employee_id", "approver_employee_id", "owner_employee_id",
        "cardholder_employee_id", "received_by_employee_id",
        "changed_by_employee_id", "delegated_from_employee_id",
        "duplicate_of_supplier_id", "duplicate_of_inv_seq", "entity_id",
    }
    for name, df in tables.items():
        if df is None or df.empty:
            continue
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
                elif ser.dtype == object:
                    # Stages hand dates over in whichever form they held them -
                    # Timestamp from one table, datetime.date from another - and
                    # a column carrying both is an object column that parquet
                    # refuses to write. Coerce once, here, for every table.
                    try:
                        df[col] = pd.to_datetime(ser, errors="coerce").dt.date
                    except (TypeError, ValueError):
                        pass
            elif pd.api.types.is_float_dtype(ser) and col.endswith("_usd"):
                df[col] = ser.round(2)
        tables[name] = df


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path, formats: list[str],
                 s, tier: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_ok = "csv" in formats and tier == s.output.get("csv_max_tier", "small")
    total = 0
    written = 0
    for name, df in sorted(tables.items()):
        if df is None or df.empty:
            print(f"    WARNING: {name} is empty, not written")
            continue
        if "parquet" in formats:
            df.to_parquet(out_dir / f"{name}.parquet", index=False,
                          compression="snappy")
        if csv_ok:
            df.to_csv(out_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        total += len(df)
        written += 1
    print(f"  wrote {written} tables, {total:,} rows "
          f"({'parquet' if 'parquet' in formats else ''}{'+csv' if csv_ok else ''})")


if __name__ == "__main__":
    raise SystemExit(main())
