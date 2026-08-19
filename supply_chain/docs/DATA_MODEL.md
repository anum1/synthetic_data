# Data model

**Meridian Global Industries — Supply Chain Control Tower**

18 tables in a star schema, generated from a single scenario config. Every fact
joins to the dimensions through conformed integer keys; there are no bridge
tables and no many-to-many relationships, which is what lets the same model load
unchanged into Tableau, Power BI, Databricks and Snowflake.

Conventions (naming, money types, booleans, NULL-FK policy, calendars) are
inherited verbatim from the sibling ApexTech sales dataset — see
`../sales/docs/DATA_MODEL.md` §3b and §4. Section 8 below records only the
places where this dataset *departs* from them.

---

## 1. Star schema

```
                                  dim_date
                                      |
                                      | date_key / year_month_key
        ┌─────────────────────────────┼─────────────────────────────┐
        |                             |                             |
   INBOUND                        INVENTORY                     OUTBOUND
        |                             |                             |
  dim_supplier                  dim_location                   dim_customer
        |                             |                             |
        v                             v                             v
  fact_purchase_order  ──po_line_id──> fact_inventory_snapshot   fact_sales_order_line
        |                             ^        ^                      |
        v                             |        |                      v
  fact_supplier_delivery ─────────────┘        |                fact_shipment ── dim_carrier
        |                                      |                      |
        v                                      |                      |
  fact_production ─────────────────────────────┘                      |
                                                                      |
   dim_product ──────────────── joins every fact above ───────────────┘
        |
        ├── primary_supplier_id   ─> dim_supplier
        └── secondary_supplier_id ─> dim_supplier   (0 = single-sourced)

  PLANNING GRAIN (coarser, see §6)
  fact_demand_signal      -> week  x product x region
  fact_forecast           -> month x product x region x forecast_version
  fact_supply_chain_risk  -> month x entity_type x entity_id
  fact_financial_impact   -> month x cost_category x entity_type x entity_id
```

## 2. Tables

| Table | Grain | Rows (small) | Rows (full) |
|---|---|---:|---:|
| `dim_date` | one day | 1,430 | 1,430 |
| `dim_product` | one SKU | 600 | 1,500 |
| `dim_supplier` | one supplier | 120 | 200 |
| `dim_location` | one node (DC, plant, port) | 20 | 40 |
| `dim_customer` | one customer | 3,000 | 10,000 |
| `dim_carrier` | one carrier | 12 | 20 |
| `dim_employee` | one planner / buyer | 150 | 500 |
| `dim_region` | one region (plan grain) | 5 | 5 |
| `dim_product_category` | one subcategory (plan grain) | 24 | 24 |
| `fact_inventory_snapshot` | day-or-week × location × SKU | ~860K | ~4.3M |
| `fact_purchase_order` | one PO line | 120K | 300K |
| `fact_supplier_delivery` | one receipt line | 100K | 250K |
| `fact_sales_order_line` | one order line | 200K | 500K |
| `fact_shipment` | one outbound shipment | 200K | 500K |
| `fact_production` | one work-order completion | 120K | 300K |
| `fact_demand_signal` | week × product × region | 470K | 1.18M |
| `fact_forecast` | month × product × region × version | 430K | 1.08M |
| `fact_supply_chain_risk` | month × entity | 27K | 63K |
| `fact_financial_impact` | month × cost_category × entity | 18K | 42K |

Estimated on disk: **~65 MB** (small, parquet) / **~400 MB** (full, parquet).
CSV export is emitted for the `small` tier only — that is the Tableau/Power BI
Desktop tier. `full` is the Snowflake/Databricks tier.

---

## 3. The grid decisions (read this before writing any code)

The source design note asks for 2M daily inventory snapshots over 1,500 products
and 40 warehouses. That cross product is **66M rows**, 33× the stated target. The
same applies to forecast (8.6M against a 1.5M target). Both are resolved here
deliberately rather than by silently truncating.

### 3.1 Inventory is stocked on a *sparse* grid

A real DC does not stock every SKU. Stocking breadth follows ABC class:

Breadth is configured as a *fraction of locations* under
`inventory.stocking_breadth`, so it scales with the tier:

| ABC class | Fraction of locations | Locations (small / full) | Pairs (small / full) |
|---|---:|---:|---:|
| A | 0.75 | 15 / 30 | 1,800 / 9,000 |
| B | 0.30 | 6 / 12 | 1,080 / 5,400 |
| C | 0.10 | 2 / 4 | 600 / 3,000 |
| **Total** | | | **3,480 / 17,400** |

That yields **17,400 stocking pairs** at full tier, not 60,000. The pair list is generated
once into `dim_product_location` semantics (embedded as the snapshot grid; no
separate table is emitted) and is stable across the whole timeline except where
Event 12 opens a new DC.

### 3.2 Snapshots are weekly, with a daily recent window

```yaml
inventory:
  snapshot_frequency: weekly      # full history
  daily_window_days: 90           # most recent N days also get daily rows
```

Weekly over 157 weeks = 2.73M rows; the trailing 90 days at daily grain adds
1.57M. Total ~4.3M at full tier, ~860K at small. This mirrors how real inventory warehouses actually retain
data — recent detail, historical rollup — and it is what makes the trailing-90-day
stockout drill-down in the demo flow have day-level resolution while the 3-year
trend stays cheap.

`snapshot_grain` (`'D'` / `'W'`) is a column on the fact so a dashboard can
filter to one grain and never double-count. **Any measure summed across mixed
grains is wrong** — the validator asserts every aggregate query in
`docs/DEMO_FLOWS.md` filters on it.

### 3.3 Forecasting happens at product × region, not product × location

Statistical forecasting at SKU × DC grain is not how planning organisations
actually work, and it would have produced 8.6M rows of mostly-zero series.
Forecast grain is **month × product × region × version**: 1,500 × 5 × 36 × 4 =
1.08M. Location-level requirements are a *derived* allocation, not a forecast.

### 3.4 Customers are deliberately thin

10,000 customers, no customer hierarchy beyond segment. Customers matter to this
dataset only as backorder and revenue-at-risk attribution. Anything richer
belongs in the sales dataset.

---

## 4. `dim_product` — the most important dimension

```
product_id                INT      PK
product_sku               VARCHAR
product_name              VARCHAR
category / subcategory    VARCHAR  -> product_category_id
brand / product_family    VARCHAR
product_type              VARCHAR  Finished Good | Component | Raw Material
material                  VARCHAR
unit_cost                 DECIMAL(18,2)   changes over time; see fact-level cost
standard_price            DECIMAL(18,2)
weight_kg / volume_m3     DECIMAL(18,3)
shelf_life_days           INT      0 = non-perishable
lead_time_days            INT      planning parameter, NOT actual
safety_stock_days         INT      planning parameter
abc_class                 CHAR(1)  A | B | C   by annual extended value
xyz_class                 CHAR(1)  X | Y | Z   by demand CV (see below)
criticality               VARCHAR  Critical | Important | Standard
country_of_origin         VARCHAR
primary_supplier_id       INT      -> dim_supplier
secondary_supplier_id     INT      -> dim_supplier, 0 = single-sourced
single_source_flag        INT      0/1, derived: secondary_supplier_id = 0
```

### ABC / XYZ must be *derived*, not assigned

Assigning these randomly is the most common way this kind of dataset falls apart
under questioning. They are computed from the generated facts:

- **ABC** — rank SKUs by trailing-12-month extended cost (annual demand ×
  unit_cost). Cumulative 80% → A, next 15% → B, remainder → C.
- **XYZ** — coefficient of variation of weekly demand over the trailing year.
  CV < 0.5 → X, 0.5–1.0 → Y, > 1.0 → Z.

This means generation order is: demand first, then classification, then the
planning parameters that depend on it. See §7.

It also means the questions the design note wants actually hold up:
*"Which AX products have the highest stockout risk?"* returns products that are
genuinely high-value and genuinely predictable, so the answer is defensible when
someone drills into it.

---

## 5. `dim_supplier` — where the problems live

```
supplier_id               INT      PK
supplier_master_id        VARCHAR  SUP-104 style; the *clean* key
supplier_name             VARCHAR  the MESSY name (see §9)
supplier_tier             VARCHAR  Strategic | Preferred | Approved | At Risk
country / region          VARCHAR
category                  VARCHAR  what they supply
payment_terms             VARCHAR  Net 30 | Net 45 | Net 60 | 2/10 Net 30
lead_time_days            INT      contracted, NOT actual
minimum_order_qty         INT
capacity_units_per_week   INT
quality_score             DECIMAL(5,2)   0-100, derived from defect rate
on_time_rate              DECIMAL(5,4)   derived from fact_supplier_delivery
defect_rate               DECIMAL(5,4)   derived
financial_risk            INT      0-100
geopolitical_risk         INT      0-100  driven by country
risk_score                INT      0-100  composite, see §6.4
```

`quality_score`, `on_time_rate`, `defect_rate` and `risk_score` are **snapshot
attributes recomputed from the facts at as-of date**, never independently
sampled. The time series lives in `fact_supply_chain_risk`. If the dimension
says S-104 is at 71% on-time and the fact table says 88%, the demo is dead — so
the validator asserts the dimension reconciles to the trailing-90-day fact
aggregate for every supplier.

---

## 6. KPI definitions

Pinning these down now is the highest-leverage thing in this spec. Fill rate and
OTIF are the two most-argued-about metrics in supply chain, and changing the
definition later means regenerating.

| KPI | Definition | Grain it is valid at |
|---|---|---|
| **Line fill rate** | order lines shipped complete on first attempt ÷ total order lines | any |
| **Unit fill rate** | units shipped ÷ units ordered | any |
| **OTIF** | shipments where `actual_delivery_date <= expected_delivery_date` AND `shipped_qty >= ordered_qty` ÷ all shipments | any |
| **Supplier on-time %** | receipts where `actual_receipt_date <= promised_date` ÷ all receipts | supplier, month |
| **Stockout rate** | snapshots where `available_qty <= 0` AND that SKU had demand that period ÷ snapshots with demand | must filter `snapshot_grain` |
| **Days of supply** | `on_hand_qty ÷ avg_daily_demand(trailing 28d)`; NULL when demand is 0 | SKU × location |
| **Inventory turns** | trailing-12-month COGS ÷ average inventory value over the same window | any, annualised |
| **Forecast accuracy** | `1 − MAPE`, floored at 0 | month × product × region |
| **MAPE** | `mean(abs(actual − forecast) / actual)`, excluding actual = 0 | as above |
| **Forecast bias** | `mean((forecast − actual) / actual)` — signed, so over/under-forecast is visible | as above |
| **Backorder value** | `backorder_qty × standard_price` | any |

Two traps worth naming, because both will be asked about live:

- **OTIF is a shipment-level metric, not a line-level one.** A single late
  shipment carrying 40 lines counts once. Computing it at line grain inflates it.
- **Days of supply must not be averaged.** Averaging DOS across SKUs weights a
  slow-moving C item the same as a fast A item. The dashboard aggregates it as
  `SUM(on_hand) / SUM(avg_daily_demand)`, and the doc says so.

### 6.4 Risk score

`overall_risk_score` is a weighted composite of five sub-scores, each 0–100 and
each **derived from the facts**, not sampled:

| Component | Derived from | Weight |
|---|---|---:|
| `supplier_risk` | on-time %, lead-time variance, single-source exposure | 30% |
| `demand_risk` | forecast error, demand CV (XYZ class) | 25% |
| `inventory_risk` | days of supply vs safety stock, stockout frequency | 20% |
| `logistics_risk` | carrier OTIF, transit-time variance | 15% |
| `quality_risk` | defect rate, rejected receipt rate | 10% |

`risk_level` bands: ≥80 Critical, 60–79 High, 35–59 Medium, <35 Low. Bands are
config knobs so the heatmap counts can be tuned to the ~12/28/67/93 distribution
the design note wants.

---

## 7. Generation order

The order is forced by the derivations above. Anything generated out of order
produces a dataset where the drill-downs do not reconcile.

```
1. dim_date, dim_region, dim_product_category, dim_location, dim_carrier
2. dim_supplier            (base attributes only; performance left blank)
3. dim_product             (base attributes; abc/xyz/planning params blank)
4. fact_demand_signal      <- baseline seasonality + events
5. dim_product ABC/XYZ     <- DERIVED from step 4
6. dim_product planning params (lead_time, safety_stock) <- depend on step 5
7. fact_forecast           <- 4 versions, each seeing progressively more events
8. fact_purchase_order     <- driven by reorder logic against step 4 + 6
9. fact_supplier_delivery  <- PO lines + supplier performance + events
10. fact_production
11. fact_inventory_snapshot <- the balance equation, see below
12. fact_sales_order_line, fact_shipment <- constrained by step 11 availability
13. dim_supplier performance attrs <- DERIVED from step 9
14. fact_supply_chain_risk  <- DERIVED from 4,9,11,12
15. fact_financial_impact   <- DERIVED from 11,12,14
```

**The inventory balance equation must actually close.** For every SKU × location:

```
on_hand[t] = on_hand[t-1] + receipts[t] + production[t] − shipped[t] − scrapped[t]
available_qty = on_hand_qty − reserved_qty
```

Generating `on_hand` as an independent random walk is the fastest way to get a
dataset that looks fine on a KPI tile and falls apart the moment someone drills
from a stockout into the receipts that should have prevented it. The validator
asserts the equation closes to the unit for a sample of 500 SKU × location series.

---

## 8. Departures from the sales dataset conventions

Everything in `../sales/docs/DATA_MODEL.md` §4 applies — lowercase snake_case, no
reserved-word column names, `DECIMAL(18,2)` money, `0/1` booleans, ISO dates, no
NULL foreign keys. Three additions specific to this dataset:

1. **Quantities are `DECIMAL(18,3)`, not INT.** Some categories ship in
   kilograms and litres. Integer quantities would force a units-of-measure
   conversion the demo does not need.
2. **`snapshot_grain` is mandatory on `fact_inventory_snapshot`** (§3.2). It is
   the one column whose omission silently doubles every inventory measure.
3. **Date columns are triples where a process spans time**: `requested_date`,
   `promised_date`, `actual_receipt_date`. Late-ness is always
   `actual − promised`, never `actual − requested`. The distinction is the whole
   supplier-performance story: a supplier that always promises late but delivers
   on its promise is a *planning* problem, not a supplier problem, and the data
   should let someone discover that.

---

## 9. Deliberate data-quality issues

Config-controlled under `baseline.data_quality`; set any knob to `0` for a
pristine dataset.

| Issue | Default | Purpose |
|---|---|---|
| Supplier name variants | 18 suppliers get 3–5 name spellings | Entity resolution demo; all map to one `supplier_master_id` |
| Missing `lead_time_days` | ~3% of suppliers | Shows up as gaps in planning parameters |
| Inconsistent product descriptions | ~5% of SKUs | Casing, abbreviations, trailing whitespace |
| Cancelled PO lines | ~4% | `status = 'Cancelled'`, `received_qty = 0` |
| Partial receipts | ~9% of PO lines | `received_qty < ordered_qty`, no follow-up receipt |
| NULL `actual_delivery_date` | ~0.5% of shipments | In-transit or lost paperwork |
| Duplicate POs | 15 exact-content pairs, distinct `po_id` | Duplicate-detection demo |

The supplier-name variants are the valuable one. `supplier_name` carries the
messy value and `supplier_master_id` the clean key, so the same dataset supports
both *"our supplier performance is fine"* (grouped on the messy name, where
S-104's failures are split five ways and invisible) and the corrected view. That
is a genuinely good demo moment and it costs nothing to build in.

---

## 10. What is not modelled

- **Multi-echelon inventory optimisation.** Locations are flat; there is no
  central-DC-feeds-regional-DC replenishment network. Adding echelons would
  double the fact volume and no dashboard page in the plan uses it.
- **Bill of materials.** `fact_production` completes finished goods without
  consuming components. A real BOM explosion is a large modelling exercise that
  only Event 5 (quality) would touch.
- **Lot/batch and serial tracking.** No traceability or recall demo.
- **Currency.** Everything is USD. The sales dataset carries the FX story; here
  it would only dilute the supply-chain narrative.
- **Relative-period flags** (`is_current_month`, `is_ytd`). Left to the BI layer,
  same reasoning as the sales dataset.
