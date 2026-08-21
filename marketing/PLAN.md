# Marketing Performance & Attribution — review of the design note, and a build plan

> **Status: built.** This plan was executed. The dataset lives in this folder —
> see [README.md](README.md) for how to run it, [docs/DATA_MODEL.md](docs/DATA_MODEL.md)
> for the 33 tables as actually shipped, [docs/EVENTS.md](docs/EVENTS.md) for the
> measured magnitude of each planted event, and
> [docs/KPI_DEFINITIONS.md](docs/KPI_DEFINITIONS.md) for the measurement rules in
> §2.1, §2.5 and §5 as they were finally settled.
>
> Where the built dataset differs from this plan — a **four-year** history rather
> than three (the first year is a warm-up; without it left-censoring made revenue
> growth read +28%), the E5 quality decay **split out of the quality index** into
> its own multiplier on MQL→SQL, the budget reallocation **solved** rather than
> tabulated, and several event magnitudes the arithmetic would not support —
> **the docs are authoritative**.

Review of [marketing_synthetic_data_demo_design.txt](marketing_synthetic_data_demo_design.txt),
plus the plan to generate it in the style of the sibling `sales` (ApexTech),
`supply_chain` (Meridian), `hr_adv` (GlobalTech), `o2c` (Vantage Industrial) and
`p2p` (Norvant Group) projects.

---

## 1. Verdict

**The demo flow is the best thing in the note — keep §19 verbatim as the spine.**
Spend → efficiency decay → channel drill → funnel drill → what-if is a genuine
Performance → Root Cause → Recommendation → Action arc, and it is the arc the
other five datasets in this repo were built around. §16's customer journey page
is the strongest single screen in any of the six design notes.

**The numbers underneath it do not survive contact with a marketer.** Every
headline in §13 contradicts either §15's funnel or §16's journey, and the
contradictions are the kind an audience catches live, not the kind you discover
in QA. The worst one is visible in four seconds of mental arithmetic:

```
$38.7M revenue / 7,000 won deals = $5,529 average deal
```

That is a self-serve SMB motion. The note is otherwise describing ABM, trade
shows, enterprise segments and a $420K opportunity in §16. Both cannot be true.

There is also a structural problem that recurs in five separate places and is
worth naming once, because fixing it is most of the work in §2:

> **The note asserts a headline number *and* asserts the subgroup numbers
> underneath it, and never checks that the subgroups blend to the headline.**
> They don't. Not for geography, not for channel conversion, not for quarterly
> lead quality, not for the budget table.

Generate bottom-up from mix and rates, derive the headline, and assert the blend
in a validator. Everything in §2 follows from that one rule.

Nine things need settling before any code (§2). §3 onward is the plan.

---

## 2. What needs to change before writing any code

### 2.1 The funnel is consumer-scale, the money is enterprise-scale

§13 tiles against §15 funnel and §16 journey:

| Metric | Note | Implied | Problem |
|---|---|---|---|
| CPL | — | **$37.94** | $18.4M / 485K leads. B2B enterprise CPL is $150–$400. |
| Cost per MQL | — | **$130** | Real range $500–$1,500. |
| Avg won deal | — | **$5,529** | §16 shows a $380K deal. |
| Avg opportunity | — | **$5,659** | §16 shows a $420K opportunity. |
| CAC | $1,840 | **$2,629** | $1,840 implies 10,000 new customers; §15 says 7,000 won. |

The money is right. B2B marketing at 2.1x ROAS on $18.4M spend, sourcing $38.7M
of a ~$110M company, is a defensible and unglamorous picture — which is exactly
what makes the demo land. **Keep the money, derive the volumes from deal size.**

Fix: set average won deal from the segment mix, then back out the funnel.

```
Segment mix of won deals: SMB 60% @ $8K, Mid-Market 32% @ $36K, Enterprise 8% @ $140K
                                                      -> avg won deal $27.5K, round to $28K

Revenue        $38.7M  /  $28.0K  =    1,382  won deals
Opportunities  1,382   /  41%     =    3,371   -> avg opp $28.5K, pipeline $96.2M  OK
SQL            3,371   /  38%     =    8,871
MQL            8,871   /  31%     =   28,617   -> cost per MQL $643   OK
Leads         28,617   /  29%     =   98,679   -> CPL $186            OK

Spend $18.4M   Pipeline $96.2M   Revenue $38.7M   ROAS 2.10x   CAC $13,313
```

Every ratio in §15 is preserved. Only the absolute volumes move, by ~4.9x.

Two consequences to state out loud in the docs:

1. **CAC must be labelled `marketing-sourced CAC`** = spend / new logos. $13.3K
   against a $28K ACV is a real, slightly uncomfortable number — good. The
   note's $1,840 is a consumer number and should be deleted.
2. **Enterprise deals are 8% of wins — ~111 a year at $140K mean.** Draw them
   lognormal so the tail reaches $420K and §16's hero journey is a real row in
   the data, not a mock-up.

### 2.2 Row count must come from behaviour, not from leads

§11 sizes `fact_lead` at 500K because §13 said 485K leads. Cutting leads to ~99K
cuts that table by 5x, and the instinct will be to resist. Don't.

**Lead count is a business number and has to be defensible. Web sessions, email
sends and ad impressions are volume and can be as large as you like.** They are
where enterprise scale actually lives, and nobody audits them.

Keep `fact_web_event` at ~5M, `fact_email_event` at ~2M, `fact_ad_performance`
at ~1M. Total lands near 9–10M rows, versus 3.9M for `p2p` — comfortably the
biggest dataset in the repo, without a single indefensible ratio.

### 2.3 Spend is defined in three places and must be defined in one

`dim_campaign.budget`, `fact_campaign_daily.spend` and
`fact_ad_performance.spend` are three independent spend numbers. The first time
two tiles disagree by $40K the demo is over.

- `fact_ad_performance` is the **grain of record** for paid channels.
- `fact_campaign_daily` is a **derived rollup**, produced by aggregation in the
  generator, never drawn independently. Non-paid channels (events, email,
  webinars) post directly to it since they have no ad grain.
- `dim_campaign.budget` is **plan, not actual** — rename it `budget_amount` and
  never sum it against spend without a Plan/Actual label.
- Attribution carries **attributed revenue only**. Never spend. Cost per channel
  comes from the spend tables; joining spend through attribution double-counts.

A validator assertion: `sum(ad_performance.spend) by campaign, month` equals
`fact_campaign_daily.spend` for every paid campaign, to the cent.

### 2.4 Attribution needs an invariant the note never states

§9 gives `attribution_weight` and `attributed_revenue` and six models, but never
says what must be true of them. Without the invariant, the attribution page
produces six different total revenues and Scenario 3 collapses.

**The rule, and it is non-negotiable:**

```
For every (opportunity, model):   sum(attribution_weight) = 1.0 exactly
                                  sum(attributed_revenue) = opportunity.amount (won only)
                                  sum(attributed_pipeline) = opportunity.amount (all)
```

Total revenue is therefore *identical* under every model. Only its distribution
across channels moves. That is the whole point of Scenario 3, and it is far more
impressive when the grand total is visibly pinned while the bars reshuffle.

Two more fixes:

- **U-Shaped and Position Based are the same model.** Drop one. Ship five:
  First Touch, Last Touch, Linear, U-Shaped (40/20/40), W-Shaped (30/30/30/10
  with the SQL-creation touch weighted).
- **Make `dim_attribution_model` a real dimension and store attribution long**,
  one row per (opportunity, touch, model). Not a column per model. It costs 5x
  the rows and buys the single best moment in the demo: the model goes in a
  slicer, and the entire dashboard re-ranks live. That is also the platform
  argument — a pre-aggregated cube cannot do it, because the re-ranking is a
  join, not a filter.

Sizing: 3,371 opps × ~7 touches × 5 models ≈ 118K rows. Cheap.

### 2.5 The sales-cycle lag is the trap that will kill the demo

Revenue attributed to a campaign requires the touch to precede the close by a
full sales cycle. At a 5–9 month B2B cycle, **campaigns from the last two
quarters cannot have closed revenue yet.** Two ways to get this wrong:

- Generate revenue for recent campaigns anyway → the data lies, and the first
  person who checks a close date against a campaign start date sees it.
- Generate it honestly and say nothing → the last two quarters of every ROAS
  chart look catastrophic, and the demo dies on the slide you were proudest of.

**Make it a feature.** Three rules for `docs/KPI_DEFINITIONS.md`:

1. Campaign ROI is always reported on a **cohort** basis — campaigns that
   started in period P, measured to date — never on revenue recognised in P.
2. Every ROI view carries a **pipeline maturity** companion: % of the cohort's
   opportunities still open. Recent cohorts read "72% still in flight", not
   "failed".
3. Tiles are as-of balances, funnel and ROI are cohorts. Never in the same row
   without a label. (Same rule the `p2p` build settled on.)

Then "why does Q2 look worse than Q1?" has an answer — *it hasn't matured yet* —
and that exchange is a better scene than the chart was.

### 2.6 Every subgroup number in §12 sits above the headline

Verified arithmetic:

**Geography (Scenario 6).** NA 4.8x / EU 3.9x / APAC 1.4x cannot blend to 2.1x
unless APAC is ~70–85% of total spend:

| NA/EU/APAC spend split | Blended ROAS |
|---|---|
| 50 / 30 / 20 | 3.85x |
| 34 / 33 / 33 | 3.38x |
| 15 / 15 / 70 | 2.28x |

Fix — **NA 2.6x, EMEA 2.1x, APAC 0.9x at a 50/30/20 spend split = 2.11x.** APAC
below 1.0x is also a stronger story than 1.4x: the region is losing money on
every dollar, not merely underperforming.

**Channel conversion (Scenario 4 / §19).** LinkedIn at 8% MQL→SQL pulls the
blend well under 31% unless the mix is chosen deliberately. A mix that works:

| Channel | Share of MQLs | MQL→SQL |
|---|---:|---:|
| Paid Search | 24% | 34% |
| LinkedIn | 16% | 9% |
| Email nurture | 14% | 30% |
| Organic | 14% | 44% |
| Webinar | 13% | 38% |
| Content Syndication | 7% | 14% |
| Trade Show | 6% | 48% |
| Partner | 4% | 50% |
| Other | 2% | 28% |
| **Blended** | **100%** | **31.3%** |

Also: Scenario 4 says LinkedIn MQL→SQL is 8%, §19 Step 4 says 11%. Pick one — 9%
above, so the story survives either quotation.

**Lead quality decay (Scenario 5).** Q1 34% → Q4 12% blends to 23%, not 31%, and
a 22-point collapse in four quarters is a company-ending event rather than a
marketing insight. Soften to **34% → 29% → 25% → 21%** (blend 27%), confine it to
the current year, and set the §15 headline as the trailing-twelve-month blend so
the two are reconcilable. The story — volume up, quality down, spend up — is
fully intact and considerably more credible.

**Hidden gem (Scenario 2).** $45K spend → $2.8M pipeline → $1.1M revenue is
24x ROAS. Too good; the room stops believing the dataset. Either raise spend to
~$120K (9x) or cut to $1.4M pipeline / $560K revenue (12x). 12x against a 2.1x
company average is still the best campaign by a mile.

### 2.7 The what-if in §17 and §19 needs a model in the data

This is the largest omission. Four of §18's questions — 15, 16, 17, 18 — are
unanswerable from any table in the note. And the two what-if numbers disagree:
§17 promises +$12.4M incremental pipeline, §19 Step 5 promises +$7M for what is
described as the same $1M move.

The §17 table also doesn't balance:

```
Current      $13.3M of $18.4M   -> $5.1M of channels simply unlisted
Recommended  $14.3M             -> a $1.0M budget INCREASE presented as a reallocation
```

Fix in two parts.

**(a) Make the table complete and zero-sum.** List every channel, sum to $18.4M
on both sides. If the recommendation adds budget, label it *"reallocation +
$1.0M incremental ask"* — that is a legitimate CMO output, but it has to be said.

**(b) Add `fact_channel_response_curve`** — a saturation curve per channel per
quarter, fitted by the generator to the spend and pipeline it actually produced:

```
pipeline(spend) = a * ln(1 + spend / b)      marginal = a / (b + spend)
```

LinkedIn is fitted past its inflection (high spend, flat marginal return);
webinars and trade shows sit below theirs. Then:

- "If we cut LinkedIn 20%, what happens to pipeline?" → integrate the curve.
- "Where should we put an extra $1M?" → rank by marginal return.
- "+$7M incremental pipeline" → **falls out of the model** instead of being
  asserted, and survives the follow-up question, which asserted numbers never do.

Store the fitted `a` and `b` plus a pre-computed grid of ±50% spend scenarios in
5% steps, so the BI tool reads it as a lookup and no live solver is needed.

### 2.8 Six tables the model is missing

| Table | Why it's needed |
|---|---|
| `fact_marketing_budget` | Time-phased plan by channel/campaign/quarter. Without it "are we on budget?" — the first question any CMO asks — cannot be answered. `dim_campaign.budget` is a single number with no calendar. |
| `dim_contact` | 50K accounts and ~99K leads means several people per account. The note conflates lead and person. §16's journey is an **account** journey stitched across contacts; that stitch is the enterprise detail competitors don't have. |
| `fact_opportunity_stage` | Listed in §2 with no schema. Needs stage entry/exit dates to support velocity and stuck-deal analysis. Grain: one row per (opportunity, stage) with entered/exited/duration. |
| `dim_content_asset` | Whitepapers, case studies, webinar recordings. §6's "which behaviours predict conversion" is weak without knowing *which asset*. Cheap to add, and it powers a good drill. |
| `dim_lost_reason` | Field exists in §8; values never defined. Needed for "campaigns that generate pipeline but not revenue" (Q10). |
| `fact_channel_response_curve` | §2.7. |

And two schema corrections:

- **`gross_margin_pct` on `dim_product`.** §4 lists both ROAS and ROI as
  computable, but ROI needs margin and the note has none. With it: *"2.1x ROAS
  looks fine — but at 61% gross margin the true marketing ROI is 0.28x."* That
  is a better scene than the ROAS tile it replaces.
- **`geo_key` FK on the facts.** §5 and §10 define `dim_geography` as a
  hierarchy, then `fact_lead` carries loose `country` / `state` text. Use the
  key; keep denormalised labels only if they're generated from it.

### 2.9 Smaller notes

- **Anonymous-to-known stitching.** `fact_web_activity` carries `lead_id`, but
  most sessions are anonymous before the form fill. Add `anonymous_id` and a
  stitch event at form submission, then back-stamp prior sessions. This is what
  makes first-touch attribution honest — the true first touch is almost always
  an anonymous organic session weeks before the lead exists.
- **Split web activity into `fact_web_session` and `fact_web_event`.** One
  session, many events. Session-grain metrics (bounce rate, duration, entry
  page) are wrong when computed off an event table.
- **Split email the same way**: `fact_email_send` (one row per recipient per
  send) and `fact_email_event` (open, click, bounce, unsubscribe). §7's schema
  has boolean flags on one row, which cannot represent three clicks or an
  unsubscribe three weeks later.
- **Consent / suppression.** Add `consent_status` and `suppression_date` on
  `dim_contact`. Supports "why is EMEA email reach lower?" — a consent-gated
  list — which is a real and topical answer.
- **Anchor the calendar to today.** §11 hardcodes 2024 / 2025 / 2026 YTD. Today
  is August 2026; that dataset is stale in January. Every sibling anchors as-of
  to the last complete month and times events in months relative to it. Do the
  same here.
- **Two size tiers, one seed.** `small` for Tableau / Power BI Desktop, `full`
  for Snowflake / Databricks / Incorta. A 10M-row dataset will not open in
  Power BI Desktop, and that is the tool most often on the demo laptop. This is
  the house convention (`p2p`, `o2c`) and the note omits it.
- **Scenario 1's $1.2M campaign** is 6.5% of annual spend in one campaign —
  aggressive but fine. Keep it. Give it a real reason for failing (broad
  targeting, a lookalike audience expansion mid-flight) so the drill has an
  answer, not just a bad number.

---

## 3. Decisions to take before Phase 0

1. **Company name and product line.** Siblings use invented names (Norvant,
   Meridian, Vantage). Needs one — nothing that collides with a real trademark.
2. **Average deal size $28K** (§2.1) — the single most load-bearing number. Every
   volume in the dataset derives from it.
3. **Is marketing-sourced revenue all revenue, or a share of it?** Recommend a
   share: marketing sources 34% of a ~$114M company. It lets the CMO page show
   "marketing-sourced vs marketing-influenced vs sales-sourced", which is how
   the argument actually goes in a real QBR.
4. **Five attribution models, long format** (§2.4).
5. **Region split 50 / 30 / 20** NA / EMEA / APAC by spend (§2.6).
6. **Sales cycle distribution** — recommend lognormal, median 142 days, p90 at
   ~310, varying by segment (SMB 45d, Enterprise 260d median).

---

## 4. Revised data model — ~31 tables

**Dimensions (16)**
`dim_date`, `dim_channel`, `dim_campaign`, `dim_ad_creative`, `dim_customer`
(account), `dim_contact`, `dim_product`, `dim_sales_rep`, `dim_geography`,
`dim_industry`, `dim_segment`, `dim_attribution_model`, `dim_lead_source`,
`dim_content_asset`, `dim_opportunity_stage`, `dim_lost_reason`

**Facts — activity (7)**
`fact_ad_performance` (grain of record for paid), `fact_campaign_daily`
(derived rollup), `fact_email_send`, `fact_email_event`, `fact_web_session`,
`fact_web_event`, `fact_lead_activity`

**Facts — funnel (5)**
`fact_lead`, `fact_opportunity`, `fact_opportunity_stage`,
`fact_attribution_touch`, `fact_marketing_budget`

**Derived / snapshot (3)**
`fact_funnel_snapshot` (monthly stage counts, for cohort trending),
`fact_campaign_summary` (campaign-cohort ROI with maturity),
`fact_channel_response_curve`

---

## 5. Architecture

A **lead-lifecycle state machine**, mirroring the document-lifecycle approach
`p2p` and `o2c` use. Generate forward through the funnel, never backwards:

```
budget -> campaign -> ad impressions -> sessions (anonymous)
                                            |
                                     form fill / stitch
                                            v
                                      contact + lead
                                            |
                          score accumulates from activity
                                            v
                                     MQL -> SQL -> opportunity
                                            |
                                     stage progression
                                            v
                                    won / lost -> revenue
                                            |
                             attribution replayed over touch history
                                            v
                              response curves fitted to the result
```

Two rules make this work:

- **Attribution and response curves are computed last, from the generated
  history.** Never drawn. If attribution is drawn, it won't reconcile to
  opportunity amounts and §2.4's invariant fails.
- **Lead score is accumulated from actual activity rows** (pricing page view
  +15, demo request +40, whitepaper +5), not sampled. Then Q14 — "which
  touchpoints are most predictive?" — has a true answer sitting in the data, and
  the drill from score to the activities that produced it always reconciles.

### Layout

```
marketing/
  PLAN.md
  README.md
  marketing_synthetic_data_demo_design.txt
  config/scenario_base.yaml        every number in §2 as a knob
  src/                             generate.py, validate.py, run_questions.py,
                                   emit_ddl.py + one module per subsystem
  sql/snowflake/  sql/databricks/  DDL + load
  data/small/  data/full/          parquet + csv
  docs/DATA_MODEL.md  EVENTS.md  KPI_DEFINITIONS.md  DEMO_FLOWS.md
```

---

## 6. Demo flow — what to change in §19

§19 is right and should be built as written, with three additions:

- **Fold Scenario 3 (attribution) in as Step 4b.** It currently sits alone in
  §12 as a curiosity. Placed right after the funnel drill, it is the moment the
  platform argument lands: change the model in a slicer, watch every channel
  re-rank, note the grand total never moves. A cube cannot do that.
- **Add Step 6 — act.** The arc currently ends at a what-if number. End it at a
  decision with an owner and a review date. That is the difference between a
  dashboard demo and a management demo.
- **Hand-build 3–5 hero accounts for §16.** This is the most important
  operational note in the whole plan. The customer journey page is the wow
  screen, and if the presenter clicks a random account they will get a two-touch
  journey and the wow evaporates. Curate a handful — 7 to 11 touches, spanning
  channels, crossing two contacts at the same account, ending in a $420K win —
  and pin them at the top of the account selector by a `is_hero_journey` flag.

§18's four anomaly-detection questions (19–22) have no page to live on. Either
add a sixth screen or drop them; a question the dashboard cannot reach is worse
than one you never promised.

---

## 7. Target headline

```
Marketing spend TTM   Leads     MQLs      Pipeline   Marketing-sourced revenue
$18.4M                98.7K     28.6K     $96.2M     $38.7M
+24% YoY              +31%      +18%      +8%        +3%

CPL      Cost/MQL   MQL->SQL   ROAS   Marketing ROI   Marketing CAC
$186     $643       31.3%      2.10x  0.28x @ 61% GM  $13,313
```

The YoY row is the demo. Spend +24%, revenue +3% — every step down the funnel is
worse than the one above it, and the dataset has to make that visible before
anyone asks.

```
Region     Spend   ROAS        Channel     Spend YoY   Revenue YoY
NA         50%     2.6x        LinkedIn      +48%         +6%
EMEA       30%     2.1x        Webinar       +12%        +41%
APAC       20%     0.9x   <-   Trade Show     +4%        +22%
                   underwater  Content Synd  +31%         -8%
```

---

## 8. Build phases

| Phase | Output | Gate |
|---|---|---|
| 0 | `config/scenario_base.yaml`, `docs/KPI_DEFINITIONS.md` | §2.1 volumes and §2.5 cohort rules settled in writing first |
| 1 | Dimensions + calendar anchoring | Hierarchies navigable; geo keys on every fact |
| 2 | Budget, campaigns, ad performance, campaign_daily rollup | §2.3 spend reconciles to the cent |
| 3 | Web sessions/events, email send/events, anonymous stitch | Session and event grains agree |
| 4 | Contacts, leads, scoring from activity, MQL/SQL | Blended rates match §2.6 mix table |
| 5 | Opportunities, stages, revenue, segment mix | Avg deal $28K; §7 headline reproduced |
| 6 | Attribution replay, 5 models | §2.4 invariant holds for every opportunity |
| 7 | Response curves, scenario grid, hero journeys | §19 Step 5 number falls out of the curve |
| 8 | `validate.py`, `run_questions.py`, DDL, docs | All 25 questions return non-empty, sane answers |

### Acceptance criteria

1. Every §2.6 subgroup number blends to its headline, asserted in `validate.py`.
2. Spend reconciles across `ad_performance` → `campaign_daily` → campaign totals.
3. Attribution sums to opportunity amount under all five models, per opportunity.
4. No opportunity closes before its first campaign touch. No revenue attributed
   to a campaign that started after the close date.
5. Every planted scenario is **measured** and written into `docs/EVENTS.md` with
   its actual magnitude — not its intended one. Where the arithmetic won't
   support the intent, the docs are authoritative and the note gets amended.
6. All 25 questions in §18 answer from the shipped tables, or are removed.

---

## 9. Summary of what changes from the design note

| # | Change | Severity |
|---|---|---|
| 1 | Funnel volumes ÷4.9; leads 485K → 98.7K; deal size drives everything | **Blocking** |
| 2 | CAC $1,840 → $13,313, relabelled marketing-sourced | **Blocking** |
| 3 | One spend source of truth; `campaign_daily` becomes derived | **Blocking** |
| 4 | Attribution invariant + long format + `dim_attribution_model`; 6 models → 5 | **Blocking** |
| 5 | Cohort/maturity rules for the sales-cycle lag | **Blocking** |
| 6 | Geography 4.8/3.9/1.4x → 2.6/2.1/0.9x | High |
| 7 | Channel mix table that blends to 31% | High |
| 8 | Lead-quality decay 34→12% softened to 34→21%, current year only | High |
| 9 | Add response-curve table; §17 table made zero-sum; one what-if number | High |
| 10 | Add budget, contact, opp_stage, content_asset, lost_reason tables | High |
| 11 | Add `gross_margin_pct`; ROI ≠ ROAS | Medium |
| 12 | Split web and email into session/event grains; anonymous stitch | Medium |
| 13 | Hero journeys hand-built and flagged | Medium |
| 14 | Anchor calendar to today; two size tiers | Medium |
| 15 | Scenario 2 hidden gem 24x → 12x | Low |
| 16 | Anomaly questions get a page or get cut | Low |
