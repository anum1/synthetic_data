# The sixteen planted events — as measured

Configured magnitudes live in `config/scenario_base.yaml`. **The numbers below
are measured from the generated data**, and where the arithmetic would not
support the configured intent, these are authoritative and the config comment
says why.

Measured on the `small` tier. The `full` tier produces the same numbers — leads,
opportunities and every dollar are identical at both tiers by design; only
behavioural volume changes.

Every one of these is asserted by `src/validate.py`. A planted story that random
noise has swallowed is worse than no story, and the usual way to discover that
is live.

---

## E1 — The money pit

**Enterprise AI Summer Campaign**, LinkedIn, $1.2M over five months.

| | Value |
|---|---|
| Spend | $1,200,000 |
| Leads | 3,133 |
| MQLs | 680 |
| SQLs | **44** |
| Won deals | **5** |
| Revenue | ~$55,000 |
| ROAS | **0.05x** vs 2.09x company |
| Cost per SQL | **$27,273** vs ~$7,000 for its channel |

Buys attention brilliantly — CTR is lifted 45% above its channel — and pipeline
terribly. The gap between the top of the funnel and the bottom is the whole
story, which is why the lift is planted in `fact_ad_performance` and the
collapse in `fact_lead`.

## E2 — The hidden gem

**CFO Analytics Masterclass Series**, Webinar, $150K over nine months.

| | Value |
|---|---|
| Spend | $150,000 |
| Leads | 1,032 |
| SQLs | 264 |
| Won deals | 63 |
| Revenue | ~$1.77M |
| ROAS | **11.8x** vs 2.09x company |

The design note wanted 24x. The first build landed at **40x**, because these
multipliers compound on top of Webinar's already-best channel rates. Past about
15x the room stops believing the dataset, so it is tuned to 12x — still six
times the company average, and still the best campaign by a mile.

## E3 — Attribution divergence

Measured on the two years the demo shows, as a share of attributed revenue:

| Channel | First touch | W-shaped | Last touch |
|---|---:|---:|---:|
| Google Ads | 20.6% | 19.2% | 15.6% |
| Trade Show | 20.3% | 27.9% | **39.6%** |
| LinkedIn | **17.3%** | 14.5% | 9.0% |
| Organic Search | 8.2% | 5.8% | 3.6% |
| Content Syndication | 7.6% | 5.4% | 2.6% |
| Webinar | 5.6% | 8.5% | 12.5% |
| Partner | 5.4% | 6.3% | 7.5% |

Openers (LinkedIn, Facebook, YouTube, Content Syndication) take **2.03x** more
credit under first-touch than last-touch; closers (Webinar, Customer Event,
Trade Show, Partner) take **1.77x** more under last-touch. Largest rank move: 4
places.

**Never drawn.** It emerges from touch ordering — paid social and syndication
open journeys, events and webinars close them — so the attribution chart and any
journey drilled from it always agree.

The total is identical under all five models. Only the split moves.

## E4 — Marketing counts leads, sales counts opportunities

MQL→SQL by channel, trailing twelve months:

| Channel | MQLs | MQL→SQL |
|---|---:|---:|
| Partner | 1,085 | 51.1% |
| Customer Event | 228 | 50.9% |
| Trade Show | 1,856 | 49.1% |
| Organic Search | 3,318 | 43.4% |
| Webinar | 2,874 | 36.4% |
| Google Ads | 6,767 | 34.1% |
| Content Syndication | 3,084 | 17.5% |
| **LinkedIn** | 4,151 | **10.8%** |

A 40-point spread. LinkedIn is second only to Google Ads in MQL volume and last
in quality — which is the cross-functional argument in one table.

## E5 — Lead quality decay

MQL→SQL by quarter of lead date, trailing twelve months:

```
2025 Q3   36.7%
2025 Q4   33.7%
2026 Q1   31.8%
2026 Q2   25.8%
```

The note wanted 34% → 12% in four quarters. That is a company-ending event, not
a marketing problem, and it also collapsed revenue by 15% instead of flattening
it. This acts on MQL→SQL alone, ramping across the trailing twelve months and
normalised so its mean over that window is 1.0 — the slope is unmistakable while
the TTM headline still equals the channel mix.

The current partial quarter is right-censored and is excluded from the chart.

## E6 — APAC is underwater

| Region | TTM spend | TTM revenue | ROAS |
|---|---:|---:|---:|
| North America | $9.73M | $26.07M | **2.68x** |
| EMEA | $5.20M | $9.50M | **1.83x** |
| APAC | $3.47M | $2.48M | **0.71x** |

Below 1.0x is the stronger story: APAC loses money on every dollar. The note's
4.8x / 3.9x / 1.4x could not blend to a 2.1x company average without APAC being
70–85% of total spend.

E16 lands on APAC as well, so the ROAS spread is wider than the configured
quality spread.

## E7 — Product launch

**Agent Studio**, launched nine months before as-of. Awareness lifts three
months *before* the launch; pipeline lifts after. Lead volume for the product
goes from ~530/month to ~2,020/month — a **3.8x** lift — with the two ramps
deliberately offset so the campaign-impact timeline has a shape.

## E8 / E9 — Over-invested and under-invested

| | LinkedIn | Webinar |
|---|---:|---:|
| TTM spend | $4.20M | $1.09M |
| Spend growth YoY | **+42%** | +15% |
| Marginal pipeline per $ | **0.40** | **9.56** |
| Saturation ratio | 3.40 (past inflection) | 0.35 (well below) |
| Solved recommendation | **−$1.68M** | **+$0.43M** |

The recommendation is solved from the response curves, not typed.

## E10 — Junk volume

Content Syndication: 15,914 leads at a $93 CPL — the second-highest lead volume
in the company — converting at 17.5% MQL→SQL for $0.84M of revenue on $1.48M of
spend (0.57x). Marginal return 1.05, saturation 2.90. The channel that wins
every lead-volume slide.

## E11 — Consent-gated reach

| Region | Subscribed contacts |
|---|---:|
| North America | 85.5% |
| APAC | 85.4% |
| **EMEA** | **52.6%** |

A real answer to "why is EMEA email reach lower?" instead of an unexplained dip.
Contacts without consent are never sent to — it is a hard constraint, not a rate.

## E12 — Hero journeys

Five accounts with curated, channel-diverse, 12-touch journeys ending in a won
deal, flagged by `dim_customer.is_hero_account` and
`fact_opportunity.is_hero_journey`. Largest: **$420,000**.

**This is the most important operational event in the dataset.** The journey
page is the wow screen, and a randomly clicked account gives a two-touch journey
and no wow. The heroes are settled from candidates that actually closed
something, so the page always has something worth opening.

## E13 — Saturation

Six of twelve channels are past their inflection point, six are below. Marginal
return is below average return for every channel — diminishing returns hold
everywhere, which is what makes the optimisation page a real optimisation rather
than a ranking.

## E14 — CPL anomaly with a cause

**Retargeting - Pricing Page Q3**, Google Ads, $640K. A lookalike-audience
expansion mid-flight broadens targeting and pushes CPL from ~$111 to **$325**
for two months — a **2.9x** spike — while spend does not move. That is what makes it an
anomaly worth finding rather than a budget change.

It tops the anomaly ranking, and the campaigns beneath it in that ranking are
ordinary noise at 1.6–1.8x, so finding it is a real find.

## E15 — Website conversion drop

Conversion-event rate on `/pricing` and `/demo-request` falls from ~2.3% to
~1.5% for two months, three months before as-of. A broken form: conversion
events on those two pages simply stop firing while traffic continues.

## E16 — Sales execution gap

APAC win rate on closed deals, twelve months either side of the ramp:

```
before   37.9%
after    29.0%
```

Keyed to the **close month**, not the lead month. Keyed to the lead month the
event was invisible in closed deals, because the leads it touched had not closed
yet — a bug the validator caught.

Marketing's numbers for APAC stay healthy while sales stops closing, which is
the separation the cross-functional story needs.
