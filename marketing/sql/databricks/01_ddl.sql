-- Novareach Software Marketing Analytics - Databricks DDL
-- Generated from data/full by src/emit_ddl.py. Do not edit.

CREATE DATABASE IF NOT EXISTS MARKETING;
USE MARKETING;

CREATE OR REPLACE TABLE dim_activity_type (
    activity_type_id INT,
    activity_type STRING,
    activity_channel STRING,
    lead_score_points SMALLINT,
    is_high_intent TINYINT
);

CREATE OR REPLACE TABLE dim_ad_creative (
    ad_creative_id INT,
    campaign_id INT,
    channel_id INT,
    creative_name STRING,
    creative_format STRING,
    creative_variant STRING,
    headline_theme STRING,
    is_control TINYINT
);

CREATE OR REPLACE TABLE dim_attribution_model (
    attribution_model_id INT,
    model_code STRING,
    model_name STRING,
    model_rule STRING,
    model_description STRING,
    is_default_model TINYINT,
    display_order BIGINT
);

CREATE OR REPLACE TABLE dim_campaign (
    campaign_id INT,
    campaign_name STRING,
    campaign_type STRING,
    channel_id INT,
    channel_name STRING,
    campaign_category STRING,
    objective STRING,
    product_id INT,
    target_segment STRING,
    target_industry STRING,
    target_region STRING,
    start_date DATE,
    end_date DATE,
    agency STRING,
    actual_spend_usd DECIMAL(18,4),
    budget_amount_usd DECIMAL(18,4),
    budget_variance_usd DECIMAL(18,4),
    campaign_status STRING
);

CREATE OR REPLACE TABLE dim_channel (
    channel_id INT,
    channel_name STRING,
    channel_group STRING,
    is_paid_media TINYINT,
    is_digital TINYINT,
    planned_spend_share DECIMAL(18,4),
    planned_cpl_usd DECIMAL(18,4),
    planned_lead_to_mql DECIMAL(18,4),
    planned_mql_to_sql DECIMAL(18,4),
    planned_sql_to_opp DECIMAL(18,4),
    planned_opp_to_won DECIMAL(18,4),
    recommended_spend_usd DECIMAL(18,4),
    planned_spend_usd DECIMAL(18,4),
    recommended_delta_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE dim_contact (
    contact_id INT,
    customer_id INT,
    first_name STRING,
    last_name STRING,
    full_name STRING,
    job_title STRING,
    persona STRING,
    seniority STRING,
    email_address STRING,
    region_name STRING,
    consent_status STRING,
    is_email_subscribed TINYINT,
    is_primary_contact TINYINT,
    suppression_date DATE
);

CREATE OR REPLACE TABLE dim_content_asset (
    content_asset_id INT,
    asset_title STRING,
    asset_type STRING,
    lead_score_weight BIGINT,
    download_share DECIMAL(18,4),
    is_gated TINYINT
);

CREATE OR REPLACE TABLE dim_customer (
    customer_id INT,
    account_name STRING,
    industry_id INT,
    segment_id INT,
    geo_key INT,
    region_name STRING,
    employee_count INT,
    annual_revenue_usd DECIMAL(18,4),
    account_type STRING,
    is_target_account TINYINT,
    is_hero_account TINYINT,
    account_tier STRING
);

CREATE OR REPLACE TABLE dim_date (
    calendar_date DATE,
    date_key INT,
    day_of_week TINYINT,
    day_name STRING,
    day_of_month TINYINT,
    day_of_year SMALLINT,
    week_of_year TINYINT,
    month_number TINYINT,
    month_name STRING,
    month_abbr STRING,
    quarter_number TINYINT,
    quarter_name STRING,
    calendar_year SMALLINT,
    year_month_key INT,
    year_month_name STRING,
    year_quarter_name STRING,
    month_start_date DATE,
    month_end_date DATE,
    is_month_end TINYINT,
    is_quarter_end TINYINT,
    is_weekend TINYINT,
    fiscal_year SMALLINT,
    fiscal_month_number TINYINT,
    fiscal_quarter_number TINYINT,
    fiscal_quarter_name STRING,
    fiscal_period_key INT,
    is_holiday TINYINT,
    holiday_name STRING,
    is_business_day TINYINT,
    business_day_index INT,
    days_from_as_of INT,
    months_from_as_of SMALLINT,
    is_current_year TINYINT,
    is_prior_year TINYINT,
    is_last_12_months TINYINT,
    is_prior_12_months TINYINT,
    is_ytd TINYINT
);

CREATE OR REPLACE TABLE dim_geography (
    geo_key INT,
    geo_hierarchy STRING,
    region_name STRING,
    sub_region_name STRING,
    country_name STRING,
    country_iso3 STRING,
    local_currency_code STRING,
    state_province STRING,
    city_name STRING,
    geo_path STRING
);

CREATE OR REPLACE TABLE dim_industry (
    industry_id INT,
    industry_name STRING,
    industry_sector STRING,
    lead_share DECIMAL(18,4)
);

CREATE OR REPLACE TABLE dim_lead_source (
    lead_source_id INT,
    lead_source_name STRING,
    source_category STRING,
    is_self_identified TINYINT
);

CREATE OR REPLACE TABLE dim_lost_reason (
    lost_reason_id INT,
    lost_reason STRING,
    lost_reason_category STRING,
    reason_share DECIMAL(18,4),
    is_marketing_addressable TINYINT
);

CREATE OR REPLACE TABLE dim_opportunity_stage (
    stage_id INT,
    stage_name STRING,
    stage_order INT,
    default_probability DECIMAL(18,4),
    is_closed TINYINT,
    is_won TINYINT,
    stage_category STRING
);

CREATE OR REPLACE TABLE dim_product (
    product_id INT,
    product_portfolio STRING,
    product_family STRING,
    product_line STRING,
    gross_margin_pct DECIMAL(18,4),
    list_price_band STRING,
    revenue_share DECIMAL(18,4),
    is_new_product TINYINT,
    launch_date DATE
);

CREATE OR REPLACE TABLE dim_sales_rep (
    sales_rep_id INT,
    rep_name STRING,
    sales_team STRING,
    region_name STRING,
    segment_focus STRING,
    rep_role STRING,
    hire_date DATE,
    quota_usd BIGINT,
    is_active TINYINT
);

CREATE OR REPLACE TABLE dim_segment (
    segment_id INT,
    segment_name STRING,
    employee_band STRING,
    annual_revenue_band STRING,
    planned_account_share DECIMAL(18,4),
    planned_lead_share DECIMAL(18,4),
    planned_won_share DECIMAL(18,4),
    target_deal_size_usd DECIMAL(18,4),
    median_sales_cycle_days BIGINT
);

CREATE OR REPLACE TABLE fact_ad_performance (
    ad_performance_id INT,
    activity_date DATE,
    campaign_id INT,
    channel_id INT,
    ad_creative_id INT,
    device_type STRING,
    placement STRING,
    region_name STRING,
    impressions BIGINT,
    clicks INT,
    spend_usd DECIMAL(18,4),
    video_views BIGINT,
    engagements INT,
    landing_page_visits INT
);

CREATE OR REPLACE TABLE fact_attribution_touch (
    attribution_id INT,
    opportunity_id INT,
    customer_id INT,
    lead_id INT,
    contact_id INT,
    campaign_id INT,
    channel_id INT,
    channel_name STRING,
    touch_type STRING,
    touch_date DATE,
    touch_sequence BIGINT,
    touches_in_journey SMALLINT,
    region_name STRING,
    segment_id INT,
    is_won TINYINT,
    attribution_model_id INT,
    model_code STRING,
    attribution_weight DECIMAL(18,4),
    attributed_pipeline_usd DECIMAL(18,4),
    attributed_revenue_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_budget_scenario (
    budget_scenario_id INT,
    channel_id INT,
    channel_name STRING,
    spend_multiplier DECIMAL(18,4),
    scenario_spend_usd DECIMAL(18,4),
    scenario_pipeline_usd DECIMAL(18,4),
    delta_spend_usd DECIMAL(18,4),
    delta_pipeline_usd DECIMAL(18,4),
    incremental_pipeline_per_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_campaign_daily (
    campaign_daily_id INT,
    activity_date DATE,
    campaign_id INT,
    channel_id INT,
    impressions BIGINT,
    clicks BIGINT,
    video_views BIGINT,
    engagements BIGINT,
    landing_page_visits BIGINT,
    spend_usd DECIMAL(18,4),
    leads INT,
    mqls INT,
    sqls INT,
    form_submissions INT
);

CREATE OR REPLACE TABLE fact_campaign_summary (
    campaign_id INT,
    campaign_name STRING,
    campaign_type STRING,
    channel_id INT,
    channel_name STRING,
    objective STRING,
    product_id INT,
    target_segment STRING,
    target_industry STRING,
    target_region STRING,
    start_date DATE,
    end_date DATE,
    budget_amount_usd DECIMAL(18,4),
    campaign_status STRING,
    agency STRING,
    spend_usd DECIMAL(18,4),
    leads INT,
    mqls INT,
    sqls INT,
    opportunities INT,
    pipeline_usd DECIMAL(18,4),
    won_deals INT,
    revenue_usd DECIMAL(18,4),
    closed INT,
    gross_margin_pct DECIMAL(18,4),
    cpl_usd DECIMAL(18,4),
    cost_per_mql_usd DECIMAL(18,4),
    cost_per_sql_usd DECIMAL(18,4),
    cac_usd DECIMAL(18,4),
    roas DECIMAL(18,4),
    marketing_roi DECIMAL(18,4),
    pipeline_per_usd DECIMAL(18,4),
    lead_to_mql_rate DECIMAL(18,4),
    mql_to_sql_rate DECIMAL(18,4),
    months_since_start SMALLINT,
    pipeline_maturity_pct DECIMAL(18,4),
    open_pipeline_usd DECIMAL(18,4),
    is_mature_cohort TINYINT,
    cohort_period STRING,
    is_ttm_cohort TINYINT
);

CREATE OR REPLACE TABLE fact_channel_response_curve (
    channel_id INT,
    channel_name STRING,
    ttm_spend_usd DECIMAL(18,4),
    ttm_pipeline_usd DECIMAL(18,4),
    ttm_revenue_usd DECIMAL(18,4),
    curve_a DECIMAL(18,4),
    curve_b_usd DECIMAL(18,4),
    saturation_ratio DECIMAL(18,4),
    marginal_pipeline_per_usd DECIMAL(18,4),
    average_pipeline_per_usd DECIMAL(18,4),
    is_past_inflection TINYINT,
    recommended_spend_usd DECIMAL(18,4),
    recommended_delta_usd DECIMAL(18,4),
    marginal_rank SMALLINT
);

CREATE OR REPLACE TABLE fact_email_event (
    email_event_id INT,
    email_send_id INT,
    campaign_id INT,
    contact_id INT,
    customer_id INT,
    region_name STRING,
    email_type STRING,
    event_date DATE,
    event_type STRING
);

CREATE OR REPLACE TABLE fact_email_send (
    email_send_id INT,
    campaign_id INT,
    contact_id INT,
    customer_id INT,
    region_name STRING,
    send_date DATE,
    email_type STRING,
    subject_line STRING,
    is_delivered TINYINT,
    is_bounced TINYINT,
    bounce_type STRING,
    send_month DATE
);

CREATE OR REPLACE TABLE fact_funnel_snapshot (
    funnel_snapshot_id INT,
    month_start DATE,
    source_channel STRING,
    region_name STRING,
    segment_id INT,
    leads INT,
    mqls INT,
    sqls INT,
    sales_accepted INT,
    lead_score_total INT,
    opportunities INT,
    pipeline_created_usd DECIMAL(18,4),
    won_deals INT,
    revenue_usd DECIMAL(18,4),
    channel_id INT
);

CREATE OR REPLACE TABLE fact_lead (
    lead_id INT,
    lead_date DATE,
    contact_id INT,
    customer_id INT,
    campaign_id INT,
    channel_id INT,
    source_channel STRING,
    geo_key INT,
    region_name STRING,
    segment_id INT,
    industry_id INT,
    product_id INT,
    is_reengaged_contact TINYINT,
    is_mql TINYINT,
    is_sql TINYINT,
    is_sales_accepted TINYINT,
    mql_date DATE,
    sql_date DATE,
    sales_accepted_date DATE,
    days_lead_to_mql DECIMAL(18,4),
    days_mql_to_sql DECIMAL(18,4),
    lead_score INT,
    converted_opportunity_id INT,
    lead_source_id INT,
    revenue_potential_usd DECIMAL(18,4),
    lead_status STRING,
    is_disqualified TINYINT,
    lead_grade STRING
);

CREATE OR REPLACE TABLE fact_lead_activity (
    lead_activity_id INT,
    lead_id INT,
    contact_id INT,
    customer_id INT,
    activity_date DATE,
    touch_sequence SMALLINT,
    touches_in_journey SMALLINT,
    channel_name STRING,
    campaign_id INT,
    activity_type STRING,
    content_asset_id INT,
    region_name STRING,
    is_first_touch TINYINT,
    is_last_touch TINYINT,
    is_conversion_touch TINYINT,
    is_web_activity TINYINT,
    lead_score_points SMALLINT
);

CREATE OR REPLACE TABLE fact_marketing_budget (
    marketing_budget_id INT,
    month_start DATE,
    channel_id INT,
    channel_name STRING,
    region_name STRING,
    actual_spend_usd DECIMAL(18,4),
    budget_amount_usd DECIMAL(18,4),
    variance_usd DECIMAL(18,4),
    variance_pct DECIMAL(18,4),
    fiscal_quarter_name STRING
);

CREATE OR REPLACE TABLE fact_opportunity (
    opportunity_id INT,
    customer_id INT,
    contact_id INT,
    lead_id INT,
    campaign_id INT,
    channel_id INT,
    source_channel STRING,
    sales_rep_id INT,
    product_id INT,
    segment_id INT,
    industry_id INT,
    geo_key INT,
    region_name STRING,
    opportunity_date DATE,
    expected_close_date DATE,
    actual_close_date DATE,
    stage_name STRING,
    probability DECIMAL(18,4),
    amount_usd DECIMAL(18,4),
    is_closed TINYINT,
    is_won TINYINT,
    lost_reason_id INT,
    sales_cycle_days DECIMAL(18,4),
    won_amount_usd DECIMAL(18,4),
    open_pipeline_usd DECIMAL(18,4),
    weighted_pipeline_usd DECIMAL(18,4),
    is_hero_journey TINYINT
);

CREATE OR REPLACE TABLE fact_opportunity_stage (
    opportunity_stage_id INT,
    opportunity_id INT,
    customer_id INT,
    stage_name STRING,
    stage_order INT,
    entered_date DATE,
    exited_date DATE,
    sequence SMALLINT,
    is_current_stage TINYINT,
    days_in_stage BIGINT
);

CREATE OR REPLACE TABLE fact_web_event (
    web_event_id INT,
    web_session_id INT,
    contact_id INT,
    customer_id INT,
    lead_id INT,
    campaign_id INT,
    event_date DATE,
    event_sequence SMALLINT,
    event_type STRING,
    page_path STRING,
    page_category STRING,
    content_asset_id INT,
    device_type STRING,
    region_name STRING,
    duration_seconds INT,
    lead_score_points SMALLINT,
    is_conversion_event TINYINT
);

CREATE OR REPLACE TABLE fact_web_session (
    web_session_id INT,
    anonymous_id STRING,
    contact_id INT,
    customer_id INT,
    lead_id INT,
    campaign_id INT,
    session_start_date DATE,
    stitched_at_date DATE,
    is_identified TINYINT,
    traffic_source STRING,
    device_type STRING,
    browser STRING,
    entry_page STRING,
    region_name STRING,
    is_new_visitor TINYINT,
    page_views SMALLINT,
    session_duration_seconds INT,
    is_conversion_session TINYINT,
    is_bounce TINYINT
);
