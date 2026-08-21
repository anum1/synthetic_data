# Data model

31 tables. One customer/order spine, and every fact resolves back to it.

Conventions inherited from the sibling ApexTech, Meridian and GlobalTech
datasets: lowercase `snake_case`, no reserved words, `DECIMAL(18,2)` money,
`0/1` integer booleans, ISO dates (never timestamps), and **no NULL foreign
keys** — an order raised without a quote points at `quote_id = 0`, not at NULL.

Two tiers, same seed, same events, same story. Parquet always; CSV at small tier.

---

## The chain

The whole demo depends on being able to follow one transaction end to end:

```
Q-0104271  quote
    └── SO-0020418  order
            └── FO-0022137  fulfilment (order x warehouse)
                    └── SH-0027845  shipment
                            └── INV-0021109  invoice
                                    └── PAY-0019034  payment
```

```
dim_customer
    │
    ├── contract_pricing ─────────────┐
    │                                 │  (what the price SHOULD be)
    ├── fact_quote                    │
    │      └── fact_quote_line ───────┤
    │                                 │
    └── fact_order                    │
           ├── fact_order_line ───────┤
           │        │                 │
           │        └── fact_shipment_line ──> fact_shipment ──> fact_delivery_event
           │                    │
           ├── fact_fulfillment  │
           │                     │
           └── fact_invoice      │
                  └── fact_invoice_line  (carries BOTH order_line_id
                  │                       and shipment_line_id)
                  ├── fact_payment_allocation ──> fact_payment
                  ├── fact_credit_memo
                  ├── fact_dispute
                  └── fact_return
```

`fact_invoice_line` carrying both parents is deliberate. Line-level price
variance is an order-line question; "which consignment did this come from" is a
shipment-line question. Drop either key and the two best drill-downs in the demo
stop working.

---

## Tables

### Dimensions

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `dim_date` | day | 1,308 | 1,308 |
| `dim_customer` | customer, hierarchy flattened | 1,500 | 5,000 |
| `dim_customer_site` | ship-to / bill-to site | 2,399 | 8,046 |
| `dim_product` | SKU, hierarchy flattened | 600 | 2,000 |
| `dim_sales_rep` | sales rep | 80 | 250 |
| `dim_warehouse` | warehouse | 12 | 30 |
| `dim_carrier` | carrier × service level | 16 | 40 |
| `dim_payment_terms` | terms code | 12 | 12 |
| `dim_currency` | currency | 8 | 8 |
| `dim_exchange_rate` | currency × month | 344 | 344 |
| `contract_pricing` | customer × product × validity period | 29,795 | 176,098 |

### Commercial

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `fact_quote` | quote header | 41,347 | 165,391 |
| `fact_quote_line` | quote line | 174,425 | 694,837 |
| `fact_order` | sales order header | 18,901 | 74,698 |
| `fact_order_line` | order line | 80,421 | 316,295 |

### Fulfilment and logistics

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `fact_fulfillment` | order × warehouse allocation | 19,952 | 79,198 |
| `fact_inventory_position` | SKU × warehouse × month-end | 66,934 | 282,558 |
| `fact_shipment` | shipment header | 24,843 | 98,697 |
| `fact_shipment_line` | shipment line → order line | 82,836 | 325,900 |
| `fact_delivery_event` | carrier scan event | 136,155 | 541,720 |

### Finance

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `fact_invoice` | invoice header | 19,997 | 82,236 |
| `fact_invoice_line` | invoice line → order line + shipment line | 80,646 | 318,604 |
| `fact_payment` | customer remittance | 19,286 | 74,584 |
| `fact_payment_allocation` | payment → invoice | 22,667 | 93,126 |
| `fact_credit_memo` | credit memo | 2,480 | 9,800 |
| `fact_dispute` | invoice dispute | 1,483 | 5,949 |
| `fact_return` | RMA | 1,735 | 6,813 |
| `fact_ar_aging_snapshot` | open invoice × month-end | 35,874 | 151,179 |
| `fact_credit_exposure_snapshot` | customer × month-end | 25,526 | 94,290 |

### Derived — the two that make the demo fast

| Table | Grain | Small | Full |
|---|---|---:|---:|
| `fact_o2c_cycle` | order: every milestone date + the value at every stage | 18,901 | 74,698 |
| `fact_o2c_exception` | one open exception | 2,478 | 9,521 |

**Totals:** 912,961 rows / 35 MB at small; **3,693,230 rows / 129 MB** at full.

---

## Why the derived tables exist

`fact_o2c_cycle` is the waterfall and the process-time bridge, precomputed. One
row per order carrying `quote_date … fully_paid_date` and the value that reached
each stage. Without it, "how much of what we booked has become cash" is a
six-table join that four BI tools will each get slightly differently — and the
executive page is the one place that cannot afford a number that moves depending
on who built the chart. See [KPI_DEFINITIONS.md](KPI_DEFINITIONS.md) §1.

`fact_o2c_exception` is the exception centre: one row per open problem, typed,
valued, aged, and assigned to a function. It is a table rather than a query so
the headline count is identical everywhere it appears.

---

## Hierarchies are flattened, not recursive

A parent pointer alone will not give you "roll everything up to this global
account" as a single filter, and the Customer 360 scene depends on exactly that.

**Customer** — `customer_level_1..5` plus `customer_path`:

```
Global Account > Region > Country > State/Province > Customer > Site
```

**Product** — `product_level_1..4` plus `product_path`:

```
Category > Family > Line > SKU
```

---

## Two grains that catch people out

**`fact_fulfillment` is order × warehouse, not order.** A minority of orders are
sourced from a second warehouse; those produce two fulfilment rows and, usually,
two consignments. This is one of the two roots of a partial shipment — the other
is a backordered line shipping later.

**`dim_carrier` is carrier × service level.** "Which carriers have
deteriorated" is always followed by "on which service", and a carrier-only grain
cannot answer it.

---

## What is deliberately absent

**Daily inventory.** The design note asked for SKU × warehouse × day. At full
tier that grain is 2,000 × 30 × 1,095 = **65.7M rows**, not the 1–3M claimed —
and no O2C question needs it. Allocation needs available-to-promise at the moment
of the decision, which is what `fact_inventory_position` provides, monthly, and
only for pairs that actually transact. The daily-inventory demo already exists in
the sibling `supply_chain` and `inventory_stockout` datasets.

**Generator dials.** Columns like the per-customer spend weight and days-to-pay
multiplier steer the events. They are dropped before writing: publishing them
hands the audience the answer key, and an AI asked to find the slow-paying
customer would read the column rather than work it out.

---

## Regenerating the DDL

Never hand-edit `sql/snowflake/01_ddl.sql` or `sql/databricks/01_ddl.sql`. They
are derived from the actual parquet schemas:

```bash
python3 src/emit_ddl.py --tier full
```
