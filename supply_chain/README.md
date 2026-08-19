# Meridian Global Industries — Supply Chain Control Tower

A scenario-driven synthetic dataset for supply-chain analytics demos, built to
work unchanged in **Tableau, Power BI, Snowflake and Databricks**.

One dataset, 19 tables, 15 planted events, 30 demo questions. Not a
random-number generator: the business events that make the demo worth watching
are *configured*, and a validator proves they are actually visible in the data
before you present it.

---

## Quick start

```bash
python3 src/generate.py --tier small
```

```bash
python3 src/validate.py --tier small
```

That writes 19 parquet files to `data/small/` (~74 MB) in about 3 seconds, then
runs 44 assertions about integrity and story visibility.

For the full-size dataset (8.6M rows, ~213 MB, ~10 seconds):

```bash
python3 src/generate.py --tier full
```

Then emit DDL and load scripts for Snowflake and Databricks:

```bash
python3 src/emit_ddl.py --tier full
```

And run the 30 demo questions against the data:

```bash
python3 src/run_questions.py --tier small
```

Requirements: Python 3.11+, `pandas`, `numpy`, `pyarrow`, `pyyaml`.
`duckdb` additionally for `run_questions.py`.

---

## What is in it

**Meridian Global Industries**, a fictional global manufacturer/distributor.
All brands, products, customers, suppliers and place-names are invented —
nothing here uses a real trademark, so it is safe to show to customers.

- **Period:** 2 full years of history plus the current incomplete year, with a
  12-month forecast horizon beyond it.
- **Anchoring:** the calendar is anchored to *today* by default, so the demo
  never goes stale. Regenerate next year and "this year" is still this year.
- **Two tiers:** `small` for laptop Tableau/Power BI Desktop work, `full` for
  Snowflake and Databricks. Same seed, same events, same story.

The headline the data currently tells:

> Inventory **+12.8%** YoY. Fill rate **96.9%**. OTIF **90.1%**.
> Stockout rate **3.4%**. Forecast accuracy **87.4%**.

Inventory is up and service has not improved. That divergence is the point —
every demo flow is a different way of answering *why*.

---

## Layout

```
config/scenario_base.yaml    every knob; copy it to build variants
src/
  generate.py                entry point; orchestrates and writes
  validate.py                integrity + story-visibility checks
  emit_ddl.py                platform DDL from the actual parquet schemas
  run_questions.py           runs the 30 demo questions via DuckDB
  mgiconfig.py               config loading + calendar anchoring
  dim_date.py                calendar: Gregorian + fiscal + NRF 4-5-4
  reference.py               taxonomy, geography, name pools
  dims.py                    dimension builders
  events.py                  the 15 planted events, as multiplier matrices
  demand.py                  demand signal + ABC/XYZ derivation
  facts_inbound.py           purchase orders, deliveries, production
  facts_inventory.py         daily balance simulation, mixed-grain output
  facts_outbound.py          sales order lines, shipments
  facts_forecast.py          four forecast versions
  derived.py                 scorecards, risk layer, financial impact
sql/demo_questions.sql       the 30 questions as runnable SQL
sql/snowflake/               01_ddl.sql, 02_load.sql
sql/databricks/              01_ddl.sql, 02_load.py
docs/DATA_MODEL.md           schema, grain decisions, KPI definitions
docs/EVENTS.md               the 15 events and their expected magnitudes
docs/DEMO_FLOWS.md           the scripted flow and the 30 questions
data/small/, data/full/      generated output (parquet)
```

---

## The 15 planted events

Configured in `config/scenario_base.yaml` under `events:`. Timing is expressed
as **offsets in months relative to the as-of date**, not absolute dates, so the
narrative stays correct whenever you regenerate. Full detail and the expected
magnitude of each is in [docs/EVENTS.md](docs/EVENTS.md).

| # | Event | What it creates |
|---|---|---|
| 1 | Supplier disruption | SUP-104 lead time 18 → 29d, on-time 95% → 71% |
| 2 | Demand spike | SmartHome +28%, forecast error up, expediting doubles |
| 3 | Excess inventory | 230 C-class SKUs over-forecast 35%; turns fall |
| 4 | Carrier degradation | C-07 in the Northeast only — 79% on-time vs 90% |
| 5 | Quality failure | SUP-137 defect rate 1.5% → 7.0% |
| 6 | Port disruption | APAC inbound +12 days transit |
| 7 | Forecast model failure | Industrial Components systematically under-forecast |
| 8 | Safety-stock policy change | +40% on 300 A-class SKUs — **net-negative by design** |
| 9 | Product substitution | Nimbus N3 → N4; excess of one, shortage of the other |
| 10 | Single-source risk | 22 critical SKUs single-sourced, 6 on the disrupted supplier |
| 11 | Cost inflation | Raw Materials +18% over four quarterly steps |
| 12 | New DC ramp | Phoenix opens; West fill rate dips then recovers |
| 13 | Labour shortage | Two DCs at 70% pick capacity |
| 14 | Obsolescence | 60 end-of-life SKUs hold stock against vanishing demand |
| 15 | Planner overrides | Help 90 SKUs, **hurt 30** — not uniformly good |

Set any event's `enabled: false` to remove that story from the data entirely.
Change its numbers to change its severity.

---

## Why the validator matters

Synthetic noise routinely swamps a planted signal, and the usual way to find
that out is live, in front of an audience. `validate.py` runs two families of
check:

**Integrity** — foreign keys resolve, no negative stock or money, received
never exceeds ordered, OTIF really is on-time *and* in-full, and the inventory
balance equation closes to 0.01 units across every SKU × location series.

**Narrative** — each enabled event is visible *at the magnitude the config
claims*. SUP-104's on-time really is near 71% during the disruption window;
SUP-137's defect rate really does reach 7%; C-07 really is worse in the
Northeast than elsewhere and than other carriers there.

Current status: **42/44 on the small tier, 40/42 on full.**

### Known gaps

Two things are worth knowing before you present this.

**Event scope is specified as absolute SKU counts, so it does not scale between
tiers.** `affected_sku_count: 300` is half the small catalogue but a fifth of
the full one, so Events 3 and 8 carry the inventory build at small tier and
barely register at full. The two tiers consequently fail *different* checks —
small misses `stockout rate` (3.4% against a 4.1–5.5% target) and
`on-time during` (65.4% against 68–74%); full misses `lead time during` and
`inventory YoY`. The fix is to express those counts as fractions of the
catalogue rather than absolute numbers.

**The small tier is the tuned one.** Demo on `small`, or re-tune before
demoing on `full`.

---

## Conventions

Inherited from the sibling ApexTech sales dataset: lowercase `snake_case`, no
reserved-word column names, `DECIMAL(18,2)` money, `0/1` integer booleans, ISO
dates, and no NULL foreign keys — a SKU with no alternate supplier carries
`secondary_supplier_id = 0`, which resolves to a real "No Alternate Supplier"
row. See [docs/DATA_MODEL.md](docs/DATA_MODEL.md) §8 for what differs.

Three things specific to this dataset are easy to get wrong:

**`fact_inventory_snapshot` carries mixed grain.** Weekly for history, daily for
the trailing 90 days, distinguished by `snapshot_grain`. Any measure summed
across both grains is wrong. Every query in `sql/demo_questions.sql` filters it.

**Lateness is always `actual − promised`, never `actual − requested`.** A
supplier that always promises late but delivers on its promise is a *planning*
problem, not a supplier problem, and the data lets you discover that.

**Supplier names are deliberately dirty.** `supplier_name_raw` on the
transaction facts carries up to five spellings per supplier while
`supplier_master_id` stays clean. Grouping on the raw name splits SUP-104's 224
late deliveries into five unremarkable rows. That is the data-quality demo, and
it is question 30.
