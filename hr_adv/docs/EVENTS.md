# The ten planted events

Configured in `config/scenario_base.yaml` under `events:`. Timing is expressed as
**offsets in months relative to the as-of date**, never as absolute dates, so the
narrative stays correct whenever the dataset is regenerated. Scope is expressed
as a **fraction of the population**, so every event stays proportionally visible
at both tiers.

Set any event's `enabled: false` to remove that story from the data entirely.

All magnitudes below are **measured on the small tier**, not written from
intent. `src/validate.py` asserts every one of them.

---

## Event 1 — Engineering hiring surge

Cloud Platform hires hard for six months, 18 to 12 months before as-of.

- **Config:** `extra_hires_share: 0.0243` (≈450 at full tier), `organization: Cloud Platform`
- **Measured:** Cloud Platform headcount **+26.7%** across the window
- **Shows up in:** headcount trend, headcount by function, cost bridge Volume

## Event 2 — Sales attrition spike

Voluntary attrition in Sales roughly doubles for nine months, concentrated in
Account Executives and Sales Engineers, and skewed towards good performers.

- **Config:** `hazard_multiplier: 2.60` on the named families, `1.70` on the rest
  of Sales, `high_performer_bias: 1.30`
- **Measured:** Sales voluntary attrition **16.0%** annualised in the window
  against ~10.7% before it; AE and SE alone reach **21%**
- **Deliberate second-order effect:** it puts several Sales leaders at the top of
  a naive manager-attrition ranking. Separating that from a genuine manager
  problem is Event 10's demo.

## Event 3 — Compensation compression

Engineering salary ranges move at 6.2%/yr while incumbent merit is capped at 3%,
and new hires arrive at midpoint. Nobody is tagged as "compressed" — it
accumulates.

- **Config:** `incumbent_merit_cap: 0.030`, `new_hire_compa: [0.98, 1.04]`, plus
  `compensation.range_movement_by_function.Engineering: 0.062`
- **Measured:** **30.3%** of Engineering sits below 0.90 compa, against **9.6%**
  in the rest of the business
- **Also measured:** off-cycle market adjustments are suppressed in Engineering
  while the event runs. The company is not fixing it, which is the question.

## Event 4 — Promotion wave

A large Engineering L4→L5 cycle in a single month.

- **Config:** `promoted_share: 0.0097` (≈180 at full tier), `increase_pct: [0.11, 0.18]`
- **Measured:** Engineering promotion rate **2.2×** the company rate that month
- **Shows up in:** the Rate component of the cost bridge, `fact_salary_history`
  with `change_reason = 'Promotion'`

## Event 5 — Benefits inflation

Employer medical cost steps up at the plan-year boundary.

- **Config:** `employer_cost_increase: 0.19`, `employee_cost_increase: 0.06`
- **Measured:** medical employer cost per plan **+24.4%** year on year
  (the 19% step compounding with 4.5% baseline inflation); benefits cost per
  employee **+13.3%** against headcount **+2.8%**
- **Shows up in:** the Benefits component of the bridge, at **+1.10pt** of a
  9.57pt total

## Event 6 — Payroll anomaly

One business unit receives grossly excessive overtime for a short window.

- **Config:** Operations in the UK, `pay_periods: 2`, `overtime_multiplier: 6.0`
- **Measured:** **9.2×** that unit's own median overtime hours, confined to the
  configured periods, flagged by `fact_payroll.is_payroll_anomaly`
- **Note:** the anomaly reaches exempt staff too, which is what makes it an
  *error* rather than a busy month. Demo question 25 finds it without being told
  where to look.

## Event 7 — Acquisition

GlobalTech acquires **DataSphere**, 11 months before as-of.

- **Config:** `headcount_share: 0.0324` (≈600 at full tier), own division, own
  locations (Portland, Leeds, Noida), own benefit plans, `compa_shift: -0.06`,
  `retention_hazard_multiplier: 1.45`
- **Measured:** 206 acquired employees at small tier, average compa **0.918**
  against **0.978** for everyone else; three legacy benefit plans still enrolled
- **Also carries:** most of the planted data-quality defects

## Event 8 — Marketing reorganisation

Marketing's three divisions are retired and replaced with Product Marketing,
Demand Generation and Corporate Communications in a single month.

- **Config:** `moved_share: 0.92`
- **Measured:** **91.0%** of Marketing has a `Reorganization` row in
  `fact_job_history`; **97.7%** of Marketing now sits in the new divisions
- **Shows up in:** `dim_organization.effective_date` and `inactive_date`, and the
  before/after in `fact_workforce_snapshot`

## Event 9 — High-performer attrition

**No parameters.** This one *emerges* from the termination hazard model: a
compa-ratio below 0.90 multiplies resignation odds 3.3×, and a rating of 4 or 5
multiplies them 1.65–1.95×.

Measured over the last 12 months:

| Segment | Avg headcount | Voluntary exits | Rate |
|---|---:|---:|---:|
| **High performer, below 0.90 compa** | 274 | 100 | **36.5%** |
| Other, below 0.90 compa | 737 | 198 | 26.9% |
| High performer, paid at market | 1,104 | 126 | 11.4% |
| Everyone else | 3,831 | 292 | 7.6% |

A **4.8× spread** across a clean 2×2, and it holds up under any cut the audience
asks for — because the mechanism is real, not a tag applied after the fact.

## Event 10 — Manager problem

One organisation runs at several times the company attrition rate, with
depressed ratings and elevated absence.

- **Config:** Data Engineering, `hazard_multiplier: 5.0`, `absence_multiplier: 2.0`,
  `rating_shift: -0.8`, `min_org_headcount_share: 0.015`
- **Measured:** the affected manager tops the excess-over-function ranking at
  **30.0% voluntary attrition over 87 people**, **2.9×** the company rate
- **The subtlety worth demoing:** on the *raw* rate the Sales attrition event can
  put a Sales leader above them. Benchmarking each manager against their own
  function separates a function-wide event from a manager who is actually
  managing badly. `fact_manager_scorecard.excess_attrition_vs_function` is the
  column that does it.

---

## Why the events are generated causally

Events 3, 9 and 10 could all have been produced by tagging chosen employees
after the fact. They are not, and the difference matters on stage.

Terminations fall out of a monthly hazard model whose drivers — compa-ratio,
performance rating, months since promotion, tenure, country, function, manager —
are all in the config and all visible in the data. Compression accumulates from
a merit cap fighting a fast-moving range, not from a "compressed" flag.

The consequence is that the correlations survive being sliced a way you did not
plan for. Tag two hundred leavers and the first unanticipated cut from the
audience exposes the wire.
