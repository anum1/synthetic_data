-- Vantage Industrial - Order-to-Cash Control Tower - databricks DDL
-- Generated from data/full on 2026-08-20. Do not hand-edit:
-- rerun src/emit_ddl.py --tier full instead.

CREATE CATALOG IF NOT EXISTS VANTAGE_O2C;
CREATE SCHEMA IF NOT EXISTS VANTAGE_O2C.ANALYTICS;
USE VANTAGE_O2C.ANALYTICS;

CREATE OR REPLACE TABLE contract_pricing (
    contract_price_id                        INT NOT NULL,
    contract_id                              STRING,
    customer_id                              INT,
    product_id                               INT,
    list_price_usd                           DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    contract_discount_pct                    DECIMAL(12,6),
    min_price_usd                            DECIMAL(18,2),
    rebate_pct                               DECIMAL(12,6),
    valid_from_date                          DATE,
    valid_to_date                            DATE,
    price_basis                              STRING,
    is_current                               INT
);
COMMENT ON TABLE contract_pricing IS 'Vantage Industrial O2C - 176,098 rows at tier full';

CREATE OR REPLACE TABLE dim_carrier (
    carrier_id                               INT NOT NULL,
    carrier_code                             STRING,
    carrier_name                             STRING,
    service_level                            STRING,
    carrier_service_name                     STRING,
    transit_multiplier                       DECIMAL(12,6),
    cost_multiplier                          DECIMAL(12,6),
    is_expedited                             INT,
    baseline_on_time_rate                    DECIMAL(12,6),
    is_active                                INT
);
COMMENT ON TABLE dim_carrier IS 'Vantage Industrial O2C - 40 rows at tier full';

CREATE OR REPLACE TABLE dim_currency (
    currency_id                              INT NOT NULL,
    currency_code                            STRING,
    currency_name                            STRING,
    currency_symbol                          STRING,
    budget_rate_per_usd                      DECIMAL(18,2),
    is_reporting_currency                    INT,
    decimal_places                           INT
);
COMMENT ON TABLE dim_currency IS 'Vantage Industrial O2C - 8 rows at tier full';

CREATE OR REPLACE TABLE dim_customer (
    customer_id                              INT NOT NULL,
    customer_number                          STRING,
    customer_name                            STRING,
    legal_name                               STRING,
    customer_segment                         STRING,
    industry                                 STRING,
    preferred_channel                        STRING,
    region                                   STRING,
    country                                  STRING,
    state_province                           STRING,
    city                                     STRING,
    business_unit                            STRING,
    currency_code                            STRING,
    payment_terms_code                       STRING,
    billing_rule                             STRING,
    credit_rating                            STRING,
    customer_since_date                      DATE,
    is_active                                INT,
    global_account_id                        INT,
    global_account_name                      STRING,
    credit_limit_usd                         DECIMAL(18,2),
    credit_status                            STRING,
    last_credit_review_date                  DATE,
    customer_path                            STRING,
    customer_level_1                         STRING,
    customer_level_2                         STRING,
    customer_level_3                         STRING,
    customer_level_4                         STRING,
    customer_level_5                         STRING,
    duplicate_of_customer_id                 INT
);
COMMENT ON TABLE dim_customer IS 'Vantage Industrial O2C - 5,000 rows at tier full';

CREATE OR REPLACE TABLE dim_customer_site (
    site_id                                  INT NOT NULL,
    customer_id                              INT,
    site_code                                STRING,
    site_name                                STRING,
    site_type                                STRING,
    address_line_1                           STRING,
    city                                     STRING,
    state_province                           STRING,
    country                                  STRING,
    region                                   STRING,
    postal_code                              STRING,
    is_ship_to                               INT,
    is_bill_to                               INT,
    is_primary_site                          INT
);
COMMENT ON TABLE dim_customer_site IS 'Vantage Industrial O2C - 8,046 rows at tier full';

CREATE OR REPLACE TABLE dim_date (
    calendar_date                            DATE,
    date_key                                 INT NOT NULL,
    day_of_week                              INT,
    day_name                                 STRING,
    day_of_month                             INT,
    day_of_year                              INT,
    week_of_year                             INT,
    month_number                             INT,
    month_name                               STRING,
    month_abbr                               STRING,
    quarter_number                           INT,
    quarter_name                             STRING,
    calendar_year                            INT,
    year_month_key                           INT,
    year_month_name                          STRING,
    year_quarter_name                        STRING,
    month_start_date                         DATE,
    month_end_date                           DATE,
    is_month_end                             INT,
    is_quarter_end                           INT,
    is_weekend                               INT,
    fiscal_year                              INT,
    fiscal_month_number                      INT,
    fiscal_quarter_number                    INT,
    fiscal_quarter_name                      STRING,
    fiscal_period_key                        INT,
    is_holiday                               INT,
    holiday_name                             STRING,
    is_business_day                          INT,
    business_day_index                       INT,
    days_from_as_of                          INT,
    months_from_as_of                        INT,
    is_current_year                          INT,
    is_prior_year                            INT,
    is_last_12_months                        INT,
    is_prior_12_months                       INT,
    is_ytd                                   INT
);
COMMENT ON TABLE dim_date IS 'Vantage Industrial O2C - 1,308 rows at tier full';

CREATE OR REPLACE TABLE dim_exchange_rate (
    exchange_rate_id                         INT NOT NULL,
    currency_code                            STRING,
    month_start_date                         DATE,
    year_month_key                           INT,
    rate_per_usd                             DECIMAL(18,2),
    usd_per_unit                             DECIMAL(18,4),
    rate_type                                STRING
);
COMMENT ON TABLE dim_exchange_rate IS 'Vantage Industrial O2C - 344 rows at tier full';

CREATE OR REPLACE TABLE dim_payment_terms (
    payment_terms_id                         INT NOT NULL,
    payment_terms_code                       STRING,
    payment_terms_name                       STRING,
    due_days                                 INT,
    discount_pct                             DECIMAL(12,6),
    discount_days                            INT,
    is_early_discount                        INT,
    terms_group                              STRING
);
COMMENT ON TABLE dim_payment_terms IS 'Vantage Industrial O2C - 12 rows at tier full';

CREATE OR REPLACE TABLE dim_product (
    product_id                               INT NOT NULL,
    sku                                      STRING,
    product_name                             STRING,
    product_category                         STRING,
    product_family                           STRING,
    product_line                             STRING,
    unit_of_measure                          STRING,
    list_price_usd                           DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    standard_margin_pct                      DECIMAL(12,6),
    abc_class                                STRING,
    is_made_to_order                         INT,
    lead_time_days                           INT,
    weight_kg                                DECIMAL(18,4),
    is_hazmat                                INT,
    lifecycle_status                         STRING,
    launch_date                              DATE,
    product_path                             STRING,
    product_level_1                          STRING,
    product_level_2                          STRING,
    product_level_3                          STRING,
    product_level_4                          STRING
);
COMMENT ON TABLE dim_product IS 'Vantage Industrial O2C - 2,000 rows at tier full';

CREATE OR REPLACE TABLE dim_sales_rep (
    sales_rep_id                             INT NOT NULL,
    sales_rep_number                         STRING,
    sales_rep_name                           STRING,
    email                                    STRING,
    region                                   STRING,
    territory                                STRING,
    sales_team                               STRING,
    manager_name                             STRING,
    hire_date                                DATE,
    annual_quota_usd                         INT,
    is_active                                INT
);
COMMENT ON TABLE dim_sales_rep IS 'Vantage Industrial O2C - 250 rows at tier full';

CREATE OR REPLACE TABLE dim_warehouse (
    warehouse_id                             INT NOT NULL,
    warehouse_code                           STRING,
    warehouse_name                           STRING,
    warehouse_type                           STRING,
    city                                     STRING,
    region                                   STRING,
    country                                  STRING,
    daily_line_capacity                      INT,
    storage_sqft                             INT,
    opened_date                              DATE,
    is_active                                INT
);
COMMENT ON TABLE dim_warehouse IS 'Vantage Industrial O2C - 30 rows at tier full';

CREATE OR REPLACE TABLE fact_ar_aging_snapshot (
    ar_aging_id                              INT NOT NULL,
    invoice_id                               INT,
    customer_id                              INT,
    snapshot_date                            DATE,
    year_month_key                           INT,
    open_amount_usd                          DECIMAL(18,2),
    days_past_due                            INT,
    aging_bucket                             STRING,
    business_unit                            STRING,
    region                                   STRING,
    customer_segment                         STRING,
    payment_terms_code                       STRING,
    is_overdue                               INT
);
COMMENT ON TABLE fact_ar_aging_snapshot IS 'Vantage Industrial O2C - 151,179 rows at tier full';

CREATE OR REPLACE TABLE fact_credit_exposure_snapshot (
    credit_exposure_id                       INT NOT NULL,
    customer_id                              INT,
    snapshot_date                            DATE,
    year_month_key                           INT,
    credit_limit_usd                         DECIMAL(18,2),
    open_ar_usd                              DECIMAL(18,2),
    open_order_backlog_usd                   DECIMAL(18,2),
    current_exposure_usd                     DECIMAL(18,2),
    available_credit_usd                     DECIMAL(18,2),
    value_on_credit_hold_usd                 DECIMAL(18,2),
    credit_utilization_pct                   DECIMAL(12,6),
    is_over_limit                            INT,
    credit_rating                            STRING,
    customer_segment                         STRING
);
COMMENT ON TABLE fact_credit_exposure_snapshot IS 'Vantage Industrial O2C - 94,290 rows at tier full';

CREATE OR REPLACE TABLE fact_credit_memo (
    credit_memo_id                           INT NOT NULL,
    credit_memo_number                       STRING,
    invoice_id                               INT,
    customer_id                              INT,
    order_id                                 INT,
    memo_date                                DATE,
    memo_amount_usd                          DECIMAL(18,2),
    memo_reason                              STRING,
    dispute_id                               INT
);
COMMENT ON TABLE fact_credit_memo IS 'Vantage Industrial O2C - 9,800 rows at tier full';

CREATE OR REPLACE TABLE fact_delivery_event (
    delivery_event_id                        INT NOT NULL,
    shipment_id                              INT,
    order_id                                 INT,
    event_sequence                           INT,
    event_date                               DATE,
    event_type                               STRING,
    location_city                            STRING,
    carrier_name                             STRING,
    exception_code                           STRING,
    is_exception                             INT
);
COMMENT ON TABLE fact_delivery_event IS 'Vantage Industrial O2C - 541,720 rows at tier full';

CREATE OR REPLACE TABLE fact_dispute (
    dispute_id                               INT NOT NULL,
    invoice_id                               INT,
    customer_id                              INT,
    order_id                                 INT,
    dispute_date                             DATE,
    dispute_reason                           STRING,
    dispute_amount_usd                       DECIMAL(18,2),
    invoice_amount_usd                       DECIMAL(18,2),
    resolved_date                            DATE,
    resolution_code                          STRING,
    dispute_owner                            STRING,
    business_unit                            STRING,
    customer_segment                         STRING,
    is_open                                  INT,
    days_open                                INT
);
COMMENT ON TABLE fact_dispute IS 'Vantage Industrial O2C - 5,949 rows at tier full';

CREATE OR REPLACE TABLE fact_fulfillment (
    fulfillment_id                           INT NOT NULL,
    fulfillment_number                       STRING,
    order_id                                 INT,
    warehouse_id                             INT,
    fulfillment_created_date                 DATE,
    planned_ship_date                        DATE,
    actual_ship_date                         DATE,
    planned_quantity                         INT,
    fulfilled_quantity                       INT,
    backordered_quantity                     INT,
    cancelled_quantity                       INT,
    line_count                               INT,
    allocated_value_usd                      DECIMAL(18,2),
    ship_delay_days                          INT,
    fulfillment_status                       STRING,
    fill_rate                                DECIMAL(12,6),
    is_backordered                           INT
);
COMMENT ON TABLE fact_fulfillment IS 'Vantage Industrial O2C - 79,198 rows at tier full';

CREATE OR REPLACE TABLE fact_inventory_position (
    inventory_position_id                    INT NOT NULL,
    product_id                               INT,
    warehouse_id                             INT,
    month_start_date                         DATE,
    year_month_key                           INT,
    demand_qty                               INT,
    supply_qty                               INT,
    allocated_qty                            INT,
    closing_qty                              INT,
    available_to_promise_qty                 INT,
    shortfall_qty                            INT,
    unit_cost_usd                            DECIMAL(18,2),
    inventory_value_usd                      DECIMAL(18,2),
    is_stockout                              INT,
    fill_rate                                DECIMAL(12,6)
);
COMMENT ON TABLE fact_inventory_position IS 'Vantage Industrial O2C - 282,558 rows at tier full';

CREATE OR REPLACE TABLE fact_invoice (
    invoice_id                               INT NOT NULL,
    invoice_number                           STRING,
    customer_id                              INT,
    order_id                                 INT,
    bill_to_site_id                          INT,
    sales_rep_id                             INT,
    invoice_date                             DATE,
    due_date                                 DATE,
    first_delivery_date                      DATE,
    payment_terms_code                       STRING,
    billing_rule                             STRING,
    business_unit                            STRING,
    region                                   STRING,
    customer_segment                         STRING,
    currency_code                            STRING,
    po_number                                STRING,
    line_count                               INT,
    order_count                              INT,
    net_amount_usd                           DECIMAL(18,2),
    tax_amount_usd                           DECIMAL(18,2),
    freight_amount_usd                       DECIMAL(18,2),
    total_amount_usd                         DECIMAL(18,2),
    is_duplicate                             INT,
    duplicate_of_invoice_id                  INT,
    days_delivery_to_invoice                 INT,
    days_order_to_invoice                    INT,
    is_written_off                           INT,
    early_discount_taken_usd                 DECIMAL(18,2),
    paid_amount_usd                          DECIMAL(18,2),
    credited_amount_usd                      DECIMAL(18,2),
    open_amount_usd                          DECIMAL(18,2),
    fully_paid_date                          DATE,
    days_overdue                             INT,
    days_to_pay_actual                       INT,
    is_open                                  INT,
    is_overdue                               INT,
    aging_bucket                             STRING,
    invoice_status                           STRING,
    disputed_amount_usd                      DECIMAL(18,2),
    is_disputed                              INT,
    exchange_rate                            DECIMAL(12,6),
    net_amount_local                         DECIMAL(18,2),
    total_amount_local                       DECIMAL(18,2)
);
COMMENT ON TABLE fact_invoice IS 'Vantage Industrial O2C - 82,236 rows at tier full';

CREATE OR REPLACE TABLE fact_invoice_line (
    invoice_line_id                          INT NOT NULL,
    invoice_id                               INT,
    order_id                                 INT,
    order_line_id                            INT,
    shipment_line_id                         INT,
    shipment_id                              INT,
    product_id                               INT,
    quantity_invoiced                        INT,
    unit_price_usd                           DECIMAL(18,2),
    order_unit_price_usd                     DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    extended_cost_usd                        DECIMAL(18,2),
    price_variance_usd                       DECIMAL(18,2),
    contract_variance_usd                    DECIMAL(18,2),
    underbilled_amount_usd                   DECIMAL(18,2),
    has_price_variance                       INT,
    is_below_contract                        INT,
    is_contract_line                         INT
);
COMMENT ON TABLE fact_invoice_line IS 'Vantage Industrial O2C - 318,604 rows at tier full';

CREATE OR REPLACE TABLE fact_o2c_cycle (
    o2c_cycle_id                             INT NOT NULL,
    order_id                                 INT,
    customer_id                              INT,
    sales_rep_id                             INT,
    quote_id                                 INT,
    region                                   STRING,
    country                                  STRING,
    business_unit                            STRING,
    customer_segment                         STRING,
    channel                                  STRING,
    payment_terms_code                       STRING,
    quote_date                               DATE,
    order_date                               DATE,
    booking_month                            DATE,
    promised_delivery_date                   DATE,
    first_ship_date                          DATE,
    last_ship_date                           DATE,
    first_delivery_date                      DATE,
    last_delivery_date                       DATE,
    first_invoice_date                       DATE,
    last_invoice_date                        DATE,
    fully_paid_date                          DATE,
    booked_net_usd                           DECIMAL(18,2),
    cancelled_net_usd                        DECIMAL(18,2),
    net_booked_usd                           DECIMAL(18,2),
    shipped_net_usd                          DECIMAL(18,2),
    delivered_net_usd                        DECIMAL(18,2),
    invoiced_net_usd                         DECIMAL(18,2),
    credited_net_usd                         DECIMAL(18,2),
    collected_net_usd                        DECIMAL(18,2),
    open_ar_net_usd                          DECIMAL(18,2),
    duplicate_invoiced_net_usd               DECIMAL(18,2),
    not_yet_shipped_usd                      DECIMAL(18,2),
    in_transit_usd                           DECIMAL(18,2),
    delivered_not_invoiced_usd               DECIMAL(18,2),
    quote_to_order_days                      INT,
    order_to_ship_days                       INT,
    ship_to_delivery_days                    INT,
    delivery_to_invoice_days                 INT,
    invoice_to_cash_days                     INT,
    order_to_cash_days                       INT,
    cost_amount_usd                          DECIMAL(18,2),
    gross_margin_usd                         DECIMAL(18,2),
    is_cancelled                             INT,
    is_credit_hold                           INT,
    is_backordered                           INT,
    is_late_delivery                         INT,
    is_delivered_not_invoiced                INT,
    is_fully_collected                       INT,
    is_on_time                               INT,
    is_complete                              INT,
    is_billed_correctly                      INT,
    is_undamaged                             INT,
    is_perfect_order                         INT
);
COMMENT ON TABLE fact_o2c_cycle IS 'Vantage Industrial O2C - 74,698 rows at tier full';

CREATE OR REPLACE TABLE fact_o2c_exception (
    exception_id                             INT NOT NULL,
    exception_type                           STRING,
    owner_function                           STRING,
    customer_id                              INT,
    reference_type                           STRING,
    reference_id                             INT,
    order_id                                 INT,
    exception_value_usd                      DECIMAL(18,2),
    since_date                               DATE,
    customer_name                            STRING,
    age_days                                 INT,
    age_bucket                               STRING,
    severity                                 STRING,
    severity_score                           DECIMAL(12,6),
    customer_segment                         STRING
);
COMMENT ON TABLE fact_o2c_exception IS 'Vantage Industrial O2C - 9,521 rows at tier full';

CREATE OR REPLACE TABLE fact_order (
    order_id                                 INT NOT NULL,
    order_number                             STRING,
    quote_id                                 INT,
    customer_id                              INT,
    site_id                                  INT,
    bill_to_site_id                          INT,
    sales_rep_id                             INT,
    order_date                               DATE,
    requested_delivery_date                  DATE,
    promised_delivery_date                   DATE,
    planned_ship_date                        DATE,
    order_source                             STRING,
    channel                                  STRING,
    region                                   STRING,
    country                                  STRING,
    business_unit                            STRING,
    customer_segment                         STRING,
    currency_code                            STRING,
    payment_terms_code                       STRING,
    billing_rule                             STRING,
    shipping_priority                        STRING,
    po_number                                STRING,
    line_count                               INT,
    total_quantity                           INT,
    order_amount_usd                         DECIMAL(18,2),
    discount_amount_usd                      DECIMAL(18,2),
    net_order_amount_usd                     DECIMAL(18,2),
    tax_amount_usd                           DECIMAL(18,2),
    freight_amount_usd                       DECIMAL(18,2),
    total_order_amount_usd                   DECIMAL(18,2),
    cost_amount_usd                          DECIMAL(18,2),
    gross_margin_usd                         DECIMAL(18,2),
    gross_margin_pct                         DECIMAL(12,6),
    credit_status                            STRING,
    credit_hold_date                         DATE,
    credit_release_date                      DATE,
    credit_limit_at_order_usd                DECIMAL(18,2),
    credit_exposure_at_order_usd             DECIMAL(18,2),
    is_credit_hold                           INT,
    cancelled_date                           DATE,
    cancel_reason                            STRING,
    is_cancelled                             INT,
    exchange_rate                            DECIMAL(12,6),
    net_order_amount_local                   DECIMAL(18,2),
    total_order_amount_local                 DECIMAL(18,2)
);
COMMENT ON TABLE fact_order IS 'Vantage Industrial O2C - 74,698 rows at tier full';

CREATE OR REPLACE TABLE fact_order_line (
    order_line_id                            INT NOT NULL,
    order_id                                 INT,
    line_number                              INT,
    product_id                               INT,
    list_price_usd                           DECIMAL(18,2),
    unit_price_usd                           DECIMAL(18,2),
    discount_pct                             DECIMAL(12,6),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    extended_cost_usd                        DECIMAL(18,2),
    margin_usd                               DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    is_contract_price                        INT,
    quote_line_id_src                        INT,
    order_date                               DATE,
    promised_delivery_date                   DATE,
    requested_delivery_date                  DATE,
    customer_id                              INT,
    is_cancelled                             INT,
    credit_status                            STRING,
    region                                   STRING,
    business_unit                            STRING,
    quantity_ordered                         INT,
    warehouse_id                             INT,
    quantity_allocated                       INT,
    quantity_backordered                     INT,
    quantity_cancelled                       INT,
    backorder_expected_date                  DATE
);
COMMENT ON TABLE fact_order_line IS 'Vantage Industrial O2C - 316,295 rows at tier full';

CREATE OR REPLACE TABLE fact_payment (
    payment_id                               INT NOT NULL,
    payment_number                           STRING,
    customer_id                              INT,
    payment_date                             DATE,
    payment_amount_usd                       DECIMAL(18,2),
    currency_code                            STRING,
    payment_method                           STRING,
    bank_reference                           STRING,
    payment_status                           STRING,
    invoice_count                            INT,
    is_unapplied                             INT,
    exchange_rate                            DECIMAL(12,6),
    payment_amount_local                     DECIMAL(18,2)
);
COMMENT ON TABLE fact_payment IS 'Vantage Industrial O2C - 74,584 rows at tier full';

CREATE OR REPLACE TABLE fact_payment_allocation (
    payment_allocation_id                    INT NOT NULL,
    payment_id                               INT,
    invoice_id                               INT,
    customer_id                              INT,
    allocated_amount_usd                     DECIMAL(18,2),
    allocation_date                          DATE,
    allocation_sequence                      INT
);
COMMENT ON TABLE fact_payment_allocation IS 'Vantage Industrial O2C - 93,126 rows at tier full';

CREATE OR REPLACE TABLE fact_quote (
    quote_id                                 INT NOT NULL,
    quote_number                             STRING,
    customer_id                              INT,
    site_id                                  INT,
    sales_rep_id                             INT,
    quote_date                               DATE,
    expiration_date                          DATE,
    currency_code                            STRING,
    region                                   STRING,
    country                                  STRING,
    business_unit                            STRING,
    customer_segment                         STRING,
    channel                                  STRING,
    line_count                               INT,
    quote_amount_usd                         DECIMAL(18,2),
    discount_amount_usd                      DECIMAL(18,2),
    discount_pct                             DECIMAL(12,6),
    net_quote_amount_usd                     DECIMAL(18,2),
    estimated_cost_usd                       DECIMAL(18,2),
    expected_margin_usd                      DECIMAL(18,2),
    expected_margin_pct                      DECIMAL(12,6),
    win_probability                          DECIMAL(18,4),
    quote_status                             STRING,
    lost_reason                              STRING,
    is_won                                   INT,
    is_open                                  INT,
    converted_order_id                       INT,
    days_to_convert                          INT,
    exchange_rate                            DECIMAL(12,6),
    net_quote_amount_local                   DECIMAL(18,2),
    quote_amount_local                       DECIMAL(18,2)
);
COMMENT ON TABLE fact_quote IS 'Vantage Industrial O2C - 165,391 rows at tier full';

CREATE OR REPLACE TABLE fact_quote_line (
    quote_line_id                            INT NOT NULL,
    quote_id                                 INT,
    line_number                              INT,
    product_id                               INT,
    quantity                                 INT,
    list_price_usd                           DECIMAL(18,2),
    quoted_price_usd                         DECIMAL(18,2),
    discount_pct                             DECIMAL(12,6),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    estimated_cost_usd                       DECIMAL(18,2),
    estimated_margin_usd                     DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    is_contract_price                        INT
);
COMMENT ON TABLE fact_quote_line IS 'Vantage Industrial O2C - 694,837 rows at tier full';

CREATE OR REPLACE TABLE fact_return (
    return_id                                INT NOT NULL,
    rma_number                               STRING,
    invoice_id                               INT,
    invoice_line_id                          INT,
    order_id                                 INT,
    customer_id                              INT,
    product_id                               INT,
    product_category                         STRING,
    return_date                              DATE,
    quantity_returned                        INT,
    return_value_usd                         DECIMAL(18,2),
    return_reason                            STRING,
    disposition                              STRING,
    is_credited                              INT
);
COMMENT ON TABLE fact_return IS 'Vantage Industrial O2C - 6,813 rows at tier full';

CREATE OR REPLACE TABLE fact_shipment (
    shipment_id                              INT NOT NULL,
    shipment_number                          STRING,
    order_id                                 INT,
    customer_id                              INT,
    site_id                                  INT,
    warehouse_id                             INT,
    carrier_id                               INT,
    carrier_name                             STRING,
    service_level                            STRING,
    tracking_number                          STRING,
    ship_date                                DATE,
    expected_delivery_date                   DATE,
    actual_delivery_date                     DATE,
    promised_delivery_date                   DATE,
    shipping_priority                        STRING,
    region                                   STRING,
    business_unit                            STRING,
    line_count                               INT,
    shipped_quantity                         INT,
    planned_transit_days                     INT,
    actual_transit_days                      INT,
    delay_days                               INT,
    freight_cost_usd                         DECIMAL(18,2),
    is_expedited                             INT,
    is_backorder_shipment                    INT,
    is_split_shipment                        INT,
    shipment_status                          STRING,
    is_delivered                             INT,
    is_on_time_carrier                       INT,
    is_on_time_promise                       INT,
    is_lost                                  INT
);
COMMENT ON TABLE fact_shipment IS 'Vantage Industrial O2C - 98,697 rows at tier full';

CREATE OR REPLACE TABLE fact_shipment_line (
    shipment_line_id                         INT NOT NULL,
    shipment_id                              INT,
    order_id                                 INT,
    order_line_id                            INT,
    product_id                               INT,
    warehouse_id                             INT,
    quantity_shipped                         INT,
    unit_price_usd                           DECIMAL(18,2),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    agreed_price_usd                         DECIMAL(18,2),
    is_contract_price                        INT,
    is_backorder_line                        INT
);
COMMENT ON TABLE fact_shipment_line IS 'Vantage Industrial O2C - 325,900 rows at tier full';
