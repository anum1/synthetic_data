# Demo flows

Six flows. Flow 1 is the fifteen-minute executive run and is the spine — it is
the design note's §19 arc, with three additions: the attribution scene folded
in where it belongs, a what-if that comes from a model, and an ending that is a
decision rather than a number.

All figures are measured from the `small` tier. Both tiers produce identical
business numbers.

**Say this in the first thirty seconds**: tiles are trailing twelve months,
revenue is counted when a deal *closes*, and a deal closes six to nine months
after the campaign that sourced it. Everything else follows from that.

---

## Flow 1 — The fifteen-minute executive run

### Scene 1 — the tiles (30 seconds)

```
Marketing spend TTM   Leads     MQLs      Pipeline created   Marketing-sourced revenue
$18.4M                90.3K     27.3K     $84.3M             $38.1M

CPL     Cost/MQL   MQL->SQL   ROAS     Marketing ROI     Marketing-sourced CAC
$204    $674       30.8%      2.07x    0.26x @ 60.8% GM  $13,450
```

Two things to point at:

- **ROAS 2.07x looks fine. Marketing ROI is 0.26x.** Twenty-six cents of gross
  profit per dollar spent, before any sales cost. Most marketing dashboards
  cannot show this because they carry no margin. (Q2)
- **CAC is marketing-sourced** — spend over new logos. Say so, or someone will
  compare it to a fully-loaded number.

### Scene 2 — the question that matters (Q23)

> *"Is marketing actually getting more efficient?"*

```
Spend              +24.0%
Leads              +16.3%
MQLs               +11.6%
Pipeline created    +3.8%     (both sides lagged two months - see KPI §1)
Revenue             +8.8%
```

Spend is growing six times faster than the pipeline it buys, and every step from
spend down to new pipeline is worse than the one above it.

Revenue is the exception, and the reason is worth saying out loud, because
someone will ask: **revenue lags**. The deals closing now were sourced eighteen
months ago, out of cohorts that were smaller but converted better. So:

> *We are still collecting revenue from pipeline we built last year. The
> pipeline we are building this year is flat.*

**That is the demo.** Everything after this is finding out why.

### Scene 3 — drill into channels (Q2, Q7)

| Channel | TTM spend | Leads | MQL→SQL | Revenue | ROAS |
|---|---:|---:|---:|---:|---:|
| **LinkedIn** | **$4.20M** | 12,931 | **10.8%** | $1.05M | **0.25x** |
| Google Ads | $3.75M | 24,213 | 34.1% | $6.15M | 1.64x |
| Trade Show | $3.36M | 4,144 | 49.1% | $6.60M | 1.97x |
| Content Syndication | $1.48M | 15,914 | 17.5% | $0.84M | 0.57x |
| **Webinar** | **$1.09M** | 5,725 | 36.4% | $7.14M | **6.57x** |
| **Organic Search** | **$1.00M** | 9,197 | 43.4% | $7.34M | **7.34x** |

The largest line in the budget returns 25 cents on the dollar. The two smallest
return six and seven times their spend. Content Syndication is the second-biggest lead
source in the company and the second-worst return — the channel that wins every
lead-volume slide.

### Scene 4 — drill into the funnel (Q7)

Marketing and sales are both right, about different things:

```
                 leads     MQL->SQL
LinkedIn        12,931       10.7%
Trade Show       4,144       49.1%
Partner          2,073       51.1%
```

LinkedIn generates three times the leads of trade shows and a fifth of the
qualification rate. *"Marketing generated 12,931 leads"* and *"trade shows are
where our opportunities come from"* are both true.

### Scene 5 — the attribution slicer (Q11) — **the platform moment**

Put `dim_attribution_model` in a slicer. Change it. Watch:

| Channel | First touch | W-shaped | Last touch |
|---|---:|---:|---:|
| Google Ads | 20.6% | 19.2% | 15.6% |
| Trade Show | 20.3% | 27.9% | **39.6%** |
| **LinkedIn** | **17.3%** | 14.5% | **9.0%** |
| Organic Search | 8.2% | 5.8% | 3.6% |
| Content Syndication | 7.6% | 5.4% | 2.6% |
| Webinar | 5.6% | 8.5% | 12.5% |

Then say the important part:

> **The grand total never moves.** Every model attributes exactly the same
> total. Only the credit moves.

LinkedIn is worth 17% of revenue if you believe first touch and 9% if you
believe last touch. Trade Show goes the other way: 20% to 40%. Both are defensible; the honest read is the W-shaped middle.

This is also the platform argument, and it should be made explicitly:
re-ranking every channel when the model changes is a **join**, not a filter. A
pre-aggregated cube cannot do it.

### Scene 6 — the what-if (Q15, Q16, Q18)

> *"So what do I do about LinkedIn?"*

Marginal return, from curves fitted to each channel's own observed spend and
pipeline:

| Channel | TTM spend | Marginal pipeline / $ | Saturation |
|---|---:|---:|---:|
| Organic Search | $1.00M | **12.18** | 0.62 |
| Webinar | $1.09M | **9.56** | 0.35 |
| Partner | $0.89M | 8.29 | 0.48 |
| Google Ads | $3.75M | 3.27 | 1.05 |
| Content Syndication | $1.48M | 1.05 | 2.90 |
| **LinkedIn** | **$4.20M** | **0.40** | **3.40 (past inflection)** |

The next LinkedIn dollar buys 40 cents of pipeline. The next webinar dollar
buys $9.56. Then run the reallocation — **solved**, not typed, zero-sum, capped
at ±40% movement per channel:

```
LinkedIn             -$1.68M
Content Syndication  -$0.59M
YouTube              -$0.29M
Facebook             -$0.23M
Direct Mail          -$0.10M
                    ---------
Trade Show           +$0.65M
Google Ads           +$0.62M
Webinar              +$0.43M
Organic Search       +$0.40M
Email                +$0.36M
Partner              +$0.36M
Customer Event       +$0.08M
```

Net spend change: **zero**. Net pipeline change: **positive, and read off the
model** — Q18 computes it from `fact_budget_scenario`, not from a slide.

### Scene 7 — end on a decision, not a number

> *"Move $1.68M out of LinkedIn over two quarters. Webinars and partner take
> the first $0.8M. Review at the end of Q1 against MQL→SQL, not lead volume."*

That last clause is the whole demo in one sentence: **the metric that was
driving the wrong decision was lead volume.**

---

## Flow 2 — Lead quality is deteriorating (Q8, Q14)

MQL→SQL by quarter of lead date:

```
2025 Q3   36.7%
2025 Q4   33.7%
2026 Q1   31.8%
2026 Q2   25.8%
```

Volume up 16%, quality down 11 points. Then ask *which behaviours actually
predict conversion* (Q14) — `lead_score` is summed from real activity rows, so
the drill from a score to the touches that produced it always reconciles.

Note the current partial quarter is excluded: its MQLs have not had time to
become SQLs. Saying that out loud is better than being asked.

---

## Flow 3 — The money pit and the hidden gem (Q3, Q4, Q5)

| Campaign | Spend | Leads | SQLs | Won | Revenue | ROAS |
|---|---:|---:|---:|---:|---:|---:|
| Enterprise AI Summer Campaign | $1,200,000 | 3,133 | 44 | 5 | $55K | **0.05x** |
| CFO Analytics Masterclass Series | $150,000 | 1,032 | 264 | 63 | $1.77M | **11.80x** |

The flagship's click-through rate is *above* its channel average — it buys
attention brilliantly. Cost per SQL is $27,273 against roughly $7,000 for its
channel. The masterclass costs an eighth as much and produces six times the
SQLs.

Then filter `is_mature_cohort = 0` and show the young campaigns being judged on
nothing: a campaign three months old has closed almost nothing, and its ROAS is
not a verdict.

---

## Flow 4 — The customer journey (Q25) — **the wow page**

Pick any account where `is_hero_account = 1`. Five are curated, 12 touches each,
spanning channels and multiple contacts at the same account, ending in a won
deal. The largest is **$420,000**.

A journey runs like:

```
Organic Search   ->  whitepaper download        (anonymous, 8 months out)
LinkedIn         ->  ad click
Content Synd.    ->  case study download
Email            ->  nurture click              <- form fill: STITCHED here
Google Ads       ->  pricing view
Webinar          ->  attendance                 <- SQL created
Trade Show       ->  booth visit
Partner          ->  demo request
                 ->  Closed Won  $420,000
```

Three things to point at:

1. **The first touch is anonymous and predates the lead record.** Sessions carry
   `anonymous_id` always and `contact_id` only once identified, with
   `stitched_at_date` recording the join. Attribution that can only see
   post-form touches is quietly lying about first touch.
2. **The journey spans several people at the account.** That is why
   `dim_contact` is separate from `dim_customer`, and why attribution is
   gathered at account level.
3. **The W-shaped weights on screen sum to exactly 1.0.** Add them up live.

---

## Flow 5 — Geography (Q24, Q20)

| Region | TTM spend | TTM revenue | ROAS |
|---|---:|---:|---:|
| North America | $9.73M | $26.07M | 2.68x |
| EMEA | $5.20M | $9.50M | 1.83x |
| **APAC** | **$3.47M** | **$2.48M** | **0.71x** |

APAC loses money on every dollar. Then split the cause, because there are two
and they are different problems:

- **Marketing**: APAC CPL is highest and its conversion lowest.
- **Sales**: APAC win rate on closed deals fell from **37.9% to 29.0%** over the
  last eight months (Q20), while marketing's APAC numbers held.

That separation — good leads, worse closing — is the cross-functional
conversation, and it is the one a single ROAS tile cannot start.

---

## Flow 6 — Anomalies (Q19, Q22)

Two planted anomalies, each with a cause a person can act on:

- **Retargeting - Pricing Page Q3** — CPL spikes from ~$111 to **$325** for two
  months, a 2.9x jump, while spend does not move. Cause: a lookalike-audience
  expansion mid-flight broadened targeting. The campaigns below it in the
  ranking sit at 1.6–1.8x, which is ordinary noise, so this is a real find
  rather than the only row in the table.
- **/pricing and /demo-request** — conversion-event rate falls from ~2.3% to
  ~1.5% for two months while traffic continues. Cause: a broken form.

Both are the shape of question an AI analyst is good at and a static dashboard
is not: nobody built a tile for either.

---

## What not to do

- **Do not click a random account on the journey page.** Filter to
  `is_hero_account = 1` first.
- **Do not show campaign ROAS without maturity.** Recent cohorts read as
  failures. Use `is_mature_cohort` or show `pipeline_maturity_pct` beside it.
- **Do not put a TTM tile next to a YTD tile** without labelling both.
- **Do not sum spend through `fact_attribution_touch`.** It multiplies spend by
  the number of touches. Cost comes from the spend tables.
