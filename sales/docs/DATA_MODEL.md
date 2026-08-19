# Data model

**ApexTech — Enterprise Sales & Profitability 360**

20 tables in a star schema. Every table joins to the others through conformed
dimension keys; there are no bridge tables and no many-to-many relationships,
which is what lets the same model load unchanged into Tableau, Power BI,
Databricks and Snowflake.

---

## 1. Star schema

```
                            dim_date
                                |
                                | date_key / year_month_key
                                |
  dim_customer ─┐               |             ┌─ dim_location ─┐
  dim_sales_rep ─┼── fact_sales_order ────────┤                │
  dim_channel ──┘        |                    └─ dim_currency  │
                         | order_id                            │
                         v                                     │
                fact_sales_order_line ─────────────────────────┘
                         |
        ┌────────────┬───┴────┬──────────────┐
        v            v        v              v
   dim_product  dim_supplier  dim_promotion  dim_channel
        |
        └── supplier_id ── dim_supplier

  fact_returns              -> order_line_id, product, customer, supplier, location
  fact_inventory            -> product, location, date
  fact_supplier_performance -> supplier, product, month
  fact_sales_rep_quota      -> sales_rep, month
  fact_budget               -> month x region x country x category x subcategory x channel
  fact_forecast             -> same grain as budget, plus forecast_version
```

## 2. Tables

| Table | Grain | Rows (small) | Rows (full) |
|---|---|---:|---:|
| `dim_date` | one day | 1,430 | 1,430 |
| `dim_customer` | one customer | 2,000 | 8,000 |
| `dim_product` | one SKU | 800 | 2,500 |
| `dim_supplier` | one supplier | 150 | 500 |
| `dim_location` | one location | 120 | 500 |
| `dim_promotion` | one campaign | 202 | 202 |
| `dim_sales_rep` | one rep | 90 | 300 |
| `dim_channel` | one channel | 5 | 5 |
| `dim_country` | one country (plan grain) | 22 | 22 |
| `dim_product_category` | one subcategory (plan grain) | 29 | 29 |
| `dim_currency` | one currency | 15 | 15 |
| `dim_exchange_rate` | month × currency | 705 | 705 |
| `fact_sales_order` | one order header | 85,720 | 857,151 |
| **`fact_sales_order_line`** | **one order line** | **299,863** | **3,000,186** |
| `fact_returns` | one return | 8,872 | 88,637 |
| `fact_inventory` | week × location × SKU | 224,100 | 507,600 |
| `fact_supplier_performance` | month × supplier × product | 14,676 | 47,790 |
| `fact_budget` | month × region × country × category × subcategory × channel | 128,968 | 149,930 |
| `fact_forecast` | budget grain × forecast_version | 219,520 | 255,200 |
| `fact_sales_rep_quota` | month × rep | 2,790 | 9,300 |

Total on disk: **51 MB** (small, parquet) / **370 MB** (full, parquet).
CSV export for the small tier is ~135 MB.

## 3. Hierarchies

Every hierarchy is emitted **twice**: as the natural attribute columns, and as
explicitly numbered `level` columns. Power BI can walk a parent-child column
with `PATH()`; Tableau cannot. The flattened columns mean one definition works
in both, and drill-down paths are unambiguous.

| Hierarchy | Columns |
|---|---|
| Geography | `geo_level1_global` → `level2_region` → `level3_country` → `level4_state` → `level5_city` → `level6_location` |
| Product | `product_level1_category` → `level2_subcategory` → `level3_brand` → `level4_family` → `level5_product` → `level6_sku` |
| Customer | `cust_level1_segment` → `level2_industry` → `level3_tier` → `level4_customer` |
| Supplier | `supplier_level1_region` → `level2_group` → `level3_tier` → `level4_name` |
| Sales org | `rep_level1_vp` → `level2_region` → `level3_director` → `level4_manager` → `level5_rep` |

## 3b. Calendars in `dim_date`

`dim_date` carries **three parallel calendars over the same 1,430 rows**, plus
an ISO week layer. Each date is simultaneously described by all of them, so a
dashboard switches calendars by changing which columns it groups on — there is
no second date table and no reload.

| Calendar | Columns | Driven by |
|---|---|---|
| **Gregorian** | `year_number`, `quarter_number`, `month_number`, `week_of_year`, `day_of_*` | fixed |
| **Fiscal** | `fiscal_year`, `fiscal_quarter`, `fiscal_month`, `fiscal_week`, `fiscal_year_month` | `calendar.fiscal_year_start_month` |
| **Retail (NRF)** | `retail_year`, `retail_454_quarter`, `retail_454_period`, `retail_454_week` | `calendar.retail_454_start_month`, `calendar.retail_pattern` |
| **ISO 8601 week** | `iso_year`, `week_of_year`, `iso_year_week`, `iso_year_week_key` | fixed |

### How each is derived

**Fiscal** — the year is shifted by `fiscal_year_start_month` and labelled by
the calendar year it *ends* in. With the shipped value of `2`, FY2027 runs
1 Feb 2026 → 31 Jan 2027. Set it to `7` and FY2027 starts 1 Jul 2026. Fiscal
periods are month-aligned, not week-aligned.

**Retail** — a true NRF-style calendar, not month arithmetic. The retail year
starts on the **first Sunday on or after** the 1st of `retail_454_start_month`,
so every retail week is a full Sunday–Saturday week and every period is exactly
7 × its week count. Supported `retail_pattern` values:

| Pattern | Shape | Periods |
|---|---|---|
| `4-5-4` | 4-5-4 / 4-5-4 / 4-5-4 / 4-5-4 | 12 (NRF standard) |
| `4-4-5` | 4-4-5 / 4-4-5 / 4-4-5 / 4-4-5 | 12 |
| `5-4-4` | 5-4-4 / 5-4-4 / 5-4-4 / 5-4-4 | 12 |
| `13x4` | thirteen equal 4-week periods | 13 |

A **53-week retail year** is handled: the extra week is absorbed by the final
period, exactly as the NRF calendar does. Retail 2026 is a 53-week year in the
shipped data, so the "comparing a 52-week year against a 53-week year" problem
is present and demonstrable rather than papered over.

**ISO 8601** — `week_of_year` is the ISO week, which belongs to an *ISO year*
that can differ from the calendar year: 30 Dec 2024 is ISO week 1 of **2025**.
Grouping a weekly trend by `(year_number, week_of_year)` therefore splits that
week across two years. Use `iso_year_week` or `iso_year_week_key` instead —
they keep it intact.

### What is not modelled

- Non-Gregorian civil calendars (Hijri, Hebrew, Japanese era, fiscal calendars
  that do not follow a Gregorian month or NRF week structure).
- A 52/53-**week** fiscal calendar. The fiscal layer is month-aligned; if you
  need week-aligned fiscal periods, use the retail columns, which already are.
- Relative-period flags (`is_current_month`, `is_ytd`, `is_last_12_months`).
  These are deliberately left to the BI layer, because each tool computes them
  against its own "today" and a baked-in flag goes stale the moment the extract
  is older than the data.

## 4. Conventions that keep all four platforms happy

**Naming.** All identifiers are lowercase `snake_case`. No column is named
`date`, `year`, `month`, `quarter`, `week`, `day` or `order` — every one of
those is reserved or a built-in function in Spark SQL or Snowflake, and using
them forces quoted identifiers everywhere. The calendar uses `calendar_date`,
`year_number`, `month_number`, `quarter_number`, `week_of_year`, `day_of_month`.

**Money is decimal, never float.** All monetary columns are `DECIMAL(18,2)`
(`NUMBER(18,2)` in Snowflake). Values are rounded once, at write time. This is
what lets a profit waterfall sum exactly to the KPI tile above it — with floats
the bars drift by cents and the demo loses credibility.

**Currency.** Transaction amounts are stored **twice**: the plain column names
(`net_sales`, `gross_profit`, `cost`, …) are in **USD**, the reporting currency,
so any tool sums them correctly with no setup. The `_lc` suffixed columns
(`net_sales_lc`, …) hold the same amount in the transaction's local currency.
`dim_exchange_rate` carries a monthly rate per currency, so FX movement is
itself demoable.

**Booleans are `0/1` integers**, not `true/false`. This is the only
representation all four tools read identically from CSV.

**Dates are `DATE`**, formatted ISO 8601 (`YYYY-MM-DD`) in CSV. No timezones,
no timestamps where a date will do.

**No NULL foreign keys.** Lines with no promotion carry `promotion_id = 0`,
which resolves to a real `"No Promotion"` row in `dim_promotion`. Inner joins
therefore never silently drop rows.

**Order headers reconcile to their lines.** `fact_sales_order.total_order_amount`
is computed by aggregating the order's own lines, so it can never drift.
The validator asserts this to the cent.

## 5. Planning grain

`fact_budget` and `fact_forecast` sit at a coarser grain than the sales fact
(month × country × subcategory × channel). This is the single most common thing
that breaks plan-vs-actual dashboards.

It works here because of two **conformed dimensions** built specifically for it:

- **`dim_country`** — 22 rows, `country_id` unique. `dim_location` cannot serve
  this role: it has 500 rows with repeated region and country values, so it is
  not a valid "one" side of a 1:many relationship at plan grain.
- **`dim_product_category`** — 21 rows, `product_category_id` unique, carrying
  both category and subcategory. `dim_product` repeats subcategory for the same
  reason.

Both the sales line fact and the plan facts carry `country_id`,
`product_category_id`, `channel_id` and `year_month_key` directly. Plan-vs-actual
is therefore a **four-integer-key join** with no text matching, no bridge table,
no many-to-many relationship and no data blending:

```sql
SELECT   b.year_month_key, c.region, pc.category,
         SUM(a.net_sales)   AS actual_sales,
         SUM(b.budget_sales) AS budget_sales
FROM    (SELECT year_month_key, country_id, product_category_id, channel_id,
                SUM(net_sales) AS net_sales
         FROM   fact_sales_order_line
         GROUP BY 1,2,3,4) a
JOIN     fact_budget b
  ON     a.year_month_key     = b.year_month_key
 AND     a.country_id         = b.country_id
 AND     a.product_category_id = b.product_category_id
 AND     a.channel_id         = b.channel_id
JOIN     dim_country          c  ON c.country_id = b.country_id
JOIN     dim_product_category pc ON pc.product_category_id = b.product_category_id
GROUP BY 1,2,3;
```

100% of actual grain cells match a budget row. The validator asserts that every
plan foreign key resolves.

**The budget is built from pre-event actuals only.** It represents the plan as
written before anything went wrong, so the events show up as variance rather
than being absorbed into the plan. Without this, every region misses plan by
the same percentage and the variance dashboard has nothing on it.

`fact_forecast` holds five versions: `Original Budget`, `Forecast v1`,
`Forecast v2`, `Latest Forecast`, `Recovery Scenario`. Later versions have seen
more of the planted events, which is what makes the forecast-deterioration
story visible as a walk across versions.

## 6. Deliberate data-quality issues

Controlled and configurable under `baseline.data_quality`, so a data-quality
demo has something real to find:

- ~0.4% of orders have a NULL `actual_ship_date`
- 12 duplicated orders (identical content, new `order_id`)
- ~2% of returns arrive late enough to land in a later period than the sale

Everything else is clean. Set the knobs to `0` if you want a pristine dataset.
