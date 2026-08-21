-- Load from an internal stage. Upload the parquet files first:
--   snowsql -q "PUT file://data/full/*.parquet @%o2c_stage AUTO_COMPRESS=FALSE"
USE SCHEMA VANTAGE_O2C.ANALYTICS;
CREATE STAGE IF NOT EXISTS o2c_stage FILE_FORMAT = (TYPE = PARQUET);

COPY INTO contract_pricing FROM @o2c_stage/contract_pricing.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_carrier FROM @o2c_stage/dim_carrier.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_currency FROM @o2c_stage/dim_currency.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_customer FROM @o2c_stage/dim_customer.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_customer_site FROM @o2c_stage/dim_customer_site.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_date FROM @o2c_stage/dim_date.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_exchange_rate FROM @o2c_stage/dim_exchange_rate.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_payment_terms FROM @o2c_stage/dim_payment_terms.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_product FROM @o2c_stage/dim_product.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_sales_rep FROM @o2c_stage/dim_sales_rep.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO dim_warehouse FROM @o2c_stage/dim_warehouse.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_ar_aging_snapshot FROM @o2c_stage/fact_ar_aging_snapshot.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_credit_exposure_snapshot FROM @o2c_stage/fact_credit_exposure_snapshot.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_credit_memo FROM @o2c_stage/fact_credit_memo.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_delivery_event FROM @o2c_stage/fact_delivery_event.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_dispute FROM @o2c_stage/fact_dispute.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_fulfillment FROM @o2c_stage/fact_fulfillment.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_inventory_position FROM @o2c_stage/fact_inventory_position.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_invoice FROM @o2c_stage/fact_invoice.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_invoice_line FROM @o2c_stage/fact_invoice_line.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_o2c_cycle FROM @o2c_stage/fact_o2c_cycle.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_o2c_exception FROM @o2c_stage/fact_o2c_exception.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_order FROM @o2c_stage/fact_order.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_order_line FROM @o2c_stage/fact_order_line.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_payment FROM @o2c_stage/fact_payment.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_payment_allocation FROM @o2c_stage/fact_payment_allocation.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_quote FROM @o2c_stage/fact_quote.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_quote_line FROM @o2c_stage/fact_quote_line.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_return FROM @o2c_stage/fact_return.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_shipment FROM @o2c_stage/fact_shipment.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
COPY INTO fact_shipment_line FROM @o2c_stage/fact_shipment_line.parquet FILE_FORMAT = (TYPE = PARQUET) MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE;
