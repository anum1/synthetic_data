"""
Generates a flat CSV of daily supply-chain / inventory transactions for a demo.

Storyline baked into the data:
  Supplier "TechSource Asia" (feeds most of the Electronics category) sees its
  lead time balloon from ~8 days to ~24 days starting mid-way through the
  90-day window. Nobody raised the reorder points to compensate, so those
  SKUs start stocking out hard in the back half of the period while every
  other supplier/category stays healthy. That's the "problem" the AI chat
  should surface, and the dashboard insights should track.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

rng = np.random.default_rng(42)

END_DATE = date(2026, 8, 3)   # yesterday relative to "today" in the demo
DAYS = 90
START_DATE = END_DATE - timedelta(days=DAYS - 1)

WAREHOUSES = [
    ("WH-EAST", "Newark DC", "Northeast", 1.2),
    ("WH-CENTRAL", "Dallas DC", "Central", 1.0),
    ("WH-SOUTH", "Atlanta DC", "Southeast", 0.9),
    ("WH-WEST", "Reno DC", "West", 0.8),
    ("WH-NORTHWEST", "Portland DC", "Northwest", 0.7),
]

# product_id, name, category, supplier, base_lead_time_days, base_daily_demand, unit_cost, unit_price, problem_supplier?
PRODUCTS = [
    ("E1", "Wireless Earbuds Pro", "Electronics", "TechSource Asia", 8, 9, 22.0, 49.99, True),
    ("E2", "USB-C Power Bank 20000mAh", "Electronics", "TechSource Asia", 8, 11, 14.0, 34.99, True),
    ("E3", "Bluetooth Speaker Mini", "Electronics", "TechSource Asia", 8, 7, 18.0, 39.99, True),
    ("E4", "Smart Home Hub", "Electronics", "TechSource Asia", 8, 5, 28.0, 64.99, True),
    ("E5", "Wireless Charging Pad", "Electronics", "Global Circuits Ltd", 9, 6, 9.0, 24.99, False),
    ("H1", "Stainless Steel Water Bottle", "Home & Kitchen", "HomeGoods Direct", 10, 8, 6.5, 19.99, False),
    ("H2", "Non-Stick Frying Pan Set", "Home & Kitchen", "HomeGoods Direct", 10, 4, 21.0, 49.99, False),
    ("H3", "Ceramic Coffee Mug Set", "Home & Kitchen", "HomeGoods Direct", 10, 6, 9.0, 22.99, False),
    ("H4", "Kitchen Knife Set", "Home & Kitchen", "HomeGoods Direct", 11, 3, 26.0, 59.99, False),
    ("H5", "Electric Kettle", "Home & Kitchen", "HomeGoods Direct", 10, 5, 15.0, 34.99, False),
    ("O1", "Gel Pens 12-Pack", "Office Supplies", "OfficeMart Wholesale", 5, 14, 2.0, 6.99, False),
    ("O2", "Sticky Notes Multi-Pack", "Office Supplies", "OfficeMart Wholesale", 5, 12, 3.0, 8.99, False),
    ("O3", "Desk Organizer", "Office Supplies", "OfficeMart Wholesale", 6, 4, 7.5, 17.99, False),
    ("O4", "Printer Paper Ream (10pk)", "Office Supplies", "OfficeMart Wholesale", 5, 9, 18.0, 32.99, False),
    ("O5", "Stapler Heavy Duty", "Office Supplies", "OfficeMart Wholesale", 6, 3, 5.5, 13.99, False),
    ("P1", "Moisturizing Body Lotion", "Personal Care", "PureCare Manufacturing", 12, 10, 4.5, 11.99, False),
    ("P2", "Electric Toothbrush", "Personal Care", "PureCare Manufacturing", 12, 5, 16.0, 39.99, False),
    ("P3", "Shampoo & Conditioner Set", "Personal Care", "PureCare Manufacturing", 12, 8, 8.0, 19.99, False),
    ("P4", "Hand Sanitizer 3-Pack", "Personal Care", "PureCare Manufacturing", 13, 11, 3.0, 8.99, False),
    ("P5", "Facial Tissue Box 6-Pack", "Personal Care", "PureCare Manufacturing", 12, 9, 5.0, 12.99, False),
]

RAMP_START_DAY = 45   # lead time starts climbing
RAMP_END_DAY = 60     # lead time plateaus at the new normal


def lead_time_for_day(base_lead_time, is_problem_supplier, day_idx):
    if not is_problem_supplier:
        return max(1, base_lead_time + rng.integers(-1, 2))
    if day_idx < RAMP_START_DAY:
        target = base_lead_time
    elif day_idx < RAMP_END_DAY:
        progress = (day_idx - RAMP_START_DAY) / (RAMP_END_DAY - RAMP_START_DAY)
        target = base_lead_time + progress * (24 - base_lead_time)
    else:
        target = 24
    return max(1, int(round(target + rng.normal(0, 1.5))))


rows = []

for wh_id, wh_name, region, wh_factor in WAREHOUSES:
    for pid, pname, category, supplier, base_lt, base_demand, cost, price, is_problem in PRODUCTS:
        avg_demand = base_demand * wh_factor
        reorder_point = round(avg_demand * base_lt + avg_demand * 3)
        safety_stock = round(avg_demand * 3)
        order_qty = max(1, round(avg_demand * base_lt * 2))

        inventory = round(reorder_point * 1.5)
        pending_orders = []   # list of [arrival_day_idx, qty]
        outstanding_order = False

        for day_idx in range(DAYS):
            current_date = START_DATE + timedelta(days=day_idx)
            lead_time_today = lead_time_for_day(base_lt, is_problem, day_idx)

            beginning_inventory = inventory

            arrivals = [q for (d, q) in pending_orders if d == day_idx]
            units_received = int(sum(arrivals))
            if arrivals:
                pending_orders = [(d, q) for (d, q) in pending_orders if d != day_idx]
                outstanding_order = False

            inventory += units_received

            weekday_factor = 0.7 if current_date.weekday() >= 5 else 1.0
            demand = rng.poisson(max(0.1, avg_demand * weekday_factor))

            units_sold = min(demand, inventory)
            stockout = demand > inventory
            inventory -= units_sold
            ending_inventory = inventory

            if inventory <= reorder_point and not outstanding_order:
                arrival_day = day_idx + lead_time_today
                pending_orders.append((arrival_day, order_qty))
                outstanding_order = True

            days_of_supply = round(ending_inventory / avg_demand, 1) if avg_demand > 0 else None

            rows.append({
                "date": current_date.isoformat(),
                "warehouse_id": wh_id,
                "warehouse_name": wh_name,
                "region": region,
                "product_id": pid,
                "product_name": pname,
                "category": category,
                "supplier_name": supplier,
                "lead_time_days": lead_time_today,
                "unit_cost": cost,
                "unit_price": price,
                "beginning_inventory": beginning_inventory,
                "units_received": units_received,
                "units_demanded": int(demand),
                "units_sold": int(units_sold),
                "ending_inventory": ending_inventory,
                "reorder_point": reorder_point,
                "safety_stock": safety_stock,
                "stockout_flag": bool(stockout),
                "days_of_supply": days_of_supply,
            })

df = pd.DataFrame(rows)
out_path = "/Users/anuragmalik/Documents/ai_apps/python_data_prep/supply_chain/supply_chain_inventory_demo.csv"
df.to_csv(out_path, index=False)
print(f"Wrote {len(df)} rows to {out_path}")

# Quick sanity check of the embedded problem
problem = df[(df["supplier_name"] == "TechSource Asia")]
healthy = df[(df["supplier_name"] != "TechSource Asia")]
print("\nStockout rate - TechSource Asia (Electronics):", round(problem["stockout_flag"].mean() * 100, 1), "%")
print("Stockout rate - all other suppliers:", round(healthy["stockout_flag"].mean() * 100, 1), "%")

problem_last30 = problem[problem["date"] >= (END_DATE - timedelta(days=30)).isoformat()]
problem_first30 = problem[problem["date"] < (START_DATE + timedelta(days=30)).isoformat()]
print("TechSource Asia stockout rate - first 30 days:", round(problem_first30["stockout_flag"].mean() * 100, 1), "%")
print("TechSource Asia stockout rate - last 30 days:", round(problem_last30["stockout_flag"].mean() * 100, 1), "%")
