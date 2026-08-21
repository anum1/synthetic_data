"""fact_lead - the funnel, derived from the spend that bought it.

PLAN 2.1 in code. Lead volume is never drawn: it is

    leads = spend / cost_per_lead

for every campaign-month, with cost-per-lead varying by channel, region and
planted event. Every stage below it is a Bernoulli draw against a rate that is
itself the product of a channel rate, the lead-quality index, and the region,
segment and account modifiers. So there is no number in this table that the
media plan cannot account for, and CPL, cost-per-MQL and CAC all reconcile in
every slice without being checked.

The two-pass shape matters. `plan_lead_counts` runs BEFORE the contact pool
exists, because the size of the contact pool is a consequence of how many
people marketing actually acquired (PLAN 2.2) - not a configured number that
the funnel then has to be squeezed into.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from mktconfig import Scenario, lognormal_from_median

STATUS_NEW, STATUS_WORKING = "New", "Working"
STATUS_NURTURE, STATUS_DISQ = "Nurture", "Disqualified"
STATUS_MQL, STATUS_SQL, STATUS_CONV = "MQL", "SQL", "Converted"

# Which lead source a channel produces. Real MAPs record how the person
# arrived, and it is not the same fact as which channel paid for them.
SOURCE_BY_CHANNEL = {
    "Google Ads": ["Paid Ad Click", "Demo Request", "Contact Sales Form"],
    "LinkedIn": ["Paid Ad Click", "Content Download"],
    "Facebook": ["Paid Ad Click", "Content Download"],
    "YouTube": ["Paid Ad Click", "Content Download"],
    "Content Syndication": ["Content Download", "List Purchase"],
    "Email": ["Email Reply", "Content Download", "Demo Request"],
    "Organic Search": ["Content Download", "Demo Request",
                       "Chat Conversation", "Free Trial Signup"],
    "Webinar": ["Webinar Registration"],
    "Trade Show": ["Event Badge Scan"],
    "Customer Event": ["Event Badge Scan"],
    "Partner": ["Partner Referral"],
    "Direct Mail": ["Direct Mail Response"],
}


def plan_lead_counts(s: Scenario, camp: pd.DataFrame, cm: pd.DataFrame,
                     ep: EventPlan, rng: np.random.Generator) -> pd.DataFrame:
    """Leads per campaign-month = spend / effective CPL.

    Returns (campaign_id, month_start, region_name, spend_usd, n_leads,
    effective_cpl). This is the only place lead volume is decided.
    """
    cinfo = camp.set_index("campaign_id")
    df = cm.copy()
    df["channel_name"] = df["campaign_id"].map(cinfo["channel_name"])
    df["_tag"] = df["campaign_id"].map(cinfo["_tag"])
    df["month_start"] = pd.to_datetime(df["month_start"])
    df["months_from_as_of"] = _months_from(s, df["month_start"])

    cpl = df["channel_name"].map(
        {c: v["cpl_usd"] for c, v in s.channels.items()}).astype(float)
    cpl *= df["region_name"].map(
        {r: v["cpl_mult"] for r, v in s.regions.items()}).astype(float)

    # Media inflation: CPL drifts up across history in every real account, and
    # its absence is one of the first things a paid-media lead notices.
    # Normalised to a TTM mean of 1.0 so the drift changes the SHAPE of the CPL
    # trend without moving the headline CPL off the media plan. (PLAN 1)
    span = len(s.timeline.month_starts())
    drift = 1.0 + 0.16 * (df["months_from_as_of"].to_numpy() + span) / span
    ttm_drift = 1.0 + 0.16 * (np.arange(-11, 1) + span) / span
    cpl *= drift / ttm_drift.mean()

    # E1 - the flagship pays more per lead as well as converting worse.
    if ep.flagship:
        cpl[df["_tag"] == "flagship"] *= float(ep.flagship["cpl_mult"])
    # E2 - the gem is cheap as well as good.
    if ep.gem:
        cpl[df["_tag"] == "gem"] *= float(ep.gem["cpl_mult"])
    # E14 - a lookalike expansion mid-flight broadens targeting and doubles
    # cost per lead for two months. Spend does not move, which is what makes it
    # an anomaly worth finding rather than a budget change.
    if ep.cpl_anomaly:
        hit = ((df["_tag"] == "anomaly")
               & df["months_from_as_of"].between(
                   int(ep.cpl_anomaly["month_offset"]),
                   int(ep.cpl_anomaly["month_offset"]) + 1))
        cpl[hit] *= float(ep.cpl_anomaly["cpl_mult"])

    cpl *= rng.uniform(0.88, 1.14, len(df))
    expected = df["spend_usd"].to_numpy() / cpl.to_numpy()
    df["effective_cpl_usd"] = cpl.round(2)
    df["n_leads"] = rng.poisson(np.clip(expected, 0, None))
    return df[df["n_leads"] > 0].reset_index(drop=True)


def _weighted_mean(x: np.ndarray, mask: np.ndarray) -> float:
    """Mean of `x` over `mask`, or 1.0 if the mask is empty."""
    if mask.sum() == 0:
        return 1.0
    return float(x[mask].mean()) or 1.0


def _months_from(s: Scenario, months: pd.Series) -> pd.Series:
    a = s.timeline.as_of_month
    return ((months.dt.year - a.year) * 12 + (months.dt.month - a.month))


def contact_demand(s: Scenario, counts: pd.DataFrame) -> dict[str, int]:
    """How many NEW contacts each region's leads require.

    Sized per region so that no contact is left over: a contact exists in this
    dataset because a campaign found them, and a pool of people nobody ever
    acquired would be exactly the kind of unexplained row a customer asks
    about.
    """
    rate = 1.0 - float(s.universe["reengagement_rate"])
    by_region = counts.groupby("region_name")["n_leads"].sum()
    return {r: int(np.ceil(v * rate * 1.02)) for r, v in by_region.items()}


def build_leads(s: Scenario, counts: pd.DataFrame, camp: pd.DataFrame,
                contacts: pd.DataFrame, accounts: pd.DataFrame,
                sources: pd.DataFrame, ep: EventPlan,
                rng: np.random.Generator) -> pd.DataFrame:
    """Explode the planned counts into lead rows and run them down the funnel."""
    cinfo = camp.set_index("campaign_id")
    n = int(counts["n_leads"].sum())

    rep = counts["n_leads"].to_numpy()
    cid = np.repeat(counts["campaign_id"].to_numpy(), rep)
    month = np.repeat(counts["month_start"].to_numpy(), rep)
    region = np.repeat(counts["region_name"].to_numpy(), rep)
    m_off = np.repeat(counts["months_from_as_of"].to_numpy(), rep)
    channel = np.repeat(counts["channel_name"].to_numpy(), rep)
    tag = np.repeat(counts["_tag"].to_numpy(), rep)

    # Lead dates spread across the month, weekday-weighted.
    dim = pd.to_datetime(month).days_in_month
    day = np.minimum((rng.beta(1.6, 1.6, n) * dim).astype(int) + 1, dim)
    lead_date = pd.to_datetime(month) + pd.to_timedelta(day - 1, unit="D")
    lead_date = pd.DatetimeIndex(
        np.minimum(lead_date, pd.Timestamp(s.timeline.as_of_date)))

    # --- who the lead is -----------------------------------------------------
    contact_id, is_reengaged = _assign_contacts(
        s, contacts, region, pd.Series(lead_date), rng)
    cmap = contacts.set_index("contact_id")
    customer_id = cmap.loc[contact_id, "customer_id"].to_numpy()
    amap = accounts.set_index("customer_id")
    segment_id = amap.loc[customer_id, "segment_id"].to_numpy()
    industry_id = amap.loc[customer_id, "industry_id"].to_numpy()
    geo_key = amap.loc[customer_id, "geo_key"].to_numpy()
    acct_quality = amap.loc[customer_id, "_quality"].to_numpy()
    persona_w = cmap.loc[contact_id, "_persona_weight"].to_numpy()

    seg_name = np.array(list(s.segments))[segment_id - 1]
    seg_quality = np.array([s.segments[x]["quality_mult"] for x in seg_name])
    reg_quality = np.array([s.regions[x]["quality_mult"] for x in region])
    # The lead-quality index. Normalised to a TTM mean of 1.0, so the blended
    # TTM headline still equals the channel mix table. (PLAN 1)
    q_index = s.quality_index(m_off)

    quality = (q_index * reg_quality * seg_quality
               * np.clip(acct_quality, 0.2, 2.2)
               * np.clip(persona_w, 0.3, 1.8) ** 0.55)

    # PLAN 1, and the subtlest part of it. The channel rates in the config are
    # BLENDED TTM rates; the modifiers above express relative differences
    # between leads. If the modifiers do not average to 1.0 on the population
    # they are applied to, every headline drifts off the mix table and the
    # dataset quietly stops meaning what the config says.
    #
    # They do not average to 1.0 on their own, for a reason worth keeping:
    # bigger and better accounts hold more contacts, so they generate more
    # leads, so the lead-weighted mean quality is above the account-weighted
    # one - and each stage selects survivors upward again. Normalising per
    # stage, on that stage's own input population, keeps the whole correlation
    # structure (good leads really do convert better at every step, which is
    # what makes lead_score predictive in Q14) while pinning the blend.
    ttm = m_off >= -11
    quality = quality / _weighted_mean(quality, ttm)

    # --- lead -> MQL ---------------------------------------------------------
    p_mql = np.array([s.channels[c]["lead_to_mql"] for c in channel]) * quality
    if ep.flagship:
        p_mql[tag == "flagship"] *= float(ep.flagship["mql_mult"])
    if ep.gem:
        p_mql[tag == "gem"] *= float(ep.gem["mql_mult"])
    prod_line = cinfo.loc[cid, "_product_line"].to_numpy() \
        if "_product_line" in cinfo.columns else np.array([""] * n)
    # Exponents, not the raw multiplier. A launch lifts the AWARENESS funnel
    # hard - impressions, traffic, lead volume - and the conversion rate only
    # gently, because the extra people it attracts are earlier in their buying
    # cycle. Passing 2.6x straight into a conversion rate moved the company
    # blended lead->MQL by 12 points and quietly took the headline off the mix
    # table. (PLAN 1)
    p_mql *= ep.launch_awareness_mult(prod_line, m_off) ** 0.15
    is_mql = rng.random(n) < np.clip(p_mql, 0, 0.97)

    # --- MQL -> SQL ----------------------------------------------------------
    q_sql = quality / _weighted_mean(quality, ttm & is_mql)
    p_sql = np.array([s.channels[c]["mql_to_sql"] for c in channel]) * q_sql
    if ep.flagship:
        p_sql[tag == "flagship"] *= float(ep.flagship["sql_mult"])
    if ep.gem:
        p_sql[tag == "gem"] *= float(ep.gem["sql_mult"])
    p_sql *= ep.launch_pipeline_mult(prod_line, m_off) ** 0.30
    # E5 - the current-year quality slide, on this step only.
    p_sql *= ep.mql_to_sql_decay(m_off)
    is_sql = is_mql & (rng.random(n) < np.clip(p_sql, 0, 0.95))

    # --- SQL -> opportunity accepted ----------------------------------------
    q_opp = np.clip(quality, 0.55, 1.5) ** 0.5
    q_opp = q_opp / _weighted_mean(q_opp, ttm & is_sql)
    p_opp = np.array([s.channels[c]["sql_to_opp"] for c in channel]) * q_opp
    is_opp = is_sql & (rng.random(n) < np.clip(p_opp, 0, 0.95))

    # --- dates ---------------------------------------------------------------
    lc = s.lifecycle
    d1 = lognormal_from_median(rng, lc["lead_to_mql_days"]["median"],
                               lc["lead_to_mql_days"]["sigma"], n)
    d2 = lognormal_from_median(rng, lc["mql_to_sql_days"]["median"],
                               lc["mql_to_sql_days"]["sigma"], n)
    d3 = lognormal_from_median(rng, lc["sql_to_opp_days"]["median"],
                               lc["sql_to_opp_days"]["sigma"], n)
    as_of = pd.Timestamp(s.timeline.as_of_date)
    mql_date = pd.DatetimeIndex(lead_date + pd.to_timedelta(np.round(d1), unit="D"))
    sql_date = pd.DatetimeIndex(mql_date + pd.to_timedelta(np.round(d2), unit="D"))
    opp_date = pd.DatetimeIndex(sql_date + pd.to_timedelta(np.round(d3), unit="D"))

    # A stage that has not happened yet has not happened. Truncating the funnel
    # at as-of is what creates the immature recent cohorts in PLAN 2.5 - and
    # deleting that truncation to make the last two quarters look better is the
    # single most tempting way to make this dataset lie.
    is_mql &= np.asarray(mql_date <= as_of)
    is_sql &= np.asarray(sql_date <= as_of)
    is_opp &= np.asarray(opp_date <= as_of)

    df = pd.DataFrame({
        "lead_id": np.arange(1, n + 1),
        "lead_date": lead_date.date,
        "contact_id": contact_id.astype(np.int32),
        "customer_id": customer_id.astype(np.int32),
        "campaign_id": cid.astype(np.int32),
        "channel_id": cinfo.loc[cid, "channel_id"].to_numpy().astype(np.int32),
        "source_channel": channel,
        "geo_key": geo_key.astype(np.int32),
        "region_name": region,
        "segment_id": segment_id.astype(np.int32),
        "industry_id": industry_id.astype(np.int32),
        "product_id": cinfo.loc[cid, "product_id"].to_numpy().astype(np.int32),
        "is_reengaged_contact": is_reengaged.astype(np.int8),
        "is_mql": is_mql.astype(np.int8),
        "is_sql": is_sql.astype(np.int8),
        "is_sales_accepted": is_opp.astype(np.int8),
        "mql_date": np.where(is_mql, mql_date.date, None),
        "sql_date": np.where(is_sql, sql_date.date, None),
        "sales_accepted_date": np.where(is_opp, opp_date.date, None),
        "days_lead_to_mql": np.where(is_mql, np.round(d1), np.nan),
        "days_mql_to_sql": np.where(is_sql, np.round(d2), np.nan),
        "lead_score": np.int32(0),          # back-filled from real activity
        "converted_opportunity_id": np.int32(0),
        "_quality": quality,
        "_months_from_as_of": m_off.astype(np.int16),
    })

    src_by_name = sources.set_index("lead_source_name")["lead_source_id"].to_dict()
    pick = rng.random(n)
    source_id = np.zeros(n, dtype=np.int32)
    for ch_name, names in SOURCE_BY_CHANNEL.items():
        m = channel == ch_name
        if not m.any():
            continue
        ids = np.array([src_by_name[x] for x in names])
        source_id[m] = ids[(pick[m] * len(ids)).astype(int)]
    df["lead_source_id"] = source_id

    # Revenue potential is the account's plausible deal size, set at lead time -
    # it is a forecast input, so it must not know the outcome.
    seg_mean = np.array([s.deal["segment_mix"][x]["mean_usd"] for x in seg_name])
    df["revenue_potential_usd"] = (
        seg_mean * np.clip(acct_quality, 0.3, 2.4)
        * rng.uniform(0.55, 1.6, n)).round(0)

    df["lead_status"] = _status(df, rng)
    df["is_disqualified"] = (df["lead_status"] == STATUS_DISQ).astype(np.int8)
    return df


def _assign_contacts(s: Scenario, contacts: pd.DataFrame, region: np.ndarray,
                     lead_date: pd.Series, rng: np.random.Generator):
    """Match each lead to a person in the right region.

    New contacts are consumed in order, re-engagements are drawn from people
    already acquired. Order matters: a lead cannot re-engage a contact who does
    not exist yet, and letting it happen puts touches in a journey before the
    person entered the database.
    """
    n = len(region)
    out = np.zeros(n, dtype=np.int64)
    reeng = np.zeros(n, dtype=bool)
    rate = float(s.universe["reengagement_rate"])

    order = np.argsort(lead_date.to_numpy(), kind="stable")
    pools = {r: g["contact_id"].to_numpy()
             for r, g in contacts.groupby("region_name")}
    cursor = {r: 0 for r in pools}

    reg_ordered = region[order]
    want_reeng = rng.random(n) < rate
    for i, idx in enumerate(order):
        r = reg_ordered[i]
        pool = pools.get(r)
        if pool is None or len(pool) == 0:
            pool = next(iter(pools.values()))
            r = None
        used = cursor.get(r, 0) if r is not None else 0
        if want_reeng[idx] and used > 32:
            out[idx] = pool[rng.integers(0, used)]
            reeng[idx] = True
        elif r is not None and used < len(pool):
            out[idx] = pool[used]
            cursor[r] = used + 1
        else:
            out[idx] = pool[rng.integers(0, max(len(pool), 1))]
            reeng[idx] = True
    return out, reeng


def _status(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Lead status, consistent with the flags by construction.

    Deriving status from the flags rather than sampling it is why the status
    breakdown and the funnel chart can never disagree - which they will, live,
    if both are drawn.
    """
    n = len(df)
    st = np.full(n, STATUS_NEW, dtype=object)
    r = rng.random(n)
    cold = ~df["is_mql"].astype(bool).to_numpy()
    st[cold & (r < 0.34)] = STATUS_WORKING
    st[cold & (r >= 0.34) & (r < 0.68)] = STATUS_NURTURE
    st[cold & (r >= 0.68) & (r < 0.86)] = STATUS_DISQ
    mql_only = (df["is_mql"] == 1) & (df["is_sql"] == 0)
    st[mql_only.to_numpy()] = np.where(r[mql_only.to_numpy()] < 0.24,
                                       STATUS_NURTURE, STATUS_MQL)
    sql_only = (df["is_sql"] == 1) & (df["is_sales_accepted"] == 0)
    st[sql_only.to_numpy()] = np.where(r[sql_only.to_numpy()] < 0.55,
                                       STATUS_DISQ, STATUS_SQL)
    st[(df["is_sales_accepted"] == 1).to_numpy()] = STATUS_CONV
    return st
