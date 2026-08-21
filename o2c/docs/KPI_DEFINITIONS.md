# KPI definitions

Settle these before building a single page. Every one of them is a place where
two people can produce two different numbers from the same data and both be
right, and an O2C demo has a finance audience — the hardest room there is for a
number that moves depending on who built the chart.

---

## 1. The funnel is a booking cohort. The tiles are balances. They are not the same population.

This is the most important definition in the dataset.

**The funnel / waterfall** answers: *of the value we booked in a period, how much
has reached each stage by now?* It is filtered on `fact_o2c_cycle.order_date`,
never on the stage's own date. Every stage value is carried on the order's row,
so the whole waterfall is a set of `SUM`s over one table.

**The KPI tiles** answer: *what is the balance today, and what flowed this
period?* Open AR is a balance at as-of across invoices of every vintage. Cash
collected in a period includes collections against invoices booked years ago.

Mixing them produces the classic dead end:

> "DSO is 52 days and terms average 36. Of course last quarter's bookings aren't
> cash yet. What is actually wrong here?"

**Rule:** label tiles as balances (`Open AR as of 2026-07-31`) and keep them
visually separate from the funnel. Never put them in the same row.

### Splitting the gap

The gap between booked and collected is not one thing. `fact_o2c_cycle` carries
each stage as its own column so the waterfall can be classified:

| Stage column | Disposition | Meaning |
|---|---|---|
| `cancelled_net_usd` | **LOST** | never coming back |
| `not_yet_shipped_usd` | **AT RISK** | backorder or credit hold |
| `in_transit_usd` | **TIMING** | in a truck |
| `delivered_not_invoiced_usd` | **LEAKAGE** | goods gone, no invoice raised |
| `credited_net_usd` | **LOST** | credit notes and returns |
| `open_ar_net_usd` | **TIMING** | invoiced, not yet collected |
| `collected_net_usd` | **CASH** | done |

At full tier the trailing-twelve-month cohort reads:

```
Booked $128.4M -> Collected $88.1M
  LOST     $6.2M   (cancellations $2.5M, credits and returns $3.7M)
  LEAKAGE  $7.5M   (delivered, never invoiced)
  AT RISK  $7.4M   (backordered or on credit hold)
  TIMING  $19.2M   (in transit $1.9M, open AR $17.4M)
```

"$40M has not converted" is not a finding. "**$6.2M is gone, $7.5M was never
billed, and $26.6M is still moving**" is.

### The waterfall closes by construction

```
booked - cancelled                = net booked
net booked - shipped              = not yet shipped
shipped - delivered               = in transit
delivered - invoiced              = delivered, not invoiced
invoiced - credited               = net invoiced
net invoiced - collected          = open AR on the cohort
```

`validate.py` asserts the residual is under $1 on $128M. Each stage is also
clamped to the one above it, so no order can show more delivered than shipped.

---

## 2. Net of tax and freight, everywhere in the funnel

Every stage in `fact_o2c_cycle` is **net**: goods value, excluding tax and
freight. Cash and credit notes land against invoice **totals**, so they are
converted to the net basis by each invoice's `net_amount / total_amount` ratio
before entering the funnel.

AR balances and the ageing matrix run on invoice **totals** — that is what the
customer actually owes. Two measures, both correct, both labelled.

`Revenue` = invoiced, net of credit memos. Not bookings, not cash, not shipped.

---

## 3. The AR ledger

```
open_amount = total_amount
            - allocated cash        (fact_payment_allocation)
            - credit memos          (fact_credit_memo)
            - early-payment discount taken
```

The last term catches people out. A customer on 2/10 Net 30 who pays early
short-pays by the discount and the invoice is **closed**. Treat the shortfall as
a receivable and every discounted invoice leaves a permanent 2% residue; three
years later that residue is the entire 90+ ageing bucket.

**Invoice status is derived, never drawn:**

| Status | Condition |
|---|---|
| `Written Off` | past the write-off threshold and never going to pay |
| `Disputed` | open, with an unresolved dispute against it |
| `Paid` | `open_amount <= 0.01` |
| `Overdue` | open and `due_date < as_of` |
| `Partially Paid` | some cash applied, balance remains |
| `Issued` | open, not yet due |

Disputed beats Overdue deliberately. An invoice that is late *because it is
being argued about* belongs to the disputes queue, not the collections queue —
counting it in both chases the same money twice.

**Written-off invoices leave AR.** They are bad debt, reported separately.
Carrying them makes every collections metric wrong in the same direction.

`validate.py` asserts, at as-of: ageing buckets = ledger open AR = the tile,
to the cent.

---

## 4. DSO

```
DSO = open AR / (trailing-12-month billings / 365)
```

Billings are invoice **totals**, so the numerator and denominator are on the same
basis. Full tier: **52.4 days**.

The count-back method gives a different (usually lower) number on a growing book.
If you show both, label them — do not let one page use each.

**Demo question 20** ("improve DSO by 5 days — how much cash?") is a simulation,
not a query. It is answered as `5 × average daily billings` with the assumption
stated on screen: **$2.06M** at full tier.

---

## 5. On-time: two different questions

| Measure | Against | Answers |
|---|---|---|
| `is_on_time_carrier` | the carrier's quoted transit | did the carrier do its job? |
| `is_on_time_promise` | the date the customer was given | did we do ours? |

Promise performance also absorbs warehouse queues, backorders and credit holds,
so it is always the lower number (94% vs 67% at full tier). Conflating them is
how a logistics page ends up arguing with a customer-service page.

Carrier scorecards use `is_on_time_carrier`. Customer-facing service levels and
the perfect-order rate use `is_on_time_promise`.

---

## 6. Perfect order rate

The product of four flags, all of which exist as columns on `fact_o2c_cycle`:

```
is_perfect_order = is_on_time (to promise)
                 & is_complete (nothing backordered)
                 & is_billed_correctly (no underbilling, no duplicate)
                 & is_undamaged
```

Full tier: **45.9%**, trending down from 57% three years ago.

That is low, and it is meant to be. A distributor carrying a warehouse
bottleneck, a failing carrier and a billing backlog does not run at 85%. The
value of the metric here is the decomposition — Q25 shows which component is
breaking it, and the answer changes over the timeline.

---

## 7. Quote conversion

Reported **two ways**, always labelled:

- **By count**: won quotes / decided quotes = **39.4%**
- **By value**: won quote value / total quoted value ≈ 55%

Big deals win more often, so the two differ by design. Quoting one and captioning
it with the other is a mistake the design note made twice.

Open quotes (still inside their validity window) are excluded from both — they
have not been decided yet, and including them understates the rate by whatever
happens to be in flight.

---

## 8. Backorder and fill rate

- **Fill rate** = allocated quantity / ordered quantity, on live order lines
  (excluding cancelled and credit-held, which never reach allocation).
- **Backorder rate** = 1 − fill rate.

Both are quantity-weighted. A line-count version runs several points worse
because short lines cluster in high-volume SKUs; pick one and label it.

---

## 9. Currency

Fixed budget rate, held flat across the whole timeline. Every money column exists
in USD; the four headline facts also carry a `_local` amount and the rate used.

This is deliberate. A floating rate would put FX movement inside the
bookings-to-cash waterfall, and "where did the money go" would acquire an answer
nobody in the room wants to discuss. Payment currency is forced to match invoice
currency for the same reason.

---

## 10. Price variance vs contract compliance

Two separate measures, and rolling them together produces a two-sided number
nobody can act on.

| Column | Baseline | Question |
|---|---|---|
| `price_variance_usd` | the price on the **order** | did we bill what we agreed? |
| `contract_variance_usd` | the **contracted** price | did we agree what we contracted? |

`underbilled_amount_usd` is the positive side of the first — the money left on
the table. Full tier: **$442K**, 28% of it in three accounts.
