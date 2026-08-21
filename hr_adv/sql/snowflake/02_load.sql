-- Load from an internal stage. Upload the parquet files first:
--   snowsql -q "PUT file://data/full/*.parquet @%hr_stage AUTO_COMPRESS=FALSE"
USE SCHEMA GLOBALTECH_HR.ANALYTICS;
CREATE STAGE IF NOT EXISTS hr_stage FILE_FORMAT = (TYPE = PARQUET);

COPY INTO dim_benefit_plan FROM @hr_stage/dim_benefit_plan.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_date FROM @hr_stage/dim_date.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_employee FROM @hr_stage/dim_employee.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_job FROM @hr_stage/dim_job.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_location FROM @hr_stage/dim_location.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_organization FROM @hr_stage/dim_organization.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_pay_calendar FROM @hr_stage/dim_pay_calendar.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_absence FROM @hr_stage/fact_absence.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_benefit_enrollment FROM @hr_stage/fact_benefit_enrollment.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_bonus FROM @hr_stage/fact_bonus.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_job_history FROM @hr_stage/fact_job_history.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_manager_scorecard FROM @hr_stage/fact_manager_scorecard.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_payroll FROM @hr_stage/fact_payroll.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_performance_review FROM @hr_stage/fact_performance_review.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_salary_history FROM @hr_stage/fact_salary_history.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_termination FROM @hr_stage/fact_termination.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_workforce_cost_bridge FROM @hr_stage/fact_workforce_cost_bridge.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_workforce_risk FROM @hr_stage/fact_workforce_risk.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_workforce_snapshot FROM @hr_stage/fact_workforce_snapshot.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO job_salary_range FROM @hr_stage/job_salary_range.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
