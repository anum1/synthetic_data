# Demo flows

**Meridian Global Industries — Supply Chain Control Tower**

Six dashboard pages, one scripted flow, and 30 questions that the dataset can
actually answer. Every number quoted below is **measured from the small tier**,
not written from intent — regenerate and run `src/run_questions.py` to
reproduce them. Absolute figures move a little with the as-of date; the
relationships between them are what the events guarantee.

---

## The headline

At the as-of date the executive row reads:

| KPI | Value |
|---|---:|
| Inventory value YoY | **+12.8%** |
| Unit fill rate | 96.9% |
| OTIF | 90.1% |
| Stockout rate | 3.4% |
| Forecast accuracy (ML, 1-month) | 87.4% |
| Days of supply | 80 |

Inventory is up nearly 13% and service has not improved. That divergence is the
whole demo — every flow below is a different way of answering *why*.

---

## The scripted flow

### Step 1 — "At first glance this looks healthy"

Open the Executive Control Tower. Inventory is up, revenue is up, and the
service KPIs are only slightly soft. Nothing on this page tells you where to
look, which is exactly the point.

### Step 2 — "Why are stockouts up when inventory is up 13%?"

**Q3** and **Q5**. The inventory growth is not where the demand is. Event 3 put
230 slow-moving C-class SKUs into over-forecast, Event 8 added 40% safety stock
to 300 A-class SKUs, and Event 14 left 60 end-of-life SKUs holding stock against
demand that has fallen away. Three separate causes that aggregate into one
misleading number.

### Step 3 — "Which suppliers are deteriorating?"

**Q7** returns the answer unambiguously:

| Supplier | On-time before | On-time recent | Change |
|---|---:|---:|---:|
| **SUP-104** Baltic Metalworks Co. | 95.5% | 69.6% | **−25.9 pts** |
| SUP-175 Foundry Nine GmbH | 91.6% | 79.2% | −12.4 pts |
| SUP-186 Ardent Fabrication | 96.5% | 86.2% | −10.3 pts |

The gap between first and second place is the drill-down target.

### Step 4 — Drill into SUP-104

Lead time moved **18 → 29 days**; on-time fell **95% → 71%** over the three-month
disruption window, and recovery is deliberately partial — it does not snap back.

### Step 5 — "What else is exposed to SUP-104?"

**Q8** and **Q28**. SUP-104 is the only supplier in the business scored
**Critical**, supplying **6 critical single-sourced SKUs** with **7**
single-sourced SKUs in total. There is no alternate source for any of them.

| Supplier | Risk | Score | 90-day spend | Critical SKUs | Single-sourced |
|---|---|---:|---:|---:|---:|
| SUP-101 Torvald Industrial | High | 61.4 | $278,819 | 2 | 5 |
| **SUP-104 Baltic Metalworks** | **Critical** | **100.0** | $95,194 | **6** | **7** |
| SUP-117 Monarch Valves | High | 65.7 | $150,558 | 0 | 3 |

Note that SUP-104 is *not* the largest spend. Ranking on spend alone hides it —
that is the argument for the exposure index.

### Step 6 — The data-quality reveal

**Q30**. Ask the same question grouped on the supplier name as it appears on the
transaction, and the worst supplier in the business disappears:

| Grouping | Shown as | Deliveries | Late |
|---|---|---:|---:|
| master id | **SUP-104** | 2,299 | **224** |
| raw name | `Baltic Metalworks Co.` | 450 | 53 |
| raw name | `Baltic  Metalworks  Co.` | 492 | 48 |
| raw name | `Baltic Metalworks Co` | 461 | 45 |
| raw name | `Baltic Metalworks Co.` (trailing space) | 469 | 42 |
| raw name | `BALTIC METALWORKS CO.` | 427 | 36 |

224 late deliveries is a problem someone owns. Five rows of 36–53 are noise
nobody escalates. Same data, two answers, one of them wrong.

### Step 7 — The geographic drill

**Q17** ranks carriers globally and C-07 looks unremarkable — 89.5% on-time
against a 90.4% field. **Q18** adds sub-region and the picture changes:

| Carrier | Sub-region | On-time | Shipments |
|---|---|---:|---:|
| **C-07** | **Northeast** | **79.0%** | 1,083 |
| C-09 | Midwest | 89.2% | 1,144 |
| C-06 | Southwest | 89.4% | 1,324 |

The degradation is real and concentrated. An aggregate view cannot find it,
which is a good argument for the drill path rather than a flaw in the data.

---

## The six pages

| Page | Built from | Questions |
|---|---|---|
| 1 — Executive Control Tower | all facts, `fact_supply_chain_risk` | Q26, Q28, Q29 |
| 2 — Inventory | `fact_inventory_snapshot` | Q1–Q5, Q22, Q23 |
| 3 — Supplier Performance | `fact_supplier_delivery`, `fact_purchase_order` | Q6–Q10, Q21, Q24 |
| 4 — Demand & Forecast | `fact_forecast`, `fact_demand_signal` | Q11–Q15 |
| 5 — Logistics | `fact_shipment` | Q16–Q20 |
| 6 — Root Cause / AI | everything | Q25, Q27, Q30 |

**Every page touching `fact_inventory_snapshot` must filter `snapshot_grain`.**
The table holds weekly history and a daily recent window; summing across both
double-counts every inventory measure. Page 2 should filter `= 'D'` for the
current view and `= 'W'` for the trend.

---

## The 30 questions

Runnable SQL is in [`sql/demo_questions.sql`](../sql/demo_questions.sql).
Portable ANSI — verified on DuckDB, written to run unchanged on Snowflake and
Databricks. "Today" is always derived from the data, so they stay correct after
a regenerate.

```bash
python3 src/run_questions.py --tier small
```

```bash
python3 src/run_questions.py --tier small --only 7,18,28,30
```

| # | Question | Finds |
|---|---|---|
| 1 | Which products have excess inventory? | Event 3 |
| 2 | Which products are most likely to stock out? | Events 1, 7 |
| 3 | Where is inventory growing faster than demand? | Events 3, 14 |
| 4 | Which warehouses have the lowest inventory turns? | Events 3, 12 |
| 5 | Which products have inventory but declining demand? | Events 9, 14 |
| 6 | Which suppliers are responsible for most late POs? | Event 1 |
| 7 | Which suppliers have deteriorating performance? | **Event 1 — SUP-104 −25.9 pts** |
| 8 | Which critical products depend on a single supplier? | Event 10 |
| 9 | Which suppliers have high spend and high risk? | risk layer |
| 10 | Which suppliers have increasing defect rates? | **Event 5 — SUP-137 1.5% → 7.0%** |
| 11 | Which products have the largest forecast bias? | Events 3, 7 |
| 12 | Where is forecast accuracy deteriorating? | Events 2, 7 |
| 13 | Which categories are systematically under-forecast? | **Event 7 — Industrial Components −5.2%** |
| 14 | Which planner overrides improved forecast accuracy? | Event 15 |
| 15 | Which products have highly volatile demand? | XYZ classification |
| 16 | Why did OTIF decline? | Events 4, 13 |
| 17 | Which carriers are causing the most delays? | Event 4 (weakly — see Q18) |
| 18 | Which routes have increasing transit times? | **Event 4 — C-07 Northeast 79.0%** |
| 19 | Which regions have the highest freight cost? | Events 4, 6 |
| 20 | What is driving expedited shipping? | Events 2, 6 |
| 21 | Which suppliers are causing stockouts? | Events 1, 5 |
| 22 | Which products have high demand but low supply? | Events 1, 7 |
| 23 | Which inventory is tied to poor forecast accuracy? | Events 3, 7 |
| 24 | Which supplier issues have the greatest revenue impact? | Events 1, 5 |
| 25 | Which products have simultaneous supply and demand risk? | Events 1, 10 |
| 26 | What are the top 10 supply-chain risks? | risk layer |
| 27 | Where should we invest to improve service levels? | Events 1, 7 |
| 28 | Which problems should we address first? | **Event 10 — SUP-104 Critical** |
| 29 | What is causing working capital to increase? | Events 3, 8 |
| 30 | Does grouping on the raw supplier name change the answer? | **data quality — 224 late split five ways** |

### Two questions that deliberately under-deliver

**Q17** and **Q26** are the weaker ones, and both are informative about the
model rather than broken.

Q17 ranks carriers globally, where C-07's Northeast problem is diluted to near
invisibility — it only becomes findable in Q18. That is what a geographically
concentrated failure looks like in real data.

Q26 ranks the monthly risk fact rather than the supplier scorecard, so the
answer moves month to month and SUP-104 does not always top it. **Q28** is the
executive question, and it puts SUP-104 at Critical every time.
