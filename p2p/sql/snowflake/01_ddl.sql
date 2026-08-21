-- Norvant Group Procure-to-Pay - Snowflake DDL
-- Generated from data/full by src/emit_ddl.py. Do not edit.

CREATE SCHEMA IF NOT EXISTS P2P;
USE SCHEMA P2P;

CREATE OR REPLACE TABLE contract (
    contract_id INTEGER,
    contract_number VARCHAR,
    supplier_id INTEGER,
    family_name VARCHAR,
    contract_type VARCHAR,
    contract_start_date DATE,
    contract_end_date DATE,
    payment_terms_code VARCHAR,
    owner_employee_id INTEGER,
    auto_renew_flag SMALLINT,
    company_code VARCHAR,
    currency_code VARCHAR,
    committed_value_usd NUMBER(18,4),
    is_expired SMALLINT,
    days_to_expiry INTEGER,
    contract_status VARCHAR
);

CREATE OR REPLACE TABLE contract_price (
    contract_id INTEGER,
    supplier_id INTEGER,
    item_id INTEGER,
    category_id INTEGER,
    contract_unit_price_usd NUMBER(18,4),
    list_price_usd NUMBER(18,4),
    discount_off_list NUMBER(18,4),
    minimum_quantity BIGINT,
    valid_from_date DATE,
    valid_to_date DATE,
    currency_code VARCHAR,
    contract_price_id INTEGER
);

CREATE OR REPLACE TABLE dim_approval_policy (
    approval_policy_id INTEGER,
    company_code VARCHAR,
    role_name VARCHAR,
    approval_limit_usd NUMBER(18,4),
    effective_from_date DATE,
    effective_to_date DATE,
    policy_version BIGINT,
    is_current BIGINT
);

CREATE OR REPLACE TABLE dim_category (
    category_id INTEGER,
    category_code VARCHAR,
    segment_name VARCHAR,
    family_name VARCHAR,
    category_name VARCHAR,
    subcategory_name VARCHAR,
    is_direct_spend BIGINT,
    category_path VARCHAR
);

CREATE OR REPLACE TABLE dim_company_code (
    company_code_id INTEGER,
    company_code VARCHAR,
    company_name VARCHAR,
    country_code VARCHAR,
    functional_currency VARCHAR,
    is_primary BIGINT
);

CREATE OR REPLACE TABLE dim_cost_center (
    cost_center_id INTEGER,
    cost_center_code VARCHAR,
    cost_center_name VARCHAR,
    department_id INTEGER,
    company_code VARCHAR,
    region_name VARCHAR,
    is_active SMALLINT
);

CREATE OR REPLACE TABLE dim_currency (
    currency_id INTEGER,
    currency_code VARCHAR,
    currency_name VARCHAR,
    units_per_usd NUMBER(18,4),
    is_base_currency BIGINT
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

CREATE OR REPLACE TABLE dim_department (
    department_id INTEGER,
    department_code VARCHAR,
    department_name VARCHAR,
    region_name VARCHAR,
    company_code VARCHAR,
    function_name VARCHAR
);

CREATE OR REPLACE TABLE dim_employee (
    employee_id INTEGER,
    employee_code VARCHAR,
    first_name VARCHAR,
    last_name VARCHAR,
    full_name VARCHAR,
    email_address VARCHAR,
    role_name VARCHAR,
    department_id INTEGER,
    cost_center_id INTEGER,
    company_code VARCHAR,
    region_name VARCHAR,
    department_name VARCHAR,
    function_name VARCHAR,
    approval_limit_usd NUMBER(18,4),
    is_buyer SMALLINT,
    is_approver SMALLINT,
    hire_date DATE,
    is_active SMALLINT,
    manager_employee_id INTEGER
);

CREATE OR REPLACE TABLE dim_exchange_rate (
    currency_code VARCHAR,
    rate_date DATE,
    rate_to_usd NUMBER(18,4),
    exchange_rate_id INTEGER,
    units_per_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE dim_gl_account (
    gl_account_id INTEGER,
    gl_account_code VARCHAR,
    gl_account_name VARCHAR,
    gl_block_name VARCHAR,
    account_type VARCHAR,
    is_capex BIGINT
);

CREATE OR REPLACE TABLE dim_hold_reason (
    hold_reason_id INTEGER,
    hold_reason_code VARCHAR,
    hold_reason_description VARCHAR,
    owning_team VARCHAR,
    blocks_payment BIGINT,
    hold_category VARCHAR
);

CREATE OR REPLACE TABLE dim_item (
    item_id INTEGER,
    item_code VARCHAR,
    item_name VARCHAR,
    category_id INTEGER,
    segment_name VARCHAR,
    family_name VARCHAR,
    category_name VARCHAR,
    is_direct_spend BIGINT,
    unit_of_measure VARCHAR,
    list_price_usd NUMBER(18,4),
    gl_account_id INTEGER,
    is_service_item SMALLINT,
    normalized_item_key VARCHAR
);

CREATE OR REPLACE TABLE dim_match_tolerance (
    match_tolerance_id INTEGER,
    scope_type VARCHAR,
    segment_name VARCHAR,
    price_tolerance_pct NUMBER(18,4),
    price_tolerance_abs_usd NUMBER(18,4),
    qty_tolerance_pct NUMBER(18,4),
    qty_tolerance_abs_units NUMBER(18,4),
    total_variance_cap_usd NUMBER(18,4),
    effective_from_date DATE,
    is_current BIGINT
);

CREATE OR REPLACE TABLE dim_payment_terms (
    payment_terms_id INTEGER,
    payment_terms_code VARCHAR,
    payment_terms_name VARCHAR,
    discount_percent NUMBER(18,4),
    discount_days BIGINT,
    net_days BIGINT,
    is_discount_eligible BIGINT,
    implied_annual_rate NUMBER(18,4)
);

CREATE OR REPLACE TABLE dim_supplier (
    supplier_id INTEGER,
    supplier_code VARCHAR,
    supplier_name VARCHAR,
    country_code VARCHAR,
    currency_code VARCHAR,
    is_duplicate_variant BIGINT,
    duplicate_of_supplier_id INTEGER,
    variant_style VARCHAR,
    normalized_supplier_name VARCHAR,
    supplier_parent_id INTEGER,
    tax_id VARCHAR,
    has_tax_id SMALLINT,
    duns_number VARCHAR,
    onboarded_date DATE,
    risk_score NUMBER(18,4),
    risk_tier VARCHAR,
    is_diverse_supplier SMALLINT,
    diversity_classification VARCHAR,
    supplier_status VARCHAR,
    primary_contact_name VARCHAR,
    is_preferred_supplier SMALLINT,
    conflict_flag BIGINT
);

CREATE OR REPLACE TABLE dim_supplier_bank_account (
    bank_account_id INTEGER,
    supplier_id INTEGER,
    bank_name VARCHAR,
    bank_country_code VARCHAR,
    account_number_masked VARCHAR,
    account_number_hash VARCHAR,
    iban_prefix VARCHAR,
    is_primary_account BIGINT,
    is_active BIGINT,
    shared_flag_reason VARCHAR
);

CREATE OR REPLACE TABLE dim_supplier_parent (
    supplier_parent_id INTEGER,
    parent_code VARCHAR,
    parent_name VARCHAR,
    normalized_parent_name VARCHAR,
    headquarters_country VARCHAR
);

CREATE OR REPLACE TABLE dim_supplier_site (
    supplier_site_id INTEGER,
    supplier_site_code VARCHAR,
    supplier_id INTEGER,
    site_purpose VARCHAR,
    address_line VARCHAR,
    city_name VARCHAR,
    country_code VARCHAR,
    site_tax_id VARCHAR,
    is_primary_site BIGINT,
    is_pay_site BIGINT,
    is_active BIGINT
);

CREATE OR REPLACE TABLE dim_supplier_status_history (
    status_history_id INTEGER,
    supplier_id INTEGER,
    supplier_status VARCHAR,
    effective_from_date DATE,
    effective_to_date DATE,
    is_current BIGINT,
    change_reason VARCHAR
);

CREATE OR REPLACE TABLE fact_ap_aging_snapshot (
    snapshot_month_end DATE,
    invoice_id INTEGER,
    supplier_id INTEGER,
    company_code VARCHAR,
    department_id INTEGER,
    invoice_date DATE,
    due_date DATE,
    open_amount_usd NUMBER(18,4),
    days_past_due INTEGER,
    aging_bucket VARCHAR,
    is_overdue SMALLINT,
    has_open_hold SMALLINT,
    ap_aging_id INTEGER
);

CREATE OR REPLACE TABLE fact_approval_event (
    approval_event_id INTEGER,
    document_type VARCHAR,
    document_id BIGINT,
    document_number VARCHAR,
    step_number SMALLINT,
    approver_employee_id INTEGER,
    approver_role VARCHAR,
    queue_entered_date DATE,
    action_date DATE,
    action_taken VARCHAR,
    days_in_queue INTEGER,
    is_delegated SMALLINT,
    delegated_from_employee_id INTEGER,
    company_code VARCHAR,
    department_id INTEGER,
    document_amount_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_budget (
    cost_center_id INTEGER,
    actual_spend_usd NUMBER(18,4),
    department_id INTEGER,
    company_code VARCHAR,
    budget_amount_usd NUMBER(18,4),
    variance_usd NUMBER(18,4),
    variance_pct NUMBER(18,4),
    is_over_budget SMALLINT,
    fiscal_period_start DATE,
    fiscal_period_name VARCHAR,
    fiscal_year SMALLINT,
    budget_id INTEGER
);

CREATE OR REPLACE TABLE fact_goods_receipt (
    purchase_order_id INTEGER,
    supplier_id INTEGER,
    company_code VARCHAR,
    receipt_date DATE,
    line_count BIGINT,
    goods_receipt_id INTEGER,
    receipt_number VARCHAR,
    received_by_employee_id INTEGER,
    receipt_type VARCHAR,
    total_received_amount_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_goods_receipt_line (
    goods_receipt_line_id INTEGER,
    goods_receipt_id INTEGER,
    purchase_order_id INTEGER,
    purchase_order_line_id INTEGER,
    item_id INTEGER,
    category_id INTEGER,
    supplier_id INTEGER,
    receipt_date DATE,
    quantity_ordered NUMBER(18,4),
    quantity_received NUMBER(18,4),
    unit_price_usd NUMBER(18,4),
    receipt_sequence SMALLINT,
    received_amount_usd NUMBER(18,4),
    is_partial_delivery SMALLINT,
    quantity_rejected NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_invoice (
    purchase_order_id INTEGER,
    supplier_id INTEGER,
    invoice_date DATE,
    match_type VARCHAR,
    department_id INTEGER,
    cost_center_id INTEGER,
    line_count BIGINT,
    gross_amount_usd NUMBER(18,4),
    company_code VARCHAR,
    is_non_po BIGINT,
    non_po_reason VARCHAR,
    source_channel VARCHAR,
    is_maverick_spend SMALLINT,
    duplicate_archetype VARCHAR,
    duplicate_of_inv_seq INTEGER,
    invoice_type VARCHAR,
    currency_code VARCHAR,
    supplier_site_id INTEGER,
    exchange_rate NUMBER(18,4),
    gross_amount_local NUMBER(18,4),
    payment_terms_code VARCHAR,
    discount_percent NUMBER(18,4),
    discount_days BIGINT,
    net_days BIGINT,
    invoice_received_date DATE,
    due_date DATE,
    discount_due_date DATE,
    tax_amount_usd NUMBER(18,4),
    net_amount_usd NUMBER(18,4),
    invoice_number VARCHAR,
    is_duplicate_suspect SMALLINT,
    invoice_id INTEGER,
    days_to_approve NUMBER(18,4),
    has_open_hold SMALLINT,
    hold_count SMALLINT,
    approval_date DATE,
    approval_status VARCHAR,
    is_straight_through SMALLINT,
    payment_status VARCHAR,
    amount_paid_usd NUMBER(18,4),
    discount_taken_usd NUMBER(18,4),
    open_amount_usd NUMBER(18,4),
    is_open SMALLINT,
    days_past_due INTEGER,
    is_overdue SMALLINT,
    discount_available_usd NUMBER(18,4),
    discount_missed_usd NUMBER(18,4),
    missed_due_to_approval SMALLINT
);

CREATE OR REPLACE TABLE fact_invoice_distribution (
    invoice_distribution_id INTEGER,
    invoice_id INTEGER,
    invoice_line_id INTEGER,
    gl_account_id INTEGER,
    cost_center_id INTEGER,
    department_id INTEGER,
    amount_usd NUMBER(18,4),
    distribution_percent NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_invoice_hold (
    invoice_id INTEGER,
    hold_reason_code VARCHAR,
    raised_date DATE,
    blocked_amount_usd NUMBER(18,4),
    hold_reason_id INTEGER,
    owning_team VARCHAR,
    blocks_payment SMALLINT,
    is_open SMALLINT,
    days_held INTEGER,
    resolution VARCHAR,
    invoice_hold_id INTEGER,
    released_date DATE
);

CREATE OR REPLACE TABLE fact_invoice_line (
    purchase_order_line_id INTEGER,
    purchase_order_id INTEGER,
    item_id INTEGER,
    category_id INTEGER,
    supplier_id INTEGER,
    quantity_invoiced NUMBER(18,4),
    unit_price_usd NUMBER(18,4),
    line_amount_usd NUMBER(18,4),
    po_unit_price_usd NUMBER(18,4),
    po_line_amount_usd NUMBER(18,4),
    quantity_ordered NUMBER(18,4),
    quantity_received NUMBER(18,4),
    match_type VARCHAR,
    gl_account_id INTEGER,
    segment_name VARCHAR,
    department_id INTEGER,
    cost_center_id INTEGER,
    tax_code VARCHAR,
    invoice_id INTEGER,
    invoice_line_id INTEGER,
    line_number SMALLINT
);

CREATE OR REPLACE TABLE fact_match_result (
    invoice_id INTEGER,
    invoice_line_id INTEGER,
    purchase_order_id INTEGER,
    purchase_order_line_id INTEGER,
    supplier_id INTEGER,
    category_id INTEGER,
    match_type VARCHAR,
    match_tolerance_id INTEGER,
    quantity_ordered NUMBER(18,4),
    quantity_received NUMBER(18,4),
    quantity_invoiced NUMBER(18,4),
    po_unit_price_usd NUMBER(18,4),
    invoice_unit_price_usd NUMBER(18,4),
    price_variance_usd NUMBER(18,4),
    price_variance_pct NUMBER(18,4),
    quantity_variance NUMBER(18,4),
    quantity_variance_pct NUMBER(18,4),
    amount_variance_usd NUMBER(18,4),
    is_price_within_tolerance SMALLINT,
    is_quantity_within_tolerance SMALLINT,
    is_amount_within_tolerance SMALLINT,
    match_status VARCHAR,
    exception_reason_code VARCHAR,
    is_auto_write_off SMALLINT,
    is_first_pass_match SMALLINT,
    match_result_id INTEGER
);

CREATE OR REPLACE TABLE fact_open_commitment_snapshot (
    snapshot_month_end DATE,
    supplier_id INTEGER,
    open_commitment_usd NUMBER(18,4),
    gr_ir_amount_usd NUMBER(18,4),
    line_count BIGINT,
    open_commitment_id INTEGER
);

CREATE OR REPLACE TABLE fact_p2p_cycle (
    invoice_id INTEGER,
    invoice_number VARCHAR,
    supplier_id INTEGER,
    purchase_order_id INTEGER,
    company_code VARCHAR,
    department_id INTEGER,
    match_type VARCHAR,
    invoice_date DATE,
    invoice_received_date DATE,
    approval_date DATE,
    due_date DATE,
    gross_amount_usd NUMBER(18,4),
    is_non_po BIGINT,
    po_date DATE,
    requisition_id INTEGER,
    requisition_date DATE,
    requisition_approval_date DATE,
    receipt_date DATE,
    payment_date DATE,
    days_req_to_req_approved NUMBER(18,4),
    days_req_approved_to_po NUMBER(18,4),
    days_po_to_receipt NUMBER(18,4),
    days_receipt_to_invoice NUMBER(18,4),
    days_invoice_to_approved NUMBER(18,4),
    days_approved_to_paid NUMBER(18,4),
    days_req_to_cash NUMBER(18,4),
    days_po_to_invoice NUMBER(18,4),
    days_supplier NUMBER(18,4),
    days_controllable NUMBER(18,4),
    days_terms NUMBER(18,4),
    p2p_cycle_id INTEGER
);

CREATE OR REPLACE TABLE fact_p2p_exception (
    exception_type VARCHAR,
    exception_stage VARCHAR,
    entity_type VARCHAR,
    entity_id INTEGER,
    supplier_id INTEGER,
    exception_value_usd NUMBER(18,4),
    age_days BIGINT,
    owning_team VARCHAR,
    age_bucket VARCHAR,
    p2p_exception_id INTEGER
);

CREATE OR REPLACE TABLE fact_payment (
    supplier_id INTEGER,
    payment_date DATE,
    invoice_count BIGINT,
    payment_amount_usd NUMBER(18,4),
    discount_taken_usd NUMBER(18,4),
    payment_id INTEGER,
    payment_number VARCHAR,
    payment_method VARCHAR,
    payment_run_id BIGINT,
    currency_code VARCHAR,
    company_code VARCHAR,
    bank_account_id INTEGER,
    exchange_rate NUMBER(18,4),
    payment_amount_local NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_payment_application (
    invoice_id INTEGER,
    supplier_id INTEGER,
    invoice_gross_usd NUMBER(18,4),
    applied_amount_usd NUMBER(18,4),
    discount_taken_usd NUMBER(18,4),
    invoice_date DATE,
    due_date DATE,
    payment_date DATE,
    is_partial_settlement SMALLINT,
    days_from_due INTEGER,
    is_paid_late SMALLINT,
    days_to_pay INTEGER,
    payment_id INTEGER,
    payment_application_id INTEGER
);

CREATE OR REPLACE TABLE fact_pcard_transaction (
    pcard_transaction_id INTEGER,
    transaction_reference VARCHAR,
    transaction_date DATE,
    cardholder_employee_id INTEGER,
    department_id INTEGER,
    cost_center_id INTEGER,
    company_code VARCHAR,
    supplier_id INTEGER,
    merchant_name VARCHAR,
    merchant_category VARCHAR,
    category_id INTEGER,
    segment_name VARCHAR,
    amount_usd NUMBER(18,4),
    currency_code VARCHAR,
    is_receipted SMALLINT,
    is_policy_exception SMALLINT,
    is_maverick_spend BIGINT
);

CREATE OR REPLACE TABLE fact_po_change (
    po_change_id INTEGER,
    purchase_order_id INTEGER,
    change_sequence BIGINT,
    change_date DATE,
    change_type VARCHAR,
    field_changed VARCHAR,
    old_value_usd NUMBER(18,4),
    new_value_usd NUMBER(18,4),
    changed_by_employee_id INTEGER,
    change_reason VARCHAR
);

CREATE OR REPLACE TABLE fact_purchase_order (
    supplier_id INTEGER,
    company_code VARCHAR,
    department_id INTEGER,
    cost_center_id INTEGER,
    requester_employee_id INTEGER,
    po_date DATE,
    requisition_count BIGINT,
    line_count BIGINT,
    purchase_order_id INTEGER,
    po_number VARCHAR,
    buyer_employee_id INTEGER,
    supplier_site_id INTEGER,
    currency_code VARCHAR,
    payment_terms_code VARCHAR,
    total_amount_usd NUMBER(18,4),
    split_group_key VARCHAR,
    approval_threshold_usd NUMBER(18,4),
    is_below_approval_threshold SMALLINT,
    po_type VARCHAR,
    is_cancelled SMALLINT,
    cancelled_date DATE,
    po_status VARCHAR,
    committed_amount_usd NUMBER(18,4),
    needed_by_date DATE,
    is_contract_backed SMALLINT,
    contract_id INTEGER
);

CREATE OR REPLACE TABLE fact_purchase_order_line (
    requisition_line_id INTEGER,
    requisition_id INTEGER,
    item_id INTEGER,
    category_id INTEGER,
    suggested_supplier_id BIGINT,
    contract_id INTEGER,
    quantity_ordered NUMBER(18,4),
    unit_price_usd NUMBER(18,4),
    unit_of_measure VARCHAR,
    gl_account_id INTEGER,
    segment_name VARCHAR,
    is_service_line SMALLINT,
    is_contract_price SMALLINT,
    department_id INTEGER,
    cost_center_id INTEGER,
    contract_unit_price_usd NUMBER(18,4),
    line_amount_usd NUMBER(18,4),
    contract_price_variance_usd NUMBER(18,4),
    off_contract_premium_usd NUMBER(18,4),
    is_priced_above_contract SMALLINT,
    is_off_contract_purchase SMALLINT,
    has_contract_price SMALLINT,
    purchase_order_id INTEGER,
    po_line_number SMALLINT,
    purchase_order_line_id INTEGER,
    po_date DATE,
    supplier_id INTEGER,
    is_cancelled SMALLINT,
    po_type VARCHAR,
    company_code VARCHAR,
    match_type VARCHAR,
    expected_receipt_date DATE,
    quantity_received NUMBER(18,4),
    is_received SMALLINT,
    receipt_state VARCHAR,
    days_late NUMBER(18,4),
    is_on_time NUMBER(18,4),
    is_over_receipt SMALLINT,
    is_short_receipt SMALLINT,
    open_commitment_usd NUMBER(18,4),
    received_amount_usd NUMBER(18,4),
    quantity_invoiced NUMBER(18,4),
    invoiced_amount_usd NUMBER(18,4),
    is_invoiced SMALLINT,
    gr_ir_amount_usd NUMBER(18,4)
);

CREATE OR REPLACE TABLE fact_requisition (
    requisition_id INTEGER,
    requisition_number VARCHAR,
    requisition_date DATE,
    requester_employee_id INTEGER,
    department_id INTEGER,
    cost_center_id INTEGER,
    company_code VARCHAR,
    total_amount_usd NUMBER(18,4),
    line_count BIGINT,
    requisition_status VARCHAR,
    approval_days NUMBER(18,4),
    approval_date DATE,
    rejection_reason VARCHAR,
    is_urgent SMALLINT,
    needed_by_date DATE,
    currency_code VARCHAR
);

CREATE OR REPLACE TABLE fact_requisition_line (
    requisition_line_id INTEGER,
    requisition_id INTEGER,
    line_number SMALLINT,
    item_id INTEGER,
    category_id INTEGER,
    suggested_supplier_id BIGINT,
    contract_id INTEGER,
    quantity_requested NUMBER(18,4),
    unit_price_usd NUMBER(18,4),
    line_amount_usd NUMBER(18,4),
    is_contract_price SMALLINT,
    has_contract_available SMALLINT,
    unit_of_measure VARCHAR,
    gl_account_id INTEGER,
    segment_name VARCHAR,
    is_service_item SMALLINT,
    requisition_date DATE
);

CREATE OR REPLACE TABLE fact_spend (
    spend_channel VARCHAR,
    source_document VARCHAR,
    source_id BIGINT,
    source_line_id BIGINT,
    purchase_order_id INTEGER,
    supplier_id INTEGER,
    category_id INTEGER,
    item_id INTEGER,
    department_id INTEGER,
    cost_center_id INTEGER,
    gl_account_id INTEGER,
    segment_name VARCHAR,
    spend_date DATE,
    company_code VARCHAR,
    spend_amount_usd NUMBER(18,4),
    match_type VARCHAR,
    is_contract_available BIGINT,
    is_maverick_spend SMALLINT,
    spend_class VARCHAR,
    spend_id INTEGER
);

CREATE OR REPLACE TABLE fact_supplier_risk_snapshot (
    supplier_id INTEGER,
    snapshot_month DATE,
    risk_score NUMBER(18,4),
    risk_tier VARCHAR,
    supplier_risk_id INTEGER
);
