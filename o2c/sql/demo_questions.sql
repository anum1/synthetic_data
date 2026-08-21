-- =============================================================================
-- Vantage Industrial - Order-to-Cash Control Tower
-- The demo questions, as runnable SQL.
--
-- Q1-Q20 are the design note's twenty. Q21-Q30 cover the exception centre, the
-- ageing matrix and the process-time bridge.
--
-- Written for DuckDB (src/run_questions.py) and portable to Snowflake and
-- Databricks with no changes beyond the catalog prefix. Every date filter is
-- relative to the data, never a hard-coded literal, so these keep working after
-- a regeneration.
--
--   python3 src/run_questions.py --tier small
-- =============================================================================


-- Q1. Where is revenue getting trapped in our O2C process?
--     The cohort waterfall: of what we booked in the last twelve months, where
--     did it stop? LOST is gone; the rest is timing or risk.
WITH cohort AS (
  SELECT * FROM fact_o2c_cycle
  WHERE order_date >= (SELECT DATE_TRUNC('month', MAX(order_date)) - INTERVAL 11 MONTH
                       FROM fact_o2c_cycle)
)
SELECT stage, disposition, ROUND(amount_usd / 1e6, 2) AS usd_millions
FROM (
  SELECT 1 AS ord, 'Booked'                 AS stage, 'START'  AS disposition, SUM(booked_net_usd)              AS amount_usd FROM cohort
  UNION ALL SELECT 2, 'Cancelled',              'LOST',    SUM(cancelled_net_usd)            FROM cohort
  UNION ALL SELECT 3, 'Not yet shipped',        'AT RISK', SUM(not_yet_shipped_usd)          FROM cohort
  UNION ALL SELECT 4, 'In transit',             'TIMING',  SUM(in_transit_usd)               FROM cohort
  UNION ALL SELECT 5, 'Delivered not invoiced', 'LEAKAGE', SUM(delivered_not_invoiced_usd)   FROM cohort
  UNION ALL SELECT 6, 'Credited / returned',    'LOST',    SUM(credited_net_usd)             FROM cohort
  UNION ALL SELECT 7, 'Open AR on the cohort',  'TIMING',  SUM(open_ar_net_usd)              FROM cohort
  UNION ALL SELECT 8, 'Collected',              'CASH',    SUM(collected_net_usd)            FROM cohort
) t ORDER BY ord;


-- Q2. Why did our cash conversion cycle increase this quarter?
--     The process-time bridge, quarter by quarter. The stage that moved is the
--     answer.
SELECT DATE_TRUNC('quarter', order_date)                    AS booking_quarter,
       COUNT(*)                                             AS orders,
       ROUND(AVG(NULLIF(quote_to_order_days, -1)), 1)       AS quote_to_order,
       ROUND(AVG(NULLIF(order_to_ship_days, -1)), 1)        AS order_to_ship,
       ROUND(AVG(NULLIF(ship_to_delivery_days, -1)), 1)     AS ship_to_delivery,
       ROUND(AVG(NULLIF(delivery_to_invoice_days, -1)), 1)  AS delivery_to_invoice,
       ROUND(AVG(NULLIF(invoice_to_cash_days, -1)), 1)      AS invoice_to_cash,
       ROUND(AVG(NULLIF(order_to_cash_days, -1)), 1)        AS total_o2c_days
FROM fact_o2c_cycle
GROUP BY 1 ORDER BY 1;


-- Q3. Which customers represent the greatest cash-collection risk?
SELECT c.customer_name, c.customer_segment, c.credit_rating,
       ROUND(SUM(i.open_amount_usd), 0)                                       AS open_ar,
       ROUND(SUM(CASE WHEN i.is_overdue = 1 THEN i.open_amount_usd END), 0)   AS overdue_ar,
       ROUND(SUM(i.disputed_amount_usd), 0)                                   AS disputed,
       MAX(i.days_overdue)                                                    AS worst_days_overdue
FROM fact_invoice i JOIN dim_customer c USING (customer_id)
WHERE i.is_open = 1
GROUP BY 1,2,3
HAVING SUM(CASE WHEN i.is_overdue = 1 THEN i.open_amount_usd END) > 0
ORDER BY overdue_ar DESC LIMIT 15;


-- Q4. What are the top five causes of O2C leakage?
SELECT exception_type, owner_function,
       COUNT(*)                                   AS open_exceptions,
       ROUND(SUM(exception_value_usd), 0)         AS value_blocked,
       ROUND(AVG(age_days), 0)                    AS avg_age_days,
       SUM(CASE WHEN severity = 'High' THEN 1 ELSE 0 END) AS high_severity
FROM fact_o2c_exception
GROUP BY 1,2 ORDER BY value_blocked DESC LIMIT 5;


-- Q5. How much revenue has been delivered but not invoiced?
SELECT business_unit,
       COUNT(*)                                        AS orders_affected,
       ROUND(SUM(delivered_not_invoiced_usd), 0)       AS unbilled_usd,
       ROUND(AVG(DATE_DIFF('day', last_delivery_date,
                 (SELECT MAX(order_date) FROM fact_o2c_cycle))), 0) AS avg_days_since_delivery
FROM fact_o2c_cycle
WHERE is_delivered_not_invoiced = 1
GROUP BY 1 ORDER BY unbilled_usd DESC;


-- Q6. Which sales reps have high bookings but poor margins?
SELECT r.sales_rep_name, r.region, r.territory,
       ROUND(SUM(o.net_order_amount_usd), 0)                     AS bookings,
       ROUND(AVG(o.gross_margin_pct), 4)                         AS avg_margin_pct,
       ROUND(AVG(o.discount_amount_usd / NULLIF(o.order_amount_usd, 0)), 4) AS avg_discount_pct
FROM fact_order o JOIN dim_sales_rep r USING (sales_rep_id)
WHERE o.is_cancelled = 0
GROUP BY 1,2,3
HAVING SUM(o.net_order_amount_usd) > 0
ORDER BY bookings DESC LIMIT 20;


-- Q7. Which reps are discounting more than their peers?
--     Measured over the last six months against the median of their own region,
--     so a region-wide pricing policy does not read as a rogue rep.
WITH recent AS (
  SELECT q.sales_rep_id, r.sales_rep_name, r.region, r.territory,
         AVG(ql.discount_pct) AS rep_discount, COUNT(*) AS lines
  FROM fact_quote_line ql
  JOIN fact_quote q USING (quote_id)
  JOIN dim_sales_rep r ON r.sales_rep_id = q.sales_rep_id
  WHERE q.quote_date >= (SELECT MAX(quote_date) - INTERVAL 6 MONTH FROM fact_quote)
  GROUP BY 1,2,3,4 HAVING COUNT(*) > 30
), regional AS (
  SELECT region, MEDIAN(rep_discount) AS region_median FROM recent GROUP BY 1
)
SELECT sales_rep_name, region, territory, lines,
       ROUND(rep_discount, 4) AS rep_discount,
       ROUND(region_median, 4) AS region_median,
       ROUND(rep_discount / NULLIF(region_median, 0), 2) AS times_peer_median
FROM recent JOIN regional USING (region)
ORDER BY times_peer_median DESC LIMIT 10;


-- Q8. Which customers have declining quote conversion?
WITH per_period AS (
  SELECT customer_id, region,
         CASE WHEN quote_date >= (SELECT MAX(quote_date) - INTERVAL 6 MONTH FROM fact_quote)
              THEN 'recent' ELSE 'baseline' END AS period,
         AVG(is_won * 1.0) AS win_rate, COUNT(*) AS quotes
  FROM fact_quote WHERE is_open = 0 GROUP BY 1,2,3
)
SELECT c.customer_name, p.region,
       ROUND(MAX(CASE WHEN period = 'baseline' THEN win_rate END), 3) AS baseline_win_rate,
       ROUND(MAX(CASE WHEN period = 'recent'   THEN win_rate END), 3) AS recent_win_rate,
       SUM(quotes) AS quotes
FROM per_period p JOIN dim_customer c USING (customer_id)
GROUP BY 1,2
HAVING SUM(quotes) > 25
   AND MAX(CASE WHEN period = 'recent' THEN win_rate END)
     < MAX(CASE WHEN period = 'baseline' THEN win_rate END) * 0.6
ORDER BY quotes DESC LIMIT 15;


-- Q9. Which products have the highest quote-to-order conversion?
SELECT p.product_category, p.product_family,
       COUNT(*)                                              AS quoted_lines,
       ROUND(AVG(q.is_won * 1.0), 3)                          AS line_win_rate,
       ROUND(SUM(ql.extended_amount_usd * q.is_won) / 1e6, 2) AS won_value_millions
FROM fact_quote_line ql
JOIN fact_quote q USING (quote_id)
JOIN dim_product p USING (product_id)
WHERE q.is_open = 0
GROUP BY 1,2 HAVING COUNT(*) > 200
ORDER BY line_win_rate DESC LIMIT 15;


-- Q10. Which warehouses are causing the most backorders?
SELECT w.warehouse_code, w.warehouse_name, w.region,
       SUM(ol.quantity_ordered)                                              AS qty_ordered,
       SUM(ol.quantity_backordered)                                          AS qty_backordered,
       ROUND(SUM(ol.quantity_backordered) * 1.0 / NULLIF(SUM(ol.quantity_ordered), 0), 4) AS backorder_rate,
       ROUND(SUM(ol.unit_price_usd * ol.quantity_backordered), 0)            AS backorder_value
FROM fact_order_line ol JOIN dim_warehouse w USING (warehouse_id)
WHERE ol.is_cancelled = 0
  AND ol.order_date >= (SELECT MAX(order_date) - INTERVAL 6 MONTH FROM fact_order)
GROUP BY 1,2,3 ORDER BY backorder_rate DESC LIMIT 10;


-- Q11. Which orders are at risk of missing promised delivery dates?
SELECT o.order_number, c.customer_name, o.promised_delivery_date,
       s.shipment_number, s.carrier_name, s.expected_delivery_date,
       ROUND(o.net_order_amount_usd, 0) AS order_value,
       DATE_DIFF('day', o.promised_delivery_date, s.expected_delivery_date) AS days_late_forecast
FROM fact_shipment s
JOIN fact_order o USING (order_id)
JOIN dim_customer c ON c.customer_id = o.customer_id
WHERE s.is_delivered = 0 AND s.is_lost = 0
  AND s.expected_delivery_date > o.promised_delivery_date
ORDER BY order_value DESC LIMIT 20;


-- Q12. Which customers are experiencing the most partial shipments?
WITH per_order AS (
  SELECT order_id, customer_id, COUNT(*) AS consignments
  FROM fact_shipment
  WHERE ship_date >= (SELECT MAX(ship_date) - INTERVAL 6 MONTH FROM fact_shipment)
  GROUP BY 1,2
)
SELECT c.customer_name, c.customer_segment,
       COUNT(*)                                                        AS orders,
       SUM(CASE WHEN consignments > 1 THEN 1 ELSE 0 END)               AS split_orders,
       ROUND(AVG(CASE WHEN consignments > 1 THEN 1.0 ELSE 0.0 END), 3) AS split_rate,
       ROUND(AVG(consignments), 2)                                     AS avg_consignments
FROM per_order JOIN dim_customer c USING (customer_id)
GROUP BY 1,2 HAVING COUNT(*) >= 10
ORDER BY split_rate DESC, orders DESC LIMIT 15;


-- Q13. Which carriers have deteriorated in on-time delivery?
--      Carrier performance is measured against the carrier's own quoted transit,
--      not against the customer promise - see docs/KPI_DEFINITIONS.md.
WITH periods AS (
  SELECT carrier_name, service_level,
         CASE WHEN ship_date >= (SELECT MAX(ship_date) - INTERVAL 3 MONTH FROM fact_shipment)
              THEN 'recent' ELSE 'baseline' END AS period,
         AVG(is_on_time_carrier * 1.0) AS on_time, COUNT(*) AS shipments
  FROM fact_shipment WHERE is_delivered = 1 GROUP BY 1,2,3
)
SELECT carrier_name,
       ROUND(SUM(CASE WHEN period='baseline' THEN on_time*shipments END)
             / NULLIF(SUM(CASE WHEN period='baseline' THEN shipments END),0), 3) AS baseline_on_time,
       ROUND(SUM(CASE WHEN period='recent' THEN on_time*shipments END)
             / NULLIF(SUM(CASE WHEN period='recent' THEN shipments END),0), 3)   AS recent_on_time,
       SUM(shipments) AS shipments
FROM periods GROUP BY 1
ORDER BY (recent_on_time - baseline_on_time) LIMIT 10;


-- Q14. How much are delayed shipments costing us?
SELECT DATE_TRUNC('month', s.ship_date) AS ship_month,
       COUNT(*)                                                     AS shipments,
       SUM(CASE WHEN s.is_expedited = 1 THEN 1 ELSE 0 END)          AS expedited,
       ROUND(AVG(s.is_expedited * 1.0), 3)                          AS expedite_rate,
       ROUND(SUM(s.freight_cost_usd), 0)                            AS freight_spend,
       ROUND(SUM(s.freight_cost_usd)
             / NULLIF(SUM(o.net_order_amount_usd), 0), 4)           AS freight_pct_of_revenue
FROM fact_shipment s JOIN fact_order o USING (order_id)
GROUP BY 1 ORDER BY 1;


-- Q15. Which regions have the longest delivery cycle time?
SELECT s.region,
       COUNT(*)                                   AS delivered_shipments,
       ROUND(AVG(s.actual_transit_days), 2)       AS avg_transit_days,
       ROUND(AVG(s.delay_days), 2)                AS avg_delay_days,
       ROUND(AVG(s.is_on_time_promise * 1.0), 3)  AS on_time_to_promise
FROM fact_shipment s WHERE s.is_delivered = 1
GROUP BY 1 ORDER BY avg_transit_days DESC;


-- Q16. Which customers have the highest overdue AR?
SELECT c.customer_name, c.customer_segment, c.credit_rating, c.payment_terms_code,
       ROUND(SUM(i.open_amount_usd), 0) AS overdue_ar,
       COUNT(*)                         AS overdue_invoices,
       MAX(i.days_overdue)              AS worst_days_overdue
FROM fact_invoice i JOIN dim_customer c USING (customer_id)
WHERE i.is_overdue = 1
GROUP BY 1,2,3,4 ORDER BY overdue_ar DESC LIMIT 20;


-- Q17. What invoices are more than 60 days overdue?
SELECT i.invoice_number, c.customer_name, i.invoice_date, i.due_date,
       i.days_overdue, i.aging_bucket, i.invoice_status,
       ROUND(i.open_amount_usd, 0)     AS open_amount,
       ROUND(i.disputed_amount_usd, 0) AS disputed
FROM fact_invoice i JOIN dim_customer c USING (customer_id)
WHERE i.is_open = 1 AND i.days_overdue > 60
ORDER BY i.open_amount_usd DESC LIMIT 25;


-- Q18. Which customers have increasing dispute rates?
WITH monthly AS (
  SELECT c.global_account_name, DATE_TRUNC('month', d.dispute_date) AS m,
         SUM(d.dispute_amount_usd) AS disputed, COUNT(*) AS disputes
  FROM fact_dispute d JOIN dim_customer c USING (customer_id)
  GROUP BY 1,2
)
SELECT global_account_name,
       ROUND(AVG(CASE WHEN m >= (SELECT MAX(m) - INTERVAL 5 MONTH FROM monthly)
                      THEN disputed END), 0) AS recent_monthly_disputed,
       ROUND(AVG(CASE WHEN m <  (SELECT MAX(m) - INTERVAL 11 MONTH FROM monthly)
                      THEN disputed END), 0) AS baseline_monthly_disputed,
       SUM(disputes)                          AS total_disputes
FROM monthly
WHERE global_account_name <> 'Unaffiliated'
GROUP BY 1
HAVING AVG(CASE WHEN m >= (SELECT MAX(m) - INTERVAL 5 MONTH FROM monthly) THEN disputed END) IS NOT NULL
ORDER BY recent_monthly_disputed DESC LIMIT 10;


-- Q19. Where are invoice-to-order pricing discrepancies occurring?
--      The baseline is the price on the ORDER - the agreement - so anything
--      non-zero here is a billing error rather than a contract question.
SELECT c.customer_name, c.customer_segment,
       COUNT(*)                                        AS underbilled_lines,
       ROUND(SUM(il.underbilled_amount_usd), 0)        AS underbilled_usd,
       ROUND(AVG(1 - il.unit_price_usd
                 / NULLIF(il.order_unit_price_usd, 0)), 4) AS avg_shortfall_pct
FROM fact_invoice_line il
JOIN fact_invoice i USING (invoice_id)
JOIN dim_customer c ON c.customer_id = i.customer_id
WHERE il.underbilled_amount_usd > 0
GROUP BY 1,2 ORDER BY underbilled_usd DESC LIMIT 15;


-- Q20. If we improve DSO by 5 days, how much cash would we release?
--      DSO here is AR divided by average daily billings over the trailing year.
--      Stated as an assumption on screen, per docs/KPI_DEFINITIONS.md.
WITH ttm AS (
  SELECT SUM(total_amount_usd) AS billings
  FROM fact_invoice
  WHERE invoice_date >= (SELECT MAX(invoice_date) - INTERVAL 12 MONTH FROM fact_invoice)
), ar AS (
  SELECT SUM(open_amount_usd) AS open_ar FROM fact_invoice WHERE is_open = 1
)
SELECT ROUND(open_ar, 0)                            AS open_ar,
       ROUND(billings / 365.0, 0)                   AS avg_daily_billings,
       ROUND(open_ar / (billings / 365.0), 1)       AS dso_days,
       ROUND(5 * billings / 365.0, 0)               AS cash_released_by_5_day_improvement
FROM ttm, ar;


-- Q21. The AR ageing matrix.
SELECT c.customer_name,
       ROUND(SUM(CASE WHEN a.aging_bucket = 'Current' THEN a.open_amount_usd ELSE 0 END), 0) AS current_ar,
       ROUND(SUM(CASE WHEN a.aging_bucket = '1-30'    THEN a.open_amount_usd ELSE 0 END), 0) AS d1_30,
       ROUND(SUM(CASE WHEN a.aging_bucket = '31-60'   THEN a.open_amount_usd ELSE 0 END), 0) AS d31_60,
       ROUND(SUM(CASE WHEN a.aging_bucket = '61-90'   THEN a.open_amount_usd ELSE 0 END), 0) AS d61_90,
       ROUND(SUM(CASE WHEN a.aging_bucket = '90+'     THEN a.open_amount_usd ELSE 0 END), 0) AS d90_plus,
       ROUND(SUM(a.open_amount_usd), 0)                                                      AS total_ar
FROM fact_ar_aging_snapshot a JOIN dim_customer c USING (customer_id)
WHERE a.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_ar_aging_snapshot)
GROUP BY 1 ORDER BY total_ar DESC LIMIT 20;


-- Q22. The exception centre: what is open right now, and who owns it?
SELECT exception_type, severity, owner_function,
       COUNT(*)                            AS items,
       ROUND(SUM(exception_value_usd), 0)  AS value_blocked,
       MAX(age_days)                       AS oldest_days
FROM fact_o2c_exception
GROUP BY 1,2,3 ORDER BY value_blocked DESC LIMIT 25;


-- Q23. How much is blocked by credit holds, and for whom?
SELECT c.customer_name, c.customer_segment, c.credit_rating,
       COUNT(*)                                     AS orders_on_hold,
       ROUND(SUM(o.total_order_amount_usd), 0)      AS value_on_hold,
       ROUND(MAX(o.credit_exposure_at_order_usd), 0) AS exposure_at_order,
       ROUND(MAX(o.credit_limit_at_order_usd), 0)   AS limit_at_order
FROM fact_order o JOIN dim_customer c USING (customer_id)
WHERE o.credit_status = 'Credit Hold' AND o.is_cancelled = 0
GROUP BY 1,2,3 ORDER BY value_on_hold DESC LIMIT 15;


-- Q24. Credit utilisation over time - the trend the current-state table cannot show.
SELECT snapshot_date,
       COUNT(*)                                                AS customers,
       SUM(is_over_limit)                                      AS over_limit,
       ROUND(SUM(current_exposure_usd) / 1e6, 2)               AS exposure_millions,
       ROUND(SUM(value_on_credit_hold_usd) / 1e6, 3)           AS on_hold_millions,
       ROUND(AVG(credit_utilization_pct), 3)                   AS avg_utilisation
FROM fact_credit_exposure_snapshot
GROUP BY 1 ORDER BY 1 DESC LIMIT 18;


-- Q25. Perfect order rate, and which component is breaking it.
SELECT DATE_TRUNC('quarter', order_date) AS booking_quarter,
       COUNT(*)                                  AS orders,
       ROUND(AVG(is_on_time * 1.0), 3)           AS on_time,
       ROUND(AVG(is_complete * 1.0), 3)          AS complete,
       ROUND(AVG(is_billed_correctly * 1.0), 3)  AS billed_correctly,
       ROUND(AVG(is_perfect_order * 1.0), 3)     AS perfect_order_rate
FROM fact_o2c_cycle
GROUP BY 1 ORDER BY 1;


-- Q26. Which SKUs ran out, and what did it cost us in unfilled demand?
SELECT p.sku, p.product_name, p.product_category, p.abc_class,
       ROUND(p.standard_margin_pct, 3)                    AS margin_pct,
       SUM(ip.demand_qty)                                 AS demand_qty,
       SUM(ip.shortfall_qty)                              AS shortfall_qty,
       ROUND(SUM(ip.shortfall_qty * p.list_price_usd), 0) AS unfilled_demand_usd
FROM fact_inventory_position ip JOIN dim_product p USING (product_id)
GROUP BY 1,2,3,4,5
HAVING SUM(ip.shortfall_qty) > 0
ORDER BY unfilled_demand_usd DESC LIMIT 15;


-- Q27. Returns by category - which one has gone wrong?
WITH billed AS (
  SELECT p.product_category, DATE_TRUNC('month', i.invoice_date) AS m,
         COUNT(*) AS lines
  FROM fact_invoice_line il
  JOIN fact_invoice i USING (invoice_id)
  JOIN dim_product p USING (product_id)
  GROUP BY 1,2
), returned AS (
  SELECT product_category, DATE_TRUNC('month', return_date) AS m, COUNT(*) AS rmas
  FROM fact_return GROUP BY 1,2
)
SELECT b.product_category,
       ROUND(SUM(CASE WHEN b.m >= (SELECT MAX(m) - INTERVAL 5 MONTH FROM billed)
                      THEN COALESCE(r.rmas,0) END)
             / NULLIF(SUM(CASE WHEN b.m >= (SELECT MAX(m) - INTERVAL 5 MONTH FROM billed)
                      THEN b.lines END), 0), 4) AS recent_return_rate,
       ROUND(SUM(CASE WHEN b.m <  (SELECT MAX(m) - INTERVAL 11 MONTH FROM billed)
                      THEN COALESCE(r.rmas,0) END)
             / NULLIF(SUM(CASE WHEN b.m <  (SELECT MAX(m) - INTERVAL 11 MONTH FROM billed)
                      THEN b.lines END), 0), 4) AS baseline_return_rate
FROM billed b LEFT JOIN returned r ON r.product_category = b.product_category AND r.m = b.m
GROUP BY 1 ORDER BY recent_return_rate DESC;


-- Q28. Duplicate billing - the same order invoiced twice.
SELECT d.invoice_number AS duplicate_invoice, o.invoice_number AS original_invoice,
       c.customer_name, d.invoice_date AS duplicate_date, o.invoice_date AS original_date,
       ROUND(d.total_amount_usd, 0) AS amount, d.invoice_status
FROM fact_invoice d
JOIN fact_invoice o ON o.invoice_id = d.duplicate_of_invoice_id
JOIN dim_customer c ON c.customer_id = d.customer_id
WHERE d.is_duplicate = 1
ORDER BY d.total_amount_usd DESC LIMIT 20;


-- Q29. Off-contract spend - what are we buying without a negotiated price?
SELECT c.customer_segment,
       COUNT(*)                                                          AS order_lines,
       ROUND(AVG(CASE WHEN ol.is_contract_price = 1 THEN 1.0 ELSE 0.0 END), 3) AS on_contract_rate,
       ROUND(SUM(CASE WHEN ol.is_contract_price = 0
                      THEN ol.extended_amount_usd ELSE 0 END) / 1e6, 2)  AS off_contract_millions,
       ROUND(AVG(CASE WHEN ol.is_contract_price = 0 THEN ol.discount_pct END), 4) AS off_contract_discount,
       ROUND(AVG(CASE WHEN ol.is_contract_price = 1 THEN ol.discount_pct END), 4) AS contract_discount
FROM fact_order_line ol
JOIN dim_customer c ON c.customer_id = ol.customer_id
GROUP BY 1 ORDER BY off_contract_millions DESC;


-- Q30. The customer 360 - one account, all the way down the chain.
WITH target AS (
  SELECT customer_id FROM fact_o2c_cycle
  GROUP BY 1 ORDER BY SUM(booked_net_usd) DESC LIMIT 1
)
SELECT c.customer_name, c.customer_segment, c.credit_rating, c.payment_terms_code,
       ROUND(SUM(y.booked_net_usd), 0)               AS booked,
       ROUND(SUM(y.delivered_net_usd), 0)            AS delivered,
       ROUND(SUM(y.invoiced_net_usd), 0)             AS invoiced,
       ROUND(SUM(y.collected_net_usd), 0)            AS collected,
       ROUND(SUM(y.open_ar_net_usd), 0)              AS open_ar,
       ROUND(AVG(NULLIF(y.order_to_cash_days, -1)), 1) AS avg_o2c_days
FROM fact_o2c_cycle y
JOIN target t USING (customer_id)
JOIN dim_customer c ON c.customer_id = y.customer_id
GROUP BY 1,2,3,4;
