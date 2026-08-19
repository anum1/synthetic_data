# Supply Chain Inventory Demo — Guide

## Data

**File:** `supply_chain_inventory_demo.csv` (9,000 rows, flat/denormalized — one row per day × product × warehouse)
**Generator:** `generate_data.py` (re-run to regenerate; seeded, so output is reproducible)

**Period:** 2026-05-06 → 2026-08-03 (90 days)
**Scope:** 5 warehouses × 20 products across 4 categories

| Column | Description |
|---|---|
| date | Transaction date |
| warehouse_id / warehouse_name / region | Where the inventory sits |
| product_id / product_name / category | What's being tracked |
| supplier_name | Supplier for that SKU |
| lead_time_days | Supplier lead time observed that day |
| unit_cost / unit_price | Cost and sell price per unit |
| beginning_inventory | Stock at start of day (after any receipt) |
| units_received | Units delivered that day from a supplier order |
| units_demanded | Customer demand that day |
| units_sold | Demand actually fulfilled (capped by inventory) |
| ending_inventory | Stock at end of day |
| reorder_point | Static threshold that triggers a reorder |
| safety_stock | Buffer stock built into the reorder point |
| stockout_flag | True when demand exceeded available inventory |
| days_of_supply | Ending inventory ÷ average daily demand |

### The embedded problem

**Supplier "TechSource Asia"** supplies 4 of the 5 Electronics SKUs (Wireless Earbuds Pro, USB-C Power Bank, Bluetooth Speaker Mini, Smart Home Hub). Starting around **day 45 (~June 20)**, their lead time climbs from ~8 days to ~24 days over three weeks and stays there. Reorder points were never adjusted to account for the longer lead time, so:

- Stockout rate for TechSource Asia SKUs: **0% in the first 30 days → 34.8% in the last 30 days**
- Every other supplier/category stays essentially flat (**~0.1%** stockout rate throughout)
- The 5th Electronics SKU (Wireless Charging Pad, sourced from "Global Circuits Ltd") stays healthy — good for contrast, since it's the same category but not the same supplier

This is the "needle" the AI chat should find, and what the dashboard should then be enhanced to track.

---

## Step 1 — Question to ask the AI chat

Lead with something open-ended so the discovery feels real rather than pre-scripted:

> "Why have we been seeing more stockouts recently? Is there a pattern across products, categories, warehouses, or suppliers?"

Good follow-ups once it responds, to deepen the drill-down on camera:
- "Which supplier is driving that, and has their lead time changed?"
- "Which specific SKUs and warehouses are worst affected?"
- "Are our reorder points still appropriate given the new lead times?"

**Expected answer shape:** stockouts are concentrated in Electronics SKUs supplied by TechSource Asia; their lead time roughly tripled (~8 → ~24 days) since mid-June; reorder points weren't updated, so inventory now runs out well before the replacement order arrives; other suppliers/categories are unaffected.

---

## Step 2 — Insights to add to the dashboard

Once the AI has surfaced the problem, propose adding these to make it trackable on an ongoing basis (not just a one-time answer):

1. **Stockout rate by supplier (trend line, last 90 days)** — the core early-warning metric; makes the TechSource Asia divergence from every other supplier visually obvious.
2. **Supplier lead time trend (avg lead_time_days over time, by supplier)** — the leading indicator that explains *why* stockouts are rising, ideally shown side-by-side with the stockout trend.
3. **Reorder point vs. effective lead-time coverage** — a table/bar flagging SKUs where `reorder_point ÷ avg_daily_demand` no longer covers current `lead_time_days` + safety buffer. This turns the insight into an actionable "fix these SKUs" list.
4. **Days-of-supply heatmap (product × warehouse)** — quickly shows which warehouse/SKU combinations are running critically low right now.
5. **Lost-sales estimate (units_demanded − units_sold, × unit_price)** — converts the operational problem into a $ business-impact number for the exec view.
6. **At-risk SKU watchlist** — auto-filtered list of products where stockout_flag has been true for 3+ of the last 7 days, sorted by lost-sales impact, so the team has a concrete action queue rather than just a chart.
