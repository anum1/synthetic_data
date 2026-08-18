# Workday HR Demo Data Enhancement Assessment

## Enhancements Overview

### 1. Supervisory Organizations (Manager Hierarchy)
- Add `manager_id` and `org_level` (IC / Manager / Director / VP / C-Suite) to `workers`
- Need careful generation to avoid circular references and ensure span-of-control looks realistic (5–8 direct reports per manager)
- Could also add a separate `org_units` table

### 2. Job Profiles and Grades
- New `job_profiles` table: `job_profile_id`, `job_title`, `job_family`, `grade` (e.g. G1–G8), `min_salary`, `max_salary`
- Link to `workers` and constrain `compensation` salaries to fall within grade bands

### 3. Open Enrollment Events
- New `enrollment_events` table: `employee_id`, `enrollment_period`, `event_type` (Open Enrollment / Life Event), `prior_plan`, `new_plan`, `effective_date`
- Triggers update to `benefit_enrollment`

### 4. Employee Transfers / Promotions
- New `job_history` table: `employee_id`, `effective_date`, `event_type` (Hire / Transfer / Promotion), `from_dept`, `to_dept`, `from_grade`, `to_grade`, `from_salary`, `to_salary`
- Workers table would show current snapshot; history table shows the trail

### 5. Attrition and Terminations
- Add `status`, `termination_date`, `termination_reason` to `workers`
- Payroll rows should stop at termination date
- Could add a `terminations` table with exit interview data (voluntary / involuntary / retirement)

### 6. Diversity Metrics
- Expand `workers`: add `ethnicity`, `gender_identity` (broader than Male/Female), `veteran_status`, `disability_status`
- Needs realistic demographic distributions by department/location

### 7. Monthly Benefit Claims
- New `benefit_claims` table: `employee_id`, `claim_month`, `claim_type` (Medical / Dental / Vision), `billed_amount`, `approved_amount`, `out_of_pocket`
- Correlate with plan type (Gold = higher utilization, Bronze = lower)

---

## Impact Summary

| Enhancement | New Tables | Modified Tables | Complexity |
|---|---|---|---|
| Manager hierarchy | 0 | `workers` | Medium |
| Job profiles & grades | 1 (`job_profiles`) | `workers`, `compensation` | Medium |
| Open enrollment | 1 (`enrollment_events`) | `benefit_enrollment` | Low |
| Transfers/promotions | 1 (`job_history`) | `workers` | Medium |
| Attrition | 0–1 | `workers`, `payroll` | Medium |
| Diversity metrics | 0 | `workers` | Low |
| Benefit claims | 1 (`benefit_claims`) | none | Low |

---

## Recommended Implementation Order

1. **Diversity metrics** — simple column additions to `workers`
2. **Job profiles & grades** — new table, constrains compensation
3. **Manager hierarchy** — depends on org_level from job profiles
4. **Job history** (transfers/promotions + attrition) — depends on hierarchy and grades
5. **Open enrollment events** — depends on benefit_enrollment baseline
6. **Benefit claims** — depends on enrollment and plan data
