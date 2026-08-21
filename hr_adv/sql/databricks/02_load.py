# Databricks notebook: load the parquet files into the tables.
# Upload data/full to a volume or DBFS path, then set SOURCE below.
SOURCE = "dbfs:/FileStore/globaltech_hr/full"
spark.sql("USE GLOBALTECH_HR.ANALYTICS")

for table in ["dim_benefit_plan", "dim_date", "dim_employee", "dim_job", "dim_location", "dim_organization", "dim_pay_calendar", "fact_absence", "fact_benefit_enrollment", "fact_bonus", "fact_job_history", "fact_manager_scorecard", "fact_payroll", "fact_performance_review", "fact_salary_history", "fact_termination", "fact_workforce_cost_bridge", "fact_workforce_risk", "fact_workforce_snapshot", "job_salary_range"]:
    (spark.read.parquet(f"{SOURCE}/{table}.parquet")
        .write.mode("overwrite").saveAsTable(table))
    print(table, spark.table(table).count())
