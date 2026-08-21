"""fact_web_session and fact_web_event.

Two repairs to the design note here (PLAN 2.9).

**Split grains.** The note had one `fact_web_activity` carrying both. Session
metrics - bounce rate, session duration, entry page, device - are wrong when
computed off an event table, because every session with six events counts six
times. One session, many events.

**Anonymous first.** The note put `lead_id` on every web row. In reality almost
every session is anonymous until a form is filled, and the true first touch in
a journey is usually an organic search weeks before the person exists in the
CRM. Sessions therefore carry an `anonymous_id` always and a `contact_id` only
once identified, with `stitched_at_date` recording when the two were joined.
Without this, first-touch attribution is quietly a lie: it can only ever see
touches that happened after the lead was created.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from mktconfig import Scenario

PAGES = [
    ("/", "Home", 0.17), ("/product/bi-platform", "Product", 0.09),
    ("/product/ai-analytics", "Product", 0.08),
    ("/product/data-warehouse", "Product", 0.06),
    ("/pricing", "Pricing", 0.07), ("/demo-request", "Conversion", 0.04),
    ("/resources", "Content", 0.10), ("/resources/whitepapers", "Content", 0.07),
    ("/customers", "Social Proof", 0.06), ("/blog", "Content", 0.11),
    ("/docs", "Technical", 0.06), ("/company/about", "Company", 0.04),
    ("/contact-sales", "Conversion", 0.03), ("/events/webinars", "Content", 0.02),
]
SOURCES = [("Organic Search", 0.34), ("Direct", 0.22), ("Paid Search", 0.16),
           ("Paid Social", 0.12), ("Referral", 0.08), ("Email", 0.05),
           ("Organic Social", 0.03)]
DEVICES = [("Desktop", 0.61), ("Mobile", 0.33), ("Tablet", 0.06)]
BROWSERS = [("Chrome", 0.58), ("Safari", 0.21), ("Edge", 0.13), ("Firefox", 0.08)]
EVENT_TYPES = [("Page View", 0.58), ("Product View", 0.13), ("Video View", 0.09),
               ("Whitepaper Download", 0.07), ("Pricing View", 0.06),
               ("Chat", 0.03), ("Demo Request", 0.02),
               ("Case Study Download", 0.015), ("Contact Sales", 0.01),
               ("Trial Signup", 0.005)]


def build_web(s: Scenario, lead: pd.DataFrame, act: pd.DataFrame,
              contacts: pd.DataFrame, assets: pd.DataFrame,
              activity_types: pd.DataFrame, ep: EventPlan,
              rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (fact_web_session, fact_web_event)."""
    ident = _identified_sessions(s, lead, act, rng)
    anon = _anonymous_sessions(s, lead, len(ident), ep, rng)
    # Both builders emit datetime64, not datetime.date: a column holding both
    # cannot be sorted, and pandas raises only at the sort rather than where the
    # types diverged.
    ses = pd.concat([ident, anon], ignore_index=True)
    ses = ses.sort_values("session_start_date").reset_index(drop=True)
    ses.insert(0, "web_session_id", np.arange(1, len(ses) + 1))

    ev = _events(s, ses, assets, activity_types, ep, rng)
    # Session-grain metrics are computed FROM the events, so a session's
    # page-view count can never disagree with the rows underneath it.
    agg = ev.groupby("web_session_id").agg(
        page_views=("web_event_id", "size"),
        session_duration_seconds=("duration_seconds", "sum"),
        is_conversion_session=("is_conversion_event", "max"))
    ses = ses.merge(agg, on="web_session_id", how="left")
    ses["page_views"] = ses["page_views"].fillna(1).astype(np.int16)
    ses["session_duration_seconds"] = (
        ses["session_duration_seconds"].fillna(20).astype(np.int32))
    ses["is_conversion_session"] = (
        ses["is_conversion_session"].fillna(0).astype(np.int8))
    ses["is_bounce"] = (ses["page_views"] <= 1).astype(np.int8)
    return ses, ev


def _identified_sessions(s: Scenario, lead: pd.DataFrame, act: pd.DataFrame,
                         rng: np.random.Generator) -> pd.DataFrame:
    """One session for every web touch in a real journey.

    These are the sessions that matter: they belong to a person, they sit in a
    journey, and they are what the customer-journey page walks through.
    """
    w = act[act["is_web_activity"] == 1]
    if w.empty:
        return pd.DataFrame()
    n = len(w)
    lead_dt = pd.to_datetime(
        lead.set_index("lead_id")["lead_date"]).reindex(w["lead_id"]).to_numpy()
    act_dt = pd.to_datetime(w["activity_date"]).to_numpy()
    # Identified only once the form has been filled. Everything before that is
    # anonymous at the time and stitched retroactively.
    identified = act_dt >= lead_dt

    return pd.DataFrame({
        "anonymous_id": _anon_ids(w["contact_id"].to_numpy(), rng),
        "contact_id": np.where(identified, w["contact_id"].to_numpy(), 0),
        "customer_id": np.where(identified, w["customer_id"].to_numpy(), 0),
        "lead_id": np.where(identified, w["lead_id"].to_numpy(), 0),
        "campaign_id": w["campaign_id"].to_numpy(),
        "session_start_date": w["activity_date"].to_numpy(),
        "stitched_at_date": pd.to_datetime(lead_dt).to_numpy(),
        "is_identified": identified.astype(np.int8),
        "traffic_source": _channel_to_source(w["channel_name"].to_numpy(), rng),
        "device_type": _pick(DEVICES, n, rng),
        "browser": _pick(BROWSERS, n, rng),
        "entry_page": _pick(PAGES, n, rng, idx=0),
        "region_name": w["region_name"].to_numpy(),
        "is_new_visitor": (rng.random(n) < 0.38).astype(np.int8),
        "_intent": np.where(identified, 1.35, 0.85),
    })


def _anonymous_sessions(s: Scenario, lead: pd.DataFrame, n_identified: int,
                        ep: EventPlan, rng: np.random.Generator) -> pd.DataFrame:
    """Background traffic that never becomes anything.

    This is where the tier's volume lives (PLAN 2.2). It is also what makes the
    site-wide conversion rate a real number: without the people who visited and
    left, every visitor in the dataset converts and E15's conversion drop has
    nothing to drop from.
    """
    want = int(float(s.sizes["web_sessions_per_lead"]) * len(lead))
    n = max(want - n_identified, 0)
    if n == 0:
        return pd.DataFrame()

    tl = s.timeline
    span = (tl.as_of_date - tl.start_date).days
    # Traffic grows with spend, so the trend line under the funnel matches it.
    frac = rng.beta(2.1, 1.35, n)
    day = (frac * span).astype(int)
    date = pd.to_datetime(tl.start_date) + pd.to_timedelta(day, unit="D")

    reg = list(s.regions)
    reg_p = np.array([s.regions[r]["spend_share"] for r in reg])
    return pd.DataFrame({
        "anonymous_id": _anon_ids(np.zeros(n, dtype=np.int64), rng),
        "contact_id": np.int32(0), "customer_id": np.int32(0),
        "lead_id": np.int32(0), "campaign_id": np.int32(0),
        "session_start_date": date.to_numpy(),
        "stitched_at_date": np.datetime64("NaT"),
        "is_identified": np.int8(0),
        "traffic_source": _pick(SOURCES, n, rng),
        "device_type": _pick(DEVICES, n, rng),
        "browser": _pick(BROWSERS, n, rng),
        "entry_page": _pick(PAGES, n, rng, idx=0),
        "region_name": rng.choice(reg, n, p=reg_p / reg_p.sum()),
        "is_new_visitor": (rng.random(n) < 0.71).astype(np.int8),
        "_intent": np.float64(0.42),
    })


def _events(s: Scenario, ses: pd.DataFrame, assets: pd.DataFrame,
            activity_types: pd.DataFrame, ep: EventPlan,
            rng: np.random.Generator) -> pd.DataFrame:
    """Page-level events inside each session."""
    per = float(s.sizes["web_events_per_session"])
    k = 1 + rng.poisson(np.maximum(per - 1, 0.2) * ses["_intent"].to_numpy())
    k = np.clip(k, 1, 24)
    total = int(k.sum())
    ix = np.repeat(np.arange(len(ses)), k)
    seq = np.arange(total) - np.repeat(
        np.concatenate([[0], np.cumsum(k)[:-1]]), k)

    page_i = rng.choice(len(PAGES), total,
                        p=np.array([p[2] for p in PAGES])
                        / sum(p[2] for p in PAGES))
    page = np.array([p[0] for p in PAGES])[page_i]
    page_cat = np.array([p[1] for p in PAGES])[page_i]

    etype = _pick(EVENT_TYPES, total, rng)
    # High-intent event types only fire for high-intent sessions. Otherwise a
    # third of anonymous drive-by traffic requests a demo.
    intent = ses["_intent"].to_numpy()[ix]
    downgrade = (np.isin(etype, ["Demo Request", "Contact Sales", "Trial Signup",
                                 "Pricing View"])
                 & (rng.random(total) > np.clip(intent - 0.30, 0.02, 0.95)))
    etype = np.where(downgrade, "Page View", etype)

    # E15 - a form-conversion drop on two pages for two months, with a cause:
    # a broken form. Conversion events on those pages simply stop firing.
    date = pd.to_datetime(ses["session_start_date"].to_numpy()[ix])
    if ep.web_drop:
        m0 = pd.Timestamp(s.timeline.offset_month(int(ep.web_drop["month_offset"])))
        m1 = pd.Timestamp(s.timeline.offset_month(
            int(ep.web_drop["month_offset"]) + int(ep.web_drop["duration_months"])))
        hit = (np.isin(page, ep.web_drop_pages)
               & np.asarray(date >= m0) & np.asarray(date < m1)
               & (rng.random(total) > float(ep.web_drop["conversion_mult"])))
        etype = np.where(hit & np.isin(etype, ["Demo Request", "Contact Sales",
                                               "Pricing View"]),
                         "Page View", etype)

    pts = activity_types.set_index("activity_type")["lead_score_points"].to_dict()
    asset_ids = assets["content_asset_id"].to_numpy()
    aw = assets["download_share"].to_numpy()
    needs = np.isin(etype, ["Whitepaper Download", "Case Study Download",
                            "Video View"])
    return pd.DataFrame({
        "web_event_id": np.arange(1, total + 1),
        "web_session_id": ses["web_session_id"].to_numpy()[ix],
        "contact_id": ses["contact_id"].to_numpy()[ix],
        "customer_id": ses["customer_id"].to_numpy()[ix],
        "lead_id": ses["lead_id"].to_numpy()[ix],
        "campaign_id": ses["campaign_id"].to_numpy()[ix],
        "event_date": ses["session_start_date"].to_numpy()[ix],
        "event_sequence": (seq + 1).astype(np.int16),
        "event_type": etype,
        "page_path": page,
        "page_category": page_cat,
        "content_asset_id": np.where(
            needs, rng.choice(asset_ids, total, p=aw / aw.sum()), 0).astype(np.int32),
        "device_type": ses["device_type"].to_numpy()[ix],
        "region_name": ses["region_name"].to_numpy()[ix],
        "duration_seconds": np.clip(
            rng.lognormal(3.4, 0.95, total), 3, 1800).round().astype(np.int32),
        "lead_score_points": np.array([pts.get(e, 1) for e in etype],
                                      dtype=np.int16),
        "is_conversion_event": np.isin(
            etype, ["Demo Request", "Contact Sales", "Trial Signup"]
        ).astype(np.int8),
    })


def _anon_ids(contact_id: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Stable-looking cookie ids. A known contact keeps one id across sessions,
    which is what makes the stitch meaningful; anonymous traffic gets a fresh
    one each time, which is what makes visitor counts realistic."""
    n = len(contact_id)
    r = rng.integers(0, 2 ** 31, n)
    # int64 throughout: contact_id arrives as int32 and the Knuth multiplier
    # overflows it long before the modulo runs.
    cid = contact_id.astype(np.int64)
    seed = np.where(cid > 0, (cid * 2_654_435_761) % 2 ** 31, r)
    return np.char.add("anon_", seed.astype(str))


def _channel_to_source(channel: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    m = {"Google Ads": "Paid Search", "LinkedIn": "Paid Social",
         "Facebook": "Paid Social", "YouTube": "Paid Social",
         "Email": "Email", "Organic Search": "Organic Search",
         "Content Syndication": "Referral", "Partner": "Referral",
         "Webinar": "Direct", "Trade Show": "Direct",
         "Customer Event": "Direct", "Direct Mail": "Direct"}
    return np.array([m.get(c, "Direct") for c in channel])


def _pick(table, n: int, rng: np.random.Generator, idx: int = 0) -> np.ndarray:
    vals = np.array([t[idx] for t in table])
    w = np.array([t[-1] for t in table], dtype=float)
    return rng.choice(vals, n, p=w / w.sum())
