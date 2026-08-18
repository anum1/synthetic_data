-- ============================================================
-- Workday HR — Materialized Views for AI Chat
-- ============================================================
-- Execution order:
--   1. mv_employee_360          (base — no MV dependencies)
--   2. mv_performance_summary   (base — no MV dependencies)
--   3. mv_promotion_readiness   (depends on mv_employee_360 + mv_performance_summary)
--   4. mv_payroll_summary       (base — no MV dependencies)
--
-- Prerequisites: all base tables registered as Spark temp views:
--   workers, job_profiles, compensation, benefit_enrollment,
--   absence, payroll, job_history, performance, learning_development
-- ============================================================


-- ============================================================
-- MV 1: mv_employee_360
-- Grain: one row per employee
-- Purpose: covers ~80% of HR chat questions — employee lookup,
--          department filtering, compensation vs band, benefits
-- ============================================================
CREATE OR REPLACE TEMPORARY VIEW mv_employee_360 AS
SELECT
    w.employee_id,
    w.employee_name,
    w.gender_identity,
    w.ethnicity,
    w.veteran_status,
    w.disability_status,
    w.department,
    w.location,
    w.hire_date,
    w.age,
    w.grade,
    w.job_title,
    w.org_level,
    w.status,
    w.termination_date,
    w.termination_reason,
    w.manager_id,
    mgr.employee_name                                                                       AS manager_name,

    -- Job profile / salary band
    jp.job_family,
    jp.min_salary,
    jp.max_salary,

    -- Compensation
    c.annual_salary,
    c.annual_bonus_target,
    ROUND(
        (c.annual_salary - jp.min_salary) / NULLIF(jp.max_salary - jp.min_salary, 0) * 100,
        1
    )                                                                                       AS salary_band_pct,
    CASE
        WHEN c.annual_salary > jp.max_salary                                                THEN 'Above Band'
        WHEN c.annual_salary < jp.min_salary                                                THEN 'Below Band'
        WHEN (c.annual_salary - jp.min_salary) / NULLIF(jp.max_salary - jp.min_salary, 0) >= 0.8
                                                                                            THEN 'Top of Band'
        WHEN (c.annual_salary - jp.min_salary) / NULLIF(jp.max_salary - jp.min_salary, 0) >= 0.5
                                                                                            THEN 'Mid Band'
        ELSE                                                                                     'Lower Band'
    END                                                                                     AS band_position_label,

    -- Benefits
    be.medical_plan,
    be.dental_plan,
    be.vision_plan,
    be.dependents,
    be.monthly_benefit_cost,
    ROUND(be.monthly_benefit_cost * 12, 2)                                                  AS annual_benefit_cost,

    -- Absence
    ab.pto_days,
    ab.sick_days,

    -- Derived
    ROUND(DATEDIFF(CURRENT_DATE(), TO_DATE(w.hire_date, 'yyyy-MM-dd')) / 365.25, 1)        AS tenure_years

FROM workers w
LEFT JOIN workers            mgr ON w.manager_id     = mgr.employee_id
LEFT JOIN job_profiles        jp  ON w.job_profile_id = jp.job_profile_id
LEFT JOIN compensation         c  ON w.employee_id    = c.employee_id
LEFT JOIN benefit_enrollment  be  ON w.employee_id    = be.employee_id
LEFT JOIN absence             ab  ON w.employee_id    = ab.employee_id;


-- ============================================================
-- MV 2: mv_performance_summary
-- Grain: one row per employee
-- Purpose: per-year performance columns + aggregates + trend —
--          used by both chat queries and mv_promotion_readiness
-- ============================================================
CREATE OR REPLACE TEMPORARY VIEW mv_performance_summary AS
WITH rated AS (
    SELECT
        employee_id,
        CAST(review_year AS INT)                    AS review_year,
        rating,
        potential,
        CAST(manager_score    AS DOUBLE)            AS manager_score,
        CAST(goals_met_pct    AS DOUBLE)            AS goals_met_pct,
        CASE rating
            WHEN 'Exceptional'          THEN 5
            WHEN 'Exceeds Expectations' THEN 4
            WHEN 'Meets Expectations'   THEN 3
            WHEN 'Below Expectations'   THEN 2
            WHEN 'Unsatisfactory'       THEN 1
        END                                         AS rating_score,
        CASE potential
            WHEN 'High'   THEN 3
            WHEN 'Medium' THEN 2
            WHEN 'Low'    THEN 1
        END                                         AS potential_score
    FROM performance
),
latest_yr AS (
    SELECT employee_id, MAX(review_year) AS max_year
    FROM rated
    GROUP BY employee_id
)
SELECT
    r.employee_id,

    -- Per-year pivoted rating scores (numeric)
    MAX(CASE WHEN r.review_year = 2022 THEN r.rating_score   END)   AS rating_score_2022,
    MAX(CASE WHEN r.review_year = 2023 THEN r.rating_score   END)   AS rating_score_2023,
    MAX(CASE WHEN r.review_year = 2024 THEN r.rating_score   END)   AS rating_score_2024,
    MAX(CASE WHEN r.review_year = 2025 THEN r.rating_score   END)   AS rating_score_2025,

    -- Per-year rating labels
    MAX(CASE WHEN r.review_year = 2022 THEN r.rating         END)   AS rating_label_2022,
    MAX(CASE WHEN r.review_year = 2023 THEN r.rating         END)   AS rating_label_2023,
    MAX(CASE WHEN r.review_year = 2024 THEN r.rating         END)   AS rating_label_2024,
    MAX(CASE WHEN r.review_year = 2025 THEN r.rating         END)   AS rating_label_2025,

    -- Per-year goals met %
    MAX(CASE WHEN r.review_year = 2022 THEN r.goals_met_pct  END)   AS goals_met_pct_2022,
    MAX(CASE WHEN r.review_year = 2023 THEN r.goals_met_pct  END)   AS goals_met_pct_2023,
    MAX(CASE WHEN r.review_year = 2024 THEN r.goals_met_pct  END)   AS goals_met_pct_2024,
    MAX(CASE WHEN r.review_year = 2025 THEN r.goals_met_pct  END)   AS goals_met_pct_2025,

    -- Per-year manager score
    MAX(CASE WHEN r.review_year = 2022 THEN r.manager_score  END)   AS manager_score_2022,
    MAX(CASE WHEN r.review_year = 2023 THEN r.manager_score  END)   AS manager_score_2023,
    MAX(CASE WHEN r.review_year = 2024 THEN r.manager_score  END)   AS manager_score_2024,
    MAX(CASE WHEN r.review_year = 2025 THEN r.manager_score  END)   AS manager_score_2025,

    -- Multi-year aggregates
    ROUND(AVG(r.rating_score),    2)                                AS avg_rating_score,
    ROUND(AVG(r.potential_score), 2)                                AS avg_potential_score,
    ROUND(AVG(r.manager_score),   2)                                AS avg_manager_score,
    ROUND(AVG(r.goals_met_pct),   2)                                AS avg_goals_met_pct,

    -- Latest year snapshot
    MAX(l.max_year)                                                 AS latest_review_year,
    MAX(CASE WHEN r.review_year = l.max_year THEN r.rating         END) AS latest_rating,
    MAX(CASE WHEN r.review_year = l.max_year THEN r.potential      END) AS latest_potential,
    MAX(CASE WHEN r.review_year = l.max_year THEN r.rating_score   END) AS latest_rating_score,
    MAX(CASE WHEN r.review_year = l.max_year THEN r.potential_score END) AS latest_potential_score,

    -- Trend: Pearson correlation of year vs rating score across available reviews
    CASE
        WHEN COUNT(*) >= 2
             AND CORR(CAST(r.review_year AS DOUBLE), CAST(r.rating_score AS DOUBLE)) >  0.3 THEN 'Improving'
        WHEN COUNT(*) >= 2
             AND CORR(CAST(r.review_year AS DOUBLE), CAST(r.rating_score AS DOUBLE)) < -0.3 THEN 'Declining'
        ELSE 'Stable'
    END                                                             AS rating_trend

FROM rated r
JOIN latest_yr l ON r.employee_id = l.employee_id
GROUP BY r.employee_id;


-- ============================================================
-- MV 3: mv_promotion_readiness
-- Grain: one row per employee
-- Purpose: one-stop view for "who is ready for promotion?"
--          Combines all 8 signals from the table_relationship.md
--          signal map. Includes composite score for ranking.
-- Depends on: mv_employee_360, mv_performance_summary
-- ============================================================
CREATE OR REPLACE TEMPORARY VIEW mv_promotion_readiness AS
WITH
last_grade_event AS (
    -- Most recent Hire or Promotion event = start of current grade
    SELECT
        employee_id,
        MAX(TO_DATE(effective_date, 'yyyy-MM-dd'))  AS grade_start_date
    FROM job_history
    WHERE event_type IN ('Hire', 'Promotion')
    GROUP BY employee_id
),
required_courses AS (
    SELECT
        employee_id,
        COUNT(*)                                    AS required_courses_done
    FROM learning_development
    WHERE is_required = 'Yes'
    GROUP BY employee_id
)
SELECT
    -- Identity
    e.employee_id,
    e.employee_name,
    e.department,
    e.location,
    e.grade,
    e.job_title,
    e.org_level,
    e.status,
    e.manager_name,

    -- Signal 1: Company tenure
    e.tenure_years,

    -- Signal 2: Time in current grade
    ROUND(DATEDIFF(CURRENT_DATE(), ge.grade_start_date) / 30.44, 1) AS months_in_current_grade,

    -- Signal 3+4: Salary vs band (at top of band = less room, but signals stagnation)
    e.annual_salary,
    e.min_salary,
    e.max_salary,
    e.salary_band_pct,
    e.band_position_label,

    -- Signal 5: Consistently high rating (3-year avg)
    ps.avg_rating_score,
    ps.rating_score_2022,
    ps.rating_score_2023,
    ps.rating_score_2024,
    ps.rating_score_2025,
    ps.rating_trend,
    ps.latest_rating,

    -- Signal 6: High potential
    ps.latest_potential,
    ps.avg_potential_score,

    -- Signal 7: Manager endorsement
    ps.avg_manager_score,
    ps.manager_score_2022,
    ps.manager_score_2023,
    ps.manager_score_2024,
    ps.manager_score_2025,

    -- Goals performance
    ps.avg_goals_met_pct,
    ps.goals_met_pct_2022,
    ps.goals_met_pct_2023,
    ps.goals_met_pct_2024,
    ps.goals_met_pct_2025,

    -- Signal 8: Required courses completed
    COALESCE(rc.required_courses_done, 0)                           AS required_courses_done,

    -- Active flag
    (e.status = 'Active')                                           AS is_active,

    -- Composite readiness score (0–100) — for ranking only
    -- Weights: performance 30, goals 20, manager 20, learning 15, potential 15
    ROUND(
        COALESCE(ps.avg_rating_score,  0) / 5.0   * 30.0
      + COALESCE(ps.avg_goals_met_pct, 0) / 100.0 * 20.0
      + COALESCE(ps.avg_manager_score, 0) / 10.0  * 20.0
      + LEAST(COALESCE(rc.required_courses_done, 0), 10) / 10.0 * 15.0
      + CASE ps.latest_potential
            WHEN 'High'   THEN 15.0
            WHEN 'Medium' THEN  8.0
            ELSE               0.0
        END,
    1)                                                              AS promotion_readiness_score

FROM mv_employee_360         e
LEFT JOIN last_grade_event   ge ON e.employee_id = ge.employee_id
LEFT JOIN mv_performance_summary ps ON e.employee_id = ps.employee_id
LEFT JOIN required_courses   rc ON e.employee_id = rc.employee_id;


-- ============================================================
-- MV 4: mv_payroll_summary
-- Grain: one row per employee (aggregated across all pay periods)
-- Purpose: payroll cost questions, tax rate, dept cost roll-ups
-- ============================================================
CREATE OR REPLACE TEMPORARY VIEW mv_payroll_summary AS
SELECT
    p.employee_id,
    w.employee_name,
    w.department,
    w.location,
    w.grade,
    w.status,

    COUNT(*)                                                        AS pay_periods_count,
    ROUND(SUM(p.gross_pay),         2)                             AS total_gross_pay,
    ROUND(AVG(p.gross_pay),         2)                             AS avg_gross_pay_per_period,
    ROUND(SUM(p.tax),               2)                             AS total_tax,
    ROUND(SUM(p.benefit_deduction), 2)                             AS total_benefit_deduction,
    ROUND(SUM(p.retirement),        2)                             AS total_retirement,
    ROUND(SUM(p.net_pay),           2)                             AS total_net_pay,
    ROUND(AVG(p.net_pay),           2)                             AS avg_net_pay_per_period,

    -- Derived rates
    ROUND(SUM(p.tax)               / NULLIF(SUM(p.gross_pay), 0) * 100, 1) AS effective_tax_rate_pct,
    ROUND(SUM(p.benefit_deduction) / NULLIF(SUM(p.gross_pay), 0) * 100, 1) AS benefit_deduction_rate_pct,
    ROUND(SUM(p.retirement)        / NULLIF(SUM(p.gross_pay), 0) * 100, 1) AS retirement_contribution_rate_pct

FROM payroll p
JOIN workers w ON p.employee_id = w.employee_id
GROUP BY
    p.employee_id,
    w.employee_name,
    w.department,
    w.location,
    w.grade,
    w.status;
