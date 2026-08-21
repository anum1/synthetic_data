# KPI definitions

Every number in this dataset has one definition and one denominator. Where the
design note left a metric ambiguous, the decision is recorded here and the
generator, the validator and `sql/demo_questions.sql` all follow it.

Read §1 before building anything. It is the rule that keeps the dashboard
honest, and it is the one the original design note did not have.

---

## 1. Period, cohort, and the sales-cycle lag

An opportunity closes a full sales cycle after the lead that created it. The
median cycle here is about two months blended, and 260 days for Enterprise. So
a deal closing this month was sourced by a campaign that ran six to nine months
ago.

That single fact forces three rules.

**Rule 1 — every measure declares its date.**

| Measure | Counted on |
|---|---|
| Spend, impressions, clicks | activity date |
| Leads, MQLs, SQLs | the date that stage was reached |
| Pipeline created | opportunity **created** date |
| Revenue, win rate, deal size | opportunity **close** date |
| Open pipeline, AP-style balances | as-of date |

Never mix them in one row of tiles without a label. "TTM revenue" and "pipeline
created TTM" are different populations, and the difference is not an error.

**Rule 2 — campaign ROI is a cohort measure and travels with its maturity.**

`fact_campaign_summary` carries `pipeline_maturity_pct` (closed opportunities /
all opportunities) and `is_mature_cohort` (started at least median-cycle +
one quarter ago, ~9 months). A campaign younger than that has not had time to
close anything, and its ROAS is not evidence.

Filter `is_mature_cohort = 1` in any "which campaigns worked" view. Show
`pipeline_maturity_pct` in any view that does not. A recent cohort reads
*"72% still in flight"*, not *"failed"* — and saying that out loud is a better
moment than the chart it replaces.

**Rule 3 — the recent edge is right-censored, in both directions.**

- The current partial quarter has MQLs that have not had time to become SQLs.
  Charts of MQL→SQL by quarter exclude it (see Q8).
- Pipeline creation is short for the last two months for the same reason.
  Year-over-year comparisons of pipeline created lag **both** sides by two
  months so they are like-for-like (see Q23).
- The dataset carries a **warm-up year** at the start of history that the demo
  never measures. Without it the earliest close quarters cannot contain
  long-cycle deals — long cycles are big deals — so average deal size ramps
  across the window and revenue growth reads +28% when it is really +4%.

---

## 2. Spend has one source of truth

| Table | Role |
|---|---|
| `fact_ad_performance.spend_usd` | **Actual.** Grain of record for paid channels. |
| `fact_campaign_daily.spend_usd` | **Derived.** Rollup of the above, plus non-paid channels posting directly. Never drawn. |
| `fact_marketing_budget.budget_amount_usd` | **Plan.** Quarterly, time-phased, set before the quarter. |
| `dim_campaign.budget_amount_usd` | **Plan.** Campaign-level approval. Never summed against actuals without a Plan/Actual label. |

`validate.py` asserts the ad grain rolls up to `fact_campaign_daily` to the cent.

Attribution carries **attributed revenue and pipeline only, never spend**.
Joining spend through the attribution table multiplies it by the number of
touches. Cost per channel comes from the spend tables.

---

## 3. Funnel rates

All four are computed on the trailing twelve months by lead date.

```
lead -> MQL   =  MQLs / leads
MQL  -> SQL   =  SQLs / MQLs
SQL  -> opp   =  sales-accepted / SQLs
opp  -> won   =  won deals / opportunities created
```

These are **derived from the channel mix**, never configured next to it. Change
a channel's rate in `config/scenario_base.yaml` and the blended headline moves;
`validate.py` asserts the generated data matches what the mix implies. The
company blend is whatever the mix produces — it is not a target.

---

## 4. Cost and return

```
CPL              = spend / leads
Cost per MQL     = spend / MQLs
Cost per SQL     = spend / SQLs
CAC              = spend / won deals          <- marketing-sourced CAC
ROAS             = revenue / spend
Marketing ROI    = (revenue x gross margin - spend) / spend
Pipeline per $   = pipeline created / spend
```

**CAC here is marketing-sourced CAC**: marketing spend over new logos marketing
sourced. It excludes sales cost, so it is not fully-loaded CAC and must be
labelled. The design note's $1,840 implied 10,000 new customers a year against
a funnel producing 1,400 — a self-serve number on an enterprise motion.

**ROAS and ROI are not the same metric.** ROAS ignores cost of goods. At a
blended 60.8% gross margin, a 2.0x ROAS is a marketing ROI of about 0.2x —
twenty cents of gross profit per dollar spent, before any sales cost. Both are
in `fact_campaign_summary`; show them side by side.

---

## 5. Attribution

Five models: First Touch, Last Touch, Linear, U-Shaped (40/20/40) and W-Shaped
(30/30/30/10, the middle anchor being the touch at SQL creation).

U-Shaped and Position Based are the same model. The note listed both; only one
ships.

**The invariant**, asserted by `validate.py` for every opportunity:

```
sum(attribution_weight)      = 1.0
sum(attributed_pipeline_usd) = opportunity.amount_usd
sum(attributed_revenue_usd)  = opportunity.won_amount_usd
```

So **total attributed revenue is identical under all five models**. Only the
distribution across channels moves. Put `dim_attribution_model` in a slicer and
watch the channel ranking re-order while the grand total does not move — that
is the point, and it is also the platform argument, because re-ranking on the
fly is a join and a pre-aggregated cube cannot do joins.

Journeys are gathered at **account** level over the 365 days before the
opportunity opened, capped at the most recent 12 touches. B2B buying is a
committee; a single contact's touches are not the journey.

---

## 6. Response curves and what-if

```
pipeline(spend) = a * ln(1 + spend / b)
marginal(spend) = a / (b + spend)
saturation      = spend / b        > 1 means past the inflection point
```

`a` is fitted so each channel's curve passes **exactly through its observed
(spend, pipeline) point**, so at current spend the model reproduces the actuals
and only extrapolates as the slider moves.

`fact_budget_scenario` pre-computes +/-50% in 5% steps so any BI tool can answer
"what if we cut LinkedIn 20%" with a lookup rather than a solver.

`recommended_spend_usd` is **solved**, not typed: constrained water-filling
across the curves at a fixed total budget, capped at +/-40% movement per channel
per cycle. It is exactly zero-sum, and `validate.py` checks that it is. The
design note's table summed to $13.3M current against $14.3M recommended — a $1M
budget increase presented as a reallocation.

---

## 7. Lead score

`fact_lead.lead_score` is the **sum of points from the lead's real activity
rows**, using the weights in `dim_activity_type`. It is never sampled. So the
drill from a score to the behaviours that produced it always reconciles, and
"which touchpoints predict conversion" has a true answer in the data rather
than a plausible-looking one.

`lead_grade` buckets it: D (0-20), C (21-45), B (46-90), A (91+).

---

## 8. Segment mix

The share of **won deals** each segment holds is derived, not configured. A
segment's quality multiplier applies at four funnel steps, so its share of won
deals moves as roughly the cube of it:

```
won_share(segment)  ∝  lead_share x quality_mult^3
```

Enterprise is ~3% of accounts, ~5.5% of leads, ~8% of won deals and ~44% of
revenue. That shape is the real shape of B2B, and it is a good question in its
own right: *why does 60% of the budget chase the segment that produces 15% of
the revenue?*
