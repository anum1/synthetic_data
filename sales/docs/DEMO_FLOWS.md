# Demo flows

15 dashboard flows the dataset supports, plus the single executive story that
strings the best of them together.

Each flow names the config block that drives it. Change that block and
regenerate, and the flow changes with it — that is the "tweaking" property:
you are not editing dashboards, you are editing the business.

Headline numbers below are from the **full** tier with the shipped base
scenario. They move with the as-of date, so treat them as the shape of the
answer rather than exact figures.

> **Current headline:** revenue **+10.1%** YoY, gross profit **−7.3%**,
> margin **21.1% → 17.8%** (-3.3 pts). Europe is the largest profit
> decline of **$18.2M**.

---

## The executive story (use this one)

Nine steps, roughly twelve minutes. Do not show all fifteen flows.

| Step | Question | Where it lands |
|---|---|---|
| 1 | "How are we doing?" | Revenue up 10.1%, profit down 7.3% |
| 2 | "Why is profit falling while revenue grows?" | Five drivers, ranked |
| 3 | "Where?" | Europe → Germany → Electronics → Laptops |
| 4 | "Is it price or cost?" | Global Components, +12% unit cost from April |
| 5 | "Are we also losing sales we could have made?" | 6 laptop SKUs, 42% stockout rate |
| 6 | "Which customers moved?" | GlobalTech Corp, orders −26% |
| 7 | "What is that $2.8M spike?" | One-off enterprise deployment, not a trend |
| 8 | "What happens if nothing changes?" | Latest Forecast: −$7.1M profit vs plan |
| 9 | "What if we act?" | Recovery Scenario: +$5.1M back |

The arc goes **what happened → why → what next → what should we do**.

---

## The 15 flows

### 1. Executive KPI and variance
*Config: whole scenario.* KPI row (revenue, gross profit, margin, units,
customers, forecast vs plan) with YoY, YTD/PYTD, MoM and QoQ. The point is the
divergence: revenue arrow up, profit arrow down.

### 2. Profit bridge / waterfall
*Config: all events.* Decompose prior-year profit to current-year profit
through volume, price, mix, discount, COGS, returns. Every bar has a named
cause in the data. Because money is `DECIMAL(18,2)`, the bars sum exactly to
the KPI tile.

### 3. Geographic drill-down and map
*Config: `region_margin_erosion`.* Global → Region → Country → State → City →
Location, with `latitude`/`longitude` for map marks. Europe is the largest
profit decline; drilling converges on Germany → Electronics → Laptops.

### 4. Product hierarchy and new-product cannibalisation
*Config: `product_launch`.* Category → Subcategory → Brand → Family → Product →
SKU (29 subcategories, 68 families, 201 products, 2,500 SKUs). Nimbus Air N4 launches with zero prior sales and takes 28k units, while
the incumbent N3 falls 5.8% against peer laptops at +20.4% — a 26-point gap.
The question "incremental or cannibalising?" has a defensible answer.

### 5. Customer 360 and concentration risk
*Config: `customer_contraction`.* Top-N concentration, segment/industry/tier
hierarchy, revenue and margin per account. GlobalTech Corp is ~4% of revenue
and its order share drops 26% while peer strategic accounts grow.

### 6. Supplier cost and quality scorecard
*Config: `supplier_cost_shock`.* Per-product unit cost for Global Components
rises 14% from April while every other supplier group stays within 0.1%.
Traces supplier → product → margin → profit.

### 7. Returns and defect analysis
*Config: `quality_failure`.* Return rate for the affected supplier group goes
1.96% → 5.61%, defect rate 2.05% → 9.23%. Returns join back to the exact order
line that produced them, so supplier → product → customer → profit is one path.

### 8. Inventory health and lost sales
*Config: `inventory_shortage`.* Six laptop SKUs go from 0% to 42% stockout
rate; days of supply falls 32.5 → 8.7. Unaffected SKUs stay at 0%. This is what
separates "customers stopped wanting it" from "we had nothing to sell".

### 9. Promotion effectiveness and discount leakage
*Config: `promotion_surge`.* Electronics units +40% during the campaign,
discount rate +6.1 pts, margin −9.7 pts. The classic "we bought revenue".

### 10. Sales rep quota attainment
*Config: `fact_sales_rep_quota`.* Monthly quota vs actual per rep, rolled up
the five-level VP → Region → Director → Manager → Rep hierarchy.

### 11. Budget vs actual vs forecast
*Config: `forecast_deterioration`.* Five forecast versions over the same grain.
Walking Original Budget → Latest Forecast shows a $7.1M profit shortfall
opening up.

### 12. Anomaly detection and explanation
*Config: `sales_anomaly`.* One $2.80M order sits at 55× the 99.9th percentile.
Obvious enough for any outlier method to flag, and explainable when drilled:
one customer, one date, 14 high-value lines.

### 13. What-if / recovery scenario
*Config: `recovery_scenario`.* Supplier cost −7%, discount −4 pts, inventory
availability +20%, customer recovery +10% → +$5.1M profit back. Wire the four
knobs to dashboard parameters for a live scenario tool.

### 14. Time intelligence showcase
*Config: `dim_date`.* YTD, PYTD, LTM, MTD, QTD, rolling 12, fiscal calendar
(February start) and a full NRF 4-5-4 retail calendar including the 53-week
retail year. "Compare this retail period against the same period last year"
works out of the box.

### 15. Multi-currency consolidation
*Config: `dim_exchange_rate`.* 15 currencies, monthly rates. Plain columns are
USD; `_lc` columns are local. Shows constant-currency vs actual growth.

### Cross-cutting: natural-language / AI
All 30 questions in the original design work against this schema. They are
deliberately aggregation-and-drill questions, not retrieval questions, so they
exercise Databricks Genie, Power BI Copilot or Tableau Pulse properly.

---

## Building more flows

Each block in `config/scenario_base.yaml` is independent. Some starting points:

| Want | Change |
|---|---|
| A cost crisis instead of a wobble | `supplier_cost_shock.cost_increase_pct: 0.12 → 0.25` |
| The problem in APAC, not Europe | `region_margin_erosion.region: APAC`, pick a country |
| A clean year with no bad news | set every event `enabled: false` |
| A pure growth story | disable the cost shock and promotion, raise `underlying_growth_yoy` |
| A deeper stockout crisis | `inventory_shortage.affected_sku_count: 6 → 25` |
| Different company size | switch tier, or edit `tiers.*.order_lines` |
| A pristine dataset | zero out `baseline.data_quality` |

After any change, run the validator. It will tell you whether the story you
configured is actually visible in the data:

```bash
python3 src/generate.py --scenario config/my_scenario.yaml --tier small && python3 src/validate.py --tier small
```
