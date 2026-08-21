# Norvant Group — Procure-to-Pay Control Tower

A scenario-driven synthetic dataset for enterprise analytics demos, built to work
unchanged in **Tableau, Power BI, Databricks and Snowflake**.

One dataset, 44 tables, 18 planted business events, 25 demo questions. Not a
random-number CSV generator: the events that make the demo worth watching are
*configured*, and a validator proves they are actually visible in the data — and
that the money adds up — before you present.

---

## Quick start

```bash
python3 src/generate.py --tier small
```

```bash
python3 src/validate.py --tier small
```

That writes 44 parquet + 44 CSV files to `data/small/` in about 7 seconds, then
runs 50 assertions about integrity, the AP subledger, the commitment waterfall
and story visibility.

For the full-size dataset (3.9M rows, ~26 seconds):

```bash
python3 src/generate.py --tier full --formats parquet
```

Then emit DDL and load scripts for Snowflake and Databricks:

```bash
python3 src/emit_ddl.py --tier full
```

And prove the demo questions answer:

```bash
python3 src/run_questions.py --tier full
```

Requirements: Python 3.11+, `pandas`, `numpy`, `pyarrow`, `pyyaml`. `duckdb` for
`run_questions.py`.

---

## What is in it

**Norvant Group**, a fictional diversified manufacturer — direct materials plus
IT, facilities, professional services, logistics and travel. Every supplier,
employee, item and tax identifier is invented; nothing here uses a real
trademark, so it is safe to show to a customer.

- **Period:** 3 full years of history plus the current year to date — 43 months.
- **Anchoring:** the calendar is anchored to *today* by default, so the demo
  never goes stale. As-of is the last day of the previous complete month, and
  every planted event is timed in months relative to it.
- **Scale:** two tiers from one seed. `small` for Tableau / Power BI Desktop,
  `full` for Snowflake / Databricks / Incorta. Same events, same story.
- **Chain:** requisition → PO → receipt → invoice → match → payment, with every
  link keyed so a single transaction can be followed end to end.

### The headline it produces

```
Total spend TTM   Open payables   Overdue      GR/IR accrual   Maverick
$282.2M           $36.1M          $11.0M       $15.3M          $13.8M
+15.1% YoY                        30% of AP    75% aged >90d   4.9% of spend

First-pass match   STP rate    Exception rate   Req-to-cash
92.3%              66.1%       15.7%            74.6 days

32,165 open P2P exceptions blocking $77.8M
```

and the commitment-to-cash waterfall that explains where the money is:

```
PO commitment raised (TTM, gross)      $235.5M
  - Cancelled / closed short             -$8.0M   RELEASED
  - Not yet received                    -$15.3M   IN FLIGHT
  = Received (three-way lines)          $136.6M
  - Received, never invoiced (GR/IR)    -$15.3M   ACCRUAL  <- 75% aged >90d
  = Invoiced                            $124.3M
```

Total spend reconciles across all three channels, which is what makes the
headline defensible:

```
PO-backed invoiced    $206.1M
Non-PO invoiced        $44.0M   <- of which $13.8M had a contract: MAVERICK
P-card / expense       $32.0M
= Total spend TTM     $282.2M
```

---

## The document funnel widens — and that is the story

```
                      ┌── PO invoices ──┐
Requisitions -> POs                      ├──> Pay runs
                      └── Non-PO invoices┘
```

More invoices arrive than purchase orders are raised, for three reasons the demo
names out loud: a sixth of spend has no PO at all, blanket and milestone POs are
invoiced several times, and service lines are two-way matched with no receipt.
Say it in the first thirty seconds and it becomes the best scene in the demo;
leave it unlabelled and an AP audience notices in about four seconds.

---

## Repository layout

```
config/scenario_base.yaml   every knob, including all 18 event definitions
src/
  generate.py               entry point
  validate.py               integrity + subledger + waterfall + narrative
  emit_ddl.py               DDL from the actual parquet schemas
  run_questions.py          runs the demo questions via DuckDB
  p2pconfig.py              config load + calendar anchoring
  dim_date.py               calendar dimension
  reference.py              invented name and hierarchy pools
  orgs.py                   entities, departments, cost centres, people, DOA
  suppliers.py              hierarchy, sites, banks, duplicates, risk
  catalog.py                categories, items, GL accounts
  dims.py                   terms, currency, FX, hold reasons, tolerances
  contracts.py              supplier coverage, contracts, contract prices
  requisitions.py           demand, sourcing suggestion, approval routing
  purchasing.py             req->PO conversion, price drift, splitting
  receiving.py              lead times, partial/over/short, open commitment
  invoicing.py              PO and non-PO invoices, duplicates, GR/IR, FX
  matching.py               tolerance engine, hold ledger, invoice approval
  payments.py               pay runs, discount capture, applications
  pcard.py                  the card channel
  snapshots.py              AP ageing, open commitment and GR/IR by month
  derived.py                spend, budget, P2P cycle, exception centre
  events.py                 the 18 planted events as resolved targets
sql/demo_questions.sql      the 25 questions as runnable SQL
sql/snowflake/  sql/databricks/
docs/DATA_MODEL.md  EVENTS.md  DEMO_FLOWS.md  KPI_DEFINITIONS.md
data/small/  data/full/
```

`PLAN.md` is the review of the original design note and the build plan it was
built from; where this README and the docs disagree with it, they are
authoritative.

---

## Changing the story

Every event is a config block. To make the price drift more dramatic:

```yaml
events:
  contract_price_drift:
    supplier_count: 14
    drift_pct_range: [0.06, 0.23]
    hero_supplier_drift: 0.18     # raise this
```

Regenerate and re-validate. The validator will tell you if a change has made a
story invisible — which is the failure mode that otherwise shows up live.

```bash
python3 src/generate.py --tier small && python3 src/validate.py --tier small
```
