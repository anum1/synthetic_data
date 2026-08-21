# Demo flows

Nine flows. The first is the fifteen-minute headline run; the rest are the
follow-ups an audience actually asks for, each with the question, the tables it
touches, and the number it lands on.

Every figure below is from `data/full` and is asserted by `src/validate.py`, so
if the build is green these numbers are what will be on screen.

---

## Flow 1 — The fifteen-minute executive run

**The line that opens it:**

> *"We booked $128.4M in the last twelve months. $88.1M has become cash. Let's
> find the other $40M."*

### Scene 1 — the tiles (30 seconds)

```
Bookings TTM   Collected     Open AR      Overdue AR    DSO      Perfect order
$128.4M        $88.1M        $21.6M       $8.3M         52 days  45.9%
+10.1% YoY                                38% of AR              -11pt vs 3yr ago
```

Say out loud that the tiles are **balances** and the funnel is a **booking
cohort**. It costs five seconds and it pre-empts the only question that can
derail the whole session. ([KPI_DEFINITIONS.md](KPI_DEFINITIONS.md) §1.)

### Scene 2 — the waterfall (Q1)

```
Booked                    $128.4M
  - Cancelled               $2.5M   LOST
  - Not yet shipped         $7.4M   AT RISK
  - In transit              $1.9M   TIMING
  - Delivered not invoiced  $7.5M   LEAKAGE
  - Credits and returns     $3.7M   LOST
  - Open AR on the cohort  $17.4M   TIMING
  = Collected              $88.1M
```

> *"$6.2M is gone. $7.5M we shipped and never billed. $26.6M is still moving.
> Only one of those three is an emergency."*

### Scene 3 — the exception centre (Q4, Q22)

**9,521 open exceptions blocking $21.7M.** Sorted by value:

| Exception | Items | Blocked | Avg age | Owner |
|---|---:|---:|---:|---|
| Delivered not invoiced | 5,572 | $7.6M | 185 d | Billing |
| Overdue invoice | 1,836 | $6.7M | 135 d | AR Collections |
| Missing PO | 293 | $1.7M | 445 d | Customer Service |
| Unapplied cash | 298 | $1.5M | 531 d | AR Collections |
| Credit hold | 179 | $1.3M | 51 d | Credit |

The unapplied-cash row is worth pausing on: **$1.5M of the receivable is money
we already have** and never applied to an invoice.

### Scene 4 — billing (Q5)

Delivered-not-invoiced by business unit. West, Central and Export carry it;
West's delivery-to-invoice lag is **15.0 days** against a company average of 6.8.

### Scene 5 — collections (Q16, Q21)

The ageing matrix. Click **90+** → customer → invoices → orders → shipments. Five
clicks, five tables, no dead ends.

### Scene 6 — customer 360 (Q30)

The largest account, all the way down:

```
Booked  ->  Delivered  ->  Invoiced  ->  Collected  ->  Open AR
```

### Scene 7 — root cause (Q18, Q19)

> *"This account's overdue balance is concentrated in invoices carrying pricing
> disputes — and the disputes trace to invoice lines billed 7–12% below the price
> agreed on the order."*

Both halves are in the data. `fact_invoice_line.underbilled_amount_usd` is the
money; `fact_dispute.dispute_reason = 'Pricing Discrepancy'` is the argument.
The disputes were **generated from** the variance, so the chain holds however the
audience slices it. ([EVENTS.md](EVENTS.md), Event 7 → Event 10.)

### Scene 8 — action (Q17, Q20)

Invoices over 60 days, ranked. Then the arithmetic that closes the meeting:

> *"Five days of DSO is $2.06M of cash."*

---

## Flow 2 — Where the cash conversion cycle went (Q2)

The process-time bridge by quarter. Each stage is a column on `fact_o2c_cycle`,
so the whole bridge is one `GROUP BY`.

```
Quote -> Order -> Ship -> Deliver -> Invoice -> Cash
```

Watch `delivery_to_invoice` climb through the last four quarters. That is
Event 5 and Event 15 arriving together.

---

## Flow 3 — The sales conversation (Q6, Q7, Q8, Q9)

- **Q7** — three reps discounting at **2.23× their own region's median**. Measured
  against the region, not the company, so a regional pricing policy does not read
  as a rogue rep.
- **Q8** — EMEA conversion at **25.2%** against 40.6% elsewhere. Twelve months ago
  they were level.
- **Q6** — the reps with high bookings and thin margins are not the same people.
  That contrast is the point.

---

## Flow 4 — The fulfilment conversation (Q10, Q11, Q26)

**WH-07**: backorder rate **16.5%** against a network 3.4%, and shipments leaving
**4.9 days** late against a network 0.06.

Neither number is stamped on. Order lines are allocated first-come-first-served
against a finite monthly supply, and the pick queue carries its backlog day to
day. Slice it by customer, by month, by product — it holds.

**Q26** finds the six high-margin SKUs that ran dry, and what the unfilled demand
was worth.

---

## Flow 5 — The logistics conversation (Q13, Q14, Q15)

**Meridian Freight**: on-time **73.2%** against a 94% network, across every
service level it operates.

Then the cost (Q14): expedite rate **3.25×** its baseline and freight running
**1.35×** its normal share of revenue. Ask where the expediting is concentrated —
it is on the backorders coming out of WH-07. Event 3 causes Event 14, and the
data says so.

---

## Flow 6 — The credit conversation (Q23, Q24)

**$1.28M of orders cannot ship** because Credit has not cleared them, and **134
customers are over their limit**.

Q24 is the one the design note could not have supported: exposure and utilisation
**by month**. The spike has a shape, and the shape is a limit that stopped moving
while volume kept going.

---

## Flow 7 — Billing quality (Q19, Q28, Q29)

- **Q19** — $442K underbilled, 28% of it in three accounts.
- **Q28** — 325 invoices billed twice, each linked to its original.
- **Q29** — off-contract spend by segment, with the discount gap beside it.

---

## Flow 8 — The data-quality flow

Good for a technical audience, and a genuinely better story than it sounds,
because the defects have consequences rather than just being wrong:

1. **2,300 orders with no PO number** → become *Missing PO* disputes → **$1.7M**
   sitting uninvoiced, average age 445 days.
2. **14 customers spelled two ways** — one legal entity, two AR balances.
   `duplicate_of_customer_id` is the answer key.
3. **$1.5M of cash received and never applied.**

> *"Three data problems. $3.2M of the receivable, and none of it is a collections
> problem."*

---

## Flow 9 — Ask the AI

The thirty questions in [`sql/demo_questions.sql`](../sql/demo_questions.sql) are
the ones worth putting to an NLQ layer, because each has a checkable answer.
`src/run_questions.py` runs all thirty and proves they return rows before you
present.

The four that make the strongest impression, because each needs several tables
and a definition:

1. *Where is revenue getting trapped in our O2C process?*
2. *Which customers represent the greatest cash-collection risk?*
3. *Where are invoice-to-order pricing discrepancies occurring?*
4. *If we improve DSO by 5 days, how much cash would we release?*

---

## Preparing

```bash
python3 src/generate.py --tier full --formats parquet
python3 src/validate.py --tier full
python3 src/run_questions.py --tier full --quiet
```

75 assertions and 30 questions. If all three are green, every number on this page
is what the audience will see.

If a prospect's own pain point happens to be one of the fifteen events, turn it
off in `config/scenario_base.yaml` and regenerate — the story leaves the data
completely rather than lingering as a half-signal.
