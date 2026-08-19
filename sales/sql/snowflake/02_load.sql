-- Load parquet into Snowflake.
-- 1. Put the files somewhere Snowflake can read them.
-- 2. Run this script.

USE SCHEMA APEXTECH.SALES;

CREATE OR REPLACE FILE FORMAT apex_parquet TYPE = PARQUET;
CREATE OR REPLACE STAGE apex_stage FILE_FORMAT = apex_parquet;

-- From a local machine (SnowSQL only), for the 'full' tier:
--   PUT file://<abs-path>/data/full/*.parquet @apex_stage AUTO_COMPRESS=FALSE;
-- Or point the stage at your own S3/Azure/GCS location instead.

COPY INTO dim_channel
  FROM @apex_stage/dim_channel.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_country
  FROM @apex_stage/dim_country.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_currency
  FROM @apex_stage/dim_currency.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_customer
  FROM @apex_stage/dim_customer.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_date
  FROM @apex_stage/dim_date.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_exchange_rate
  FROM @apex_stage/dim_exchange_rate.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_location
  FROM @apex_stage/dim_location.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_product
  FROM @apex_stage/dim_product.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_product_category
  FROM @apex_stage/dim_product_category.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_promotion
  FROM @apex_stage/dim_promotion.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_sales_rep
  FROM @apex_stage/dim_sales_rep.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_supplier
  FROM @apex_stage/dim_supplier.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_budget
  FROM @apex_stage/fact_budget.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_forecast
  FROM @apex_stage/fact_forecast.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_inventory
  FROM @apex_stage/fact_inventory.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_returns
  FROM @apex_stage/fact_returns.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_sales_order
  FROM @apex_stage/fact_sales_order.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_sales_order_line
  FROM @apex_stage/fact_sales_order_line.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_sales_rep_quota
  FROM @apex_stage/fact_sales_rep_quota.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_supplier_performance
  FROM @apex_stage/fact_supplier_performance.parquet
  FILE_FORMAT = (FORMAT_NAME = apex_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

-- Sanity check: these three numbers drive the executive KPI row.
SELECT COUNT(*) AS order_lines,
       ROUND(SUM(net_sales)   / 1e6, 1) AS net_sales_musd,
       ROUND(SUM(gross_profit) / 1e6, 1) AS gross_profit_musd
FROM   fact_sales_order_line;