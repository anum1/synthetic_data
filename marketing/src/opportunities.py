"""fact_opportunity and fact_opportunity_stage.

Where PLAN 2.5 becomes load-bearing. An opportunity closes a full sales cycle
after the lead that created it, so a deal closing this month was sourced by a
campaign that ran six to nine months ago. Two consequences the demo has to
carry rather than hide:

  - Campaigns from the last two quarters CANNOT have closed revenue. Their
    cohorts are immature, not failing, and `pipeline_maturity_pct` on
    fact_campaign_summary is what says so.
  - Revenue measured by CLOSE DATE lags lead volume. When leads grow 31% and
    revenue grows 3%, part of that gap is the lag and part is the quality
    decay. Separating the two is the best question in the dataset.

Nothing here truncates or back-dates to make recent periods look better. A
close date after as-of means the deal is still open, and it stays open.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dims import STAGES
from events import EventPlan
from mktconfig import Scenario, lognormal_from_median

OPEN_STAGES = [s[0] for s in STAGES if not s[0].startswith("Closed")]


def build_opportunities(s: Scenario, lead: pd.DataFrame, camp: pd.DataFrame,
                        accounts: pd.DataFrame, reps: pd.DataFrame,
                        products: pd.DataFrame, lost_reasons: pd.DataFrame,
                        ep: EventPlan, rng: np.random.Generator
                        ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (fact_opportunity, fact_opportunity_stage, lead with FK filled)."""
    src = lead[lead["is_sales_accepted"] == 1].reset_index(drop=True)
    n = len(src)
    as_of = pd.Timestamp(s.timeline.as_of_date)

    seg_names = np.array(list(s.segments))[src["segment_id"].to_numpy() - 1]
    region = src["region_name"].to_numpy()
    channel = src["source_channel"].to_numpy()
    quality = src["_quality"].to_numpy()
    m_off = src["_months_from_as_of"].to_numpy()

    # --- ownership -----------------------------------------------------------
    rep_id, rep_eff = _assign_reps(reps, region, seg_names, rng)

    # --- probability of winning ---------------------------------------------
    # Computed BEFORE the amount, because the amount normalisation has to be
    # weighted by it: channels that bring big deals (Trade Show 1.45x, Partner
    # 1.30x) also convert best, so won deals over-select large ones and an
    # unweighted normalisation lands the average won deal 15% high.
    ttm = m_off >= -11
    p_won = np.array([s.channels[c]["opp_to_won"] for c in channel])
    qw = rep_eff * np.clip(quality, 0.5, 1.8) ** 0.5
    qw = qw / (qw[ttm].mean() if ttm.any() else 1.0)
    p_won = np.clip(p_won * qw, 0.02, 0.95)

    # --- amount --------------------------------------------------------------
    mix = s.deal["segment_mix"]
    mean = np.array([mix[x]["mean_usd"] for x in seg_names])
    sigma = np.array([mix[x]["sigma"] for x in seg_names])
    # Configured value is the MEAN, so shift the log-mean down by sigma^2/2.
    # Drawing exp(normal(log(mean), sigma)) instead makes `mean` the median and
    # inflates every deal total by exp(sigma^2/2) - 36% for Enterprise.
    amount = np.exp(rng.normal(np.log(mean) - sigma ** 2 / 2.0, sigma))

    dm = (np.array([s.channels[c]["deal_mult"] for c in channel])
          * np.array([s.regions[r]["deal_mult"] for r in region])
          * np.clip(quality, 0.4, 2.0) ** 0.45)
    if ep.gem:
        dm[src["campaign_id"].to_numpy()
           == ep.named_campaign_ids.get("gem", -1)] *= float(ep.gem["deal_mult"])
    prod_line = camp.set_index("campaign_id")["_product_line"].reindex(
        src["campaign_id"]).to_numpy()
    dm *= ep.launch_pipeline_mult(prod_line, m_off) ** 0.30
    # Same discipline as the funnel rates (PLAN 1): the multipliers express
    # relative differences, so they are pinned to a mean of 1.0 - weighted by
    # win probability, so it is the average WON deal that lands on the segment
    # mix, which is the number the headline quotes.
    wt = p_won[ttm]
    dm = dm / ((dm[ttm] * wt).sum() / wt.sum() if ttm.any() else 1.0)
    amount = (amount * dm).round(2)

    # --- cycle and close -----------------------------------------------------
    cyc_med = np.array([s.segments[x]["cycle_days_median"] for x in seg_names])
    # Bigger deals take longer. Without this, a $400K deal closes as fast as a
    # $9K one and every velocity chart is flat.
    cyc_med = cyc_med * np.clip(amount / mean, 0.35, 4.0) ** 0.22
    cycle = np.round(lognormal_from_median(
        rng, 1.0, float(s.lifecycle["cycle_sigma"]), n) * cyc_med)
    cycle = np.clip(cycle, 7, 900).astype(int)

    open_date = pd.to_datetime(src["sales_accepted_date"])
    expected_close = open_date + pd.to_timedelta(cyc_med.round(), unit="D")
    actual_close = open_date + pd.to_timedelta(cycle, unit="D")
    is_closed = (actual_close <= as_of).to_numpy()

    # E16 - one region stops closing what marketing hands it. Keyed to the
    # CLOSE month, not the lead month: a rep team that stops converting affects
    # the deals it is working now, and those were sourced six to nine months
    # ago. Keyed to the lead month the event was invisible in closed deals,
    # because the leads it touched had not closed yet.
    #
    # Applied after the normalisation above so the event moves the blend rather
    # than being absorbed by it.
    close_m_off = ((actual_close.dt.year - s.timeline.as_of_month.year) * 12
                   + (actual_close.dt.month - s.timeline.as_of_month.month)
                   ).to_numpy()
    p_won = np.clip(p_won * ep.region_quality_mult(region, close_m_off),
                    0.02, 0.95)
    is_won = is_closed & (rng.random(n) < p_won)

    # --- stage ---------------------------------------------------------------
    # object dtype, not the '<U11' numpy infers from these two literals -
    # "Qualification" is 13 characters and silently truncates into a fixed
    # width array.
    stage = np.empty(n, dtype=object)
    stage[:] = np.where(is_won, "Closed Won",
                        np.where(is_closed, "Closed Lost", ""))
    open_mask = stage == ""
    # An open deal's stage follows how far through its expected cycle it is:
    # a deal opened last week is in Discovery, one opened six months ago is in
    # Negotiation. Drawing the stage at random instead makes every velocity and
    # stuck-deal analysis meaningless.
    progress = np.clip(
        (as_of - open_date).dt.days.to_numpy() / np.maximum(cycle, 1), 0, 0.999)
    idx = np.clip((progress * len(OPEN_STAGES)).astype(int),
                  0, len(OPEN_STAGES) - 1)
    stage[open_mask] = np.array(OPEN_STAGES)[idx[open_mask]]

    prob_map = {n_: p for n_, _o, p in STAGES}
    probability = np.array([prob_map[x] for x in stage])

    lr_ids = lost_reasons["lost_reason_id"].to_numpy()
    lr_w = lost_reasons["reason_share"].to_numpy()
    lost_id = np.where(is_closed & ~is_won,
                       rng.choice(lr_ids, size=n, p=lr_w / lr_w.sum()), 0)

    opp = pd.DataFrame({
        "opportunity_id": np.arange(1, n + 1),
        "customer_id": src["customer_id"].to_numpy().astype(np.int32),
        "contact_id": src["contact_id"].to_numpy().astype(np.int32),
        "lead_id": src["lead_id"].to_numpy().astype(np.int32),
        "campaign_id": src["campaign_id"].to_numpy().astype(np.int32),
        "channel_id": src["channel_id"].to_numpy().astype(np.int32),
        "source_channel": channel,
        "sales_rep_id": rep_id.astype(np.int32),
        "product_id": src["product_id"].to_numpy().astype(np.int32),
        "segment_id": src["segment_id"].to_numpy().astype(np.int32),
        "industry_id": src["industry_id"].to_numpy().astype(np.int32),
        "geo_key": src["geo_key"].to_numpy().astype(np.int32),
        "region_name": region,
        "opportunity_date": open_date.dt.date,
        "expected_close_date": expected_close.dt.date,
        "actual_close_date": np.where(is_closed, actual_close.dt.date, None),
        "stage_name": stage,
        "probability": probability,
        "amount_usd": amount,
        "is_closed": is_closed.astype(np.int8),
        "is_won": is_won.astype(np.int8),
        "lost_reason_id": lost_id.astype(np.int32),
        "sales_cycle_days": np.where(is_closed, cycle, np.nan),
        "_cycle": cycle,
        "_months_from_as_of": m_off.astype(np.int16),
    })
    opp["won_amount_usd"] = np.where(is_won, amount, 0.0)
    opp["open_pipeline_usd"] = np.where(~is_closed, amount, 0.0)
    opp["weighted_pipeline_usd"] = (opp["open_pipeline_usd"]
                                    * opp["probability"]).round(2)

    opp = _apply_hero_deals(s, opp, ep, rng)
    stages = _build_stage_history(s, opp, rng)

    lead = lead.copy()
    fk = pd.Series(opp["opportunity_id"].to_numpy(),
                   index=opp["lead_id"].to_numpy())
    lead["converted_opportunity_id"] = (
        lead["lead_id"].map(fk).fillna(0).astype(np.int32))
    return opp, stages, lead


def _assign_reps(reps: pd.DataFrame, region: np.ndarray, seg: np.ndarray,
                 rng: np.random.Generator):
    """Match each opportunity to a rep who covers its region and segment."""
    active = reps[reps["is_active"] == 1]
    n = len(region)
    out = np.zeros(n, dtype=np.int64)
    eff = np.ones(n)
    pools = {k: (g["sales_rep_id"].to_numpy(), g["_effectiveness"].to_numpy())
             for k, g in active.groupby(["region_name", "segment_focus"])}
    reg_pools = {k: (g["sales_rep_id"].to_numpy(), g["_effectiveness"].to_numpy())
                 for k, g in active.groupby("region_name")}
    frame = pd.DataFrame({"r": region, "s": seg})
    for (r, sg), grp in frame.groupby(["r", "s"], sort=False):
        pool = pools.get((r, sg)) or reg_pools.get(r)
        if pool is None:
            pool = (active["sales_rep_id"].to_numpy(),
                    active["_effectiveness"].to_numpy())
        ids, e = pool
        pick = rng.integers(0, len(ids), len(grp))
        ix = grp.index.to_numpy()
        out[ix] = ids[pick]
        eff[ix] = e[pick]
    return out, eff


def _apply_hero_deals(s: Scenario, opp: pd.DataFrame, ep: EventPlan,
                      rng: np.random.Generator) -> pd.DataFrame:
    """E12 - give the hero accounts their headline deal, won, at a known date.

    The journey page shows one account at a time, so the deal at the end of it
    has to be worth showing. Picking the largest existing deal instead would
    work exactly once, then move the next time the data is regenerated.
    """
    opp = opp.copy()
    opp["is_hero_journey"] = np.int8(0)
    if ep.hero_count == 0:
        return opp
    # Settle the final heroes from the candidates that actually closed a deal,
    # largest first, so the journey page always has something worth opening.
    won = opp[(opp["customer_id"].isin(ep.hero_candidate_ids))
              & (opp["is_won"] == 1) & (opp["is_closed"] == 1)]
    if won.empty:
        won = opp[opp["customer_id"].isin(ep.hero_candidate_ids)]
    chosen = (won.sort_values("amount_usd", ascending=False)
              .drop_duplicates("customer_id")["customer_id"]
              .head(ep.hero_count).to_numpy())
    ep.hero_customer_ids = chosen
    for i, cid in enumerate(chosen):
        cand = opp.index[(opp["customer_id"] == cid)]
        if len(cand) == 0:
            continue
        # The account's largest opportunity becomes the hero deal.
        ix = opp.loc[cand, "amount_usd"].idxmax()
        opened = pd.Timestamp(opp.loc[ix, "opportunity_date"])
        as_of = pd.Timestamp(s.timeline.as_of_date)
        close = s.timeline.offset_month(int(ep.hero_close_offsets[
            i % len(ep.hero_close_offsets)]))
        close = pd.Timestamp(close) + pd.Timedelta(days=int(rng.integers(3, 26)))
        # The configured close offset is a preference, not a licence to date a
        # deal before it opened. Clamp it into the only window that can be true;
        # if even the earliest valid close is in the future, keep the date the
        # deal already had rather than inventing one.
        earliest = opened + pd.Timedelta(days=21)
        if earliest > as_of:
            close = pd.Timestamp(opp.loc[ix, "actual_close_date"])
        else:
            close = min(max(close, earliest), as_of)
        amt = float(ep.hero_deal_usd[i % len(ep.hero_deal_usd)])
        opp.loc[ix, ["amount_usd", "won_amount_usd", "stage_name",
                     "probability", "is_closed", "is_won", "lost_reason_id",
                     "open_pipeline_usd", "weighted_pipeline_usd",
                     "is_hero_journey"]] = [amt, amt, "Closed Won", 1.0, 1, 1,
                                            0, 0.0, 0.0, 1]
        opp.loc[ix, "actual_close_date"] = close.date()
        opp.loc[ix, "sales_cycle_days"] = max((close - opened).days, 14)
    return opp


def _build_stage_history(s: Scenario, opp: pd.DataFrame,
                         rng: np.random.Generator) -> pd.DataFrame:
    """One row per (opportunity, stage entered), with entry and exit dates.

    The note listed this table and gave it no schema, which leaves stage
    velocity and stuck-deal analysis - the whole of Q6 - unanswerable.
    """
    order = {n: o for n, o, _p in STAGES}
    reached = opp["stage_name"].map(order).to_numpy()
    # A closed deal traversed the open stages before closing; an open deal has
    # traversed up to where it now sits.
    closed = opp["is_closed"].to_numpy() == 1
    n_open_stages = np.where(closed, len(OPEN_STAGES), reached)
    n_rows = n_open_stages + closed.astype(int)

    opp_ix = np.repeat(np.arange(len(opp)), n_rows)
    pos = np.arange(len(opp_ix)) - np.repeat(
        np.concatenate([[0], np.cumsum(n_rows)[:-1]]), n_rows)
    kk = np.repeat(n_rows, n_rows)
    is_final = pos == kk - 1

    stage_name = np.empty(len(opp_ix), dtype=object)
    stage_name[:] = np.array(OPEN_STAGES, dtype=object)[
        np.minimum(pos, len(OPEN_STAGES) - 1)]
    final_closed = is_final & np.repeat(closed, n_rows)
    stage_name[final_closed] = np.repeat(
        opp["stage_name"].to_numpy(), n_rows)[final_closed]

    start = pd.to_datetime(opp["opportunity_date"]).to_numpy()
    cyc = opp["_cycle"].to_numpy()
    # Deals do not spend equal time in each stage: Evaluation and Negotiation
    # are where they sit, and that shape is what a velocity chart is for.
    shape = np.array([0.14, 0.16, 0.28, 0.18, 0.24])
    cum = np.concatenate([[0.0], np.cumsum(shape)])
    frac_in = cum[np.minimum(pos, len(shape))]
    frac_out = cum[np.minimum(pos + 1, len(shape))]
    jitter = rng.uniform(0.85, 1.15, len(opp_ix))
    days_in = np.repeat(cyc, n_rows) * frac_in * jitter
    days_out = np.repeat(cyc, n_rows) * frac_out * jitter

    as_of = np.datetime64(s.timeline.as_of_date)
    entered = np.repeat(start, n_rows) + np.round(days_in).astype("timedelta64[D]")
    exited = np.repeat(start, n_rows) + np.round(days_out).astype("timedelta64[D]")
    entered = np.minimum(entered, as_of)
    still_here = is_final & ~np.repeat(closed, n_rows)
    exited = np.where(still_here, np.datetime64("NaT"),
                      np.minimum(exited, as_of))

    df = pd.DataFrame({
        "opportunity_stage_id": np.arange(1, len(opp_ix) + 1),
        "opportunity_id": opp["opportunity_id"].to_numpy()[opp_ix].astype(np.int32),
        "customer_id": opp["customer_id"].to_numpy()[opp_ix].astype(np.int32),
        "stage_name": stage_name,
        "stage_order": [order[x] for x in stage_name],
        "entered_date": entered.astype("datetime64[D]"),
        "exited_date": exited.astype("datetime64[D]"),
        "sequence": (pos + 1).astype(np.int16),
        "is_current_stage": still_here.astype(np.int8),
    })
    df["days_in_stage"] = ((pd.to_datetime(df["exited_date"]).fillna(
        pd.Timestamp(s.timeline.as_of_date))
        - pd.to_datetime(df["entered_date"])).dt.days).clip(lower=0)
    return df
