# ApexTech — Enterprise Sales & Profitability 360

A scenario-driven synthetic dataset for enterprise analytics demos, built to
work unchanged in **Tableau, Power BI, Databricks (+ Databricks Dashboards)
and Snowflake**.

One dataset, 20 tables, 15 demo flows. Not a random-number CSV generator: the
business events that make the demos worth watching are *configured*, and a
validator proves they are actually visible in the data before you present it.

---

## Quick start

```bash
python3 src/generate.py --tier small
```

```bash
python3 src/validate.py --tier small
```

That writes 20 parquet + 20 CSV files to `data/small/` (~51 MB parquet) in
about 8 seconds, then checks 58 assertions about integrity and story visibility.

For the full-size dataset (3M order lines, ~370 MB parquet, ~10 seconds):

```bash
python3 src/generate.py --tier full --formats parquet
```

Then emit DDL and load scripts for Snowflake and Databricks:

```bash
python3 src/emit_ddl.py --tier full
```

Requirements: Python 3.11+, `pandas`, `numpy`, `pyarrow`, `pyyaml`.

---

## What is in it

**ApexTech**, a fictional global technology retailer/manufacturer. All brands,
products, customers and suppliers are invented — nothing here uses a real
trademark, so it is safe to show to customers.

- **Period:** 2 full years of history plus the current incomplete year, with a
  16-month budget/forecast horizon beyond it.
- **Anchoring:** the calendar is anchored to *today* by default, so the demo
  never goes stale. Regenerate next year and "this year" is still this year.
- **Two tiers:** `small` (300K lines) for laptop Tableau/Power BI Desktop work,
  `full` (3M lines) for Snowflake and Databricks. Same seed, same events, same
  story.

The current headline the data tells:

> Revenue **+10.1%** YoY. Gross profit **−7.3%**. Margin **21.1% → 17.8%**.
> Europe is the largest profit decline of **$18.2M**.

That divergence is the whole point — every demo flow is a different way of
answering *why*.

---

## Layout

```
config/scenario_base.yaml    every knob; copy it to build variants
src/
  generate.py                entry point; orchestrates and writes
  apexconfig.py              config loading + calendar anchoring
  dim_date.py                calendar: Gregorian + fiscal + NRF 4-5-4
  dims.py                    all other dimensions
  facts.py                   orders and order lines
  facts_support.py           returns, inventory, budget, forecast, scorecards
  events.py                  the planted business events
  validate.py                integrity + story-visibility checks
  emit_ddl.py                platform DDL from the actual parquet schemas
  catalog.py, geography.py   product taxonomy and geography reference data
sql/snowflake/               01_ddl.sql, 02_load.sql
sql/databricks/              01_ddl.sql, 02_load.py
docs/DATA_MODEL.md           schema, hierarchies, cross-platform conventions
docs/DEMO_FLOWS.md           the 15 flows and the executive story
data/small/, data/full/      generated output (parquet, + CSV for small)
```

---

## The ten planted events

Configured in `config/scenario_base.yaml` under `events:`. Timing is expressed
as **offsets in months relative to the as-of date**, not absolute dates, so the
narrative stays correct whenever you regenerate.

| # | Event | When | What it creates |
|---|---|---|---|
| 1 | Supplier cost shock | as-of −3 | Global Components +12% unit cost; revenue holds, margin erodes |
| 2 | Promotion overreach | −2 to −1 | Electronics units +40%, discount +6 pts, margin −10 pts |
| 3 | New product launch | −2 | Nimbus Air N4 launches; N3 cannibalised by 26 pts vs peers |
| 4 | Regional erosion | −4 to 0 | Europe becomes the largest profit decline |
| 5 | Customer contraction | −2 onward | GlobalTech Corp (~4% of revenue) orders −26% |
| 6 | Inventory shortage | −1 to 0 | 6 laptop SKUs hit 42% stockout; days of supply 32 → 9 |
| 7 | Quality failure | −1 onward | Return rate 2.0% → 5.6%, defect rate 2.1% → 9.2% |
| 8 | Sales anomaly | 0 | One $2.8M order at 55× the 99.9th percentile |
| 9 | Forecast deterioration | +1 | Latest Forecast −$7.1M profit vs original budget |
| 10 | Recovery scenario | +3 | Modelled actions return +$5.1M |

Set any event's `enabled: false` to remove that story from the data entirely.
Change its numbers to change its severity. Referential integrity and business
logic are preserved automatically.

---

## Why the validator matters

Synthetic noise routinely swamps a planted signal, and the usual way to find
that out is live, in front of an audience. `validate.py` runs two families of
check:

- **Integrity** — foreign keys resolve (including the conformed plan keys on
  budget and forecast), order headers tie to their lines to the cent, no
  negative money, no sales before a product's launch date, no actuals after the
  as-of date, no forecast rows in the past.
- **Narrative** — every enabled event is measurably visible. Not just "the
  number moved", but moved *against a control*: the shocked supplier group's
  per-product unit cost rises 14% while unshocked suppliers stay within 0.1%;
  the cannibalised product falls while peer products in the same subcategory
  and the same promotion rise.

Both tiers currently pass 58/58.

---

## Loading into each platform

**Tableau / Power BI Desktop** — point at `data/small/`. Use parquet if your
version supports it, CSV otherwise. The small tier is sized so Desktop stays
responsive. Build relationships on the `_id` columns; use the `level` columns
for drill-down hierarchies.

**Snowflake** — run `sql/snowflake/01_ddl.sql`, then `02_load.sql`. The load
script stages from a local `PUT` (SnowSQL) or your own cloud storage.

**Databricks** — run `sql/databricks/01_ddl.sql`, then `02_load.py` as a
notebook. Tables are Delta with liquid clustering on the analytical keys.

Both DDL files are **generated from the parquet schemas** by `emit_ddl.py`, so
they cannot drift from what the generator produces. Regenerate them whenever
you change the schema.

---

## Building your own scenario

```bash
cp config/scenario_base.yaml config/pessimistic.yaml
```

Edit the knobs, then:

```bash
python3 src/generate.py --scenario config/pessimistic.yaml --tier small
```

Always run the validator afterwards — it is the fastest way to find out whether
the story you configured actually landed. See `docs/DEMO_FLOWS.md` for a table
of common tweaks.
