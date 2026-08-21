#!/usr/bin/env python3
"""Emit Snowflake and Databricks DDL from the parquet schemas actually written.

Generated from the data rather than hand-maintained, so the DDL cannot drift
away from what the generator produces.

  python3 src/emit_ddl.py --tier full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p2pconfig import PROJECT_ROOT

# Keyed on ARROW type names, not numpy ones: pyarrow reports "double" and
# "string", so a table keyed on "float64"/"object" silently falls through to the
# default and every money column is emitted as VARCHAR.
SNOWFLAKE = {"int8": "SMALLINT", "int16": "SMALLINT", "int32": "INTEGER",
             "int64": "BIGINT", "float": "FLOAT", "double": "NUMBER(18,4)",
             "decimal": "NUMBER(18,4)", "bool": "BOOLEAN",
             "date32": "DATE", "date64": "DATE", "timestamp": "TIMESTAMP_NTZ",
             "string": "VARCHAR", "large_string": "VARCHAR"}
DATABRICKS = {"int8": "TINYINT", "int16": "SMALLINT", "int32": "INT",
              "int64": "BIGINT", "float": "FLOAT", "double": "DECIMAL(18,4)",
              "decimal": "DECIMAL(18,4)", "bool": "BOOLEAN",
              "date32": "DATE", "date64": "DATE", "timestamp": "TIMESTAMP",
              "string": "STRING", "large_string": "STRING"}

# Longest key first, so "large_string" is not swallowed by "string" and
# "int64" is not matched by "int8".
def sql_type(arrow_type, mapping: dict) -> str:
    key = str(arrow_type)
    for k in sorted(mapping, key=len, reverse=True):
        if key.startswith(k):
            return mapping[k]
    return mapping["string"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", default="full", choices=["small", "full"])
    ap.add_argument("--schema", default="P2P")
    args = ap.parse_args(argv)

    data = PROJECT_ROOT / "data" / args.tier
    files = sorted(data.glob("*.parquet"))
    if not files:
        print(f"no parquet in {data}; run generate.py --formats parquet first")
        return 2

    for flavour, mapping, out_path in (
            ("Snowflake", SNOWFLAKE, PROJECT_ROOT / "sql" / "snowflake" / "01_ddl.sql"),
            ("Databricks", DATABRICKS,
             PROJECT_ROOT / "sql" / "databricks" / "01_ddl.sql")):
        lines = [f"-- Norvant Group Procure-to-Pay - {flavour} DDL",
                 f"-- Generated from data/{args.tier} by src/emit_ddl.py. Do not edit.",
                 ""]
        if flavour == "Snowflake":
            lines += [f"CREATE SCHEMA IF NOT EXISTS {args.schema};",
                      f"USE SCHEMA {args.schema};", ""]
        else:
            lines += [f"CREATE DATABASE IF NOT EXISTS {args.schema};",
                      f"USE {args.schema};", ""]
        for f in files:
            schema = pq.read_schema(f)
            cols = [f"    {name} {sql_type(schema.field(name).type, mapping)}"
                    for name in schema.names]
            lines.append(f"CREATE OR REPLACE TABLE {f.stem} (")
            lines.append(",\n".join(cols))
            lines.append(");")
            lines.append("")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines))
        print(f"  wrote {out_path.relative_to(PROJECT_ROOT)} ({len(files)} tables)")

    # Load scripts.
    sf = ["-- Load parquet into Snowflake. Stage the data/ folder first:",
          "--   PUT file://data/full/*.parquet @~/p2p AUTO_COMPRESS=FALSE;", ""]
    for f in files:
        sf.append(f"COPY INTO {f.stem} FROM @~/p2p/{f.name} "
                  f"FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = "
                  f"CASE_INSENSITIVE;")
    (PROJECT_ROOT / "sql" / "snowflake" / "02_load.sql").write_text("\n".join(sf))

    db = ['# Load parquet into Databricks. Point BASE at the uploaded folder.',
          'BASE = "dbfs:/FileStore/p2p/full"', 'SCHEMA = "p2p"', "",
          'spark.sql(f"CREATE DATABASE IF NOT EXISTS {SCHEMA}")', ""]
    for f in files:
        db.append(f'spark.read.parquet(f"{{BASE}}/{f.name}")'
                  f'.write.mode("overwrite").saveAsTable(f"{{SCHEMA}}.{f.stem}")')
    (PROJECT_ROOT / "sql" / "databricks" / "02_load.py").write_text("\n".join(db))
    print("  wrote load scripts for both platforms")
    _ = pd
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
