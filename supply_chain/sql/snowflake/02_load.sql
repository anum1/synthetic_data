-- Meridian Global Industries | Supply Chain Control Tower
-- Load parquet into Snowflake.

USE SCHEMA MERIDIAN.SUPPLY_CHAIN;

CREATE OR REPLACE FILE FORMAT mgi_parquet TYPE = PARQUET;
CREATE OR REPLACE STAGE mgi_stage FILE_FORMAT = mgi_parquet;

-- From a local machine (SnowSQL only), for the 'full' tier:
--   PUT file://<abs-path>/data/full/*.parquet @mgi_stage AUTO_COMPRESS=FALSE;
-- Or point the stage at your own S3/Azure/GCS location instead.

COPY INTO dim_carrier
  FROM @mgi_stage/dim_carrier.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_customer
  FROM @mgi_stage/dim_customer.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_date
  FROM @mgi_stage/dim_date.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_employee
  FROM @mgi_stage/dim_employee.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_location
  FROM @mgi_stage/dim_location.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_product
  FROM @mgi_stage/dim_product.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_product_category
  FROM @mgi_stage/dim_product_category.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_region
  FROM @mgi_stage/dim_region.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO dim_supplier
  FROM @mgi_stage/dim_supplier.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_demand_signal
  FROM @mgi_stage/fact_demand_signal.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_financial_impact
  FROM @mgi_stage/fact_financial_impact.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_forecast
  FROM @mgi_stage/fact_forecast.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_inventory_snapshot
  FROM @mgi_stage/fact_inventory_snapshot.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_production
  FROM @mgi_stage/fact_production.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_purchase_order
  FROM @mgi_stage/fact_purchase_order.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_sales_order_line
  FROM @mgi_stage/fact_sales_order_line.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_shipment
  FROM @mgi_stage/fact_shipment.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_supplier_delivery
  FROM @mgi_stage/fact_supplier_delivery.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

COPY INTO fact_supply_chain_risk
  FROM @mgi_stage/fact_supply_chain_risk.parquet
  FILE_FORMAT = (FORMAT_NAME = mgi_parquet)
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT;

-- Sanity check: the executive KPI row. Note the snapshot_grain filter --
-- fact_inventory_snapshot holds weekly history AND a daily recent window,
-- and summing across both grains double-counts every inventory measure.
SELECT ROUND(AVG(daily_value) / 1e6, 1) AS inventory_musd,
       ROUND(AVG(stockout) * 100, 1)    AS stockout_pct
FROM  (SELECT snapshot_date,
              SUM(inventory_value) AS daily_value,
              AVG(CAST(stockout_flag AS DOUBLE)) AS stockout
       FROM   fact_inventory_snapshot
       WHERE  snapshot_grain = 'D'
       GROUP  BY snapshot_date) t;