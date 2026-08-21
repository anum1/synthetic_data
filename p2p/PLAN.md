# Procure-to-Pay Control Tower — review of the design note, and a build plan

> **Status: built.** This plan was executed. The dataset lives in this folder —
> see [README.md](README.md) for how to run it, [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
> for the 44 tables as actually shipped, [docs/EVENTS.md](docs/EVENTS.md) for the
> measured magnitude of each planted event, and
> [docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) for the measurement decisions
> in §2.1, §2.2 and §2.5 as they were finally settled. Where the built dataset
> differs from this plan — 161K POs rather than 104K, 5.3M rows estimated against
> 3.9M shipped, `contract_price_variance` split from `off_contract_premium`, and
> several event magnitudes the arithmetic would not support — **the docs are
> authoritative**.

Review of [p2p_demo_data_design.txt](p2p_demo_data_design.txt), plus the plan to
generate it as a real dataset in the style of the sibling `sales` (ApexTech),
`supply_chain` (Meridian), `hr_adv` (GlobalTech) and `o2c` (Vantage Industrial)
projects.

---

## 1. Verdict

The story is right. P2P is the strongest of the five design notes for an
Incorta/NLQ demo, for one reason the note doesn't quite say out loud: **P2P is
the only one of these processes where the interesting questions are inherently
multi-table.** "Which suppliers have high spend, poor delivery and high exception
rates" needs six joins and cannot be answered from a pre-aggregated cube. That is
the platform argument, and it is handed to you by the process itself.

The fraud/risk section (§7) is the differentiator. No competitor demo has it, and
"find suppliers sharing a bank account" lands in a room in a way that "spend by
category" never does.

**Keep the story. The data design underneath it is not buildable as written.**
Nine things need settling before any code, listed in §2 roughly in the order they
will hurt you. §3 onward is the plan.

The single most important one is §2.1: **the funnel on page 1 goes up, not down**
— 82K POs producing 120K invoices — and the note never says why. An AP audience
notices in about four seconds. Fixed, it becomes the best scene in the demo.

---

## 2. What needs to change before writing any code

### 2.1 The funnel widens. That is the whole story — but only if you label it.

The note's §10 funnel:

```
100K Requisitions -> 82K POs -> 77K Receipts -> 120K Invoices -> 108K Payments
```

Invoices exceed receipts by 43K and POs by 38K. Read literally this says the
company is invoiced for things it never ordered and never received, which is
either the most alarming slide ever shown to a CFO or, more likely, an
unlabelled mixture of three populations:

- invoices with no PO at all (the maverick spend story, §6 Event 1),
- POs invoiced in several instalments (milestone billing, blanket call-offs),
- service invoices with no goods receipt (2-way match, which the note never mentions).

And payments cannot be 108K against 120K invoices, because **a payment run pays
many invoices at once**. The real ratio is 2–3 invoices per payment, so payments
should be roughly 45–60K. There is no `payment_application` table in the model,
which is why the note didn't notice.

**Fix: two lanes, drawn separately, and a value waterfall underneath.**

```
                      ┌── PO invoices 42.0K ──┐
Reqs 42.1K -> POs 34.2K                        ├──> 20.0K pay runs, 50.0K invoices
                      └── Non-PO invoices 8.0K ┘
```

(PO invoices exceed POs because a blanket or milestone PO is invoiced several
times. Say that sentence; it is the one the room is waiting for.)

The document funnel is for orientation. The number the demo actually hangs off
is the **PO commitment-to-cash waterfall**, on a trailing-twelve-month PO cohort:

```
PO commitment raised (TTM, gross)         $268.0M
  - Cancelled / closed short                -$9.4M   RELEASED
  = Net commitment                         $258.6M
  - Not yet received (open commitment)     -$34.1M   IN FLIGHT
  = Received                               $224.5M
  - Received, never invoiced (GR/IR)       -$18.7M   ACCRUAL  <- 62% aged >90d
  = Invoiced                               $205.8M
  - Blocked on match exceptions            -$16.2M   STUCK
  = Approved for payment                   $189.6M
  - Open payables still within terms       -$21.3M   TIMING
  = Paid                                   $168.3M
```

and total spend reconciles across all three channels:

```
PO-backed invoiced   $205.8M
Non-PO invoiced       $46.6M   <- of which $12.8M had a contract available: MAVERICK
P-card / expense      $32.2M
= Total spend TTM    $284.6M   (the note's headline, now with a derivation)
```

Three rules follow, and they belong in `docs/KPI_DEFINITIONS.md` before any code:

1. Every waterfall stage filters on `purchase_order.po_period`, never on the
   stage's own date. The generator therefore carries `committed_amount` down
   every downstream table, so each bar is a `SUM`, not a six-table join.
2. **GR/IR — received-not-invoiced — is a headline tile, not a footnote.** The
   note omits it entirely and it is the single most CFO-relevant number in P2P:
   goods consumed, accrual sitting on the balance sheet, no invoice in sight. It
   is also the exact mirror of the "delivered not invoiced" leakage that carries
   the `o2c` demo, so the two datasets tell a matched pair of stories.
3. Tiles are balances (`Open payables as of <date>`), the funnel is a cohort.
   Say it out loud in the first 30 seconds. Do not let them share a row.

### 2.2 Eight headline numbers contradict each other

Straight from the note:

| Metric | Says | Also says | Where |
|---|---|---|---|
| Purchase orders | 80,000 | 82K | §2 vs §10 |
| Goods receipts | 150,000 | 77K | §2 vs §10 |
| Payments | 100,000 | 108K | §2 vs §10 |
| Avg P2P cycle | 28.4 days | 31.4 days | §10 vs §9/§15 |
| Match / STP rate | 91.2% | 91% | §10 vs §12 |
| Exception rate | 12.7% | 9% | §10 vs §12 |
| Total spend | $284.6M | $50M PO + $8M non-PO | §10 vs §6 |
| Contracted spend | 87.4% | implied ~65% | §10 vs §6 |

Some are typos; two are real design questions.

**Match rate vs STP vs exception rate are three different metrics** and should be
given three deliberately different numbers, each with a stated denominator:

- **First-pass match rate** = PO invoices passing every tolerance check on the
  first attempt / PO invoices. Target **88.6%**.
- **Straight-through processing** = invoices reaching payment with zero human
  touch / *all* invoices. Lower, because non-PO invoices always need coding and
  approval. Target **71.4%**.
- **Exception rate** = invoices that ever carried a hold / all invoices. Target
  **14.8%**.

If all three are 91%, the first person who divides differently catches you.

**Total spend**: §6 Event 1's $50M/$8M/$5M is a different (and much smaller)
universe than the $284.6M headline. Use the §2.1 reconciliation and delete
Event 1's numbers.

### 2.3 The 3-way match must be *derived from a tolerance policy*, never drawn

`three_way_match` at 120,000 rows — one per invoice — is the most dangerous table
in the model. Two problems:

- **Wrong grain.** Match happens per invoice *line*. A header-level match row
  hides exactly the quantity mismatch that §6 Event 3 wants to show. Grain must
  be invoice line: ~296K rows.
- **Wrong direction.** If the match outcome is drawn from a distribution, then
  the moment anyone drills from "exception" to the PO / receipt / invoice
  quantities, the numbers will not justify the verdict. The demo dies on the
  drill-down, which is the one place you were counting on it not to.

Add `dim_match_tolerance` as real data — by category and company code:

```yaml
price_tolerance_pct: 0.02        # or $50 absolute, whichever is greater
price_tolerance_abs: 50
qty_tolerance_pct: 0.05          # or 2 units, whichever is greater
qty_tolerance_abs_units: 2
total_variance_cap: 250          # under this, auto-write-off, no hold
```

and compute `fact_match_result` per invoice line from the actual PO price, actual
received quantity and actual invoiced quantity. Match type is data too:

- **3-way** — goods POs with a receipt required
- **2-way** — service POs and blankets (no receipt exists; the note never
  accounts for these, and they are ~30% of indirect spend)
- **non-PO** — no match possible; coding + approval only

Then "exception rate" can be broken down by match type on stage, which is a
genuinely good answer to "why is our exception rate 14.8%".

Also note §12's exception reason mix mixes two taxonomies: *price mismatch* and
*quantity mismatch* are match outcomes; *missing receipt*, *PO missing* and
*duplicate* are AP holds. Model them as `fact_invoice_hold` with a reason code,
raised/released dates and an owning team — one invoice can carry several — and
derive the match result separately.

### 2.4 The missing bridge: `payment_application`

Without an invoice-to-payment bridge you cannot compute partial payments,
discount taken, DPO, on-time payment %, or "which invoices did this $840K
payment cover" — which is the drill the note promises in §18. Every one of the
AP metrics in §8 depends on this table. It is the largest single omission.

Grain: one row per (payment, invoice) with `applied_amount`, `discount_taken`,
`days_early_or_late`. Payments then aggregate naturally, and the AP subledger
identity becomes checkable:

```
invoice.open_amount = invoice.gross_amount
                    - SUM(payment_application.applied_amount)
                    - SUM(credit_memo.amount)
                    - SUM(payment_application.discount_taken)
```

The validator asserts this to the cent, at every month-end, against the aging
snapshot. In `o2c` that check is what caught three separate bugs.

### 2.5 Cycle time as drawn is arithmetically impossible

§9 wants "end-to-end P2P cycle time 31.4 days" over a chain that includes
requisition approval, supplier lead time, invoice approval **and payment terms**.
On Net 30 terms the payment leg alone is ~30 days. A real req-to-cash P2P chain
is 65–80 days, and quoting 31 tells a procurement audience you have never
measured one.

Model six legs, and — this is the point — **split what you control from what you
don't**:

| Leg | Days | Owner |
|---|---:|---|
| Requisition created -> approved | 3.1 | **Us** |
| Requisition approved -> PO issued | 4.6 | **Us** |
| PO issued -> first receipt | 21.8 | Supplier (lead time) |
| Receipt -> invoice received | 9.4 | Supplier (billing lag) |
| Invoice received -> approved | 11.2 | **Us** |
| Approved -> paid | 22.6 | Terms + pay-run cadence |
| **Req -> cash** | **72.7** | |

> *"Seventy-three days. Thirty-one are the supplier's, twenty-three are the
> contract. **Nineteen are ours** — and that nineteen is where the money is."*

That reframing does the same work the leakage/timing split does in `o2c`, and it
sets up §2.6.

### 2.6 Make the events causal — the discount story is the best example

The note lists Event 6 (slow invoice approval) and Event 8 (missed early-payment
discounts) as unrelated. **They are the same event**, and connecting them turns a
KPI into a root cause:

```
Terms 2%/10 Net 30      -> discount window closes on day 10
Invoice received -> approved, average 11.2 days
                        -> the window is already shut when the invoice is
                           approved. Treasury never had a decision to make.
```

Target: $1.24M of discount eligible TTM, $0.19M captured, **$1.05M missed — and
78% of the misses were approved after day 10.** The AI answer to "how much are we
leaving on the table" then continues into "and why", which is the moment the demo
earns its keep.

Chain at least five more the same way:

- **Contract price vs PO price drift (E4)** -> price-variance holds (E2) ->
  longer invoice approval (E6) -> missed discounts (E8) -> late payment (E9).
  One root cause, five symptoms, five different dashboard pages. This is the
  §17 demo story and it must be *generated* causally, not stamped on five tables
  independently, or an unplanned drill-down will contradict the narrative.
- **Late receipts (E5)** -> receipt/invoice date inversion -> "invoice before
  receipt" holds.
- **Supplier concentration (E10)** -> price increases accepted -> the
  consolidation savings opportunity is *also* a risk exposure. Both readings from
  one dataset is a good tension to have on screen.

### 2.7 2% fraud is not fraud, it is a business model

§16 allocates **2% of data to fraud/risk scenarios**. At 120K invoices that is
2,400 fraudulent transactions. Ask the AI "find suppliers sharing bank accounts"
and it returns hundreds of rows; nobody in the room believes it, and there is no
detection story because detection is trivial.

Fraud plants should be **dozens of cases, placed precisely**:

| Condition | Note says | Use |
|---|---:|---:|
| Normal | 85% | 84% |
| Minor anomalies (noise, roundings, small variances) | 7% | 10% |
| Operational problems (the ten planted events) | 5% | 5.5% |
| Fraud / risk scenarios | 2% | **0.4%** |
| Extreme planted events | 1% | 0.1% |

And every fraud pattern needs a **control group of innocent lookalikes**, or the
demo is a filter, not an analysis:

- Shared bank accounts: 3 real clusters **plus 2 benign ones** (subsidiaries of a
  common parent legitimately sharing a remit-to account).
- Employee/supplier name matches: 4 genuine conflicts **plus 6 coincidental
  surname collisions**.
- Just-below-threshold POs: the point is not that POs exist at $49,850 — some
  always will. It is that there is *excess mass* in the $45–50K bin versus the
  fitted lognormal for that category. Generate the legitimate tail first, then
  add the excess, so the analysis has to be statistical.
- PO splitting: same requester + supplier + category within 10 days summing past
  a threshold. Plant 40 real cases against a natural base rate of ~300 innocent
  co-occurrences.

The DOA thresholds must exist **as an effective-dated policy table**, varying by
role, category and legal entity — otherwise "just below the threshold" is an
assertion the data cannot support, and the join that proves it is exactly the
kind of thing you want the platform doing live.

### 2.8 Duplicate invoices need archetypes — and some must have been paid

`INV-10021` twice for the same supplier violates the unique constraint in every
real ERP, so an AP audience will not accept it. Real duplicates arrive through
four doors, and you want all four:

1. **Formatting variants** — `ABC-12345` / `ABC12345` / `ABC-012345`, same
   supplier, same amount, same PO.
2. **Different supplier site or duplicate supplier record** — the same invoice
   entered against `Northbeam Technologies` and `Northbeam Tech Corp`. This is
   where §4's supplier-duplication story pays off twice.
3. **PO invoiced twice** — one from the supplier portal, one by email.
4. **Credit memo never applied** — a rebill that looks like a duplicate and is not.
   The false positive that makes the demo honest.

Critically: **some of these must have been paid.** "We have 412 suspected
duplicates worth $2.1M" is interesting. "**We paid 63 of them. $418K left the
building.**" is the number people repeat afterwards.

Detection needs a fuzzy key the data supports: supplier *parent* + gross amount
± 1% + invoice date within 10 days + normalized invoice number distance ≤ 2.

### 2.9 Smaller notes

- **Trademarks.** §4 uses IBM. Every sibling project is explicitly safe to show
  to a customer because nothing in it is a real company. Replace with an invented
  supplier family; the demo point is identical.
- **Fixed dates.** §15 pins 2024–2026. Anchor to *today* instead: as-of is the
  last day of the previous complete month, three years of history plus YTD (43
  months), and every event timed in months relative to as-of. The demo then never
  goes stale — this is already the pattern in `hr_adv` and `o2c` and the code
  ports directly.
- **Requisition-to-PO cardinality is unspecified**, and 100K reqs -> 80K POs
  implies near-1:1, which makes "req to PO days" trivially uninteresting. Use
  70% 1:1, 25% many-reqs-to-one-PO (aggregation, which is *why* it takes 4.6
  days), 5% one-req-across-several-POs. And ~18% of requisitions never become a
  PO at all — rejected, withdrawn, budget-blocked. That loss is a story the note
  currently has no way to tell.
- **`approval_event` needs a polymorphic key** (`doc_type`, `doc_id`) so it
  covers requisitions, POs, PO changes and invoices in one table, plus
  `approver_id`, `delegated_from_id` and `queue_entered_at`. Without the last
  two, "which approver is the bottleneck" and "approvals stall when the CFO is on
  leave" are unanswerable.
- **`budget` has no join key** in the note. Grain: cost centre × category ×
  fiscal period. Story: budget overspend concentrated in the same two departments
  that carry the maverick spend.
- **FX is listed but not designed.** Store transaction currency and amount, plus
  `amount_usd` at the document-date rate, and add `dim_exchange_rate` at daily
  grain. Then plant one European supplier whose apparent 9% price increase is
  entirely EUR/USD — a red herring that rewards the analyst who checks, and a
  great "the AI got this right" moment.
- **No item master.** "Where are we paying different prices for the same product"
  (§14) requires items to be comparable across suppliers. Add `dim_item` with a
  `normalized_item_key` so the same widget bought from three suppliers is
  joinable. Without it that question — one of the best in the note — is dead.
- **Inactive suppliers receiving POs** (§4) needs supplier status to be
  *effective-dated*, not a current-state flag, or you cannot tell "was inactive
  when the PO was raised" from "went inactive since".

---

## 3. Decisions to take before Phase 0

1. **Company and hero supplier names.** Proposed: **Norvant Group**, a
   diversified manufacturer (so both direct and indirect spend are in scope), and
   **Northbeam Technologies** as the §17 hero supplier. Suppliers, employees and
   items all invented.
2. **Direct spend in or out?** Recommend **in**. The note's category tree is
   indirect-only, which caps total spend credibility at ~$60M and makes supplier
   concentration artificial. Adding a direct branch (raw materials, components,
   packaging) gets you to $284.6M honestly and gives contract compliance real
   teeth.
3. **P-card / expense channel in or out?** Recommend **in**, one flat table. It
   completes the total-spend reconciliation in §2.1 and it is where the most
   defensible maverick spend lives.
4. **Multi-entity?** Recommend **yes** — 6 legal entities. Duplicate suppliers
   and split POs are far more realistic across entities, and it is one extra
   dimension.
5. **Tiers.** `small` for Tableau / Power BI Desktop, `full` for Snowflake /
   Databricks / Incorta. Same seed, same events, same story.

---

## 4. Revised data model — 44 tables

Naming follows `o2c`: `dim_*` for master and policy, `fact_*` for transactions
and snapshots.

### Master and policy (19)

| Table | Full rows | Notes |
|---|---:|---|
| `dim_date` | 1,600 | port unchanged from `supply_chain` |
| `dim_supplier` | 2,400 | incl. planted duplicates; `normalized_name`, `parent_id`, tax id |
| `dim_supplier_site` | 4,300 | order-from and remit-to; own tax id and address |
| `dim_supplier_parent` | 1,700 | corporate hierarchy for the roll-up story |
| `dim_supplier_bank_account` | 2,900 | the shared-account scenario lives here |
| `dim_supplier_status_history` | 3,100 | effective-dated — see §2.9 |
| `dim_item` | 4,000 | with `normalized_item_key` for cross-supplier price comparison |
| `dim_category` | 340 | 4 levels: segment -> family -> category -> subcategory |
| `dim_employee` | 5,000 | requesters, buyers, approvers; `manager_id`, `doa_limit` |
| `dim_department` | 96 | |
| `dim_cost_center` | 520 | |
| `dim_company_code` | 6 | legal entities |
| `dim_gl_account` | 240 | |
| `dim_payment_terms` | 18 | `discount_pct`, `discount_days`, `net_days` |
| `dim_currency` | 12 | |
| `dim_exchange_rate` | 15,700 | daily, per currency |
| `dim_approval_policy` | 180 | effective-dated DOA by role x category x entity |
| `dim_match_tolerance` | 60 | by category x entity — see §2.3 |
| `dim_hold_reason` | 22 | code, description, owning team, blocks-payment flag |

### Commercial (3)

| Table | Full rows | Notes |
|---|---:|---|
| `contract` | 3,200 | header: supplier, category, dates, committed value, terms |
| `contract_price` | 46,000 | **the source of truth for what we should be paying** |
| `fact_budget` | 26,000 | cost centre x category x fiscal period |

### Transactions (14)

| Table | Full rows | Notes |
|---|---:|---|
| `fact_requisition` | 128,000 | 18% never become a PO |
| `fact_requisition_line` | 312,000 | |
| `fact_purchase_order` | 104,000 | carries `committed_amount` for the waterfall |
| `fact_purchase_order_line` | 246,000 | |
| `fact_po_change` | 38,000 | price / qty / date amendments — the drift story |
| `fact_goods_receipt` | 178,000 | goods POs only; service POs are 2-way |
| `fact_goods_receipt_line` | 372,000 | partial, over- and short-receipts |
| `fact_invoice` | 152,000 | PO-backed and non-PO in one table, `match_type` |
| `fact_invoice_line` | 358,000 | |
| `fact_invoice_distribution` | 410,000 | GL coding; the only link non-PO spend has |
| `fact_payment` | 61,000 | pay runs, not one-per-invoice |
| `fact_payment_application` | 138,000 | **the bridge — see §2.4** |
| `fact_pcard_transaction` | 84,000 | third spend channel |
| `fact_approval_event` | 520,000 | polymorphic; incl. delegation and queue time |

### Derived and snapshots (8)

| Table | Full rows | Notes |
|---|---:|---|
| `fact_match_result` | 296,000 | per invoice line, computed against tolerance |
| `fact_invoice_hold` | 41,000 | exception ledger: reason, raised, released, owner |
| `fact_p2p_cycle` | 152,000 | one row per chain: all six milestone dates + amounts |
| `fact_spend` | 594,000 | unified spend line across PO / non-PO / p-card, with contract and maverick classification carried down |
| `fact_ap_aging_snapshot` | 516,000 | month-end, open invoices |
| `fact_open_commitment_snapshot` | 340,000 | month-end open PO and GR/IR balance |
| `fact_p2p_exception` | 48,000 | unified exception centre across all stages |
| `fact_supplier_risk_snapshot` | 103,000 | monthly per supplier |

**≈ 5.3M rows at `full`**, ~1.3M at `small` — somewhat larger than `o2c`'s
3.7M, entirely because P2P has three more document stages.

`fact_spend` and `fact_p2p_cycle` are the two that matter for demo feel. Both
exist so that the executive page is a single-table scan and stays responsive
while someone is watching.

---

## 5. Architecture — a document-lifecycle state machine

Same reason as `o2c`: the feedback loops *are* the demo. Invoice approval time
depends on whether a hold was raised; the hold depends on price variance against
a contract; the discount depends on the approval date; the payment date depends
on the pay-run calendar and the terms. None of that survives a
table-at-a-time builder.

**Core loop** — weekly, from history start to as-of:

```
 1  draw requisitions per department x category            -> requisition, lines
 2  route through DOA policy                               -> approve / reject / withdraw
 3  convert approved reqs to POs; pick supplier            -> PO, PO lines
       contract / preferred / spot, and price from contract_price
 4  amend open POs                                          -> po_change
 5  advance open POs by supplier lead time                  -> receipts (full,
       partial, over, short, late)
 6  supplier issues invoice: from receipt, or standalone    -> invoice, lines,
       distributions
 7  run the match engine against dim_match_tolerance        -> match_result,
       and raise holds where it fails                          invoice_hold
 8  route invoice approval; resolve or age the holds        -> approval_event
 9  weekly pay run: select approved invoices due,           -> payment,
       take the discount only if still inside the window       payment_application
10  month-end: AP aging, open commitment / GR-IR, risk      -> snapshots
```

Then, after the loop: `fact_match_result` roll-up, `fact_p2p_cycle`,
`fact_spend`, `fact_p2p_exception`.

**The invariant that makes it work:** `committed_amount` from the PO line is
carried onto every receipt line, invoice line and payment application. The
waterfall in §2.1 is then a `SUM` per stage and cannot drift from the detail.

### Layout

```
config/scenario_base.yaml   every knob, including all 18 event definitions
src/
  generate.py               entry point
  validate.py               integrity + subledger + waterfall + narrative
  emit_ddl.py               DDL from the actual parquet schemas
  run_questions.py          runs the demo questions via DuckDB
  p2pconfig.py              config load + calendar anchoring   [port from o2c]
  dim_date.py               [port from supply_chain, unchanged]
  reference.py              supplier / item / geography name pools
  suppliers.py              hierarchy, sites, bank accounts, duplicates, risk
  orgs.py                   employees, departments, cost centres, DOA policy
  catalog.py                categories, items, GL accounts
  contracts.py              contracts and contract_price - the price truth
  requisitions.py           demand, approval routing, rejection
  purchasing.py             req->PO conversion, sourcing, PO changes
  receiving.py              lead times, partial/over/short/late receipts
  invoicing.py              PO and non-PO invoices, duplicates, FX, coding
  matching.py               tolerance engine, match results, hold ledger
  payments.py               pay runs, discount capture, applications
  pcard.py                  the third spend channel
  snapshots.py              AP aging, open commitment/GR-IR, supplier risk
  derived.py                p2p_cycle, spend, exception centre, funnel roll-up
  events.py                 the 18 planted events as multiplier matrices
sql/demo_questions.sql      the questions as runnable SQL
sql/snowflake/  sql/databricks/
docs/DATA_MODEL.md  EVENTS.md  DEMO_FLOWS.md  KPI_DEFINITIONS.md
data/small/  data/full/
```

`events.py` resolves every event to concrete targets — which suppliers, which
departments, which approvers — **once, before anything is drawn**, so all ten
loop stages agree on where the stories land. This is the pattern from `o2c` and
it is the difference between clustered anomalies and noise.

---

## 6. The eighteen events

All ten from §6 and all four from §7 survive, restated with parameters, plus four
the note is missing. Each gets a magnitude the validator asserts.

| # | Event | Shape | Causal link |
|---|---|---|---|
| 1 | Maverick spend | $12.8M non-PO where a contract existed; 68% in 2 departments | -> E14 budget |
| 2 | Invoice amount variance | 4.1% of PO invoices over tolerance | <- E4 |
| 3 | Quantity mismatch | 2.6% of lines; concentrated in 3 categories | -> E7 holds |
| 4 | Price drift vs contract | 14 suppliers, PO price above `contract_price` | root cause |
| 5 | Late receipts | OTD falls 94% -> 79% for 9 suppliers over 14 months | -> E9 |
| 6 | Slow invoice approval | avg 11.2d; one dept deteriorates to 24d from M-9 | -> E8 |
| 7 | Duplicate invoices | 412 suspected, **63 paid, $418K**; 4 archetypes | see §2.8 |
| 8 | Missed early-payment discount | $1.05M missed, 78% because of E6 | <- E6 |
| 9 | Late payments | 11.4% paid past due; worst 3 suppliers | <- E5, E7 |
| 10 | Supplier concentration | one category at 42/31/15/12 | tension with E18 |
| 11 | Shared bank accounts | 3 real clusters + 2 benign | fraud |
| 12 | Employee/supplier conflict | 4 real + 6 coincidental | fraud |
| 13 | PO splitting | 40 real cases + ~300 innocent co-occurrences | fraud |
| 14 | Threshold clustering | excess mass in $45–50K vs fitted lognormal | fraud |
| 15 | **GR/IR pile** | $18.7M received-not-invoiced, 62% aged >90d | *new — §2.1* |
| 16 | **Contract expiry wave** | 340 contracts expire in 90d, $41M of spend | *new* |
| 17 | **FX red herring** | one EUR supplier, apparent +9% is entirely rate | *new — §2.9* |
| 18 | **Consolidation opportunity** | 3 categories, 40+ suppliers, top-5 <35% | *new* |

Events 4 -> 2 -> 6 -> 8 -> 9 is the chain that carries the §17 demo. Build and
verify it first; everything else is decoration by comparison.

---

## 7. Target headline

```
Total spend TTM   Suppliers    Open payables   Past due     GR/IR accrual
$284.6M           2,400        $38.9M          $7.2M        $18.7M
+14.1% YoY        active 1,880                 18.5%        62% aged >90d

First-pass match   STP rate    Maverick spend   Missed discount   Req->cash
88.6%              71.4%       $12.8M           $1.05M            72.7 days
                                4.5% of spend                     +9.4d over 3 yrs
```

and the identified opportunity, which is the "so what":

```
Price variance vs contract     $2.1M
Maverick spend recoverable     $4.8M
Missed early-pay discounts     $1.05M
Duplicate payments recoverable $0.42M
Supplier consolidation         $3.4M
= Total opportunity           $11.8M   on $284.6M spend  (4.1%)
```

These are targets. The generator will land within a few percent; the validator
asserts each one is visible at the claimed magnitude before you present.

---

## 8. Build phases

| Phase | Output | Est. |
|---|---|---|
| 0 | `docs/DATA_MODEL.md` + `KPI_DEFINITIONS.md` — exact columns, keys, and §2.1/§2.2/§2.5 settled | 0.5d |
| 1 | Config, calendar anchoring, reference pools, supplier/category/org hierarchies, DOA and tolerance policy | 1.5d |
| 2 | Contracts and `contract_price` — the price truth everything else measures against | 1d |
| 3 | Requisitions: demand, approval routing, rejection, budget check | 1d |
| 4 | Purchasing: sourcing, req->PO conversion, PO changes, commitment | 1.5d |
| 5 | Receiving: lead times, partial/over/short, late deliveries, GR/IR | 1d |
| 6 | Invoicing: PO and non-PO, distributions, duplicates, FX | 1.5d |
| 7 | **Matching: tolerance engine, match results, hold ledger** | 1.5d |
| 8 | Payments: pay runs, discount capture, applications, AP aging | 1.5d |
| 9 | P-card, budget, supplier risk, snapshots | 1d |
| 10 | Derived: `fact_p2p_cycle`, `fact_spend`, exception centre, funnel | 1d |
| 11 | `validate.py` — integrity, subledger, waterfall, narrative | 1d |
| 12 | `emit_ddl.py`, demo questions as SQL, `run_questions.py` | 0.5d |
| 13 | `README.md`, `DEMO_FLOWS.md`, `EVENTS.md`, 15-minute script | 0.5d |

Roughly **15 days** — the longest of the five, because P2P has more document
stages than O2C and the match engine (Phase 7) is genuinely intricate. Phases
2–8 are the critical path and are strictly sequential. Write Phase 11
incrementally against partial output rather than saving it for the end; on both
the Meridian and Vantage builds the validator is what caught planted signals
being swamped by noise, and here it is also the only thing standing between you
and an AP subledger that does not add up in front of a controller.

### Acceptance criteria

The dataset is demo-ready when:

1. The commitment waterfall closes: PO commitment less every stage equals paid,
   to the cent — and total spend reconciles across all three channels.
2. At every month-end, `SUM(aging buckets) = SUM(open payables) = SUM(invoice
   gross - applications - credit memos - discounts taken)`, to the cent.
3. Every `fact_match_result` verdict is reproducible from the PO price, received
   quantity, invoiced quantity and the tolerance row that applied on that date.
   No exception exists that the underlying numbers do not justify.
4. Every invoice line resolves to a PO line and (for 3-way) a receipt line, with
   quantities that reconcile; every payment application resolves to both sides.
5. No invoice status contradicts its computed open amount.
6. `fact_p2p_cycle` milestone dates are monotonic for every chain.
7. Every enabled event passes its narrative check at the §6 magnitude.
8. Each fraud pattern returns its planted cases **ranked above** its control
   group, not merely returns them.
9. All demo questions return non-empty, non-absurd results via `run_questions.py`.

---

## 9. Summary of what changes from the design note

| Change | Why |
|---|---|
| Funnel split into two lanes; value waterfall on a PO cohort | §2.1 — as drawn the funnel widens with no explanation |
| GR/IR (received-not-invoiced) promoted to headline | §2.1 — the best CFO number in P2P, absent from the note |
| Eight contradictory headline numbers reconciled; match rate / STP / exception rate given separate definitions | §2.2 |
| `three_way_match` regrained to invoice line and **derived** from `dim_match_tolerance`; `match_type` 3-way / 2-way / non-PO added | §2.3 — the demo dies on the drill-down otherwise |
| `fact_invoice_hold` added, separate from match results | §2.3 — §12 mixes two taxonomies |
| `fact_payment_application` added | §2.4 — every AP metric depends on it |
| Payments 100K -> 61K | §2.1 — pay runs cover many invoices |
| Cycle time 31.4 -> 72.7 days, split into six legs by owner | §2.5 — 31 days is arithmetically impossible on Net 30 |
| Six events made causal; E4->E2->E6->E8->E9 chained | §2.6 — the root-cause scene must survive an unplanned drill |
| Fraud share 2% -> 0.4%, with control groups for every pattern | §2.7 — otherwise detection is a filter, not an analysis |
| `dim_approval_policy` added as effective-dated data | §2.7 — "below threshold" is unprovable without it |
| Duplicate invoices restructured into 4 archetypes; 63 of them paid | §2.8 — exact-duplicate numbers are not credible |
| `contract_price`, `dim_item`, `dim_exchange_rate`, `dim_supplier_status_history`, `fact_po_change`, `fact_invoice_distribution`, `fact_pcard_transaction` added | §2.3, §2.9 — several §14 questions have no table behind them today |
| Real trademarks replaced with invented suppliers | §2.9 — every sibling dataset is customer-safe |
| Calendar anchored to today; events as month offsets | §2.9 — the demo must not go stale |
| Direct spend, p-card and 6 legal entities added | §3 — indirect-only caps spend credibility at ~$60M |
| 4 events added (GR/IR, contract expiry, FX red herring, consolidation) | §6 |
| `fact_p2p_cycle` and `fact_spend` added as derived tables | §4 — keeps the executive page a single-table scan |
