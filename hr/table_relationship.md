# Workday HR — Table Relationship Diagram

## Entity Relationship Diagram

```
┌──────────────────────────────┐
│         job_profiles         │
│──────────────────────────────│
│ PK  job_profile_id           │
│     job_title                │
│     job_family               │
│     grade                    │
│     min_salary               │
│     max_salary               │
└──────────────┬───────────────┘
               │ job_profile_id (FK)
               ▼
┌─────────────────────────────────────────────────┐
│                     workers                     │
│─────────────────────────────────────────────────│
│ PK  employee_id ◄────────────────────┐          │
│ FK  job_profile_id                   │ self-ref │
│ FK  manager_id ──────────────────────┘          │
│     employee_name                               │
│     gender_identity · ethnicity                 │
│     veteran_status · disability_status          │
│     department · location · hire_date · age     │
│     grade · job_title · org_level               │
│     status · termination_date                   │
│     termination_reason                          │
└──────┬──────────────────────────────────────────┘
       │
       │  employee_id (FK) — all child tables
       │
  ┌────┴──────┬──────────┬────────────┬──────────────────────┬─────────────┐
  │           │          │            │                      │             │
  ▼           ▼          ▼            ▼                      ▼             ▼
┌──────────┐ ┌────────┐ ┌──────────┐ ┌────────────────────┐ ┌───────────┐ ┌──────────────────────┐
│ absence  │ │payroll │ │ comp-    │ │ benefit_enrollment │ │job_history│ │  performance         │
│──────────│ │────────│ │ ensation │ │────────────────────│ │───────────│ │──────────────────────│
│FK eid    │ │FK eid  │ │──────────│ │FK  employee_id     │ │FK  eid    │ │FK  employee_id       │
│pto_days  │ │period  │ │FK eid    │ │medical_plan        │ │eff_date   │ │    review_year       │
│sick_days │ │gross   │ │salary    │ │dependents          │ │event_type │ │    review_period     │
│          │ │tax     │ │bonus     │ │dental_plan         │ │from/to    │ │    rating            │
│1 row     │ │benefit─┼─┤          │ │vision_plan         │ │  dept     │ │    potential         │
│per emp   │ │  deduct│ │1 row     │ │monthly_cost ───────┼─┘  grade   │ │    manager_score     │
└──────────┘ │retire  │ │per emp   │ │                    │    title   │ │    goals_met_pct     │
             │net_pay │ └──────────┘ │1 row per emp       │    salary  │ │                      │
             │        │             └────────────────────┘ │           │ │1 row per emp/year    │
             │1+ rows │                                     │1+ rows    │ └──────────┬───────────┘
             │per emp │                                     │per emp    │            │
             └────────┘                                     └───────────┘            │
                                                                                     │
                                                            ┌────────────────────────┘
                                                            ▼
                                               ┌────────────────────────────┐
                                               │    learning_development    │
                                               │────────────────────────────│
                                               │ FK  employee_id            │
                                               │     course_name            │
                                               │     completion_date        │
                                               │     skill_category         │
                                               │     is_required            │
                                               │                            │
                                               │ 1+ rows per emp            │
                                               │ (required + optional)      │
                                               └────────────────────────────┘
```

## Key Relationships

| Relationship | Type | Note |
|---|---|---|
| `job_profiles` → `workers` | 1:many | One profile can apply to many workers |
| `workers.manager_id` → `workers.employee_id` | self-ref | Manager hierarchy tree |
| `workers` → `compensation` | 1:1 | One salary record per employee |
| `workers` → `benefit_enrollment` | 1:1 | One benefit record per employee |
| `workers` → `absence` | 1:1 | One absence record per employee |
| `workers` → `payroll` | 1:many | One row per employee per pay period |
| `workers` → `job_history` | 1:many | Hire + any promotions / transfers / terminations |
| `workers` → `performance` | 1:many | One annual review per employee per year (2022–2024) |
| `workers` → `learning_development` | 1:many | Required and optional courses completed |
| `benefit_enrollment.monthly_benefit_cost` → `payroll.benefit_deduction` | logical | Not a FK column — derived at payroll generation time |

## Promotion Readiness — Signal Map

How an AI combines tables to answer *"Which employees are promotion ready?"*

| Signal | Source Table | Column(s) |
|---|---|---|
| Consistently high rating | `performance` | `rating`, `goals_met_pct` |
| High potential | `performance` | `potential` |
| Manager endorsement | `performance` | `manager_score` |
| Time in current grade | `job_history` | last promotion `effective_date` → today |
| At top of salary band | `compensation` + `job_profiles` | `annual_salary` vs `max_salary` |
| Required next-grade courses done | `learning_development` | `is_required = Yes`, next grade courses |
| Company tenure | `workers` | `hire_date` |
| Active employee | `workers` | `status = Active` |

## Table Summary

| Table | Rows | Grain |
|---|---|---|
| `workers` | 1,000 | 1 row per employee |
| `job_profiles` | 56 | 1 row per dept × grade |
| `compensation` | 1,000 | 1 row per employee |
| `benefit_enrollment` | 1,000 | 1 row per employee |
| `absence` | 1,000 | 1 row per employee |
| `payroll` | ~11,200 | 1 row per employee per pay period |
| `job_history` | ~1,360 | 1+ rows per employee (career events) |
| `performance` | ~2,148 | 1 row per employee per review year |
| `learning_development` | ~10,763 | 1 row per employee per course |
