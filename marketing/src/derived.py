"""Derived tables: the campaign-daily rollup, the campaign cohort summary, the
monthly funnel snapshot, and the lead score.

Three PLAN decisions live here.

**fact_campaign_daily is a ROLLUP, never a draw (PLAN 2.3).** Paid spend is
aggregated up from `fact_ad_performance`; non-paid channels post directly
because they have no ad grain. Lead, MQL and SQL counts come from the leads
that actually exist. So the daily table cannot disagree with either the media
plan above it or the funnel below it.

**fact_campaign_summary carries maturity (PLAN 2.5).** A campaign that started
three months ago has not had time to produce closed revenue, and its ROAS is
therefore not a verdict. `pipeline_maturity_pct` and `is_mature_cohort` are
what let the dashboard say "72% still in flight" instead of showing a red tile,
and they are the difference between the lag being a feature and being a bug.

**lead_score is summed from real activity (PLAN 5).** Not sampled. The drill
from a score to the behaviours that produced it always reconciles, and Q14 -
which behaviours predict conversion - has a true answer rather than a
plausible-looking one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mktconfig import Scenario


def build_lead_score(lead: pd.DataFrame, act: pd.DataFrame,
                     web_ev: pd.DataFrame) -> pd.DataFrame:
    """Sum the score points a lead's own activity actually earned."""
    parts = [act.groupby("lead_id")["lead_score_points"].sum()]
    if len(web_ev):
        w = web_ev[web_ev["lead_id"] > 0]
        if len(w):
            parts.append(w.groupby("lead_id")["lead_score_points"].sum())
    score = pd.concat(parts, axis=1).sum(axis=1)
    lead = lead.copy()
    lead["lead_score"] = (lead["lead_id"].map(score).fillna(0)
                          .clip(0, 999).astype(np.int32))
    lead["lead_grade"] = pd.cut(
        lead["lead_score"], [-1, 20, 45, 90, 9999],
        labels=["D", "C", "B", "A"]).astype(str)
    return lead


def build_campaign_daily(s: Scenario, ad: pd.DataFrame, cm: pd.DataFrame,
                         camp: pd.DataFrame, lead: pd.DataFrame,
                         rng: np.random.Generator) -> pd.DataFrame:
    """Daily campaign performance, assembled from the grains beneath it."""
    paid_ids = set(ad["campaign_id"].unique()) if len(ad) else set()

    frames = []
    if len(ad):
        frames.append(ad.groupby(["activity_date", "campaign_id", "channel_id"],
                                 as_index=False).agg(
            impressions=("impressions", "sum"), clicks=("clicks", "sum"),
            video_views=("video_views", "sum"),
            engagements=("engagements", "sum"),
            landing_page_visits=("landing_page_visits", "sum"),
            spend_usd=("spend_usd", "sum")))

    # Non-paid channels have no ad grain, so their spend is spread across the
    # month's days directly. Events are lumpy - a trade show costs what it costs
    # on the days it runs - so the spread is weighted, not flat.
    np_cm = cm[~cm["campaign_id"].isin(paid_ids)].merge(
        camp[["campaign_id", "channel_id", "channel_name"]], on="campaign_id",
        how="left")
    rows = []
    for _, r in np_cm.iterrows():
        m0 = pd.Timestamp(r["month_start"])
        days = pd.date_range(m0, m0 + pd.offsets.MonthEnd(0), freq="D")
        days = days[days <= pd.Timestamp(s.timeline.as_of_date)]
        if len(days) == 0:
            continue
        if r["channel_name"] in ("Trade Show", "Customer Event"):
            w = np.zeros(len(days))
            w[rng.integers(0, len(days), min(3, len(days)))] = 1.0
            w = w if w.sum() > 0 else np.ones(len(days))
        else:
            w = np.where(days.dayofweek >= 5, 0.35, 1.0)
        w = w / w.sum()
        rows.append(pd.DataFrame({
            "activity_date": days.date, "campaign_id": int(r["campaign_id"]),
            "channel_id": int(r["channel_id"]),
            "impressions": 0, "clicks": 0, "video_views": 0, "engagements": 0,
            "landing_page_visits": 0,
            "spend_usd": (w * float(r["spend_usd"])).round(4)}))
    if rows:
        frames.append(pd.concat(rows, ignore_index=True))

    daily = pd.concat(frames, ignore_index=True)
    daily = daily.groupby(["activity_date", "campaign_id", "channel_id"],
                          as_index=False).sum()

    # Funnel counts from the leads that exist, keyed on the same day.
    lm = lead.groupby(["lead_date", "campaign_id"]).agg(
        leads=("lead_id", "size"), mqls=("is_mql", "sum"),
        sqls=("is_sql", "sum")).reset_index().rename(
        columns={"lead_date": "activity_date"})
    daily = daily.merge(lm, on=["activity_date", "campaign_id"], how="left")
    for c in ("leads", "mqls", "sqls"):
        daily[c] = daily[c].fillna(0).astype(np.int32)

    # Form submissions exceed leads: duplicates, test entries and disposable
    # addresses are deduped out before a lead record is created.
    daily["form_submissions"] = (
        daily["leads"] * rng.uniform(1.02, 1.14, len(daily))).round().astype(np.int32)
    daily["spend_usd"] = daily["spend_usd"].round(2)
    daily.insert(0, "campaign_daily_id", np.arange(1, len(daily) + 1))
    return daily


def build_campaign_summary(s: Scenario, camp: pd.DataFrame, cm: pd.DataFrame,
                           lead: pd.DataFrame, opp: pd.DataFrame,
                           products: pd.DataFrame) -> pd.DataFrame:
    """One row per campaign: cohort economics, with maturity attached."""
    tl = s.timeline
    as_of = pd.Timestamp(tl.as_of_date)

    spend = cm.groupby("campaign_id")["spend_usd"].sum()
    lf = lead.groupby("campaign_id").agg(
        leads=("lead_id", "size"), mqls=("is_mql", "sum"),
        sqls=("is_sql", "sum"))
    of = opp.groupby("campaign_id").agg(
        opportunities=("opportunity_id", "size"),
        pipeline_usd=("amount_usd", "sum"),
        won_deals=("is_won", "sum"),
        revenue_usd=("won_amount_usd", "sum"),
        closed=("is_closed", "sum"))

    d = camp[["campaign_id", "campaign_name", "campaign_type", "channel_id",
              "channel_name", "objective", "product_id", "target_segment",
              "target_industry", "target_region", "start_date", "end_date",
              "budget_amount_usd", "campaign_status", "agency"]].copy()
    d = d.join(spend.rename("spend_usd"), on="campaign_id")
    d = d.join(lf, on="campaign_id").join(of, on="campaign_id")
    for c in ("spend_usd", "leads", "mqls", "sqls", "opportunities",
              "pipeline_usd", "won_deals", "revenue_usd", "closed"):
        d[c] = d[c].fillna(0)

    margin = products.set_index("product_id")["gross_margin_pct"]
    d["gross_margin_pct"] = d["product_id"].map(margin).fillna(0.6)

    safe = lambda x, y: np.where(y > 0, x / np.where(y > 0, y, 1), np.nan)
    d["cpl_usd"] = safe(d["spend_usd"], d["leads"]).round(2)
    d["cost_per_mql_usd"] = safe(d["spend_usd"], d["mqls"]).round(2)
    d["cost_per_sql_usd"] = safe(d["spend_usd"], d["sqls"]).round(2)
    d["cac_usd"] = safe(d["spend_usd"], d["won_deals"]).round(2)
    d["roas"] = safe(d["revenue_usd"], d["spend_usd"]).round(4)
    # ROI, not ROAS: gross profit less spend, over spend. The gap between the
    # two is what dim_product.gross_margin_pct was added for. (PLAN 2.8)
    d["marketing_roi"] = safe(
        d["revenue_usd"] * d["gross_margin_pct"] - d["spend_usd"],
        d["spend_usd"]).round(4)
    d["pipeline_per_usd"] = safe(d["pipeline_usd"], d["spend_usd"]).round(4)
    d["lead_to_mql_rate"] = safe(d["mqls"], d["leads"]).round(4)
    d["mql_to_sql_rate"] = safe(d["sqls"], d["mqls"]).round(4)

    # --- maturity (PLAN 2.5) -------------------------------------------------
    start = pd.to_datetime(d["start_date"])
    d["months_since_start"] = ((as_of.year - start.dt.year) * 12
                               + (as_of.month - start.dt.month)).astype(np.int16)
    # Share of the campaign's opportunities that have actually closed. A young
    # campaign reads "72% still in flight", not "failed".
    d["pipeline_maturity_pct"] = safe(d["closed"], d["opportunities"]).round(4)
    d["open_pipeline_usd"] = (d["pipeline_usd"]
                              - opp[opp["is_closed"] == 1]
                              .groupby("campaign_id")["amount_usd"].sum()
                              .reindex(d["campaign_id"]).fillna(0).to_numpy()
                              ).round(2)
    # A cohort is mature once a full median sales cycle plus a quarter has
    # passed. Before that, its ROAS is not evidence.
    median_cycle_months = 6
    d["is_mature_cohort"] = (
        d["months_since_start"] >= median_cycle_months + 3).astype(np.int8)
    d["cohort_period"] = start.dt.to_period("Q").astype(str)
    d["is_ttm_cohort"] = (start >= pd.Timestamp(tl.ttm_start)).astype(np.int8)
    for c in ("leads", "mqls", "sqls", "opportunities", "won_deals", "closed"):
        d[c] = d[c].astype(np.int32)
    return d.reset_index(drop=True)


def build_funnel_snapshot(s: Scenario, lead: pd.DataFrame, opp: pd.DataFrame,
                          channels: pd.DataFrame) -> pd.DataFrame:
    """Monthly funnel counts by channel, region and segment.

    Pre-aggregated purely so the executive trend page is one scan rather than a
    five-million-row group-by in the browser. Everything in it is reproducible
    from fact_lead and fact_opportunity, and validate.py checks that it is.
    """
    l = lead.copy()
    l["month_start"] = pd.to_datetime(l["lead_date"]).dt.to_period("M").dt.start_time
    key = ["month_start", "source_channel", "region_name", "segment_id"]
    f = l.groupby(key, as_index=False).agg(
        leads=("lead_id", "size"), mqls=("is_mql", "sum"),
        sqls=("is_sql", "sum"), sales_accepted=("is_sales_accepted", "sum"),
        lead_score_total=("lead_score", "sum"))

    o = opp.copy()
    o["month_start"] = pd.to_datetime(
        o["opportunity_date"]).dt.to_period("M").dt.start_time
    ok = ["month_start", "source_channel", "region_name", "segment_id"]
    g = o.groupby(ok, as_index=False).agg(
        opportunities=("opportunity_id", "size"),
        pipeline_created_usd=("amount_usd", "sum"))

    c = o[o["is_won"] == 1].copy()
    c["month_start"] = pd.to_datetime(
        c["actual_close_date"]).dt.to_period("M").dt.start_time
    ck = ["month_start", "source_channel", "region_name", "segment_id"]
    h = c.groupby(ck, as_index=False).agg(
        won_deals=("opportunity_id", "size"),
        revenue_usd=("won_amount_usd", "sum"))

    out = f.merge(g, on=key, how="outer").merge(h, on=key, how="outer")
    for col in ("leads", "mqls", "sqls", "sales_accepted", "opportunities",
                "won_deals", "lead_score_total"):
        out[col] = out[col].fillna(0).astype(np.int32)
    for col in ("pipeline_created_usd", "revenue_usd"):
        out[col] = out[col].fillna(0.0).round(2)
    out = out.merge(channels[["channel_id", "channel_name"]],
                    left_on="source_channel", right_on="channel_name",
                    how="left").drop(columns=["channel_name"])
    out["channel_id"] = out["channel_id"].fillna(0).astype(np.int32)
    out["month_start"] = out["month_start"].dt.date
    out.insert(0, "funnel_snapshot_id", np.arange(1, len(out) + 1))
    return out
