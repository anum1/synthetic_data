"""fact_ad_performance - the grain of record for paid media.

PLAN 2.3. Spend exists in exactly one place per channel and everything else is
derived from it:

  paid channels  -> drawn here, per (date, creative, device), summing EXACTLY
                    to the campaign-month spend campaigns.py allocated
  all channels   -> rolled up into fact_campaign_daily by derived.py, never
                    drawn independently

Impressions and clicks are derived from spend by the channel's own pricing
model - CPM where the channel sells impressions, CPC where it sells clicks -
so a CTR in this table is always spend divided by two numbers that came from
that spend. Draw impressions and spend separately and the first person to
divide them finds a CPM the media plan never contained.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from mktconfig import Scenario

DEVICES = [("Desktop", 0.54), ("Mobile", 0.38), ("Tablet", 0.08)]
PLACEMENTS = {
    "Google Ads": ["Search Top", "Search Other", "Display Network"],
    "LinkedIn": ["Feed", "Right Rail", "InMail"],
    "Facebook": ["Feed", "Stories", "Audience Network"],
    "YouTube": ["In-Stream", "Discovery", "Shorts"],
    "Content Syndication": ["Partner Newsletter", "Partner Portal"],
}


def build_fact_ad_performance(s: Scenario, camp: pd.DataFrame,
                              creatives: pd.DataFrame, cm: pd.DataFrame,
                              ep: EventPlan,
                              rng: np.random.Generator) -> pd.DataFrame:
    """One row per (date, ad creative, device). Paid channels only."""
    if creatives.empty:
        return pd.DataFrame()

    ch_meta = s.channels
    cinfo = camp.set_index("campaign_id")
    paid_ids = set(creatives["campaign_id"].unique())
    cm = cm[cm["campaign_id"].isin(paid_ids)]

    dev_names = np.array([d[0] for d in DEVICES])
    dev_w = np.array([d[1] for d in DEVICES])

    by_camp = {cid: g for cid, g in creatives.groupby("campaign_id")}
    frames = []

    for cid, grp in cm.groupby("campaign_id"):
        c = cinfo.loc[cid]
        ch = c["channel_name"]
        meta = ch_meta[ch]
        cre = by_camp.get(cid)
        if cre is None or cre.empty:
            continue
        cre_ids = cre["ad_creative_id"].to_numpy()
        ctr_mult = cre["_ctr_mult"].to_numpy()

        for _, mrow in grp.iterrows():
            m0 = pd.Timestamp(mrow["month_start"])
            days = pd.date_range(m0, m0 + pd.offsets.MonthEnd(0), freq="D")
            days = days[days <= pd.Timestamp(s.timeline.as_of_date)]
            if len(days) == 0:
                continue
            nd, nc, nv = len(days), len(cre_ids), len(dev_names)

            # Weights over (day, creative, device). Weekday seasonality is real
            # in B2B media and shows up in every daily chart, so it is here
            # rather than being a smooth line nobody believes.
            dow = days.dayofweek.to_numpy()
            day_w = np.where(dow >= 5, 0.42, 1.0) * rng.uniform(0.82, 1.18, nd)
            day_w /= day_w.sum()
            cre_w = rng.dirichlet(np.ones(nc) * 3.5)
            w = day_w[:, None, None] * cre_w[None, :, None] * dev_w[None, None, :]
            spend = w * float(mrow["spend_usd"])          # sums to the month

            imp, clicks = _impressions_and_clicks(
                spend, meta, ctr_mult[None, :, None], rng, (nd, nc, nv))

            # E1: the flagship buys attention brilliantly and pipeline terribly.
            # The lift belongs HERE, at the top of the funnel, and the collapse
            # belongs in leads.py - that gap is the entire story.
            if ep.flagship and cid == ep.named_campaign_ids.get("flagship"):
                clicks = clicks * float(ep.flagship["ctr_mult"])

            frames.append(pd.DataFrame({
                "activity_date": np.repeat(days.date, nc * nv),
                "campaign_id": np.int32(cid),
                "channel_id": np.int32(c["channel_id"]),
                "ad_creative_id": np.tile(np.repeat(cre_ids, nv), nd),
                "device_type": np.tile(dev_names, nd * nc),
                "placement": rng.choice(PLACEMENTS.get(ch, ["Default"]),
                                        nd * nc * nv),
                "region_name": mrow["region_name"],
                "impressions": imp.round().astype(np.int64).ravel(),
                "clicks": clicks.round().astype(np.int32).ravel(),
                # Rounded to cents HERE, not at write time: campaign_daily is
                # a sum of these rows, and sum(round(x)) != round(sum(x)). If
                # the rounding happens after the rollup the two tables differ
                # by pennies, which is exactly the kind of discrepancy that
                # gets spotted on a slide.
                "spend_usd": spend.ravel().round(2),
            }))

    df = pd.concat(frames, ignore_index=True)
    df = df[df["impressions"] > 0].reset_index(drop=True)

    # Video views only exist where there is video; engagements are social.
    ch_name = camp.set_index("campaign_id")["channel_name"]
    cname = df["campaign_id"].map(ch_name)
    is_video = cname.isin(["YouTube", "Facebook"]).to_numpy()
    is_social = cname.isin(["LinkedIn", "Facebook"]).to_numpy()
    df["video_views"] = np.where(
        is_video, (df["impressions"] * rng.uniform(0.14, 0.32, len(df))), 0
    ).round().astype(np.int64)
    df["engagements"] = np.where(
        is_social, df["clicks"] * rng.uniform(1.5, 3.4, len(df)), df["clicks"]
    ).round().astype(np.int32)
    # Not every click reaches the page: bots, bounces and slow pages.
    df["landing_page_visits"] = (df["clicks"]
                                 * rng.uniform(0.82, 0.95, len(df))
                                 ).round().astype(np.int32)
    df.insert(0, "ad_performance_id", np.arange(1, len(df) + 1))
    return df


def _impressions_and_clicks(spend, meta, ctr_mult, rng, shape):
    """Derive volume from spend using the channel's own pricing model.

    CPM channels sell impressions; CPC channels sell clicks. Deriving both from
    spend is what guarantees that every ratio in this table - CTR, CPC, CPM -
    reconciles to the media plan, in every slice, without being checked.
    """
    ctr = float(meta["ctr"]) * ctr_mult * rng.uniform(0.80, 1.25, shape)
    cpm = float(meta.get("cpm_usd") or 0.0)
    if cpm > 0:
        eff_cpm = cpm * rng.uniform(0.86, 1.16, shape)
        imp = spend / eff_cpm * 1000.0
        clicks = imp * ctr
    else:
        cpc = float(meta.get("cpc_usd") or 6.0) * rng.uniform(0.84, 1.20, shape)
        clicks = spend / cpc
        imp = clicks / np.maximum(ctr, 1e-6)
    return imp, np.minimum(clicks, imp)
