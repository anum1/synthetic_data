-- GlobalTech HR Analytics - databricks DDL
-- Generated from data/full on 2026-08-20. Do not hand-edit:
-- rerun src/emit_ddl.py --tier full instead.

CREATE CATALOG IF NOT EXISTS GLOBALTECH_HR;
CREATE SCHEMA IF NOT EXISTS GLOBALTECH_HR.ANALYTICS;
USE GLOBALTECH_HR.ANALYTICS;

CREATE OR REPLACE TABLE dim_benefit_plan (
    benefit_plan_id                            INT NOT NULL,
    plan_code                                  STRING,
    benefit_type                               STRING,
    plan_name                                  STRING,
    provider                                   STRING,
    plan_year                                  INT,
    supports_dependents                        INT,
    cost_basis                                 STRING,
    salary_pct                                 DECIMAL(12,6),
    annual_total_cost_usd                      DECIMAL(18,2),
    annual_employer_cost_usd                   DECIMAL(18,2),
    annual_employee_cost_usd                   DECIMAL(18,2),
    employer_cost_pct_of_salary                DECIMAL(18,4),
    employer_cost_share                        DECIMAL(12,6),
    effective_date                             DATE,
    end_date                                   DATE,
    is_legacy_acquired_plan                    INT,
    is_active                                  INT
);
COMMENT ON TABLE dim_benefit_plan IS 'GlobalTech HR Analytics - 76 rows at tier full';

CREATE OR REPLACE TABLE dim_date (
    calendar_date                              DATE,
    date_key                                   INT NOT NULL,
    day_of_week                                INT,
    day_name                                   STRING,
    day_of_month                               INT,
    day_of_year                                INT,
    week_of_year                               INT,
    month_number                               INT,
    month_name                                 STRING,
    month_abbr                                 STRING,
    quarter_number                             INT,
    quarter_name                               STRING,
    calendar_year                              INT,
    year_month_key                             INT,
    year_month_name                            STRING,
    year_quarter_name                          STRING,
    month_start_date                           DATE,
    month_end_date                             DATE,
    is_month_end                               INT,
    is_weekend                                 INT,
    fiscal_year                                INT,
    fiscal_month_number                        INT,
    fiscal_quarter_number                      INT,
    fiscal_quarter_name                        STRING,
    fiscal_period_key                          INT,
    is_holiday_us                              INT,
    is_working_day_us                          INT,
    is_holiday_canada                          INT,
    is_working_day_canada                      INT,
    is_holiday_uk                              INT,
    is_working_day_uk                          INT,
    is_holiday_germany                         INT,
    is_working_day_germany                     INT,
    is_holiday_india                           INT,
    is_working_day_india                       INT,
    is_holiday_japan                           INT,
    is_working_day_japan                       INT,
    is_holiday_any                             INT,
    holiday_name_us                            STRING,
    days_from_as_of                            INT,
    months_from_as_of                          INT,
    is_current_year                            INT,
    is_prior_year                              INT,
    is_last_12_months                          INT,
    is_ytd                                     INT
);
COMMENT ON TABLE dim_date IS 'GlobalTech HR Analytics - 1,308 rows at tier full';

CREATE OR REPLACE TABLE dim_employee (
    employee_id                                INT NOT NULL,
    first_name                                 STRING,
    last_name                                  STRING,
    country                                    STRING,
    location_id                                INT NOT NULL,
    organization_id                            INT NOT NULL,
    function_name                              STRING,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    career_track                               STRING,
    manager_employee_id                        INT NOT NULL,
    hire_date                                  DATE,
    termination_date                           DATE,
    employment_status                          STRING,
    worker_type                                STRING,
    fte                                        DECIMAL(18,4),
    base_salary_local                          DECIMAL(18,2),
    base_salary_usd                            DECIMAL(18,2),
    currency                                   STRING,
    performance_rating                         INT,
    birth_date                                 DATE,
    is_acquired                                INT,
    employee_number                            STRING,
    employment_type                            STRING,
    pay_frequency                              STRING,
    cost_center                                STRING,
    exempt_status                              STRING,
    city                                       STRING,
    state_province                             STRING,
    region                                     STRING,
    organization_name                          STRING,
    division_name                              STRING,
    department_name                            STRING,
    is_people_manager                          INT,
    tenure_years                               DECIMAL(18,4),
    age_years                                  DECIMAL(18,4),
    age_band                                   STRING,
    tenure_band                                STRING,
    work_email                                 STRING,
    is_active                                  INT,
    is_duplicate_record                        INT
);
COMMENT ON TABLE dim_employee IS 'GlobalTech HR Analytics - 25,367 rows at tier full';

CREATE OR REPLACE TABLE dim_job (
    job_id                                     INT NOT NULL,
    job_family                                 STRING,
    job_subfamily                              STRING,
    function_name                              STRING,
    job_level                                  STRING,
    career_track                               STRING,
    management_level                           STRING,
    job_title                                  STRING,
    is_people_manager                          INT,
    job_code                                   STRING,
    job_family_premium                         DECIMAL(18,4),
    exempt_status                              STRING,
    job_profile_status                         STRING,
    effective_date                             DATE
);
COMMENT ON TABLE dim_job IS 'GlobalTech HR Analytics - 870 rows at tier full';

CREATE OR REPLACE TABLE dim_location (
    location_id                                INT NOT NULL,
    location_code                              STRING,
    location_name                              STRING,
    site_type                                  STRING,
    city                                       STRING,
    state_province                             STRING,
    country                                    STRING,
    country_iso                                STRING,
    region                                     STRING,
    geo_zone                                   STRING,
    currency                                   STRING,
    pay_frequency                              STRING,
    is_hub                                     INT,
    is_remote_hub                              INT,
    headcount_capacity                         INT,
    opened_date                                DATE,
    is_active                                  INT
);
COMMENT ON TABLE dim_location IS 'GlobalTech HR Analytics - 253 rows at tier full';

CREATE OR REPLACE TABLE dim_organization (
    organization_id                            INT NOT NULL,
    organization_code                          STRING,
    organization_name                          STRING,
    organization_type                          STRING,
    parent_organization_id                     INT,
    org_level_1                                STRING,
    org_level_2                                STRING,
    org_level_3                                STRING,
    org_level_4                                STRING,
    org_level_5                                STRING,
    org_level_6                                STRING,
    org_depth                                  INT,
    org_path                                   STRING,
    business_unit                              STRING,
    function_name                              STRING,
    division_name                              STRING,
    department_name                            STRING,
    cost_center                                STRING,
    effective_date                             DATE,
    is_leaf                                    INT,
    is_active                                  INT,
    inactive_date                              DATE,
    manager_employee_id                        INT NOT NULL
);
COMMENT ON TABLE dim_organization IS 'GlobalTech HR Analytics - 800 rows at tier full';

CREATE OR REPLACE TABLE dim_pay_calendar (
    pay_period_id                              INT NOT NULL,
    pay_frequency                              STRING,
    pay_group_countries                        STRING,
    pay_period_start                           DATE,
    pay_period_end                             DATE,
    pay_date                                   DATE,
    periods_per_year                           INT,
    year_month_key                             INT,
    pay_period_name                            STRING
);
COMMENT ON TABLE dim_pay_calendar IS 'GlobalTech HR Analytics - 137 rows at tier full';

CREATE OR REPLACE TABLE fact_absence (
    absence_id                                 INT NOT NULL,
    employee_id                                INT NOT NULL,
    organization_id                            INT NOT NULL,
    country                                    STRING,
    absence_type                               STRING,
    start_date                                 DATE,
    end_date                                   DATE,
    year_month_key                             INT,
    calendar_days                              INT,
    absence_days                               INT,
    absence_hours                              DECIMAL(18,4),
    is_paid                                    INT,
    unpaid_hours                               DECIMAL(18,4),
    absence_status                             STRING
);
COMMENT ON TABLE fact_absence IS 'GlobalTech HR Analytics - 517,842 rows at tier full';

CREATE OR REPLACE TABLE fact_benefit_enrollment (
    benefit_enrollment_id                      INT NOT NULL,
    employee_id                                INT NOT NULL,
    benefit_plan_id                            INT NOT NULL,
    plan_year                                  INT,
    benefit_type                               STRING,
    plan_name                                  STRING,
    coverage_level                             STRING,
    annual_employee_contribution_usd           DECIMAL(18,2),
    annual_employer_contribution_usd           DECIMAL(18,2),
    annual_total_cost_usd                      DECIMAL(18,2),
    months_covered                             INT,
    prorated_employee_contribution_usd         DECIMAL(18,2),
    prorated_employer_contribution_usd         DECIMAL(18,2),
    organization_id                            INT NOT NULL,
    country                                    STRING,
    is_acquired                                INT,
    effective_date                             DATE,
    end_date                                   DATE,
    enrollment_status                          STRING,
    enrollment_reason                          STRING,
    monthly_employee_contribution_usd          DECIMAL(18,2),
    monthly_employer_contribution_usd          DECIMAL(18,2)
);
COMMENT ON TABLE fact_benefit_enrollment IS 'GlobalTech HR Analytics - 235,025 rows at tier full';

CREATE OR REPLACE TABLE fact_bonus (
    bonus_id                                   INT NOT NULL,
    employee_id                                INT NOT NULL,
    bonus_type                                 STRING,
    plan_year                                  INT,
    payout_date                                DATE,
    target_pct                                 DECIMAL(12,6),
    target_amount_usd                          DECIMAL(18,2),
    payout_factor                              DECIMAL(12,6),
    bonus_amount_usd                           DECIMAL(18,2),
    currency                                   STRING,
    organization_id                            INT NOT NULL,
    performance_rating                         INT,
    is_acquired                                INT,
    bonus_amount_local                         DECIMAL(18,2),
    target_amount_local                        DECIMAL(18,2),
    year_month_key                             INT,
    award_date                                 DATE
);
COMMENT ON TABLE fact_bonus IS 'GlobalTech HR Analytics - 61,737 rows at tier full';

CREATE OR REPLACE TABLE fact_job_history (
    job_history_id                             INT NOT NULL,
    employee_id                                INT NOT NULL,
    effective_date                             DATE,
    action                                     STRING,
    reason                                     STRING,
    old_job_id                                 INT,
    new_job_id                                 INT,
    old_job_level                              STRING,
    new_job_level                              STRING,
    old_organization_id                        INT,
    new_organization_id                        INT,
    old_manager_employee_id                    INT,
    new_manager_employee_id                    INT,
    old_location_id                            INT,
    new_location_id                            INT,
    salary_usd                                 DECIMAL(18,2)
);
COMMENT ON TABLE fact_job_history IS 'GlobalTech HR Analytics - 55,170 rows at tier full';

CREATE OR REPLACE TABLE fact_manager_scorecard (
    manager_scorecard_id                       INT NOT NULL,
    manager_employee_id                        INT NOT NULL,
    org_headcount_months                       INT,
    months_active                              INT,
    avg_compa_ratio                            DECIMAL(12,6),
    avg_performance_rating                     DECIMAL(18,4),
    avg_org_headcount                          DECIMAL(18,4),
    annualisation_factor                       DECIMAL(12,6),
    direct_reports                             DECIMAL(18,4),
    exits_total                                DECIMAL(18,4),
    voluntary_exits                            DECIMAL(18,4),
    regrettable_exits                          DECIMAL(18,4),
    absence_days_per_employee                  DECIMAL(18,4),
    voluntary_attrition_rate                   DECIMAL(12,6),
    regrettable_attrition_rate                 DECIMAL(12,6),
    manager_organization_id                    INT,
    manager_job_level                          STRING,
    manager_country                            STRING,
    manager_name                               STRING,
    manager_function                           STRING,
    function_attrition_rate                    DECIMAL(12,6),
    excess_attrition_vs_function               DECIMAL(18,4),
    company_attrition_rate                     DECIMAL(12,6),
    manager_risk_score                         DECIMAL(12,6),
    manager_risk_band                          STRING,
    period_start                               DATE,
    period_end                                 DATE
);
COMMENT ON TABLE fact_manager_scorecard IS 'GlobalTech HR Analytics - 802 rows at tier full';

CREATE OR REPLACE TABLE fact_payroll (
    payroll_id                                 INT NOT NULL,
    employee_id                                INT NOT NULL,
    year_month_key                             INT,
    organization_id                            INT NOT NULL,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    function_name                              STRING,
    country                                    STRING,
    location_id                                INT NOT NULL,
    base_salary_usd                            DECIMAL(18,2),
    fte                                        DECIMAL(18,4),
    currency                                   STRING,
    cost_center                                STRING,
    manager_employee_id                        INT NOT NULL,
    is_acquired                                INT,
    pay_frequency                              STRING,
    pay_period_id                              INT NOT NULL,
    pay_period_start                           DATE,
    pay_period_end                             DATE,
    pay_date                                   DATE,
    periods_per_year                           INT,
    exempt_status                              STRING,
    regular_hours                              DECIMAL(18,4),
    unpaid_hours                               DECIMAL(18,4),
    regular_pay                                DECIMAL(18,2),
    is_payroll_anomaly                         INT,
    overtime_hours                             DECIMAL(18,4),
    overtime_pay                               DECIMAL(18,2),
    bonus_pay                                  DECIMAL(18,2),
    commission                                 DECIMAL(18,2),
    allowance                                  DECIMAL(18,2),
    gross_pay                                  DECIMAL(18,2),
    benefit_deduction                          DECIMAL(18,2),
    employer_benefit_cost                      DECIMAL(18,2),
    tax                                        DECIMAL(18,2),
    employer_tax                               DECIMAL(18,2),
    other_deduction                            DECIMAL(18,2),
    net_pay                                    DECIMAL(18,2),
    total_employer_cost                        DECIMAL(18,2),
    gross_pay_local                            DECIMAL(18,2),
    net_pay_local                              DECIMAL(18,2),
    regular_pay_local                          DECIMAL(18,2)
);
COMMENT ON TABLE fact_payroll IS 'GlobalTech HR Analytics - 1,203,510 rows at tier full';

CREATE OR REPLACE TABLE fact_performance_review (
    review_id                                  INT NOT NULL,
    employee_id                                INT NOT NULL,
    review_year                                INT,
    review_date                                DATE,
    review_period                              STRING,
    performance_rating                         INT,
    performance_rating_label                   STRING,
    potential_rating                           INT,
    goal_score                                 DECIMAL(12,6),
    competency_score                           DECIMAL(12,6),
    overall_score                              DECIMAL(12,6),
    promotion_recommendation                   INT,
    merit_recommendation_pct                   DECIMAL(12,6),
    review_status                              STRING,
    organization_id                            INT NOT NULL,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    manager_employee_id                        INT NOT NULL
);
COMMENT ON TABLE fact_performance_review IS 'GlobalTech HR Analytics - 65,846 rows at tier full';

CREATE OR REPLACE TABLE fact_salary_history (
    salary_history_id                          INT NOT NULL,
    employee_id                                INT NOT NULL,
    effective_date                             DATE,
    change_reason                              STRING,
    salary_amount_local                        DECIMAL(18,2),
    salary_amount_usd                          DECIMAL(18,2),
    prior_salary_usd                           DECIMAL(18,2),
    currency                                   STRING,
    salary_basis                               STRING,
    change_percentage                          DECIMAL(12,6),
    merit_percentage                           DECIMAL(12,6),
    promotion_percentage                       DECIMAL(12,6),
    market_adjustment_percentage               DECIMAL(12,6),
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    organization_id                            INT NOT NULL,
    compa_ratio                                DECIMAL(12,6),
    end_date                                   DATE,
    is_current                                 INT
);
COMMENT ON TABLE fact_salary_history IS 'GlobalTech HR Analytics - 131,997 rows at tier full';

CREATE OR REPLACE TABLE fact_termination (
    termination_id                             INT NOT NULL,
    employee_id                                INT NOT NULL,
    termination_date                           DATE,
    termination_type                           STRING,
    termination_reason                         STRING,
    termination_category                       STRING,
    voluntary_flag                             INT,
    regrettable_flag                           INT,
    years_of_service                           DECIMAL(18,4),
    organization_id                            INT NOT NULL,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    manager_employee_id                        INT NOT NULL,
    location_id                                INT NOT NULL,
    country                                    STRING,
    performance_rating                         INT,
    compa_ratio_at_exit                        DECIMAL(18,4),
    salary_usd_at_exit                         DECIMAL(18,4),
    is_acquired                                INT
);
COMMENT ON TABLE fact_termination IS 'GlobalTech HR Analytics - 6,854 rows at tier full';

CREATE OR REPLACE TABLE fact_workforce_cost_bridge (
    cost_bridge_id                             INT NOT NULL,
    comparison_label                           STRING,
    prior_period_start                         DATE,
    prior_period_end                           DATE,
    current_period_start                       DATE,
    current_period_end                         DATE,
    scope_type                                 STRING,
    scope_name                                 STRING,
    cost_component                             STRING,
    component_order                            INT,
    delta_usd                                  DECIMAL(18,2),
    prior_total_cost_usd                       DECIMAL(18,2),
    current_total_cost_usd                     DECIMAL(18,2),
    contribution_pct                           DECIMAL(12,6),
    is_total                                   INT,
    measured_total_delta_usd                   DECIMAL(18,2)
);
COMMENT ON TABLE fact_workforce_cost_bridge IS 'GlobalTech HR Analytics - 80 rows at tier full';

CREATE OR REPLACE TABLE fact_workforce_risk (
    workforce_risk_id                          INT NOT NULL,
    employee_id                                INT NOT NULL,
    snapshot_date                              DATE,
    organization_id                            INT NOT NULL,
    organization_name                          STRING,
    function_name                              STRING,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    country                                    STRING,
    location_id                                INT NOT NULL,
    manager_employee_id                        INT NOT NULL,
    base_salary_usd                            DECIMAL(18,2),
    compa_ratio                                DECIMAL(12,6),
    performance_rating                         INT,
    tenure_years                               DECIMAL(18,4),
    months_since_promotion                     INT,
    is_acquired                                INT,
    flight_risk_score                          DECIMAL(12,6),
    flight_risk_band                           STRING,
    primary_risk_driver                        STRING,
    is_regrettable_if_lost                     INT
);
COMMENT ON TABLE fact_workforce_risk IS 'GlobalTech HR Analytics - 18,500 rows at tier full';

CREATE OR REPLACE TABLE fact_workforce_snapshot (
    workforce_snapshot_id                      INT NOT NULL,
    employee_id                                INT NOT NULL,
    snapshot_date                              DATE,
    year_month_key                             INT,
    organization_id                            INT NOT NULL,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    career_track                               STRING,
    function_name                              STRING,
    location_id                                INT NOT NULL,
    country                                    STRING,
    manager_employee_id                        INT NOT NULL,
    fte                                        DECIMAL(18,4),
    worker_type                                STRING,
    base_salary_usd                            DECIMAL(18,2),
    base_salary_local                          DECIMAL(18,2),
    currency                                   STRING,
    range_midpoint_usd                         DECIMAL(18,2),
    compa_ratio                                DECIMAL(12,6),
    performance_rating                         INT,
    tenure_years                               DECIMAL(18,4),
    months_since_promotion                     INT,
    is_acquired                                INT,
    is_people_manager                          INT,
    cost_center                                STRING,
    organization_name                          STRING,
    division_name                              STRING,
    department_name                            STRING,
    headcount                                  INT,
    fte_count                                  DECIMAL(18,4),
    manager_chain_l1                           INT,
    manager_chain_l2                           INT,
    manager_chain_l3                           INT,
    manager_chain_l4                           INT,
    manager_chain_l5                           INT,
    manager_chain_l6                           INT,
    reporting_depth                            INT
);
COMMENT ON TABLE fact_workforce_snapshot IS 'GlobalTech HR Analytics - 754,749 rows at tier full';

CREATE OR REPLACE TABLE job_salary_range (
    job_salary_range_id                        INT NOT NULL,
    job_id                                     INT NOT NULL,
    job_level                                  STRING,
    effective_year                             INT,
    geo_zone                                   STRING,
    currency                                   STRING,
    fx_rate_to_usd                             DECIMAL(18,2),
    midpoint_usd                               DECIMAL(18,2),
    minimum_usd                                DECIMAL(18,2),
    maximum_usd                                DECIMAL(18,2),
    minimum_local                              DECIMAL(18,2),
    midpoint_local                             DECIMAL(18,2),
    maximum_local                              DECIMAL(18,2),
    range_spread_pct                           DECIMAL(12,6),
    standard_hours                             DECIMAL(18,4),
    range_movement_pct                         DECIMAL(12,6)
);
COMMENT ON TABLE job_salary_range IS 'GlobalTech HR Analytics - 20,880 rows at tier full';
