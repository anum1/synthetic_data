#!/usr/bin/env python3
"""Run the 30 demo questions against a generated tier and print the answers.

The point is that the answers in docs/DEMO_FLOWS.md are MEASURED, not written
from intent. If an event is retuned and a documented answer changes, running
this shows it immediately.

  python3 src/run_questions.py --tier small
  python3 src/run_questions.py --tier small --only 3,4,21
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mgiconfig import PROJECT_ROOT

try:
    import duckdb
except ImportError:
    print("duckdb is required:  pip install duckdb")
    raise SystemExit(2)


def parse(path: Path) -> list[tuple[int, str, str]]:
    """-> [(number, question, sql)]"""
    out = []
    for block in path.read_text().split("\n-- Q"):
        m = re.match(r"(\d+)\s*\|\s*(.+)", block)
        if not m:
            continue
        sql = block[block.index("\n"):].strip()
        sql = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
        out.append((int(m.group(1)), m.group(2).strip(), sql.strip()))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--only", default=None, help="comma list of question numbers")
    ap.add_argument("--rows", type=int, default=8)
    a = ap.parse_args(argv)

    data = PROJECT_ROOT / "data" / a.tier
    files = sorted(data.glob("*.parquet"))
    if not files:
        print(f"no parquet in {data}; run generate.py first")
        return 2

    con = duckdb.connect()
    for f in files:
        con.execute(f"CREATE VIEW {f.stem} AS SELECT * FROM read_parquet('{f}')")

    wanted = {int(x) for x in a.only.split(",")} if a.only else None
    questions = parse(PROJECT_ROOT / "sql" / "demo_questions.sql")
    failed = 0
    for n, q, sql in questions:
        if wanted and n not in wanted:
            continue
        print(f"\n{'=' * 78}\nQ{n} | {q}\n{'=' * 78}")
        try:
            df = con.execute(sql).df()
            print(df.head(a.rows).to_string(index=False) if len(df) else "  (no rows)")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERROR: {exc}")
    print(f"\n{len(questions) - failed}/{len(questions)} questions ran cleanly")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
