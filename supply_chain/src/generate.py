#!/usr/bin/env python3
"""Meridian Global Industries - Supply Chain Control Tower : generator.

  python3 src/generate.py --tier small
  python3 src/generate.py --tier full --formats parquet
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import derived
import dims
import demand as dmd
import facts_forecast as ff
import facts_inbound as fi
import facts_inventory as fv
import facts_outbound as fo
from dim_date import build_dim_date
from events import EventEngine
from mgiconfig import PROJECT_ROOT, load_scenario


def generate(s, rng) -> dict[str, pd.DataFrame]:
    """Order is forced by the derivations -- docs/DATA_MODEL.md section 7."""
    t = {}
    log = []

    def step(msg):
        log.append((msg, time.time()))
        print(f"  {msg}")

    # 1. calendar + conformed dimensions
    step("dimensions")
    t["dim_date"] = build_dim_date(
        s.timeline.start_date, s.timeline.end_date,
        int(s.cfg["calendar"]["fiscal_year_start_month"]),
        int(s.cfg["calendar"]["retail_454_start_month"]),
        str(s.cfg["calendar"].get("retail_pattern", "4-5-4")))
    t["dim_region"] = dims.build_dim_region()
    t["dim_product_category"] = dims.build_dim_product_category()
    t["dim_location"] = dims.build_dim_location(
        int(s.sizes["locations"]), rng, bool(s.event("new_dc_ramp")))
    t["dim_carrier"] = dims.build_dim_carrier(int(s.sizes["carriers"]), rng)

    # 2-3. suppliers and products (base attributes only)
    t["dim_supplier"] = dims.build_dim_supplier(int(s.sizes["suppliers"]), rng, s.cfg)
    name_variants = dims.build_name_variants(
        t["dim_supplier"], int(s.baseline["data_quality"]["supplier_name_variant_count"]), rng)
    pinned = [e["supplier_master_id"] for k in ("supplier_disruption", "quality_failure")
              if (e := s.event(k)) and "supplier_master_id" in e]
    name_variants = dims.force_variants_on(name_variants, t["dim_supplier"], pinned, rng)
    t["dim_product"] = dims.build_dim_product(
        int(s.sizes["products"]), t["dim_supplier"], t["dim_product_category"], rng, s.cfg)
    t["dim_customer"] = dims.build_dim_customer(
        int(s.sizes["customers"]), t["dim_location"], rng, s.cfg)
    t["dim_employee"] = dims.build_dim_employee(
        int(s.sizes["employees"]), t["dim_location"], rng)

    step("events")
    engine = EventEngine(s, t["dim_product"], t["dim_supplier"],
                         t["dim_location"], t["dim_carrier"], rng)

    # 4-6. demand, then the classifications derived from it
    step("demand signal")
    t["fact_demand_signal"] = dmd.build_fact_demand_signal(
        s, t["dim_product"], t["dim_region"], engine, rng)
    t["dim_product"] = dmd.derive_abc_xyz(t["fact_demand_signal"], t["dim_product"], s)
    t["dim_product"] = dmd.set_planning_params(t["dim_product"], t["dim_supplier"], s)
    engine.retarget_after_classification(t["dim_product"])
    grid = dmd.build_stocking_grid(t["dim_product"], t["dim_location"], s, rng)

    # 7. forecast
    step("forecast")
    t["fact_forecast"] = ff.build_fact_forecast(
        s, t["fact_demand_signal"], t["dim_product"], t["dim_region"], engine, rng)

    # 8-10. inbound
    step("purchase orders + deliveries + production")
    t["fact_purchase_order"] = fi.build_purchase_orders(
        s, t["dim_product"], t["dim_supplier"], t["dim_location"], grid,
        engine, name_variants, rng)
    t["fact_supplier_delivery"] = fi.build_supplier_deliveries(
        s, t["fact_purchase_order"], t["dim_supplier"], engine, rng)
    t["fact_production"] = fi.build_production(
        s, t["dim_product"], t["dim_location"], grid, engine, rng)

    # 11. inventory
    step("inventory simulation")
    t["fact_inventory_snapshot"] = fv.build_inventory_snapshots(
        s, t["dim_product"], t["dim_location"], grid,
        t["fact_supplier_delivery"], t["fact_production"], engine, rng)

    # 12. outbound, constrained by what inventory actually served
    step("sales orders + shipments")
    t["fact_sales_order_line"] = fo.build_sales_order_lines(
        s, t["fact_inventory_snapshot"], t["dim_product"], t["dim_location"],
        t["dim_customer"], engine, rng)
    t["fact_shipment"] = fo.build_shipments(
        s, t["fact_sales_order_line"], t["dim_location"], t["dim_carrier"],
        t["dim_customer"], engine, rng)

    # 13-15. everything derived from the facts
    step("scorecards, risk, financial impact")
    t["dim_supplier"] = derived.backfill_supplier_scorecard(
        s, t["dim_supplier"], t["fact_supplier_delivery"], t["dim_product"])
    t["dim_carrier"] = derived.backfill_carrier_scorecard(
        t["dim_carrier"], t["fact_shipment"])
    t["fact_supply_chain_risk"] = derived.build_fact_supply_chain_risk(
        s, t["dim_supplier"], t["dim_product"], t["dim_location"],
        t["fact_supplier_delivery"], t["fact_inventory_snapshot"],
        t["fact_forecast"], t["fact_shipment"])
    t["fact_financial_impact"] = derived.build_fact_financial_impact(
        s, t["fact_inventory_snapshot"], t["fact_shipment"],
        t["fact_supplier_delivery"], t["fact_sales_order_line"], t["dim_product"])

    print("\nPlanted events:")
    print(engine.summary())
    return t


def write(tables: dict[str, pd.DataFrame], out_dir: Path, s, formats) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dec = int(s.output.get("decimals", 2))
    for name, df in sorted(tables.items()):
        if "parquet" in formats:
            df.to_parquet(out_dir / f"{name}.parquet", index=False)
        if "csv" in formats:
            df.to_csv(out_dir / f"{name}.csv", index=False,
                      date_format="%Y-%m-%d", float_format=f"%.{dec + 1}f")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--formats", default=None, help="comma list: parquet,csv")
    a = ap.parse_args(argv)

    s = load_scenario(a.scenario, a.tier)
    rng = np.random.default_rng(s.seed)
    out_dir = Path(a.out) if a.out else PROJECT_ROOT / "data" / a.tier

    formats = ([x.strip() for x in a.formats.split(",")] if a.formats
               else list(s.output["formats"]))
    if "csv" in formats and a.tier != s.output.get("csv_max_tier", "small"):
        formats = [f for f in formats if f != "csv"]

    print(f"Meridian Global Industries - supply chain, tier={a.tier}")
    print(f"as-of {s.timeline.as_of_date}  |  {s.timeline.start_date} .. {s.timeline.end_date}\n")
    t0 = time.time()
    tables = generate(s, rng)
    print(f"\ngenerated in {time.time() - t0:.1f}s")

    write(tables, out_dir, s, formats)
    total = sum(len(df) for df in tables.values())
    print(f"\nwrote {len(tables)} tables, {total:,} rows -> {out_dir}")
    for n, df in sorted(tables.items()):
        print(f"  {n:28s} {len(df):>10,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
