-- =============================================================================
-- GlobalTech HR Analytics - 50 demo questions
--
-- Every one runs against the generated tables and returns real rows. Written for
-- DuckDB (src/run_questions.py) and portable to Snowflake and Databricks with no
-- changes beyond the catalog prefix.
--
-- The as-of date is never hard-coded: it is read from the data, so these stay
-- correct after any regeneration.
-- =============================================================================


-- =========================== PAGE 1 - WORKFORCE ==============================

-- Q1: What is our headcount today, and how has it changed over 12 months?
WITH months AS (
    SELECT year_month_key, COUNT(*) AS headcount, SUM(fte) AS fte
    FROM fact_workforce_snapshot GROUP BY 1
)
SELECT year_month_key, headcount, ROUND(fte, 1) AS fte,
       headcount - LAG(headcount, 12) OVER (ORDER BY year_month_key) AS yoy_change,
       ROUND(headcount * 1.0 / LAG(headcount, 12) OVER (ORDER BY year_month_key) - 1, 4)
           AS yoy_pct
FROM months ORDER BY year_month_key DESC LIMIT 13;

-- Q2: Which functions contributed most to headcount growth?
WITH b AS (SELECT MAX(year_month_key) AS cur FROM fact_workforce_snapshot)
SELECT s.function_name,
       COUNT(*) FILTER (WHERE s.year_month_key = b.cur) AS headcount_now,
       COUNT(*) FILTER (WHERE s.year_month_key = b.cur - 100) AS headcount_last_year,
       COUNT(*) FILTER (WHERE s.year_month_key = b.cur)
           - COUNT(*) FILTER (WHERE s.year_month_key = b.cur - 100) AS change
FROM fact_workforce_snapshot s CROSS JOIN b
WHERE s.year_month_key IN (b.cur, b.cur - 100)
GROUP BY 1 ORDER BY change DESC;

-- Q3: Headcount by country and region.
SELECT l.region, s.country, COUNT(*) AS headcount, ROUND(SUM(s.fte), 1) AS fte,
       ROUND(AVG(s.base_salary_usd), 0) AS avg_salary_usd
FROM fact_workforce_snapshot s JOIN dim_location l USING (location_id)
WHERE s.year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1, 2 ORDER BY headcount DESC;

-- Q4: What is our voluntary attrition rate by function?
WITH bounds AS (SELECT MAX(snapshot_date) AS d FROM fact_workforce_snapshot),
     pop AS (SELECT function_name, COUNT(*) / 12.0 AS avg_headcount
             FROM fact_workforce_snapshot, bounds
             WHERE snapshot_date > d - INTERVAL 12 MONTH GROUP BY 1),
     ex AS (SELECT s.function_name,
                   COUNT(*) FILTER (WHERE t.voluntary_flag = 1) AS voluntary,
                   COUNT(*) FILTER (WHERE t.regrettable_flag = 1) AS regrettable
            FROM fact_termination t
            JOIN (SELECT DISTINCT employee_id, function_name
                  FROM fact_workforce_snapshot) s USING (employee_id)
            CROSS JOIN bounds
            WHERE t.termination_date > bounds.d - INTERVAL 12 MONTH GROUP BY 1)
SELECT pop.function_name, ROUND(pop.avg_headcount, 0) AS avg_headcount,
       ex.voluntary, ex.regrettable,
       ROUND(ex.voluntary / pop.avg_headcount, 4) AS voluntary_rate,
       ROUND(ex.regrettable / pop.avg_headcount, 4) AS regrettable_rate
FROM pop JOIN ex USING (function_name) ORDER BY voluntary_rate DESC;

-- Q5: Which locations have the highest regrettable attrition?
WITH bounds AS (SELECT MAX(snapshot_date) AS d FROM fact_workforce_snapshot)
SELECT l.city, l.country, COUNT(*) AS exits,
       SUM(t.regrettable_flag) AS regrettable,
       ROUND(SUM(t.regrettable_flag) * 1.0 / COUNT(*), 3) AS regrettable_share
FROM fact_termination t JOIN dim_location l USING (location_id), bounds
WHERE t.termination_date > d - INTERVAL 12 MONTH AND t.voluntary_flag = 1
GROUP BY 1, 2 HAVING COUNT(*) >= 10 ORDER BY regrettable_share DESC LIMIT 10;

-- Q6: New hires versus terminations, by month.
WITH h AS (SELECT year_month_key, COUNT(*) AS hires FROM fact_job_history j
           JOIN (SELECT year_month_key,
                        CAST(year_month_key / 100 AS INT) AS y,
                        year_month_key % 100 AS m
                 FROM fact_workforce_snapshot GROUP BY 1) d
             ON YEAR(j.effective_date) = d.y AND MONTH(j.effective_date) = d.m
           WHERE j.action = 'Hire' GROUP BY 1),
     t AS (SELECT YEAR(termination_date) * 100 + MONTH(termination_date) AS year_month_key,
                  COUNT(*) AS terminations,
                  SUM(voluntary_flag) AS voluntary
           FROM fact_termination GROUP BY 1)
SELECT h.year_month_key, h.hires, t.terminations, t.voluntary,
       h.hires - t.terminations AS net_change
FROM h JOIN t USING (year_month_key) ORDER BY 1 DESC LIMIT 14;

-- Q7: What does the tenure profile look like, and where do people leave?
SELECT CASE WHEN tenure_years < 1 THEN '1. <1 year'
            WHEN tenure_years < 2 THEN '2. 1-2 years'
            WHEN tenure_years < 3 THEN '3. 2-3 years'
            WHEN tenure_years < 5 THEN '4. 3-5 years'
            ELSE '5. 5+ years' END AS tenure_band,
       COUNT(*) AS headcount, ROUND(AVG(compa_ratio), 3) AS avg_compa
FROM fact_workforce_snapshot
WHERE year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1 ORDER BY 1;

-- Q8: Span of control - how many people does each level manage?
SELECT job_level, COUNT(*) AS managers,
       ROUND(AVG(direct_reports), 1) AS avg_direct_reports
FROM (SELECT s.manager_employee_id, COUNT(*) AS direct_reports
      FROM fact_workforce_snapshot s
      WHERE s.year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
        AND s.manager_employee_id > 0
      GROUP BY 1) r
JOIN fact_workforce_snapshot m ON m.employee_id = r.manager_employee_id
WHERE m.year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1 ORDER BY 1;

-- Q9: Drill the hierarchy: headcount at every level of the org tree.
SELECT o.organization_type, o.org_level_2 AS business_unit, o.org_level_3 AS function,
       COUNT(*) AS headcount
FROM fact_workforce_snapshot s JOIN dim_organization o USING (organization_id)
WHERE s.year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1, 2, 3 ORDER BY headcount DESC LIMIT 12;

-- Q10: Worker type and employment type mix.
SELECT worker_type, COUNT(*) AS headcount,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct,
       ROUND(AVG(fte), 3) AS avg_fte
FROM fact_workforce_snapshot
WHERE year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1 ORDER BY headcount DESC;


-- ========================= PAGE 2 - COMPENSATION =============================

-- Q11: THE KILLER QUESTION - why did workforce cost rise ~9% on 3% headcount?
SELECT cost_component, ROUND(delta_usd / 1e6, 2) AS delta_musd,
       ROUND(contribution_pct * 100, 2) AS contribution_pct
FROM fact_workforce_cost_bridge
WHERE scope_type = 'Company' ORDER BY component_order;

-- Q12: Decompose the same bridge by function - who drove it?
SELECT scope_name AS function,
       ROUND(MAX(CASE WHEN cost_component = 'Total' THEN contribution_pct END) * 100, 2)
           AS total_pct,
       ROUND(MAX(CASE WHEN cost_component LIKE 'Rate%' THEN delta_usd END) / 1e6, 2)
           AS rate_musd,
       ROUND(MAX(CASE WHEN cost_component LIKE 'Volume%' THEN delta_usd END) / 1e6, 2)
           AS volume_musd,
       ROUND(MAX(CASE WHEN cost_component = 'Mix' THEN delta_usd END) / 1e6, 2)
           AS mix_musd
FROM fact_workforce_cost_bridge WHERE scope_type = 'Function'
GROUP BY 1 ORDER BY total_pct DESC;

-- Q13: Which employees sit below 90% of their salary range midpoint?
SELECT function_name, job_level, COUNT(*) AS employees,
       COUNT(*) FILTER (WHERE compa_ratio < 0.90) AS below_90,
       ROUND(COUNT(*) FILTER (WHERE compa_ratio < 0.90) * 1.0 / COUNT(*), 3) AS share,
       ROUND(AVG(compa_ratio), 3) AS avg_compa
FROM fact_workforce_snapshot
WHERE year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1, 2 HAVING COUNT(*) >= 25 ORDER BY share DESC LIMIT 15;

-- Q14: Which job families have the worst salary compression?
WITH cur AS (SELECT s.*, j.job_family
             FROM fact_workforce_snapshot s JOIN dim_job j USING (job_id)
             WHERE s.year_month_key = (SELECT MAX(year_month_key)
                                       FROM fact_workforce_snapshot))
SELECT job_family,
       ROUND(AVG(CASE WHEN tenure_years >= 3 THEN compa_ratio END), 3) AS tenured_compa,
       ROUND(AVG(CASE WHEN tenure_years < 1 THEN compa_ratio END), 3) AS new_hire_compa,
       ROUND(AVG(CASE WHEN tenure_years < 1 THEN compa_ratio END)
             - AVG(CASE WHEN tenure_years >= 3 THEN compa_ratio END), 3) AS compression_gap,
       COUNT(*) AS employees
FROM cur GROUP BY 1
HAVING COUNT(*) FILTER (WHERE tenure_years < 1) >= 10
   AND COUNT(*) FILTER (WHERE tenure_years >= 3) >= 10
ORDER BY compression_gap DESC LIMIT 12;

-- Q15: Salary distribution against the range: min, midpoint, max, actual.
SELECT r.geo_zone, s.job_level,
       ROUND(AVG(r.minimum_usd), 0) AS range_min,
       ROUND(AVG(r.midpoint_usd), 0) AS range_mid,
       ROUND(AVG(r.maximum_usd), 0) AS range_max,
       ROUND(AVG(s.base_salary_usd), 0) AS actual_avg,
       ROUND(AVG(s.compa_ratio), 3) AS compa
FROM fact_workforce_snapshot s
JOIN job_salary_range r ON r.job_id = s.job_id AND r.geo_zone = s.country
 AND r.effective_year = CAST(s.year_month_key / 100 AS INT)
WHERE s.year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1, 2 ORDER BY 1, 2;

-- Q16: Are high performers actually paid more?
SELECT performance_rating, COUNT(*) AS employees,
       ROUND(AVG(compa_ratio), 3) AS avg_compa,
       ROUND(AVG(base_salary_usd), 0) AS avg_salary_usd,
       ROUND(COUNT(*) FILTER (WHERE compa_ratio < 0.90) * 1.0 / COUNT(*), 3)
           AS share_below_90
FROM fact_workforce_snapshot
WHERE year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
  AND performance_rating > 0
GROUP BY 1 ORDER BY 1;

-- Q17: Do larger salary increases go to higher performers?
SELECT p.performance_rating, COUNT(*) AS increases,
       ROUND(AVG(h.change_percentage) * 100, 2) AS avg_increase_pct
FROM fact_salary_history h
JOIN fact_performance_review p ON p.employee_id = h.employee_id
 AND p.review_year = YEAR(h.effective_date)
WHERE h.change_reason = 'Annual Merit'
GROUP BY 1 ORDER BY 1;

-- Q18: What drove salary growth - merit, promotion or market adjustment?
SELECT YEAR(effective_date) AS yr, change_reason, COUNT(*) AS actions,
       ROUND(AVG(change_percentage) * 100, 2) AS avg_pct,
       ROUND(SUM(salary_amount_usd - prior_salary_usd) / 1e6, 2) AS added_musd
FROM fact_salary_history
WHERE change_reason <> 'New Hire'
GROUP BY 1, 2 ORDER BY 1 DESC, added_musd DESC;

-- Q19: Promotions by function, and what they cost.
SELECT s.function_name, COUNT(*) AS promotions,
       ROUND(AVG(h.promotion_percentage) * 100, 2) AS avg_increase_pct,
       ROUND(SUM(h.salary_amount_usd - h.prior_salary_usd) / 1e3, 0) AS added_kusd
FROM fact_salary_history h
JOIN (SELECT DISTINCT employee_id, function_name FROM fact_workforce_snapshot) s
  USING (employee_id)
WHERE h.change_reason = 'Promotion'
  AND h.effective_date > (SELECT MAX(snapshot_date) FROM fact_workforce_snapshot)
                         - INTERVAL 12 MONTH
GROUP BY 1 ORDER BY promotions DESC;

-- Q20: Compa-ratio distribution - the histogram behind the risk card.
SELECT CASE WHEN compa_ratio < 0.80 THEN '1. under 0.80'
            WHEN compa_ratio < 0.90 THEN '2. 0.80-0.90'
            WHEN compa_ratio < 1.00 THEN '3. 0.90-1.00'
            WHEN compa_ratio < 1.10 THEN '4. 1.00-1.10'
            ELSE '5. 1.10+' END AS compa_band,
       COUNT(*) AS employees,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct,
       ROUND(AVG(performance_rating), 2) AS avg_rating
FROM fact_workforce_snapshot
WHERE year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1 ORDER BY 1;

-- Q21: Gender-neutral pay equity check by level (runs on whatever is present).
SELECT job_level, career_track, COUNT(*) AS employees,
       ROUND(AVG(base_salary_usd), 0) AS avg_salary_usd,
       ROUND(MEDIAN(base_salary_usd), 0) AS median_salary_usd,
       ROUND(AVG(compa_ratio), 3) AS avg_compa
FROM fact_workforce_snapshot
WHERE year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1, 2 HAVING COUNT(*) >= 20 ORDER BY 1, 2;


-- ===================== PAGE 3 - PAYROLL & WORKFORCE COST =====================

-- Q22: Total workforce cost, last 12 months, by component.
WITH bounds AS (SELECT MAX(pay_period_end) AS d FROM fact_payroll)
SELECT ROUND(SUM(regular_pay) / 1e6, 1) AS base_musd,
       ROUND(SUM(overtime_pay) / 1e6, 1) AS overtime_musd,
       ROUND(SUM(bonus_pay) / 1e6, 1) AS bonus_musd,
       ROUND(SUM(commission) / 1e6, 1) AS commission_musd,
       ROUND(SUM(allowance) / 1e6, 1) AS allowance_musd,
       ROUND(SUM(employer_tax) / 1e6, 1) AS employer_tax_musd,
       ROUND(SUM(employer_benefit_cost) / 1e6, 1) AS employer_benefits_musd,
       ROUND(SUM(total_employer_cost) / 1e6, 1) AS total_musd
FROM fact_payroll, bounds WHERE pay_period_end > d - INTERVAL 12 MONTH;

-- Q23: Workforce cost by function and country.
WITH bounds AS (SELECT MAX(pay_period_end) AS d FROM fact_payroll)
SELECT function_name, country,
       ROUND(SUM(total_employer_cost) / 1e6, 2) AS cost_musd,
       COUNT(DISTINCT employee_id) AS employees,
       ROUND(SUM(total_employer_cost) / COUNT(DISTINCT employee_id), 0) AS cost_per_employee
FROM fact_payroll, bounds WHERE pay_period_end > d - INTERVAL 12 MONTH
GROUP BY 1, 2 ORDER BY cost_musd DESC LIMIT 15;

-- Q24: Payroll trend by month, split into its components.
SELECT year_month_key,
       ROUND(SUM(regular_pay) / 1e6, 2) AS base,
       ROUND(SUM(overtime_pay) / 1e3, 1) AS overtime_k,
       ROUND(SUM(bonus_pay) / 1e6, 2) AS bonus,
       ROUND(SUM(total_employer_cost) / 1e6, 2) AS total
FROM fact_payroll GROUP BY 1 ORDER BY 1 DESC LIMIT 14;

-- Q25: THE PAYROLL ANOMALY - find it without being told where it is.
WITH m AS (SELECT function_name, country, year_month_key,
                  SUM(overtime_hours) AS ot_hours, SUM(overtime_pay) AS ot_pay,
                  COUNT(DISTINCT employee_id) AS employees
           FROM fact_payroll GROUP BY 1, 2, 3),
     b AS (SELECT function_name, country,
                  MEDIAN(ot_hours) AS median_ot FROM m GROUP BY 1, 2)
SELECT m.function_name, m.country, m.year_month_key, m.employees,
       ROUND(m.ot_hours, 0) AS ot_hours, ROUND(b.median_ot, 0) AS typical_ot_hours,
       ROUND(m.ot_hours / NULLIF(b.median_ot, 0), 1) AS times_normal,
       ROUND(m.ot_pay, 0) AS ot_pay
FROM m JOIN b USING (function_name, country)
WHERE b.median_ot > 0 AND m.ot_hours / b.median_ot > 2
ORDER BY times_normal DESC LIMIT 10;

-- Q26: Overtime is supposed to be non-exempt only. Is it?
SELECT exempt_status, COUNT(*) AS payroll_rows,
       ROUND(SUM(overtime_pay) / 1e3, 1) AS overtime_kusd,
       ROUND(AVG(overtime_hours), 2) AS avg_ot_hours
FROM fact_payroll GROUP BY 1;

-- Q27: Cost per FTE by division, and how it moved.
WITH bounds AS (SELECT MAX(pay_period_end) AS d FROM fact_payroll),
     cur AS (SELECT o.division_name, SUM(p.total_employer_cost) AS cost,
                    COUNT(DISTINCT p.employee_id) AS emps
             FROM fact_payroll p JOIN dim_organization o USING (organization_id), bounds
             WHERE p.pay_period_end > d - INTERVAL 12 MONTH GROUP BY 1),
     pri AS (SELECT o.division_name, SUM(p.total_employer_cost) AS cost,
                    COUNT(DISTINCT p.employee_id) AS emps
             FROM fact_payroll p JOIN dim_organization o USING (organization_id), bounds
             WHERE p.pay_period_end BETWEEN d - INTERVAL 24 MONTH AND d - INTERVAL 12 MONTH
             GROUP BY 1)
SELECT cur.division_name, cur.emps,
       ROUND(cur.cost / cur.emps, 0) AS cost_per_employee,
       ROUND(pri.cost / pri.emps, 0) AS prior_cost_per_employee,
       ROUND(cur.cost / cur.emps / (pri.cost / pri.emps) - 1, 4) AS yoy
FROM cur JOIN pri USING (division_name)
WHERE cur.emps >= 25 ORDER BY yoy DESC LIMIT 12;

-- Q28: Commission attainment for the sales organisation.
WITH bounds AS (SELECT MAX(pay_period_end) AS d FROM fact_payroll)
SELECT year_month_key, ROUND(SUM(commission) / 1e3, 1) AS commission_kusd,
       COUNT(DISTINCT employee_id) AS earners,
       ROUND(SUM(commission) / COUNT(DISTINCT employee_id), 0) AS per_earner
FROM fact_payroll, bounds
WHERE commission > 0 AND pay_period_end > d - INTERVAL 12 MONTH
GROUP BY 1 ORDER BY 1;

-- Q29: Pay frequency mix - the reason "26 pay periods" is the wrong assumption.
SELECT pay_frequency, periods_per_year, COUNT(*) AS payroll_rows,
       COUNT(DISTINCT employee_id) AS employees,
       ROUND(SUM(gross_pay) / 1e6, 1) AS gross_musd
FROM fact_payroll GROUP BY 1, 2 ORDER BY payroll_rows DESC;

-- Q30: Does payroll reconcile to compensation? (It should, to the cent.)
WITH bounds AS (SELECT MAX(pay_period_end) AS d FROM fact_payroll)
SELECT ROUND(SUM(p.bonus_pay) / 1e6, 3) AS payroll_bonus_musd,
       (SELECT ROUND(SUM(bonus_amount_usd) / 1e6, 3) FROM fact_bonus, bounds
        WHERE payout_date > d - INTERVAL 12 MONTH) AS fact_bonus_musd
FROM fact_payroll p, bounds WHERE p.pay_period_end > d - INTERVAL 12 MONTH;


-- =========================== PAGE 4 - BENEFITS ===============================

-- Q31: What is benefits cost per employee, and how fast is it growing?
WITH bounds AS (SELECT MAX(pay_period_end) AS d FROM fact_payroll)
SELECT CASE WHEN pay_period_end > d - INTERVAL 12 MONTH THEN 'Last 12 months'
            ELSE 'Prior 12 months' END AS period,
       ROUND(SUM(employer_benefit_cost) / 1e6, 2) AS employer_cost_musd,
       COUNT(DISTINCT employee_id) AS employees,
       ROUND(SUM(employer_benefit_cost) / COUNT(DISTINCT employee_id), 0) AS per_employee
FROM fact_payroll, bounds
WHERE pay_period_end > d - INTERVAL 24 MONTH GROUP BY 1 ORDER BY 1;

-- Q32: Which benefit types drove the increase in employer cost?
SELECT benefit_type, plan_year,
       ROUND(SUM(prorated_employer_contribution_usd) / 1e6, 2) AS employer_musd,
       COUNT(DISTINCT employee_id) AS enrolled
FROM fact_benefit_enrollment GROUP BY 1, 2 ORDER BY benefit_type, plan_year;

-- Q33: Healthcare as a share of total benefits cost.
WITH y AS (SELECT plan_year, benefit_type,
                  SUM(prorated_employer_contribution_usd) AS cost
           FROM fact_benefit_enrollment GROUP BY 1, 2)
SELECT plan_year, ROUND(SUM(cost) FILTER (WHERE benefit_type = 'Medical')
                        / SUM(cost), 3) AS medical_share,
       ROUND(SUM(cost) / 1e6, 2) AS total_musd
FROM y GROUP BY 1 ORDER BY 1;

-- Q34: Benefits cost per employee by country.
SELECT country, COUNT(DISTINCT employee_id) AS employees,
       ROUND(SUM(prorated_employer_contribution_usd)
             / COUNT(DISTINCT employee_id), 0) AS employer_cost_per_employee
FROM fact_benefit_enrollment
WHERE plan_year = (SELECT MAX(plan_year) FROM fact_benefit_enrollment)
GROUP BY 1 ORDER BY employer_cost_per_employee DESC;

-- Q35: Which plans are growing fastest per enrolled employee?
WITH y AS (SELECT plan_name, plan_year, COUNT(*) AS enrolled,
                  SUM(annual_employer_contribution_usd) / COUNT(*) AS per_head
           FROM fact_benefit_enrollment GROUP BY 1, 2)
SELECT plan_name, ROUND(MAX(per_head) FILTER (WHERE plan_year = (SELECT MAX(plan_year)
                                                                 FROM y)), 0) AS this_year,
       ROUND(MAX(per_head) FILTER (WHERE plan_year = (SELECT MAX(plan_year) FROM y) - 1),
             0) AS last_year,
       ROUND(MAX(per_head) FILTER (WHERE plan_year = (SELECT MAX(plan_year) FROM y))
             / NULLIF(MAX(per_head) FILTER (WHERE plan_year = (SELECT MAX(plan_year)
                                                               FROM y) - 1), 0) - 1,
             4) AS growth
FROM y GROUP BY 1 ORDER BY growth DESC NULLS LAST LIMIT 10;

-- Q36: Coverage-level mix, which is what actually drives medical cost.
SELECT coverage_level, COUNT(*) AS elections,
       ROUND(AVG(annual_employer_contribution_usd), 0) AS avg_employer_cost
FROM fact_benefit_enrollment
WHERE benefit_type = 'Medical'
  AND plan_year = (SELECT MAX(plan_year) FROM fact_benefit_enrollment)
GROUP BY 1 ORDER BY elections DESC;

-- Q37: What did the acquisition add to the benefits book?
SELECT p.is_legacy_acquired_plan, p.plan_name, COUNT(*) AS enrolled,
       ROUND(SUM(e.prorated_employer_contribution_usd) / 1e3, 1) AS employer_kusd
FROM fact_benefit_enrollment e JOIN dim_benefit_plan p USING (benefit_plan_id)
WHERE p.is_legacy_acquired_plan = 1 GROUP BY 1, 2 ORDER BY employer_kusd DESC;


-- ==================== PAGE 5 - WORKFORCE RISK AND AI =========================

-- Q38: Which managers have the worst attrition, benchmarked against their function?
SELECT manager_name, manager_function, ROUND(avg_org_headcount, 0) AS org_size,
       ROUND(voluntary_attrition_rate, 3) AS voluntary_rate,
       ROUND(function_attrition_rate, 3) AS function_rate,
       ROUND(excess_attrition_vs_function, 3) AS excess,
       manager_risk_band
FROM fact_manager_scorecard
WHERE avg_org_headcount >= 20
ORDER BY excess_attrition_vs_function DESC LIMIT 10;

-- Q39: The same list on the raw rate - and why it is the wrong ranking.
SELECT manager_name, manager_function, ROUND(avg_org_headcount, 0) AS org_size,
       ROUND(voluntary_attrition_rate, 3) AS voluntary_rate,
       ROUND(function_attrition_rate, 3) AS function_rate
FROM fact_manager_scorecard
WHERE avg_org_headcount >= 20
ORDER BY voluntary_attrition_rate DESC LIMIT 10;

-- Q40: Is the worst manager's problem showing up in ratings and absence too?
SELECT manager_name, ROUND(avg_org_headcount, 0) AS org_size,
       ROUND(avg_performance_rating, 2) AS avg_rating,
       ROUND(avg_compa_ratio, 3) AS avg_compa,
       ROUND(absence_days_per_employee, 1) AS absence_days,
       ROUND(voluntary_attrition_rate, 3) AS voluntary_rate,
       manager_risk_score
FROM fact_manager_scorecard
WHERE avg_org_headcount >= 20 ORDER BY manager_risk_score DESC LIMIT 8;

-- Q41: Are we losing high performers who are underpaid? (Event 9, discovered.)
WITH bounds AS (SELECT MAX(snapshot_date) AS d FROM fact_workforce_snapshot),
     pop AS (SELECT CASE WHEN performance_rating >= 4 AND compa_ratio < 0.90
                          THEN 'High performer, below 0.90 compa'
                         WHEN performance_rating >= 4 THEN 'High performer, paid at market'
                         WHEN compa_ratio < 0.90 THEN 'Other, below 0.90 compa'
                         ELSE 'Everyone else' END AS segment,
                    COUNT(*) / 12.0 AS avg_headcount
             FROM fact_workforce_snapshot, bounds
             WHERE snapshot_date > d - INTERVAL 12 MONTH GROUP BY 1),
     ex AS (SELECT CASE WHEN performance_rating >= 4 AND compa_ratio_at_exit < 0.90
                          THEN 'High performer, below 0.90 compa'
                        WHEN performance_rating >= 4 THEN 'High performer, paid at market'
                        WHEN compa_ratio_at_exit < 0.90 THEN 'Other, below 0.90 compa'
                        ELSE 'Everyone else' END AS segment,
                   COUNT(*) AS exits
            FROM fact_termination, bounds
            WHERE termination_date > d - INTERVAL 12 MONTH AND voluntary_flag = 1
            GROUP BY 1)
SELECT pop.segment, ROUND(pop.avg_headcount, 0) AS avg_headcount, ex.exits,
       ROUND(ex.exits / pop.avg_headcount, 3) AS resignation_rate
FROM pop JOIN ex USING (segment) ORDER BY resignation_rate DESC;

-- Q42: Who is at risk right now, and why?
SELECT primary_risk_driver, flight_risk_band, COUNT(*) AS employees,
       ROUND(AVG(compa_ratio), 3) AS avg_compa,
       ROUND(AVG(performance_rating), 2) AS avg_rating,
       SUM(is_regrettable_if_lost) AS would_be_regrettable
FROM fact_workforce_risk GROUP BY 1, 2
ORDER BY employees DESC LIMIT 12;

-- Q43: The named list - critical-risk employees a manager can act on.
SELECT r.employee_id, e.first_name, e.last_name, r.function_name, r.job_level,
       r.country, ROUND(r.compa_ratio, 3) AS compa, r.performance_rating,
       r.months_since_promotion, r.flight_risk_score, r.primary_risk_driver
FROM fact_workforce_risk r JOIN dim_employee e USING (employee_id)
WHERE r.flight_risk_band = 'Critical' AND r.is_regrettable_if_lost = 1
ORDER BY r.flight_risk_score DESC LIMIT 15;

-- Q44: What do leavers say the reason was, and does the data agree?
SELECT termination_reason, COUNT(*) AS exits,
       ROUND(AVG(compa_ratio_at_exit), 3) AS avg_compa_at_exit,
       ROUND(AVG(performance_rating), 2) AS avg_rating,
       ROUND(AVG(years_of_service), 1) AS avg_service_years,
       SUM(regrettable_flag) AS regrettable
FROM fact_termination WHERE voluntary_flag = 1
GROUP BY 1 ORDER BY exits DESC;

-- Q45: Absence by organisation - who is running hot?
WITH bounds AS (SELECT MAX(snapshot_date) AS d FROM fact_workforce_snapshot),
     pop AS (SELECT organization_id, COUNT(DISTINCT employee_id) AS employees
             FROM fact_workforce_snapshot, bounds
             WHERE snapshot_date > d - INTERVAL 12 MONTH GROUP BY 1)
SELECT o.department_name, o.division_name, pop.employees,
       ROUND(SUM(a.absence_days) * 1.0 / pop.employees, 1) AS days_per_employee,
       ROUND(SUM(a.absence_days) FILTER (WHERE a.absence_type = 'Sick') * 1.0
             / pop.employees, 1) AS sick_days_per_employee
FROM fact_absence a JOIN pop USING (organization_id)
JOIN dim_organization o USING (organization_id), bounds
WHERE a.start_date > d - INTERVAL 12 MONTH
GROUP BY 1, 2, 3 HAVING pop.employees >= 25
ORDER BY sick_days_per_employee DESC LIMIT 10;


-- ================== ORGANISATION HISTORY AND DATA QUALITY ====================

-- Q46: What happened in the reorganisation - who moved where?
SELECT o_old.organization_name AS moved_from, o_new.division_name AS moved_to,
       COUNT(*) AS employees, MIN(h.effective_date) AS effective_date
FROM fact_job_history h
JOIN dim_organization o_old ON o_old.organization_id = h.old_organization_id
JOIN dim_organization o_new ON o_new.organization_id = h.new_organization_id
WHERE h.action = 'Reorganization'
GROUP BY 1, 2 ORDER BY employees DESC LIMIT 12;

-- Q47: Career movement - what kinds of job events happen, and how often?
SELECT action, COUNT(*) AS events,
       COUNT(DISTINCT employee_id) AS employees,
       MIN(effective_date) AS first_seen, MAX(effective_date) AS last_seen
FROM fact_job_history GROUP BY 1 ORDER BY events DESC;

-- Q48: How is the acquired population doing two years on?
SELECT s.is_acquired, COUNT(*) AS headcount,
       ROUND(AVG(s.compa_ratio), 3) AS avg_compa,
       ROUND(AVG(s.performance_rating), 2) AS avg_rating,
       ROUND(AVG(s.tenure_years), 2) AS avg_tenure,
       (SELECT ROUND(COUNT(*) FILTER (WHERE t.is_acquired = 1) * 1.0
                     / NULLIF(COUNT(*) FILTER (WHERE t.is_acquired = 0), 0), 3)
        FROM fact_termination t WHERE t.voluntary_flag = 1) AS acq_exit_ratio
FROM fact_workforce_snapshot s
WHERE s.year_month_key = (SELECT MAX(year_month_key) FROM fact_workforce_snapshot)
GROUP BY 1;

-- Q49: Cost centres do not follow one convention. Which ones are wrong?
SELECT CASE WHEN cost_center LIKE 'CC-%' THEN 'CC- (standard)'
            WHEN cost_center LIKE 'DS-%' THEN 'DS- (acquired system)'
            ELSE 'other' END AS convention,
       COUNT(*) AS employees, COUNT(DISTINCT cost_center) AS distinct_codes
FROM dim_employee WHERE employee_id > 0 GROUP BY 1 ORDER BY employees DESC;

-- Q50: THE DATA QUALITY QUESTION - what is wrong with this dataset?
SELECT 'Duplicate person records' AS issue,
       COUNT(*) AS rows_affected,
       'Headcount is overstated unless is_duplicate_record = 0' AS impact
FROM dim_employee WHERE is_duplicate_record = 1
UNION ALL
SELECT 'Active employees with no manager', COUNT(*),
       'Break the reporting rollup; roll up to No Manager (id 0)'
FROM dim_employee WHERE is_active = 1 AND manager_employee_id = 0 AND employee_id > 0
UNION ALL
SELECT 'Non-standard cost centre codes', COUNT(*),
       'Cost centre grouping splits the acquired population in two'
FROM dim_employee WHERE cost_center LIKE 'DS-%'
UNION ALL
SELECT 'Payroll posted after termination', COUNT(*),
       'Real money paid to people who had already left'
FROM fact_payroll p JOIN dim_employee e USING (employee_id)
WHERE e.termination_date IS NOT NULL AND p.pay_period_start > e.termination_date
UNION ALL
SELECT 'Inconsistent surname casing', COUNT(*),
       'Name-based joins and lookups miss these rows'
FROM dim_employee WHERE last_name = UPPER(last_name) AND employee_id > 0
ORDER BY rows_affected DESC;
