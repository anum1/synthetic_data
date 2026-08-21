# Novareach Software — Marketing Performance & Attribution

A scenario-driven synthetic dataset for enterprise analytics demos, built to
work unchanged in **Tableau, Power BI, Databricks and Snowflake**.

One dataset, 33 tables, 16 planted business events, 25 demo questions. Not a
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

That writes 33 parquet + 33 CSV files to `data/small/` in about 40 seconds, then
runs 68 assertions about referential integrity, spend reconciliation, the
attribution invariant, and whether every planted story is actually visible.

For the full-size dataset (15.6M rows, ~33 seconds):

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

**Novareach Software**, a fictional B2B analytics vendor — BI, embedded
analytics, AI analytics, data platform and AI applications. Every account,
contact, campaign and email address is invented; nothing here uses a real
trademark, so it is safe to show to a customer.

- **Period:** four years of history, of which the first is a **warm-up the demo
  never measures**. Without it the earliest quarters cannot contain long-cycle
  deals — long cycles are big deals — so average deal size ramps across the
  window and revenue growth reads +28% when it is really +3%.
- **Anchoring:** the calendar is anchored to *today*, so the demo never goes
  stale. As-of is the last day of the previous complete month, and every planted
  event is timed in months relative to it.
- **Two tiers, one seed.** `small` for Tableau / Power BI Desktop, `full` for
  Snowflake / Databricks / Incorta. **Leads, opportunities and every dollar are
  identical at both tiers** — they are business numbers and have to be
  defensible. Only behavioural volume changes: sessions, sends and impressions.
- **Chain:** budget → campaign → impression → click → lead → MQL → SQL →
  opportunity → revenue, with attribution replayed over the real touch history.

### The headline it produces

```
Marketing spend TTM   Leads     MQLs      Pipeline created   Marketing-sourced revenue
$18.4M                90.3K     27.3K     $84.3M             $38.1M

CPL     Cost/MQL   MQL->SQL   ROAS     Marketing ROI      Marketing-sourced CAC
$204    $674       30.8%      2.07x    0.26x @ 60.8% GM   $13,450
```

and the year-over-year line the whole demo hangs off:

```
Spend              +24.0%
Leads              +16.3%
MQLs               +11.6%
Pipeline created    +3.8%
Revenue             +8.8%
```

Every step from spend down to new pipeline is worse than the one above it, and
spend is growing six times faster than the pipeline it buys. Revenue still rises
faster than pipeline because it is a **lagging** measure — the deals closing now
came from the larger, better-converting cohorts of eighteen months ago. That gap
is the sharpest line in the demo:

> *We are still collecting revenue from pipeline we built last year. The
> pipeline we are building this year is flat.*

---

## The three things that make it defensible

**1. Volume is derived from spend, never drawn.**

```
leads = spend / cost-per-lead
```

for every campaign-month, with CPL varying by channel, region and planted event.
Every stage below is a Bernoulli draw against a rate built from the channel mix.
So there is no number in this dataset that the media plan cannot account for,
and CPL, cost-per-MQL and CAC reconcile in every slice without being checked.

**2. The blended headline is computed from the mix, not configured beside it.**

Change a channel rate in `config/scenario_base.yaml` and the headline moves.
`validate.py` asserts the generated data matches what the mix implies. The
design note asserted both, and they disagreed — its regional ROAS could not
blend to its company average without APAC being 70–85% of total spend.

**3. Attribution totals are identical under all five models.**

```
for every (opportunity, model):  sum(attribution_weight) = 1.0
```

Put `dim_attribution_model` in a slicer and the channel ranking re-orders while
the grand total does not move. That is the best scene in the demo, and it is
also the platform argument — re-ranking on the fly is a join, and a
pre-aggregated cube cannot do joins.

---

## Repository layout

```
marketing/
  PLAN.md                    review of the design note + the build plan
  README.md                  this file
  marketing_synthetic_data_demo_design.txt   the original design note
  config/scenario_base.yaml  every number as a knob
  src/                       generate, validate, run_questions, emit_ddl
                             + one module per subsystem
  sql/demo_questions.sql     the 25 questions, runnable
  sql/snowflake/  databricks/  generated DDL + load scripts
  data/small/  data/full/    parquet (+ CSV at small)
  docs/DATA_MODEL.md         the 33 tables as shipped
  docs/EVENTS.md             the 16 events, at MEASURED magnitude
  docs/KPI_DEFINITIONS.md    every metric's definition and denominator
  docs/DEMO_FLOWS.md         six flows, scene by scene
```

## Scale

| | small | full |
|---|---:|---:|
| Tables | 33 | 33 |
| Rows | 8.1M | 15.6M |
| Parquet | 146 MB | 249 MB |
| CSV | 836 MB | not written |
| Generate | ~40s (with CSV) | ~33s |

Identical at both tiers: 50,000 accounts, ~168K contacts, 526 campaigns,
~238K leads, ~10K opportunities, $18.4M TTM spend, $38.1M TTM revenue.

## Making your own scenario

```bash
cp config/scenario_base.yaml config/my_scenario.yaml
# edit, then:
python3 src/generate.py --scenario config/my_scenario.yaml --tier small
python3 src/validate.py --scenario config/my_scenario.yaml --tier small
```

Referential integrity and business logic are preserved automatically. If a
change breaks a planted story, `validate.py` says which one and by how much.

---

## Read this before presenting

`docs/KPI_DEFINITIONS.md` §1. An opportunity closes a full sales cycle after the
lead that created it, so recent campaign cohorts have not had time to produce
revenue. They are **immature, not failing**, and `pipeline_maturity_pct` is what
says so. Filter on `is_mature_cohort = 1` in any "which campaigns worked" view.

And filter the journey page to `is_hero_account = 1` before clicking anything.
Five accounts have curated 12-touch journeys ending in a won deal; a randomly
clicked account gives a two-touch journey and no wow.
