#!/usr/bin/env python3
"""Run every demo question and prove it answers.

A question that returns nothing, or something absurd, is worse than no question
at all - it fails live, in front of the audience. This runs all of them against
the generated parquet via DuckDB and reports row counts and timings.

  python3 src/run_questions.py --tier small
  python3 src/run_questions.py --tier full --show 3
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mktconfig import PROJECT_ROOT


def split_questions(sql: str) -> list[tuple[str, str]]:
    """(label, statement) for each question, keyed off the -- Qn. comments."""
    out, label, buf = [], None, []
    for line in sql.splitlines():
        m = re.match(r"^--\s*(Q\d+)\.\s*(.*)$", line.strip())
        if m:
            if label and buf:
                out.append((label, "\n".join(buf)))
            label, buf = f"{m.group(1)} {m.group(2)}", []
            continue
        if line.strip().startswith("--"):
            continue
        if label is not None:
            buf.append(line)
    if label and buf:
        out.append((label, "\n".join(buf)))
    return [(l, s.strip()) for l, s in out if s.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--show", type=int, default=0,
                    help="print this many result rows per question")
    args = ap.parse_args(argv)

    try:
        import duckdb
    except ImportError:
        print("duckdb is required: pip install duckdb")
        return 2

    data = PROJECT_ROOT / "data" / args.tier
    files = sorted(data.glob("*.parquet"))
    if not files:
        print(f"no parquet in {data}; run generate.py first")
        return 2

    con = duckdb.connect()
    for f in files:
        con.execute(f"CREATE VIEW {f.stem} AS "
                    f"SELECT * FROM read_parquet('{f.as_posix()}')")

    sql_path = PROJECT_ROOT / "sql" / "demo_questions.sql"
    questions = split_questions(sql_path.read_text())
    print(f"{len(questions)} questions against data/{args.tier}\n")

    failed = 0
    for label, stmt in questions:
        t0 = time.time()
        try:
            df = con.execute(stmt).fetchdf()
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  [ERROR] {label}\n          {str(exc).splitlines()[0]}")
            continue
        ms = (time.time() - t0) * 1000
        if df.empty:
            failed += 1
            print(f"  [EMPTY] {label}  ({ms:,.0f}ms)")
            continue
        print(f"  [ok]    {label}  -  {len(df):,} rows, {ms:,.0f}ms")
        if args.show:
            print(df.head(args.show).to_string(index=False, max_colwidth=34))
            print()
    print(f"\n{len(questions) - failed}/{len(questions)} questions answered")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
