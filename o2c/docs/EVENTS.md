# The fifteen planted events

Every number in the "measured" column comes from `src/validate.py` against
`data/full`. The validator asserts each one on every run, so this page cannot
drift from the data without the build going red.

Timing is expressed in **months relative to as-of**, never as absolute dates.
Regenerate next year and the story is still this year's story.

Scope is expressed as a **fraction of the population**, never as a count, so a
story stays proportionally visible at both tiers.

---

## Two events are chained, on purpose

```
Event 3  warehouse bottleneck
   └──> backorders
          └──> Event 14  expedited freight to recover the delivery date

Event 7  pricing leakage
   └──> Event 10  the customer disputes the invoices
```

Building the chains rather than two independent multipliers is what lets the
root-cause scene survive a drill-down nobody rehearsed. When the audience asks
"why is that account disputing so much", the answer is in the data.

---

## The events

| # | Event | Scope | Window | Measured at full tier |
|---|---|---|---|---|
| 1 | Quote conversion collapse | EMEA | −14 → 0 | conversion **25.2%** vs 40.6% elsewhere (1.61×) |
| 2 | Discount explosion | 1.2% of reps | −12 → 0 | worst reps at **2.23×** their region's median discount |
| 3 | Warehouse bottleneck | WH-07 | −10 → 0 | backorder rate **16.5%** vs 3.4% network; ship delay **4.9 days** vs 0.06 |
| 4 | Carrier deterioration | Meridian Freight | −8 → 0 | on-time **73.2%** vs 94% network (from a 94% baseline) |
| 5 | Invoice lag | West business unit | −9 → 0 | delivery-to-invoice **15.0 days** vs 6.8 company |
| 6 | Customer payment slowdown | 3rd largest account | −7 → 0 | days-to-pay **88** vs 51 median large account (1.71×) |
| 7 | Pricing leakage | 12% of contract lines, concentrated | −15 → 0 | **$442K** underbilled, **28%** of it in three accounts |
| 8 | Partial shipment problem | Hydraulic Pumps | −11 → 0 | split rate **1.71×** the rest; freight/revenue **1.10×** |
| 9 | Credit hold | 20% of Enterprise/Mid-Market | −6 → 0 | **$1.28M** on hold, **134** customers over limit |
| 10 | Dispute spike | largest global account | −5 → 0 | **$73.7K/month** disputed, ~7× its own baseline |
| 11 | Product shortage | 6 high-margin A-class SKUs | −8 → −3 | fill rate **39%** in the window |
| 12 | Returns spike | Electrical & Automation | −6 → 0 | return rate **3.20×** the rest |
| 13 | Duplicate billing | 0.4% of invoices | all history | **325** duplicate pairs, each linked to its original |
| 14 | Freight leakage | network-wide, backorder-weighted | −10 → 0 | freight/revenue **1.35×** baseline; expedite rate **3.25×** |
| 15 | Revenue trapped | West, Central, Export | −6 → 0 | **$7.6M** delivered but not invoiced |

---

## Six of them are causal, not stamped

If you tag rows after the fact, any cut that is not the exact cut you planned
falls apart, and the AI "discovery" is a magic trick with a visible wire. These
six emerge from the simulation:

| Event | Emerges from |
|---|---|
| 3 — warehouse bottleneck | order lines allocated first-come-first-served against a finite monthly supply, plus a pick queue that carries backlog day to day |
| 6 — payment slowdown | a per-customer days-to-pay distribution whose mean ramps across the window |
| 7 — pricing leakage | `invoice_line.unit_price` vs the price agreed on the order |
| 9 — credit hold | a running exposure ledger evaluated at order entry, order by order, against a limit that is capped while volume keeps growing |
| 11 — product shortage | available-to-promise exhaustion on specific SKUs |
| 15 — delivered not invoiced | a fat-tailed billing-lag distribution per business unit |

The other nine move a distribution rather than tagging a set of rows, which is
enough for them to survive being sliced.

### Event 9 in detail, because it is the subtlest

Credit limits grow with the business, so utilisation is roughly flat through
history. For the affected population the limit is **capped at 45%** of what
their grown volume would have earned them, from the freeze month onward. Nothing
is flagged: their exposure keeps rising, their limit does not, and orders start
failing the check on their own.

The second half matters as much. A credit manager can wave through a one-off
breach — and does, 82% of the time. They cannot wave through a limit that is
structurally below the customer's run rate, so for the frozen population the
override rate drops to 18% and a queue builds. Without that asymmetry the holds
either all clear (and there is nothing to see) or all cancel (and the
cancellation rate becomes absurd).

---

## Three places the design note's numbers do not survive the arithmetic

The design note asked for magnitudes that cannot be produced by a business of
this shape. Rather than inflate the dataset until they appeared, the numbers were
recomputed and the bands set to what a credible business actually generates.
Each is called out here so the demo script quotes the real figure.

### Credit holds: $4.7M asked, $1.28M delivered

$4.7M of blocked orders on a $128M book is **13 days of company-wide bookings**
sitting on hold simultaneously. Reaching it needs either a hold rate near 50%
across the whole customer base, or a frozen population representing 40% of
revenue. Both describe a business in the middle of a solvency event, not one
with a credit-control problem.

$1.28M is **3.6 days of bookings on 179 orders** — a real, actionable queue, and
still a strong headline: *"179 orders worth $1.3M cannot ship until Credit
clears them."*

### Dispute spike: $1.4M/month asked, $73.7K/month delivered

$1.4M of disputes a month requires an account billing at least $1.4M a month —
$17M a year, **13% of total revenue** from one customer. No distributor's largest
account is 13% of revenue, and if it were, that concentration would be the demo.

The event was moved from a single legal entity to the largest **global account**
(a dozen ship-to entities under one parent), which is both bigger and a better
drill-down target. $73.7K/month against its own ~$10K baseline is a **7× spike**,
which is what the story actually needs.

### Pricing leakage: implied millions, $442K delivered

Leaking $1.5M on a $104M invoiced book means roughly a third of all contract
lines are mispriced. That is not a stale price list, it is a broken one, and an
audience will ask why nobody noticed.

$442K is **0.6% of invoiced revenue** — squarely in the 0.5–3% band that price-
realisation work actually finds — with 28% of it in three named accounts, so the
drill-down still converges on a name.

### And one where the note gave no number

Perfect order rate landed at **45.9%**. There is no honest way to run 85% while
also carrying a warehouse bottleneck, a carrier at 73% on-time and a billing
backlog. The decomposition (Q25) is where the value is: on-time 67%, complete
75%, billed correctly 99%.

---

## Planted data-quality defects

The best of these is causal — the defect and the AR exception are the same
finding seen from two ends, rather than two unrelated oddities.

| Defect | Volume (full) | Downstream consequence |
|---|---|---|
| Orders raised with no PO number | 2,300 orders | become **Missing PO** disputes; $1.7M sits uninvoiced |
| Duplicate customer name variants | 14 customers | one legal entity, two AR balances; `duplicate_of_customer_id` is the answer key |
| Unapplied cash | 298 remittances, $1.46M | inflates AR until someone finds it |
| Duplicate invoices | 325 pairs | become **Duplicate Invoice** disputes |

---

## Turning an event off

Every event has an `enabled` flag in `config/scenario_base.yaml`. Setting it to
`false` removes the story from the data entirely — no residue, no half-signal —
and `validate.py` skips its checks. Useful when a prospect's own pain point is
one of these and you would rather not have a competing narrative on screen.
