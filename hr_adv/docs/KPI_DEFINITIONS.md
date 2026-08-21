# KPI definitions

Every number the demo quotes, defined once. Where two definitions are defensible,
the one used here is stated and the other is named so nobody has to guess which
was meant.

---

## 1. Headcount

**Headcount** = rows in `fact_workforce_snapshot` for a given `year_month_key`.
One row per active employee per month end. An employee who joins on the 3rd and
leaves on the 28th of the same month never appears.

- **FTE** = `SUM(fte)` over the same rows. A 0.6 FTE part-timer is 1 headcount
  and 0.6 FTE. Cost measures use FTE; people measures use headcount.
- **Average headcount** over a period = `COUNT(*) / months in the period`.
- **FTE-months** = `SUM(fte)` across all months in the period. This is the volume
  measure the cost bridge uses.

`dim_employee.is_active` gives the same answer at the as-of date only. For any
other date, use the snapshot — do not derive it from hire and termination dates
at query time.

**Duplicate records.** `dim_employee` deliberately contains a small number of
duplicate person records from the acquisition. They carry
`is_duplicate_record = 1` and are excluded from every headcount here. A headcount
taken off `dim_employee` without that filter is overstated.

## 2. Attrition

Denominator is **average headcount over the period**, not opening or closing
headcount.

| Measure | Definition |
|---|---|
| Voluntary attrition | voluntary exits ÷ average headcount |
| Involuntary attrition | involuntary exits ÷ average headcount |
| Total attrition | all exits ÷ average headcount |
| Regrettable attrition | exits with `regrettable_flag = 1` ÷ average headcount |

`regrettable_flag` is set from the leaver's last performance rating — a rating 5
leaver is regrettable 95% of the time, a rating 1 leaver never is.

**Manager attrition** is measured over a manager's whole **organization**
(`manager_chain_l1..l6` rollup), not their direct reports. A director with four
direct reports and ninety people underneath is not low-risk.

## 3. Compensation

- **Compa-ratio** = `base_salary_usd ÷ range_midpoint_usd`, where the midpoint
  comes from `job_salary_range` for that employee's **job × geo zone × year**.
  A single global midpoint would make everyone in India look underpaid.
- **Range penetration** = `(salary − min) ÷ (max − min)`.
- **Average salary** = mean `base_salary_usd` over active employees. Note that
  this **falls** when hiring is weighted towards lower-cost geographies even
  while everyone gets a rise. Use the bridge's Rate component for "what people
  actually got".
- **Salary increase %** = `change_percentage` on `fact_salary_history`, which is
  `new ÷ prior − 1` for that action.
- **Compression gap** = mean compa of employees with under 1 year of service
  minus mean compa of employees with 3+ years, within a job family.

Money is carried in local currency **and** USD, converted at a **fixed budget
rate** held in `job_salary_range.fx_rate_to_usd`. The rate does not float. Every
KPI above is USD; the local amount exists so the data looks like a real extract.

## 4. Workforce cost

**Total workforce cost** = `fact_payroll.total_employer_cost`, which is:

```
gross_pay  (= regular + overtime + bonus + commission + allowance)
+ employer_tax
+ employer_benefit_cost
```

Employer benefit cost and employer payroll tax are **not** part of gross pay.
Conflating them is how workforce-cost figures end up ~20% too high.

`benefit_deduction` is the *employee's* contribution and is a deduction from net
pay, not a company cost.

## 5. The workforce cost bridge

`fact_workforce_cost_bridge` decomposes the change in total workforce cost
between the last 12 months and the 12 months before that. Every component is
divided by **prior-period total cost**, so the column sums to the headline
percentage by construction.

| Component | Definition |
|---|---|
| **Volume (headcount)** | (FTE-months current − FTE-months prior) × prior average base cost per FTE-month |
| **Rate (merit, promotion, market)** | Σ over country × function groups of (current rate − prior rate) × current FTE-months |
| **Mix** | Δ base pay − Volume − Rate. Headcount shifting between groups that cost different amounts |
| **Bonus** | Δ `bonus_pay` |
| **Overtime** | Δ `overtime_pay` |
| **Benefits** | Δ `employer_benefit_cost` |
| **Other** | Δ (`commission` + `allowance` + `employer_tax`) |
| **Total** | the sum of the above |

Three decisions worth knowing:

**Grouping is country × function, not country × level.** Grouping on level would
push every promotion into Mix, which is wrong — a promotion is a pay action and
belongs in the component labelled Rate. Mix is then what its name says:
geography and function shifting under the headcount.

**Volume uses the prior-period rate, Rate uses current-period volume.** That
ordering is the standard price/volume convention and means the two never
double-count the same dollar.

**Mix is a residual, and it is negative here.** Hiring is deliberately weighted
towards India, so the average cost per FTE falls even as everyone's pay rises.
A bridge where every line is positive looks like five numbers picked to add up.

`validate.py` asserts `|Σ components − measured total delta| < 0.1pt` at company
level and at every function.

## 6. Benefits

- **Benefits cost per employee** = `SUM(employer_benefit_cost)` from
  `fact_payroll` ÷ headcount. Use payroll, not enrolment: payroll is what was
  actually incurred period by period, enrolment is the annual rate.
- `fact_benefit_enrollment` is at **employee × plan × plan year**. Any measure
  that sums across plan years without grouping by year double-counts.
- `annual_*_contribution_usd` is the full-year rate; `prorated_*` is that rate
  scaled by `months_covered` for someone who joined mid-year.
- Retirement plans (`cost_basis = 'pct'`) cost a percentage of salary, so a pay
  rise carries a benefits cost with it. Flat plans do not.

## 7. Performance

Ratings run 1–5: Needs Improvement, Developing, Successful, Exceeds
Expectations, Exceptional. `fact_performance_review` is one row per employee per
review year. The rating carried on the snapshot is the one in force that month.

## 8. Absence

- **Absence days** are **working** days, not calendar days, computed per country
  from `dim_date.is_working_day_<country>`.
- Unpaid leave reduces `regular_pay` through `fact_payroll.unpaid_hours`. Paid
  absence does not.

## 9. Time

The as-of date is the **last day of the previous complete month**, resolved at
generation time. "Last 12 months" means the 12 months ending on it; "prior 12
months" the 12 before that. `dim_date` carries `is_last_12_months`,
`is_current_year`, `is_prior_year` and `months_from_as_of` so no dashboard has to
hard-code a date that goes stale.
