#!/usr/bin/env python3
"""GlobalTech - HR / Workforce Analytics : dataset generator.

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

import absence as absence_mod
import benefits as benefits_mod
import compensation as comp_mod
import derived as derived_mod
import payroll as payroll_mod
import snapshots as snapshots_mod
from dim_date import build_dim_date
from hrconfig import PROJECT_ROOT, load_scenario
from jobs import build_dim_job, build_job_salary_range
from org import build_dim_location, build_dim_organization
from population import Workforce

# Columns holding protected-class attributes. Generated either way; written only
# when demographics.enabled is true.
DEMOGRAPHIC_COLUMNS = ["gender", "ethnicity", "veteran_status", "disability_status"]


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
    # configured seed. Sharing one generator means changing a benefits knob
    # reshuffles every draw downstream of it, so tuning one number moves five
    # unrelated numbers and the dataset never converges.
    def stream(tag: int) -> np.random.Generator:
        return np.random.default_rng([s.seed, tag])

    rng = stream(1)

    print(f"GlobalTech HR generator | scenario={s.cfg['meta']['scenario_name']} "
          f"tier={args.tier}")
    print(f"  history {s.timeline.start_date} -> as-of {s.timeline.as_of_date} "
          f"({len(s.timeline.month_starts())} months)")

    tables: dict[str, pd.DataFrame] = {}

    print("  building dimensions...")
    tables["dim_date"] = build_dim_date(s.timeline.start_date, s.timeline.end_date,
                                        int(s.calendar["fiscal_year_start_month"]))
    tables["dim_organization"] = build_dim_organization(s, stream(2))
    tables["dim_location"] = build_dim_location(s, stream(3))
    tables["dim_job"] = build_dim_job(s, stream(4))
    tables["job_salary_range"] = build_job_salary_range(s, tables["dim_job"])

    print("  simulating the workforce month by month...")
    wf = Workforce(s, tables, stream(5))
    tables.update(wf.run())
    tables["fact_workforce_snapshot"] = snapshots_mod.add_manager_chain(
        tables["fact_workforce_snapshot"])
    snap = tables["fact_workforce_snapshot"]
    emp = tables["dim_employee"]
    print(f"    employees={len(emp) - 1:,} snapshot_rows={len(snap):,} "
          f"headcount_at_as_of={int((emp['is_active'] == 1).sum()):,}")

    print("  building benefits...")
    tables["dim_benefit_plan"] = benefits_mod.build_dim_benefit_plan(s, stream(6))
    tables["fact_benefit_enrollment"] = benefits_mod.build_benefit_enrollment(
        s, snap, tables["dim_benefit_plan"], stream(7))

    print("  building bonus and absence...")
    tables["fact_bonus"] = comp_mod.build_bonus(s, snap, emp, stream(8))
    tables["fact_absence"] = absence_mod.build_absence(s, snap, stream(9),
                                                       wf.mgr_problem_orgs)

    print("  deriving payroll...")
    tables["dim_pay_calendar"] = payroll_mod.build_pay_calendar(s)
    tables["fact_payroll"] = payroll_mod.build_payroll(
        s, snap, tables["dim_pay_calendar"], tables["dim_job"], tables["fact_bonus"],
        tables["fact_benefit_enrollment"], tables["fact_absence"], emp, stream(10))
    pay = tables["fact_payroll"]
    print(f"    payroll_rows={len(pay):,} "
          f"gross=${pay['gross_pay'].sum() / 1e9:,.2f}B "
          f"total_cost=${pay['total_employer_cost'].sum() / 1e9:,.2f}B")

    print("  deriving the cost bridge and risk layer...")
    tables["fact_workforce_cost_bridge"] = derived_mod.build_cost_bridge(s, pay, snap)
    tables["fact_manager_scorecard"] = derived_mod.build_manager_scorecard(
        s, snap, tables["fact_termination"], tables["fact_absence"], emp)
    tables["fact_workforce_risk"] = derived_mod.build_workforce_risk(
        s, snap, tables["fact_manager_scorecard"], emp)

    head = tables["fact_workforce_cost_bridge"]
    head = head[(head["scope_type"] == "Company") & (head["is_total"] == 1)]
    if len(head):
        print(f"    workforce cost {float(head['contribution_pct'].iloc[0]):+.1%} YoY")

    apply_demographics_policy(s, tables)
    normalize_types(tables)

    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "data" / args.tier
    formats = (args.formats.split(",") if args.formats else s.output["formats"])
    write_tables(tables, out_dir, formats, s, args.tier)
    print(f"  done in {time.time() - t0:,.1f}s -> {out_dir}")
    return 0


def apply_demographics_policy(s, tables: dict[str, pd.DataFrame]) -> None:
    """Drop protected-class columns unless the scenario opts in.

    They are generated regardless so a DEI page is one config flag away, but the
    default is off: plenty of prospects do not want gender or ethnicity on a
    screen in front of a room.
    """
    if s.demographics.get("enabled", False):
        return
    cols = s.demographics.get("columns", DEMOGRAPHIC_COLUMNS)
    for name, df in tables.items():
        drop = [c for c in cols if c in df.columns]
        if drop:
            tables[name] = df.drop(columns=drop)


DATE_COLS = ("_date", "date_", "birth_date", "hire_date", "start_date", "end_date",
             "pay_date", "snapshot_date", "award_date", "payout_date")


def normalize_types(tables: dict[str, pd.DataFrame]) -> None:
    """Give every written column a deliberate type.

    Without this the output inherits whatever pandas inferred during
    concatenation - int64 surrogate keys, timestamps for plain dates - and the
    generated DDL inherits the same sloppiness.
    """
    id32 = {"employee_id", "manager_employee_id", "organization_id", "location_id",
            "job_id", "benefit_plan_id", "job_salary_range_id", "pay_period_id",
            "parent_organization_id", "termination_id", "review_id",
            "old_job_id", "new_job_id", "old_organization_id", "new_organization_id",
            "old_manager_employee_id", "new_manager_employee_id", "old_location_id",
            "new_location_id", "date_key", "year_month_key"}
    for name, df in tables.items():
        for col in df.columns:
            ser = df[col]
            if col in id32 and pd.api.types.is_numeric_dtype(ser):
                df[col] = ser.fillna(0).astype("int32")
            elif col.startswith("is_") and pd.api.types.is_bool_dtype(ser):
                df[col] = ser.astype("int8")
            elif any(col.endswith(sfx) or col == sfx for sfx in DATE_COLS):
                if pd.api.types.is_datetime64_any_dtype(ser):
                    # Dates, not timestamps: no BI tool benefits from a 00:00:00.
                    df[col] = ser.dt.date
            elif pd.api.types.is_float_dtype(ser) and (
                    col.endswith("_usd") or col.endswith("_local")
                    or col.endswith("_pay") or col.endswith("_cost")):
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
