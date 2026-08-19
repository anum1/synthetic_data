#!/usr/bin/env python3
"""Emit platform DDL and load scripts from the generated parquet schemas.

Deriving the DDL from the data rather than hand-writing it means the types can
never drift from what the generator actually produces.

  python3 src/emit_ddl.py --tier full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mgiconfig import PROJECT_ROOT

CATALOG = "meridian"
SCHEMA = "supply_chain"

# Money needs explicit scale. Floats would let a cost waterfall drift away
# from the KPI tile it is supposed to reconcile to.
MONEY_SUFFIXES = ("_value", "_cost", "_amount", "_price", "_revenue",
                  "_profit", "_spend", "_impact_amount")
# Quantities are DECIMAL(18,3): some categories ship in kg and litres, so
# integer quantities would force a units-of-measure conversion nobody needs.
QTY_SUFFIXES = ("_qty",)
RATIO_SUFFIXES = ("_pct", "_rate", "_score", "_accuracy", "_share", "_cv",
                  "_risk", "_error")

MONEY_EXACT = {"unit_cost", "standard_price", "freight_cost", "quality_cost",
               "production_cost", "receipt_value", "inventory_value"}

DECIMAL_OVERRIDES = {
    "days_of_supply": (12, 2), "avg_daily_demand": (18, 4),
    "demand_cv": (10, 4), "yield_pct": (8, 4), "defect_rate": (10, 5),
    "abs_pct_error": (12, 5), "forecast_accuracy": (12, 5),
    "forecast_bias_pct": (12, 5), "discount_pct": (8, 4),
    "weight_kg": (12, 3), "volume_m3": (12, 4),
    "distance_km": (12, 1), "base_cost_per_km": (12, 4),
    "actual_lead_time_days": (10, 1), "on_time_rate": (10, 4),
    "avg_transit_days": (10, 2), "quality_score": (7, 2),
    "demand_share": (12, 8), "forecast_error": (18, 3),
}

PRIMARY_KEYS = {
    "dim_date": "date_key", "dim_product": "product_id",
    "dim_supplier": "supplier_id", "dim_location": "location_id",
    "dim_customer": "customer_id", "dim_carrier": "carrier_id",
    "dim_employee": "employee_id", "dim_region": "region_id",
    "dim_product_category": "product_category_id",
    "fact_purchase_order": "po_line_id",
    "fact_supplier_delivery": "delivery_id",
    "fact_production": "production_id",
    "fact_sales_order_line": "order_line_id",
    "fact_shipment": "shipment_id",
}

# The remaining facts are at composite grain and carry no surrogate key:
#   fact_inventory_snapshot   snapshot_date x snapshot_grain x product x location
#   fact_demand_signal        week x product x region
#   fact_forecast             month x product x region x version x horizon
#   fact_supply_chain_risk    month x entity_type x entity_id
#   fact_financial_impact     month x cost_category

CLUSTER_KEYS = {
    "fact_inventory_snapshot": ["year_month_key", "product_id"],
    "fact_forecast": ["year_month_key", "product_id"],
    "fact_demand_signal": ["year_month_key", "product_id"],
    "fact_purchase_order": ["year_month_key", "supplier_id"],
    "fact_supplier_delivery": ["year_month_key", "supplier_id"],
    "fact_sales_order_line": ["year_month_key", "product_id"],
    "fact_shipment": ["year_month_key", "carrier_id"],
    "fact_production": ["year_month_key", "product_id"],
    "fact_supply_chain_risk": ["year_month_key"],
}


def _num(dialect: str, p: int, s: int) -> str:
    return f"{'NUMBER' if dialect == 'snowflake' else 'DECIMAL'}({p},{s})"


def sql_type(col: str, dtype, dialect: str) -> str:
    name = str(dtype)
    if name.startswith(("int", "uint")):
        width = int("".join(c for c in name if c.isdigit()) or 64)
        if width <= 16:
            return "SMALLINT"
        return "INT" if width <= 32 else "BIGINT"
    if name.startswith("bool"):
        return "BOOLEAN"
    if name.startswith(("datetime", "timestamp")):
        # No timezones and no timestamps where a date will do -- every temporal
        # column in this dataset is a calendar date.
        return "DATE" if col.endswith("_date") else (
            "TIMESTAMP_NTZ" if dialect == "snowflake" else "TIMESTAMP")
    if name.startswith("float") or name == "double":
        if col in DECIMAL_OVERRIDES:
            return _num(dialect, *DECIMAL_OVERRIDES[col])
        if col in MONEY_EXACT or col.endswith(MONEY_SUFFIXES):
            return _num(dialect, 18, 2)
        if col.endswith(QTY_SUFFIXES):
            return _num(dialect, 18, 3)
        if col.endswith(RATIO_SUFFIXES):
            return _num(dialect, 12, 6)
        return _num(dialect, 18, 4)
    return "OBJECT"


def resolve_object(series: pd.Series) -> str:
    non_null = series.dropna()
    if len(non_null) and hasattr(non_null.iloc[0], "isoformat"):
        return "DATE"
    width = int(non_null.astype(str).str.len().max()) if len(non_null) else 16
    return f"VARCHAR({max(16, min(int(width * 1.5) + 8, 1000))})"


def build_schema(data_dir: Path, dialect: str) -> dict[str, list[tuple[str, str]]]:
    out = {}
    for path in sorted(data_dir.glob("*.parquet")):
        head = pd.read_parquet(path).head(2000)
        cols = []
        for col in head.columns:
            t = sql_type(col, head[col].dtype, dialect)
            if t == "OBJECT":
                t = resolve_object(head[col])
            cols.append((col, t))
        out[path.stem] = cols
    return out


def _table_body(cols) -> str:
    width = max(len(c) for c, _ in cols) + 2
    return ",\n".join(f"    {c:<{width}}{t}" for c, t in cols)


HEADER = "-- Meridian Global Industries | Supply Chain Control Tower"
SANITY = [
    "-- Sanity check: the executive KPI row. Note the snapshot_grain filter --",
    "-- fact_inventory_snapshot holds weekly history AND a daily recent window,",
    "-- and summing across both grains double-counts every inventory measure.",
    "SELECT ROUND(AVG(daily_value) / 1e6, 1) AS inventory_musd,",
    "       ROUND(AVG(stockout) * 100, 1)    AS stockout_pct",
    "FROM  (SELECT snapshot_date,",
    "              SUM(inventory_value) AS daily_value,",
    "              AVG(CAST(stockout_flag AS DOUBLE)) AS stockout",
    "       FROM   fact_inventory_snapshot",
    "       WHERE  snapshot_grain = 'D'",
    "       GROUP  BY snapshot_date) t;",
]


def emit_snowflake(schema: dict, out_dir: Path, tier: str) -> None:
    cat, sch = CATALOG.upper(), SCHEMA.upper()
    L = [HEADER, "-- Snowflake DDL. Generated by src/emit_ddl.py - do not hand-edit.",
         "", f"CREATE DATABASE IF NOT EXISTS {cat};",
         f"CREATE SCHEMA   IF NOT EXISTS {cat}.{sch};",
         f"USE SCHEMA {cat}.{sch};", ""]
    for table, cols in schema.items():
        L.append(f"CREATE OR REPLACE TABLE {table} (\n{_table_body(cols)}\n)")
        if table in CLUSTER_KEYS:
            L[-1] += f"\nCLUSTER BY ({', '.join(CLUSTER_KEYS[table])})"
        L[-1] += ";"
        if table in PRIMARY_KEYS:
            L.append(f"ALTER TABLE {table} ADD PRIMARY KEY ({PRIMARY_KEYS[table]});")
        L.append("")
    (out_dir / "01_ddl.sql").write_text("\n".join(L))

    ld = [HEADER, "-- Load parquet into Snowflake.", "",
          f"USE SCHEMA {cat}.{sch};", "",
          "CREATE OR REPLACE FILE FORMAT mgi_parquet TYPE = PARQUET;",
          "CREATE OR REPLACE STAGE mgi_stage FILE_FORMAT = mgi_parquet;", "",
          f"-- From a local machine (SnowSQL only), for the '{tier}' tier:",
          f"--   PUT file://<abs-path>/data/{tier}/*.parquet @mgi_stage "
          "AUTO_COMPRESS=FALSE;",
          "-- Or point the stage at your own S3/Azure/GCS location instead.", ""]
    for table in schema:
        ld += [f"COPY INTO {table}",
               f"  FROM @mgi_stage/{table}.parquet",
               "  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)",
               "  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE",
               "  ON_ERROR = ABORT_STATEMENT;", ""]
    ld += SANITY
    (out_dir / "02_load.sql").write_text("\n".join(ld))


def emit_databricks(schema: dict, out_dir: Path, tier: str) -> None:
    L = [HEADER, "-- Databricks (Unity Catalog) DDL. Generated by src/emit_ddl.py.",
         "", f"CREATE CATALOG IF NOT EXISTS {CATALOG};",
         f"CREATE SCHEMA  IF NOT EXISTS {CATALOG}.{SCHEMA};",
         f"USE {CATALOG}.{SCHEMA};", ""]
    for table, cols in schema.items():
        L.append(f"CREATE OR REPLACE TABLE {table} (\n{_table_body(cols)}\n)\nUSING DELTA")
        if table in CLUSTER_KEYS:
            L[-1] += f"\nCLUSTER BY ({', '.join(CLUSTER_KEYS[table])})"
        L[-1] += ";"
        if table in PRIMARY_KEYS:
            pk = PRIMARY_KEYS[table]
            L.append(f"ALTER TABLE {table} ALTER COLUMN {pk} SET NOT NULL;")
            L.append(f"ALTER TABLE {table} ADD CONSTRAINT pk_{table} PRIMARY KEY ({pk});")
        L.append("")
    (out_dir / "01_ddl.sql").write_text("\n".join(L))

    py = f'''"""Load the Meridian parquet files into Unity Catalog.

Run as a Databricks notebook or with databricks-connect. Upload the parquet
directory to a volume first, e.g.:

    databricks fs cp -r data/{tier} dbfs:/Volumes/{CATALOG}/{SCHEMA}/raw/
"""

CATALOG = "{CATALOG}"
SCHEMA = "{SCHEMA}"
SOURCE = "/Volumes/{CATALOG}/{SCHEMA}/raw"        # adjust to your volume

TABLES = {list(schema)!r}

spark.sql(f"CREATE CATALOG IF NOT EXISTS {{CATALOG}}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{CATALOG}}.{{SCHEMA}}")

for table in TABLES:
    df = spark.read.parquet(f"{{SOURCE}}/{{table}}.parquet")
    (df.write
       .mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(f"{{CATALOG}}.{{SCHEMA}}.{{table}}"))
    print(f"loaded {{table}}: {{df.count():,}} rows")

# Liquid clustering on the tables that carry the analytical load.
for table, keys in {CLUSTER_KEYS!r}.items():
    spark.sql(f"ALTER TABLE {{CATALOG}}.{{SCHEMA}}.{{table}} "
              f"CLUSTER BY ({{', '.join(keys)}})")

# The snapshot_grain filter is not optional: the table holds weekly history
# AND a daily recent window, so summing across both double-counts inventory.
spark.sql(f"""
    SELECT ROUND(AVG(daily_value) / 1e6, 1) AS inventory_musd,
           ROUND(AVG(stockout) * 100, 1)    AS stockout_pct
    FROM  (SELECT snapshot_date,
                  SUM(inventory_value)               AS daily_value,
                  AVG(CAST(stockout_flag AS DOUBLE)) AS stockout
           FROM   {{CATALOG}}.{{SCHEMA}}.fact_inventory_snapshot
           WHERE  snapshot_grain = 'D'
           GROUP  BY snapshot_date) t
""").show()
'''
    (out_dir / "02_load.py").write_text(py)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="full", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)

    data_dir = Path(args.data) if args.data else PROJECT_ROOT / "data" / args.tier
    if not data_dir.exists():
        print(f"no data at {data_dir}; run generate.py first")
        return 2

    for dialect, emit in (("snowflake", emit_snowflake), ("databricks", emit_databricks)):
        out_dir = PROJECT_ROOT / "sql" / dialect
        out_dir.mkdir(parents=True, exist_ok=True)
        emit(build_schema(data_dir, dialect), out_dir, args.tier)
        print(f"  wrote sql/{dialect}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
