# Vantage Industrial — Order-to-Cash Control Tower

A scenario-driven synthetic dataset for enterprise analytics demos, built to work
unchanged in **Tableau, Power BI, Databricks and Snowflake**.

One dataset, 31 tables, 9 demo flows, 30 questions. Not a random-number CSV
generator: the business events that make the demos worth watching are
*configured*, and a validator proves they are actually visible in the data —
and that the money adds up — before you present.

---

## Quick start

```bash
python3 src/generate.py --tier small
```

```bash
python3 src/validate.py --tier small
```

That writes 31 parquet + 31 CSV files to `data/small/` (~35 MB parquet) in about
7 seconds, then checks 75 assertions about integrity, the AR ledger, the
waterfall and story visibility.

For the full-size dataset (3.7M rows, ~129 MB parquet, ~12 seconds):

```bash
python3 src/generate.py --tier full --formats parquet
```

Then emit DDL and load scripts for Snowflake and Databricks:

```bash
python3 src/emit_ddl.py --tier full
```

And prove the demo questions answer:

```bash
python3 src/run_questions.py --tier small
```

Requirements: Python 3.11+, `pandas`, `numpy`, `pyarrow`, `pyyaml`. `duckdb` for
`run_questions.py`.

---

## What is in it

**Vantage Industrial**, a fictional global industrial distributor — power
transmission, fluid handling, electrical, bearings, safety, tools. All customers,
products, carriers and staff are invented; nothing here uses a real trademark, so
it is safe to show to a customer.

- **Period:** 3 full years of history plus the current year to date — 43 months.
- **Anchoring:** the calendar is anchored to *today* by default, so the demo never
  goes stale. As-of is the last day of the previous complete month, and every
  planted event is timed in months relative to it.
- **Scale:** two tiers from one seed. `small` for Tableau / Power BI Desktop,
  `full` for Snowflake / Databricks / Incorta. Same events, same story.
- **Chain:** quote → order → fulfilment → shipment → invoice → payment, with every
  link keyed so a single transaction can be followed end to end.

### The headline it produces

```
Bookings TTM   Collected     Open AR      Overdue AR    DSO      Perfect order
$128.4M        $88.1M        $21.6M       $8.3M         52 days  45.9%
+10.1% YoY                                38% of AR              -11pt over 3 years

9,521 open O2C exceptions blocking $21.7M
```

and the cohort waterfall that explains the gap:

```
Booked $128.4M
  - $2.5M  cancelled                LOST
  - $7.4M  not yet shipped          AT RISK
  - $1.9M  in transit               TIMING
  - $7.5M  delivered, not invoiced  LEAKAGE
  - $3.7M  credits and returns      LOST
  - $17.4M open AR on the cohort    TIMING
  = $88.1M collected
```

$6.2M is gone. $7.5M was never billed. The rest is still moving. That split is
what makes this a diagnosis rather than a complaint — see
[docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) §1.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | all 31 tables, grains, keys, hierarchies, and what is deliberately absent |
| [docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) | every definition two people could disagree about — read this first |
| [docs/EVENTS.md](docs/EVENTS.md) | the 15 planted events, their measured magnitudes, and three places the design note's numbers do not survive the arithmetic |
| [docs/DEMO_FLOWS.md](docs/DEMO_FLOWS.md) | the 15-minute run plus 8 follow-up flows, with the numbers each one lands on |
| [PLAN.md](PLAN.md) | the review of the original design note, and the build plan |

---

## What makes it different from a random data generator

**The events are causal, not stamped on.** Six of the fifteen emerge from the
simulation rather than being tagged onto pre-chosen rows. Backorders come from
order lines consuming a finite monthly supply, first come first served. Credit
holds come from a running exposure ledger evaluated at order entry. Disputes are
generated *from* the price variance that caused them. Slice any of them by a cut
nobody rehearsed and they still hold.

**The money reconciles.** `fact_payment_allocation` is the only source of truth
for what has been paid; invoice status, AR balance and the ageing matrix are all
derived from it and never drawn. `validate.py` asserts the ageing buckets equal
the ledger equals the tile, to the cent, and that the booking waterfall closes to
under a dollar on $128M.

**Two chains are built on purpose.** Warehouse bottleneck → backorders →
expedited freight. Pricing leakage → customer disputes. The root-cause scene has
something real underneath it.

**Everything is a knob.** `config/scenario_base.yaml` holds every parameter and
all fifteen events. Copy it, change values, regenerate — referential integrity
and business logic are preserved automatically:

```bash
python3 src/generate.py --scenario config/my_scenario.yaml --tier full
```

Setting an event's `enabled: false` removes that story from the data entirely,
which is what you want when a prospect's own pain point would compete with it.

---

## Layout

```
config/scenario_base.yaml   every knob, including all 15 event definitions
src/
  generate.py               entry point
  validate.py               integrity + ledger + waterfall + narrative checks
  emit_ddl.py               DDL from the actual parquet schemas
  run_questions.py          runs the 30 demo questions via DuckDB
  o2cconfig.py              config load + calendar anchoring
  dim_date.py               calendar, fiscal, business-day index
  reference.py              geography, taxonomies, name banks
  customers.py              hierarchy, sites, credit limits, behaviour
  products.py               catalogue and the product hierarchy
  pricing.py                contract pricing, and the one place a line is priced
  quotes.py                 quote generation, win/loss, conversion
  orders.py                 order booking and the credit-exposure ledger
  fulfillment.py            ATP allocation, backorders, the pick queue
  shipping.py               shipments, carriers, the delivery event trail
  billing.py                billing rules, invoices, price variance, duplicates
  receivables.py            cash application, disputes, credit memos, returns
  snapshots.py              the AR ledger, monthly ageing, credit exposure
  derived.py                the O2C cycle and the exception centre
  events.py                 the 15 events, resolved once into concrete targets
sql/demo_questions.sql      the 30 questions as runnable SQL
sql/snowflake/  sql/databricks/
docs/                       DATA_MODEL, KPI_DEFINITIONS, EVENTS, DEMO_FLOWS
data/small/  data/full/     generated output (gitignored)
```

---

## Before a demo

```bash
python3 src/generate.py --tier full --formats parquet
python3 src/validate.py --tier full        # 75 assertions
python3 src/run_questions.py --tier full   # 30 questions
```

Green on both means every number in [docs/DEMO_FLOWS.md](docs/DEMO_FLOWS.md) is
what the audience will see.
