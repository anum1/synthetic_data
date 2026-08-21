-- Norvant Group Procure-to-Pay - Databricks DDL
-- Generated from data/full by src/emit_ddl.py. Do not edit.

CREATE DATABASE IF NOT EXISTS P2P;
USE P2P;

CREATE OR REPLACE TABLE contract (
    contract_id INT,
    contract_number STRING,
    supplier_id INT,
    family_name STRING,
    contract_type STRING,
    contract_start_date DATE,
    contract_end_date DATE,
    payment_terms_code STRING,
    owner_employee_id INT,
    auto_renew_flag TINYINT,
    company_code STRING,
    currency_code STRING,
    committed_value_usd DECIMAL(18,4),
    is_expired TINYINT,
    days_to_expiry INT,
    contract_status STRING
);

CREATE OR REPLACE TABLE contract_price (
    contract_id INT,
    supplier_id INT,
    item_id INT,
    category_id INT,
    contract_unit_price_usd DECIMAL(18,4),
    list_price_usd DECIMAL(18,4),
    discount_off_list DECIMAL(18,4),
    minimum_quantity BIGINT,
    valid_from_date DATE,
    valid_to_date DATE,
    currency_code STRING,
    contract_price_id INT
);

CREATE OR REPLACE TABLE dim_approval_policy (
    approval_policy_id INT,
    company_code STRING,
    role_name STRING,
    approval_limit_usd DECIMAL(18,4),
    effective_from_date DATE,
    effective_to_date DATE,
    policy_version BIGINT,
    is_current BIGINT
);

CREATE OR REPLACE TABLE dim_category (
    category_id INT,
    category_code STRING,
    segment_name STRING,
    family_name STRING,
    category_name STRING,
    subcategory_name STRING,
    is_direct_spend BIGINT,
    category_path STRING
);

CREATE OR REPLACE TABLE dim_company_code (
    company_code_id INT,
    company_code STRING,
    company_name STRING,
    country_code STRING,
    functional_currency STRING,
    is_primary BIGINT
);

CREATE OR REPLACE TABLE dim_cost_center (
    cost_center_id INT,
    cost_center_code STRING,
    cost_center_name STRING,
    department_id INT,
    company_code STRING,
    region_name STRING,
    is_active TINYINT
);

CREATE OR REPLACE TABLE dim_currency (
    currency_id INT,
    currency_code STRING,
    currency_name STRING,
    units_per_usd DECIMAL(18,4),
    is_base_currency BIGINT
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

CREATE OR REPLACE TABLE dim_department (
    department_id INT,
    department_code STRING,
    department_name STRING,
    region_name STRING,
    company_code STRING,
    function_name STRING
);

CREATE OR REPLACE TABLE dim_employee (
    employee_id INT,
    employee_code STRING,
    first_name STRING,
    last_name STRING,
    full_name STRING,
    email_address STRING,
    role_name STRING,
    department_id INT,
    cost_center_id INT,
    company_code STRING,
    region_name STRING,
    department_name STRING,
    function_name STRING,
    approval_limit_usd DECIMAL(18,4),
    is_buyer TINYINT,
    is_approver TINYINT,
    hire_date DATE,
    is_active TINYINT,
    manager_employee_id INT
);

CREATE OR REPLACE TABLE dim_exchange_rate (
    currency_code STRING,
    rate_date DATE,
    rate_to_usd DECIMAL(18,4),
    exchange_rate_id INT,
    units_per_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE dim_gl_account (
    gl_account_id INT,
    gl_account_code STRING,
    gl_account_name STRING,
    gl_block_name STRING,
    account_type STRING,
    is_capex BIGINT
);

CREATE OR REPLACE TABLE dim_hold_reason (
    hold_reason_id INT,
    hold_reason_code STRING,
    hold_reason_description STRING,
    owning_team STRING,
    blocks_payment BIGINT,
    hold_category STRING
);

CREATE OR REPLACE TABLE dim_item (
    item_id INT,
    item_code STRING,
    item_name STRING,
    category_id INT,
    segment_name STRING,
    family_name STRING,
    category_name STRING,
    is_direct_spend BIGINT,
    unit_of_measure STRING,
    list_price_usd DECIMAL(18,4),
    gl_account_id INT,
    is_service_item TINYINT,
    normalized_item_key STRING
);

CREATE OR REPLACE TABLE dim_match_tolerance (
    match_tolerance_id INT,
    scope_type STRING,
    segment_name STRING,
    price_tolerance_pct DECIMAL(18,4),
    price_tolerance_abs_usd DECIMAL(18,4),
    qty_tolerance_pct DECIMAL(18,4),
    qty_tolerance_abs_units DECIMAL(18,4),
    total_variance_cap_usd DECIMAL(18,4),
    effective_from_date DATE,
    is_current BIGINT
);

CREATE OR REPLACE TABLE dim_payment_terms (
    payment_terms_id INT,
    payment_terms_code STRING,
    payment_terms_name STRING,
    discount_percent DECIMAL(18,4),
    discount_days BIGINT,
    net_days BIGINT,
    is_discount_eligible BIGINT,
    implied_annual_rate DECIMAL(18,4)
);

CREATE OR REPLACE TABLE dim_supplier (
    supplier_id INT,
    supplier_code STRING,
    supplier_name STRING,
    country_code STRING,
    currency_code STRING,
    is_duplicate_variant BIGINT,
    duplicate_of_supplier_id INT,
    variant_style STRING,
    normalized_supplier_name STRING,
    supplier_parent_id INT,
    tax_id STRING,
    has_tax_id TINYINT,
    duns_number STRING,
    onboarded_date DATE,
    risk_score DECIMAL(18,4),
    risk_tier STRING,
    is_diverse_supplier TINYINT,
    diversity_classification STRING,
    supplier_status STRING,
    primary_contact_name STRING,
    is_preferred_supplier TINYINT,
    conflict_flag BIGINT
);

CREATE OR REPLACE TABLE dim_supplier_bank_account (
    bank_account_id INT,
    supplier_id INT,
    bank_name STRING,
    bank_country_code STRING,
    account_number_masked STRING,
    account_number_hash STRING,
    iban_prefix STRING,
    is_primary_account BIGINT,
    is_active BIGINT,
    shared_flag_reason STRING
);

CREATE OR REPLACE TABLE dim_supplier_parent (
    supplier_parent_id INT,
    parent_code STRING,
    parent_name STRING,
    normalized_parent_name STRING,
    headquarters_country STRING
);

CREATE OR REPLACE TABLE dim_supplier_site (
    supplier_site_id INT,
    supplier_site_code STRING,
    supplier_id INT,
    site_purpose STRING,
    address_line STRING,
    city_name STRING,
    country_code STRING,
    site_tax_id STRING,
    is_primary_site BIGINT,
    is_pay_site BIGINT,
    is_active BIGINT
);

CREATE OR REPLACE TABLE dim_supplier_status_history (
    status_history_id INT,
    supplier_id INT,
    supplier_status STRING,
    effective_from_date DATE,
    effective_to_date DATE,
    is_current BIGINT,
    change_reason STRING
);

CREATE OR REPLACE TABLE fact_ap_aging_snapshot (
    snapshot_month_end DATE,
    invoice_id INT,
    supplier_id INT,
    company_code STRING,
    department_id INT,
    invoice_date DATE,
    due_date DATE,
    open_amount_usd DECIMAL(18,4),
    days_past_due INT,
    aging_bucket STRING,
    is_overdue TINYINT,
    has_open_hold TINYINT,
    ap_aging_id INT
);

CREATE OR REPLACE TABLE fact_approval_event (
    approval_event_id INT,
    document_type STRING,
    document_id BIGINT,
    document_number STRING,
    step_number TINYINT,
    approver_employee_id INT,
    approver_role STRING,
    queue_entered_date DATE,
    action_date DATE,
    action_taken STRING,
    days_in_queue INT,
    is_delegated TINYINT,
    delegated_from_employee_id INT,
    company_code STRING,
    department_id INT,
    document_amount_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_budget (
    cost_center_id INT,
    actual_spend_usd DECIMAL(18,4),
    department_id INT,
    company_code STRING,
    budget_amount_usd DECIMAL(18,4),
    variance_usd DECIMAL(18,4),
    variance_pct DECIMAL(18,4),
    is_over_budget TINYINT,
    fiscal_period_start DATE,
    fiscal_period_name STRING,
    fiscal_year SMALLINT,
    budget_id INT
);

CREATE OR REPLACE TABLE fact_goods_receipt (
    purchase_order_id INT,
    supplier_id INT,
    company_code STRING,
    receipt_date DATE,
    line_count BIGINT,
    goods_receipt_id INT,
    receipt_number STRING,
    received_by_employee_id INT,
    receipt_type STRING,
    total_received_amount_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_goods_receipt_line (
    goods_receipt_line_id INT,
    goods_receipt_id INT,
    purchase_order_id INT,
    purchase_order_line_id INT,
    item_id INT,
    category_id INT,
    supplier_id INT,
    receipt_date DATE,
    quantity_ordered DECIMAL(18,4),
    quantity_received DECIMAL(18,4),
    unit_price_usd DECIMAL(18,4),
    receipt_sequence TINYINT,
    received_amount_usd DECIMAL(18,4),
    is_partial_delivery TINYINT,
    quantity_rejected DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_invoice (
    purchase_order_id INT,
    supplier_id INT,
    invoice_date DATE,
    match_type STRING,
    department_id INT,
    cost_center_id INT,
    line_count BIGINT,
    gross_amount_usd DECIMAL(18,4),
    company_code STRING,
    is_non_po BIGINT,
    non_po_reason STRING,
    source_channel STRING,
    is_maverick_spend TINYINT,
    duplicate_archetype STRING,
    duplicate_of_inv_seq INT,
    invoice_type STRING,
    currency_code STRING,
    supplier_site_id INT,
    exchange_rate DECIMAL(18,4),
    gross_amount_local DECIMAL(18,4),
    payment_terms_code STRING,
    discount_percent DECIMAL(18,4),
    discount_days BIGINT,
    net_days BIGINT,
    invoice_received_date DATE,
    due_date DATE,
    discount_due_date DATE,
    tax_amount_usd DECIMAL(18,4),
    net_amount_usd DECIMAL(18,4),
    invoice_number STRING,
    is_duplicate_suspect TINYINT,
    invoice_id INT,
    days_to_approve DECIMAL(18,4),
    has_open_hold TINYINT,
    hold_count SMALLINT,
    approval_date DATE,
    approval_status STRING,
    is_straight_through TINYINT,
    payment_status STRING,
    amount_paid_usd DECIMAL(18,4),
    discount_taken_usd DECIMAL(18,4),
    open_amount_usd DECIMAL(18,4),
    is_open TINYINT,
    days_past_due INT,
    is_overdue TINYINT,
    discount_available_usd DECIMAL(18,4),
    discount_missed_usd DECIMAL(18,4),
    missed_due_to_approval TINYINT
);

CREATE OR REPLACE TABLE fact_invoice_distribution (
    invoice_distribution_id INT,
    invoice_id INT,
    invoice_line_id INT,
    gl_account_id INT,
    cost_center_id INT,
    department_id INT,
    amount_usd DECIMAL(18,4),
    distribution_percent DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_invoice_hold (
    invoice_id INT,
    hold_reason_code STRING,
    raised_date DATE,
    blocked_amount_usd DECIMAL(18,4),
    hold_reason_id INT,
    owning_team STRING,
    blocks_payment TINYINT,
    is_open TINYINT,
    days_held INT,
    resolution STRING,
    invoice_hold_id INT,
    released_date DATE
);

CREATE OR REPLACE TABLE fact_invoice_line (
    purchase_order_line_id INT,
    purchase_order_id INT,
    item_id INT,
    category_id INT,
    supplier_id INT,
    quantity_invoiced DECIMAL(18,4),
    unit_price_usd DECIMAL(18,4),
    line_amount_usd DECIMAL(18,4),
    po_unit_price_usd DECIMAL(18,4),
    po_line_amount_usd DECIMAL(18,4),
    quantity_ordered DECIMAL(18,4),
    quantity_received DECIMAL(18,4),
    match_type STRING,
    gl_account_id INT,
    segment_name STRING,
    department_id INT,
    cost_center_id INT,
    tax_code STRING,
    invoice_id INT,
    invoice_line_id INT,
    line_number SMALLINT
);

CREATE OR REPLACE TABLE fact_match_result (
    invoice_id INT,
    invoice_line_id INT,
    purchase_order_id INT,
    purchase_order_line_id INT,
    supplier_id INT,
    category_id INT,
    match_type STRING,
    match_tolerance_id INT,
    quantity_ordered DECIMAL(18,4),
    quantity_received DECIMAL(18,4),
    quantity_invoiced DECIMAL(18,4),
    po_unit_price_usd DECIMAL(18,4),
    invoice_unit_price_usd DECIMAL(18,4),
    price_variance_usd DECIMAL(18,4),
    price_variance_pct DECIMAL(18,4),
    quantity_variance DECIMAL(18,4),
    quantity_variance_pct DECIMAL(18,4),
    amount_variance_usd DECIMAL(18,4),
    is_price_within_tolerance TINYINT,
    is_quantity_within_tolerance TINYINT,
    is_amount_within_tolerance TINYINT,
    match_status STRING,
    exception_reason_code STRING,
    is_auto_write_off TINYINT,
    is_first_pass_match TINYINT,
    match_result_id INT
);

CREATE OR REPLACE TABLE fact_open_commitment_snapshot (
    snapshot_month_end DATE,
    supplier_id INT,
    open_commitment_usd DECIMAL(18,4),
    gr_ir_amount_usd DECIMAL(18,4),
    line_count BIGINT,
    open_commitment_id INT
);

CREATE OR REPLACE TABLE fact_p2p_cycle (
    invoice_id INT,
    invoice_number STRING,
    supplier_id INT,
    purchase_order_id INT,
    company_code STRING,
    department_id INT,
    match_type STRING,
    invoice_date DATE,
    invoice_received_date DATE,
    approval_date DATE,
    due_date DATE,
    gross_amount_usd DECIMAL(18,4),
    is_non_po BIGINT,
    po_date DATE,
    requisition_id INT,
    requisition_date DATE,
    requisition_approval_date DATE,
    receipt_date DATE,
    payment_date DATE,
    days_req_to_req_approved DECIMAL(18,4),
    days_req_approved_to_po DECIMAL(18,4),
    days_po_to_receipt DECIMAL(18,4),
    days_receipt_to_invoice DECIMAL(18,4),
    days_invoice_to_approved DECIMAL(18,4),
    days_approved_to_paid DECIMAL(18,4),
    days_req_to_cash DECIMAL(18,4),
    days_po_to_invoice DECIMAL(18,4),
    days_supplier DECIMAL(18,4),
    days_controllable DECIMAL(18,4),
    days_terms DECIMAL(18,4),
    p2p_cycle_id INT
);

CREATE OR REPLACE TABLE fact_p2p_exception (
    exception_type STRING,
    exception_stage STRING,
    entity_type STRING,
    entity_id INT,
    supplier_id INT,
    exception_value_usd DECIMAL(18,4),
    age_days BIGINT,
    owning_team STRING,
    age_bucket STRING,
    p2p_exception_id INT
);

CREATE OR REPLACE TABLE fact_payment (
    supplier_id INT,
    payment_date DATE,
    invoice_count BIGINT,
    payment_amount_usd DECIMAL(18,4),
    discount_taken_usd DECIMAL(18,4),
    payment_id INT,
    payment_number STRING,
    payment_method STRING,
    payment_run_id BIGINT,
    currency_code STRING,
    company_code STRING,
    bank_account_id INT,
    exchange_rate DECIMAL(18,4),
    payment_amount_local DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_payment_application (
    invoice_id INT,
    supplier_id INT,
    invoice_gross_usd DECIMAL(18,4),
    applied_amount_usd DECIMAL(18,4),
    discount_taken_usd DECIMAL(18,4),
    invoice_date DATE,
    due_date DATE,
    payment_date DATE,
    is_partial_settlement TINYINT,
    days_from_due INT,
    is_paid_late TINYINT,
    days_to_pay INT,
    payment_id INT,
    payment_application_id INT
);

CREATE OR REPLACE TABLE fact_pcard_transaction (
    pcard_transaction_id INT,
    transaction_reference STRING,
    transaction_date DATE,
    cardholder_employee_id INT,
    department_id INT,
    cost_center_id INT,
    company_code STRING,
    supplier_id INT,
    merchant_name STRING,
    merchant_category STRING,
    category_id INT,
    segment_name STRING,
    amount_usd DECIMAL(18,4),
    currency_code STRING,
    is_receipted TINYINT,
    is_policy_exception TINYINT,
    is_maverick_spend BIGINT
);

CREATE OR REPLACE TABLE fact_po_change (
    po_change_id INT,
    purchase_order_id INT,
    change_sequence BIGINT,
    change_date DATE,
    change_type STRING,
    field_changed STRING,
    old_value_usd DECIMAL(18,4),
    new_value_usd DECIMAL(18,4),
    changed_by_employee_id INT,
    change_reason STRING
);

CREATE OR REPLACE TABLE fact_purchase_order (
    supplier_id INT,
    company_code STRING,
    department_id INT,
    cost_center_id INT,
    requester_employee_id INT,
    po_date DATE,
    requisition_count BIGINT,
    line_count BIGINT,
    purchase_order_id INT,
    po_number STRING,
    buyer_employee_id INT,
    supplier_site_id INT,
    currency_code STRING,
    payment_terms_code STRING,
    total_amount_usd DECIMAL(18,4),
    split_group_key STRING,
    approval_threshold_usd DECIMAL(18,4),
    is_below_approval_threshold TINYINT,
    po_type STRING,
    is_cancelled TINYINT,
    cancelled_date DATE,
    po_status STRING,
    committed_amount_usd DECIMAL(18,4),
    needed_by_date DATE,
    is_contract_backed TINYINT,
    contract_id INT
);

CREATE OR REPLACE TABLE fact_purchase_order_line (
    requisition_line_id INT,
    requisition_id INT,
    item_id INT,
    category_id INT,
    suggested_supplier_id BIGINT,
    contract_id INT,
    quantity_ordered DECIMAL(18,4),
    unit_price_usd DECIMAL(18,4),
    unit_of_measure STRING,
    gl_account_id INT,
    segment_name STRING,
    is_service_line TINYINT,
    is_contract_price TINYINT,
    department_id INT,
    cost_center_id INT,
    contract_unit_price_usd DECIMAL(18,4),
    line_amount_usd DECIMAL(18,4),
    contract_price_variance_usd DECIMAL(18,4),
    off_contract_premium_usd DECIMAL(18,4),
    is_priced_above_contract TINYINT,
    is_off_contract_purchase TINYINT,
    has_contract_price TINYINT,
    purchase_order_id INT,
    po_line_number SMALLINT,
    purchase_order_line_id INT,
    po_date DATE,
    supplier_id INT,
    is_cancelled TINYINT,
    po_type STRING,
    company_code STRING,
    match_type STRING,
    expected_receipt_date DATE,
    quantity_received DECIMAL(18,4),
    is_received TINYINT,
    receipt_state STRING,
    days_late DECIMAL(18,4),
    is_on_time DECIMAL(18,4),
    is_over_receipt TINYINT,
    is_short_receipt TINYINT,
    open_commitment_usd DECIMAL(18,4),
    received_amount_usd DECIMAL(18,4),
    quantity_invoiced DECIMAL(18,4),
    invoiced_amount_usd DECIMAL(18,4),
    is_invoiced TINYINT,
    gr_ir_amount_usd DECIMAL(18,4)
);

CREATE OR REPLACE TABLE fact_requisition (
    requisition_id INT,
    requisition_number STRING,
    requisition_date DATE,
    requester_employee_id INT,
    department_id INT,
    cost_center_id INT,
    company_code STRING,
    total_amount_usd DECIMAL(18,4),
    line_count BIGINT,
    requisition_status STRING,
    approval_days DECIMAL(18,4),
    approval_date DATE,
    rejection_reason STRING,
    is_urgent TINYINT,
    needed_by_date DATE,
    currency_code STRING
);

CREATE OR REPLACE TABLE fact_requisition_line (
    requisition_line_id INT,
    requisition_id INT,
    line_number SMALLINT,
    item_id INT,
    category_id INT,
    suggested_supplier_id BIGINT,
    contract_id INT,
    quantity_requested DECIMAL(18,4),
    unit_price_usd DECIMAL(18,4),
    line_amount_usd DECIMAL(18,4),
    is_contract_price TINYINT,
    has_contract_available TINYINT,
    unit_of_measure STRING,
    gl_account_id INT,
    segment_name STRING,
    is_service_item TINYINT,
    requisition_date DATE
);

CREATE OR REPLACE TABLE fact_spend (
    spend_channel STRING,
    source_document STRING,
    source_id BIGINT,
    source_line_id BIGINT,
    purchase_order_id INT,
    supplier_id INT,
    category_id INT,
    item_id INT,
    department_id INT,
    cost_center_id INT,
    gl_account_id INT,
    segment_name STRING,
    spend_date DATE,
    company_code STRING,
    spend_amount_usd DECIMAL(18,4),
    match_type STRING,
    is_contract_available BIGINT,
    is_maverick_spend TINYINT,
    spend_class STRING,
    spend_id INT
);

CREATE OR REPLACE TABLE fact_supplier_risk_snapshot (
    supplier_id INT,
    snapshot_month DATE,
    risk_score DECIMAL(18,4),
    risk_tier STRING,
    supplier_risk_id INT
);
