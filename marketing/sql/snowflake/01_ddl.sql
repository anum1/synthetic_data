-- Novareach Software Marketing Analytics - Snowflake DDL
-- Generated from data/full by src/emit_ddl.py. Do not edit.

CREATE SCHEMA IF NOT EXISTS MARKETING;
USE SCHEMA MARKETING;

CREATE OR REPLACE TABLE dim_activity_type (
    activity_type_id INTEGER,
    activity_type VARCHAR,
    activity_channel VARCHAR,
    lead_score_points SMALLINT,
    is_high_intent SMALLINT
);

CREATE OR REPLACE TABLE dim_ad_creative (
    ad_creative_id INTEGER,
    campaign_id INTEGER,
    channel_id INTEGER,
    creative_name VARCHAR,
    creative_format VARCHAR,
    creative_variant VARCHAR,
    headline_theme VARCHAR,
    is_control SMALLINT
);

CREATE OR REPLACE TABLE dim_attribution_model (
    attribution_model_id INTEGER,
    model_code VARCHAR,
    model_name VARCHAR,
    model_rule VARCHAR,
    model_description VARCHAR,
    is_default_model SMALLINT,
    display_order BIGINT
);

CREATE OR REPLACE TABLE dim_campaign (
    campaign_id INTEGER,
    campaign_name VARCHAR,
    campaign_type VARCHAR,
    channel_id INTEGER,
    channel_name VARCHAR,
    campaign_category VARCHAR,
    objective VARCHAR,
    product_id INTEGER,
    target_segment VARCHAR,
    target_industry VARCHAR,
    target_region VARCHAR,
    start_date DATE,
    end_date DATE,
    agency VARCHAR,
    actual_spend_usd NUMBER(18,4),
    budget_amount_usd NUMBER(18,4),
    budget_variance_usd NUMBER(18,4),
    campaign_status VARCHAR
);

CREATE OR REPLACE TABLE dim_channel (
    channel_id INTEGER,
    channel_name VARCHAR,
    channel_group VARCHAR,
    is_paid_media SMALLINT,
    is_digital SMALLINT,
    planned_spend_share NUMBER(18,4),
    planned_cpl_usd NUMBER(18,4),
    planned_lead_to_mql NUMBER(18,4),
    planned_mql_to_sql NUMBER(18,4),
    planned_sql_to_opp NUMBER(18,4),
    planned_opp_to_won NUMBER(18,4),
    recommended_spend_usd NUMBER(18,4),
    planned_spend_usd NUMBER(18,4),
    recommended_delta_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE dim_contact (
    contact_id INTEGER,
    customer_id INTEGER,
    first_name VARCHAR,
    last_name VARCHAR,
    full_name VARCHAR,
    job_title VARCHAR,
    persona VARCHAR,
    seniority VARCHAR,
    email_address VARCHAR,
    region_name VARCHAR,
    consent_status VARCHAR,
    is_email_subscribed SMALLINT,
    is_primary_contact SMALLINT,
    suppression_date DATE
);

CREATE OR REPLACE TABLE dim_content_asset (
    content_asset_id INTEGER,
    asset_title VARCHAR,
    asset_type VARCHAR,
    lead_score_weight BIGINT,
    download_share NUMBER(18,4),
    is_gated SMALLINT
);

CREATE OR REPLACE TABLE dim_customer (
    customer_id INTEGER,
    account_name VARCHAR,
    industry_id INTEGER,
    segment_id INTEGER,
    geo_key INTEGER,
    region_name VARCHAR,
    employee_count INTEGER,
    annual_revenue_usd NUMBER(18,4),
    account_type VARCHAR,
    is_target_account SMALLINT,
    is_hero_account SMALLINT,
    account_tier VARCHAR
);

CREATE OR REPLACE TABLE dim_date (
    calendar_date DATE,
    date_key INTEGER,
    day_of_week SMALLINT,
    day_name VARCHAR,
    day_of_month SMALLINT,
    day_of_year SMALLINT,
    week_of_year SMALLINT,
    month_number SMALLINT,
    month_name VARCHAR,
    month_abbr VARCHAR,
    quarter_number SMALLINT,
    quarter_name VARCHAR,
    calendar_year SMALLINT,
    year_month_key INTEGER,
    year_month_name VARCHAR,
    year_quarter_name VARCHAR,
    month_start_date DATE,
    month_end_date DATE,
    is_month_end SMALLINT,
    is_quarter_end SMALLINT,
    is_weekend SMALLINT,
    fiscal_year SMALLINT,
    fiscal_month_number SMALLINT,
    fiscal_quarter_number SMALLINT,
    fiscal_quarter_name VARCHAR,
    fiscal_period_key INTEGER,
    is_holiday SMALLINT,
    holiday_name VARCHAR,
    is_business_day SMALLINT,
    business_day_index INTEGER,
    days_from_as_of INTEGER,
    months_from_as_of SMALLINT,
    is_current_year SMALLINT,
    is_prior_year SMALLINT,
    is_last_12_months SMALLINT,
    is_prior_12_months SMALLINT,
    is_ytd SMALLINT
);

CREATE OR REPLACE TABLE dim_geography (
    geo_key INTEGER,
    geo_hierarchy VARCHAR,
    region_name VARCHAR,
    sub_region_name VARCHAR,
    country_name VARCHAR,
    country_iso3 VARCHAR,
    local_currency_code VARCHAR,
    state_province VARCHAR,
    city_name VARCHAR,
    geo_path VARCHAR
);

CREATE OR REPLACE TABLE dim_industry (
    industry_id INTEGER,
    industry_name VARCHAR,
    industry_sector VARCHAR,
    lead_share NUMBER(18,4)
);

CREATE OR REPLACE TABLE dim_lead_source (
    lead_source_id INTEGER,
    lead_source_name VARCHAR,
    source_category VARCHAR,
    is_self_identified SMALLINT
);

CREATE OR REPLACE TABLE dim_lost_reason (
    lost_reason_id INTEGER,
    lost_reason VARCHAR,
    lost_reason_category VARCHAR,
    reason_share NUMBER(18,4),
    is_marketing_addressable SMALLINT
);

CREATE OR REPLACE TABLE dim_opportunity_stage (
    stage_id INTEGER,
    stage_name VARCHAR,
    stage_order INTEGER,
    default_probability NUMBER(18,4),
    is_closed SMALLINT,
    is_won SMALLINT,
    stage_category VARCHAR
);

CREATE OR REPLACE TABLE dim_product (
    product_id INTEGER,
    product_portfolio VARCHAR,
    product_family VARCHAR,
    product_line VARCHAR,
    gross_margin_pct NUMBER(18,4),
    list_price_band VARCHAR,
    revenue_share NUMBER(18,4),
    is_new_product SMALLINT,
    launch_date DATE
);

CREATE OR REPLACE TABLE dim_sales_rep (
    sales_rep_id INTEGER,
    rep_name VARCHAR,
    sales_team VARCHAR,
    region_name VARCHAR,
    segment_focus VARCHAR,
    rep_role VARCHAR,
    hire_date DATE,
    quota_usd BIGINT,
    is_active SMALLINT
);

CREATE OR REPLACE TABLE dim_segment (
    segment_id INTEGER,
    segment_name VARCHAR,
    employee_band VARCHAR,
    annual_revenue_band VARCHAR,
    planned_account_share NUMBER(18,4),
    planned_lead_share NUMBER(18,4),
    planned_won_share NUMBER(18,4),
    target_deal_size_usd NUMBER(18,4),
    median_sales_cycle_days BIGINT
);

CREATE OR REPLACE TABLE fact_ad_performance (
    ad_performance_id INTEGER,
    activity_date DATE,
    campaign_id INTEGER,
    channel_id INTEGER,
    ad_creative_id INTEGER,
    device_type VARCHAR,
    placement VARCHAR,
    region_name VARCHAR,
    impressions BIGINT,
    clicks INTEGER,
    spend_usd NUMBER(18,4),
    video_views BIGINT,
    engagements INTEGER,
    landing_page_visits INTEGER
);

CREATE OR REPLACE TABLE fact_attribution_touch (
    attribution_id INTEGER,
    opportunity_id INTEGER,
    customer_id INTEGER,
    lead_id INTEGER,
    contact_id INTEGER,
    campaign_id INTEGER,
    channel_id INTEGER,
    channel_name VARCHAR,
    touch_type VARCHAR,
    touch_date DATE,
    touch_sequence BIGINT,
    touches_in_journey SMALLINT,
    region_name VARCHAR,
    segment_id INTEGER,
    is_won SMALLINT,
    attribution_model_id INTEGER,
    model_code VARCHAR,
    attribution_weight NUMBER(18,4),
    attributed_pipeline_usd NUMBER(18,4),
    attributed_revenue_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_budget_scenario (
    budget_scenario_id INTEGER,
    channel_id INTEGER,
    channel_name VARCHAR,
    spend_multiplier NUMBER(18,4),
    scenario_spend_usd NUMBER(18,4),
    scenario_pipeline_usd NUMBER(18,4),
    delta_spend_usd NUMBER(18,4),
    delta_pipeline_usd NUMBER(18,4),
    incremental_pipeline_per_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_campaign_daily (
    campaign_daily_id INTEGER,
    activity_date DATE,
    campaign_id INTEGER,
    channel_id INTEGER,
    impressions BIGINT,
    clicks BIGINT,
    video_views BIGINT,
    engagements BIGINT,
    landing_page_visits BIGINT,
    spend_usd NUMBER(18,4),
    leads INTEGER,
    mqls INTEGER,
    sqls INTEGER,
    form_submissions INTEGER
);

CREATE OR REPLACE TABLE fact_campaign_summary (
    campaign_id INTEGER,
    campaign_name VARCHAR,
    campaign_type VARCHAR,
    channel_id INTEGER,
    channel_name VARCHAR,
    objective VARCHAR,
    product_id INTEGER,
    target_segment VARCHAR,
    target_industry VARCHAR,
    target_region VARCHAR,
    start_date DATE,
    end_date DATE,
    budget_amount_usd NUMBER(18,4),
    campaign_status VARCHAR,
    agency VARCHAR,
    spend_usd NUMBER(18,4),
    leads INTEGER,
    mqls INTEGER,
    sqls INTEGER,
    opportunities INTEGER,
    pipeline_usd NUMBER(18,4),
    won_deals INTEGER,
    revenue_usd NUMBER(18,4),
    closed INTEGER,
    gross_margin_pct NUMBER(18,4),
    cpl_usd NUMBER(18,4),
    cost_per_mql_usd NUMBER(18,4),
    cost_per_sql_usd NUMBER(18,4),
    cac_usd NUMBER(18,4),
    roas NUMBER(18,4),
    marketing_roi NUMBER(18,4),
    pipeline_per_usd NUMBER(18,4),
    lead_to_mql_rate NUMBER(18,4),
    mql_to_sql_rate NUMBER(18,4),
    months_since_start SMALLINT,
    pipeline_maturity_pct NUMBER(18,4),
    open_pipeline_usd NUMBER(18,4),
    is_mature_cohort SMALLINT,
    cohort_period VARCHAR,
    is_ttm_cohort SMALLINT
);

CREATE OR REPLACE TABLE fact_channel_response_curve (
    channel_id INTEGER,
    channel_name VARCHAR,
    ttm_spend_usd NUMBER(18,4),
    ttm_pipeline_usd NUMBER(18,4),
    ttm_revenue_usd NUMBER(18,4),
    curve_a NUMBER(18,4),
    curve_b_usd NUMBER(18,4),
    saturation_ratio NUMBER(18,4),
    marginal_pipeline_per_usd NUMBER(18,4),
    average_pipeline_per_usd NUMBER(18,4),
    is_past_inflection SMALLINT,
    recommended_spend_usd NUMBER(18,4),
    recommended_delta_usd NUMBER(18,4),
    marginal_rank SMALLINT
);

CREATE OR REPLACE TABLE fact_email_event (
    email_event_id INTEGER,
    email_send_id INTEGER,
    campaign_id INTEGER,
    contact_id INTEGER,
    customer_id INTEGER,
    region_name VARCHAR,
    email_type VARCHAR,
    event_date DATE,
    event_type VARCHAR
);

CREATE OR REPLACE TABLE fact_email_send (
    email_send_id INTEGER,
    campaign_id INTEGER,
    contact_id INTEGER,
    customer_id INTEGER,
    region_name VARCHAR,
    send_date DATE,
    email_type VARCHAR,
    subject_line VARCHAR,
    is_delivered SMALLINT,
    is_bounced SMALLINT,
    bounce_type VARCHAR,
    send_month DATE
);

CREATE OR REPLACE TABLE fact_funnel_snapshot (
    funnel_snapshot_id INTEGER,
    month_start DATE,
    source_channel VARCHAR,
    region_name VARCHAR,
    segment_id INTEGER,
    leads INTEGER,
    mqls INTEGER,
    sqls INTEGER,
    sales_accepted INTEGER,
    lead_score_total INTEGER,
    opportunities INTEGER,
    pipeline_created_usd NUMBER(18,4),
    won_deals INTEGER,
    revenue_usd NUMBER(18,4),
    channel_id INTEGER
);

CREATE OR REPLACE TABLE fact_lead (
    lead_id INTEGER,
    lead_date DATE,
    contact_id INTEGER,
    customer_id INTEGER,
    campaign_id INTEGER,
    channel_id INTEGER,
    source_channel VARCHAR,
    geo_key INTEGER,
    region_name VARCHAR,
    segment_id INTEGER,
    industry_id INTEGER,
    product_id INTEGER,
    is_reengaged_contact SMALLINT,
    is_mql SMALLINT,
    is_sql SMALLINT,
    is_sales_accepted SMALLINT,
    mql_date DATE,
    sql_date DATE,
    sales_accepted_date DATE,
    days_lead_to_mql NUMBER(18,4),
    days_mql_to_sql NUMBER(18,4),
    lead_score INTEGER,
    converted_opportunity_id INTEGER,
    lead_source_id INTEGER,
    revenue_potential_usd NUMBER(18,4),
    lead_status VARCHAR,
    is_disqualified SMALLINT,
    lead_grade VARCHAR
);

CREATE OR REPLACE TABLE fact_lead_activity (
    lead_activity_id INTEGER,
    lead_id INTEGER,
    contact_id INTEGER,
    customer_id INTEGER,
    activity_date DATE,
    touch_sequence SMALLINT,
    touches_in_journey SMALLINT,
    channel_name VARCHAR,
    campaign_id INTEGER,
    activity_type VARCHAR,
    content_asset_id INTEGER,
    region_name VARCHAR,
    is_first_touch SMALLINT,
    is_last_touch SMALLINT,
    is_conversion_touch SMALLINT,
    is_web_activity SMALLINT,
    lead_score_points SMALLINT
);

CREATE OR REPLACE TABLE fact_marketing_budget (
    marketing_budget_id INTEGER,
    month_start DATE,
    channel_id INTEGER,
    channel_name VARCHAR,
    region_name VARCHAR,
    actual_spend_usd NUMBER(18,4),
    budget_amount_usd NUMBER(18,4),
    variance_usd NUMBER(18,4),
    variance_pct NUMBER(18,4),
    fiscal_quarter_name VARCHAR
);

CREATE OR REPLACE TABLE fact_opportunity (
    opportunity_id INTEGER,
    customer_id INTEGER,
    contact_id INTEGER,
    lead_id INTEGER,
    campaign_id INTEGER,
    channel_id INTEGER,
    source_channel VARCHAR,
    sales_rep_id INTEGER,
    product_id INTEGER,
    segment_id INTEGER,
    industry_id INTEGER,
    geo_key INTEGER,
    region_name VARCHAR,
    opportunity_date DATE,
    expected_close_date DATE,
    actual_close_date DATE,
    stage_name VARCHAR,
    probability NUMBER(18,4),
    amount_usd NUMBER(18,4),
    is_closed SMALLINT,
    is_won SMALLINT,
    lost_reason_id INTEGER,
    sales_cycle_days NUMBER(18,4),
    won_amount_usd NUMBER(18,4),
    open_pipeline_usd NUMBER(18,4),
    weighted_pipeline_usd NUMBER(18,4),
    is_hero_journey SMALLINT
);

CREATE OR REPLACE TABLE fact_opportunity_stage (
    opportunity_stage_id INTEGER,
    opportunity_id INTEGER,
    customer_id INTEGER,
    stage_name VARCHAR,
    stage_order INTEGER,
    entered_date DATE,
    exited_date DATE,
    sequence SMALLINT,
    is_current_stage SMALLINT,
    days_in_stage BIGINT
);

CREATE OR REPLACE TABLE fact_web_event (
    web_event_id INTEGER,
    web_session_id INTEGER,
    contact_id INTEGER,
    customer_id INTEGER,
    lead_id INTEGER,
    campaign_id INTEGER,
    event_date DATE,
    event_sequence SMALLINT,
    event_type VARCHAR,
    page_path VARCHAR,
    page_category VARCHAR,
    content_asset_id INTEGER,
    device_type VARCHAR,
    region_name VARCHAR,
    duration_seconds INTEGER,
    lead_score_points SMALLINT,
    is_conversion_event SMALLINT
);

CREATE OR REPLACE TABLE fact_web_session (
    web_session_id INTEGER,
    anonymous_id VARCHAR,
    contact_id INTEGER,
    customer_id INTEGER,
    lead_id INTEGER,
    campaign_id INTEGER,
    session_start_date DATE,
    stitched_at_date DATE,
    is_identified SMALLINT,
    traffic_source VARCHAR,
    device_type VARCHAR,
    browser VARCHAR,
    entry_page VARCHAR,
    region_name VARCHAR,
    is_new_visitor SMALLINT,
    page_views SMALLINT,
    session_duration_seconds INTEGER,
    is_conversion_session SMALLINT,
    is_bounce SMALLINT
);
