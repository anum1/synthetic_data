# Understanding This Data (No Supply Chain Background Needed)

This file explains the concepts behind `inventory_stockout_demo.csv` in plain
terms. If you already know supply chain jargon, skip to `DEMO_GUIDE.md` instead.

## The basic idea

A retailer keeps products sitting in warehouses so it can sell them to
customers. Every day, three things happen to the stock of a product in a
warehouse:

1. **Stock arrives** from a supplier (a shipment gets delivered).
2. **Customers buy it**, so stock goes down.
3. Whatever's left over at the end of the day carries into tomorrow.

Each row in the CSV is a snapshot of exactly that, for **one product, in one
warehouse, on one day**. With 20 products × 5 warehouses × 90 days, that's
9,000 rows — one "day in the life" of each product/warehouse pair.

## Key terms, explained

**Lead time** — the number of days between placing an order with a supplier
and the shipment actually arriving. If lead time is 8 days, and you order on
Monday, it shows up the following Tuesday. Longer lead time means you need to
plan further ahead.

**Demand** — how many units customers wanted to buy that day. This is
different from *sales*, because if you run out of stock, you can't sell what
customers wanted — you can only sell what you have.

**Stockout** — the moment demand is higher than what's on the shelf. If 10
customers want the product but you only have 6 left, you sell 6 and 4 people
leave empty-handed (or buy from a competitor). That's a stockout, and it's
lost revenue, not just an inconvenience.

**Reorder point** — a threshold inventory level that automatically triggers a
new order to the supplier. For example, "when stock drops to 50 units, order
more." It's normally set based on: *how much do we sell per day* × *how many
days it takes the supplier to deliver*, plus a cushion.

**Safety stock** — the cushion mentioned above. Demand and delivery times
aren't perfectly predictable, so companies keep some extra stock as a buffer
against surprises. It's baked into the reorder point.

**Days of supply** — at the current rate of sales, how many days will the
remaining stock last? `Days of supply = current inventory ÷ average daily
demand`. A low number (e.g., 2 days) is a warning sign; a stockout is likely
very soon unless a shipment arrives.

## Why reorder points can go stale

The reorder point math only works if the lead time it was built on stays
true. Here's the trap this dataset is built around:

- A reorder point is set assuming the supplier delivers in **8 days**.
- The supplier's lead time quietly grows to **24 days** (maybe a factory
  slowdown, a shipping delay, a new customs process — the data doesn't say
  why, only that it happened).
- Nobody goes back and re-calculates the reorder point for the new, longer
  lead time.
- Now the company keeps ordering "too late" relative to how long delivery
  actually takes, inventory runs out before the next shipment lands, and
  stockouts start happening — repeatedly, not just once.

That's exactly the pattern in this data: one supplier's lead time triples
partway through the 90 days, its reorder points never change, and stockouts
for its products climb from essentially zero to about 1-in-3 days by the end
of the period, while every other supplier in the dataset stays healthy the
whole time.

## How the columns fit together (one row, explained)

```
date: 2026-06-25
product_name: Wireless Earbuds Pro
warehouse_name: Newark DC
supplier_name: TechSource Asia
lead_time_days: 22          -> today, this supplier is taking 22 days to deliver
beginning_inventory: 40     -> we started today with 40 units on the shelf
units_received: 0           -> no shipment arrived today
units_demanded: 15          -> customers wanted 15 units
units_sold: 15              -> we had enough, so we sold all 15
ending_inventory: 25        -> 40 - 15 = 25 units left for tomorrow
reorder_point: 119          -> we're supposed to reorder once stock hits 119
stockout_flag: False        -> demand was fully met today
days_of_supply: 2.3         -> at this sales rate, 25 units run out in ~2.3 days
```

Notice `ending_inventory` (25) is already well below `reorder_point` (119) —
an order should already be in transit. But because it was sized for an
8-day-lead-time world and the supplier now takes 22 days, that order won't
land in time, and a stockout on this product is coming within days.

## Where to go next

- `DEMO_GUIDE.md` — the demo script: what to ask the AI chat, and what
  dashboard insights to add once the problem is confirmed.
- `generate_data.py` — the code that generated the CSV, if you want to see
  exactly how the numbers were simulated.
