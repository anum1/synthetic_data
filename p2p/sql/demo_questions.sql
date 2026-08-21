-- Norvant Group - Procure-to-Pay Control Tower
-- The demo questions, as runnable SQL.
--
-- Written for DuckDB against the parquet in data/<tier>/ (see src/run_questions.py),
-- and portable to Snowflake or Databricks by replacing the read_parquet() calls
-- with the table names emitted by src/emit_ddl.py.
--
-- Each question is preceded by the plain-English version an executive would ask.

-- ============================================================================
-- EXECUTIVE
-- ============================================================================

-- Q1. What did we spend in the last twelve months, and how does it split across
--     the three channels?
SELECT spend_channel,
       ROUND(SUM(spend_amount_usd) / 1e6, 1) AS spend_musd,
       COUNT(*)                              AS lines
FROM fact_spend
WHERE spend_date >= (SELECT MAX(spend_date) - INTERVAL 12 MONTH FROM fact_spend)
GROUP BY 1 ORDER BY 2 DESC;

-- Q2. How is that spend managed? Contracted, off-contract, or maverick?
SELECT spend_class,
       ROUND(SUM(spend_amount_usd) / 1e6, 1) AS spend_musd,
       ROUND(100.0 * SUM(spend_amount_usd)
             / SUM(SUM(spend_amount_usd)) OVER (), 1) AS pct
FROM fact_spend
WHERE spend_date >= (SELECT MAX(spend_date) - INTERVAL 12 MONTH FROM fact_spend)
GROUP BY 1 ORDER BY 2 DESC;

-- Q3. Which categories grew fastest year on year?
WITH s AS (
  SELECT c.segment_name, c.category_name,
         SUM(CASE WHEN f.spend_date >= (SELECT MAX(spend_date) - INTERVAL 12 MONTH
                                        FROM fact_spend)
                  THEN f.spend_amount_usd END) AS ttm,
         SUM(CASE WHEN f.spend_date <  (SELECT MAX(spend_date) - INTERVAL 12 MONTH
                                        FROM fact_spend)
                   AND f.spend_date >= (SELECT MAX(spend_date) - INTERVAL 24 MONTH
                                        FROM fact_spend)
                  THEN f.spend_amount_usd END) AS prior
  FROM fact_spend f JOIN dim_category c USING (category_id)
  GROUP BY 1, 2)
SELECT segment_name, category_name,
       ROUND(ttm / 1e6, 2) AS ttm_musd,
       ROUND(100.0 * (ttm / NULLIF(prior, 0) - 1), 1) AS growth_pct
FROM s WHERE prior > 0 AND ttm > 500000
ORDER BY growth_pct DESC LIMIT 10;

-- Q4. Where is the whole process losing time?
SELECT ROUND(AVG(days_req_to_req_approved), 1) AS req_to_approved,
       ROUND(AVG(days_req_approved_to_po),   1) AS approved_to_po,
       ROUND(AVG(days_po_to_receipt),        1) AS po_to_receipt,
       ROUND(AVG(days_receipt_to_invoice),   1) AS receipt_to_invoice,
       ROUND(AVG(days_invoice_to_approved),  1) AS invoice_to_approved,
       ROUND(AVG(days_approved_to_paid),     1) AS approved_to_paid,
       ROUND(AVG(days_req_to_cash),          1) AS total_days,
       ROUND(AVG(days_controllable),         1) AS ours,
       ROUND(AVG(days_supplier),             1) AS suppliers
FROM fact_p2p_cycle WHERE days_req_to_cash IS NOT NULL;

-- ============================================================================
-- PROCUREMENT
-- ============================================================================

-- Q5. How much are we actually spending with each supplier GROUP? (The supplier
--     master fragments the same vendor across several records.)
SELECT p.parent_name,
       COUNT(DISTINCT s.supplier_id)         AS supplier_records,
       ROUND(SUM(f.spend_amount_usd) / 1e6, 2) AS spend_musd
FROM fact_spend f
JOIN dim_supplier s USING (supplier_id)
JOIN dim_supplier_parent p USING (supplier_parent_id)
GROUP BY 1 HAVING COUNT(DISTINCT s.supplier_id) > 1
ORDER BY 3 DESC LIMIT 10;

-- Q6. Which suppliers are we paying MORE than the price we contracted?
SELECT s.supplier_name,
       COUNT(*)                                            AS po_lines,
       ROUND(SUM(l.contract_price_variance_usd) / 1e3, 1)  AS overpaid_kusd,
       ROUND(100.0 * AVG(l.unit_price_usd / NULLIF(l.contract_unit_price_usd, 0) - 1),
             1)                                            AS avg_premium_pct
FROM fact_purchase_order_line l JOIN dim_supplier s USING (supplier_id)
WHERE l.has_contract_price = 1 AND l.is_priced_above_contract = 1
GROUP BY 1 HAVING SUM(l.contract_price_variance_usd) > 0
ORDER BY 3 DESC LIMIT 10;

-- Q7. Where are we over-dependent on a handful of suppliers?
WITH k AS (
  SELECT c.category_name, f.supplier_id, SUM(f.spend_amount_usd) AS spend
  FROM fact_spend f JOIN dim_category c USING (category_id)
  GROUP BY 1, 2)
SELECT category_name,
       COUNT(*)                                        AS suppliers,
       ROUND(SUM(spend) / 1e6, 2)                      AS spend_musd,
       ROUND(100.0 * MAX(spend) / SUM(spend), 1)       AS top1_share_pct
FROM k GROUP BY 1 HAVING SUM(spend) > 2000000
ORDER BY top1_share_pct DESC LIMIT 10;

-- Q8. Which categories are fragmented enough to consolidate?
WITH k AS (
  SELECT c.category_name, f.supplier_id, SUM(f.spend_amount_usd) AS spend
  FROM fact_spend f JOIN dim_category c USING (category_id)
  GROUP BY 1, 2),
r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY category_name ORDER BY spend DESC) rn
      FROM k)
SELECT category_name, COUNT(*) AS suppliers,
       ROUND(SUM(spend) / 1e6, 2) AS spend_musd,
       ROUND(100.0 * SUM(CASE WHEN rn <= 5 THEN spend END) / SUM(spend), 1) AS top5_pct
FROM r GROUP BY 1 HAVING COUNT(*) >= 25
ORDER BY top5_pct ASC LIMIT 10;

-- Q9. Which departments have the highest maverick spend?
SELECT d.department_name,
       ROUND(SUM(f.spend_amount_usd) / 1e6, 2) AS maverick_musd,
       COUNT(*)                                AS transactions
FROM fact_spend f JOIN dim_department d USING (department_id)
WHERE f.is_maverick_spend = 1
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- Q10. Which contracts expire in the next 90 days, and how much spend rides on them?
SELECT s.supplier_name, c.contract_number, c.contract_end_date, c.days_to_expiry,
       ROUND(c.committed_value_usd / 1e6, 2) AS committed_musd
FROM contract c JOIN dim_supplier s USING (supplier_id)
WHERE c.days_to_expiry BETWEEN 1 AND 90
ORDER BY c.committed_value_usd DESC LIMIT 15;

-- Q11. Where are we paying different prices for the same specification?
SELECT i.normalized_item_key,
       COUNT(DISTINCT l.supplier_id)          AS suppliers,
       ROUND(MIN(l.unit_price_usd), 2)        AS lowest,
       ROUND(MAX(l.unit_price_usd), 2)        AS highest,
       ROUND(100.0 * (MAX(l.unit_price_usd) / NULLIF(MIN(l.unit_price_usd), 0) - 1),
             0)                               AS spread_pct
FROM fact_purchase_order_line l JOIN dim_item i USING (item_id)
GROUP BY 1 HAVING COUNT(DISTINCT l.supplier_id) >= 3
ORDER BY spread_pct DESC LIMIT 10;

-- ============================================================================
-- ACCOUNTS PAYABLE
-- ============================================================================

-- Q12. What are the top causes of invoice exceptions, and who owns them?
SELECT h.hold_reason_code, r.hold_reason_description, r.owning_team,
       COUNT(*)                                       AS holds,
       ROUND(SUM(h.blocked_amount_usd) / 1e6, 2)      AS blocked_musd,
       ROUND(AVG(h.days_held), 0)                     AS avg_days
FROM fact_invoice_hold h JOIN dim_hold_reason r USING (hold_reason_id)
GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 12;

-- Q13. What is the first-pass match rate, by match type?
SELECT match_type,
       COUNT(*)                                                   AS lines,
       ROUND(100.0 * AVG(is_first_pass_match), 1)                 AS first_pass_pct,
       ROUND(100.0 * AVG(CASE WHEN exception_reason_code = 'PRICE_VAR'
                              THEN 1 ELSE 0 END), 1)              AS price_var_pct,
       ROUND(100.0 * AVG(CASE WHEN exception_reason_code = 'QTY_VAR'
                              THEN 1 ELSE 0 END), 1)              AS qty_var_pct
FROM fact_match_result GROUP BY 1 ORDER BY 2 DESC;

-- Q14. How much early-payment discount are we leaving on the table, and why?
SELECT ROUND(SUM(discount_available_usd) / 1e3, 1)  AS available_kusd,
       ROUND(SUM(discount_taken_usd) / 1e3, 1)      AS taken_kusd,
       ROUND(SUM(discount_missed_usd) / 1e3, 1)     AS missed_kusd,
       ROUND(100.0 * SUM(CASE WHEN missed_due_to_approval = 1
                              THEN discount_missed_usd ELSE 0 END)
             / NULLIF(SUM(discount_missed_usd), 0), 0) AS pct_missed_on_approval
FROM fact_invoice
WHERE invoice_date >= (SELECT MAX(invoice_date) - INTERVAL 12 MONTH FROM fact_invoice);

-- Q15. What does the payables ageing look like?
SELECT aging_bucket,
       COUNT(*)                                  AS invoices,
       ROUND(SUM(open_amount_usd) / 1e6, 2)      AS open_musd
FROM fact_ap_aging_snapshot
WHERE snapshot_month_end = (SELECT MAX(snapshot_month_end) FROM fact_ap_aging_snapshot)
GROUP BY 1 ORDER BY 3 DESC;

-- Q16. How big is the GR/IR accrual, and how old is it?
SELECT CASE WHEN age_days > 180 THEN '180+ days'
            WHEN age_days > 90  THEN '91-180 days'
            WHEN age_days > 30  THEN '31-90 days'
            ELSE '0-30 days' END                    AS age_band,
       COUNT(*)                                     AS po_lines,
       ROUND(SUM(exception_value_usd) / 1e6, 2)     AS accrual_musd
FROM fact_p2p_exception WHERE exception_type = 'GR_IR'
GROUP BY 1 ORDER BY 3 DESC;

-- Q17. Which approvers are the bottleneck?
-- Grouped on the APPROVER's department, not the document's. Grouping on the
-- document's department splits one approver's queue across every department
-- they approve for, and nobody clears the volume threshold.
SELECT e.full_name, e.role_name, e.department_name,
       COUNT(*)                        AS approvals,
       ROUND(AVG(a.days_in_queue), 1)  AS avg_days_in_queue,
       ROUND(SUM(a.document_amount_usd) / 1e6, 2) AS approved_musd
FROM fact_approval_event a
JOIN dim_employee e ON e.employee_id = a.approver_employee_id
GROUP BY 1, 2, 3 HAVING COUNT(*) > 50
ORDER BY avg_days_in_queue DESC LIMIT 10;

-- ============================================================================
-- FRAUD AND RISK
-- ============================================================================

-- Q18. Which suppliers share a bank account? (Note the benign cluster: two
--      subsidiaries of one parent legitimately share a remit-to account.)
SELECT b.account_number_hash,
       COUNT(DISTINCT b.supplier_id)              AS suppliers,
       COUNT(DISTINCT s.supplier_parent_id)       AS distinct_parents,
       STRING_AGG(DISTINCT s.supplier_name, ' | ') AS names
FROM dim_supplier_bank_account b JOIN dim_supplier s USING (supplier_id)
GROUP BY 1 HAVING COUNT(DISTINCT b.supplier_id) > 1
ORDER BY distinct_parents DESC, suppliers DESC;

-- Q19. Find potential duplicate payments: same supplier group, near-identical
--      amount, within ten days. Fuzzy on purpose - exact matches are impossible
--      in a real ERP.
SELECT a.invoice_number AS inv_a, b.invoice_number AS inv_b,
       s1.supplier_name AS supplier_a, s2.supplier_name AS supplier_b,
       ROUND(a.gross_amount_usd, 2) AS amount,
       a.invoice_date, b.invoice_date AS invoice_date_b,
       a.payment_status, b.payment_status AS payment_status_b
FROM fact_invoice a
JOIN dim_supplier s1 ON s1.supplier_id = a.supplier_id
JOIN fact_invoice b ON b.invoice_id > a.invoice_id
JOIN dim_supplier s2 ON s2.supplier_id = b.supplier_id
WHERE s1.supplier_parent_id = s2.supplier_parent_id
  AND ABS(a.gross_amount_usd - b.gross_amount_usd) <= a.gross_amount_usd * 0.01
  AND ABS(DATE_DIFF('day', a.invoice_date, b.invoice_date)) <= 10
  AND a.gross_amount_usd > 1000
  AND a.invoice_type = 'Standard Invoice' AND b.invoice_type = 'Standard Invoice'
ORDER BY a.gross_amount_usd DESC LIMIT 20;

-- Q20. Duplicates we actually PAID. This is the money line.
SELECT COUNT(*)                                  AS paid_duplicates,
       ROUND(SUM(amount_paid_usd) / 1e3, 1)      AS paid_kusd
FROM fact_invoice
WHERE is_duplicate_suspect = 1 AND payment_status IN ('Paid', 'Partially Paid');

-- Q21. Are buyers systematically raising POs just below their approval limit?
--      Compared against the policy in force ON THE PO DATE, not today's.
WITH band AS (
  SELECT buyer_employee_id,
         COUNT(*) FILTER (WHERE total_amount_usd BETWEEN approval_threshold_usd * 0.90
                                                     AND approval_threshold_usd) AS just_below,
         COUNT(*) FILTER (WHERE total_amount_usd BETWEEN approval_threshold_usd
                                                     AND approval_threshold_usd * 1.10) AS just_above,
         COUNT(*) AS total_pos
  FROM fact_purchase_order GROUP BY 1)
SELECT e.full_name, b.just_below, b.just_above, b.total_pos,
       ROUND(1.0 * b.just_below / NULLIF(b.just_above, 0), 2) AS below_above_ratio
FROM band b JOIN dim_employee e ON e.employee_id = b.buyer_employee_id
WHERE b.just_below >= 3
ORDER BY below_above_ratio DESC, b.just_below DESC LIMIT 10;

-- Q22. Identify potential PO splitting: same buyer, same supplier, same category,
--      several POs inside ten days that together cross the approval threshold.
SELECT p.buyer_employee_id, e.full_name, p.supplier_id, s.supplier_name,
       COUNT(*)                              AS pos_in_window,
       ROUND(SUM(p.total_amount_usd), 0)     AS combined_usd,
       ROUND(MAX(p.approval_threshold_usd), 0) AS threshold_usd,
       MIN(p.po_date) AS first_po, MAX(p.po_date) AS last_po
FROM fact_purchase_order p
JOIN dim_employee e ON e.employee_id = p.buyer_employee_id
JOIN dim_supplier s USING (supplier_id)
GROUP BY 1, 2, 3, 4, DATE_TRUNC('month', p.po_date)
HAVING COUNT(*) >= 2
   AND SUM(p.total_amount_usd) > MAX(p.approval_threshold_usd)
   AND MAX(p.total_amount_usd) < MAX(p.approval_threshold_usd)
   AND DATE_DIFF('day', MIN(p.po_date), MAX(p.po_date)) <= 10
ORDER BY combined_usd DESC LIMIT 15;

-- Q23. Employees whose name matches a supplier contact. Includes coincidental
--      surname collisions on purpose - this is a ranking problem, not a filter.
SELECT s.supplier_name, s.primary_contact_name, e.full_name AS employee_name,
       e.department_name,
       ROUND(SUM(f.spend_amount_usd) / 1e3, 1) AS spend_kusd,
       CASE WHEN s.primary_contact_name = e.full_name THEN 'Full name match'
            ELSE 'Surname only' END AS match_strength
FROM dim_supplier s
JOIN dim_employee e ON e.last_name = SPLIT_PART(s.primary_contact_name, ' ', 2)
LEFT JOIN fact_spend f ON f.supplier_id = s.supplier_id
GROUP BY 1, 2, 3, 4, 6
ORDER BY match_strength, spend_kusd DESC LIMIT 20;

-- Q24. Suppliers that were INACTIVE on the day the PO was raised.
SELECT s.supplier_name, h.supplier_status, h.effective_from_date,
       COUNT(*)                                 AS pos_after_deactivation,
       ROUND(SUM(p.total_amount_usd) / 1e3, 1)  AS value_kusd
FROM fact_purchase_order p
JOIN dim_supplier s USING (supplier_id)
JOIN dim_supplier_status_history h ON h.supplier_id = p.supplier_id
WHERE h.supplier_status <> 'Active'
  AND p.po_date >= h.effective_from_date
GROUP BY 1, 2, 3 ORDER BY 5 DESC LIMIT 15;

-- ============================================================================
-- SUPPLIER 360  -  the drill-through the demo lands on
-- ============================================================================

-- Q25. Everything about one supplier, on one row.
WITH t AS (SELECT MAX(spend_date) - INTERVAL 12 MONTH AS ttm FROM fact_spend)
SELECT s.supplier_name, s.risk_tier, s.supplier_status,
       ROUND((SELECT SUM(f.spend_amount_usd) FROM fact_spend f, t
              WHERE f.supplier_id = s.supplier_id AND f.spend_date >= t.ttm) / 1e6, 2)
           AS ttm_spend_musd,
       (SELECT COUNT(*) FROM fact_purchase_order p
        WHERE p.supplier_id = s.supplier_id AND p.po_status = 'Open') AS open_pos,
       (SELECT ROUND(100.0 * AVG(l.is_on_time), 1) FROM fact_purchase_order_line l
        WHERE l.supplier_id = s.supplier_id AND l.is_on_time IS NOT NULL)
           AS on_time_pct,
       (SELECT ROUND(100.0 * AVG(m.is_first_pass_match), 1) FROM fact_match_result m
        WHERE m.supplier_id = s.supplier_id) AS first_pass_pct,
       (SELECT ROUND(SUM(l.gr_ir_amount_usd) / 1e3, 1) FROM fact_purchase_order_line l
        WHERE l.supplier_id = s.supplier_id) AS gr_ir_kusd
FROM dim_supplier s
WHERE s.supplier_name LIKE 'Northbeam%';
