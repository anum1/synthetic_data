"""fact_lead_activity - the touch history every journey and every attribution
model is replayed over.

This module is where Scenario 3 is actually created, and the way it is created
is the point. **The attribution divergence is never drawn.** Channels differ in
where they sit in a journey - paid social and syndication OPEN journeys,
webinars and events CLOSE them - and first-touch and last-touch therefore
disagree because the journeys really are shaped that way. Draw the divergence
as a number instead and the first drill from the attribution chart into a
customer journey contradicts the chart above it, live.

Touch counts and journey length are correlated with outcome, which is causally
right - engaged buyers buy - and is what makes `lead_score` a genuine predictor
in Q14 rather than a decorative column.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from mktconfig import Scenario, lognormal_from_median

# Which activity a channel produces when it touches someone, and whether that
# touch happens on the website (so web.py can materialise a session for it).
TOUCH_BY_CHANNEL = {
    "Google Ads": [("Ad Click", 0.55), ("Page View", 0.25), ("Pricing View", 0.20)],
    "LinkedIn": [("Ad Click", 0.62), ("Video View", 0.20), ("Page View", 0.18)],
    "Facebook": [("Ad Click", 0.70), ("Video View", 0.30)],
    "YouTube": [("Video View", 0.78), ("Ad Click", 0.22)],
    "Content Syndication": [("Whitepaper Download", 0.68),
                            ("Case Study Download", 0.32)],
    "Email": [("Email Open", 0.58), ("Email Click", 0.42)],
    "Organic Search": [("Page View", 0.42), ("Product View", 0.24),
                       ("Pricing View", 0.18), ("Chat", 0.10),
                       ("Trial Signup", 0.06)],
    "Webinar": [("Webinar Attendance", 0.82), ("Video View", 0.18)],
    "Trade Show": [("Event Booth Visit", 0.88), ("Demo Request", 0.12)],
    "Customer Event": [("Event Booth Visit", 0.74), ("Demo Request", 0.26)],
    "Partner": [("Page View", 0.55), ("Demo Request", 0.45)],
    "Direct Mail": [("Page View", 0.70), ("Contact Sales", 0.30)],
}
WEB_ACTIVITIES = {"Page View", "Product View", "Pricing View", "Demo Request",
                  "Contact Sales", "Chat", "Video View", "Trial Signup",
                  "Whitepaper Download", "Case Study Download"}


def build_lead_activity(s: Scenario, lead: pd.DataFrame, camp: pd.DataFrame,
                        cm: pd.DataFrame, assets: pd.DataFrame,
                        activity_types: pd.DataFrame, ep: EventPlan,
                        rng: np.random.Generator) -> pd.DataFrame:
    """One row per touch. Ordered, dated, and tied to a real campaign."""
    n = len(lead)
    lc = s.lifecycle["touches"]

    # --- how many touches --------------------------------------------------
    base = lognormal_from_median(rng, float(lc["median"]), 0.62, n)
    base *= 1.0 + 0.55 * lead["is_mql"].to_numpy()
    base *= 1.0 + 0.45 * lead["is_sql"].to_numpy()
    base *= 1.0 + 0.35 * lead["is_sales_accepted"].to_numpy()
    k = np.clip(np.round(base), int(lc["min"]), int(lc["max"])).astype(int)

    # E12 - the hero accounts get a long, channel-diverse journey. Without this
    # the presenter clicks an account and gets a two-touch journey, and the
    # single best screen in the demo evaporates. (PLAN 6)
    hero_lo, hero_hi = ep.hero_touches
    is_hero_lead = lead["customer_id"].isin(ep.hero_candidate_ids).to_numpy()
    hero_conv = is_hero_lead & (lead["is_sales_accepted"] == 1).to_numpy()
    k[hero_conv] = rng.integers(hero_lo, hero_hi + 1, hero_conv.sum())

    total = int(k.sum())
    lead_ix = np.repeat(np.arange(n), k)
    pos = _positions(k)
    kk = np.repeat(k, k)
    is_first = pos == 0
    is_last = pos == kk - 1

    # --- which channel touches, and where in the journey -------------------
    chans = np.array(list(s.channels))
    base_w = np.array([s.channels[c]["spend_share"] for c in chans])
    base_w = base_w / base_w.sum()
    first_w = base_w * ep.first_touch_bias(chans)
    last_w = base_w * ep.last_touch_bias(chans)
    draw = rng.random(total)
    channel = np.where(
        is_first, _weighted_pick(chans, first_w, draw),
        np.where(is_last, _weighted_pick(chans, last_w, draw),
                 _weighted_pick(chans, base_w, draw)))

    # The acquiring campaign's channel is not optional: it is the touch that
    # created the lead record, so it must appear in the journey. It goes at the
    # conversion point - the last touch on or before the lead date.
    src = lead["source_channel"].to_numpy()
    conv_pos = np.maximum((kk * 0.62).astype(int), 0)
    conv_pos = np.minimum(conv_pos, kk - 1)
    is_conv = pos == conv_pos
    channel = np.where(is_conv, np.repeat(src, k), channel)

    # --- when ---------------------------------------------------------------
    lead_dt = pd.to_datetime(lead["lead_date"]).to_numpy()
    lookback = np.round(lognormal_from_median(rng, 52.0, 0.78, n)).astype(int)
    lookback = np.clip(lookback, 5, 420)
    end_dt = pd.to_datetime(
        lead["sales_accepted_date"].fillna(lead["sql_date"])
        .fillna(lead["mql_date"]).fillna(lead["lead_date"])).to_numpy()
    # A journey cannot begin before the dataset does. Leads acquired in the
    # first months of history have a lookback that predates the CRM, so their
    # journeys are left-censored - which is exactly what happens in a real
    # migration, and is why early-cohort touch counts are lower. Without this
    # clamp, 1.6% of touches are dated before any campaign existed and get
    # attached to a campaign that had not started.
    start = np.maximum(lead_dt - lookback.astype("timedelta64[D]"),
                       np.datetime64(s.timeline.start_date))
    span = np.maximum((end_dt - start) / np.timedelta64(1, "D"), 1.0)
    # Measured from the CLAMPED start, not from the requested lookback: for a
    # left-censored journey those differ, and using the requested lookback puts
    # the conversion touch past the lead date.
    lead_offset = np.clip((lead_dt - start) / np.timedelta64(1, "D"), 0.0, None)

    # Touch times are sorted uniforms scaled into the journey window, with the
    # conversion touch pinned to the lead date and the touches either side of
    # it rescaled around that pin.
    #
    # Pinning by overwriting one value and re-sorting does NOT work: the sort
    # moves the pinned value to wherever it ranks, so the conversion touch
    # stops being at the conversion position and 4% of touches end up dated
    # outside the campaign that supposedly produced them.
    u = _sort_within(rng.random(total), k)
    frac_lead = np.repeat(np.clip(lead_offset / span, 0.0, 1.0), k)
    u_conv = np.repeat(u[is_conv], k)          # one per lead, broadcast back
    before = pos <= conv_pos
    frac = np.where(
        before,
        frac_lead * np.divide(u, u_conv, out=np.ones_like(u), where=u_conv > 0),
        frac_lead + (1.0 - frac_lead) * np.divide(
            u - u_conv, 1.0 - u_conv,
            out=np.zeros_like(u), where=u_conv < 1.0))
    frac = np.clip(frac, 0.0, 1.0)
    days = np.repeat(span, k) * frac
    touch_dt = np.repeat(start, k) + np.round(days).astype("timedelta64[D]")
    as_of = np.datetime64(s.timeline.as_of_date)
    touch_dt = np.minimum(touch_dt, as_of)

    # --- what happened, and under which campaign ---------------------------
    campaign_id, channel = _campaign_for(
        s, camp, cm, channel, touch_dt,
        np.repeat(lead["region_name"].to_numpy(), k),
        np.repeat(lead["campaign_id"].to_numpy(), k), is_conv, rng)
    act, is_web = _activity_for(channel, rng)

    pts = activity_types.set_index("activity_type")["lead_score_points"].to_dict()
    asset_ids = assets["content_asset_id"].to_numpy()
    asset_w = assets["download_share"].to_numpy()
    asset_w = asset_w / asset_w.sum()
    needs_asset = np.isin(act, ["Whitepaper Download", "Case Study Download",
                                "Video View", "Webinar Attendance"])
    asset = np.where(needs_asset,
                     rng.choice(asset_ids, size=total, p=asset_w), 0)

    df = pd.DataFrame({
        "lead_activity_id": np.arange(1, total + 1),
        "lead_id": lead["lead_id"].to_numpy()[lead_ix].astype(np.int32),
        "contact_id": lead["contact_id"].to_numpy()[lead_ix].astype(np.int32),
        "customer_id": lead["customer_id"].to_numpy()[lead_ix].astype(np.int32),
        "activity_date": touch_dt.astype("datetime64[D]"),
        "touch_sequence": (pos + 1).astype(np.int16),
        "touches_in_journey": kk.astype(np.int16),
        "channel_name": channel,
        "campaign_id": campaign_id.astype(np.int32),
        "activity_type": act,
        "content_asset_id": asset.astype(np.int32),
        "region_name": np.repeat(lead["region_name"].to_numpy(), k),
        "is_first_touch": is_first.astype(np.int8),
        "is_last_touch": is_last.astype(np.int8),
        "is_conversion_touch": is_conv.astype(np.int8),
        "is_web_activity": is_web.astype(np.int8),
        "lead_score_points": np.array([pts.get(a, 1) for a in act], dtype=np.int16),
    })
    return df.sort_values(["lead_id", "touch_sequence"]).reset_index(drop=True)


def _positions(k: np.ndarray) -> np.ndarray:
    """0..k-1 for each group, without a Python loop."""
    total = int(k.sum())
    idx = np.arange(total)
    starts = np.repeat(np.concatenate([[0], np.cumsum(k)[:-1]]), k)
    return idx - starts


def _sort_within(x: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Sort each group's values ascending, in place across the flat array."""
    grp = np.repeat(np.arange(len(k)), k)
    order = np.lexsort((x, grp))
    out = np.empty_like(x)
    out[np.argsort(grp, kind="stable")] = x[order]
    return out


def _weighted_pick(values: np.ndarray, w: np.ndarray,
                   draw: np.ndarray) -> np.ndarray:
    """Inverse-CDF pick, so all three journey positions can share one uniform
    draw and stay vectorised across millions of touches."""
    cdf = np.cumsum(w / w.sum())
    return values[np.searchsorted(cdf, draw, side="right").clip(0, len(values) - 1)]


def _activity_for(channel: np.ndarray, rng: np.random.Generator):
    act = np.empty(len(channel), dtype=object)
    u = rng.random(len(channel))
    for ch, opts in TOUCH_BY_CHANNEL.items():
        m = channel == ch
        if not m.any():
            continue
        names = np.array([o[0] for o in opts])
        cdf = np.cumsum([o[1] for o in opts])
        cdf = cdf / cdf[-1]
        act[m] = names[np.searchsorted(cdf, u[m], side="right")
                       .clip(0, len(names) - 1)]
    act = act.astype(str)
    return act, np.isin(act, list(WEB_ACTIVITIES))


def _campaign_for(s: Scenario, camp: pd.DataFrame, cm: pd.DataFrame,
                  channel: np.ndarray, when: np.ndarray, region: np.ndarray,
                  lead_campaign: np.ndarray, is_conv: np.ndarray,
                  rng: np.random.Generator):
    """Attach every touch to a campaign that was actually running.

    A touch on a campaign that had not started is the fastest way to lose the
    room on the journey page, and it is invisible in aggregate - which is
    exactly why it has to be prevented here rather than checked for later.

    Returns (campaign_id, channel_name): where a channel ran nothing in the
    month a touch lands in, the touch is moved to a campaign that WAS running
    and its channel is corrected to match. Leaving the channel alone and
    letting the campaign fall back would put 1.6% of touches on a campaign that
    had not started - small enough to survive every aggregate and certain to
    appear the first time someone opens a journey.
    """
    key = cm.copy()
    key["channel_name"] = key["campaign_id"].map(
        camp.set_index("campaign_id")["channel_name"])
    key["ym"] = (pd.to_datetime(key["month_start"]).dt.year * 100
                 + pd.to_datetime(key["month_start"]).dt.month)
    pools = {k: (g["campaign_id"].to_numpy(), g["spend_usd"].to_numpy())
             for k, g in key.groupby(["channel_name", "region_name", "ym"])}
    # Fall back to channel+month when a channel ran nothing in that region that
    # month, and to the lead's own campaign when it ran nothing at all.
    ch_pools = {k: (g["campaign_id"].to_numpy(), g["spend_usd"].to_numpy())
                for k, g in key.groupby(["channel_name", "ym"])}
    ym_pools = {k: (g["campaign_id"].to_numpy(), g["spend_usd"].to_numpy())
                for k, g in key.groupby("ym")}
    camp_channel = camp.set_index("campaign_id")["channel_name"]

    w = pd.to_datetime(when)
    ym = (w.year * 100 + w.month).to_numpy()
    out = lead_campaign.copy()
    out_ch = channel.copy()
    frame = pd.DataFrame({"ch": channel, "rg": region, "ym": ym})
    for (ch, rg, y), grp in frame.groupby(["ch", "rg", "ym"], sort=False):
        ix = grp.index.to_numpy()
        pool = pools.get((ch, rg, y)) or ch_pools.get((ch, y))
        moved = False
        if pool is None:
            pool = ym_pools.get(y)
            moved = True
        if pool is None:
            continue
        ids, sp = pool
        p = sp / sp.sum() if sp.sum() > 0 else None
        picked = rng.choice(ids, size=len(ix), p=p)
        out[ix] = picked
        if moved:
            out_ch[ix] = camp_channel.reindex(picked).to_numpy()
    # The conversion touch always belongs to the campaign that created the lead.
    out[is_conv] = lead_campaign[is_conv]
    out_ch[is_conv] = camp_channel.reindex(lead_campaign[is_conv]).to_numpy()
    return out, out_ch
