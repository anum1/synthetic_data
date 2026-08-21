# Demo flows

Six flows. The first is the fifteen-minute headline run; the rest are the
follow-ups an audience actually asks for, each with the question, the tables it
touches, and the number it lands on.

Every figure is from `data/full` and asserted by `src/validate.py`. Question
numbers refer to `sql/demo_questions.sql`, which `src/run_questions.py` proves
all answer.

---

## Flow 1 — The fifteen-minute executive run

**The line that opens it:**

> *"We spent $282 million last year, up 15%. Are we getting more for it?"*

### Scene 1 — the tiles (30 seconds)

```
Total spend TTM   Open payables   Overdue      GR/IR accrual   Maverick
$282.2M           $36.1M          $11.0M       $15.3M          $13.8M
+15.1% YoY                        30% of AP    75% aged >90d   4.9% of spend
```

Say out loud that the tiles are **balances** and the waterfall is a **cohort**.
It costs five seconds and pre-empts the only question that can derail the whole
session. ([KPI_DEFINITIONS.md](KPI_DEFINITIONS.md) §1.)

### Scene 2 — where the money actually is (Q1, Q2)

```
PO-backed invoiced    $206.1M
Non-PO invoiced        $44.0M   <- $13.8M of this had a contract available
P-card / expense       $32.0M
= Total spend TTM     $282.2M
```

> *"A quarter of our spend never touched a purchase order. Some of that is
> unavoidable. $13.8M of it is spend we had already negotiated a price for."*

### Scene 3 — the commitment waterfall

```
PO commitment raised (TTM)             $235.5M
  - Cancelled / closed short             -$8.0M   RELEASED
  - Not yet received                    -$15.3M   IN FLIGHT
  = Received                            $136.6M
  - Received, never invoiced (GR/IR)    -$15.3M   ACCRUAL
  = Invoiced                            $124.3M
```

> *"$15.3M of goods we have taken delivery of and never been billed for. Three
> quarters of it is more than ninety days old. That is not a timing difference,
> it is an accrual nobody owns."*

### Scene 4 — the exception centre (Q12, Q16)

**32,165 open exceptions blocking $77.8M.** Sorted by value:

| Exception | Items | Blocked | Owner |
|---|---:|---:|---|
| GR/IR — received not invoiced | 22,334 | $48.6M | Receiving |
| Overdue invoice | 4,927 | $11.0M | AP Operations |
| Overdue receipt | 3,774 | $9.8M | Procurement |
| Price variance | 338 | $4.2M | Procurement |
| Quantity variance | 113 | $1.2M | Receiving |

### Scene 5 — the cycle (Q4)

```
Requisition -> cash          74.6 days

  ours          18.0 days   <- the only part we control
  supplier      36.5 days
  payment terms 20.1 days
```

### Scene 6 — drill to the supplier (Q6, Q25)

Sort suppliers by amount paid above contract. **Northbeam Solutions**, third
largest supplier, is at the top. Open Supplier 360:

```
Northbeam Solutions
  TTM spend        $14M+       growing
  On-time delivery falling
  First-pass match below average
  Paying above the contracted price
```

> *"Our third-biggest supplier is growing, delivering later, invoicing wrong and
> charging above the price we agreed. All four at once."*

### Scene 7 — the AI question

> *"How much would we have saved if Northbeam's POs had used the contracted
> price?"*

and then the one that makes the room sit up:

> *"Are there other suppliers with the same pattern?"*

**Fourteen suppliers, $0.89M on contract price alone — and $4.60M more in spend
that went off-contract entirely.** Two different problems, two different owners.
([KPI_DEFINITIONS.md](KPI_DEFINITIONS.md) §5.)

---

## Flow 2 — The discount that was never available (Q14)

The best causal story in the dataset, and it takes ninety seconds.

```
Terms 2/10 Net 30       -> the discount window closes on day 10
Invoice received -> approved, average 12.0 days
                        -> the window is already shut
```

**$912K of discount missed. 88% of it because approval landed after day 10.**

> *"We are not missing this because treasury pays late. We are missing it
> because the invoice is not approved until day twelve of a ten-day window.
> Fixing treasury does nothing. Fixing approval recovers most of $912K."*

At 2/10 Net 30 the implied annual rate is **37.2%** — `dim_payment_terms`
carries it as a column, so the CFO does not have to take your word for it.

---

## Flow 3 — Supplier 360 and the fragmented master (Q5)

> *"How much are we actually spending with Northbeam?"*

The supplier master has the same vendor under several records — `Northbeam
Solutions`, `Northbeam Sol`, `Northbeam-Solutions Co.`, `Northbeam
International`. Each has its own id, its own site and often its own bank
account, so spend fragments across all of them.

Answering needs `normalized_supplier_name`, `duplicate_of_supplier_id` or the
parent hierarchy. Show the fragmented total, then the consolidated one.

Roughly half the duplicate records **share the original's tax identifier**,
which is the strongest available evidence that two records are one vendor.

---

## Flow 4 — AP operations (Q12, Q13, Q15)

```
First-pass match   STP rate    Exception rate
92.3%              66.1%       15.7%
```

Three numbers, three denominators, deliberately different. Explaining why takes
fifteen seconds and buys enormous credibility with an AP audience
([KPI_DEFINITIONS.md](KPI_DEFINITIONS.md) §2).

Then break the match rate by type (Q13): three-way lines match differently from
two-way lines, because a two-way line has no receipt to check against. Then
ageing (Q15), then the hold ledger by owning team (Q12) — every exception has a
team that owns it, which turns a chart into a set of actions.

---

## Flow 5 — Fraud and risk (Q18–Q24)

Run these in order. Each one has a control group, so each one is an analysis
rather than a filter.

1. **Shared bank accounts (Q18).** Five accounts shared across suppliers. Sort
   by `distinct_parents` — the clusters spanning *different* corporate parents
   are the suspicious ones. The two-subsidiary cluster under one parent is
   legitimate. *Say so.* Volunteering the false positive is what makes the true
   positives credible.
2. **Duplicate payments (Q19, Q20).** Fuzzy match on parent + amount ±1% + 10
   days. 412 suspects; **51 were paid, $231K**.
3. **Threshold hugging (Q21).** 217 POs just below the approval limit against
   137 just above. Tested against the policy in force **on the PO date** — the
   limits changed 19 months ago, and testing against today's gets it wrong.
4. **PO splitting (Q22).** Same buyer, same supplier, ten days, individually
   under the limit, together over it. 39 real groups against a natural base rate.
5. **Employee/supplier conflicts (Q23).** Full-name matches ranked above
   surname-only collisions.
6. **Inactive suppliers still being bought from (Q24).** Uses
   `dim_supplier_status_history`, so the question is "was it inactive *on the PO
   date*", not "is it inactive now".

---

## Flow 6 — The FX red herring (E17)

A European supplier's USD spend is up 9% year on year. The category owner
escalates a price increase.

It is entirely the exchange rate. `dim_exchange_rate` moves EUR 9.0% across the
window and the supplier's EUR price list never changed.

> *"The analyst who checked the rate got this right. The one who read the USD
> trend did not. This is what a platform that keeps the transaction currency
> alongside the reporting currency is for."*

A good closing note: it is the one flow where the dashboard's first answer is
wrong, and the data is what corrects it.
