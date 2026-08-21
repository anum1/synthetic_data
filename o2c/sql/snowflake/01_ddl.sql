-- Vantage Industrial - Order-to-Cash Control Tower - snowflake DDL
-- Generated from data/full on 2026-08-20. Do not hand-edit:
-- rerun src/emit_ddl.py --tier full instead.

CREATE DATABASE IF NOT EXISTS VANTAGE_O2C;
CREATE SCHEMA IF NOT EXISTS VANTAGE_O2C.ANALYTICS;
USE SCHEMA VANTAGE_O2C.ANALYTICS;

CREATE OR REPLACE TABLE contract_pricing (
    contract_price_id                        NUMBER(10,0) NOT NULL,
    contract_id                              VARCHAR(16),
    customer_id                              NUMBER(10,0),
    product_id                               NUMBER(10,0),
    list_price_usd                           DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    contract_discount_pct                    DECIMAL(12,6),
    min_price_usd                            DECIMAL(18,2),
    rebate_pct                               DECIMAL(12,6),
    valid_from_date                          DATE,
    valid_to_date                            DATE,
    price_basis                              VARCHAR(16),
    is_current                               NUMBER(10,0)
,
    CONSTRAINT pk_contract_pricing PRIMARY KEY (contract_price_id)
);
ALTER TABLE contract_pricing ADD CONSTRAINT fk_contract_pricing_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE contract_pricing ADD CONSTRAINT fk_contract_pricing_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
COMMENT ON TABLE contract_pricing IS 'Vantage Industrial O2C - 176,098 rows at tier full';

CREATE OR REPLACE TABLE dim_carrier (
    carrier_id                               NUMBER(10,0) NOT NULL,
    carrier_code                             VARCHAR(16),
    carrier_name                             VARCHAR(32),
    service_level                            VARCHAR(16),
    carrier_service_name                     VARCHAR(48),
    transit_multiplier                       DECIMAL(12,6),
    cost_multiplier                          DECIMAL(12,6),
    is_expedited                             NUMBER(10,0),
    baseline_on_time_rate                    DECIMAL(12,6),
    is_active                                NUMBER(10,0)
,
    CONSTRAINT pk_dim_carrier PRIMARY KEY (carrier_id)
);
COMMENT ON TABLE dim_carrier IS 'Vantage Industrial O2C - 40 rows at tier full';

CREATE OR REPLACE TABLE dim_currency (
    currency_id                              NUMBER(10,0) NOT NULL,
    currency_code                            VARCHAR(16),
    currency_name                            VARCHAR(32),
    currency_symbol                          VARCHAR(16),
    budget_rate_per_usd                      DECIMAL(18,2),
    is_reporting_currency                    NUMBER(10,0),
    decimal_places                           NUMBER(10,0)
,
    CONSTRAINT pk_dim_currency PRIMARY KEY (currency_id)
);
COMMENT ON TABLE dim_currency IS 'Vantage Industrial O2C - 8 rows at tier full';

CREATE OR REPLACE TABLE dim_customer (
    customer_id                              NUMBER(10,0) NOT NULL,
    customer_number                          VARCHAR(16),
    customer_name                            VARCHAR(64),
    legal_name                               VARCHAR(64),
    customer_segment                         VARCHAR(16),
    industry                                 VARCHAR(32),
    preferred_channel                        VARCHAR(16),
    region                                   VARCHAR(16),
    country                                  VARCHAR(32),
    state_province                           VARCHAR(32),
    city                                     VARCHAR(32),
    business_unit                            VARCHAR(16),
    currency_code                            VARCHAR(16),
    payment_terms_code                       VARCHAR(16),
    billing_rule                             VARCHAR(32),
    credit_rating                            VARCHAR(16),
    customer_since_date                      DATE,
    is_active                                NUMBER(10,0),
    global_account_id                        NUMBER(10,0),
    global_account_name                      VARCHAR(32),
    credit_limit_usd                         DECIMAL(18,2),
    credit_status                            VARCHAR(16),
    last_credit_review_date                  DATE,
    customer_path                            VARCHAR(112),
    customer_level_1                         VARCHAR(32),
    customer_level_2                         VARCHAR(16),
    customer_level_3                         VARCHAR(32),
    customer_level_4                         VARCHAR(32),
    customer_level_5                         VARCHAR(48),
    duplicate_of_customer_id                 NUMBER(10,0)
,
    CONSTRAINT pk_dim_customer PRIMARY KEY (customer_id)
);
COMMENT ON TABLE dim_customer IS 'Vantage Industrial O2C - 5,000 rows at tier full';

CREATE OR REPLACE TABLE dim_customer_site (
    site_id                                  NUMBER(10,0) NOT NULL,
    customer_id                              NUMBER(10,0),
    site_code                                VARCHAR(16),
    site_name                                VARCHAR(80),
    site_type                                VARCHAR(32),
    address_line_1                           VARCHAR(32),
    city                                     VARCHAR(32),
    state_province                           VARCHAR(32),
    country                                  VARCHAR(32),
    region                                   VARCHAR(16),
    postal_code                              VARCHAR(16),
    is_ship_to                               NUMBER(10,0),
    is_bill_to                               NUMBER(10,0),
    is_primary_site                          NUMBER(10,0)
,
    CONSTRAINT pk_dim_customer_site PRIMARY KEY (site_id)
);
ALTER TABLE dim_customer_site ADD CONSTRAINT fk_dim_customer_site_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
COMMENT ON TABLE dim_customer_site IS 'Vantage Industrial O2C - 8,046 rows at tier full';

CREATE OR REPLACE TABLE dim_date (
    calendar_date                            DATE,
    date_key                                 NUMBER(10,0) NOT NULL,
    day_of_week                              NUMBER(10,0),
    day_name                                 VARCHAR(16),
    day_of_month                             NUMBER(10,0),
    day_of_year                              NUMBER(10,0),
    week_of_year                             NUMBER(10,0),
    month_number                             NUMBER(10,0),
    month_name                               VARCHAR(16),
    month_abbr                               VARCHAR(16),
    quarter_number                           NUMBER(10,0),
    quarter_name                             VARCHAR(16),
    calendar_year                            NUMBER(10,0),
    year_month_key                           NUMBER(10,0),
    year_month_name                          VARCHAR(16),
    year_quarter_name                        VARCHAR(16),
    month_start_date                         DATE,
    month_end_date                           DATE,
    is_month_end                             NUMBER(10,0),
    is_quarter_end                           NUMBER(10,0),
    is_weekend                               NUMBER(10,0),
    fiscal_year                              NUMBER(10,0),
    fiscal_month_number                      NUMBER(10,0),
    fiscal_quarter_number                    NUMBER(10,0),
    fiscal_quarter_name                      VARCHAR(16),
    fiscal_period_key                        NUMBER(10,0),
    is_holiday                               NUMBER(10,0),
    holiday_name                             VARCHAR(32),
    is_business_day                          NUMBER(10,0),
    business_day_index                       NUMBER(10,0),
    days_from_as_of                          NUMBER(10,0),
    months_from_as_of                        NUMBER(10,0),
    is_current_year                          NUMBER(10,0),
    is_prior_year                            NUMBER(10,0),
    is_last_12_months                        NUMBER(10,0),
    is_prior_12_months                       NUMBER(10,0),
    is_ytd                                   NUMBER(10,0)
,
    CONSTRAINT pk_dim_date PRIMARY KEY (date_key)
);
COMMENT ON TABLE dim_date IS 'Vantage Industrial O2C - 1,308 rows at tier full';

CREATE OR REPLACE TABLE dim_exchange_rate (
    exchange_rate_id                         NUMBER(10,0) NOT NULL,
    currency_code                            VARCHAR(16),
    month_start_date                         DATE,
    year_month_key                           NUMBER(10,0),
    rate_per_usd                             DECIMAL(18,2),
    usd_per_unit                             DECIMAL(18,4),
    rate_type                                VARCHAR(16)
,
    CONSTRAINT pk_dim_exchange_rate PRIMARY KEY (exchange_rate_id)
);
COMMENT ON TABLE dim_exchange_rate IS 'Vantage Industrial O2C - 344 rows at tier full';

CREATE OR REPLACE TABLE dim_payment_terms (
    payment_terms_id                         NUMBER(10,0) NOT NULL,
    payment_terms_code                       VARCHAR(16),
    payment_terms_name                       VARCHAR(32),
    due_days                                 NUMBER(10,0),
    discount_pct                             DECIMAL(12,6),
    discount_days                            NUMBER(10,0),
    is_early_discount                        NUMBER(10,0),
    terms_group                              VARCHAR(16)
,
    CONSTRAINT pk_dim_payment_terms PRIMARY KEY (payment_terms_id)
);
COMMENT ON TABLE dim_payment_terms IS 'Vantage Industrial O2C - 12 rows at tier full';

CREATE OR REPLACE TABLE dim_product (
    product_id                               NUMBER(10,0) NOT NULL,
    sku                                      VARCHAR(16),
    product_name                             VARCHAR(48),
    product_category                         VARCHAR(32),
    product_family                           VARCHAR(32),
    product_line                             VARCHAR(48),
    unit_of_measure                          VARCHAR(16),
    list_price_usd                           DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    standard_margin_pct                      DECIMAL(12,6),
    abc_class                                VARCHAR(16),
    is_made_to_order                         NUMBER(10,0),
    lead_time_days                           NUMBER(10,0),
    weight_kg                                DECIMAL(18,4),
    is_hazmat                                NUMBER(10,0),
    lifecycle_status                         VARCHAR(16),
    launch_date                              DATE,
    product_path                             VARCHAR(96),
    product_level_1                          VARCHAR(32),
    product_level_2                          VARCHAR(32),
    product_level_3                          VARCHAR(48),
    product_level_4                          VARCHAR(16)
,
    CONSTRAINT pk_dim_product PRIMARY KEY (product_id)
);
COMMENT ON TABLE dim_product IS 'Vantage Industrial O2C - 2,000 rows at tier full';

CREATE OR REPLACE TABLE dim_sales_rep (
    sales_rep_id                             NUMBER(10,0) NOT NULL,
    sales_rep_number                         VARCHAR(16),
    sales_rep_name                           VARCHAR(32),
    email                                    VARCHAR(48),
    region                                   VARCHAR(16),
    territory                                VARCHAR(16),
    sales_team                               VARCHAR(16),
    manager_name                             VARCHAR(32),
    hire_date                                DATE,
    annual_quota_usd                         NUMBER(10,0),
    is_active                                NUMBER(10,0)
,
    CONSTRAINT pk_dim_sales_rep PRIMARY KEY (sales_rep_id)
);
COMMENT ON TABLE dim_sales_rep IS 'Vantage Industrial O2C - 250 rows at tier full';

CREATE OR REPLACE TABLE dim_warehouse (
    warehouse_id                             NUMBER(10,0) NOT NULL,
    warehouse_code                           VARCHAR(16),
    warehouse_name                           VARCHAR(32),
    warehouse_type                           VARCHAR(16),
    city                                     VARCHAR(16),
    region                                   VARCHAR(16),
    country                                  VARCHAR(16),
    daily_line_capacity                      NUMBER(10,0),
    storage_sqft                             NUMBER(10,0),
    opened_date                              DATE,
    is_active                                NUMBER(10,0)
,
    CONSTRAINT pk_dim_warehouse PRIMARY KEY (warehouse_id)
);
COMMENT ON TABLE dim_warehouse IS 'Vantage Industrial O2C - 30 rows at tier full';

CREATE OR REPLACE TABLE fact_ar_aging_snapshot (
    ar_aging_id                              NUMBER(10,0) NOT NULL,
    invoice_id                               NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    snapshot_date                            DATE,
    year_month_key                           NUMBER(10,0),
    open_amount_usd                          DECIMAL(18,2),
    days_past_due                            NUMBER(10,0),
    aging_bucket                             VARCHAR(16),
    business_unit                            VARCHAR(16),
    region                                   VARCHAR(16),
    customer_segment                         VARCHAR(16),
    payment_terms_code                       VARCHAR(16),
    is_overdue                               NUMBER(10,0)
,
    CONSTRAINT pk_fact_ar_aging_snapshot PRIMARY KEY (ar_aging_id)
);
ALTER TABLE fact_ar_aging_snapshot ADD CONSTRAINT fk_fact_ar_aging_snapshot_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_ar_aging_snapshot ADD CONSTRAINT fk_fact_ar_aging_snapshot_invoice_id FOREIGN KEY (invoice_id) REFERENCES fact_invoice(invoice_id);
COMMENT ON TABLE fact_ar_aging_snapshot IS 'Vantage Industrial O2C - 151,179 rows at tier full';

CREATE OR REPLACE TABLE fact_credit_exposure_snapshot (
    credit_exposure_id                       NUMBER(10,0) NOT NULL,
    customer_id                              NUMBER(10,0),
    snapshot_date                            DATE,
    year_month_key                           NUMBER(10,0),
    credit_limit_usd                         DECIMAL(18,2),
    open_ar_usd                              DECIMAL(18,2),
    open_order_backlog_usd                   DECIMAL(18,2),
    current_exposure_usd                     DECIMAL(18,2),
    available_credit_usd                     DECIMAL(18,2),
    value_on_credit_hold_usd                 DECIMAL(18,2),
    credit_utilization_pct                   DECIMAL(12,6),
    is_over_limit                            NUMBER(10,0),
    credit_rating                            VARCHAR(16),
    customer_segment                         VARCHAR(16)
,
    CONSTRAINT pk_fact_credit_exposure_snapshot PRIMARY KEY (credit_exposure_id)
);
ALTER TABLE fact_credit_exposure_snapshot ADD CONSTRAINT fk_fact_credit_exposure_snapshot_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
COMMENT ON TABLE fact_credit_exposure_snapshot IS 'Vantage Industrial O2C - 94,290 rows at tier full';

CREATE OR REPLACE TABLE fact_credit_memo (
    credit_memo_id                           NUMBER(10,0) NOT NULL,
    credit_memo_number                       VARCHAR(16),
    invoice_id                               NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    memo_date                                DATE,
    memo_amount_usd                          DECIMAL(18,2),
    memo_reason                              VARCHAR(16),
    dispute_id                               NUMBER(10,0)
,
    CONSTRAINT pk_fact_credit_memo PRIMARY KEY (credit_memo_id)
);
ALTER TABLE fact_credit_memo ADD CONSTRAINT fk_fact_credit_memo_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_credit_memo ADD CONSTRAINT fk_fact_credit_memo_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
ALTER TABLE fact_credit_memo ADD CONSTRAINT fk_fact_credit_memo_invoice_id FOREIGN KEY (invoice_id) REFERENCES fact_invoice(invoice_id);
COMMENT ON TABLE fact_credit_memo IS 'Vantage Industrial O2C - 9,800 rows at tier full';

CREATE OR REPLACE TABLE fact_delivery_event (
    delivery_event_id                        NUMBER(10,0) NOT NULL,
    shipment_id                              NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    event_sequence                           NUMBER(10,0),
    event_date                               DATE,
    event_type                               VARCHAR(32),
    location_city                            VARCHAR(16),
    carrier_name                             VARCHAR(32),
    exception_code                           VARCHAR(16),
    is_exception                             NUMBER(10,0)
,
    CONSTRAINT pk_fact_delivery_event PRIMARY KEY (delivery_event_id)
);
ALTER TABLE fact_delivery_event ADD CONSTRAINT fk_fact_delivery_event_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
ALTER TABLE fact_delivery_event ADD CONSTRAINT fk_fact_delivery_event_shipment_id FOREIGN KEY (shipment_id) REFERENCES fact_shipment(shipment_id);
COMMENT ON TABLE fact_delivery_event IS 'Vantage Industrial O2C - 541,720 rows at tier full';

CREATE OR REPLACE TABLE fact_dispute (
    dispute_id                               NUMBER(10,0) NOT NULL,
    invoice_id                               NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    dispute_date                             DATE,
    dispute_reason                           VARCHAR(32),
    dispute_amount_usd                       DECIMAL(18,2),
    invoice_amount_usd                       DECIMAL(18,2),
    resolved_date                            DATE,
    resolution_code                          VARCHAR(32),
    dispute_owner                            VARCHAR(32),
    business_unit                            VARCHAR(16),
    customer_segment                         VARCHAR(16),
    is_open                                  NUMBER(10,0),
    days_open                                NUMBER(10,0)
,
    CONSTRAINT pk_fact_dispute PRIMARY KEY (dispute_id)
);
ALTER TABLE fact_dispute ADD CONSTRAINT fk_fact_dispute_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_dispute ADD CONSTRAINT fk_fact_dispute_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
ALTER TABLE fact_dispute ADD CONSTRAINT fk_fact_dispute_invoice_id FOREIGN KEY (invoice_id) REFERENCES fact_invoice(invoice_id);
COMMENT ON TABLE fact_dispute IS 'Vantage Industrial O2C - 5,949 rows at tier full';

CREATE OR REPLACE TABLE fact_fulfillment (
    fulfillment_id                           NUMBER(10,0) NOT NULL,
    fulfillment_number                       VARCHAR(16),
    order_id                                 NUMBER(10,0),
    warehouse_id                             NUMBER(10,0),
    fulfillment_created_date                 DATE,
    planned_ship_date                        DATE,
    actual_ship_date                         DATE,
    planned_quantity                         NUMBER(10,0),
    fulfilled_quantity                       NUMBER(10,0),
    backordered_quantity                     NUMBER(10,0),
    cancelled_quantity                       NUMBER(10,0),
    line_count                               NUMBER(10,0),
    allocated_value_usd                      DECIMAL(18,2),
    ship_delay_days                          NUMBER(10,0),
    fulfillment_status                       VARCHAR(32),
    fill_rate                                DECIMAL(12,6),
    is_backordered                           NUMBER(10,0)
,
    CONSTRAINT pk_fact_fulfillment PRIMARY KEY (fulfillment_id)
);
ALTER TABLE fact_fulfillment ADD CONSTRAINT fk_fact_fulfillment_warehouse_id FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse(warehouse_id);
ALTER TABLE fact_fulfillment ADD CONSTRAINT fk_fact_fulfillment_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
COMMENT ON TABLE fact_fulfillment IS 'Vantage Industrial O2C - 79,198 rows at tier full';

CREATE OR REPLACE TABLE fact_inventory_position (
    inventory_position_id                    NUMBER(10,0) NOT NULL,
    product_id                               NUMBER(10,0),
    warehouse_id                             NUMBER(10,0),
    month_start_date                         DATE,
    year_month_key                           NUMBER(10,0),
    demand_qty                               NUMBER(10,0),
    supply_qty                               NUMBER(10,0),
    allocated_qty                            NUMBER(10,0),
    closing_qty                              NUMBER(10,0),
    available_to_promise_qty                 NUMBER(10,0),
    shortfall_qty                            NUMBER(10,0),
    unit_cost_usd                            DECIMAL(18,2),
    inventory_value_usd                      DECIMAL(18,2),
    is_stockout                              NUMBER(10,0),
    fill_rate                                DECIMAL(12,6)
,
    CONSTRAINT pk_fact_inventory_position PRIMARY KEY (inventory_position_id)
);
ALTER TABLE fact_inventory_position ADD CONSTRAINT fk_fact_inventory_position_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
ALTER TABLE fact_inventory_position ADD CONSTRAINT fk_fact_inventory_position_warehouse_id FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse(warehouse_id);
COMMENT ON TABLE fact_inventory_position IS 'Vantage Industrial O2C - 282,558 rows at tier full';

CREATE OR REPLACE TABLE fact_invoice (
    invoice_id                               NUMBER(10,0) NOT NULL,
    invoice_number                           VARCHAR(16),
    customer_id                              NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    bill_to_site_id                          NUMBER(10,0),
    sales_rep_id                             NUMBER(10,0),
    invoice_date                             DATE,
    due_date                                 DATE,
    first_delivery_date                      DATE,
    payment_terms_code                       VARCHAR(16),
    billing_rule                             VARCHAR(32),
    business_unit                            VARCHAR(16),
    region                                   VARCHAR(16),
    customer_segment                         VARCHAR(16),
    currency_code                            VARCHAR(16),
    po_number                                VARCHAR(16),
    line_count                               NUMBER(10,0),
    order_count                              NUMBER(10,0),
    net_amount_usd                           DECIMAL(18,2),
    tax_amount_usd                           DECIMAL(18,2),
    freight_amount_usd                       DECIMAL(18,2),
    total_amount_usd                         DECIMAL(18,2),
    is_duplicate                             NUMBER(10,0),
    duplicate_of_invoice_id                  NUMBER(10,0),
    days_delivery_to_invoice                 NUMBER(10,0),
    days_order_to_invoice                    NUMBER(10,0),
    is_written_off                           NUMBER(10,0),
    early_discount_taken_usd                 DECIMAL(18,2),
    paid_amount_usd                          DECIMAL(18,2),
    credited_amount_usd                      DECIMAL(18,2),
    open_amount_usd                          DECIMAL(18,2),
    fully_paid_date                          DATE,
    days_overdue                             NUMBER(10,0),
    days_to_pay_actual                       NUMBER(10,0),
    is_open                                  NUMBER(10,0),
    is_overdue                               NUMBER(10,0),
    aging_bucket                             VARCHAR(16),
    invoice_status                           VARCHAR(16),
    disputed_amount_usd                      DECIMAL(18,2),
    is_disputed                              NUMBER(10,0),
    exchange_rate                            DECIMAL(12,6),
    net_amount_local                         DECIMAL(18,2),
    total_amount_local                       DECIMAL(18,2)
,
    CONSTRAINT pk_fact_invoice PRIMARY KEY (invoice_id)
);
ALTER TABLE fact_invoice ADD CONSTRAINT fk_fact_invoice_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_invoice ADD CONSTRAINT fk_fact_invoice_sales_rep_id FOREIGN KEY (sales_rep_id) REFERENCES dim_sales_rep(sales_rep_id);
ALTER TABLE fact_invoice ADD CONSTRAINT fk_fact_invoice_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
COMMENT ON TABLE fact_invoice IS 'Vantage Industrial O2C - 82,236 rows at tier full';

CREATE OR REPLACE TABLE fact_invoice_line (
    invoice_line_id                          NUMBER(10,0) NOT NULL,
    invoice_id                               NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    order_line_id                            NUMBER(10,0),
    shipment_line_id                         NUMBER(10,0),
    shipment_id                              NUMBER(10,0),
    product_id                               NUMBER(10,0),
    quantity_invoiced                        NUMBER(10,0),
    unit_price_usd                           DECIMAL(18,2),
    order_unit_price_usd                     DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    extended_cost_usd                        DECIMAL(18,2),
    price_variance_usd                       DECIMAL(18,2),
    contract_variance_usd                    DECIMAL(18,2),
    underbilled_amount_usd                   DECIMAL(18,2),
    has_price_variance                       NUMBER(10,0),
    is_below_contract                        NUMBER(10,0),
    is_contract_line                         NUMBER(10,0)
,
    CONSTRAINT pk_fact_invoice_line PRIMARY KEY (invoice_line_id)
);
ALTER TABLE fact_invoice_line ADD CONSTRAINT fk_fact_invoice_line_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
ALTER TABLE fact_invoice_line ADD CONSTRAINT fk_fact_invoice_line_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
ALTER TABLE fact_invoice_line ADD CONSTRAINT fk_fact_invoice_line_order_line_id FOREIGN KEY (order_line_id) REFERENCES fact_order_line(order_line_id);
ALTER TABLE fact_invoice_line ADD CONSTRAINT fk_fact_invoice_line_shipment_id FOREIGN KEY (shipment_id) REFERENCES fact_shipment(shipment_id);
ALTER TABLE fact_invoice_line ADD CONSTRAINT fk_fact_invoice_line_shipment_line_id FOREIGN KEY (shipment_line_id) REFERENCES fact_shipment_line(shipment_line_id);
ALTER TABLE fact_invoice_line ADD CONSTRAINT fk_fact_invoice_line_invoice_id FOREIGN KEY (invoice_id) REFERENCES fact_invoice(invoice_id);
COMMENT ON TABLE fact_invoice_line IS 'Vantage Industrial O2C - 318,604 rows at tier full';

CREATE OR REPLACE TABLE fact_o2c_cycle (
    o2c_cycle_id                             NUMBER(10,0) NOT NULL,
    order_id                                 NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    sales_rep_id                             NUMBER(10,0),
    quote_id                                 NUMBER(10,0),
    region                                   VARCHAR(16),
    country                                  VARCHAR(32),
    business_unit                            VARCHAR(16),
    customer_segment                         VARCHAR(16),
    channel                                  VARCHAR(16),
    payment_terms_code                       VARCHAR(16),
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
    quote_to_order_days                      NUMBER(10,0),
    order_to_ship_days                       NUMBER(10,0),
    ship_to_delivery_days                    NUMBER(10,0),
    delivery_to_invoice_days                 NUMBER(10,0),
    invoice_to_cash_days                     NUMBER(10,0),
    order_to_cash_days                       NUMBER(10,0),
    cost_amount_usd                          DECIMAL(18,2),
    gross_margin_usd                         DECIMAL(18,2),
    is_cancelled                             NUMBER(10,0),
    is_credit_hold                           NUMBER(10,0),
    is_backordered                           NUMBER(10,0),
    is_late_delivery                         NUMBER(10,0),
    is_delivered_not_invoiced                NUMBER(10,0),
    is_fully_collected                       NUMBER(10,0),
    is_on_time                               NUMBER(10,0),
    is_complete                              NUMBER(10,0),
    is_billed_correctly                      NUMBER(10,0),
    is_undamaged                             NUMBER(10,0),
    is_perfect_order                         NUMBER(10,0)
,
    CONSTRAINT pk_fact_o2c_cycle PRIMARY KEY (o2c_cycle_id)
);
ALTER TABLE fact_o2c_cycle ADD CONSTRAINT fk_fact_o2c_cycle_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_o2c_cycle ADD CONSTRAINT fk_fact_o2c_cycle_sales_rep_id FOREIGN KEY (sales_rep_id) REFERENCES dim_sales_rep(sales_rep_id);
ALTER TABLE fact_o2c_cycle ADD CONSTRAINT fk_fact_o2c_cycle_quote_id FOREIGN KEY (quote_id) REFERENCES fact_quote(quote_id);
ALTER TABLE fact_o2c_cycle ADD CONSTRAINT fk_fact_o2c_cycle_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
COMMENT ON TABLE fact_o2c_cycle IS 'Vantage Industrial O2C - 74,698 rows at tier full';

CREATE OR REPLACE TABLE fact_o2c_exception (
    exception_id                             NUMBER(10,0) NOT NULL,
    exception_type                           VARCHAR(32),
    owner_function                           VARCHAR(32),
    customer_id                              NUMBER(10,0),
    reference_type                           VARCHAR(16),
    reference_id                             NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    exception_value_usd                      DECIMAL(18,2),
    since_date                               DATE,
    customer_name                            VARCHAR(64),
    age_days                                 NUMBER(10,0),
    age_bucket                               VARCHAR(16),
    severity                                 VARCHAR(16),
    severity_score                           DECIMAL(12,6),
    customer_segment                         VARCHAR(16)
,
    CONSTRAINT pk_fact_o2c_exception PRIMARY KEY (exception_id)
);
ALTER TABLE fact_o2c_exception ADD CONSTRAINT fk_fact_o2c_exception_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_o2c_exception ADD CONSTRAINT fk_fact_o2c_exception_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
COMMENT ON TABLE fact_o2c_exception IS 'Vantage Industrial O2C - 9,521 rows at tier full';

CREATE OR REPLACE TABLE fact_order (
    order_id                                 NUMBER(10,0) NOT NULL,
    order_number                             VARCHAR(16),
    quote_id                                 NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    site_id                                  NUMBER(10,0),
    bill_to_site_id                          NUMBER(10,0),
    sales_rep_id                             NUMBER(10,0),
    order_date                               DATE,
    requested_delivery_date                  DATE,
    promised_delivery_date                   DATE,
    planned_ship_date                        DATE,
    order_source                             VARCHAR(16),
    channel                                  VARCHAR(16),
    region                                   VARCHAR(16),
    country                                  VARCHAR(32),
    business_unit                            VARCHAR(16),
    customer_segment                         VARCHAR(16),
    currency_code                            VARCHAR(16),
    payment_terms_code                       VARCHAR(16),
    billing_rule                             VARCHAR(32),
    shipping_priority                        VARCHAR(16),
    po_number                                VARCHAR(16),
    line_count                               NUMBER(10,0),
    total_quantity                           NUMBER(10,0),
    order_amount_usd                         DECIMAL(18,2),
    discount_amount_usd                      DECIMAL(18,2),
    net_order_amount_usd                     DECIMAL(18,2),
    tax_amount_usd                           DECIMAL(18,2),
    freight_amount_usd                       DECIMAL(18,2),
    total_order_amount_usd                   DECIMAL(18,2),
    cost_amount_usd                          DECIMAL(18,2),
    gross_margin_usd                         DECIMAL(18,2),
    gross_margin_pct                         DECIMAL(12,6),
    credit_status                            VARCHAR(32),
    credit_hold_date                         DATE,
    credit_release_date                      DATE,
    credit_limit_at_order_usd                DECIMAL(18,2),
    credit_exposure_at_order_usd             DECIMAL(18,2),
    is_credit_hold                           NUMBER(10,0),
    cancelled_date                           DATE,
    cancel_reason                            VARCHAR(32),
    is_cancelled                             NUMBER(10,0),
    exchange_rate                            DECIMAL(12,6),
    net_order_amount_local                   DECIMAL(18,2),
    total_order_amount_local                 DECIMAL(18,2)
,
    CONSTRAINT pk_fact_order PRIMARY KEY (order_id)
);
ALTER TABLE fact_order ADD CONSTRAINT fk_fact_order_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_order ADD CONSTRAINT fk_fact_order_site_id FOREIGN KEY (site_id) REFERENCES dim_customer_site(site_id);
ALTER TABLE fact_order ADD CONSTRAINT fk_fact_order_sales_rep_id FOREIGN KEY (sales_rep_id) REFERENCES dim_sales_rep(sales_rep_id);
ALTER TABLE fact_order ADD CONSTRAINT fk_fact_order_quote_id FOREIGN KEY (quote_id) REFERENCES fact_quote(quote_id);
COMMENT ON TABLE fact_order IS 'Vantage Industrial O2C - 74,698 rows at tier full';

CREATE OR REPLACE TABLE fact_order_line (
    order_line_id                            NUMBER(10,0) NOT NULL,
    order_id                                 NUMBER(10,0),
    line_number                              NUMBER(10,0),
    product_id                               NUMBER(10,0),
    list_price_usd                           DECIMAL(18,2),
    unit_price_usd                           DECIMAL(18,2),
    discount_pct                             DECIMAL(12,6),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    extended_cost_usd                        DECIMAL(18,2),
    margin_usd                               DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    is_contract_price                        NUMBER(10,0),
    quote_line_id_src                        NUMBER(10,0),
    order_date                               DATE,
    promised_delivery_date                   DATE,
    requested_delivery_date                  DATE,
    customer_id                              NUMBER(10,0),
    is_cancelled                             NUMBER(10,0),
    credit_status                            VARCHAR(32),
    region                                   VARCHAR(16),
    business_unit                            VARCHAR(16),
    quantity_ordered                         NUMBER(10,0),
    warehouse_id                             NUMBER(10,0),
    quantity_allocated                       NUMBER(10,0),
    quantity_backordered                     NUMBER(10,0),
    quantity_cancelled                       NUMBER(10,0),
    backorder_expected_date                  DATE
,
    CONSTRAINT pk_fact_order_line PRIMARY KEY (order_line_id)
);
ALTER TABLE fact_order_line ADD CONSTRAINT fk_fact_order_line_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_order_line ADD CONSTRAINT fk_fact_order_line_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
ALTER TABLE fact_order_line ADD CONSTRAINT fk_fact_order_line_warehouse_id FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse(warehouse_id);
ALTER TABLE fact_order_line ADD CONSTRAINT fk_fact_order_line_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
COMMENT ON TABLE fact_order_line IS 'Vantage Industrial O2C - 316,295 rows at tier full';

CREATE OR REPLACE TABLE fact_payment (
    payment_id                               NUMBER(10,0) NOT NULL,
    payment_number                           VARCHAR(16),
    customer_id                              NUMBER(10,0),
    payment_date                             DATE,
    payment_amount_usd                       DECIMAL(18,2),
    currency_code                            VARCHAR(16),
    payment_method                           VARCHAR(16),
    bank_reference                           VARCHAR(16),
    payment_status                           VARCHAR(16),
    invoice_count                            NUMBER(10,0),
    is_unapplied                             NUMBER(10,0),
    exchange_rate                            DECIMAL(12,6),
    payment_amount_local                     DECIMAL(18,2)
,
    CONSTRAINT pk_fact_payment PRIMARY KEY (payment_id)
);
ALTER TABLE fact_payment ADD CONSTRAINT fk_fact_payment_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
COMMENT ON TABLE fact_payment IS 'Vantage Industrial O2C - 74,584 rows at tier full';

CREATE OR REPLACE TABLE fact_payment_allocation (
    payment_allocation_id                    NUMBER(10,0) NOT NULL,
    payment_id                               NUMBER(10,0),
    invoice_id                               NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    allocated_amount_usd                     DECIMAL(18,2),
    allocation_date                          DATE,
    allocation_sequence                      NUMBER(10,0)
,
    CONSTRAINT pk_fact_payment_allocation PRIMARY KEY (payment_allocation_id)
);
ALTER TABLE fact_payment_allocation ADD CONSTRAINT fk_fact_payment_allocation_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_payment_allocation ADD CONSTRAINT fk_fact_payment_allocation_invoice_id FOREIGN KEY (invoice_id) REFERENCES fact_invoice(invoice_id);
ALTER TABLE fact_payment_allocation ADD CONSTRAINT fk_fact_payment_allocation_payment_id FOREIGN KEY (payment_id) REFERENCES fact_payment(payment_id);
COMMENT ON TABLE fact_payment_allocation IS 'Vantage Industrial O2C - 93,126 rows at tier full';

CREATE OR REPLACE TABLE fact_quote (
    quote_id                                 NUMBER(10,0) NOT NULL,
    quote_number                             VARCHAR(16),
    customer_id                              NUMBER(10,0),
    site_id                                  NUMBER(10,0),
    sales_rep_id                             NUMBER(10,0),
    quote_date                               DATE,
    expiration_date                          DATE,
    currency_code                            VARCHAR(16),
    region                                   VARCHAR(16),
    country                                  VARCHAR(32),
    business_unit                            VARCHAR(16),
    customer_segment                         VARCHAR(16),
    channel                                  VARCHAR(16),
    line_count                               NUMBER(10,0),
    quote_amount_usd                         DECIMAL(18,2),
    discount_amount_usd                      DECIMAL(18,2),
    discount_pct                             DECIMAL(12,6),
    net_quote_amount_usd                     DECIMAL(18,2),
    estimated_cost_usd                       DECIMAL(18,2),
    expected_margin_usd                      DECIMAL(18,2),
    expected_margin_pct                      DECIMAL(12,6),
    win_probability                          DECIMAL(18,4),
    quote_status                             VARCHAR(16),
    lost_reason                              VARCHAR(32),
    is_won                                   NUMBER(10,0),
    is_open                                  NUMBER(10,0),
    converted_order_id                       NUMBER(10,0),
    days_to_convert                          NUMBER(10,0),
    exchange_rate                            DECIMAL(12,6),
    net_quote_amount_local                   DECIMAL(18,2),
    quote_amount_local                       DECIMAL(18,2)
,
    CONSTRAINT pk_fact_quote PRIMARY KEY (quote_id)
);
ALTER TABLE fact_quote ADD CONSTRAINT fk_fact_quote_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_quote ADD CONSTRAINT fk_fact_quote_site_id FOREIGN KEY (site_id) REFERENCES dim_customer_site(site_id);
ALTER TABLE fact_quote ADD CONSTRAINT fk_fact_quote_sales_rep_id FOREIGN KEY (sales_rep_id) REFERENCES dim_sales_rep(sales_rep_id);
COMMENT ON TABLE fact_quote IS 'Vantage Industrial O2C - 165,391 rows at tier full';

CREATE OR REPLACE TABLE fact_quote_line (
    quote_line_id                            NUMBER(10,0) NOT NULL,
    quote_id                                 NUMBER(10,0),
    line_number                              NUMBER(10,0),
    product_id                               NUMBER(10,0),
    quantity                                 NUMBER(10,0),
    list_price_usd                           DECIMAL(18,2),
    quoted_price_usd                         DECIMAL(18,2),
    discount_pct                             DECIMAL(12,6),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    estimated_cost_usd                       DECIMAL(18,2),
    estimated_margin_usd                     DECIMAL(18,2),
    contract_price_usd                       DECIMAL(18,2),
    is_contract_price                        NUMBER(10,0)
,
    CONSTRAINT pk_fact_quote_line PRIMARY KEY (quote_line_id)
);
ALTER TABLE fact_quote_line ADD CONSTRAINT fk_fact_quote_line_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
ALTER TABLE fact_quote_line ADD CONSTRAINT fk_fact_quote_line_quote_id FOREIGN KEY (quote_id) REFERENCES fact_quote(quote_id);
COMMENT ON TABLE fact_quote_line IS 'Vantage Industrial O2C - 694,837 rows at tier full';

CREATE OR REPLACE TABLE fact_return (
    return_id                                NUMBER(10,0) NOT NULL,
    rma_number                               VARCHAR(16),
    invoice_id                               NUMBER(10,0),
    invoice_line_id                          NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    product_id                               NUMBER(10,0),
    product_category                         VARCHAR(32),
    return_date                              DATE,
    quantity_returned                        NUMBER(10,0),
    return_value_usd                         DECIMAL(18,2),
    return_reason                            VARCHAR(32),
    disposition                              VARCHAR(32),
    is_credited                              NUMBER(10,0)
,
    CONSTRAINT pk_fact_return PRIMARY KEY (return_id)
);
ALTER TABLE fact_return ADD CONSTRAINT fk_fact_return_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_return ADD CONSTRAINT fk_fact_return_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
ALTER TABLE fact_return ADD CONSTRAINT fk_fact_return_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
ALTER TABLE fact_return ADD CONSTRAINT fk_fact_return_invoice_id FOREIGN KEY (invoice_id) REFERENCES fact_invoice(invoice_id);
COMMENT ON TABLE fact_return IS 'Vantage Industrial O2C - 6,813 rows at tier full';

CREATE OR REPLACE TABLE fact_shipment (
    shipment_id                              NUMBER(10,0) NOT NULL,
    shipment_number                          VARCHAR(16),
    order_id                                 NUMBER(10,0),
    customer_id                              NUMBER(10,0),
    site_id                                  NUMBER(10,0),
    warehouse_id                             NUMBER(10,0),
    carrier_id                               NUMBER(10,0),
    carrier_name                             VARCHAR(32),
    service_level                            VARCHAR(16),
    tracking_number                          VARCHAR(16),
    ship_date                                DATE,
    expected_delivery_date                   DATE,
    actual_delivery_date                     DATE,
    promised_delivery_date                   DATE,
    shipping_priority                        VARCHAR(16),
    region                                   VARCHAR(16),
    business_unit                            VARCHAR(16),
    line_count                               NUMBER(10,0),
    shipped_quantity                         NUMBER(10,0),
    planned_transit_days                     NUMBER(10,0),
    actual_transit_days                      NUMBER(10,0),
    delay_days                               NUMBER(10,0),
    freight_cost_usd                         DECIMAL(18,2),
    is_expedited                             NUMBER(10,0),
    is_backorder_shipment                    NUMBER(10,0),
    is_split_shipment                        NUMBER(10,0),
    shipment_status                          VARCHAR(16),
    is_delivered                             NUMBER(10,0),
    is_on_time_carrier                       NUMBER(10,0),
    is_on_time_promise                       NUMBER(10,0),
    is_lost                                  NUMBER(10,0)
,
    CONSTRAINT pk_fact_shipment PRIMARY KEY (shipment_id)
);
ALTER TABLE fact_shipment ADD CONSTRAINT fk_fact_shipment_customer_id FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id);
ALTER TABLE fact_shipment ADD CONSTRAINT fk_fact_shipment_site_id FOREIGN KEY (site_id) REFERENCES dim_customer_site(site_id);
ALTER TABLE fact_shipment ADD CONSTRAINT fk_fact_shipment_warehouse_id FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse(warehouse_id);
ALTER TABLE fact_shipment ADD CONSTRAINT fk_fact_shipment_carrier_id FOREIGN KEY (carrier_id) REFERENCES dim_carrier(carrier_id);
ALTER TABLE fact_shipment ADD CONSTRAINT fk_fact_shipment_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
COMMENT ON TABLE fact_shipment IS 'Vantage Industrial O2C - 98,697 rows at tier full';

CREATE OR REPLACE TABLE fact_shipment_line (
    shipment_line_id                         NUMBER(10,0) NOT NULL,
    shipment_id                              NUMBER(10,0),
    order_id                                 NUMBER(10,0),
    order_line_id                            NUMBER(10,0),
    product_id                               NUMBER(10,0),
    warehouse_id                             NUMBER(10,0),
    quantity_shipped                         NUMBER(10,0),
    unit_price_usd                           DECIMAL(18,2),
    extended_amount_usd                      DECIMAL(18,2),
    unit_cost_usd                            DECIMAL(18,2),
    agreed_price_usd                         DECIMAL(18,2),
    is_contract_price                        NUMBER(10,0),
    is_backorder_line                        NUMBER(10,0)
,
    CONSTRAINT pk_fact_shipment_line PRIMARY KEY (shipment_line_id)
);
ALTER TABLE fact_shipment_line ADD CONSTRAINT fk_fact_shipment_line_product_id FOREIGN KEY (product_id) REFERENCES dim_product(product_id);
ALTER TABLE fact_shipment_line ADD CONSTRAINT fk_fact_shipment_line_warehouse_id FOREIGN KEY (warehouse_id) REFERENCES dim_warehouse(warehouse_id);
ALTER TABLE fact_shipment_line ADD CONSTRAINT fk_fact_shipment_line_order_id FOREIGN KEY (order_id) REFERENCES fact_order(order_id);
ALTER TABLE fact_shipment_line ADD CONSTRAINT fk_fact_shipment_line_order_line_id FOREIGN KEY (order_line_id) REFERENCES fact_order_line(order_line_id);
ALTER TABLE fact_shipment_line ADD CONSTRAINT fk_fact_shipment_line_shipment_id FOREIGN KEY (shipment_id) REFERENCES fact_shipment(shipment_id);
COMMENT ON TABLE fact_shipment_line IS 'Vantage Industrial O2C - 325,900 rows at tier full';
