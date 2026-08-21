# Data model

20 tables: 8 dimensions, 12 facts. Employee-grain throughout, with one
month-end snapshot that carries the whole workforce state.

---

## 1. Tables

### Dimensions

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `dim_date` | day | 1,308 | 1,308 |
| `dim_employee` | employee (current state) | 8,335 | 25,367 |
| `dim_organization` | supervisory org, flattened | 300 | 800 |
| `dim_location` | site | 83 | 253 |
| `dim_job` | job profile | 400 | 870 |
| `job_salary_range` | job × geo zone × year | 9,600 | 20,880 |
| `dim_benefit_plan` | plan × plan year | 76 | 76 |
| `dim_pay_calendar` | pay group × period | 137 | 137 |

### Facts

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `fact_workforce_snapshot` | employee × month end | 244,818 | 754,749 |
| `fact_payroll` | employee × pay period | 389,421 | 1,203,510 |
| `fact_absence` | absence occurrence | 168,982 | 517,842 |
| `fact_benefit_enrollment` | employee × plan × plan year | 76,938 | 235,025 |
| `fact_salary_history` | employee × salary change | 42,868 | 131,997 |
| `fact_performance_review` | employee × review year | 21,317 | 65,846 |
| `fact_bonus` | employee × payout | 20,028 | 61,737 |
| `fact_job_history` | employee × job event | 17,663 | 55,170 |
| `fact_termination` | terminated employee | 2,322 | 6,854 |
| `fact_workforce_risk` | employee at as-of | 6,000 | 18,500 |
| `fact_manager_scorecard` | manager × last 12 months | 239 | 802 |
| `fact_workforce_cost_bridge` | scope × cost component | 80 | 80 |

Roughly 1.0M rows / 40 MB at small tier, 3.1M rows / 131 MB at full.

---

## 2. How it fits together

```
dim_date ─────────────┐
dim_organization ─────┤
dim_location ─────────┼──► fact_workforce_snapshot ──► fact_manager_scorecard
dim_job ──┬───────────┤         │                 └──► fact_workforce_risk
          └► job_salary_range   │
dim_employee ─────────┘         ├──► fact_payroll ──► fact_workforce_cost_bridge
                                │        ▲   ▲   ▲
dim_pay_calendar ───────────────┘        │   │   │
                                         │   │   │
fact_salary_history ─────────────────────┘   │   │
fact_bonus ──────────────────────────────────┘   │
fact_benefit_enrollment ◄── dim_benefit_plan ────┘
fact_absence ────────────────────────────────────┘

fact_job_history · fact_termination · fact_performance_review
```

The arrows into `fact_payroll` are the important ones. Payroll is **derived**,
never drawn: base pay comes from `fact_salary_history` (through the month-end
snapshot that reflects it), bonus from `fact_bonus`, the benefit deduction from
`fact_benefit_enrollment`, and unpaid hours from `fact_absence`. Generate any of
those independently and the Compensation page stops agreeing with the Payroll
page — which is the fastest way to lose a room.

---

## 3. Grain decisions worth knowing

### `fact_workforce_snapshot` is the workhorse

One row per active employee per month end, carrying org, manager, job, level,
location, FTE, salary, compa-ratio, rating and tenure **as of that month**.

Without it, "headcount by department in March 2024" is an as-of resolution
against `fact_job_history`, which Tableau, Power BI and most NLQ layers either
cannot express or run too slowly to demo. With it, every trend on the executive
page is a `GROUP BY`.

It also carries the flattened management chain — `manager_chain_l1..l6`
top-down, plus `reporting_depth` — so "roll everything up to this VP" is a
filter, not a recursive CTE.

### Hierarchies are emitted both ways

`dim_organization` carries `parent_organization_id` for anyone who wants to walk
the tree, and `org_level_1..org_level_6` + `org_path` + `org_depth` + `is_leaf`
for everyone else. Employees are assigned to **leaf orgs only**.

The hierarchy is **function-based**, not geography-based:

```
Company → Business Unit → Function → Division → Department → Team
```

Geography lives on `dim_location`. Nesting country inside the org tree — as the
original design note did — multiplies every function by every country and
produces thousands of near-empty supervisory orgs. Workday does not model it
that way and neither does this.

### Salary ranges are per job **per geography**

`job_salary_range` is keyed `job_id × geo_zone × effective_year`, in local
currency and USD. Compa-ratio is the backbone of two planted events, so a single
global midpoint is not survivable: it would make every employee in India look
catastrophically underpaid and turn the risk card into noise.

Ranges move each year. **Engineering ranges move at 6.2%/yr against 2.8%
elsewhere** — that hot market, against a capped incumbent merit budget, is what
actually generates the compression story.

### Pay frequency is mixed

US and Canada run **biweekly** (26 periods); the UK, Germany, India and Japan run
**monthly** (12). The original design assumed 26 for everyone, which is both
wrong and a missed opportunity — the mixed frequency is what makes the payroll
anomaly hard to spot by eye.

A consequence: a 12-month window can contain **27** biweekly period-ends, so
annual payroll can exceed annual salary by ~2% for that population. That is a
real payroll phenomenon, not an error, and `validate.py` accounts for it.

---

## 4. Conventions

Inherited from the sibling ApexTech (sales) and Meridian (supply chain)
datasets:

- lowercase `snake_case`, no reserved-word column names
- `DECIMAL(18,2)` for money, `DECIMAL(12,6)` for rates and ratios
- `0/1` integer booleans, never `TRUE`/`FALSE` strings
- ISO dates, `DATE` not `TIMESTAMP` — no BI tool benefits from a `00:00:00`
- **no NULL foreign keys.** An employee at the top of the tree carries
  `manager_employee_id = 0`, which resolves to a real "No Manager" row in
  `dim_employee`. That is also what keeps the 40 deliberately manager-less
  records queryable rather than invisible.
- **transactional** money facts carry local currency **and** USD at a fixed
  budget rate: `fact_payroll`, `fact_salary_history`, `fact_bonus`,
  `fact_workforce_snapshot`. The analytical layers — `fact_workforce_cost_bridge`,
  `fact_workforce_risk`, `fact_benefit_enrollment` — are **USD only** by design,
  because they are reporting output and a mixed-currency sum there would be wrong
  rather than useful

---

## 5. Protected-class attributes

`gender`, `ethnicity`, `veteran_status` and `disability_status` are generated
with realistic per-country distributions but are **not written to disk** unless
`demographics.enabled: true` in the scenario. Default is off: plenty of
prospects do not want those columns on a screen in front of a room. Turning them
on is one config flag and a regeneration.

Personal names are drawn from ordinary given-name and surname pools matched to
the employee's country. Emails use the reserved `.example` TLD, which can never
resolve. Nothing here is or resembles a real person.

---

## 6. Deliberate data-quality defects

Controlled by the `data_quality` block; set `enabled: false` for a clean
dataset. The acquisition carries most of them, because that is how HR data
actually gets dirty.

| Defect | Where | What it breaks |
|---|---|---|
| Duplicate person records | `dim_employee.is_duplicate_record = 1` | Headcount is overstated without the filter |
| Employees with no manager | `manager_employee_id = 0` | Reporting rollups |
| Non-standard cost centres | `cost_center LIKE 'DS-%'` | Cost-centre grouping splits the acquired population |
| Payroll after termination | `fact_payroll` rows past `termination_date` | Real money paid to people who had left |
| Inconsistent surname casing | `dim_employee.last_name` | Name-based joins miss rows |

Demo question 50 finds all five in one query.

---

## 7. What was dropped from the original design note

- **`position` (21K rows)** — a join that contributes to none of the 50 demo
  questions. `dim_job` carries what the demo needs.
- **`manager_relationship`** — redundant with `dim_employee.manager_employee_id`.
  Replaced by the flattened chain on the snapshot, which is the thing that
  actually enables the drill-down.

And what was added: `fact_workforce_snapshot`, `job_salary_range`,
`dim_pay_calendar`, `fact_workforce_cost_bridge`, `fact_manager_scorecard` and
`fact_workforce_risk`.
