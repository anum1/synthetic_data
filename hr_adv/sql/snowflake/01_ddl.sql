-- GlobalTech HR Analytics - snowflake DDL
-- Generated from data/full on 2026-08-20. Do not hand-edit:
-- rerun src/emit_ddl.py --tier full instead.

CREATE DATABASE IF NOT EXISTS GLOBALTECH_HR;
CREATE SCHEMA IF NOT EXISTS GLOBALTECH_HR.ANALYTICS;
USE SCHEMA GLOBALTECH_HR.ANALYTICS;

CREATE OR REPLACE TABLE dim_benefit_plan (
    benefit_plan_id                            NUMBER(10,0) NOT NULL,
    plan_code                                  VARCHAR(16),
    benefit_type                               VARCHAR(16),
    plan_name                                  VARCHAR(32),
    provider                                   VARCHAR(32),
    plan_year                                  NUMBER(10,0),
    supports_dependents                        NUMBER(10,0),
    cost_basis                                 VARCHAR(16),
    salary_pct                                 DECIMAL(12,6),
    annual_total_cost_usd                      DECIMAL(18,2),
    annual_employer_cost_usd                   DECIMAL(18,2),
    annual_employee_cost_usd                   DECIMAL(18,2),
    employer_cost_pct_of_salary                DECIMAL(18,4),
    employer_cost_share                        DECIMAL(12,6),
    effective_date                             DATE,
    end_date                                   DATE,
    is_legacy_acquired_plan                    NUMBER(10,0),
    is_active                                  NUMBER(10,0)
,
    CONSTRAINT pk_dim_benefit_plan PRIMARY KEY (benefit_plan_id)
);
COMMENT ON TABLE dim_benefit_plan IS 'GlobalTech HR Analytics - 76 rows at tier full';

CREATE OR REPLACE TABLE dim_date (
    calendar_date                              DATE,
    date_key                                   NUMBER(10,0) NOT NULL,
    day_of_week                                NUMBER(10,0),
    day_name                                   VARCHAR(16),
    day_of_month                               NUMBER(10,0),
    day_of_year                                NUMBER(10,0),
    week_of_year                               NUMBER(10,0),
    month_number                               NUMBER(10,0),
    month_name                                 VARCHAR(16),
    month_abbr                                 VARCHAR(16),
    quarter_number                             NUMBER(10,0),
    quarter_name                               VARCHAR(16),
    calendar_year                              NUMBER(10,0),
    year_month_key                             NUMBER(10,0),
    year_month_name                            VARCHAR(16),
    year_quarter_name                          VARCHAR(16),
    month_start_date                           DATE,
    month_end_date                             DATE,
    is_month_end                               NUMBER(10,0),
    is_weekend                                 NUMBER(10,0),
    fiscal_year                                NUMBER(10,0),
    fiscal_month_number                        NUMBER(10,0),
    fiscal_quarter_number                      NUMBER(10,0),
    fiscal_quarter_name                        VARCHAR(16),
    fiscal_period_key                          NUMBER(10,0),
    is_holiday_us                              NUMBER(10,0),
    is_working_day_us                          NUMBER(10,0),
    is_holiday_canada                          NUMBER(10,0),
    is_working_day_canada                      NUMBER(10,0),
    is_holiday_uk                              NUMBER(10,0),
    is_working_day_uk                          NUMBER(10,0),
    is_holiday_germany                         NUMBER(10,0),
    is_working_day_germany                     NUMBER(10,0),
    is_holiday_india                           NUMBER(10,0),
    is_working_day_india                       NUMBER(10,0),
    is_holiday_japan                           NUMBER(10,0),
    is_working_day_japan                       NUMBER(10,0),
    is_holiday_any                             NUMBER(10,0),
    holiday_name_us                            VARCHAR(32),
    days_from_as_of                            NUMBER(10,0),
    months_from_as_of                          NUMBER(10,0),
    is_current_year                            NUMBER(10,0),
    is_prior_year                              NUMBER(10,0),
    is_last_12_months                          NUMBER(10,0),
    is_ytd                                     NUMBER(10,0)
,
    CONSTRAINT pk_dim_date PRIMARY KEY (date_key)
);
COMMENT ON TABLE dim_date IS 'GlobalTech HR Analytics - 1,308 rows at tier full';

CREATE OR REPLACE TABLE dim_employee (
    employee_id                                NUMBER(10,0) NOT NULL,
    first_name                                 VARCHAR(16),
    last_name                                  VARCHAR(16),
    country                                    VARCHAR(16),
    location_id                                NUMBER(10,0) NOT NULL,
    organization_id                            NUMBER(10,0) NOT NULL,
    function_name                              VARCHAR(32),
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    career_track                               VARCHAR(32),
    manager_employee_id                        NUMBER(10,0) NOT NULL,
    hire_date                                  DATE,
    termination_date                           DATE,
    employment_status                          VARCHAR(16),
    worker_type                                VARCHAR(16),
    fte                                        DECIMAL(18,4),
    base_salary_local                          DECIMAL(18,2),
    base_salary_usd                            DECIMAL(18,2),
    currency                                   VARCHAR(16),
    performance_rating                         NUMBER(10,0),
    birth_date                                 DATE,
    is_acquired                                NUMBER(10,0),
    employee_number                            VARCHAR(16),
    employment_type                            VARCHAR(16),
    pay_frequency                              VARCHAR(16),
    cost_center                                VARCHAR(16),
    exempt_status                              VARCHAR(16),
    city                                       VARCHAR(16),
    state_province                             VARCHAR(32),
    region                                     VARCHAR(16),
    organization_name                          VARCHAR(48),
    division_name                              VARCHAR(32),
    department_name                            VARCHAR(32),
    is_people_manager                          NUMBER(10,0),
    tenure_years                               DECIMAL(18,4),
    age_years                                  DECIMAL(18,4),
    age_band                                   VARCHAR(16),
    tenure_band                                VARCHAR(16),
    work_email                                 VARCHAR(48),
    is_active                                  NUMBER(10,0),
    is_duplicate_record                        NUMBER(10,0)
,
    CONSTRAINT pk_dim_employee PRIMARY KEY (employee_id)
);
ALTER TABLE dim_employee ADD CONSTRAINT fk_dim_employee_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE dim_employee ADD CONSTRAINT fk_dim_employee_location_id FOREIGN KEY (location_id) REFERENCES dim_location(location_id);
ALTER TABLE dim_employee ADD CONSTRAINT fk_dim_employee_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE dim_employee IS 'GlobalTech HR Analytics - 25,367 rows at tier full';

CREATE OR REPLACE TABLE dim_job (
    job_id                                     NUMBER(10,0) NOT NULL,
    job_family                                 VARCHAR(32),
    job_subfamily                              VARCHAR(32),
    function_name                              VARCHAR(32),
    job_level                                  VARCHAR(16),
    career_track                               VARCHAR(32),
    management_level                           VARCHAR(32),
    job_title                                  VARCHAR(64),
    is_people_manager                          NUMBER(10,0),
    job_code                                   VARCHAR(16),
    job_family_premium                         DECIMAL(18,4),
    exempt_status                              VARCHAR(16),
    job_profile_status                         VARCHAR(16),
    effective_date                             DATE
,
    CONSTRAINT pk_dim_job PRIMARY KEY (job_id)
);
COMMENT ON TABLE dim_job IS 'GlobalTech HR Analytics - 870 rows at tier full';

CREATE OR REPLACE TABLE dim_location (
    location_id                                NUMBER(10,0) NOT NULL,
    location_code                              VARCHAR(32),
    location_name                              VARCHAR(32),
    site_type                                  VARCHAR(32),
    city                                       VARCHAR(16),
    state_province                             VARCHAR(32),
    country                                    VARCHAR(16),
    country_iso                                VARCHAR(16),
    region                                     VARCHAR(16),
    geo_zone                                   VARCHAR(16),
    currency                                   VARCHAR(16),
    pay_frequency                              VARCHAR(16),
    is_hub                                     NUMBER(10,0),
    is_remote_hub                              NUMBER(10,0),
    headcount_capacity                         NUMBER(10,0),
    opened_date                                DATE,
    is_active                                  NUMBER(10,0)
,
    CONSTRAINT pk_dim_location PRIMARY KEY (location_id)
);
COMMENT ON TABLE dim_location IS 'GlobalTech HR Analytics - 253 rows at tier full';

CREATE OR REPLACE TABLE dim_organization (
    organization_id                            NUMBER(10,0) NOT NULL,
    organization_code                          VARCHAR(16),
    organization_name                          VARCHAR(48),
    organization_type                          VARCHAR(16),
    parent_organization_id                     NUMBER(10,0),
    org_level_1                                VARCHAR(16),
    org_level_2                                VARCHAR(32),
    org_level_3                                VARCHAR(32),
    org_level_4                                VARCHAR(32),
    org_level_5                                VARCHAR(32),
    org_level_6                                VARCHAR(48),
    org_depth                                  NUMBER(10,0),
    org_path                                   VARCHAR(160),
    business_unit                              VARCHAR(32),
    function_name                              VARCHAR(32),
    division_name                              VARCHAR(32),
    department_name                            VARCHAR(32),
    cost_center                                VARCHAR(16),
    effective_date                             DATE,
    is_leaf                                    NUMBER(10,0),
    is_active                                  NUMBER(10,0),
    inactive_date                              DATE,
    manager_employee_id                        NUMBER(10,0) NOT NULL
,
    CONSTRAINT pk_dim_organization PRIMARY KEY (organization_id)
);
ALTER TABLE dim_organization ADD CONSTRAINT fk_dim_organization_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
COMMENT ON TABLE dim_organization IS 'GlobalTech HR Analytics - 800 rows at tier full';

CREATE OR REPLACE TABLE dim_pay_calendar (
    pay_period_id                              NUMBER(10,0) NOT NULL,
    pay_frequency                              VARCHAR(16),
    pay_group_countries                        VARCHAR(32),
    pay_period_start                           DATE,
    pay_period_end                             DATE,
    pay_date                                   DATE,
    periods_per_year                           NUMBER(10,0),
    year_month_key                             NUMBER(10,0),
    pay_period_name                            VARCHAR(16)
,
    CONSTRAINT pk_dim_pay_calendar PRIMARY KEY (pay_period_id)
);
COMMENT ON TABLE dim_pay_calendar IS 'GlobalTech HR Analytics - 137 rows at tier full';

CREATE OR REPLACE TABLE fact_absence (
    absence_id                                 NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    organization_id                            NUMBER(10,0) NOT NULL,
    country                                    VARCHAR(16),
    absence_type                               VARCHAR(16),
    start_date                                 DATE,
    end_date                                   DATE,
    year_month_key                             NUMBER(10,0),
    calendar_days                              NUMBER(10,0),
    absence_days                               NUMBER(10,0),
    absence_hours                              DECIMAL(18,4),
    is_paid                                    NUMBER(10,0),
    unpaid_hours                               DECIMAL(18,4),
    absence_status                             VARCHAR(16)
,
    CONSTRAINT pk_fact_absence PRIMARY KEY (absence_id)
);
ALTER TABLE fact_absence ADD CONSTRAINT fk_fact_absence_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_absence ADD CONSTRAINT fk_fact_absence_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
COMMENT ON TABLE fact_absence IS 'GlobalTech HR Analytics - 517,842 rows at tier full';

CREATE OR REPLACE TABLE fact_benefit_enrollment (
    benefit_enrollment_id                      NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    benefit_plan_id                            NUMBER(10,0) NOT NULL,
    plan_year                                  NUMBER(10,0),
    benefit_type                               VARCHAR(16),
    plan_name                                  VARCHAR(32),
    coverage_level                             VARCHAR(32),
    annual_employee_contribution_usd           DECIMAL(18,2),
    annual_employer_contribution_usd           DECIMAL(18,2),
    annual_total_cost_usd                      DECIMAL(18,2),
    months_covered                             NUMBER(10,0),
    prorated_employee_contribution_usd         DECIMAL(18,2),
    prorated_employer_contribution_usd         DECIMAL(18,2),
    organization_id                            NUMBER(10,0) NOT NULL,
    country                                    VARCHAR(16),
    is_acquired                                NUMBER(10,0),
    effective_date                             DATE,
    end_date                                   DATE,
    enrollment_status                          VARCHAR(16),
    enrollment_reason                          VARCHAR(16),
    monthly_employee_contribution_usd          DECIMAL(18,2),
    monthly_employer_contribution_usd          DECIMAL(18,2)
,
    CONSTRAINT pk_fact_benefit_enrollment PRIMARY KEY (benefit_enrollment_id)
);
ALTER TABLE fact_benefit_enrollment ADD CONSTRAINT fk_fact_benefit_enrollment_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_benefit_enrollment ADD CONSTRAINT fk_fact_benefit_enrollment_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_benefit_enrollment ADD CONSTRAINT fk_fact_benefit_enrollment_benefit_plan_id FOREIGN KEY (benefit_plan_id) REFERENCES dim_benefit_plan(benefit_plan_id);
COMMENT ON TABLE fact_benefit_enrollment IS 'GlobalTech HR Analytics - 235,025 rows at tier full';

CREATE OR REPLACE TABLE fact_bonus (
    bonus_id                                   NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    bonus_type                                 VARCHAR(32),
    plan_year                                  NUMBER(10,0),
    payout_date                                DATE,
    target_pct                                 DECIMAL(12,6),
    target_amount_usd                          DECIMAL(18,2),
    payout_factor                              DECIMAL(12,6),
    bonus_amount_usd                           DECIMAL(18,2),
    currency                                   VARCHAR(16),
    organization_id                            NUMBER(10,0) NOT NULL,
    performance_rating                         NUMBER(10,0),
    is_acquired                                NUMBER(10,0),
    bonus_amount_local                         DECIMAL(18,2),
    target_amount_local                        DECIMAL(18,2),
    year_month_key                             NUMBER(10,0),
    award_date                                 DATE
,
    CONSTRAINT pk_fact_bonus PRIMARY KEY (bonus_id)
);
ALTER TABLE fact_bonus ADD CONSTRAINT fk_fact_bonus_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_bonus ADD CONSTRAINT fk_fact_bonus_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
COMMENT ON TABLE fact_bonus IS 'GlobalTech HR Analytics - 61,737 rows at tier full';

CREATE OR REPLACE TABLE fact_job_history (
    job_history_id                             NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    effective_date                             DATE,
    action                                     VARCHAR(16),
    reason                                     VARCHAR(32),
    old_job_id                                 NUMBER(10,0),
    new_job_id                                 NUMBER(10,0),
    old_job_level                              VARCHAR(16),
    new_job_level                              VARCHAR(16),
    old_organization_id                        NUMBER(10,0),
    new_organization_id                        NUMBER(10,0),
    old_manager_employee_id                    NUMBER(10,0),
    new_manager_employee_id                    NUMBER(10,0),
    old_location_id                            NUMBER(10,0),
    new_location_id                            NUMBER(10,0),
    salary_usd                                 DECIMAL(18,2)
,
    CONSTRAINT pk_fact_job_history PRIMARY KEY (job_history_id)
);
ALTER TABLE fact_job_history ADD CONSTRAINT fk_fact_job_history_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
COMMENT ON TABLE fact_job_history IS 'GlobalTech HR Analytics - 55,170 rows at tier full';

CREATE OR REPLACE TABLE fact_manager_scorecard (
    manager_scorecard_id                       NUMBER(10,0) NOT NULL,
    manager_employee_id                        NUMBER(10,0) NOT NULL,
    org_headcount_months                       NUMBER(10,0),
    months_active                              NUMBER(10,0),
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
    manager_organization_id                    NUMBER(10,0),
    manager_job_level                          VARCHAR(16),
    manager_country                            VARCHAR(16),
    manager_name                               VARCHAR(32),
    manager_function                           VARCHAR(32),
    function_attrition_rate                    DECIMAL(12,6),
    excess_attrition_vs_function               DECIMAL(18,4),
    company_attrition_rate                     DECIMAL(12,6),
    manager_risk_score                         DECIMAL(12,6),
    manager_risk_band                          VARCHAR(16),
    period_start                               DATE,
    period_end                                 DATE
,
    CONSTRAINT pk_fact_manager_scorecard PRIMARY KEY (manager_scorecard_id)
);
ALTER TABLE fact_manager_scorecard ADD CONSTRAINT fk_fact_manager_scorecard_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
COMMENT ON TABLE fact_manager_scorecard IS 'GlobalTech HR Analytics - 802 rows at tier full';

CREATE OR REPLACE TABLE fact_payroll (
    payroll_id                                 NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    year_month_key                             NUMBER(10,0),
    organization_id                            NUMBER(10,0) NOT NULL,
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    function_name                              VARCHAR(32),
    country                                    VARCHAR(16),
    location_id                                NUMBER(10,0) NOT NULL,
    base_salary_usd                            DECIMAL(18,2),
    fte                                        DECIMAL(18,4),
    currency                                   VARCHAR(16),
    cost_center                                VARCHAR(16),
    manager_employee_id                        NUMBER(10,0) NOT NULL,
    is_acquired                                NUMBER(10,0),
    pay_frequency                              VARCHAR(16),
    pay_period_id                              NUMBER(10,0) NOT NULL,
    pay_period_start                           DATE,
    pay_period_end                             DATE,
    pay_date                                   DATE,
    periods_per_year                           NUMBER(10,0),
    exempt_status                              VARCHAR(16),
    regular_hours                              DECIMAL(18,4),
    unpaid_hours                               DECIMAL(18,4),
    regular_pay                                DECIMAL(18,2),
    is_payroll_anomaly                         NUMBER(10,0),
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
,
    CONSTRAINT pk_fact_payroll PRIMARY KEY (payroll_id)
);
ALTER TABLE fact_payroll ADD CONSTRAINT fk_fact_payroll_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_payroll ADD CONSTRAINT fk_fact_payroll_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_payroll ADD CONSTRAINT fk_fact_payroll_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_payroll ADD CONSTRAINT fk_fact_payroll_location_id FOREIGN KEY (location_id) REFERENCES dim_location(location_id);
ALTER TABLE fact_payroll ADD CONSTRAINT fk_fact_payroll_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
ALTER TABLE fact_payroll ADD CONSTRAINT fk_fact_payroll_pay_period_id FOREIGN KEY (pay_period_id) REFERENCES dim_pay_calendar(pay_period_id);
COMMENT ON TABLE fact_payroll IS 'GlobalTech HR Analytics - 1,203,510 rows at tier full';

CREATE OR REPLACE TABLE fact_performance_review (
    review_id                                  NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    review_year                                NUMBER(10,0),
    review_date                                DATE,
    review_period                              VARCHAR(16),
    performance_rating                         NUMBER(10,0),
    performance_rating_label                   VARCHAR(32),
    potential_rating                           NUMBER(10,0),
    goal_score                                 DECIMAL(12,6),
    competency_score                           DECIMAL(12,6),
    overall_score                              DECIMAL(12,6),
    promotion_recommendation                   NUMBER(10,0),
    merit_recommendation_pct                   DECIMAL(12,6),
    review_status                              VARCHAR(16),
    organization_id                            NUMBER(10,0) NOT NULL,
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    manager_employee_id                        NUMBER(10,0) NOT NULL
,
    CONSTRAINT pk_fact_performance_review PRIMARY KEY (review_id)
);
ALTER TABLE fact_performance_review ADD CONSTRAINT fk_fact_performance_review_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_performance_review ADD CONSTRAINT fk_fact_performance_review_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_performance_review ADD CONSTRAINT fk_fact_performance_review_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_performance_review ADD CONSTRAINT fk_fact_performance_review_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE fact_performance_review IS 'GlobalTech HR Analytics - 65,846 rows at tier full';

CREATE OR REPLACE TABLE fact_salary_history (
    salary_history_id                          NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    effective_date                             DATE,
    change_reason                              VARCHAR(32),
    salary_amount_local                        DECIMAL(18,2),
    salary_amount_usd                          DECIMAL(18,2),
    prior_salary_usd                           DECIMAL(18,2),
    currency                                   VARCHAR(16),
    salary_basis                               VARCHAR(16),
    change_percentage                          DECIMAL(12,6),
    merit_percentage                           DECIMAL(12,6),
    promotion_percentage                       DECIMAL(12,6),
    market_adjustment_percentage               DECIMAL(12,6),
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    organization_id                            NUMBER(10,0) NOT NULL,
    compa_ratio                                DECIMAL(12,6),
    end_date                                   DATE,
    is_current                                 NUMBER(10,0)
,
    CONSTRAINT pk_fact_salary_history PRIMARY KEY (salary_history_id)
);
ALTER TABLE fact_salary_history ADD CONSTRAINT fk_fact_salary_history_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_salary_history ADD CONSTRAINT fk_fact_salary_history_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_salary_history ADD CONSTRAINT fk_fact_salary_history_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE fact_salary_history IS 'GlobalTech HR Analytics - 131,997 rows at tier full';

CREATE OR REPLACE TABLE fact_termination (
    termination_id                             NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    termination_date                           DATE,
    termination_type                           VARCHAR(16),
    termination_reason                         VARCHAR(32),
    termination_category                       VARCHAR(16),
    voluntary_flag                             NUMBER(10,0),
    regrettable_flag                           NUMBER(10,0),
    years_of_service                           DECIMAL(18,4),
    organization_id                            NUMBER(10,0) NOT NULL,
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    manager_employee_id                        NUMBER(10,0) NOT NULL,
    location_id                                NUMBER(10,0) NOT NULL,
    country                                    VARCHAR(16),
    performance_rating                         NUMBER(10,0),
    compa_ratio_at_exit                        DECIMAL(18,4),
    salary_usd_at_exit                         DECIMAL(18,4),
    is_acquired                                NUMBER(10,0)
,
    CONSTRAINT pk_fact_termination PRIMARY KEY (termination_id)
);
ALTER TABLE fact_termination ADD CONSTRAINT fk_fact_termination_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_termination ADD CONSTRAINT fk_fact_termination_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_termination ADD CONSTRAINT fk_fact_termination_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_termination ADD CONSTRAINT fk_fact_termination_location_id FOREIGN KEY (location_id) REFERENCES dim_location(location_id);
ALTER TABLE fact_termination ADD CONSTRAINT fk_fact_termination_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE fact_termination IS 'GlobalTech HR Analytics - 6,854 rows at tier full';

CREATE OR REPLACE TABLE fact_workforce_cost_bridge (
    cost_bridge_id                             NUMBER(10,0) NOT NULL,
    comparison_label                           VARCHAR(48),
    prior_period_start                         DATE,
    prior_period_end                           DATE,
    current_period_start                       DATE,
    current_period_end                         DATE,
    scope_type                                 VARCHAR(16),
    scope_name                                 VARCHAR(32),
    cost_component                             VARCHAR(32),
    component_order                            NUMBER(10,0),
    delta_usd                                  DECIMAL(18,2),
    prior_total_cost_usd                       DECIMAL(18,2),
    current_total_cost_usd                     DECIMAL(18,2),
    contribution_pct                           DECIMAL(12,6),
    is_total                                   NUMBER(10,0),
    measured_total_delta_usd                   DECIMAL(18,2)
,
    CONSTRAINT pk_fact_workforce_cost_bridge PRIMARY KEY (cost_bridge_id)
);
COMMENT ON TABLE fact_workforce_cost_bridge IS 'GlobalTech HR Analytics - 80 rows at tier full';

CREATE OR REPLACE TABLE fact_workforce_risk (
    workforce_risk_id                          NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    snapshot_date                              DATE,
    organization_id                            NUMBER(10,0) NOT NULL,
    organization_name                          VARCHAR(48),
    function_name                              VARCHAR(32),
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    country                                    VARCHAR(16),
    location_id                                NUMBER(10,0) NOT NULL,
    manager_employee_id                        NUMBER(10,0) NOT NULL,
    base_salary_usd                            DECIMAL(18,2),
    compa_ratio                                DECIMAL(12,6),
    performance_rating                         NUMBER(10,0),
    tenure_years                               DECIMAL(18,4),
    months_since_promotion                     NUMBER(10,0),
    is_acquired                                NUMBER(10,0),
    flight_risk_score                          DECIMAL(12,6),
    flight_risk_band                           VARCHAR(16),
    primary_risk_driver                        VARCHAR(32),
    is_regrettable_if_lost                     NUMBER(10,0)
,
    CONSTRAINT pk_fact_workforce_risk PRIMARY KEY (workforce_risk_id)
);
ALTER TABLE fact_workforce_risk ADD CONSTRAINT fk_fact_workforce_risk_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_workforce_risk ADD CONSTRAINT fk_fact_workforce_risk_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_workforce_risk ADD CONSTRAINT fk_fact_workforce_risk_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_workforce_risk ADD CONSTRAINT fk_fact_workforce_risk_location_id FOREIGN KEY (location_id) REFERENCES dim_location(location_id);
ALTER TABLE fact_workforce_risk ADD CONSTRAINT fk_fact_workforce_risk_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE fact_workforce_risk IS 'GlobalTech HR Analytics - 18,500 rows at tier full';

CREATE OR REPLACE TABLE fact_workforce_snapshot (
    workforce_snapshot_id                      NUMBER(10,0) NOT NULL,
    employee_id                                NUMBER(10,0) NOT NULL,
    snapshot_date                              DATE,
    year_month_key                             NUMBER(10,0),
    organization_id                            NUMBER(10,0) NOT NULL,
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    career_track                               VARCHAR(32),
    function_name                              VARCHAR(32),
    location_id                                NUMBER(10,0) NOT NULL,
    country                                    VARCHAR(16),
    manager_employee_id                        NUMBER(10,0) NOT NULL,
    fte                                        DECIMAL(18,4),
    worker_type                                VARCHAR(16),
    base_salary_usd                            DECIMAL(18,2),
    base_salary_local                          DECIMAL(18,2),
    currency                                   VARCHAR(16),
    range_midpoint_usd                         DECIMAL(18,2),
    compa_ratio                                DECIMAL(12,6),
    performance_rating                         NUMBER(10,0),
    tenure_years                               DECIMAL(18,4),
    months_since_promotion                     NUMBER(10,0),
    is_acquired                                NUMBER(10,0),
    is_people_manager                          NUMBER(10,0),
    cost_center                                VARCHAR(16),
    organization_name                          VARCHAR(48),
    division_name                              VARCHAR(32),
    department_name                            VARCHAR(32),
    headcount                                  NUMBER(10,0),
    fte_count                                  DECIMAL(18,4),
    manager_chain_l1                           NUMBER(10,0),
    manager_chain_l2                           NUMBER(10,0),
    manager_chain_l3                           NUMBER(10,0),
    manager_chain_l4                           NUMBER(10,0),
    manager_chain_l5                           NUMBER(10,0),
    manager_chain_l6                           NUMBER(10,0),
    reporting_depth                            NUMBER(10,0)
,
    CONSTRAINT pk_fact_workforce_snapshot PRIMARY KEY (workforce_snapshot_id)
);
ALTER TABLE fact_workforce_snapshot ADD CONSTRAINT fk_fact_workforce_snapshot_employee_id FOREIGN KEY (employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_workforce_snapshot ADD CONSTRAINT fk_fact_workforce_snapshot_manager_employee_id FOREIGN KEY (manager_employee_id) REFERENCES dim_employee(employee_id);
ALTER TABLE fact_workforce_snapshot ADD CONSTRAINT fk_fact_workforce_snapshot_organization_id FOREIGN KEY (organization_id) REFERENCES dim_organization(organization_id);
ALTER TABLE fact_workforce_snapshot ADD CONSTRAINT fk_fact_workforce_snapshot_location_id FOREIGN KEY (location_id) REFERENCES dim_location(location_id);
ALTER TABLE fact_workforce_snapshot ADD CONSTRAINT fk_fact_workforce_snapshot_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE fact_workforce_snapshot IS 'GlobalTech HR Analytics - 754,749 rows at tier full';

CREATE OR REPLACE TABLE job_salary_range (
    job_salary_range_id                        NUMBER(10,0) NOT NULL,
    job_id                                     NUMBER(10,0) NOT NULL,
    job_level                                  VARCHAR(16),
    effective_year                             NUMBER(10,0),
    geo_zone                                   VARCHAR(16),
    currency                                   VARCHAR(16),
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
,
    CONSTRAINT pk_job_salary_range PRIMARY KEY (job_salary_range_id)
);
ALTER TABLE job_salary_range ADD CONSTRAINT fk_job_salary_range_job_id FOREIGN KEY (job_id) REFERENCES dim_job(job_id);
COMMENT ON TABLE job_salary_range IS 'GlobalTech HR Analytics - 20,880 rows at tier full';
