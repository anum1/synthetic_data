#!/usr/bin/env python3
"""ApexTech - Enterprise Sales & Profitability 360 : dataset generator.

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

import dims
import facts_support as fs
from apexconfig import PROJECT_ROOT, load_scenario
from dim_date import build_dim_date
from facts import SalesGenerator, month_range


def build_dimensions(s, rng) -> dict[str, pd.DataFrame]:
    sz = s.sizes
    t = s.timeline
    out: dict[str, pd.DataFrame] = {}

    out["dim_date"] = build_dim_date(
        t.start_date, t.end_date,
        int(s.cfg["calendar"]["fiscal_year_start_month"]),
        int(s.cfg["calendar"]["retail_454_start_month"]),
        str(s.cfg["calendar"].get("retail_pattern", "4-5-4")))

    # Conformed dimensions shared by the sales fact and the plan facts.
    out["dim_country"] = dims.build_dim_country()
    out["dim_product_category"] = dims.build_dim_product_category()
    country_key = dict(zip(out["dim_country"]["country"], out["dim_country"]["country_id"]))
    category_key = dict(zip(out["dim_product_category"]["category"] + "|"
                            + out["dim_product_category"]["subcategory"],
                            out["dim_product_category"]["product_category_id"]))

    out["dim_channel"] = dims.build_dim_channel(s.baseline["channel_mix"])
    out["dim_currency"] = dims.build_dim_currency()
    months = pd.DatetimeIndex(pd.to_datetime(month_range(t.start_date, t.end_date)))
    out["dim_exchange_rate"] = dims.build_dim_exchange_rate(months, rng)

    out["dim_supplier"] = dims.build_dim_supplier(sz["suppliers"], rng, t)
    out["dim_product"] = dims.build_dim_product(
        sz["products"], out["dim_supplier"]["supplier_id"].to_numpy(),
        out["dim_supplier"]["supplier_group"].to_numpy(), rng, t,
        s.event("product_launch"),
        target_margin=float(s.baseline["base_gross_margin_pct"]),
        expected_discount=float(s.baseline["base_discount_pct"]) + 0.028,
        shipping_rate=0.021,
        shock_group=(s.event("supplier_cost_shock") or {}).get("supplier_group"),
        shock_subcategories=tuple(s.cfg["events"]["supplier_cost_shock"]
                                  .get("sourced_subcategories", [])),
        category_key=category_key)
    out["dim_location"] = dims.build_dim_location(
        sz["locations"], s.baseline["region_mix"], rng, country_key)
    out["dim_sales_rep"] = dims.build_dim_sales_rep(
        sz["sales_reps"], list(s.baseline["region_mix"]), rng, t)
    out["dim_customer"] = dims.build_dim_customer(
        sz["customers"], out["dim_location"], out["dim_sales_rep"]["sales_rep_id"].to_numpy(),
        list(out["dim_channel"]["sales_channel"]), rng, t, s.event("customer_contraction"))
    out["dim_promotion"] = dims.build_dim_promotion(
        200, t, rng, s.event("promotion_surge"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--out", default=None, help="output directory (default data/<tier>)")
    ap.add_argument("--formats", default=None, help="comma list: parquet,csv")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    rng = np.random.default_rng(s.seed)
    t0 = time.time()

    print(f"ApexTech generator | scenario={s.cfg['meta']['scenario_name']} tier={args.tier}")
    print(f"  history {s.timeline.start_date} -> as-of {s.timeline.as_of_date} "
          f"-> horizon {s.timeline.end_date}")

    print("  building dimensions...")
    tables = build_dimensions(s, rng)

    print("  building sales facts...")
    gen = SalesGenerator(s, tables, rng)
    tables.update(gen.generate())

    print("  building supporting facts...")
    lines = tables["fact_sales_order_line"]
    tables["fact_returns"] = fs.build_returns(
        s, lines, tables["dim_product"], tables["dim_supplier"], gen.events, rng)
    tables["fact_inventory"] = fs.build_inventory(
        s, lines, tables["dim_product"], tables["dim_location"], gen.events, rng)
    tables["fact_supplier_performance"] = fs.build_supplier_performance(
        s, lines, tables["dim_product"], tables["dim_supplier"], gen.events, rng)

    plan_actuals = fs._plan_grain(lines, tables["dim_product"],
                                  tables["dim_location"], tables["dim_channel"])
    tables["fact_budget"] = fs.build_budget(s, plan_actuals, rng)
    tables["fact_forecast"] = fs.build_forecast(s, plan_actuals, tables["fact_budget"], rng)
    tables["fact_sales_rep_quota"] = fs.build_rep_quota(
        s, lines, tables["dim_sales_rep"], rng)

    print(f"    orders={len(tables['fact_sales_order']):,} lines={len(lines):,} "
          f"net_sales=${lines['net_sales'].sum()/1e6:,.1f}M "
          f"margin={lines['gross_profit'].sum()/lines['net_sales'].sum():.1%}")

    normalize_types(tables)
    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "data" / args.tier
    formats = (args.formats.split(",") if args.formats else s.output["formats"])
    write_tables(tables, out_dir, formats, s, args.tier)

    print(f"  done in {time.time() - t0:,.1f}s -> {out_dir}")
    return 0


DATE_COLS_AS_DATE = True

# Columns whose name does not advertise that they hold money.
_MONEY_EXACT = {"cost", "quantity_cost", "supplier_cost"}


def normalize_types(tables: dict[str, pd.DataFrame]) -> None:
    """Give every written column a deliberate type.

    Without this the output inherits whatever pandas happened to infer during
    concatenation - int64 surrogate keys, timestamps for plain dates - and the
    generated DDL inherits the same sloppiness.
    """
    id_cols = {"customer_id": "int32", "product_id": "int32", "supplier_id": "int32",
               "location_id": "int32", "sales_rep_id": "int32", "promotion_id": "int32",
               "channel_id": "int16", "date_key": "int32", "year_month_key": "int32",
               "order_id": "int64", "order_line_id": "int64", "return_id": "int64",
               "quantity": "int32", "line_number": "int16"}
    for name, df in tables.items():
        for col in df.columns:
            if col in id_cols and pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].astype(id_cols[col])
            elif col.startswith("is_") and pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].astype("int8")
            elif (col.endswith("_date") or col == "snapshot_date") and DATE_COLS_AS_DATE:
                # Dates, not timestamps: no BI tool benefits from a 00:00:00.
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.date
        tables[name] = df


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path,
                 formats: list[str], s, tier: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_ok = "csv" in formats and tier == s.output.get("csv_max_tier", "small")
    for name, df in tables.items():
        if "parquet" in formats:
            df.to_parquet(out_dir / f"{name}.parquet", index=False,
                          compression="snappy")
        if csv_ok:
            df.to_csv(out_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    print(f"  wrote {len(tables)} tables "
          f"({'parquet' if 'parquet' in formats else ''}"
          f"{'+csv' if csv_ok else ''})")


if __name__ == "__main__":
    raise SystemExit(main())
