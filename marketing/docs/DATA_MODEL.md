# Data model — 33 tables as shipped

Star-schema-shaped: conformed dimensions, fact tables at their natural grain,
and three derived tables that are rollups of the facts rather than independent
sources. Every fact carries `geo_key`, `region_name`, `campaign_id` or
`channel_id` where relevant, so any measure can be sliced by the same
hierarchies.

The design note proposed 15 tables. Six were added because its own questions
could not be answered without them; four were split because the note's grain
was wrong. Both sets are marked below.

---

## Dimensions (17)

| Table | Grain | Notes |
|---|---|---|
| `dim_date` | one day | Gregorian + fiscal + `months_from_as_of` and relative-period flags. Anchored to today. |
| `dim_geography` | one city | Global → Region → Sub-region → Country → State → City. Facts join on `geo_key`, never on loose country text. |
| `dim_industry` | one industry | 9 industries, grouped into sectors. |
| `dim_segment` | one segment | SMB / Mid-Market / Enterprise, with `planned_account_share`, `planned_lead_share` and derived `planned_won_share`. |
| `dim_product` | one product line | Portfolio → Family → Line. **`gross_margin_pct` — ADDED**, so ROI is not the same number as ROAS. |
| `dim_channel` | one channel | 12 channels, carrying the plan: `planned_cpl_usd`, the four planned conversion rates, and the solved `recommended_spend_usd`. |
| `dim_campaign` | one campaign | Type, objective, target segment/industry/region, product, dates, budget vs actual. |
| `dim_ad_creative` | one creative | Paid channels only. Format, variant, control flag. |
| `dim_customer` | one **account** | 50,000 accounts. `is_hero_account` pins the curated journeys. |
| `dim_contact` | one **person** | **ADDED.** The note conflated lead and person. Persona, seniority, consent status, suppression date. |
| `dim_sales_rep` | one rep | Region, segment focus, team, quota. |
| `dim_lead_source` | one source | How the person arrived — not the same fact as which channel paid for them. |
| `dim_content_asset` | one asset | **ADDED.** Named whitepapers, calculators and reports, each with a lead-score weight. |
| `dim_activity_type` | one activity type | **ADDED.** Score points live here as data, so `lead_score` is auditable. |
| `dim_attribution_model` | one model | **ADDED.** Five models. Makes the model a slicer instead of five columns. |
| `dim_opportunity_stage` | one stage | Order, default probability, closed/won flags. |
| `dim_lost_reason` | one reason | **ADDED.** The note declared the column and never the values. `is_marketing_addressable` separates "sales lost it" from "marketing sent the wrong people". |

## Activity facts (7)

| Table | Grain | Notes |
|---|---|---|
| `fact_ad_performance` | date × creative × device | **Grain of record for paid spend.** Impressions and clicks are derived from spend by the channel's own pricing model, so CTR, CPC and CPM always reconcile. |
| `fact_campaign_daily` | date × campaign | **Derived rollup**, never drawn. Paid spend aggregated up; non-paid channels post directly. Carries leads/MQLs/SQLs from the leads that exist. |
| `fact_web_session` | one session | **SPLIT** from the note's single web table. Carries `anonymous_id` always and `contact_id` only once identified, plus `stitched_at_date`. |
| `fact_web_event` | one event in a session | **SPLIT.** Session metrics are computed from these, so page counts cannot disagree. |
| `fact_email_send` | one recipient per send | **SPLIT.** The note's boolean-flag row cannot represent three clicks or a late unsubscribe. |
| `fact_email_event` | one event | Delivered / Opened / Clicked / Unsubscribed, each with its own date. Clicks are conditional on opens. |
| `fact_lead_activity` | one touch | The identified journey. Ordered, dated, and tied to a campaign that was actually running. |

## Funnel facts (5)

| Table | Grain | Notes |
|---|---|---|
| `fact_lead` | one lead | Lifecycle dates and flags, `lead_score` summed from real activity, `lead_grade`, revenue potential, FK to the opportunity it became. |
| `fact_opportunity` | one opportunity | Amount, stage, probability, cycle days, won/lost, lost reason, `is_hero_journey`. |
| `fact_opportunity_stage` | opportunity × stage | **ADDED SCHEMA.** Entry/exit dates and `days_in_stage`, so stage velocity and stuck-deal analysis work. |
| `fact_attribution_touch` | opportunity × touch × **model** | Long format. Five models. The invariant is asserted by `validate.py`. |
| `fact_marketing_budget` | month × channel × region | **ADDED.** Time-phased plan vs actual. Without it "are we on budget?" is unanswerable. |

## Derived (4)

| Table | Grain | Notes |
|---|---|---|
| `fact_campaign_summary` | one campaign | Cohort economics: CPL, cost per MQL/SQL, CAC, ROAS, ROI, plus `pipeline_maturity_pct` and `is_mature_cohort`. |
| `fact_funnel_snapshot` | month × channel × region × segment | Monthly funnel counts, so the executive trend page is one scan. Reproducible from the facts; `validate.py` checks it. |
| `fact_channel_response_curve` | one channel | **ADDED.** Fitted `a`, `b`, saturation ratio, marginal and average pipeline per dollar, and the solved recommendation. |
| `fact_budget_scenario` | channel × spend multiplier | **ADDED.** ±50% in 5% steps, so what-if is a lookup rather than a solver. |

---

## The joins that matter

```
dim_campaign ──< fact_campaign_daily >── dim_date
      │
      ├──< fact_ad_performance >── dim_ad_creative
      │
      └──< fact_lead >── dim_contact ──< dim_customer ──< dim_geography
                │                              │
                │                              └── dim_segment, dim_industry
                │
                └──< fact_lead_activity            (the journey)
                          │
                          ▼
                   fact_attribution_touch >── dim_attribution_model
                          ▲
                          │
                    fact_opportunity >── dim_sales_rep, dim_lost_reason
                          │
                          └──< fact_opportunity_stage
```

`fact_attribution_touch` is the only table that joins a journey to a deal, and
it is deliberately the widest: it is the one an NLQ engine reaches for when
asked anything about credit.

## What is NOT in here, deliberately

- **No spend on the attribution table.** Joining spend through it multiplies
  spend by the number of touches. Cost comes from the spend tables.
- **No `position_based` attribution model.** It is U-Shaped under another name;
  the design note listed both.
- **No pre-aggregated "channel performance" cube.** Every channel view is a
  join, on purpose — that is the platform argument.
