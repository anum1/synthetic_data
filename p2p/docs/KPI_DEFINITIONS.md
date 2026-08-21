# KPI definitions

The measurement decisions, settled once. Three of these are the ones an audience
will try to catch you on, and they are first.

---

## 1. The tiles are balances. The funnel is a cohort. Say so.

The KPI tiles report **balances at as-of** (open payables, GR/IR accrual) and
**flows over the trailing twelve months** (total spend, missed discount). The
commitment waterfall reports a **cohort**: of the PO commitment raised in the
last twelve months, how much has reached each stage *by now*.

They are different populations and they will not tie to each other. Say that out
loud in the first thirty seconds — it costs five seconds and pre-empts the one
question that can derail the session.

- Balance tiles are labelled `... as of <date>`.
- Cohort bars filter on `purchase_order.po_date`, never on the stage's own date.
- The generator carries `committed_amount` down every downstream table so each
  bar is a `SUM`, not a six-table join.

---

## 2. Match rate, straight-through rate and exception rate are three metrics

They have three different denominators and three different numbers. If all three
come out at 91%, the first person who divides differently catches you.

| Metric | Numerator | Denominator | Value |
|---|---|---|---:|
| **First-pass match rate** | PO invoices passing every tolerance check at the first attempt | PO-backed invoices only | **92.3%** |
| **Straight-through rate** | Invoices reaching payment with no hold and no manual touch | *All* invoices | **66.1%** |
| **Exception rate** | Invoices that ever carried a hold | *All* invoices | **15.7%** |

Straight-through is much lower than first-pass because non-PO invoices always
need coding and a cost-centre owner's approval — they can never be
straight-through, and they are a sixth of spend.

An auto-write-off counts as a first-pass match. Under the tolerance cap
(`total_variance_cap_usd`, $250 by default) AP writes the difference off without
a human touching it, which is what real AP departments do. Excluding those would
inflate the exception rate with rows nobody ever works.

---

## 3. Cycle time: six legs, and only three of them are ours

Requisition-to-cash is **74.6 days**. Quoting a single number invites the
response "so what". The split is the point:

| Leg | Days | Owner |
|---|---:|---|
| Requisition created → approved | 2.6 | **Us** |
| Requisition approved → PO issued | 4.4 | **Us** (aggregation into a PO takes time) |
| PO issued → first receipt | 23.8 | Supplier lead time |
| Receipt → invoice received | 13.5 | Supplier billing lag |
| Invoice received → approved | 12.1 | **Us** |
| Approved → paid | 19.6 | Payment terms + pay-run calendar |

Rolled up by owner, and the three parts sum to the total exactly:

```
74.6 days  =  18.0 ours  +  36.5 supplier  +  20.1 terms
```

> *"Seventy-five days. Thirty-six are the supplier's, twenty are the contract.
> **Eighteen are ours** — and that eighteen is where the money is."*

`fact_p2p_cycle` carries `days_controllable`, `days_supplier` and `days_terms`
precomputed so this split is one column, not a case statement repeated in four
dashboards. A two-way line has no receipt, so its supplier leg is measured PO to
invoice end to end rather than through a receipt that does not exist — otherwise
the components would not add up to the total, and `validate.py` asserts that they
do.

---

## 4. Spend

**Total spend** is invoiced value plus card value, across three mutually
exclusive channels that sum to the total:

```
PO-backed invoiced + Non-PO invoiced + P-card = Total spend
```

Credit memos are excluded from spend (they are settled against the invoice they
correct). Cancelled POs contribute nothing — commitment is released, not spent.

**Spend class** is a mutually exclusive four-way split on `fact_spend`:

| Class | Meaning |
|---|---|
| `Contracted on PO` | On a PO, and a contract covered that supplier × category |
| `Non-contracted on PO` | On a PO, no contract existed |
| `Maverick` | **A contract existed and was bypassed** — off-PO despite coverage |
| `Unmanaged` | Off-PO, and no contract existed either |

**Maverick is derived, never flagged.** An invoice or card transaction is
maverick when `contract_price` contains a row for that supplier and category and
the spend did not go through a PO. Anyone can reproduce that definition from the
data, which a boolean column would not allow.

---

## 5. Contract price variance vs off-contract premium

Two different leaks, two different owners, two different columns. Adding them
together produces a "price variance" no procurement lead would recognise.

| Column | Meaning | TTM |
|---|---|---:|
| `contract_price_variance_usd` | We used the contract and paid **above** the agreed price | $0.89M |
| `off_contract_premium_usd` | A contract existed and we bought at spot instead | $4.60M |

The first is a supplier-relationship problem (Event 4). The second is a
compliance problem. They belong on different slides.

---

## 6. GR/IR — received, not invoiced

Goods receipted against a PO line with no invoice raised against them:

```
gr_ir_amount_usd = (quantity_received - quantity_invoiced) * unit_price
```

**$15.3M, 75% of it aged past 90 days.** This is a balance-sheet accrual, not a
timing difference, and it is the mirror image of the "delivered not invoiced"
number in the sibling O2C dataset. Two-way lines are excluded: they never have a
receipt, so they cannot be received-not-invoiced.

---

## 7. The AP subledger identity

```
open_amount = gross_amount
            - SUM(payment_application.applied_amount)
            - SUM(payment_application.discount_taken)
```

`validate.py` asserts this to the cent on every invoice, and asserts that the
month-end ageing snapshot sums to the same number as the ledger at that date.
Both currently pass with a maximum residual of $0.0000.

**Days past due** is measured against `due_date` at as-of, for open invoices
only. Credit memos never sit open.

---

## 8. Early-payment discount

An invoice is eligible when its terms carry one (`discount_percent > 0`). It is
**captured** only if the invoice was *approved* before `discount_due_date`.

```
discount_missed_usd    = available where nothing was taken
missed_due_to_approval = 1 when approval landed after the window closed
```

**$912K missed, 88% of it because approval landed after day 10.** That is not
treasury paying late — the window was already shut when the invoice was
approved. Events 6 and 8 are the same event.

---

## 9. Delivery performance

`is_on_time` is set on the PO line when the actual receipt date is on or before
the expected date (PO date + category lead time). Lead time and lateness are
properties of the **delivery**, so they are drawn per purchase order, not per
line — a single shipment arrives once.

Company-wide on-time runs at 94%. The nine suppliers carrying Event 5 fall from
94% to 79% across their window; nine suppliers out of 2,400 cannot move the
company average, which is exactly why the question has to be asked per supplier.

---

## 10. Approval thresholds are effective-dated

`dim_approval_policy` carries two versions of every role × entity limit: the
original, and the revision that lifted every limit 25% nineteen months ago.
`fact_purchase_order.approval_threshold_usd` records the limit **in force on the
PO date**.

An analyst who ignores the effective dating and tests every PO against today's
limit gets the threshold-clustering answer wrong. That is a feature.
