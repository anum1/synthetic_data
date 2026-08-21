-- Novareach Software - Marketing Performance & Attribution
-- The 25 demo questions, as runnable SQL.
--
-- Written against the parquet files as views (see src/run_questions.py), which
-- is ANSI enough to paste into Snowflake or Databricks after pointing the
-- tables at a schema. Every one is proven to return sane, non-empty results by
-- run_questions.py - a question that fails live is worse than one that was
-- never promised.
--
-- MEASUREMENT RULES (docs/KPI_DEFINITIONS.md):
--   * Spend, leads, MQLs and SQLs are counted by ACTIVITY date.
--   * Pipeline is counted by opportunity CREATED date.
--   * Revenue is counted by CLOSE date. It therefore lags the leads that
--     produced it by a sales cycle - that is the point, not a bug.
--   * Campaign ROI is a COHORT measure and must be read next to
--     pipeline_maturity_pct. A campaign younger than ~9 months has not had
--     time to close anything.

-- =========================================================================
-- EXECUTIVE
-- =========================================================================

-- Q1. How is marketing efficiency trending year over year?
SELECT d.calendar_year,
       ROUND(SUM(cd.spend_usd) / 1e6, 2)                       AS spend_musd,
       SUM(cd.leads)                                            AS leads,
       SUM(cd.mqls)                                             AS mqls,
       ROUND(SUM(cd.spend_usd) / NULLIF(SUM(cd.leads), 0), 2)   AS cpl_usd
FROM fact_campaign_daily cd
JOIN dim_date d ON d.calendar_date = cd.activity_date
GROUP BY d.calendar_year
ORDER BY d.calendar_year;

-- Q2. Which channels generated the most revenue, and at what return?
SELECT c.channel_name,
       ROUND(SUM(s.spend_usd) / 1e6, 2)    AS spend_musd,
       ROUND(SUM(s.revenue_usd) / 1e6, 2)  AS revenue_musd,
       ROUND(SUM(s.revenue_usd) / NULLIF(SUM(s.spend_usd), 0), 2)  AS roas,
       ROUND(SUM(s.revenue_usd * s.gross_margin_pct - s.spend_usd)
             / NULLIF(SUM(s.spend_usd), 0), 2)                     AS marketing_roi
FROM fact_campaign_summary s
JOIN dim_channel c ON c.channel_id = s.channel_id
GROUP BY c.channel_name
ORDER BY revenue_musd DESC;

-- Q3. Where are we wasting marketing spend? (high spend, no pipeline)
SELECT campaign_name, channel_name,
       ROUND(spend_usd, 0)          AS spend_usd,
       leads, mqls, sqls,
       ROUND(pipeline_usd, 0)       AS pipeline_usd,
       ROUND(pipeline_per_usd, 2)   AS pipeline_per_usd,
       ROUND(pipeline_maturity_pct, 2) AS maturity
FROM fact_campaign_summary
WHERE is_mature_cohort = 1 AND spend_usd > 100000
ORDER BY pipeline_per_usd ASC
LIMIT 15;

-- Q4. Which campaigns should we scale? (mature, efficient, real volume)
SELECT campaign_name, channel_name,
       ROUND(spend_usd, 0) AS spend_usd, sqls, won_deals,
       ROUND(revenue_usd, 0) AS revenue_usd, ROUND(roas, 2) AS roas
FROM fact_campaign_summary
WHERE is_mature_cohort = 1 AND won_deals >= 3
ORDER BY roas DESC
LIMIT 15;

-- Q5. Which campaigns should we stop?
SELECT campaign_name, channel_name, ROUND(spend_usd, 0) AS spend_usd,
       leads, sqls, won_deals, ROUND(revenue_usd, 0) AS revenue_usd,
       ROUND(cost_per_sql_usd, 0) AS cost_per_sql_usd
FROM fact_campaign_summary
WHERE is_mature_cohort = 1 AND spend_usd > 150000 AND won_deals <= 1
ORDER BY spend_usd DESC
LIMIT 15;

-- =========================================================================
-- FUNNEL
-- =========================================================================

-- Q6. Where is our biggest funnel conversion problem?
SELECT 'lead -> MQL'  AS step,
       ROUND(1.0 * SUM(mqls) / NULLIF(SUM(leads), 0), 4) AS rate
FROM fact_funnel_snapshot
UNION ALL
SELECT 'MQL -> SQL',
       ROUND(1.0 * SUM(sqls) / NULLIF(SUM(mqls), 0), 4) FROM fact_funnel_snapshot
UNION ALL
SELECT 'SQL -> opportunity',
       ROUND(1.0 * SUM(opportunities) / NULLIF(SUM(sqls), 0), 4) FROM fact_funnel_snapshot
UNION ALL
SELECT 'opportunity -> won',
       ROUND(1.0 * SUM(won_deals) / NULLIF(SUM(opportunities), 0), 4) FROM fact_funnel_snapshot;

-- Q7. Which channels generate the highest-quality leads?
SELECT source_channel,
       SUM(leads) AS leads, SUM(mqls) AS mqls, SUM(sqls) AS sqls,
       ROUND(1.0 * SUM(mqls) / NULLIF(SUM(leads), 0), 4) AS lead_to_mql,
       ROUND(1.0 * SUM(sqls) / NULLIF(SUM(mqls), 0), 4)  AS mql_to_sql
FROM fact_funnel_snapshot
GROUP BY source_channel
HAVING SUM(mqls) > 200
ORDER BY mql_to_sql DESC;

-- Q8. Why did MQL-to-SQL conversion decline? (the current quarter is
--     right-censored by as-of, so it is excluded)
SELECT d.year_quarter_name,
       SUM(f.mqls) AS mqls, SUM(f.sqls) AS sqls,
       ROUND(1.0 * SUM(f.sqls) / NULLIF(SUM(f.mqls), 0), 4) AS mql_to_sql
FROM fact_funnel_snapshot f
JOIN dim_date d ON d.calendar_date = f.month_start
WHERE d.months_from_as_of BETWEEN -14 AND -2
GROUP BY d.year_quarter_name
ORDER BY d.year_quarter_name;

-- Q9. Which industries convert best?
SELECT i.industry_name,
       COUNT(*) AS leads,
       SUM(l.is_mql) AS mqls,
       SUM(l.is_sql) AS sqls,
       ROUND(1.0 * SUM(l.is_sql) / NULLIF(SUM(l.is_mql), 0), 4) AS mql_to_sql
FROM fact_lead l
JOIN dim_industry i ON i.industry_id = l.industry_id
GROUP BY i.industry_name
ORDER BY mql_to_sql DESC;

-- Q10. Which campaigns generate pipeline but not revenue?
SELECT s.campaign_name, s.channel_name,
       ROUND(s.spend_usd, 0)    AS spend_usd,
       ROUND(s.pipeline_usd, 0) AS pipeline_usd,
       ROUND(s.revenue_usd, 0)  AS revenue_usd,
       s.opportunities, s.won_deals,
       ROUND(s.pipeline_maturity_pct, 2) AS maturity
FROM fact_campaign_summary s
WHERE s.is_mature_cohort = 1 AND s.pipeline_usd > 400000
  AND s.revenue_usd < s.pipeline_usd * 0.12
ORDER BY s.pipeline_usd DESC
LIMIT 15;

-- =========================================================================
-- ATTRIBUTION
-- =========================================================================

-- Q11. Show revenue by first-touch versus last-touch attribution.
SELECT channel_name,
       ROUND(SUM(CASE WHEN model_code = 'FIRST_TOUCH'
                      THEN attributed_revenue_usd END) / 1e6, 2) AS first_touch_musd,
       ROUND(SUM(CASE WHEN model_code = 'W_SHAPED'
                      THEN attributed_revenue_usd END) / 1e6, 2) AS w_shaped_musd,
       ROUND(SUM(CASE WHEN model_code = 'LAST_TOUCH'
                      THEN attributed_revenue_usd END) / 1e6, 2) AS last_touch_musd
FROM fact_attribution_touch
GROUP BY channel_name
ORDER BY first_touch_musd DESC;

-- Q12. Which campaigns influence deals but rarely get the final touch?
SELECT c.campaign_name, c.channel_name,
       ROUND(SUM(CASE WHEN a.model_code = 'LINEAR'
                      THEN a.attributed_revenue_usd END), 0) AS influenced_usd,
       ROUND(SUM(CASE WHEN a.model_code = 'LAST_TOUCH'
                      THEN a.attributed_revenue_usd END), 0) AS closed_usd,
       ROUND(SUM(CASE WHEN a.model_code = 'LINEAR'
                      THEN a.attributed_revenue_usd END)
             / NULLIF(SUM(CASE WHEN a.model_code = 'LAST_TOUCH'
                      THEN a.attributed_revenue_usd END), 0), 2) AS influence_ratio
FROM fact_attribution_touch a
JOIN dim_campaign c ON c.campaign_id = a.campaign_id
GROUP BY c.campaign_name, c.channel_name
HAVING SUM(CASE WHEN a.model_code = 'LINEAR'
                THEN a.attributed_revenue_usd END) > 50000
ORDER BY influence_ratio DESC
LIMIT 15;

-- Q13. What is the average number of touches before conversion?
SELECT s.segment_name,
       COUNT(DISTINCT a.opportunity_id)      AS opportunities,
       ROUND(AVG(a.touches_in_journey), 1)   AS avg_touches,
       MAX(a.touches_in_journey)             AS max_touches
FROM fact_attribution_touch a
JOIN dim_segment s ON s.segment_id = a.segment_id
WHERE a.model_code = 'LINEAR' AND a.touch_sequence = 1
GROUP BY s.segment_name
ORDER BY avg_touches DESC;

-- Q14. Which touchpoints are most predictive of conversion?
--      lead_score is SUMMED from real activity, so this reconciles to the
--      behaviours underneath it rather than being a plausible-looking column.
SELECT t.activity_type,
       COUNT(*)                                        AS touches,
       ROUND(AVG(l.lead_score), 1)                     AS avg_lead_score,
       ROUND(AVG(1.0 * l.is_sql), 4)                   AS sql_rate,
       ROUND(AVG(1.0 * l.is_sales_accepted), 4)        AS accept_rate
FROM fact_lead_activity t
JOIN fact_lead l ON l.lead_id = t.lead_id
GROUP BY t.activity_type
HAVING COUNT(*) > 2000
ORDER BY sql_rate DESC;

-- =========================================================================
-- OPTIMISATION  (these need fact_channel_response_curve - PLAN 2.7)
-- =========================================================================

-- Q15. If we cut LinkedIn spend by 20%, what happens to pipeline?
SELECT channel_name,
       spend_multiplier,
       ROUND(scenario_spend_usd, 0)     AS scenario_spend_usd,
       ROUND(delta_spend_usd, 0)        AS delta_spend_usd,
       ROUND(delta_pipeline_usd, 0)     AS delta_pipeline_usd,
       ROUND(incremental_pipeline_per_usd, 2) AS incremental_per_usd
FROM fact_budget_scenario
WHERE channel_name = 'LinkedIn' AND spend_multiplier <= 1.0
  AND spend_multiplier >= 0.6
ORDER BY spend_multiplier;

-- Q16. Where should we invest an additional $1M?
SELECT channel_name,
       ROUND(ttm_spend_usd, 0)                 AS current_spend_usd,
       ROUND(marginal_pipeline_per_usd, 2)     AS marginal_pipeline_per_usd,
       ROUND(average_pipeline_per_usd, 2)      AS average_pipeline_per_usd,
       saturation_ratio, is_past_inflection
FROM fact_channel_response_curve
ORDER BY marginal_pipeline_per_usd DESC;

-- Q17. Which channels have the best marginal ROI, and what is the
--      recommended zero-sum reallocation?
SELECT r.channel_name,
       ROUND(r.ttm_spend_usd, 0)         AS current_usd,
       ROUND(r.recommended_spend_usd, 0) AS recommended_usd,
       ROUND(r.recommended_delta_usd, 0) AS delta_usd,
       r.marginal_rank
FROM fact_channel_response_curve r
ORDER BY r.recommended_delta_usd DESC;

-- Q18. What is the net pipeline effect of the recommended reallocation?
--      Interpolated from the scenario grid at each channel's recommended
--      multiplier - so the number is READ from a model, not asserted.
WITH target AS (
  SELECT r.channel_name,
         r.recommended_spend_usd / NULLIF(r.ttm_spend_usd, 0) AS mult
  FROM fact_channel_response_curve r
), nearest AS (
  SELECT b.channel_name, b.delta_pipeline_usd, b.delta_spend_usd,
         ROW_NUMBER() OVER (PARTITION BY b.channel_name
                            ORDER BY ABS(b.spend_multiplier - t.mult)) AS rn
  FROM fact_budget_scenario b
  JOIN target t ON t.channel_name = b.channel_name
)
SELECT ROUND(SUM(delta_spend_usd), 0)     AS net_spend_change_usd,
       ROUND(SUM(delta_pipeline_usd), 0)  AS net_pipeline_change_usd
FROM nearest WHERE rn = 1;

-- =========================================================================
-- ANOMALY DETECTION
-- =========================================================================

-- Q19. Which campaigns have unusual cost-per-lead increases?
WITH m AS (
  SELECT cd.campaign_id, d.year_month_key,
         SUM(cd.spend_usd) AS spend, SUM(cd.leads) AS leads
  FROM fact_campaign_daily cd
  JOIN dim_date d ON d.calendar_date = cd.activity_date
  GROUP BY cd.campaign_id, d.year_month_key
  HAVING SUM(cd.leads) > 30
), cpl AS (
  SELECT campaign_id, year_month_key, spend / leads AS cpl FROM m
)
SELECT c.campaign_name, c.channel_name,
       ROUND(MAX(cpl.cpl), 2)                          AS peak_cpl_usd,
       ROUND(MIN(cpl.cpl), 2)                          AS trough_cpl_usd,
       ROUND(MAX(cpl.cpl) / NULLIF(MIN(cpl.cpl), 0), 2) AS spike_ratio
FROM cpl JOIN dim_campaign c ON c.campaign_id = cpl.campaign_id
GROUP BY c.campaign_name, c.channel_name
HAVING COUNT(*) >= 3
ORDER BY spike_ratio DESC
LIMIT 10;

-- Q20. Which regions have declining conversion rates?
SELECT o.region_name, d.year_quarter_name,
       COUNT(*)                              AS closed_deals,
       ROUND(AVG(1.0 * o.is_won), 4)         AS win_rate
FROM fact_opportunity o
JOIN dim_date d ON d.calendar_date = o.actual_close_date
WHERE o.is_closed = 1 AND d.months_from_as_of >= -18
GROUP BY o.region_name, d.year_quarter_name
ORDER BY o.region_name, d.year_quarter_name;

-- Q21. Find channels where spend increased but revenue decreased.
WITH y AS (
  SELECT s.channel_name,
         SUM(CASE WHEN d.is_last_12_months = 1 THEN cd.spend_usd ELSE 0 END) AS spend_ttm,
         SUM(CASE WHEN d.is_prior_12_months = 1 THEN cd.spend_usd ELSE 0 END) AS spend_prior
  FROM fact_campaign_daily cd
  JOIN dim_date d ON d.calendar_date = cd.activity_date
  JOIN dim_campaign s ON s.campaign_id = cd.campaign_id
  GROUP BY s.channel_name
), r AS (
  SELECT o.source_channel AS channel_name,
         SUM(CASE WHEN d.is_last_12_months = 1 THEN o.won_amount_usd ELSE 0 END) AS rev_ttm,
         SUM(CASE WHEN d.is_prior_12_months = 1 THEN o.won_amount_usd ELSE 0 END) AS rev_prior
  FROM fact_opportunity o
  JOIN dim_date d ON d.calendar_date = o.actual_close_date
  WHERE o.is_won = 1
  GROUP BY o.source_channel
)
SELECT y.channel_name,
       ROUND(y.spend_ttm / NULLIF(y.spend_prior, 0) - 1, 3) AS spend_growth,
       ROUND(r.rev_ttm / NULLIF(r.rev_prior, 0) - 1, 3)     AS revenue_growth
FROM y JOIN r ON r.channel_name = y.channel_name
WHERE y.spend_prior > 0 AND r.rev_prior > 0
ORDER BY (y.spend_ttm / NULLIF(y.spend_prior, 0))
       - (r.rev_ttm / NULLIF(r.rev_prior, 0)) DESC;

-- Q22. Find sudden drops in website conversion.
SELECT d.year_month_name, e.page_path,
       COUNT(*)                                   AS events,
       ROUND(AVG(1.0 * e.is_conversion_event), 4) AS conversion_rate
FROM fact_web_event e
JOIN dim_date d ON d.calendar_date = e.event_date
WHERE e.page_path IN ('/pricing', '/demo-request')
  AND d.months_from_as_of >= -9
GROUP BY d.year_month_name, d.year_month_key, e.page_path
ORDER BY d.year_month_key, e.page_path;

-- =========================================================================
-- EXECUTIVE AI
-- =========================================================================

-- Q23. Why did marketing-sourced revenue growth stall this year?
--      The whole story in one result: spend, leads and MQLs against pipeline
--      and revenue, year over year.
SELECT 'spend'    AS metric,
       ROUND(SUM(CASE WHEN d.is_last_12_months = 1 THEN cd.spend_usd END), 0) AS ttm,
       ROUND(SUM(CASE WHEN d.is_prior_12_months = 1 THEN cd.spend_usd END), 0) AS prior
FROM fact_campaign_daily cd JOIN dim_date d ON d.calendar_date = cd.activity_date
UNION ALL
SELECT 'leads',
       SUM(CASE WHEN d.is_last_12_months = 1 THEN cd.leads END),
       SUM(CASE WHEN d.is_prior_12_months = 1 THEN cd.leads END)
FROM fact_campaign_daily cd JOIN dim_date d ON d.calendar_date = cd.activity_date
UNION ALL
SELECT 'mqls',
       SUM(CASE WHEN d.is_last_12_months = 1 THEN cd.mqls END),
       SUM(CASE WHEN d.is_prior_12_months = 1 THEN cd.mqls END)
FROM fact_campaign_daily cd JOIN dim_date d ON d.calendar_date = cd.activity_date
UNION ALL
-- Pipeline creation is RIGHT-CENSORED: a lead acquired last month has not had
-- time to become an opportunity (median lead->accepted is ~34 days), so the
-- last two months of any TTM window are structurally short. Both sides of the
-- comparison are therefore lagged two months, which makes the YoY like-for-like
-- instead of showing a 15% collapse that is an artefact of the calendar.
-- (docs/KPI_DEFINITIONS.md, PLAN 2.5)
SELECT 'pipeline_created_lag2m',
       ROUND(SUM(CASE WHEN d.months_from_as_of BETWEEN -13 AND -2
                      THEN o.amount_usd END), 0),
       ROUND(SUM(CASE WHEN d.months_from_as_of BETWEEN -25 AND -14
                      THEN o.amount_usd END), 0)
FROM fact_opportunity o JOIN dim_date d ON d.calendar_date = o.opportunity_date
UNION ALL
SELECT 'revenue',
       ROUND(SUM(CASE WHEN d.is_last_12_months = 1 AND o.is_won = 1
                      THEN o.won_amount_usd END), 0),
       ROUND(SUM(CASE WHEN d.is_prior_12_months = 1 AND o.is_won = 1
                      THEN o.won_amount_usd END), 0)
FROM fact_opportunity o JOIN dim_date d ON d.calendar_date = o.actual_close_date;

-- Q24. Summarise the top three marketing problems: worst return by region.
WITH sp AS (
  SELECT mb.region_name, SUM(mb.actual_spend_usd) AS spend
  FROM fact_marketing_budget mb
  JOIN dim_date d ON d.calendar_date = mb.month_start
  WHERE d.is_last_12_months = 1
  GROUP BY mb.region_name
), rv AS (
  SELECT o.region_name, SUM(o.won_amount_usd) AS revenue
  FROM fact_opportunity o
  JOIN dim_date d ON d.calendar_date = o.actual_close_date
  WHERE o.is_won = 1 AND d.is_last_12_months = 1
  GROUP BY o.region_name
)
SELECT sp.region_name,
       ROUND(sp.spend / 1e6, 2)   AS spend_musd,
       ROUND(rv.revenue / 1e6, 2) AS revenue_musd,
       ROUND(rv.revenue / NULLIF(sp.spend, 0), 2) AS roas
FROM sp JOIN rv ON rv.region_name = sp.region_name
ORDER BY roas ASC;

-- Q25. Show me one customer's full journey. (The hero accounts are flagged so
--      the presenter never lands on a two-touch journey - PLAN 6 / E12.)
SELECT cu.account_name, a.touch_sequence, a.touch_date, a.channel_name,
       a.touch_type, c.campaign_name,
       ROUND(a.attribution_weight, 3)      AS w_shaped_weight,
       ROUND(a.attributed_revenue_usd, 0)  AS attributed_revenue_usd
FROM fact_attribution_touch a
JOIN dim_customer cu ON cu.customer_id = a.customer_id
JOIN dim_campaign c  ON c.campaign_id = a.campaign_id
WHERE cu.is_hero_account = 1 AND a.model_code = 'W_SHAPED' AND a.is_won = 1
ORDER BY a.attributed_revenue_usd DESC, cu.account_name, a.touch_sequence
LIMIT 40;
