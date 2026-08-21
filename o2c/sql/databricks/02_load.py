# Databricks notebook: load the parquet files into the tables.
# Upload data/full to a volume or DBFS path, then set SOURCE below.
SOURCE = "dbfs:/FileStore/vantage_o2c/full"
spark.sql("USE VANTAGE_O2C.ANALYTICS")

for table in ["contract_pricing", "dim_carrier", "dim_currency", "dim_customer", "dim_customer_site", "dim_date", "dim_exchange_rate", "dim_payment_terms", "dim_product", "dim_sales_rep", "dim_warehouse", "fact_ar_aging_snapshot", "fact_credit_exposure_snapshot", "fact_credit_memo", "fact_delivery_event", "fact_dispute", "fact_fulfillment", "fact_inventory_position", "fact_invoice", "fact_invoice_line", "fact_o2c_cycle", "fact_o2c_exception", "fact_order", "fact_order_line", "fact_payment", "fact_payment_allocation", "fact_quote", "fact_quote_line", "fact_return", "fact_shipment", "fact_shipment_line"]:
    (spark.read.parquet(f"{SOURCE}/{table}.parquet")
        .write.mode("overwrite").saveAsTable(table))
    print(table, spark.table(table).count())
