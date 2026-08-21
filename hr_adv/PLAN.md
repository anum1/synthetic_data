# GlobalTech HR Analytics — review of the design note, and a build plan

> **Status: built.** This plan was executed. The dataset lives in this folder —
> see [README.md](README.md) for how to run it, [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
> for the 20 tables as actually shipped, and [docs/EVENTS.md](docs/EVENTS.md) for
> the measured magnitude of each planted event. Where the built model differs
> from §3 below (20 tables rather than 16; `dim_pay_calendar` added; benefit
> enrolment larger than estimated because it is per plan year), the docs are
> authoritative.

Review of [hr_demo_data_dsign.txt](hr_demo_data_dsign.txt), plus the plan to
generate it as a real dataset in the style of the sibling `sales` (ApexTech) and
`supply_chain` (Meridian) projects.

---

## 1. Verdict

The narrative design is strong and should be kept almost as-is. The story
("workforce cost +8.7%, headcount +3.2% — why?"), the five dashboard pages and
most of the ten planted events are exactly the right shape for an Incorta/NLQ
demo, and they are better than what the older `hr/` folder produces.

The **data design underneath it is not yet buildable**. Seven things are either
missing or specified in a way that will fall apart on stage. They are listed in
§2 in the order they will hurt you. §3 onwards is the plan.

---

## 2. What needs to change before writing any code

### 2.1 The killer question's arithmetic does not currently tie out — fix this first

The doc's headline decomposition:

```
Workforce cost +9.0%
  Salary increases +3.2%   Headcount +2.9%   Benefits +1.4%
  Bonus +0.9%              Overtime +0.6%           = +9.0%
```

This only holds if every line is `Δcomponent ÷ prior-period total workforce
cost` — i.e. contributions to a total, not growth rates of each component. Those
are different numbers and the doc uses the language of the second while
implying the first. Worse, "headcount" and "salary increases" overlap: new hires
also carry a salary, so a naive split double-counts them and the column will
not sum to the total. The demo dies in Q&A, in front of the one person in the
room who does this for a living.

**Decide the methodology now, put it in `docs/KPI_DEFINITIONS.md`, and make
`validate.py` assert it closes.** Recommended bridge, prior year → current year,
on total workforce cost:

| Component | Definition |
|---|---|
| Volume (headcount) | ΔFTE-months × prior-year average base cost per FTE-month |
| Rate (merit / promotion / market) | Δaverage base rate per FTE-month × current-year FTE-months |
| Mix | residual of base pay after volume and rate — org, level and geography shift |
| Bonus | Δbonus cost |
| Overtime | Δovertime cost |
| Benefits | Δemployer benefit cost |
| Other | allowances, commission, employer taxes |

Volume and rate are the classic price/volume split and are unambiguous in that
order; mix absorbs the interaction so nothing is double-counted. Every component
is divided by prior-year total cost, so the column sums to the headline
percentage **by construction**, and the validator can assert
`|Σcomponents − total| < 0.1pt`.

This single decision determines the grain of half the tables below. Do it first.

### 2.2 Payroll must be derived from compensation, never generated independently

The doc lists `payroll` as a table with its own `regular_pay`, `bonus_pay` and
`benefit_deduction` columns. If those are drawn independently, the Compensation
page and the Payroll page will disagree, and the fastest way for an audience to
lose trust is `avg salary × headcount ≠ payroll`.

Rule for the generator: **`salary_history` is the source of truth.** Each payroll
row is computed:

- `regular_pay` = effective salary at `pay_period_end` ÷ periods-per-year × FTE, less unpaid-absence hours
- `bonus_pay` = the `bonus` rows whose payout date falls in the period
- `benefit_deduction` = Σ `employee_contribution` from active `benefit_enrollment`, prorated per period
- `overtime_pay` = only for non-exempt employees (`exempt_status = 'Non-Exempt'`), which makes Event 6 land in a plausible population instead of on salaried engineers
- `gross_pay` = regular + overtime + bonus + commission + allowance, `net_pay` = gross − tax − deductions

Employer benefit cost does **not** belong in `gross_pay` — carry it separately so
"total workforce cost" is an explicit, defined roll-up rather than a sum someone
guesses at.

### 2.3 One salary range per job is wrong across six countries

`job` carries a single `min/mid/max`. With US, Canada, UK, Germany, India and
Japan in scope, a single USD midpoint makes every employee in India look
catastrophically underpaid, and the "below midpoint" risk card on Page 5 becomes
noise. Compa-ratio is the backbone of Events 3 and 9 — it has to be credible.

**Add `job_salary_range`, keyed `job_id × geo_zone × effective_year`**, holding
local-currency min/mid/max plus a USD equivalent at a fixed budget rate. Fixing
the FX rate keeps currency movement out of the story — you are demoing HR, not
treasury, and a floating rate would contaminate the cost bridge. Geo zones:
`US`, `CA`, `UK`, `DE`, `IN`, `JP`, with a differential applied to a global
job-level anchor.

Store money on every fact in **both** local currency and USD. Every KPI in the
demo is USD; the local amount is what makes it look like a real Workday extract.

### 2.4 Add a monthly employee snapshot — the highest-value table not in the doc

"Headcount by department in March 2024" requires as-of resolution against
`employee_job_history`, and Tableau, Power BI and most NLQ layers do that badly
or slowly. Every trend on Page 1 depends on it.

**Add `fact_workforce_snapshot`: one row per active employee per month-end**
(~18,500 × 44 months ≈ 780K rows), carrying the org, manager, job, level,
location, FTE, salary, compa-ratio and tenure *as of that month*. Headcount,
attrition, span of control and mix analysis all become a `GROUP BY` instead of a
window function. It also makes the mix component of §2.1 computable directly.

This replaces `manager_relationship` (which is redundant with
`employee.manager_employee_id`) in the table list.

### 2.5 Hierarchies must be flattened, not recursive

The org drill-down in §4 of the doc is the best part of the demo, and a parent
pointer alone will not deliver it in a BI tool. Ship `dim_organization` with
**path-enumerated columns** — `org_level_1` … `org_level_6`, `org_path`,
`org_depth`, `is_leaf` — alongside `parent_organization_id`. Do the same for the
management chain: `manager_chain_l1..l6` on the snapshot, so "roll everything up
to this VP" is one filter.

### 2.6 Events 3, 9 and 10 must be generated causally, not stamped on

Event 9 — high performers below midpoint resign more — is the most impressive
thing in the doc *if the correlation is real*. If you tag 200 employees as
leavers after the fact, any cut that is not the exact cut you planned falls
apart, and the AI "discovery" is a magic trick with a visible wire.

Generate terminations from a monthly **hazard model** instead:

```
p(resign) = base_hazard(country, job_family)
          × f_compa(compa_ratio)          # <0.90 → ~2.2x
          × f_perf(performance_rating)    # 4–5 → ~1.4x, 1–2 → ~0.7x (they get managed out instead)
          × f_promo(months_since_promotion)
          × f_tenure(tenure_months)       # 12–30 month peak
          × f_manager(manager_risk_score) # Event 10 lives here
          × event_multipliers(month, org) # Event 2 lives here
```

Put the coefficients in the config, and have `validate.py` assert the *lift* the
config claims (e.g. rating 4–5 with compa < 0.90 resign at ≥ 2.5× baseline). Same
approach for compression: don't tag compressed employees, hire new engineers at
the range midpoint while capping incumbent merit at 3%, and let compression
emerge. Then it survives being sliced any way the audience asks.

### 2.7 Anchor the calendar to today

The doc fixes the window at Jan 2023 → Aug 2026, which is today. Six months from
now the demo silently shows a stale "current" year. Follow `supply_chain`:
`anchor: today`, as-of = last day of the previous complete month, history
expressed in years back, and **event timing as month offsets relative to as-of**.
Regenerate any time and the story stays correct.

### 2.8 Smaller notes

- **Pay frequency is inconsistent.** `employee.pay_frequency` exists but the row
  estimate assumes 26 periods for everyone. US/Canada are bi-weekly; UK, Germany,
  India and Japan are monthly. Add a small `pay_calendar` table (pay group ×
  period). Realistic, and it makes the Event 6 overtime anomaly harder to spot
  by accident. Revised payroll volume: ~365K rows/year, ~1.34M over 3.7 years —
  close enough to the doc's 1.4M.
- **Drop `position` (21K rows).** It adds a join and contributes nothing to any
  of the 50 demo questions. Keep `position_id` as a degenerate attribute on the
  employee if you want the Workday look.
- **`absence` is decorative unless it feeds payroll.** Wire unpaid leave into
  `regular_hours` and use absence as an input to the Event 10 manager signal.
- **Protected-class attributes behind a config flag.** Gender, ethnicity, veteran
  and disability status (from `hr/aa.md`) make a DEI page possible, but plenty of
  prospects will not want them on screen. Default `demographics.enabled: false`,
  and use `@globaltech.example` for emails and fully synthetic name pools so the
  data is never mistaken for a real extract.
- **Plant data-quality defects deliberately** — the doc asks for them in §20 and
  never specifies any. The DataSphere acquisition is the natural carrier:
  duplicate person records under two employee numbers, cost centres coded in a
  different format, ~40 employees with no manager assigned, a handful of
  terminations posted after payroll stopped. This mirrors the dirty-supplier-name
  trick that works well in the Meridian demo.

---

## 3. Revised data model — 14 tables

| # | Table | Grain | Small | Full |
|---|---|---|---:|---:|
| 1 | `dim_date` | day | 1,700 | 1,700 |
| 2 | `dim_organization` | org unit, flattened | 300 | 800 |
| 3 | `dim_location` | location | 80 | 250 |
| 4 | `dim_job` | job profile | 400 | 1,200 |
| 5 | `job_salary_range` | job × geo zone × year | 9,600 | 28,800 |
| 6 | `dim_benefit_plan` | plan × year | 120 | 120 |
| 7 | `dim_employee` | employee (current state) | 6,000 | 18,500 |
| 8 | `fact_workforce_snapshot` | employee × month-end | 250K | 780K |
| 9 | `fact_job_history` | employee × job event | 15K | 45K |
| 10 | `fact_salary_history` | employee × salary change | 23K | 70K |
| 11 | `fact_bonus` | employee × bonus payout | 12K | 35K |
| 12 | `fact_payroll` | employee × pay period | 440K | 1.34M |
| 13 | `fact_benefit_enrollment` | employee × plan × plan year | 33K | 100K |
| 14 | `fact_performance_review` | employee × review year | 17K | 50K |
| 15 | `fact_absence` | absence occurrence | 82K | 250K |
| 16 | `fact_termination` | terminated employee | 1,700 | 5,000 |
| 17 | `fact_workforce_cost_bridge` | period × org × component | 4K | 12K |

Sixteen tables plus the pay calendar. `fact_workforce_cost_bridge` is derived —
it is §2.1 materialised, so the headline decomposition is a table the dashboard
reads rather than a calculation five tools each get slightly differently.

Two tiers, same seed, same events, same story: `small` for Tableau/Power BI
Desktop, `full` for Snowflake/Databricks/Incorta. Parquet always, CSV at small
tier only.

Conventions inherited from the siblings: lowercase `snake_case`, no reserved
words, `DECIMAL(18,2)` money, `0/1` integer booleans, ISO dates, and **no NULL
foreign keys** — an employee with no manager points at a real "No Manager" row,
which is also how the planted data-quality defect stays queryable.

---

## 4. Architecture — a month-by-month simulator, not a dimension-then-fact builder

This is the one place where this dataset must depart from `sales` and
`supply_chain`. Those build dimensions, then draw facts against them. Here the
facts feed back into each other: compa-ratio drives attrition, attrition drives
hiring, hiring at midpoint drives compression, compression drives compa-ratio.
Table-at-a-time generation cannot produce that, and it is precisely the loop
that makes the demo good.

**Core loop** — for each month from history start to as-of:

```
1  apply planned hires (baseline growth + Event 1 surge + Event 7 acquisition)
2  evaluate the termination hazard for every active employee   -> fact_termination
3  apply transfers and reorganisation moves (Event 8)          -> fact_job_history
4  in the merit month, run the annual comp cycle               -> fact_salary_history
5  apply off-cycle promotions and market adjustments (Events 3,4)
6  accrue absence, and post it against payroll hours
7  emit payroll rows for every pay period ending in the month  -> fact_payroll
8  emit the month-end snapshot of everyone active              -> fact_workforce_snapshot
```

Performance reviews, benefit enrolments (annual open enrolment, plus life
events), the bonus cycle and the cost bridge are computed after the loop, from
the state it produced.

### Layout

```
config/scenario_base.yaml   every knob, including all 10 event definitions
src/
  generate.py               entry point
  validate.py               integrity + narrative + bridge tie-out
  emit_ddl.py               DDL from the actual parquet schemas
  run_questions.py          runs the demo questions via DuckDB
  hrconfig.py               config load + calendar anchoring
  dim_date.py               (portable from supply_chain, near unchanged)
  reference.py              name pools, geography, job taxonomy
  org.py                    hierarchy build + path enumeration
  jobs.py                   job catalog + geo-differentiated salary ranges
  population.py             the month loop: hires, hazard model, terminations
  compensation.py           merit cycle, promotions, market adjustments, bonus
  payroll.py                pay calendar + derived payroll
  benefits.py               plans, open enrolment, employer cost inflation
  performance.py            ratings correlated with pay and attrition
  absence.py                PTO/sick accrual and usage
  events.py                 the 10 planted events as multiplier matrices
  snapshots.py              monthly workforce snapshot
  derived.py                cost bridge, risk scores, manager scorecard
sql/demo_questions.sql      the 50 questions as runnable SQL
sql/snowflake/ sql/databricks/
docs/DATA_MODEL.md  EVENTS.md  DEMO_FLOWS.md  KPI_DEFINITIONS.md
data/small/ data/full/
```

---

## 5. The ten events, as config

Keep all ten from the doc. Restated with the parameters the generator needs and
the magnitude the validator will assert. Timing is months relative to as-of.

| # | Event | Config | Validator asserts |
|---|---|---|---|
| 1 | Engineering hiring surge | `+450 hires, months −18..−12, org Cloud Platform` | Engineering headcount +16–20% YoY |
| 2 | Sales attrition spike | `voluntary rate 8%→17%, months −14..−6, AE + SE roles` | Sales voluntary attrition 15–19% in window |
| 3 | Compensation compression | `new-hire target compa 0.98–1.02, incumbent merit cap 3%` | ≥28% of Engineering ICs below 0.90 compa |
| 4 | Promotion wave | `+180 promotions, month −9, Engineering L4→L5` | Engineering promo rate ≥2.5× company |
| 5 | Benefits inflation | `employer medical cost +14% at plan-year boundary` | Employer benefit cost/employee +12–16% YoY |
| 6 | Payroll anomaly | `Operations UK, 2 pay periods at month −4, OT ×6` | OT hours ≥5× that unit's trailing median |
| 7 | DataSphere acquisition | `600 employees, month −11, own orgs/locations/ranges` | 600 hires with `is_acquired = 1`, distinct comp curve |
| 8 | Marketing reorganisation | `month −7, split into 3 sub-orgs` | ≥90% of Marketing has a Reorganization history row |
| 9 | High-performer attrition | *emerges from the hazard model* | resign lift ≥2.5× for rating 4–5 & compa <0.90 |
| 10 | Manager problem | `1 manager, hazard ×3, absence ×2, avg rating −0.8` | that manager top-1 on turnover among ≥15-report managers |

Each with `enabled: true|false`, so any story can be removed from the data
entirely.

---

## 6. Target headline

The as-of executive row the whole demo hangs off:

```
Headcount 18,500   +3.2% YoY        Voluntary attrition 11.4%
Total workforce cost $2.31B   +8.7% YoY
Average salary $113K   +3.4%        Benefits per employee $14.2K   +13.8%
```

And the bridge that answers it:

```
Workforce cost +8.7%
  Rate (merit/promo/market)   +3.2%
  Volume (headcount)          +2.9%
  Benefits                    +1.4%
  Bonus                       +0.9%
  Overtime                    +0.6%
  Mix                         −0.3%
                              ─────
                              +8.7%
```

The negative mix term is worth engineering deliberately: growth weighted toward
India and toward junior levels pulls average cost *down*, which is a genuinely
interesting thing for the AI to surface and it stops the bridge looking like
five numbers that happen to add up.

---

## 7. Build phases

| Phase | Output | Est. |
|---|---|---|
| 0 | `docs/DATA_MODEL.md` + `KPI_DEFINITIONS.md` — exact columns, types, keys, and the §2.1 bridge methodology settled | 0.5d |
| 1 | Config, calendar anchoring, reference data, org hierarchy, job catalog, geo salary ranges | 1d |
| 2 | Population engine: month loop, hires, hazard model, terminations, acquisition | 1.5d |
| 3 | Compensation: merit cycle, promotions, market adjustments, bonus, compa-ratio targeting | 1.5d |
| 4 | Pay calendar + derived payroll + the overtime anomaly | 1d |
| 5 | Benefits: plans, open enrolment, employer cost inflation | 0.5d |
| 6 | Performance, absence, monthly snapshot, cost bridge, risk/manager scorecards | 1d |
| 7 | `validate.py` — integrity, narrative, and the bridge tie-out | 1d |
| 8 | `emit_ddl.py`, 50 demo questions as SQL, `run_questions.py` | 0.5d |
| 9 | `README.md`, `DEMO_FLOWS.md`, `EVENTS.md`, 15-minute demo script | 0.5d |

Roughly **9 days**. Phases 1–6 are the critical path; 7 can be written against
partial output as each phase lands, and is worth writing early rather than last —
on the Meridian build the validator is what caught planted signals being
swamped by noise.

### Acceptance criteria

The dataset is demo-ready when:

1. `Σ bridge components − total workforce cost delta` < 0.1pt.
2. `Σ fact_payroll.regular_pay` for any period reconciles to salary × FTE from
   `fact_salary_history` within 0.5%.
3. Every enabled event passes its narrative check at the magnitude in §5.
4. Headcount from `fact_workforce_snapshot` matches headcount derived from
   hire/termination dates, every month, exactly.
5. All 50 demo questions return non-empty, non-absurd results via
   `run_questions.py`.

---

## 8. Decisions taken

1. **Tier sizes: `small` = 6,000 employees, `full` = 18,500.** Event scope is
   expressed as *fractions of the population*, not absolute counts, so every
   planted story stays proportionally visible at both tiers. The absolute
   numbers in §5 are what those fractions produce at full tier. This is the
   Meridian weakness deliberately not repeated.
2. **Demographics default off.** `demographics.enabled: false` in the base
   scenario. The columns are generated so a DEI page is one config flag away,
   but they are not written to disk unless the flag is set.
