"""Load the ApexTech parquet files into Unity Catalog.

Run as a Databricks notebook or with databricks-connect. Upload the parquet
directory to a volume first, e.g.:

    databricks fs cp -r data/full dbfs:/Volumes/apextech/sales/raw/
"""

CATALOG = "apextech"
SCHEMA = "sales"
SOURCE = "/Volumes/apextech/sales/raw"        # adjust to your volume

TABLES = ['dim_channel', 'dim_country', 'dim_currency', 'dim_customer', 'dim_date', 'dim_exchange_rate', 'dim_location', 'dim_product', 'dim_product_category', 'dim_promotion', 'dim_sales_rep', 'dim_supplier', 'fact_budget', 'fact_forecast', 'fact_inventory', 'fact_returns', 'fact_sales_order', 'fact_sales_order_line', 'fact_sales_rep_quota', 'fact_supplier_performance']

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
for table, keys in {'fact_sales_order_line': ['year_month_key', 'product_id'], 'fact_sales_order': ['year_month_key', 'customer_id'], 'fact_returns': ['year_month_key'], 'fact_inventory': ['year_month_key', 'product_id'], 'fact_budget': ['year_month_key'], 'fact_forecast': ['year_month_key']}.items():
    spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.{table} "
              f"CLUSTER BY ({', '.join(keys)})")

spark.sql(f"""
    SELECT COUNT(*)                        AS order_lines,
           ROUND(SUM(net_sales)   / 1e6, 1) AS net_sales_musd,
           ROUND(SUM(gross_profit) / 1e6, 1) AS gross_profit_musd
    FROM   {CATALOG}.{SCHEMA}.fact_sales_order_line
""").show()
