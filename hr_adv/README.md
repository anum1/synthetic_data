# GlobalTech — HR / Workforce Analytics

A scenario-driven synthetic HR dataset for workforce analytics demos, built to
work unchanged in **Tableau, Power BI, Snowflake, Databricks and Incorta**.

One dataset, 20 tables, 10 planted events, 50 demo questions. Not a
random-number generator: the business events that make the demo worth watching
are *configured*, the workforce is *simulated month by month* so its
correlations are real, and a validator proves the story is visible in the data
before you present it.

---

## Quick start

```bash
python3 src/generate.py --tier small
```

```bash
python3 src/validate.py --tier small
```

That writes 20 parquet files plus CSVs to `data/small/` (~1.0M rows; 40 MB as
parquet, 233 MB with the CSVs) in about 14 seconds, then runs 57 assertions
about integrity and story visibility.

For the full-size dataset (3.1M rows, 131 MB, ~21 seconds):

```bash
python3 src/generate.py --tier full
```

Emit DDL and load scripts for Snowflake and Databricks:

```bash
python3 src/emit_ddl.py --tier full
```

Run the 50 demo questions against the data:

```bash
python3 src/run_questions.py --tier small
```

Requirements: Python 3.11+, `pandas`, `numpy`, `pyarrow`, `pyyaml`. `duckdb`
additionally for `run_questions.py`.

---

## What is in it

**GlobalTech**, a fictional technology company of 18,500 people across the US,
Canada, the UK, Germany, India and Japan. Every company, division, team, job,
provider and person is invented — nothing uses a real trademark and no email
address can resolve, so it is safe to show to customers.

- **Period:** three full years of history plus the current year to date, at
  monthly and pay-period grain.
- **Anchoring:** the calendar is anchored to *today* by default, so the demo
  never goes stale. Regenerate next year and "this year" is still this year.
- **Two tiers:** `small` (6,000 employees) for laptop Tableau and Power BI
  Desktop, `full` (18,500) for Snowflake, Databricks and Incorta. Same seed,
  same events, same story.

The headline the data currently tells:

> Headcount **+2.8%**. Total workforce cost **+9.6%**.
> Voluntary attrition **12.0%**. Average compa-ratio **0.976**.

Cost is rising three times faster than headcount. That divergence is the point —
every demo flow is a different way of answering *why*.

---

## The question the dataset is built around

> **"Why did workforce cost rise 9.6% when headcount only rose 2.8%?"**

`fact_workforce_cost_bridge` answers it as a table rather than a calculation, so
five tools cannot each compute it slightly differently:

| Component | $M | Contribution |
|---|---:|---:|
| Rate (merit, promotion, market) | 40.3 | **+4.33%** |
| Volume (headcount) | 23.4 | +2.51% |
| Benefits | 10.3 | +1.10% |
| Other (commission, allowance, employer tax) | 8.8 | +0.94% |
| Bonus | 6.8 | +0.73% |
| Overtime | 0.1 | +0.01% |
| Mix (geography and function shift) | −0.6 | −0.06% |
| **Total** | **89.0** | **+9.57%** |

Every component is divided by prior-period total cost, so the column sums to the
headline **by construction** — and `validate.py` asserts it closes to 0.0001
percentage points, at company level and inside every function. The methodology
is in [docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) §5.

The negative Mix line is deliberate. Hiring is weighted towards India, so average
cost per FTE falls even as everyone's pay rises. A bridge where every line is
positive looks like five numbers chosen to add up.

---

## Layout

```
config/scenario_base.yaml    every knob; copy it to build variants
src/
  generate.py                entry point; orchestrates and writes
  validate.py                integrity + bridge tie-out + story visibility
  emit_ddl.py                platform DDL from the actual parquet schemas
  run_questions.py           runs the 50 demo questions via DuckDB
  hrconfig.py                config loading + calendar anchoring
  dim_date.py                calendar: Gregorian + fiscal + per-country holidays
  reference.py               name pools, geography, org and job taxonomy
  org.py                     hierarchy build + path enumeration; locations
  jobs.py                    job catalog + geo-differentiated salary ranges
  population.py              the month loop: hires, hazard model, comp, snapshots
  compensation.py            bonus: annual incentive, signing, retention, spot
  benefits.py                plans, enrolment, employer cost inflation
  absence.py                 PTO/sick/parental, and the unpaid hours payroll uses
  payroll.py                 pay calendar + DERIVED payroll
  snapshots.py               flattened management chain
  derived.py                 cost bridge, manager scorecard, risk layer
sql/demo_questions.sql       the 50 questions as runnable SQL
sql/snowflake/               01_ddl.sql, 02_load.sql
sql/databricks/              01_ddl.sql, 02_load.py
docs/DATA_MODEL.md           tables, grain decisions, conventions
docs/KPI_DEFINITIONS.md      every KPI defined once, including the bridge
docs/EVENTS.md               the 10 events and their measured magnitudes
docs/DEMO_FLOWS.md           the scripted flow and the 50 questions
data/small/, data/full/      generated output (parquet, + CSV at small)
```

---

## The 10 planted events

Full detail and measured magnitudes in [docs/EVENTS.md](docs/EVENTS.md).

| # | Event | What it creates |
|---|---|---|
| 1 | Engineering hiring surge | Cloud Platform headcount +26.7% over six months |
| 2 | Sales attrition spike | Sales voluntary attrition 10.7% → 16.0%, skewed to good performers |
| 3 | Compensation compression | 30.3% of Engineering below 0.90 compa vs 9.6% elsewhere |
| 4 | Promotion wave | Engineering promotes at 2.2× the company rate in one month |
| 5 | Benefits inflation | Employer medical cost +24.4%; benefits per employee +13.3% |
| 6 | Payroll anomaly | One unit at 9.2× its own median overtime, for two pay periods |
| 7 | DataSphere acquisition | 600 people, own orgs, locations, benefit plans and pay curve |
| 8 | Marketing reorganisation | 91% of Marketing moves into three new divisions |
| 9 | High-performer attrition | **Emerges** from the hazard model — a 4.8× resignation spread |
| 10 | Manager problem | 30.0% attrition over 87 people, 2.9× the company rate |

Timing is expressed as **months relative to the as-of date** and scope as
**fractions of the population**, so the narrative stays correct after any
regeneration and every event stays proportionally visible at both tiers.

---

## Why it is a simulator, not a table builder

The sibling ApexTech and Meridian datasets build dimensions and then draw facts
against them. That works because nothing there feeds back. Here it does:

```
compa-ratio → attrition → hiring → new hires at midpoint → compression → compa-ratio
```

Generating one table at a time cannot produce that loop, and the loop is what
makes the demo good. `population.py` runs month by month from the start of
history to the as-of date — hires, the termination hazard, the review cycle,
promotions, the merit cycle, market adjustments, transfers, then the month-end
snapshot.

One consequence worth knowing: **cutting the merit budget raises total workforce
cost**, because compression drives exits and the backfills come in at market.
That is the dataset behaving correctly, and it is why the headline is tuned to a
range rather than chased to a decimal place.

---

## Why the validator matters

Synthetic noise routinely swamps a planted signal, and the usual way to find that
out is live, in front of an audience. `validate.py` runs three families of check:

**Integrity** — foreign keys resolve, no NULL keys, no negative money, the
management chain terminates, exactly one current salary row per employee, and
snapshot headcount agrees with headcount derived from hire and termination dates
in **every** month.

**Reconciliation** — regular pay equals what `fact_salary_history` says the
salary was, divided by periods, to within 0.5%. Payroll's bonus line equals
`fact_bonus` payouts to the cent. The bridge closes.

**Narrative** — each enabled event is visible *at the magnitude the config
claims*: Engineering really is 30% below 0.90 compa, the payroll anomaly really
is 9× that unit's own baseline, and the high-performer resignation lift really
does clear 2.5×.

Current status: **57/57 on both tiers.** All 50 demo questions return rows on
both tiers.

---

## Conventions

Inherited from the sibling datasets: lowercase `snake_case`, no reserved-word
column names, `DECIMAL(18,2)` money, `0/1` integer booleans, ISO dates, and **no
NULL foreign keys** — an employee at the top of the tree carries
`manager_employee_id = 0`, which resolves to a real "No Manager" row.

Four things specific to this dataset are easy to get wrong:

**Payroll is derived, never drawn.** `fact_salary_history` is the only source of
base pay, `fact_bonus` of bonus, `fact_benefit_enrollment` of the benefit
deduction. Generate any of them independently and the Compensation page stops
agreeing with the Payroll page.

**Employer cost is not gross pay.** `total_employer_cost` = gross + employer tax
+ employer benefit cost. `benefit_deduction` is the *employee's* contribution and
is not a company cost. Conflating them inflates workforce cost by about 20%.

**Salary ranges are per job PER GEOGRAPHY.** A single global midpoint makes
everyone in India look catastrophically underpaid and turns compa-ratio — the
backbone of two events — into noise. Money is carried in local currency and USD
at a **fixed** budget rate, deliberately, so FX movement never contaminates the
cost bridge.

**`fact_benefit_enrollment` is per plan YEAR.** Summing across years without
grouping by `plan_year` double-counts. Use `fact_payroll.employer_benefit_cost`
for cost actually incurred and enrolment for the annual rate.

---

## Protected-class attributes

`gender`, `ethnicity`, `veteran_status` and `disability_status` are generated
with realistic per-country distributions but **not written to disk** unless
`demographics.enabled: true`. Default is off — plenty of prospects do not want
those columns on a screen in front of a room. Turning them on is one config flag
and a regeneration.

---

## Building a variant

Copy the scenario and change any number:

```bash
cp config/scenario_base.yaml config/my_scenario.yaml
python3 src/generate.py --scenario config/my_scenario.yaml --tier small
```

Referential integrity and business logic are preserved automatically. Set any
event's `enabled: false` to remove that story from the data entirely, or
`data_quality.enabled: false` for a spotless dataset.
