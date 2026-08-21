"""Campaigns, creatives and the spend plan.

This is the module the whole dataset hangs off, because of PLAN 2.1: spend is
set here and is EXACT, and every volume downstream is derived from it by
cost-per-lead. Nothing in this dataset can contradict the spend that produced
it, because nothing downstream is free to disagree.

The spend plan is fitted, not sampled. `_fit_spend_grid` runs iterative
proportional fitting over the (channel x region) TTM matrix so that both
margins land on their configured shares simultaneously - channel spend shares
and region spend shares are both constraints, and drawing them independently
satisfies neither. Prior-year blocks are then scaled to the configured YoY,
preserving each channel's own growth spread (E8/E9/E10) and APAC's (E6).

PLAN 2.3 - one source of truth for spend:
  dim_campaign.budget_amount_usd   PLAN. Never summed against actuals.
  fact_ad_performance.spend_usd    ACTUAL, grain of record for paid channels.
  fact_campaign_daily.spend_usd    DERIVED rollup. Built by aggregation in
                                   advertising.py, never drawn.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from mktconfig import Scenario, add_month, month_end

CAMPAIGN_TYPE_BY_CHANNEL = {
    "Google Ads": ["Demand Generation", "Retargeting", "Brand Awareness"],
    "LinkedIn": ["ABM", "Demand Generation", "Brand Awareness"],
    "Facebook": ["Brand Awareness", "Retargeting"],
    "YouTube": ["Brand Awareness", "Product Launch"],
    "Content Syndication": ["Content Syndication", "Demand Generation"],
    "Email": ["Email Nurture", "Demand Generation"],
    "Organic Search": ["Content Syndication", "Brand Awareness"],
    "Webinar": ["Webinar", "Demand Generation"],
    "Trade Show": ["Trade Show", "Brand Awareness"],
    "Customer Event": ["Customer Event"],
    "Partner": ["ABM", "Demand Generation"],
    "Direct Mail": ["ABM", "Retargeting"],
}
OBJECTIVES = {"Brand Awareness": "Awareness", "Demand Generation": "Pipeline",
              "Product Launch": "Awareness", "Webinar": "Pipeline",
              "Customer Event": "Retention", "Trade Show": "Pipeline",
              "Retargeting": "Conversion", "ABM": "Pipeline",
              "Content Syndication": "Leads", "Email Nurture": "Conversion"}
AGENCIES = ["In-House", "In-House", "In-House", "Redshift Media",
            "Bluepeak Partners", "Northlight Agency"]
THEMES = ["Modern Analytics", "Data Consolidation", "AI Adoption",
          "Cost of Legacy BI", "Real-Time Decisions", "Self-Service BI",
          "Governed Data", "Forecast Accuracy", "Analytics ROI",
          "Migration Made Simple", "Embedded Insights", "Executive Reporting"]
CREATIVE_FORMATS = {
    "Google Ads": ["Responsive Search", "Display Banner", "Discovery"],
    "LinkedIn": ["Sponsored Content", "Message Ad", "Document Ad",
                 "Conversation Ad"],
    "Facebook": ["Feed Image", "Carousel", "Video Feed"],
    "YouTube": ["Bumper 6s", "In-Stream 30s", "Discovery Thumbnail"],
    "Content Syndication": ["Content Offer", "Newsletter Placement"],
}


def build_spend_plan(s: Scenario, ep: EventPlan) -> pd.DataFrame:
    """Monthly spend by (month, channel, region). Exact by construction.

    Returns one row per (month_start, channel, region) with `spend_usd`. This
    is the plan the campaigns are cut from and the actuals are drawn around.
    """
    months = s.timeline.month_starts()
    m_off = np.array([_months_between(s.timeline.as_of_month, m) for m in months])

    chans = list(s.channels)
    regs = list(s.regions)
    ttm_total = float(s.spend["ttm_total_usd"])

    # Seasonality, normalised so a full year of it sums to 12.
    season_cfg = np.array(s.spend["monthly_seasonality"], dtype=float)
    season_cfg = season_cfg / season_cfg.mean()
    season = np.array([season_cfg[m.month - 1] for m in months])

    # --- TTM (channel x region) matrix, fitted to both margins ---------------
    ch_target = np.array([s.channels[c]["spend_share"] for c in chans]) * ttm_total
    rg_target = np.array([s.regions[r]["spend_share"] for r in regs]) * ttm_total
    grid = _fit_spend_grid(np.outer(ch_target, rg_target) / ttm_total,
                           ch_target, rg_target)

    # --- year-over-year, per channel and per region -------------------------
    yoy = float(s.spend["yoy_growth"])
    ch_growth = np.array([s.channels[c].get("spend_yoy", yoy) for c in chans])
    rg_growth = np.full(len(regs), yoy)
    if ep.apac_region in regs:
        rg_growth[regs.index(ep.apac_region)] = ep.apac_spend_growth

    rows = []
    for i, m in enumerate(months):
        block = min(int((-m_off[i]) // 12), 2)     # 0 = TTM, 1 = prior, 2 = before
        # Relative decay per channel/region for older blocks. Normalised to the
        # company total below, so these set the SPREAD, not the level.
        ch_f = 1.0 / np.power(1.0 + ch_growth, block)
        rg_f = 1.0 / np.power(1.0 + rg_growth, block)
        cell = grid * np.outer(ch_f, rg_f) * season[i] / 12.0
        for ci, c in enumerate(chans):
            for ri, r in enumerate(regs):
                rows.append((m, c, r, cell[ci, ri], block))
    df = pd.DataFrame(rows, columns=["month_start", "channel_name",
                                     "region_name", "spend_usd", "_block"])

    # --- normalise each trailing-12-month block to its exact total ----------
    for b, target in targets_for(s).items():
        m = df["_block"] == b
        cur = df.loc[m, "spend_usd"].sum()
        if cur > 0:
            # The first block of history is partial when history_years*12 is not
            # a multiple of 12; scale it by the months it actually has.
            n_months = df.loc[m, "month_start"].nunique()
            df.loc[m, "spend_usd"] *= (target * n_months / 12.0) / cur

    # --- and re-fit the TTM block so both margins are exact after scaling ---
    ttm = df["_block"] == 0
    piv = df[ttm].pivot_table(index="channel_name", columns="region_name",
                              values="spend_usd", aggfunc="sum")
    piv = piv.reindex(index=chans, columns=regs)
    fitted = _fit_spend_grid(piv.to_numpy(), ch_target, rg_target)
    scale = np.divide(fitted, piv.to_numpy(), out=np.ones_like(fitted),
                      where=piv.to_numpy() > 0)
    sc = pd.DataFrame(scale, index=chans, columns=regs).stack()
    sc.index.names = ["channel_name", "region_name"]
    key = pd.MultiIndex.from_frame(df.loc[ttm, ["channel_name", "region_name"]])
    df.loc[ttm, "spend_usd"] *= sc.reindex(key).to_numpy()
    return df


def _fit_spend_grid(seed: np.ndarray, row_target: np.ndarray,
                    col_target: np.ndarray, iters: int = 60) -> np.ndarray:
    """Iterative proportional fitting.

    Channel shares and region shares are both hard constraints. Drawing region
    within channel satisfies the channel margin and misses the region one;
    IPF satisfies both, which is what lets validate.py assert each margin
    exactly rather than "within 5%".
    """
    m = np.where(seed > 0, seed, 1e-9).astype(float)
    for _ in range(iters):
        m *= (row_target / m.sum(axis=1))[:, None]
        m *= (col_target / m.sum(axis=0))[None, :]
    return m


def targets_for(s: Scenario) -> dict[int, float]:
    """Exact spend total for each trailing-12-month block."""
    ttm = float(s.spend["ttm_total_usd"])
    yoy = float(s.spend["yoy_growth"])
    prior = float(s.spend["prior_yoy_growth"])
    return {0: ttm, 1: ttm / (1 + yoy), 2: ttm / (1 + yoy) / (1 + prior)}


def _months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def build_campaigns(s: Scenario, plan: pd.DataFrame, products: pd.DataFrame,
                    segments: pd.DataFrame, industries: pd.DataFrame,
                    channels: pd.DataFrame, ep: EventPlan,
                    rng: np.random.Generator
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cut the spend plan into named campaigns.

    Returns (dim_campaign, campaign_month) where `campaign_month` carries the
    monthly actual spend each campaign is responsible for. Everything after
    this module works from `campaign_month`, so the plan can never be
    contradicted downstream.
    """
    tl = s.timeline
    chan_id = channels.set_index("channel_name")["channel_id"].to_dict()
    prod_ids = products["product_id"].to_numpy()
    prod_w = products["revenue_share"].to_numpy()
    prod_line = products.set_index("product_id")["product_line"].to_dict()
    seg_names = segments["segment_name"].tolist()
    ind_names = industries["industry_name"].tolist()

    camp_rows, month_rows = [], []
    cid = 0

    # --- the named event campaigns first, so they get memorable low ids -----
    named = []
    if ep.flagship:
        named.append((ep.flagship, "flagship"))
    if ep.gem:
        named.append((ep.gem, "gem"))
    if ep.cpl_anomaly:
        named.append(({**ep.cpl_anomaly,
                       "start_month_offset": int(ep.cpl_anomaly["month_offset"]) - 2,
                       "duration_months": 5,
                       "channel": "Google Ads",
                       "spend_usd": 640_000}, "anomaly"))
    for ev, tag in named:
        cid += 1
        ep.named_campaign_ids[tag] = cid
        start = tl.offset_month(int(ev["start_month_offset"]))
        dur = int(ev["duration_months"])
        end = month_end(add_month(start, dur - 1))
        ch = ev["channel"]
        camp_rows.append(_campaign_row(
            cid, ev["campaign_name"], ch, chan_id[ch],
            "ABM" if tag == "flagship" else
            ("Webinar" if tag == "gem" else "Retargeting"),
            "North America" if tag != "gem" else "Global",
            int(rng.choice(prod_ids, p=prod_w / prod_w.sum())),
            "Enterprise" if tag == "flagship" else "All Segments",
            "All Industries", start, end, float(ev["spend_usd"]),
            "In-House", tag))
        # Spend is spread with a mid-flight hump: campaigns ramp up, peak, and
        # taper, which is what makes a monthly CPL anomaly visible at all.
        w = _flight_curve(dur, rng)
        for k in range(dur):
            m = add_month(start, k)
            if m > tl.as_of_month:
                break
            month_rows.append((cid, m, float(ev["spend_usd"]) * w[k],
                               "North America" if tag != "gem" else None))

    named_spend = pd.DataFrame(month_rows, columns=["campaign_id", "month_start",
                                                    "spend_usd", "region_name"])

    # --- subtract the named campaigns from the plan they sit inside ---------
    # Otherwise the flagship's $1.2M is spend the company never budgeted, and
    # the TTM total stops matching the tile.
    plan = plan.copy()
    if len(named_spend):
        for cid_named, row in named_spend.groupby("campaign_id"):
            camp = camp_rows[cid_named - 1]
            ch = camp["channel_name"]
            for _, r in row.iterrows():
                mask = ((plan["month_start"] == r["month_start"])
                        & (plan["channel_name"] == ch))
                pool = plan.loc[mask, "spend_usd"]
                if pool.sum() <= 0:
                    continue
                take = min(float(r["spend_usd"]), float(pool.sum()) * 0.92)
                plan.loc[mask, "spend_usd"] -= pool / pool.sum() * take

    # --- ordinary campaigns: one per (channel, region, quarter) -------------
    plan["quarter"] = pd.to_datetime(plan["month_start"]).dt.to_period("Q")
    theme_i = 0
    for (ch, reg, q), grp in plan.groupby(["channel_name", "region_name",
                                           "quarter"], sort=True):
        total = float(grp["spend_usd"].sum())
        if total < 1_000:
            continue
        n_camp = 2 if total > 220_000 else 1
        splits = rng.dirichlet(np.ones(n_camp) * 4.0)
        for k in range(n_camp):
            cid += 1
            ctypes = CAMPAIGN_TYPE_BY_CHANNEL[ch]
            ctype = ctypes[(cid + k) % len(ctypes)]
            pid = int(rng.choice(prod_ids, p=prod_w / prod_w.sum()))
            # The launch product takes over its channel's campaigns around the
            # launch window, which is what gives the impact timeline a cause.
            if (ep.launch_line
                    and _months_between(tl.as_of_month, grp["month_start"].min())
                    >= ep.launch_month - ep.launch_pre
                    and rng.random() < 0.28):
                match = products.loc[products["product_line"] == ep.launch_line,
                                     "product_id"]
                if len(match):
                    pid = int(match.iloc[0])
                    ctype = "Product Launch"
            theme = THEMES[theme_i % len(THEMES)]
            theme_i += 1
            seg = str(rng.choice(seg_names + ["All Segments"]))
            ind = str(rng.choice(ind_names + ["All Industries", "All Industries"]))
            start = grp["month_start"].min()
            end = month_end(grp["month_start"].max())
            name = (f"{prod_line[pid]} - {theme} - {reg} "
                    f"{q.strftime('%YQ%q') if hasattr(q, 'strftime') else q}")
            camp_rows.append(_campaign_row(
                cid, name, ch, chan_id[ch], ctype, reg, pid, seg, ind,
                start, end, total * splits[k],
                str(rng.choice(AGENCIES)), "standard"))
            for _, r in grp.iterrows():
                month_rows.append((cid, r["month_start"],
                                   float(r["spend_usd"]) * splits[k], reg))

    camp = pd.DataFrame(camp_rows)
    cm = pd.DataFrame(month_rows, columns=["campaign_id", "month_start",
                                           "spend_usd", "region_name"])
    cm = cm[cm["spend_usd"] > 0].reset_index(drop=True)

    # Region on the named campaigns follows the plan they displaced.
    cm["region_name"] = cm["region_name"].fillna("North America")

    # A named campaign can be larger than the plan pool it displaces in a given
    # month, so the displacement above is capped and leaves a small residual.
    # Absorb it in the ORDINARY campaigns only: the event campaigns are
    # configured amounts that docs/EVENTS.md quotes, and a headline that is
    # 0.1% off is a worse trade than a flagship that is 0.1% off.
    named_ids = set(ep.named_campaign_ids.values())
    is_named = cm["campaign_id"].isin(named_ids)
    m_off = pd.Series([_months_between(tl.as_of_month, m)
                       for m in cm["month_start"]], index=cm.index)
    block = np.clip((-m_off) // 12, 0, 2)
    for b, target in targets_for(s).items():
        sel = block == b
        if not sel.any():
            continue
        n_months = cm.loc[sel, "month_start"].nunique()
        want = target * n_months / 12.0
        fixed = float(cm.loc[sel & is_named, "spend_usd"].sum())
        pool = float(cm.loc[sel & ~is_named, "spend_usd"].sum())
        if pool > 0 and want > fixed:
            cm.loc[sel & ~is_named, "spend_usd"] *= (want - fixed) / pool

    # Budget is PLAN: what was approved, which is deliberately not what was
    # spent. The variance is a column the CMO page needs and the note had no
    # way to produce. (PLAN 2.3)
    actual = cm.groupby("campaign_id")["spend_usd"].sum()
    camp = camp.set_index("campaign_id")
    camp["actual_spend_usd"] = actual.reindex(camp.index).fillna(0.0)
    camp["budget_amount_usd"] = (
        camp["actual_spend_usd"]
        * rng.normal(1.04, 0.11, len(camp)).clip(0.72, 1.45)).round(2)
    camp["budget_variance_usd"] = (camp["actual_spend_usd"]
                                   - camp["budget_amount_usd"]).round(2)
    camp = camp.reset_index()
    # The launch product's line is carried on the campaign so leads.py can
    # apply the launch ramps without re-joining dim_product per lead.
    camp["_product_line"] = camp["product_id"].map(prod_line)
    camp["campaign_status"] = np.where(
        pd.to_datetime(camp["end_date"]) < pd.Timestamp(tl.as_of_date),
        "Completed", "Active")
    return camp, cm


def _campaign_row(cid, name, channel, channel_id, ctype, region, product_id,
                  segment, industry, start, end, budget, agency, tag) -> dict:
    return {
        "campaign_id": cid, "campaign_name": name, "campaign_type": ctype,
        "channel_id": channel_id, "channel_name": channel,
        "campaign_category": OBJECTIVES.get(ctype, "Pipeline"),
        "objective": OBJECTIVES.get(ctype, "Pipeline"),
        "product_id": product_id, "target_segment": segment,
        "target_industry": industry, "target_region": region,
        "start_date": start, "end_date": end,
        "agency": agency, "_tag": tag,
    }


def _flight_curve(n: int, rng: np.random.Generator) -> np.ndarray:
    """Ramp-peak-taper. Flat monthly spend is the tell of a generated dataset."""
    if n == 1:
        return np.array([1.0])
    x = np.linspace(-1.6, 1.6, n)
    w = np.exp(-0.5 * x ** 2) * rng.uniform(0.88, 1.12, n)
    return w / w.sum()


def build_dim_ad_creative(s: Scenario, camp: pd.DataFrame,
                          rng: np.random.Generator) -> pd.DataFrame:
    """Creatives, for paid channels only.

    This is the grain `fact_ad_performance` sits at. Non-paid channels have no
    creative and no ad grain, which is exactly why `fact_campaign_daily` has to
    exist as a rollup rather than as the only spend table.
    """
    n_per = int(s.sizes["creatives_per_campaign"])
    paid = camp[camp["channel_name"].isin(CREATIVE_FORMATS)]
    rows = []
    aid = 0
    for _, c in paid.iterrows():
        fmts = CREATIVE_FORMATS[c["channel_name"]]
        k = max(1, int(rng.integers(max(1, n_per - 2), n_per + 2)))
        for j in range(k):
            aid += 1
            rows.append({
                "ad_creative_id": aid, "campaign_id": int(c["campaign_id"]),
                "channel_id": int(c["channel_id"]),
                "creative_name": f"{c['campaign_name'][:46]} / V{j + 1}",
                "creative_format": fmts[j % len(fmts)],
                "creative_variant": f"V{j + 1}",
                "headline_theme": THEMES[(aid + j) % len(THEMES)],
                "is_control": int(j == 0),
                # Creative quality is what makes A/B testing visible: the same
                # campaign, the same spend, and a 3x spread in CTR.
                "_ctr_mult": float(np.clip(rng.lognormal(0.0, 0.42), 0.35, 3.1)),
                "_cvr_mult": float(np.clip(rng.lognormal(0.0, 0.30), 0.45, 2.4)),
            })
    return pd.DataFrame(rows)


def build_fact_marketing_budget(s: Scenario, cm: pd.DataFrame,
                                camp: pd.DataFrame, channels: pd.DataFrame,
                                rng: np.random.Generator) -> pd.DataFrame:
    """Time-phased plan by channel, region and month. (PLAN 2.8)

    The note carried a single `budget` number on the campaign and no calendar,
    which leaves "are we on budget?" - the first question any CMO asks -
    unanswerable. Plan is set at the start of each quarter and does not move;
    actuals do, which is the point.
    """
    j = cm.merge(camp[["campaign_id", "channel_id", "channel_name"]],
                 on="campaign_id", how="left")
    act = (j.groupby(["month_start", "channel_id", "channel_name",
                      "region_name"], as_index=False)["spend_usd"].sum()
           .rename(columns={"spend_usd": "actual_spend_usd"}))
    # Plan is quarterly, spread evenly across the quarter's months, and set
    # before the quarter starts - so it is smooth where actuals are lumpy.
    act["quarter"] = pd.to_datetime(act["month_start"]).dt.to_period("Q")
    q = act.groupby(["quarter", "channel_id", "channel_name", "region_name"],
                    as_index=False)["actual_spend_usd"].sum()
    q["plan_total"] = (q["actual_spend_usd"]
                       * rng.normal(1.03, 0.09, len(q)).clip(0.80, 1.35))
    months_in_q = act.groupby(["quarter", "channel_id", "region_name"])[
        "month_start"].transform("nunique")
    out = act.merge(q[["quarter", "channel_id", "region_name", "plan_total"]],
                    on=["quarter", "channel_id", "region_name"], how="left")
    out["budget_amount_usd"] = (out["plan_total"] / months_in_q).round(2)
    out["actual_spend_usd"] = out["actual_spend_usd"].round(2)
    out["variance_usd"] = (out["actual_spend_usd"]
                           - out["budget_amount_usd"]).round(2)
    out["variance_pct"] = (out["variance_usd"]
                           / out["budget_amount_usd"].replace(0, np.nan)).round(4)
    out["fiscal_quarter_name"] = out["quarter"].astype(str)
    out = out.drop(columns=["quarter", "plan_total"])
    out.insert(0, "marketing_budget_id", np.arange(1, len(out) + 1))
    return out
