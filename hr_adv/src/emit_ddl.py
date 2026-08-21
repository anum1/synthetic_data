#!/usr/bin/env python3
"""Emit platform DDL and load scripts from the ACTUAL generated schemas.

Hand-written DDL drifts from the data the first time a column is added. This
reads the parquet files and derives the types, so the DDL is correct by
construction or it does not exist.

  python3 src/emit_ddl.py --tier full
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hrconfig import PROJECT_ROOT

# Columns that are money and must not be inferred as floats.
MONEY_SUFFIX = ("_usd", "_local", "_pay", "_cost", "tax", "commission", "allowance",
                "deduction")
PCT_SUFFIX = ("_pct", "_percentage", "_ratio", "_rate", "_share", "_factor", "_score")

PRIMARY_KEY = {
    "dim_date": "date_key", "dim_employee": "employee_id",
    "dim_organization": "organization_id", "dim_location": "location_id",
    "dim_job": "job_id", "job_salary_range": "job_salary_range_id",
    "dim_benefit_plan": "benefit_plan_id", "dim_pay_calendar": "pay_period_id",
    "fact_workforce_snapshot": "workforce_snapshot_id",
    "fact_job_history": "job_history_id", "fact_salary_history": "salary_history_id",
    "fact_termination": "termination_id", "fact_performance_review": "review_id",
    "fact_bonus": "bonus_id", "fact_payroll": "payroll_id",
    "fact_benefit_enrollment": "benefit_enrollment_id", "fact_absence": "absence_id",
    "fact_workforce_cost_bridge": "cost_bridge_id",
    "fact_manager_scorecard": "manager_scorecard_id",
    "fact_workforce_risk": "workforce_risk_id",
}

FOREIGN_KEYS = {
    "employee_id": ("dim_employee", "employee_id"),
    "manager_employee_id": ("dim_employee", "employee_id"),
    "organization_id": ("dim_organization", "organization_id"),
    "location_id": ("dim_location", "location_id"),
    "job_id": ("dim_job", "job_id"),
    "benefit_plan_id": ("dim_benefit_plan", "benefit_plan_id"),
    "pay_period_id": ("dim_pay_calendar", "pay_period_id"),
    "date_key": ("dim_date", "date_key"),
}


def sql_type(col: str, series: pd.Series, dialect: str) -> str:
    dt_ = series.dtype
    if pd.api.types.is_datetime64_any_dtype(dt_):
        return "DATE"
    # pandas 3 gives text columns a dedicated string dtype rather than object, so
    # testing `== object` alone sends every string to the fallback. Note that
    # is_string_dtype() is True for plain object columns too, which is why the
    # date test has to come first - our date columns ARE object columns holding
    # datetime.date, and stringifying them first would type them as VARCHAR.
    if dt_ == object or pd.api.types.is_string_dtype(dt_):
        sample = series.dropna()
        if len(sample) and isinstance(sample.iloc[0], dt.date):
            return "DATE"
        width = int(sample.astype(str).str.len().max()) if len(sample) else 16
        n = max(16, min(512, ((width // 16) + 1) * 16))
        return f"VARCHAR({n})" if dialect == "snowflake" else "STRING"
    if pd.api.types.is_bool_dtype(dt_):
        return "TINYINT" if dialect == "databricks" else "NUMBER(1,0)"
    if pd.api.types.is_integer_dtype(dt_):
        big = series.abs().max() if len(series) else 0
        if dialect == "databricks":
            return "BIGINT" if big and big > 2_147_483_647 else "INT"
        return "NUMBER(19,0)" if big and big > 2_147_483_647 else "NUMBER(10,0)"
    if pd.api.types.is_float_dtype(dt_):
        if col.endswith(MONEY_SUFFIX):
            return "DECIMAL(18,2)"
        if col.endswith(PCT_SUFFIX):
            return "DECIMAL(12,6)"
        return "DECIMAL(18,4)"
    return "STRING" if dialect == "databricks" else "VARCHAR(256)"


def emit(tier: str, dialect: str, data_dir: Path, out_dir: Path, database: str,
         schema: str) -> None:
    files = sorted(data_dir.glob("*.parquet"))
    lines = [
        f"-- GlobalTech HR Analytics - {dialect} DDL",
        f"-- Generated from data/{tier} on {dt.date.today()}. Do not hand-edit:",
        f"-- rerun src/emit_ddl.py --tier {tier} instead.",
        "",
    ]
    if dialect == "snowflake":
        lines += [f"CREATE DATABASE IF NOT EXISTS {database};",
                  f"CREATE SCHEMA IF NOT EXISTS {database}.{schema};",
                  f"USE SCHEMA {database}.{schema};", ""]
    else:
        lines += [f"CREATE CATALOG IF NOT EXISTS {database};",
                  f"CREATE SCHEMA IF NOT EXISTS {database}.{schema};",
                  f"USE {database}.{schema};", ""]

    for f in files:
        df = pd.read_parquet(f)
        name = f.stem
        pk = PRIMARY_KEY.get(name)
        cols = []
        for col in df.columns:
            typ = sql_type(col, df[col], dialect)
            null = " NOT NULL" if col == pk or col in FOREIGN_KEYS else ""
            cols.append(f"    {col:<42s} {typ}{null}")
        body = ",\n".join(cols)
        lines.append(f"CREATE OR REPLACE TABLE {name} (")
        lines.append(body)
        if pk and dialect == "snowflake":
            lines.append(f",\n    CONSTRAINT pk_{name} PRIMARY KEY ({pk})")
        lines.append(");")
        # Foreign keys are declared for the modelling tools that read them, even
        # where the platform does not enforce them.
        if dialect == "snowflake":
            for col, (ref_table, ref_col) in FOREIGN_KEYS.items():
                if col in df.columns and name != ref_table:
                    lines.append(f"ALTER TABLE {name} ADD CONSTRAINT "
                                 f"fk_{name}_{col} FOREIGN KEY ({col}) "
                                 f"REFERENCES {ref_table}({ref_col});")
        lines.append(f"COMMENT ON TABLE {name} IS "
                     f"'GlobalTech HR Analytics - {len(df):,} rows at tier {tier}';")
        lines.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "01_ddl.sql").write_text("\n".join(lines))

    if dialect == "snowflake":
        load = [
            "-- Load from an internal stage. Upload the parquet files first:",
            "--   snowsql -q \"PUT file://data/%s/*.parquet @%%hr_stage AUTO_COMPRESS=FALSE\"" % tier,
            f"USE SCHEMA {database}.{schema};",
            "CREATE STAGE IF NOT EXISTS hr_stage "
            "FILE_FORMAT = (TYPE = PARQUET);", ""]
        for f in files:
            load.append(f"COPY INTO {f.stem} FROM @hr_stage/{f.name} "
                        f"FILE_FORMAT = (TYPE = PARQUET) "
                        f"MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;")
        (out_dir / "02_load.sql").write_text("\n".join(load) + "\n")
    else:
        py = ['# Databricks notebook: load the parquet files into the tables.',
              '# Upload data/%s to a volume or DBFS path, then set SOURCE below.' % tier,
              'SOURCE = "dbfs:/FileStore/globaltech_hr/%s"' % tier,
              f'spark.sql("USE {database}.{schema}")', "",
              "for table in [" + ", ".join(f'"{f.stem}"' for f in files) + "]:",
              "    (spark.read.parquet(f\"{SOURCE}/{table}.parquet\")",
              "        .write.mode(\"overwrite\").saveAsTable(table))",
              "    print(table, spark.table(table).count())"]
        (out_dir / "02_load.py").write_text("\n".join(py) + "\n")
    print(f"  wrote {out_dir}/01_ddl.sql ({len(files)} tables)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="full", choices=["small", "full"])
    ap.add_argument("--database", default="GLOBALTECH_HR")
    ap.add_argument("--schema", default="ANALYTICS")
    args = ap.parse_args(argv)

    data_dir = PROJECT_ROOT / "data" / args.tier
    if not data_dir.exists():
        print(f"no data at {data_dir}; run generate.py first")
        return 2
    for dialect in ("snowflake", "databricks"):
        emit(args.tier, dialect, data_dir, PROJECT_ROOT / "sql" / dialect,
             args.database, args.schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
