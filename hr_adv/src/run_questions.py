#!/usr/bin/env python3
"""Run the demo questions against the generated data with DuckDB.

Every question in sql/demo_questions.sql is executed and its first rows printed,
so "the dataset can answer this" is a thing you check rather than a thing you
hope. Use it before a demo, and after any change to the generator.

  python3 src/run_questions.py --tier small
  python3 src/run_questions.py --tier small --only 16,17,18
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hrconfig import PROJECT_ROOT

QUESTION_RE = re.compile(r"^--\s*Q(\d+)[.:]\s*(.+)$", re.MULTILINE)


def parse(path: Path) -> list[tuple[int, str, str]]:
    text = path.read_text()
    marks = list(QUESTION_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end].strip()
        body = "\n".join(l for l in body.splitlines()
                         if not l.strip().startswith("-- #"))
        out.append((int(m.group(1)), m.group(2).strip(), body.strip()))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--sql", default=str(PROJECT_ROOT / "sql" / "demo_questions.sql"))
    ap.add_argument("--only", default=None, help="comma list of question numbers")
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--quiet", action="store_true", help="pass/fail only")
    args = ap.parse_args(argv)

    try:
        import duckdb
    except ImportError:
        print("duckdb is required: pip install duckdb")
        return 2

    data = PROJECT_ROOT / "data" / args.tier
    if not data.exists():
        print(f"no data at {data}; run generate.py first")
        return 2

    con = duckdb.connect()
    for f in sorted(data.glob("*.parquet")):
        con.execute(f"CREATE VIEW {f.stem} AS SELECT * FROM read_parquet('{f}')")

    wanted = ({int(x) for x in args.only.split(",")} if args.only else None)
    questions = parse(Path(args.sql))
    failed, empty = [], []
    for num, title, sql in questions:
        if wanted and num not in wanted:
            continue
        try:
            df = con.execute(sql).fetchdf()
        except Exception as exc:                      # noqa: BLE001
            failed.append((num, title, str(exc).splitlines()[0]))
            print(f"\nQ{num:02d}  {title}\n  ERROR: {str(exc).splitlines()[0]}")
            continue
        if df.empty:
            empty.append((num, title))
        if not args.quiet:
            print(f"\nQ{num:02d}  {title}")
            print("  " + df.head(args.rows).to_string(index=False).replace("\n", "\n  "))
        elif df.empty:
            print(f"Q{num:02d}  {title}  -> EMPTY")

    total = len(wanted) if wanted else len(questions)
    print(f"\n{total - len(failed) - len(empty)}/{total} questions returned rows"
          f"  ({len(failed)} errored, {len(empty)} empty)")
    for num, title, err in failed:
        print(f"  ERROR Q{num}: {err}")
    for num, title in empty:
        print(f"  EMPTY Q{num}: {title}")
    return 1 if failed or empty else 0


if __name__ == "__main__":
    raise SystemExit(main())
