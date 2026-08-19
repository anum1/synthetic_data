-- Meridian Global Industries | Supply Chain Control Tower
-- The 30 demo questions, as runnable SQL.
--
-- Portable ANSI SQL: verified on DuckDB, and written to run unchanged on
-- Snowflake and Databricks. "Today" is always derived from the data
--   (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot)
-- so the queries stay correct whenever the dataset is regenerated.
--
-- EVERY query against fact_inventory_snapshot filters snapshot_grain. The
-- table holds weekly history AND a daily recent window; summing across both
-- double-counts every inventory measure.
--
-- Run them all:  python3 src/run_questions.py --tier small

-- Q1 | Which products have excess inventory?
SELECT p.product_sku, p.product_name, p.abc_class,
       ROUND(SUM(i.inventory_value), 0) AS inventory_value,
       ROUND(AVG(i.days_of_supply), 0)  AS days_of_supply
FROM   fact_inventory_snapshot i
JOIN   dim_product p ON p.product_id = i.product_id
WHERE  i.snapshot_grain = 'D'
  AND  i.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot)
  AND  i.excess_inventory_flag = 1
GROUP  BY p.product_sku, p.product_name, p.abc_class
ORDER  BY inventory_value DESC
LIMIT  10;

-- Q2 | Which products are most likely to stock out?
SELECT p.product_sku, p.product_name, p.abc_class, p.xyz_class,
       ROUND(AVG(i.days_of_supply), 1) AS days_of_supply,
       ROUND(AVG(CAST(i.stockout_flag AS DOUBLE)) * 100, 1) AS stockout_pct_90d
FROM   fact_inventory_snapshot i
JOIN   dim_product p ON p.product_id = i.product_id
WHERE  i.snapshot_grain = 'D' AND i.demand_qty > 0
GROUP  BY p.product_sku, p.product_name, p.abc_class, p.xyz_class
HAVING COUNT(*) > 30
ORDER  BY stockout_pct_90d DESC, days_of_supply ASC
LIMIT  10;

-- Q3 | Where is inventory growing faster than demand?
WITH now AS (
  SELECT product_id, SUM(inventory_value) AS v, SUM(demand_qty) AS d
  FROM   fact_inventory_snapshot
  WHERE  snapshot_grain = 'D'
  GROUP  BY product_id),
prior AS (
  SELECT product_id, SUM(inventory_value) / 7 AS v, SUM(demand_qty) / 7 AS d
  FROM   fact_inventory_snapshot
  WHERE  snapshot_grain = 'W'
    AND  snapshot_date >= (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot) - INTERVAL 15 MONTH
    AND  snapshot_date <  (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot) - INTERVAL 12 MONTH
  GROUP  BY product_id)
SELECT p.product_sku, p.category, p.abc_class,
       ROUND((now.v / NULLIF(prior.v, 0) - 1) * 100, 1) AS inventory_growth_pct,
       ROUND((now.d / NULLIF(prior.d, 0) - 1) * 100, 1) AS demand_growth_pct
FROM   now JOIN prior ON prior.product_id = now.product_id
JOIN   dim_product p ON p.product_id = now.product_id
WHERE  prior.v > 0 AND prior.d > 0
ORDER  BY (now.v / NULLIF(prior.v, 0)) - (now.d / NULLIF(prior.d, 0)) DESC
LIMIT  10;

-- Q4 | Which warehouses have the lowest inventory turns?
SELECT l.location_name, l.region,
       ROUND(SUM(i.demand_qty * p.unit_cost) * 365.0 / NULLIF(COUNT(DISTINCT i.snapshot_date), 0)
             / NULLIF(AVG(i.inventory_value) * COUNT(DISTINCT i.product_id), 0), 2) AS annualised_turns,
       ROUND(AVG(i.inventory_value) * COUNT(DISTINCT i.product_id), 0) AS avg_inventory_value
FROM   fact_inventory_snapshot i
JOIN   dim_location l ON l.location_id = i.location_id
JOIN   dim_product  p ON p.product_id  = i.product_id
WHERE  i.snapshot_grain = 'D'
GROUP  BY l.location_name, l.region
ORDER  BY annualised_turns ASC
LIMIT  10;

-- Q5 | Which products have inventory but declining demand?
WITH recent AS (
  SELECT product_id, AVG(demand_qty) AS d_now, SUM(inventory_value) AS v
  FROM   fact_inventory_snapshot WHERE snapshot_grain = 'D'
  GROUP  BY product_id),
older AS (
  SELECT product_id, AVG(demand_qty) / 7 AS d_then
  FROM   fact_inventory_snapshot
  WHERE  snapshot_grain = 'W'
    AND  snapshot_date < (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot) - INTERVAL 9 MONTH
  GROUP  BY product_id)
SELECT p.product_sku, p.product_name, p.abc_class,
       ROUND(recent.v, 0) AS inventory_value,
       ROUND((recent.d_now / NULLIF(older.d_then, 0) - 1) * 100, 1) AS demand_change_pct
FROM   recent JOIN older ON older.product_id = recent.product_id
JOIN   dim_product p ON p.product_id = recent.product_id
WHERE  older.d_then > 0 AND recent.d_now / older.d_then < 0.5
ORDER  BY recent.v DESC
LIMIT  10;

-- Q6 | Which suppliers are responsible for most late POs?
SELECT s.supplier_master_id, s.supplier_name_clean,
       COUNT(*) AS late_lines,
       ROUND(SUM(po.po_line_value), 0) AS late_value
FROM   fact_purchase_order po
JOIN   dim_supplier s ON s.supplier_id = po.supplier_id
WHERE  po.is_late = 1
GROUP  BY s.supplier_master_id, s.supplier_name_clean
ORDER  BY late_value DESC
LIMIT  10;

-- Q7 | Which suppliers have deteriorating performance?
WITH by_half AS (
  SELECT d.supplier_id,
         AVG(CASE WHEN d.fulfilment_month_key >= (SELECT MAX(fulfilment_month_key) - 6 FROM fact_supplier_delivery)
                  THEN CAST(d.is_on_time AS DOUBLE) END) AS recent_ot,
         AVG(CASE WHEN d.fulfilment_month_key <  (SELECT MAX(fulfilment_month_key) - 12 FROM fact_supplier_delivery)
                  THEN CAST(d.is_on_time AS DOUBLE) END) AS baseline_ot,
         COUNT(*) AS deliveries
  FROM   fact_supplier_delivery d
  GROUP  BY d.supplier_id)
SELECT s.supplier_master_id, s.supplier_name_clean,
       ROUND(baseline_ot * 100, 1) AS on_time_before_pct,
       ROUND(recent_ot   * 100, 1) AS on_time_recent_pct,
       ROUND((recent_ot - baseline_ot) * 100, 1) AS change_pts
FROM   by_half b JOIN dim_supplier s ON s.supplier_id = b.supplier_id
WHERE  deliveries > 100 AND baseline_ot IS NOT NULL AND recent_ot IS NOT NULL
ORDER  BY change_pts ASC
LIMIT  10;

-- Q8 | Which critical products depend on a single supplier?
SELECT p.product_sku, p.product_name, p.criticality,
       s.supplier_master_id, s.supplier_name_clean,
       ROUND(p.annual_demand_qty * p.standard_price, 0) AS annual_revenue_exposure
FROM   dim_product p
JOIN   dim_supplier s ON s.supplier_id = p.primary_supplier_id
WHERE  p.single_source_flag = 1 AND p.criticality = 'Critical'
ORDER  BY annual_revenue_exposure DESC
LIMIT  15;

-- Q9 | Which suppliers have high spend and high risk?
SELECT supplier_master_id, supplier_name_clean, supplier_tier, risk_level,
       risk_score, ROUND(trailing_90d_spend, 0) AS spend_90d,
       single_sourced_skus
FROM   dim_supplier
WHERE  supplier_id > 0 AND trailing_90d_spend > 0
ORDER  BY risk_score * trailing_90d_spend DESC
LIMIT  10;

-- Q10 | Which suppliers have increasing defect rates?
SELECT s.supplier_master_id, s.supplier_name_clean,
       ROUND(AVG(CASE WHEN d.fulfilment_month_key < (SELECT MAX(fulfilment_month_key) - 6 FROM fact_supplier_delivery)
                      THEN d.defect_rate END) * 100, 2) AS defect_before_pct,
       ROUND(AVG(CASE WHEN d.fulfilment_month_key >= (SELECT MAX(fulfilment_month_key) - 3 FROM fact_supplier_delivery)
                      THEN d.defect_rate END) * 100, 2) AS defect_recent_pct,
       ROUND(SUM(d.quality_cost), 0) AS quality_cost
FROM   fact_supplier_delivery d
JOIN   dim_supplier s ON s.supplier_id = d.supplier_id
GROUP  BY s.supplier_master_id, s.supplier_name_clean
HAVING AVG(CASE WHEN d.fulfilment_month_key >= (SELECT MAX(fulfilment_month_key) - 3 FROM fact_supplier_delivery)
                THEN d.defect_rate END) IS NOT NULL
ORDER  BY defect_recent_pct - defect_before_pct DESC
LIMIT  10;

-- Q11 | Which products have the largest forecast bias?
SELECT p.product_sku, p.category, p.abc_class, p.xyz_class,
       ROUND(AVG(f.forecast_bias_pct) * 100, 1) AS bias_pct,
       ROUND(AVG(f.abs_pct_error) * 100, 1)     AS mape_pct
FROM   fact_forecast f JOIN dim_product p ON p.product_id = f.product_id
WHERE  f.forecast_version = 'ML' AND f.forecast_horizon_months = 1
GROUP  BY p.product_sku, p.category, p.abc_class, p.xyz_class
HAVING COUNT(*) > 20
ORDER  BY ABS(AVG(f.forecast_bias_pct)) DESC
LIMIT  10;

-- Q12 | Where is forecast accuracy deteriorating?
SELECT p.category,
       ROUND(AVG(CASE WHEN f.year_month_key < (SELECT MAX(year_month_key) - 6 FROM fact_forecast)
                      THEN f.forecast_accuracy END) * 100, 1) AS accuracy_before_pct,
       ROUND(AVG(CASE WHEN f.year_month_key >= (SELECT MAX(year_month_key) - 6 FROM fact_forecast)
                      THEN f.forecast_accuracy END) * 100, 1) AS accuracy_recent_pct
FROM   fact_forecast f JOIN dim_product p ON p.product_id = f.product_id
WHERE  f.forecast_version = 'ML' AND f.forecast_horizon_months = 1
GROUP  BY p.category
ORDER  BY accuracy_recent_pct - accuracy_before_pct ASC;

-- Q13 | Which categories are systematically under-forecast?
-- Restricted to the recent window on purpose: averaging a bias that started
-- seven months ago across three years of history dilutes it to nothing.
SELECT p.category,
       ROUND(AVG(f.forecast_bias_pct) * 100, 1) AS bias_pct,
       ROUND(AVG(f.abs_pct_error) * 100, 1)     AS mape_pct,
       COUNT(*) AS forecast_rows
FROM   fact_forecast f JOIN dim_product p ON p.product_id = f.product_id
WHERE  f.forecast_version = 'ML'
  AND  f.year_month_key >= (SELECT MAX(year_month_key) - 6 FROM fact_forecast)
GROUP  BY p.category
ORDER  BY bias_pct ASC;

-- Q14 | Which planner overrides improved forecast accuracy?
WITH v AS (
  SELECT product_id, forecast_version, AVG(abs_pct_error) AS mape
  FROM   fact_forecast WHERE forecast_horizon_months = 1
  GROUP  BY product_id, forecast_version)
SELECT p.product_sku, p.category, p.xyz_class,
       ROUND(ml.mape * 100, 1) AS ml_mape_pct,
       ROUND(ov.mape * 100, 1) AS override_mape_pct,
       ROUND((ml.mape - ov.mape) * 100, 1) AS improvement_pts
FROM   v ml JOIN v ov ON ov.product_id = ml.product_id
JOIN   dim_product p ON p.product_id = ml.product_id
WHERE  ml.forecast_version = 'ML' AND ov.forecast_version = 'Planner Override'
ORDER  BY improvement_pts DESC
LIMIT  10;

-- Q15 | Which products have highly volatile demand?
SELECT product_sku, product_name, category, abc_class, xyz_class,
       ROUND(demand_cv, 2) AS demand_cv,
       ROUND(annual_demand_value, 0) AS annual_value
FROM   dim_product
WHERE  xyz_class = 'Z'
ORDER  BY annual_demand_value DESC
LIMIT  10;

-- Q16 | Why did OTIF decline? (by month)
SELECT year_month_key,
       ROUND(AVG(CAST(is_otif    AS DOUBLE)) * 100, 1) AS otif_pct,
       ROUND(AVG(CAST(is_on_time AS DOUBLE)) * 100, 1) AS on_time_pct,
       ROUND(AVG(CAST(is_in_full AS DOUBLE)) * 100, 1) AS in_full_pct,
       COUNT(*) AS shipments
FROM   fact_shipment
GROUP  BY year_month_key
ORDER  BY year_month_key DESC
LIMIT  12;

-- Q17 | Which carriers are causing the most delays?
SELECT c.carrier_code, c.carrier_name, c.transport_mode,
       ROUND(AVG(CAST(sh.is_on_time AS DOUBLE)) * 100, 1) AS on_time_pct,
       ROUND(AVG(sh.delay_days), 2) AS avg_delay_days,
       COUNT(*) AS shipments
FROM   fact_shipment sh JOIN dim_carrier c ON c.carrier_id = sh.carrier_id
GROUP  BY c.carrier_code, c.carrier_name, c.transport_mode
ORDER  BY on_time_pct ASC
LIMIT  10;

-- Q18 | Which routes have increasing transit times? (carrier x sub-region)
SELECT c.carrier_code, l.sub_region,
       ROUND(AVG(CAST(sh.is_on_time AS DOUBLE)) * 100, 1) AS on_time_pct,
       ROUND(AVG(sh.transit_days), 2) AS avg_transit_days,
       COUNT(*) AS shipments
FROM   fact_shipment sh
JOIN   dim_carrier  c ON c.carrier_id  = sh.carrier_id
JOIN   dim_location l ON l.location_id = sh.location_id
WHERE  l.sub_region <> ''
GROUP  BY c.carrier_code, l.sub_region
HAVING COUNT(*) > 50
ORDER  BY on_time_pct ASC
LIMIT  10;

-- Q19 | Which regions have the highest freight cost?
SELECT l.region,
       ROUND(SUM(sh.freight_cost), 0) AS freight_cost,
       ROUND(SUM(sh.freight_cost) / NULLIF(SUM(sh.quantity), 0), 3) AS cost_per_unit,
       ROUND(AVG(CAST(sh.is_expedited AS DOUBLE)) * 100, 1) AS expedited_pct
FROM   fact_shipment sh JOIN dim_location l ON l.location_id = sh.location_id
GROUP  BY l.region
ORDER  BY freight_cost DESC;

-- Q20 | What is driving expedited shipping?
SELECT year_month_key,
       ROUND(AVG(CAST(is_expedited AS DOUBLE)) * 100, 1) AS expedited_pct,
       ROUND(SUM(CASE WHEN is_expedited = 1 THEN freight_cost ELSE 0 END), 0) AS expedite_spend
FROM   fact_shipment
GROUP  BY year_month_key
ORDER  BY year_month_key DESC
LIMIT  12;

-- Q21 | Which suppliers are causing stockouts?
SELECT s.supplier_master_id, s.supplier_name_clean,
       ROUND(s.on_time_rate * 100, 1) AS on_time_pct,
       COUNT(DISTINCT p.product_id) AS skus,
       ROUND(AVG(CAST(i.stockout_flag AS DOUBLE)) * 100, 1) AS stockout_pct
FROM   fact_inventory_snapshot i
JOIN   dim_product  p ON p.product_id  = i.product_id
JOIN   dim_supplier s ON s.supplier_id = p.primary_supplier_id
WHERE  i.snapshot_grain = 'D' AND i.demand_qty > 0
GROUP  BY s.supplier_master_id, s.supplier_name_clean, s.on_time_rate
HAVING COUNT(*) > 500
ORDER  BY stockout_pct DESC
LIMIT  10;

-- Q22 | Which products have high demand but low supply?
SELECT p.product_sku, p.product_name, p.abc_class,
       ROUND(SUM(i.demand_qty), 0)  AS demand_90d,
       ROUND(SUM(i.receipt_qty), 0) AS receipts_90d,
       ROUND(SUM(i.unmet_qty), 0)   AS unmet_90d
FROM   fact_inventory_snapshot i JOIN dim_product p ON p.product_id = i.product_id
WHERE  i.snapshot_grain = 'D'
GROUP  BY p.product_sku, p.product_name, p.abc_class
HAVING SUM(i.demand_qty) > 0
ORDER  BY unmet_90d DESC
LIMIT  10;

-- Q23 | Which inventory is tied to poor forecast accuracy?
SELECT p.category,
       ROUND(AVG(f.abs_pct_error) * 100, 1) AS mape_pct,
       ROUND(SUM(i.inventory_value), 0)     AS inventory_value
FROM   fact_inventory_snapshot i
JOIN   dim_product p ON p.product_id = i.product_id
JOIN   (SELECT product_id, AVG(abs_pct_error) AS abs_pct_error
        FROM   fact_forecast WHERE forecast_version = 'ML'
        GROUP  BY product_id) f ON f.product_id = i.product_id
WHERE  i.snapshot_grain = 'D'
  AND  i.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_inventory_snapshot)
GROUP  BY p.category
ORDER  BY mape_pct DESC;

-- Q24 | Which supplier issues have the greatest revenue impact?
SELECT s.supplier_master_id, s.supplier_name_clean,
       ROUND(s.on_time_rate * 100, 1) AS on_time_pct,
       COUNT(DISTINCT p.product_id)   AS skus_affected,
       ROUND(SUM(i.lost_sales_qty * p.standard_price), 0) AS revenue_at_risk
FROM   fact_inventory_snapshot i
JOIN   dim_product  p ON p.product_id  = i.product_id
JOIN   dim_supplier s ON s.supplier_id = p.primary_supplier_id
WHERE  i.snapshot_grain = 'D'
GROUP  BY s.supplier_master_id, s.supplier_name_clean, s.on_time_rate
ORDER  BY revenue_at_risk DESC
LIMIT  10;

-- Q25 | Which products have simultaneous supply and demand risk?
SELECT p.product_sku, p.product_name, p.abc_class, p.xyz_class,
       p.single_source_flag,
       ROUND(s.on_time_rate * 100, 1) AS supplier_on_time_pct,
       ROUND(p.demand_cv, 2) AS demand_cv,
       ROUND(p.annual_demand_value, 0) AS annual_value
FROM   dim_product p JOIN dim_supplier s ON s.supplier_id = p.primary_supplier_id
WHERE  p.single_source_flag = 1 AND p.xyz_class IN ('Y', 'Z')
  AND  s.on_time_rate < 0.9
ORDER  BY p.annual_demand_value DESC
LIMIT  10;

-- Q26 | What are the top 10 supply-chain risks right now?
SELECT r.entity_type, r.entity_id,
       COALESCE(s.supplier_master_id, p.product_sku, l.location_name) AS entity,
       r.overall_risk_score, r.risk_level,
       r.supplier_risk, r.demand_risk, r.inventory_risk,
       r.logistics_risk, r.quality_risk
FROM   fact_supply_chain_risk r
LEFT   JOIN dim_supplier s ON r.entity_type = 'Supplier' AND s.supplier_id = r.entity_id
LEFT   JOIN dim_product  p ON r.entity_type = 'Product'  AND p.product_id  = r.entity_id
LEFT   JOIN dim_location l ON r.entity_type = 'Location' AND l.location_id = r.entity_id
-- Each entity's OWN latest month. Filtering on the table's global MAX month
-- returns only the entity types whose source facts run that late (shipments
-- outlive deliveries), so suppliers and products silently vanish.
JOIN  (SELECT entity_type, entity_id, MAX(year_month_key) AS mk
       FROM   fact_supply_chain_risk GROUP BY entity_type, entity_id) latest
  ON   latest.entity_type = r.entity_type
 AND   latest.entity_id   = r.entity_id
 AND   latest.mk          = r.year_month_key
ORDER  BY r.overall_risk_score DESC
LIMIT  10;

-- Q27 | Where should we invest to improve service levels?
SELECT p.category,
       ROUND(SUM(i.unmet_qty * p.standard_price), 0) AS revenue_at_risk,
       ROUND(AVG(CAST(i.stockout_flag AS DOUBLE)) * 100, 1) AS stockout_pct,
       ROUND(SUM(i.inventory_value), 0) AS inventory_value
FROM   fact_inventory_snapshot i JOIN dim_product p ON p.product_id = i.product_id
WHERE  i.snapshot_grain = 'D' AND i.demand_qty > 0
GROUP  BY p.category
ORDER  BY revenue_at_risk DESC;

-- Q28 | Which problems should the team address first? (risk x spend)
SELECT supplier_master_id, supplier_name_clean, risk_level, risk_score,
       ROUND(trailing_90d_spend, 0) AS spend_90d,
       critical_skus_supplied, single_sourced_skus,
       ROUND(risk_score * trailing_90d_spend / 100, 0) AS exposure_index
FROM   dim_supplier
WHERE  supplier_id > 0 AND risk_level IN ('Critical', 'High')
ORDER  BY exposure_index DESC
LIMIT  10;

-- Q29 | What is causing working capital to increase?
SELECT cost_category,
       ROUND(SUM(CASE WHEN year_month_key >= (SELECT MAX(year_month_key) - 3 FROM fact_financial_impact)
                      THEN impact_amount ELSE 0 END), 0) AS recent_quarter,
       ROUND(SUM(CASE WHEN year_month_key <  (SELECT MAX(year_month_key) - 12 FROM fact_financial_impact)
                  AND  year_month_key >= (SELECT MAX(year_month_key) - 15 FROM fact_financial_impact)
                      THEN impact_amount ELSE 0 END), 0) AS same_quarter_last_year
FROM   fact_financial_impact
GROUP  BY cost_category
ORDER  BY recent_quarter DESC;

-- Q30 | Entity resolution: one bad supplier, hiding behind five spellings.
-- Group late deliveries on the raw supplier name and the worst supplier in the
-- business fragments into several unremarkable rows. Group on the master id
-- and it is obvious. Same data, two answers, one of them wrong.
SELECT 'raw name'                AS grouping_basis,
       d.supplier_name_raw       AS shown_as,
       COUNT(*)                  AS deliveries,
       SUM(CASE WHEN d.is_on_time = 0 THEN 1 ELSE 0 END) AS late_deliveries
FROM   fact_supplier_delivery d
JOIN   dim_supplier s ON s.supplier_id = d.supplier_id
WHERE  s.supplier_master_id = 'SUP-104'
GROUP  BY d.supplier_name_raw
UNION ALL
SELECT 'master id', s.supplier_master_id, COUNT(*),
       SUM(CASE WHEN d.is_on_time = 0 THEN 1 ELSE 0 END)
FROM   fact_supplier_delivery d
JOIN   dim_supplier s ON s.supplier_id = d.supplier_id
WHERE  s.supplier_master_id = 'SUP-104'
GROUP  BY s.supplier_master_id
ORDER  BY late_deliveries DESC;
