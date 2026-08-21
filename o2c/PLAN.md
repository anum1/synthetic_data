# Order-to-Cash Control Tower — review of the design note, and a build plan

> **Status: built.** This plan was executed. The dataset lives in this folder —
> see [README.md](README.md) for how to run it, [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
> for the 31 tables as actually shipped, [docs/EVENTS.md](docs/EVENTS.md) for the
> measured magnitude of each planted event, and
> [docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) for the measurement decisions
> in §2.1 as they were finally settled. Where the built dataset differs from this
> plan — 170K quotes rather than 200K, `receivables.py` rather than
> `collections.py`, and three event magnitudes that the arithmetic would not
> support — the docs are authoritative.

Review of [o2c_demo_data_dsign.txt](o2c_demo_data_dsign.txt), plus the plan to
generate it as a real dataset in the style of the sibling `sales` (ApexTech),
`supply_chain` (Meridian) and `hr_adv` (GlobalTech) projects.

---

## 1. Verdict

The narrative is the best of the four design notes so far. The waterfall (§15),
the exception centre (§20) and the process-time bridge (§18) are exactly the
right shape for an Incorta/NLQ demo, and the demo story in §22 is genuinely
better than a sales dashboard because it forces cross-functional joins that only
a real analytical platform can do quickly.

**Keep the story. The data design underneath it is not yet buildable.** Eight
things are missing or specified in a way that will fall apart in front of a
finance audience — and an O2C demo *has* a finance audience, which is a harder
room than the HR one. They are listed in §2 in the order they will hurt you.
§3 onward is the plan.

The single most important fix is §2.1: **the funnel and the KPI tiles measure
two different populations**, and as drawn the "$37M leakage" is mostly just
payment terms doing their job. That gets caught in the first Q&A.

---

## 2. What needs to change before writing any code

### 2.1 The funnel is a cohort; the KPI tiles are balances. Say so, or the demo dies.

The doc's headline —

```
Bookings $128.4M   Revenue $103.7M   Open AR $41.2M   Overdue AR $12.8M   DSO 47 days
```

— and the funnel beneath it —

```
Quotes $165M -> Orders $128M -> Shipped $117M -> Delivered $111M -> Invoiced $104M -> Collected $91M
```

cannot both be period measures. The funnel is a **booking cohort**: of the orders
booked in the period, how much has reached each stage *by now*. The tiles are
**balances and flows**: AR at as-of, cash collected in the period from invoices
of any vintage. Mixing them means the funnel double-counts nothing but explains
nothing, and the first CFO in the room says:

> "DSO is 47 days and terms are Net 45. Of course Q4 bookings aren't cash yet.
> What's actually wrong here?"

At that point the "$37M leakage" story is dead, because most of it is timing.

**Fix it by splitting leakage from timing, which makes the demo better, not
worse.** Define the waterfall on a trailing-12-month booking cohort, and split
the final bar:

```
Bookings (TTM, gross)                            $128.4M
  - Cancelled                                      -$3.2M   LOST
  = Net bookings                                  $125.2M
  - Not yet shipped (backorder + credit hold)      -$8.5M   AT RISK
  = Shipped                                       $116.7M
  - In transit / not yet delivered                 -$5.4M   TIMING
  = Delivered                                     $111.3M
  - Delivered, not invoiced                        -$7.3M   LEAKAGE
  = Invoiced                                      $104.0M
  - Credit memos and returns                       -$2.6M   LOST
  = Net invoiced                                  $101.4M
  - Open AR on this cohort                        -$10.1M   (disputed $2.1M / overdue $8.0M)
  = Collected                                      $91.3M
```

Same $37.1M gap as the doc, now with a defensible answer to "so what":

> **$5.8M is gone. $31.3M is stuck. Here is the age of each pile and who owns it.**

Three rules follow, and they belong in `docs/KPI_DEFINITIONS.md` before any code:

1. Every funnel stage is filtered on `order.booking_period`, never on the stage's
   own date. The generator must therefore carry `booked_amount` down every
   downstream table so the funnel is a `SUM` per stage, not six joins.
2. The tiles are labelled as balances (`Open AR as of <date>`) and visually
   separated from the funnel. Do not let them share a row.
3. `Revenue` = invoiced net of credit memos. Not bookings, not cash, not
   shipped. Pick it once and never let a second definition into the model.

### 2.2 Quote conversion is quoted three ways and they contradict each other

- §2 row counts: 100,000 quotes to 80,000 orders = **80% conversion**
- §13 Event 1: conversion **42% falling to 24%**
- §14 funnel: $165M quotes to $128M orders = **78% by value**

By count and by value are legitimately different numbers — big deals win more
often — but not 42% vs 78% different. Someone will divide the two row counts on
screen.

**Decide: conversion is ~40% by count, ~55% by value** (won quotes skew large),
and resize accordingly. That means **quotes 200,000 and quote_lines 800,000** at
full tier, not 100K/400K. Then the funnel's top bar is quoted pipeline of
~$235M, and $128M of orders is a credible 55%.

### 2.3 Pricing leakage (Event 7) has no table behind it — add contract pricing

Event 7 says "invoice price < contracted price", and Scene 7 of the demo
narrative — the AI discovering a 7–12% contracted-vs-billed mismatch — is the
single best moment in the deck. **There is no contracted price anywhere in the
model.** As specified, the claim is unfalsifiable and the money shot has nothing
behind it.

**Add `contract_pricing`, keyed `customer_id x product_id x valid_from/valid_to`**,
holding `contract_price`, `min_price`, `rebate_pct` and `contract_id`. Then:

- `quote_line.quoted_price` is drawn relative to contract price
- `order_line.unit_price` inherits it, with an override path that is itself a
  planted defect
- `invoice_line.unit_price` is compared against it, and the variance is a real
  column, not a story
- "Pricing Discrepancy" disputes are **generated from** lines where the variance
  exceeds a threshold, so the root cause chain is causal end to end

This is the highest-value table not in the doc. Without it, four of the twenty
questions (§19 Q7, Q19, and both pricing-dispute drills) are unanswerable.

### 2.4 Payments, invoice status and AR aging must be derived, never drawn

The doc lists `invoice_status` as a generated column with values including
`Partially Paid` and `Paid`. If status is drawn independently of
`payment_allocations`, you will have invoices marked Paid with a non-zero
balance, and the AR aging matrix (§17, "mandatory" and correctly so) will not
reconcile to the Open AR tile. That is the fastest possible way to lose a
finance room.

**`payment_allocations` is the source of truth.** Everything else is computed:

```
open_amount   = invoice.total_amount
                - SUM(payment_allocations.allocated_amount)
                - SUM(credit_memos.amount applied to this invoice)
invoice_status = Cancelled                          if cancelled
                 Paid                               if open_amount <= 0.01
                 Disputed                           if an open dispute exists
                 Overdue                            if open_amount > 0 and due_date < as_of
                 Partially Paid                     if 0 < open_amount < total
                 Issued                             otherwise
aging_bucket   = f(as_of - due_date) in {Current, 1-30, 31-60, 61-90, 90+}
```

And `validate.py` asserts, at every month-end: `SUM(aging buckets) = SUM(open AR)
= the number on the tile`, to the cent. This is the O2C equivalent of the
payroll-derives-from-salary rule that `hr_adv` got right.

### 2.5 Daily inventory at SKU x warehouse x date is a trap, and you already own that story

§2 asks for `inventory` at 1–3M rows. The stated grain gives
2,000 SKUs x 30 warehouses x 1,095 days = **65.7M rows**. To land at 3M you would
have to silently break the grain, and then nobody can explain what the table is.

Two things are true: O2C does not need daily inventory, and the daily-inventory
demo already exists in `supply_chain` and `inventory_stockout`.

**Replace it with what the O2C story actually needs:**

- `fact_inventory_position` — **monthly** snapshot, restricted to SKU x warehouse
  pairs that actually transact (~15K pairs x 36 months = 540K rows)
- `available_to_promise` on that snapshot, which is what the allocation step
  reads

Then Events 3 (warehouse bottleneck) and 11 (high-margin SKU shortage) emerge
from allocation failing against ATP, rather than being stamped onto orders. An
audience that asks "why was this backordered" gets an answer that survives a
drill-down.

### 2.6 Six of the fifteen events must be causal, not stamped on

Same lesson as `hr_adv` §2.6. If you tag rows after the fact, any cut that is not
the exact cut you planned falls apart, and the AI "discovery" is a magic trick
with a visible wire. These six have to emerge from the simulation:

| # | Event | Must emerge from |
|---|---|---|
| 3 | Warehouse bottleneck | allocation against ATP, with a capacity multiplier on one warehouse |
| 6 | Customer payment slowdown | a per-customer days-to-pay distribution whose mean shifts at month *m* |
| 7 | Pricing leakage | `invoice_line.unit_price` vs `contract_pricing`, via an override path |
| 9 | Credit hold | running exposure vs limit evaluated **at order entry**, order-by-order |
| 11 | Product shortage | ATP exhaustion on specific SKUs |
| 15 | Delivered not invoiced | a fat-tailed billing-lag distribution per business unit |

Event 9 in particular cannot work as a current-state table. `customer_credit` as
specified holds one row per customer with `current_exposure` — so "why did
exposure spike in March" has no answer. **Add
`fact_credit_exposure_snapshot` (customer x month-end)** carrying limit,
exposure, available credit, orders on hold and value on hold. Same fix, same
reason, as the monthly workforce snapshot in `hr_adv`.

The other nine (discount explosion, carrier deterioration, invoice lag, partial
shipments, dispute spike, returns spike, duplicate billing, freight leakage,
quote conversion collapse) are fine as parameter shifts, because each moves a
distribution rather than tagging a set of rows.

### 2.7 Event 12 has no table, and three link keys are missing

- **Event 12 (returns spike) has nowhere to live.** `credit_memos` is the
  financial consequence of a return, not the return. Add `fact_return`
  (RMA header) with reason, condition, disposition and the linked credit memo.
- **`invoice_line` must carry `order_line_id` and `shipment_line_id`.** Without
  them, line-level price variance and "which shipment does this billing error
  come from" are impossible, and those are the two best drill-downs in the demo.
- **`shipment_line` must carry `order_line_id`**, and the fan-out must be
  many-to-one — that *is* the partial-shipment story (Event 8).
- **`dim_carrier` is listed in §12 but missing from the table list in §2.**
  Event 4 needs it.

### 2.8 Smaller notes

- **Anchor the calendar to today.** The doc hardcodes 2024 / 2025 / 2026 YTD and
  places events in named years. Six months from now the demo silently shows a
  stale "current" year. Follow the siblings: `anchor: today`, as-of = last day of
  the previous complete month, history in years back, **event timing as month
  offsets relative to as-of**. Regenerate any time, story intact.
- **Decide the billing rule per customer.** Invoices can be per-shipment or
  consolidated monthly. This single choice drives invoice count, invoice lag and
  the shape of Event 5. Put `billing_rule` on the customer
  (`per_shipment` | `consolidated_monthly`), roughly 70/30. Duplicate billing
  (Event 13) is then a defect *on top of a defined rule*, which is far more
  convincing than a random duplicate.
- **Multi-currency needs a method.** `currency` appears on quotes, orders and
  invoices and `dim_currency` is in §12, but nothing says how. Do what `sales`
  does: fixed budget rate plus `dim_exchange_rate`, and store **local and USD on
  every money column**. Force payment currency = invoice currency so FX gain/loss
  stays out of the model — you are demoing O2C, not treasury.
- **No distributions are specified anywhere.** Pareto customers (top 20% ~ 70% of
  revenue), lognormal order values, lognormal days-to-pay conditioned on segment
  and payment terms, Poisson lines-per-order. Without these the data looks
  uniform on any histogram, which is the tell that it is synthetic.
- **Define DSO once.** It is on the tile and Q20 depends on it. Recommend
  count-back DSO, documented in `KPI_DEFINITIONS.md`, with the simpler
  `AR / revenue x days` also available and *labelled differently*. Q20 ("improve
  DSO by 5 days, how much cash?") is a simulation, not a query — ship it as
  `revenue_per_day x 5` with the assumption stated on screen.
- **Define perfect order rate.** It is the best KPI in §16 and needs four flags
  to exist: on-time, complete, damage-free, correctly invoiced. Generate all
  four; the composite is their product.
- **Plant data-quality defects deliberately.** §20 implies them, §13 never
  specifies any. The best one here is causal: orders where `po_number` is blank
  become "Missing PO" disputes downstream. Add customer name variants for one
  legal entity across sites, and a handful of shipments delivered with no
  delivery event.
- **Nothing may use a real trademark.** The doc names Acme, GlobalTech and
  Contoso. GlobalTech is already the `hr_adv` company and Contoso is Microsoft's.
  Use the fictional pools the siblings use.

---

## 3. Decision to take before Phase 0

**Is this a new company, or an extension of ApexTech?**

`sales/` already ships `fact_sales_order`, `fact_sales_order_line`,
`dim_customer`, `dim_product`, `dim_sales_rep` and `fact_returns` for ApexTech.
Extending it would give one connected mega-demo; it would also mean any change to
the O2C story risks the sales demo, and the two datasets would have to be
regenerated together forever.

**Recommendation: a new standalone company, sharing code but not data.** Roughly
40% of the generator is already written and portable near-unchanged from the
siblings — `dim_date.py`, the config/anchoring loader, `emit_ddl.py`,
`run_questions.py`, and the `validate.py` skeleton. Suggested name in the house
style: **Vantage Industrial** (industrial distribution — makes backorders,
freight, contract pricing and credit holds all natural). Swap it if you prefer.

---

## 4. Revised data model — 31 tables

Full tier row counts, corrected for §2.2 and §2.5.

### Dimensions

| # | Table | Grain | Small | Full |
|---|---|---|---:|---:|
| 1 | `dim_date` | day | 1,700 | 1,700 |
| 2 | `dim_customer` | customer, flattened hierarchy | 1,500 | 5,000 |
| 3 | `dim_customer_site` | ship-to / bill-to site | 2,400 | 8,000 |
| 4 | `dim_product` | SKU, flattened hierarchy | 600 | 2,000 |
| 5 | `dim_sales_rep` | rep, with territory and region | 80 | 250 |
| 6 | `dim_warehouse` | warehouse | 12 | 30 |
| 7 | `dim_carrier` | carrier x service level | 15 | 40 |
| 8 | `dim_payment_terms` | terms code | 12 | 12 |
| 9 | `dim_currency` | currency | 8 | 8 |
| 10 | `dim_exchange_rate` | currency x month | 300 | 300 |
| 11 | `contract_pricing` | customer x product x period | 40K | 180K |

### Commercial

| # | Table | Grain | Small | Full |
|---|---|---|---:|---:|
| 12 | `fact_quote` | quote header | 50K | 200K |
| 13 | `fact_quote_line` | quote line | 200K | 800K |
| 14 | `fact_order` | sales order header | 20K | 80K |
| 15 | `fact_order_line` | order line | 80K | 320K |

### Fulfilment and logistics

| # | Table | Grain | Small | Full |
|---|---|---|---:|---:|
| 16 | `fact_fulfillment` | order x warehouse allocation | 25K | 100K |
| 17 | `fact_shipment` | shipment header | 30K | 120K |
| 18 | `fact_shipment_line` | shipment line -> order line | 100K | 400K |
| 19 | `fact_delivery_event` | carrier scan event | 150K | 600K |
| 20 | `fact_inventory_position` | SKU x warehouse x month-end | 140K | 540K |

### Finance

| # | Table | Grain | Small | Full |
|---|---|---|---:|---:|
| 21 | `fact_invoice` | invoice header | 24K | 95K |
| 22 | `fact_invoice_line` | invoice line -> order line, shipment line | 95K | 380K |
| 23 | `fact_payment` | customer payment / remittance | 18K | 70K |
| 24 | `fact_payment_allocation` | payment -> invoice | 33K | 130K |
| 25 | `fact_credit_memo` | credit memo | 2K | 8K |
| 26 | `fact_dispute` | invoice dispute | 2.5K | 10K |
| 27 | `fact_return` | RMA | 3K | 12K |
| 28 | `fact_credit_exposure_snapshot` | customer x month-end | 54K | 180K |
| 29 | `fact_ar_aging_snapshot` | open invoice x month-end | 220K | 850K |

### Derived — the three that make the demo fast

| # | Table | Grain | Small | Full |
|---|---|---|---:|---:|
| 30 | `fact_o2c_cycle` | order: every milestone date + value at each stage | 20K | 80K |
| 31 | `fact_o2c_exception` | open exception | 15K | 60K |

That is 31 rather than the doc's 15–18, but 11 are small dimensions and the last
two are materialised views of facts that already exist. Total ~4.5M rows at full
tier, ~1.2M at small.

`fact_o2c_cycle` is §15 and §18 materialised — one row per order carrying
`quote_date, order_date, promised_date, allocated_date, ship_date, delivered_date,
invoice_date, fully_paid_date` plus the value that reached each stage, and the
derived lags. The waterfall and the process-time bridge become `SUM` and `AVG`
over one table rather than a calculation five tools each get slightly
differently. Same reasoning as `fact_workforce_cost_bridge` in `hr_adv`.

`fact_o2c_exception` is §20 materialised: one row per open exception, typed,
valued, aged and owned. It is the demo entry point, and it should be a table so
the headline count is stable across tools.

**Conventions inherited from the siblings:** lowercase `snake_case`, no reserved
words, `DECIMAL(18,2)` money in local **and** USD, `0/1` integer booleans, ISO
dates, and **no NULL foreign keys** — an order with no quote points at a real
"Direct Order" row. Two tiers, same seed, same events, same story. Parquet
always, CSV at small tier only.

---

## 5. Architecture — an order-lifecycle state machine, not a table-at-a-time builder

`sales` and `supply_chain` build dimensions then draw facts against them. That
cannot work here: credit exposure depends on prior orders, allocation depends on
inventory consumed by prior orders, invoice status depends on payments, and
disputes depend on price variance produced upstream. The feedback loop *is* the
demo.

**Core loop** — for each day (or week, for speed) from history start to as-of:

```
1  generate quotes for the day; expire, win or lose the ones that mature
2  convert won quotes to orders
3  at order entry, evaluate credit exposure vs limit    -> Credit Hold or Booked
4  allocate booked orders against warehouse ATP         -> fulfilment, backorders
5  pick / pack / ship what is allocated                 -> shipments, shipment lines
6  advance in-transit shipments through carrier events  -> delivery events, delays
7  apply the customer's billing rule to delivered lines -> invoices, invoice lines
8  compare invoice price to contract price              -> price variance, disputes
9  draw customer payments from days-to-pay behaviour    -> payments, allocations
10 age open invoices; raise disputes, credit memos, returns
11 at month-end: emit AR aging, credit exposure and inventory position snapshots
```

`fact_o2c_cycle` and `fact_o2c_exception` are computed after the loop, from the
state it produced.

### Layout

```
config/scenario_base.yaml   every knob, including all 15 event definitions
src/
  generate.py               entry point
  validate.py               integrity + narrative + waterfall tie-out
  emit_ddl.py               DDL from the actual parquet schemas
  run_questions.py          runs the demo questions via DuckDB
  o2cconfig.py              config load + calendar anchoring      [port from hr_adv]
  dim_date.py               [port from supply_chain, unchanged]
  reference.py              customer / product / geography pools
  customers.py              hierarchy, sites, segments, credit limits, billing rules
  products.py               catalog, hierarchy, cost, list price
  pricing.py                contract pricing, price lists, rebates
  quotes.py                 quote generation, win/loss, conversion
  orders.py                 order booking, credit check, exposure ledger
  fulfillment.py            ATP allocation, backorders, warehouse capacity
  shipping.py               shipments, carrier events, delays, freight
  billing.py                billing rules, invoices, price variance, duplicates
  receivables.py            payment behaviour, allocations, disputes, credit memos, returns
  snapshots.py              AR aging, credit exposure, inventory position
  derived.py                o2c cycle, exception centre, funnel roll-up
  events.py                 the 15 planted events as multiplier matrices
sql/demo_questions.sql      the 30 questions as runnable SQL
sql/snowflake/  sql/databricks/
docs/DATA_MODEL.md  EVENTS.md  DEMO_FLOWS.md  KPI_DEFINITIONS.md
data/small/  data/full/
```

---

## 6. The fifteen events, as config

All fifteen from §13 survive. Restated with the parameters the generator needs
and the magnitude the validator asserts. Timing is months relative to as-of, so
nothing goes stale. Each carries `enabled: true|false` so any story can be
removed from the data entirely, and each event's scope is expressed as a
**fraction of the population**, not an absolute count, so it stays proportionally
visible at both tiers.

| # | Event | Config | Validator asserts |
|---|---|---|---|
| 1 | Quote conversion collapse | region EMEA, months -14..-1, win rate x0.57 | EMEA conversion 24-27% vs 41-44% company |
| 2 | Discount explosion | 3 reps, months -12..-1, discount 8% -> 22% | those reps' avg discount >= 2.5x peer median |
| 3 | Warehouse bottleneck | WH-07 capacity x0.55, months -10..-1 | WH-07 backorder rate 17-21% vs 4-6% network |
| 4 | Carrier deterioration | Carrier X transit x1.7, delay prob x4, months -8..-1 | Carrier X OTD 69-73% vs 93-95% |
| 5 | Invoice lag | BU West billing lag 3d -> 11d, months -9..-1 | BU West delivery-to-invoice >= 10d |
| 6 | Customer payment slowdown | top-10 customer days-to-pay 35 -> 67, months -7..-1 | that customer's avg days-to-pay >= 60 |
| 7 | Pricing leakage | 4% of invoice lines priced 7-12% below contract | >= $1.8M variance, concentrated in 2 customers |
| 8 | Partial shipment problem | one product family split-ship rate 12% -> 38% | freight per order line >= 1.6x baseline |
| 9 | Credit hold | limits frozen while volume grows, months -6..-1 | $4.2-5.2M of orders on hold at as-of |
| 10 | Dispute spike | one customer dispute rate x6, months -5..-1 | that customer's monthly disputes >= $1.2M |
| 11 | Product shortage | 6 high-margin SKUs, ATP exhausted, months -8..-3 | those SKUs' fill rate <= 70% |
| 12 | Returns spike | one category return rate 2% -> 9%, months -6..-1 | that category's return rate >= 4x company |
| 13 | Duplicate billing | 0.4% of orders billed twice, all months | >= 200 duplicate invoice pairs, detectable by amount+customer+date |
| 14 | Freight leakage | expedite rate 6% -> 19% on backordered lines, months -10..-1 | expedited freight spend >= 2.5x baseline |
| 15 | Revenue trapped | billing lag fat tail, 3 BUs, months -6..-1 | $6.8-7.8M delivered-not-invoiced at as-of |

Note that 14 is **downstream of 3** — the warehouse bottleneck causes backorders,
backorders get expedited, expedite costs rise. And 10 is **downstream of 7** —
pricing leakage causes the disputes. Building those chains rather than two
independent multipliers is what makes the AI root-cause scene in §22 real.

Event timing is deliberately staggered so the doc's §21 before/after story works:
years -3 and -2 are a clean baseline, the operational events land in year -1, and
the financial consequences land in the current year.

---

## 7. Target headline

The as-of executive row the whole demo hangs off, per §2.1:

```
Bookings (TTM)   $128.4M  +12.4%      Revenue (TTM)  $103.7M  +9.8%
Open AR          $41.2M   +14.2%      Overdue AR     $12.8M   +28.4%
DSO              47 days  +6 days     Perfect order  84.2%    -5.1pt
```

with the exception centre reading:

```
1,842 open O2C exceptions blocking $7.8M
```

and the cohort waterfall from §2.1 closing to $91.3M. `validate.py` asserts the
waterfall closes to the cent, that the aging buckets sum to open AR, and that
every enabled event hits the magnitude in §6.

The bookings-up-12.4% / revenue-up-9.8% / overdue-up-28.4% pattern is the whole
demo in three numbers: growth is real, conversion to cash is not keeping up, and
the ageing is deteriorating faster than either. Engineer those three deliberately.

---

## 8. The twenty questions

Sixteen of the doc's twenty are answerable against the model in §4 as-is. Four
need the additions above, which is the clearest argument for making them:

| Q | Needs |
|---|---|
| 5 — delivered but not invoiced | `fact_o2c_cycle` (§4) — otherwise a six-table join per query |
| 19 — invoice-to-order pricing discrepancies | `contract_pricing` (§2.3) |
| 20 — improve DSO by 5 days | a defined DSO formula (§2.8) and a stated assumption |
| 4 — top five causes of leakage | the waterfall split into LOST / AT RISK / TIMING (§2.1) |

Ship all twenty as runnable SQL in `sql/demo_questions.sql`, plus ten more
covering the exception centre and the aging matrix, and have `run_questions.py`
prove every one returns a non-empty, non-absurd result before you present.

---

## 9. Build phases

| Phase | Output | Est. |
|---|---|---|
| 0 | `docs/DATA_MODEL.md` + `KPI_DEFINITIONS.md` — exact columns, types, keys, and the §2.1 cohort methodology settled | 0.5d |
| 1 | Config, calendar anchoring, reference data, customer/product hierarchies, contract pricing | 1.5d |
| 2 | Quotes: generation, win/loss model, conversion, discount behaviour | 1d |
| 3 | Orders: booking, credit exposure ledger, credit holds | 1d |
| 4 | Fulfilment: ATP allocation, backorders, warehouse capacity, inventory position | 1.5d |
| 5 | Shipping: shipments, carrier event chains, delays, freight and expedite | 1.5d |
| 6 | Billing: billing rules, invoices, price variance, duplicates, credit memos | 1.5d |
| 7 | Collections: payment behaviour, allocations, disputes, returns, AR aging | 1.5d |
| 8 | Derived: `fact_o2c_cycle`, `fact_o2c_exception`, funnel roll-up | 1d |
| 9 | `validate.py` — integrity, narrative, waterfall and aging tie-out | 1d |
| 10 | `emit_ddl.py`, 30 demo questions as SQL, `run_questions.py` | 0.5d |
| 11 | `README.md`, `DEMO_FLOWS.md`, `EVENTS.md`, 15-minute demo script | 0.5d |

Roughly **13 days** — longer than the 9 for `hr_adv`, because the lifecycle
simulator has more stages and the finance tie-outs are stricter. Phases 2–7 are
the critical path and are strictly sequential; 9 should be written incrementally
against partial output rather than saved for the end. On the Meridian build the
validator is what caught planted signals being swamped by noise, and here it is
also the only thing standing between you and an AR matrix that does not add up.

### Acceptance criteria

The dataset is demo-ready when:

1. The cohort waterfall closes: bookings minus every stage loss equals collected,
   to the cent.
2. At every month-end, `SUM(aging buckets) = SUM(open AR) = SUM(invoice.total -
   allocations - credit memos)`, to the cent.
3. No invoice has a status inconsistent with its computed open amount.
4. Every `shipment_line` resolves to an `order_line`, every `invoice_line` to
   both an `order_line` and a `shipment_line`, with quantities that reconcile.
5. Every enabled event passes its narrative check at the magnitude in §6.
6. `fact_o2c_cycle` milestone dates are monotonic for every order.
7. All 30 demo questions return non-empty, non-absurd results.

---

## 10. Summary of what changes from the design note

| Change | Why |
|---|---|
| Funnel redefined as a booking cohort, leakage split from timing | §2.1 — otherwise the headline is indefensible |
| Quotes 100K -> 200K, quote_lines 400K -> 800K | §2.2 — conversion rate contradiction |
| `contract_pricing` added | §2.3 — Event 7 and Scene 7 have no data behind them |
| Invoice status and AR aging derived, never drawn | §2.4 — finance-room credibility |
| Daily inventory replaced with monthly position + ATP | §2.5 — stated grain gives 65M rows, and `supply_chain` already owns that demo |
| `fact_credit_exposure_snapshot` added | §2.6 — Event 9 needs history, not current state |
| `fact_return` added; three link keys added | §2.7 — Event 12 has no table; drill-downs impossible without the keys |
| `dim_carrier` added to the table list | §2.7 — listed in §12, missing from §2 |
| `fact_o2c_cycle` and `fact_o2c_exception` added as derived tables | §4 — makes §15, §18 and §20 fast and consistent across tools |
| Calendar anchored to today, events as month offsets | §2.8 — the demo must not go stale |
| Billing rule, currency method, distributions, DSO and perfect-order definitions specified | §2.8 — all unspecified in the doc |
| 6 events made causal; events 3->14 and 7->10 chained | §2.6 — the AI root-cause scene has to survive an unplanned drill-down |
