"""Reference dimensions: geography, product, channel, segment and the small
policy tables the funnel is measured against.

Two of these exist only because the design note was missing them and the demo
cannot answer its own questions without them (PLAN 2.8):

  dim_attribution_model  - so the model becomes a SLICER rather than five
                           columns. Putting it in a slicer is the single best
                           moment in the demo, because re-ranking every channel
                           on the fly is a join, and a pre-aggregated cube
                           cannot do joins.
  dim_lost_reason        - the note declared the column and never the values,
                           which leaves Q10 ("pipeline but not revenue")
                           unanswerable.

`dim_product.gross_margin_pct` is the other repair: the note listed ROI as
computable but carried no margin anywhere, so ROI and ROAS were the same
number. They are not, and the gap between them is a better tile than either.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mktconfig import Scenario

# Country -> (region, sub-region, currency, ISO). Weight is share of that
# region's activity.
COUNTRIES = [
    ("United States", "North America", "US & Canada", "USD", "USA", 0.86),
    ("Canada",        "North America", "US & Canada", "CAD", "CAN", 0.14),
    ("United Kingdom", "EMEA", "Northern Europe", "GBP", "GBR", 0.27),
    ("Germany",        "EMEA", "Central Europe",  "EUR", "DEU", 0.24),
    ("France",         "EMEA", "Western Europe",  "EUR", "FRA", 0.16),
    ("Netherlands",    "EMEA", "Western Europe",  "EUR", "NLD", 0.09),
    ("Sweden",         "EMEA", "Nordics",         "SEK", "SWE", 0.07),
    ("Spain",          "EMEA", "Southern Europe", "EUR", "ESP", 0.07),
    ("United Arab Emirates", "EMEA", "Middle East", "AED", "ARE", 0.06),
    ("South Africa",   "EMEA", "Africa",          "ZAR", "ZAF", 0.04),
    ("Australia",  "APAC", "ANZ",           "AUD", "AUS", 0.26),
    ("Singapore",  "APAC", "Southeast Asia", "SGD", "SGP", 0.20),
    ("Japan",      "APAC", "North Asia",    "JPY", "JPN", 0.18),
    ("India",      "APAC", "South Asia",    "INR", "IND", 0.17),
    ("South Korea", "APAC", "North Asia",   "KRW", "KOR", 0.10),
    ("New Zealand", "APAC", "ANZ",          "NZD", "NZL", 0.09),
]

# State/city only where the demo drills - the note's §10 hierarchy example.
STATES = {
    "United States": [("California", ["San Francisco", "Los Angeles", "San Diego"], 0.24),
                      ("Texas", ["Austin", "Dallas", "Houston"], 0.18),
                      ("New York", ["New York", "Buffalo"], 0.16),
                      ("Illinois", ["Chicago"], 0.10),
                      ("Massachusetts", ["Boston"], 0.09),
                      ("Washington", ["Seattle"], 0.08),
                      ("Georgia", ["Atlanta"], 0.08),
                      ("Colorado", ["Denver"], 0.07)],
    "Canada": [("Ontario", ["Toronto", "Ottawa"], 0.55),
               ("British Columbia", ["Vancouver"], 0.27),
               ("Quebec", ["Montreal"], 0.18)],
    "United Kingdom": [("England", ["London", "Manchester"], 0.82),
                       ("Scotland", ["Edinburgh"], 0.18)],
    "Germany": [("Bavaria", ["Munich"], 0.38), ("Hesse", ["Frankfurt"], 0.34),
                ("Berlin", ["Berlin"], 0.28)],
    "Australia": [("New South Wales", ["Sydney"], 0.52),
                  ("Victoria", ["Melbourne"], 0.48)],
    "India": [("Maharashtra", ["Mumbai", "Pune"], 0.46),
              ("Karnataka", ["Bengaluru"], 0.54)],
}


def build_dim_geography(s: Scenario) -> pd.DataFrame:
    """Global -> Region -> Sub-region -> Country -> State -> City.

    One row per city, keyed. Facts carry `geo_key`, never loose country text -
    the note declared this hierarchy in §10 and then put `country` and `state`
    strings on `fact_lead`, which makes the hierarchy undrillable. (PLAN 2.8)
    """
    rows = []
    for country, region, sub, ccy, iso, cweight in COUNTRIES:
        states = STATES.get(country, [(country, [_capital(country)], 1.0)])
        for state, cities, sweight in states:
            for city in cities:
                rows.append({
                    "geo_hierarchy": "Global", "region_name": region,
                    "sub_region_name": sub, "country_name": country,
                    "country_iso3": iso, "local_currency_code": ccy,
                    "state_province": state, "city_name": city,
                    "_weight": cweight * sweight / len(cities),
                })
    df = pd.DataFrame(rows)
    df.insert(0, "geo_key", np.arange(1, len(df) + 1))
    df["geo_path"] = (df["region_name"] + " > " + df["country_name"]
                      + " > " + df["state_province"] + " > " + df["city_name"])
    return df


def _capital(country: str) -> str:
    return {"France": "Paris", "Netherlands": "Amsterdam", "Sweden": "Stockholm",
            "Spain": "Madrid", "United Arab Emirates": "Dubai",
            "South Africa": "Johannesburg", "Singapore": "Singapore",
            "Japan": "Tokyo", "South Korea": "Seoul",
            "New Zealand": "Auckland"}.get(country, country)


def build_dim_channel(s: Scenario) -> pd.DataFrame:
    """One row per channel, carrying its planned economics.

    The rates live here as well as in the config so the dashboard can show
    "planned vs actual CPL" without the author retyping the plan into a
    measure. They are the plan; `fact_campaign_daily` is the actual.
    """
    rows = []
    for i, (name, c) in enumerate(s.channels.items(), start=1):
        rows.append({
            "channel_id": i, "channel_name": name,
            "channel_group": c["group"],
            "is_paid_media": int(bool(c["paid"])),
            "is_digital": int(name not in ("Trade Show", "Customer Event",
                                           "Direct Mail", "Partner")),
            "planned_spend_share": round(float(c["spend_share"]), 4),
            "planned_cpl_usd": float(c["cpl_usd"]),
            "planned_lead_to_mql": float(c["lead_to_mql"]),
            "planned_mql_to_sql": float(c["mql_to_sql"]),
            "planned_sql_to_opp": float(c["sql_to_opp"]),
            "planned_opp_to_won": float(c["opp_to_won"]),
            # Back-filled from fact_channel_response_curve after the curves are
            # fitted - it is a solved number, not a configured one.
            "recommended_spend_usd": 0.0,
        })
    df = pd.DataFrame(rows)
    ttm = float(s.spend["ttm_total_usd"])
    df["planned_spend_usd"] = (df["planned_spend_share"] * ttm).round(2)
    df["recommended_delta_usd"] = (df["recommended_spend_usd"]
                                   - df["planned_spend_usd"]).round(2)
    return df


def build_dim_segment(s: Scenario) -> pd.DataFrame:
    rows = []
    for i, (name, v) in enumerate(s.segments.items(), start=1):
        mix = s.deal["segment_mix"][name]
        rows.append({
            "segment_id": i, "segment_name": name,
            "employee_band": {"SMB": "1-200", "Mid-Market": "201-2,000",
                              "Enterprise": "2,001+"}[name],
            "annual_revenue_band": {"SMB": "< $50M", "Mid-Market": "$50M - $1B",
                                    "Enterprise": "> $1B"}[name],
            "planned_account_share": float(v["account_share"]),
            "planned_lead_share": float(v["lead_share"]),
            "planned_won_share": round(s.funnel.segment_won_share[name], 4),
            "target_deal_size_usd": float(mix["mean_usd"]),
            "median_sales_cycle_days": int(v["cycle_days_median"]),
        })
    return pd.DataFrame(rows)


def build_dim_industry(s: Scenario) -> pd.DataFrame:
    rows = [{"industry_id": i, "industry_name": n,
             "industry_sector": _sector(n), "lead_share": float(w)}
            for i, (n, w) in enumerate(s.industries.items(), start=1)]
    return pd.DataFrame(rows)


def _sector(name: str) -> str:
    return {"Manufacturing": "Industrials", "Energy": "Industrials",
            "Financial Services": "Financials", "Technology": "Technology",
            "Telecommunications": "Technology", "Retail": "Consumer",
            "Healthcare": "Healthcare", "Professional Services": "Services",
            "Public Sector": "Services"}.get(name, "Other")


def build_dim_product(s: Scenario) -> pd.DataFrame:
    """Portfolio -> Family -> Line.

    `gross_margin_pct` is the addition the note needed (PLAN 2.8): without it
    ROI collapses into ROAS and the difference between "2.08x return" and
    "26 cents of gross profit per dollar" cannot be shown.
    """
    rows = []
    for i, p in enumerate(s.products, start=1):
        rows.append({
            "product_id": i, "product_portfolio": "Novareach Portfolio",
            "product_family": p["family"], "product_line": p["line"],
            "gross_margin_pct": float(p["margin"]),
            "list_price_band": ("Entry" if p["margin"] > 0.66 else
                                "Standard" if p["margin"] > 0.54 else "Premium"),
            "revenue_share": float(p["share"]),
            "is_new_product": 0,
        })
    df = pd.DataFrame(rows)
    ev = s.event("product_launch")
    if ev:
        df.loc[df["product_line"] == ev["product_line"], "is_new_product"] = 1
        launch = s.timeline.offset_month(int(ev["launch_month_offset"]))
        df["launch_date"] = pd.NaT
        df.loc[df["product_line"] == ev["product_line"], "launch_date"] = \
            pd.Timestamp(launch)
    return df


def build_dim_attribution_model(s: Scenario) -> pd.DataFrame:
    """Five models, not six: U-Shaped and Position Based are the same model and
    the note listed both. (PLAN 2.4)"""
    desc = {
        "FIRST_TOUCH": "100% to the first campaign touch. Rewards demand creation.",
        "LAST_TOUCH": "100% to the final touch before the opportunity. Rewards closing.",
        "LINEAR": "Split evenly across every touch in the journey.",
        "U_SHAPED": "40% first, 40% last, 20% split across the middle.",
        "W_SHAPED": "30% first, 30% at SQL creation, 30% last, 10% across the rest.",
    }
    rows = []
    for i, m in enumerate(s.attribution["models"], start=1):
        rows.append({"attribution_model_id": i, "model_code": m["code"],
                     "model_name": m["name"], "model_rule": m["rule"],
                     "model_description": desc[m["code"]],
                     "is_default_model": int(m["code"] == "W_SHAPED"),
                     "display_order": i})
    return pd.DataFrame(rows)


STAGES = [("Discovery", 1, 0.10), ("Qualification", 2, 0.20),
          ("Evaluation", 3, 0.40), ("Proposal", 4, 0.60),
          ("Negotiation", 5, 0.80), ("Closed Won", 6, 1.00),
          ("Closed Lost", 7, 0.00)]


def build_dim_opportunity_stage(s: Scenario) -> pd.DataFrame:
    rows = [{"stage_id": i, "stage_name": n, "stage_order": o,
             "default_probability": p,
             "is_closed": int(n.startswith("Closed")),
             "is_won": int(n == "Closed Won"),
             "stage_category": ("Closed" if n.startswith("Closed")
                                else "Early" if o <= 2 else "Late")}
            for i, (n, o, p) in enumerate(STAGES, start=1)]
    return pd.DataFrame(rows)


LOST_REASONS = [
    ("Lost to Competitor", "Competitive", 0.24),
    ("No Budget", "Budget", 0.19),
    ("No Decision / Stalled", "Timing", 0.17),
    ("Timing - Deferred to Next Year", "Timing", 0.12),
    ("Poor Fit - Requirements", "Qualification", 0.11),
    ("Price Too High", "Budget", 0.09),
    ("Champion Left", "Relationship", 0.05),
    ("Chose to Build In-House", "Competitive", 0.03),
]


def build_dim_lost_reason(s: Scenario) -> pd.DataFrame:
    """The note declared `lost_reason` and never the values, which leaves Q10
    unanswerable. `is_marketing_addressable` is the column that makes the table
    worth having: it separates "sales lost it" from "marketing sent the wrong
    people", which is the entire cross-functional argument in Scenario 4."""
    rows = [{"lost_reason_id": i, "lost_reason": n, "lost_reason_category": c,
             "reason_share": w,
             "is_marketing_addressable": int(c in ("Qualification", "Competitive"))}
            for i, (n, c, w) in enumerate(LOST_REASONS, start=1)]
    return pd.DataFrame(rows)


LEAD_SOURCES = [
    ("Paid Ad Click", "Inbound"), ("Content Download", "Inbound"),
    ("Webinar Registration", "Inbound"), ("Demo Request", "Inbound"),
    ("Contact Sales Form", "Inbound"), ("Event Badge Scan", "Event"),
    ("Partner Referral", "Partner"), ("Email Reply", "Nurture"),
    ("Chat Conversation", "Inbound"), ("Free Trial Signup", "Product"),
    ("List Purchase", "Outbound"), ("Direct Mail Response", "Outbound"),
]


def build_dim_lead_source(s: Scenario) -> pd.DataFrame:
    rows = [{"lead_source_id": i, "lead_source_name": n, "source_category": c,
             "is_self_identified": int(c in ("Inbound", "Product"))}
            for i, (n, c) in enumerate(LEAD_SOURCES, start=1)]
    return pd.DataFrame(rows)


ASSETS = [
    ("The 2026 Analytics Maturity Benchmark", "Research Report", 22, 0.11),
    ("Total Economic Impact of Embedded Analytics", "Analyst Report", 18, 0.09),
    ("Data Warehouse Migration Playbook", "Whitepaper", 14, 0.10),
    ("Cutting Close Cycles with AI Forecasting", "Case Study", 16, 0.08),
    ("Reference Architecture: Real-Time Analytics", "Technical Guide", 12, 0.08),
    ("Buyer's Guide to AI Analytics Platforms", "Buyer's Guide", 20, 0.09),
    ("Manufacturing Analytics in Practice", "Case Study", 15, 0.07),
    ("Governance for Regulated Industries", "Whitepaper", 13, 0.07),
    ("Agent Studio Product Tour", "Product Demo", 28, 0.08),
    ("Live Q&A: Migrating off Legacy BI", "Webinar Recording", 24, 0.08),
    ("ROI Calculator: Analytics Consolidation", "Interactive Tool", 30, 0.06),
    ("Retail Demand Forecasting Blueprint", "Solution Brief", 11, 0.05),
    ("Pricing and Packaging Overview", "Pricing", 26, 0.04),
]


def build_dim_content_asset(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    """Named assets, each carrying a lead-score weight.

    "Which behaviours predict conversion" (Q14) is a weak question when the
    answer is "downloads". It is a good one when the answer is "the ROI
    calculator and the pricing page, and neither is where we spend".
    """
    rows = [{"content_asset_id": i, "asset_title": t, "asset_type": a,
             "lead_score_weight": w, "download_share": sh,
             "is_gated": int(a not in ("Pricing", "Webinar Recording"))}
            for i, (t, a, w, sh) in enumerate(ASSETS, start=1)]
    return pd.DataFrame(rows)


ACTIVITY_TYPES = [
    ("Page View", "Web", 1), ("Product View", "Web", 4),
    ("Pricing View", "Web", 15), ("Demo Request", "Web", 40),
    ("Whitepaper Download", "Content", 5), ("Case Study Download", "Content", 8),
    ("Contact Sales", "Web", 45), ("Chat", "Web", 12),
    ("Video View", "Web", 3), ("Email Open", "Email", 1),
    ("Email Click", "Email", 6), ("Ad Click", "Paid", 2),
    ("Webinar Attendance", "Event", 22), ("Event Booth Visit", "Event", 18),
    ("Trial Signup", "Product", 35),
]


def build_dim_activity_type(s: Scenario) -> pd.DataFrame:
    """Score weights live here as data, not in generator code.

    `fact_lead.lead_score` is the SUM of these across a lead's real activity
    rows (PLAN 5), so the drill from a score to the behaviours that produced it
    always reconciles - and Q14 has a true answer sitting in the data rather
    than a plausible-looking one.
    """
    rows = [{"activity_type_id": i, "activity_type": n, "activity_channel": c,
             "lead_score_points": p,
             "is_high_intent": int(p >= 15)}
            for i, (n, c, p) in enumerate(ACTIVITY_TYPES, start=1)]
    return pd.DataFrame(rows)
