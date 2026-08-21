# Data model — 44 tables as shipped

Generated from `data/full`. Row counts are full tier; `small` is roughly a
quarter of each transactional table.

Naming follows the sibling projects: `dim_*` for master and policy data,
`fact_*` for transactions and snapshots, and two commercial tables that are
neither (`contract`, `contract_price`).

## Master and policy

| Table | Rows | Columns | Notes |
|---|---:|---:|---|
| `dim_date` | 1,308 | 37 |  |
| `dim_company_code` | 6 | 6 |  |
| `dim_department` | 96 | 6 |  |
| `dim_cost_center` | 520 | 7 |  |
| `dim_employee` | 5,000 | 19 |  |
| `dim_approval_policy` | 84 | 8 | Effective-dated DOA by role x entity. Two versions: the policy changed 19 months ago. |
| `dim_supplier` | 2,400 | 22 | Includes duplicate variant records pointing at the original via duplicate_of_supplier_id. |
| `dim_supplier_parent` | 1,818 | 5 |  |
| `dim_supplier_site` | 4,209 | 11 |  |
| `dim_supplier_bank_account` | 2,745 | 10 | account_number_hash is the shared-account join key. shared_flag_reason marks suspicious vs benign. |
| `dim_supplier_status_history` | 2,957 | 7 | Effective-dated status: answers 'was this supplier inactive on the PO date'. |
| `dim_category` | 333 | 8 |  |
| `dim_gl_account` | 210 | 6 |  |
| `dim_item` | 4,000 | 13 | normalized_item_key groups two item codes that are the same specification. |
| `dim_payment_terms` | 7 | 8 |  |
| `dim_currency` | 7 | 5 |  |
| `dim_exchange_rate` | 9,156 | 5 | Daily rate_to_usd per currency. Carries the FX red herring (E17). |
| `dim_match_tolerance` | 4 | 10 | The policy the match verdict is computed against. Segment overrides on top of one default. |
| `dim_hold_reason` | 22 | 6 |  |

## Commercial

| Table | Rows | Columns | Notes |
|---|---:|---:|---|
| `contract` | 3,200 | 16 |  |
| `contract_price` | 80,322 | 12 | The source of truth for what we SHOULD pay. Event 4 is the gap between this and the PO price. |
| `fact_budget` | 20,860 | 12 |  |

## Transactions

| Table | Rows | Columns | Notes |
|---|---:|---:|---|
| `fact_requisition` | 124,900 | 16 |  |
| `fact_requisition_line` | 300,025 | 17 |  |
| `fact_purchase_order` | 142,551 | 26 |  |
| `fact_purchase_order_line` | 244,792 | 45 | Carries received, invoiced, GR/IR and open-commitment amounts, so the waterfall is a SUM. |
| `fact_po_change` | 34,146 | 10 |  |
| `fact_goods_receipt` | 142,172 | 10 |  |
| `fact_goods_receipt_line` | 210,136 | 15 |  |
| `fact_invoice` | 183,984 | 48 |  |
| `fact_invoice_line` | 242,715 | 21 |  |
| `fact_invoice_distribution` | 276,450 | 8 |  |
| `fact_payment` | 131,680 | 14 |  |
| `fact_payment_application` | 172,801 | 14 | The invoice-to-payment bridge. Every AP metric depends on it. |
| `fact_pcard_transaction` | 254,898 | 17 |  |
| `fact_approval_event` | 183,585 | 16 |  |

## Derived and snapshots

| Table | Rows | Columns | Notes |
|---|---:|---:|---|
| `fact_match_result` | 201,619 | 26 | One row per PO-backed invoice LINE. Verdict computed, never drawn. |
| `fact_invoice_hold` | 31,006 | 12 | The exception ledger. One invoice can carry several holds, each with an owning team. |
| `fact_p2p_cycle` | 179,195 | 31 | One row per invoice carrying all six milestone dates and the ours/supplier/terms split. |
| `fact_spend` | 497,613 | 20 | Unified spend line across all three channels with contract and maverick classification carried down. |
| `fact_ap_aging_snapshot` | 192,733 | 13 |  |
| `fact_open_commitment_snapshot` | 68,001 | 6 |  |
| `fact_p2p_exception` | 32,165 | 10 | Unified exception centre across every stage, with a value and an owner. |
| `fact_supplier_risk_snapshot` | 103,200 | 5 |  |

## The chain

```text
Supplier ── Contract ── contract_price
   │
Requisition ─ requisition_line
   │
Purchase Order ─ purchase_order_line ─ po_change
   │
Goods Receipt ─ goods_receipt_line        (three-way lines only)
   │
Invoice ─ invoice_line ─ invoice_distribution
   │
Match Result ─ Invoice Hold
   │
Payment ─ payment_application
```

Every link is keyed, so a single transaction can be followed from a $282.2M
spend tile down to one payment application and back up again. `fact_p2p_cycle`
collapses one whole chain onto a single row for speed; the detail tables are
still there when someone asks to see it.
