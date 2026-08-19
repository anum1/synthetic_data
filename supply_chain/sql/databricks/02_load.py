"""Load the Meridian parquet files into Unity Catalog.

Run as a Databricks notebook or with databricks-connect. Upload the parquet
directory to a volume first, e.g.:

    databricks fs cp -r data/full dbfs:/Volumes/meridian/supply_chain/raw/
"""

CATALOG = "meridian"
SCHEMA = "supply_chain"
SOURCE = "/Volumes/meridian/supply_chain/raw"        # adjust to your volume

TABLES = ['dim_carrier', 'dim_customer', 'dim_date', 'dim_employee', 'dim_location', 'dim_product', 'dim_product_category', 'dim_region', 'dim_supplier', 'fact_demand_signal', 'fact_financial_impact', 'fact_forecast', 'fact_inventory_snapshot', 'fact_production', 'fact_purchase_order', 'fact_sales_order_line', 'fact_shipment', 'fact_supplier_delivery', 'fact_supply_chain_risk']

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

for table in TABLES:
    df = spark.read.parquet(f"{SOURCE}/{table}.parquet")
    (df.write
       .mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(f"{CATALOG}.{SCHEMA}.{table}"))
    print(f"loaded {table}: {df.count():,} rows")

# Liquid clustering on the tables that carry the analytical load.
for table, keys in {'fact_inventory_snapshot': ['year_month_key', 'product_id'], 'fact_forecast': ['year_month_key', 'product_id'], 'fact_demand_signal': ['year_month_key', 'product_id'], 'fact_purchase_order': ['year_month_key', 'supplier_id'], 'fact_supplier_delivery': ['year_month_key', 'supplier_id'], 'fact_sales_order_line': ['year_month_key', 'product_id'], 'fact_shipment': ['year_month_key', 'carrier_id'], 'fact_production': ['year_month_key', 'product_id'], 'fact_supply_chain_risk': ['year_month_key']}.items():
    spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.{table} "
              f"CLUSTER BY ({', '.join(keys)})")

# The snapshot_grain filter is not optional: the table holds weekly history
# AND a daily recent window, so summing across both double-counts inventory.
spark.sql(f"""
    SELECT ROUND(AVG(daily_value) / 1e6, 1) AS inventory_musd,
           ROUND(AVG(stockout) * 100, 1)    AS stockout_pct
    FROM  (SELECT snapshot_date,
                  SUM(inventory_value)               AS daily_value,
                  AVG(CAST(stockout_flag AS DOUBLE)) AS stockout
           FROM   {CATALOG}.{SCHEMA}.fact_inventory_snapshot
           WHERE  snapshot_grain = 'D'
           GROUP  BY snapshot_date) t
""").show()
