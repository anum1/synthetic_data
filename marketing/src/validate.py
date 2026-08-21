#!/usr/bin/env python3
"""Post-generation checks.

Four families:

  INTEGRITY   keys resolve, journeys are ordered, no touch precedes the campaign
              that produced it, and the funnel flags cannot contradict the
              status column beside them.
  RECONCILE   spend reconciles from the ad grain up through the daily rollup to
              the campaign totals, and every pre-aggregate reproduces the fact
              table it was built from. PLAN 2.3 lives or dies here.
  ATTRIBUTION the PLAN 2.4 invariant: weights sum to 1.0 per (opportunity,
              model), and total attributed revenue is IDENTICAL under all five
              models and equal to closed-won. If this fails, the best scene in
              the demo is showing five different companies.
  NARRATIVE   the blended headline equals what the channel mix table derives
              (PLAN 1), and every enabled event is VISIBLE in the aggregates -
              measured, in the window where the ramp has actually arrived.

The narrative checks are the ones that earn their keep. Random noise routinely
swamps a planted signal, and the usual way to discover that is live, in front of
an audience, rather than here.

  python3 src/validate.py --tier small
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mktconfig import PROJECT_ROOT, load_scenario

FAMILIES = ("INTEGRITY", "RECONCILE", "ATTRIBUTION", "NARRATIVE")


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, family: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((family, name, bool(ok), detail))

    def near(self, family: str, name: str, actual: float, target: float,
             tol: float, unit: str = "") -> None:
        ok = abs(actual - target) <= abs(target) * tol
        self.check(family, name, ok,
                   f"{actual:,.2f}{unit} vs {target:,.2f}{unit} (+/-{tol:.0%})")

    def gap(self, family: str, name: str, hi: float, lo: float, min_ratio: float,
            unit: str = "") -> None:
        ok = lo > 0 and (hi / lo) >= min_ratio
        self.check(family, name, ok,
                   f"{hi:,.2f}{unit} vs {lo:,.2f}{unit} "
                   f"= {hi / lo if lo else float('nan'):.2f}x (need >={min_ratio}x)")

    def render(self) -> int:
        failed = 0
        for family in FAMILIES:
            rows = [r for r in self.rows if r[0] == family]
            if not rows:
                continue
            print(f"\n{family}")
            for _f, name, ok, detail in rows:
                failed += 0 if ok else 1
                print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
                      + (f"  -  {detail}" if detail else ""))
        total = len(self.rows)
        print(f"\n{total - failed}/{total} checks passed")
        return failed


def load(out: Path, name: str) -> pd.DataFrame:
    for ext in ("parquet", "csv"):
        f = out / f"{name}.{ext}"
        if f.exists():
            return pd.read_parquet(f) if ext == "parquet" else pd.read_csv(f)
    return pd.DataFrame()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config"
                                              / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    out = Path(args.data) if args.data else PROJECT_ROOT / "data" / args.tier
    if not out.exists():
        print(f"no data at {out}; run generate.py first")
        return 2

    names = ["dim_customer", "dim_contact", "dim_campaign", "dim_channel",
             "dim_product", "dim_segment", "dim_geography", "dim_sales_rep",
             "dim_attribution_model", "dim_ad_creative", "fact_ad_performance",
             "fact_campaign_daily", "fact_lead", "fact_lead_activity",
             "fact_opportunity", "fact_opportunity_stage",
             "fact_attribution_touch", "fact_web_session", "fact_web_event",
             "fact_email_send", "fact_email_event", "fact_marketing_budget",
             "fact_campaign_summary", "fact_funnel_snapshot",
             "fact_channel_response_curve", "fact_budget_scenario"]
    t = {n: load(out, n) for n in names}
    r = Report()
    _integrity(r, s, t)
    _reconcile(r, s, t)
    _attribution(r, s, t)
    _narrative(r, s, t)
    return 1 if r.render() else 0


def _ttm(s, df, col):
    return df[pd.to_datetime(df[col]) >= pd.Timestamp(s.timeline.ttm_start)]


def _integrity(r: Report, s, t: dict) -> None:
    lead, act, opp = t["fact_lead"], t["fact_lead_activity"], t["fact_opportunity"]
    camp = t["dim_campaign"]

    for child, col, parent, key in (
            ("fact_lead", "campaign_id", "dim_campaign", "campaign_id"),
            ("fact_lead", "contact_id", "dim_contact", "contact_id"),
            ("fact_lead", "customer_id", "dim_customer", "customer_id"),
            ("fact_opportunity", "sales_rep_id", "dim_sales_rep", "sales_rep_id"),
            ("fact_lead_activity", "campaign_id", "dim_campaign", "campaign_id"),
            ("fact_attribution_touch", "opportunity_id", "fact_opportunity",
             "opportunity_id")):
        missing = (~t[child][col].isin(t[parent][key])).sum()
        r.check("INTEGRITY", f"{child}.{col} -> {parent}", missing == 0,
                f"{missing:,} orphans")

    # Every touch sits inside the campaign that produced it. This is the check
    # that catches the failure mode nothing else does: it is invisible in every
    # aggregate and appears the first time someone opens a journey.
    j = act.merge(camp[["campaign_id", "start_date", "end_date"]],
                  on="campaign_id", how="left")
    d = pd.to_datetime(j["activity_date"])
    outside = ((d < pd.to_datetime(j["start_date"]))
               | (d > pd.to_datetime(j["end_date"]))).sum()
    r.check("INTEGRITY", "every touch inside its campaign window", outside == 0,
            f"{outside:,} of {len(act):,}")

    bad = act.groupby("lead_id")["activity_date"].apply(
        lambda x: (pd.to_datetime(pd.Series(x.values)).diff().dropna()
                   < pd.Timedelta(0)).any()).sum()
    r.check("INTEGRITY", "journeys are chronologically ordered", bad == 0,
            f"{bad:,} out-of-order journeys")

    # The funnel is a ladder: you cannot be an SQL without being an MQL.
    r.check("INTEGRITY", "SQL implies MQL",
            int(((lead["is_sql"] == 1) & (lead["is_mql"] == 0)).sum()) == 0)
    r.check("INTEGRITY", "sales-accepted implies SQL",
            int(((lead["is_sales_accepted"] == 1)
                 & (lead["is_sql"] == 0)).sum()) == 0)
    ld = pd.to_datetime(lead["lead_date"])
    md = pd.to_datetime(lead["mql_date"])
    sd = pd.to_datetime(lead["sql_date"])
    r.check("INTEGRITY", "lead -> MQL -> SQL dates are monotonic",
            int(((md < ld) | (sd < md)).sum()) == 0)

    as_of = pd.Timestamp(s.timeline.as_of_date)
    r.check("INTEGRITY", "nothing dated after as-of",
            int((ld > as_of).sum()) == 0
            and int((pd.to_datetime(opp["actual_close_date"]) > as_of).sum()) == 0,
            f"as-of {s.timeline.as_of_date}")

    # PLAN 2.5: no deal may close before the campaign that sourced it started.
    o = opp.merge(camp[["campaign_id", "start_date"]], on="campaign_id", how="left")
    early = (pd.to_datetime(o["actual_close_date"])
             < pd.to_datetime(o["start_date"])).sum()
    r.check("INTEGRITY", "no deal closes before its campaign started", early == 0,
            f"{early:,}")

    r.check("INTEGRITY", "closed opportunities have a close date",
            int((opp[opp["is_closed"] == 1]["actual_close_date"].isna()).sum()) == 0)
    r.check("INTEGRITY", "won deals carry the full amount",
            bool(np.allclose(opp.loc[opp["is_won"] == 1, "won_amount_usd"],
                             opp.loc[opp["is_won"] == 1, "amount_usd"])))
    r.check("INTEGRITY", "open pipeline is zero on closed deals",
            float(opp.loc[opp["is_closed"] == 1, "open_pipeline_usd"].sum()) == 0.0)

    ses = t["fact_web_session"]
    r.check("INTEGRITY", "identified sessions carry a contact",
            int(((ses["is_identified"] == 1) & (ses["contact_id"] == 0)).sum()) == 0)
    r.check("INTEGRITY", "anonymous sessions carry no contact",
            int(((ses["is_identified"] == 0) & (ses["contact_id"] != 0)).sum()) == 0)

    ev = t["fact_email_event"]
    snd = t["fact_email_send"]
    opened = set(ev.loc[ev["event_type"] == "Opened", "email_send_id"])
    clicked = set(ev.loc[ev["event_type"] == "Clicked", "email_send_id"])
    r.check("INTEGRITY", "every click has an open", len(clicked - opened) == 0,
            f"{len(clicked - opened):,} clicks without an open")
    bounced = set(snd.loc[snd["is_bounced"] == 1, "email_send_id"])
    r.check("INTEGRITY", "bounced emails are never opened",
            len(bounced & opened) == 0)
    unsub = t["dim_contact"]
    r.check("INTEGRITY", "unsubscribed contacts are not subscribed",
            int(((unsub["consent_status"] == "Unsubscribed")
                 & (unsub["is_email_subscribed"] == 1)).sum()) == 0)


def _reconcile(r: Report, s, t: dict) -> None:
    """PLAN 2.3 - one source of truth for spend, and pre-aggregates that
    reproduce their facts."""
    ad, daily, camp = t["fact_ad_performance"], t["fact_campaign_daily"], t["dim_campaign"]
    summary = t["fact_campaign_summary"]

    paid = set(ad["campaign_id"].unique())
    a = ad.groupby("campaign_id")["spend_usd"].sum()
    d = daily[daily["campaign_id"].isin(paid)].groupby("campaign_id")["spend_usd"].sum()
    diff = (a - d.reindex(a.index).fillna(0)).abs().max()
    r.check("RECONCILE", "ad grain -> campaign_daily spend, to the cent",
            diff < 0.011, f"max campaign diff ${diff:,.4f}")

    tot_daily = daily["spend_usd"].sum()
    tot_sum = summary["spend_usd"].sum()
    r.near("RECONCILE", "campaign_daily -> campaign_summary spend",
           tot_daily, tot_sum, 0.001, "")

    ttm = _ttm(s, daily, "activity_date")["spend_usd"].sum()
    r.near("RECONCILE", "TTM spend equals the configured total",
           ttm, float(s.spend["ttm_total_usd"]), 0.005, "")

    # Channel and region spend margins were fitted simultaneously (IPF), so both
    # are exact rather than "close".
    cs = _ttm(s, daily, "activity_date").merge(
        camp[["campaign_id", "channel_name"]], on="campaign_id", how="left")
    by_ch = cs.groupby("channel_name")["spend_usd"].sum()
    worst, worst_ch = 0.0, ""
    for name, cfg in s.channels.items():
        tgt = cfg["spend_share"] * float(s.spend["ttm_total_usd"])
        err = abs(by_ch.get(name, 0.0) - tgt) / tgt
        if err > worst:
            worst, worst_ch = err, name
    r.check("RECONCILE", "TTM channel spend shares match the media plan",
            worst < 0.02, f"worst {worst_ch} off by {worst:.2%}")

    lead = t["fact_lead"]
    r.near("RECONCILE", "campaign_summary leads = fact_lead",
           float(summary["leads"].sum()), float(len(lead)), 0.0001)
    r.near("RECONCILE", "campaign_daily leads = fact_lead",
           float(daily["leads"].sum()), float(len(lead)), 0.0001)

    snap = t["fact_funnel_snapshot"]
    r.near("RECONCILE", "funnel_snapshot leads = fact_lead",
           float(snap["leads"].sum()), float(len(lead)), 0.0001)
    r.near("RECONCILE", "funnel_snapshot MQLs = fact_lead",
           float(snap["mqls"].sum()), float(lead["is_mql"].sum()), 0.0001)
    opp = t["fact_opportunity"]
    r.near("RECONCILE", "funnel_snapshot revenue = closed-won",
           float(snap["revenue_usd"].sum()),
           float(opp["won_amount_usd"].sum()), 0.0005)

    ses, wev = t["fact_web_session"], t["fact_web_event"]
    r.near("RECONCILE", "session page_views = web_event rows",
           float(ses["page_views"].sum()), float(len(wev)), 0.0001)

    bud = t["fact_marketing_budget"]
    r.near("RECONCILE", "budget actuals = campaign_daily spend",
           float(bud["actual_spend_usd"].sum()), float(tot_daily), 0.001)

    # PLAN 2.7 - the reallocation is zero-sum. The note's table quietly added
    # $1M and called it a reallocation.
    ch = t["dim_channel"]
    r.near("RECONCILE", "recommended budget is zero-sum vs plan",
           float(ch["recommended_spend_usd"].sum()),
           float(s.spend["ttm_total_usd"]), 0.0001)


def _attribution(r: Report, s, t: dict) -> None:
    """PLAN 2.4 - the invariant the whole attribution scene rests on."""
    at, opp = t["fact_attribution_touch"], t["fact_opportunity"]
    models = t["dim_attribution_model"]

    w = at.groupby(["opportunity_id", "attribution_model_id"])[
        "attribution_weight"].sum()
    bad = int((~np.isclose(w, 1.0, atol=1e-9)).sum())
    r.check("ATTRIBUTION", "weights sum to 1.0 per (opportunity, model)",
            bad == 0, f"{bad:,} of {len(w):,} journeys")

    rev = at.groupby("model_code")["attributed_revenue_usd"].sum()
    pipe = at.groupby("model_code")["attributed_pipeline_usd"].sum()
    # The invariant is exact in the weights (checked above). The money columns
    # are rounded to cents per row, and the five models split a journey
    # differently, so their rounding residuals differ by a few dollars on a
    # ninety-million-dollar total. Compare relatively.
    r.check("ATTRIBUTION", "total attributed revenue identical across models",
            float(rev.max() - rev.min()) / max(float(rev.max()), 1) < 1e-6,
            f"spread ${rev.max() - rev.min():,.2f} on ${rev.max():,.0f} "
            f"over {len(rev)} models")
    r.check("ATTRIBUTION", "total attributed pipeline identical across models",
            float(pipe.max() - pipe.min()) / max(float(pipe.max()), 1) < 1e-6,
            f"spread ${pipe.max() - pipe.min():,.2f} on ${pipe.max():,.0f}")

    # Attribution only covers opportunities that HAVE a touch history, so it is
    # compared against those, not against every opportunity.
    covered = opp[opp["opportunity_id"].isin(at["opportunity_id"])]
    r.near("ATTRIBUTION", "attributed revenue = closed-won on covered deals",
           float(rev.iloc[0]), float(covered["won_amount_usd"].sum()), 0.0001)
    r.near("ATTRIBUTION", "attributed pipeline = opportunity amount",
           float(pipe.iloc[0]), float(covered["amount_usd"].sum()), 0.0001)
    r.check("ATTRIBUTION", "coverage of opportunities is near total",
            len(covered) / len(opp) > 0.97,
            f"{len(covered) / len(opp):.2%} of opportunities have a journey")
    r.check("ATTRIBUTION", "all five models present",
            at["model_code"].nunique() == len(models),
            f"{at['model_code'].nunique()} of {len(models)}")
    r.check("ATTRIBUTION", "U-Shaped and Position Based are not both shipped",
            "POSITION_BASED" not in set(models["model_code"]))


def _narrative(r: Report, s, t: dict) -> None:
    """PLAN 1 - the blend equals the mix - and every event visible."""
    f = s.funnel
    lead, opp, camp = t["fact_lead"], t["fact_opportunity"], t["dim_campaign"]
    summary = t["fact_campaign_summary"]
    tl = lead[pd.to_datetime(lead["lead_date"]) >= pd.Timestamp(s.timeline.ttm_start)]

    r.near("NARRATIVE", "TTM lead->MQL matches the channel mix",
           tl["is_mql"].mean(), f.lead_to_mql, 0.06)
    r.near("NARRATIVE", "TTM MQL->SQL matches the channel mix",
           tl["is_sql"].sum() / tl["is_mql"].sum(), f.mql_to_sql, 0.08)
    r.near("NARRATIVE", "TTM SQL->accepted matches the channel mix",
           tl["is_sales_accepted"].sum() / tl["is_sql"].sum(), f.sql_to_opp, 0.08)
    r.near("NARRATIVE", "TTM leads within tolerance of derived plan",
           float(len(tl)), f.leads, 0.10)

    o = opp.copy()
    o["cd"] = pd.to_datetime(o["actual_close_date"])
    won = o[(o["is_won"] == 1) & (o["cd"] >= pd.Timestamp(s.timeline.ttm_start))]
    r.near("NARRATIVE", "average won deal matches the derived segment mix",
           float(won["won_amount_usd"].mean()), f.avg_won_usd, 0.12)

    # --- E1 the money pit ----------------------------------------------------
    ev = s.event("wasteful_flagship")
    if ev:
        f1 = summary[summary["campaign_name"] == ev["campaign_name"]]
        peers = summary[(summary["channel_name"] == ev["channel"])
                        & (summary["campaign_name"] != ev["campaign_name"])
                        & (summary["leads"] > 50)]
        r.check("NARRATIVE", "E1 flagship spend is as configured",
                abs(float(f1["spend_usd"].iloc[0]) - float(ev["spend_usd"])) < 1_000,
                f"${float(f1['spend_usd'].iloc[0]):,.0f}")
        r.gap("NARRATIVE", "E1 flagship cost per SQL far above its channel",
              float(f1["cost_per_sql_usd"].iloc[0]),
              float(peers["cost_per_sql_usd"].median()), 1.8, "")

    # --- E2 the hidden gem ---------------------------------------------------
    ev = s.event("hidden_gem")
    if ev:
        g = summary[summary["campaign_name"] == ev["campaign_name"]]
        blended = summary["revenue_usd"].sum() / summary["spend_usd"].sum()
        r.gap("NARRATIVE", "E2 hidden gem ROAS far above company blended",
              float(g["roas"].iloc[0]), blended, 3.0, "x")

    # --- E3 attribution divergence ------------------------------------------
    # Scoped to the two years the demo actually shows. Over all history the
    # warm-up year dominates the mix - LinkedIn spend has grown 48% a year, so
    # four years ago it was a third of its current size - and the comparison
    # stops describing the dataset anyone will look at.
    at = t["fact_attribution_touch"]
    at = at[pd.to_datetime(at["touch_date"])
            >= pd.Timestamp(s.timeline.prior_ttm_start)]
    piv = at.pivot_table(index="channel_name", columns="model_code",
                         values="attributed_revenue_usd", aggfunc="sum")
    piv = 100 * piv / piv.sum()
    # Not "the number one flips": the largest channel is largest under every
    # model, which is realistic and stays true across reseeds. What matters -
    # and what the demo shows - is that the RANKING moves and the shares swing
    # by a lot. Asserting the crown flip made this check hinge on a fraction of
    # a point between three big channels.
    move = (piv["FIRST_TOUCH"].rank(ascending=False)
            - piv["LAST_TOUCH"].rank(ascending=False)).abs().max()
    r.check("NARRATIVE", "E3 channel ranking moves between first and last touch",
            move >= 2, f"largest rank move {move:.0f} places")
    swing = (piv["LAST_TOUCH"] - piv["FIRST_TOUCH"])
    r.check("NARRATIVE", "E3 share swing between models is large",
            swing.abs().max() >= 5.0,
            f"{swing.idxmax()} {piv.loc[swing.idxmax(), 'FIRST_TOUCH']:.1f}%"
            f" -> {piv.loc[swing.idxmax(), 'LAST_TOUCH']:.1f}% | "
            f"{swing.idxmin()} {piv.loc[swing.idxmin(), 'FIRST_TOUCH']:.1f}%"
            f" -> {piv.loc[swing.idxmin(), 'LAST_TOUCH']:.1f}%")
    ev = s.event("attribution_divergence")
    if ev:
        op = [c for c in ev["opener_channels"] if c in piv.index]
        cl = [c for c in ev["closer_channels"] if c in piv.index]
        r.gap("NARRATIVE", "E3 openers over-credited by first-touch",
              float(piv.loc[op, "FIRST_TOUCH"].sum()),
              float(piv.loc[op, "LAST_TOUCH"].sum()), 1.6, "%")
        r.gap("NARRATIVE", "E3 closers over-credited by last-touch",
              float(piv.loc[cl, "LAST_TOUCH"].sum()),
              float(piv.loc[cl, "FIRST_TOUCH"].sum()), 1.6, "%")

    # --- E4 channel quality gap ---------------------------------------------
    ev = s.event("channel_quality_gap")
    if ev:
        m = tl[tl["is_mql"] == 1].groupby("source_channel").agg(
            mql=("is_mql", "sum"), sql=("is_sql", "sum"))
        m = m[m["mql"] > 100]
        rate = (m["sql"] / m["mql"] * 100)
        r.check("NARRATIVE", "E4 MQL->SQL spread across channels is wide",
                (rate.max() - rate.min()) >= float(ev["min_spread_pp"]),
                f"{rate.idxmax()} {rate.max():.0f}% vs "
                f"{rate.idxmin()} {rate.min():.0f}% "
                f"= {rate.max() - rate.min():.0f}pp")

    # --- E5 lead quality decay ----------------------------------------------
    if s.event("lead_quality_decay"):
        x = tl[tl["is_mql"] == 1].copy()
        x["q"] = pd.to_datetime(x["lead_date"]).dt.to_period("Q")
        by_q = x.groupby("q").apply(
            lambda d: d["is_sql"].sum() / len(d), include_groups=False)
        # The last partial quarter is right-censored by as-of (PLAN 2.5), so it
        # is excluded rather than being read as a collapse.
        by_q = by_q.iloc[:-1]
        r.check("NARRATIVE", "E5 MQL->SQL declines across the TTM quarters",
                by_q.iloc[0] > by_q.iloc[-1],
                f"{by_q.iloc[0]:.1%} -> {by_q.iloc[-1]:.1%} over "
                f"{len(by_q)} quarters")

    # --- E6 APAC underwater --------------------------------------------------
    ev = s.event("apac_underwater")
    if ev:
        roas = _region_roas(s, t)
        r.check("NARRATIVE", f"E6 {ev['region']} ROAS below break-even",
                roas.get(ev["region"], 9) < float(ev["target_roas_max"]),
                "  ".join(f"{k} {v:.2f}x" for k, v in roas.items()))
        r.check("NARRATIVE", "E6 region ROAS ordering NA > EMEA > APAC",
                roas.get("North America", 0) > roas.get("EMEA", 0)
                > roas.get("APAC", 9))

    # --- E7 product launch ---------------------------------------------------
    ev = s.event("product_launch")
    if ev:
        prod = t["dim_product"]
        pid = prod.loc[prod["product_line"] == ev["product_line"], "product_id"]
        if len(pid):
            L = lead.copy()
            L["m"] = pd.to_datetime(L["lead_date"]).dt.to_period("M")
            launch = pd.Period(s.timeline.offset_month(
                int(ev["launch_month_offset"])), "M")
            hit = L[L["product_id"] == int(pid.iloc[0])]
            before = len(hit[hit["m"] < launch - 1]) / max(
                (launch - 1 - hit["m"].min()).n, 1)
            after = len(hit[hit["m"] >= launch]) / max(
                (hit["m"].max() - launch).n + 1, 1)
            r.gap("NARRATIVE", "E7 launch lifts lead volume for its product",
                  after, max(before, 1e-9), 2.0, " leads/mo")

    # --- E8/E9 the reallocation story ---------------------------------------
    ev = s.event("channel_reallocation")
    if ev:
        g = _channel_spend_growth(s, t)
        over = ev["over_invested"]["channel"]
        under = ev["under_invested"]["channel"]
        r.check("NARRATIVE",
                f"E8/E9 {over} spend grows much faster than {under}",
                g.get(over, 0) > g.get(under, 0) + 0.20,
                f"{over} {g.get(over, 0):+.0%} vs {under} {g.get(under, 0):+.0%}")
        cur = t["fact_channel_response_curve"].set_index("channel_name")
        r.check("NARRATIVE", f"E8/E9 {under} marginal ROI beats {over}",
                float(cur.loc[under, "marginal_pipeline_per_usd"])
                > float(cur.loc[over, "marginal_pipeline_per_usd"]),
                f"{under} {cur.loc[under, 'marginal_pipeline_per_usd']:.2f} vs "
                f"{over} {cur.loc[over, 'marginal_pipeline_per_usd']:.2f} "
                "pipeline per $")

    # --- E11 consent gap -----------------------------------------------------
    ev = s.event("consent_gap")
    if ev:
        con = t["dim_contact"]
        sub = con.groupby("region_name")["is_email_subscribed"].mean()
        others = sub.drop(ev["region"], errors="ignore").mean()
        r.check("NARRATIVE", f"E11 {ev['region']} email reach is consent-gated",
                sub.get(ev["region"], 1) < others - 0.15,
                f"{ev['region']} {sub.get(ev['region'], 0):.0%} vs "
                f"{others:.0%} elsewhere")

    # --- E12 hero journeys ---------------------------------------------------
    ev = s.event("hero_journeys")
    if ev and "is_hero_journey" in opp.columns:
        hero = opp[opp["is_hero_journey"] == 1]
        r.check("NARRATIVE", "E12 hero journeys exist and are won",
                len(hero) >= 3 and int(hero["is_won"].sum()) == len(hero),
                f"{len(hero)} hero deals, "
                f"${hero['won_amount_usd'].max():,.0f} largest")
        touches = at[at["opportunity_id"].isin(hero["opportunity_id"])]
        per = touches.groupby(["opportunity_id", "model_code"]).size()
        r.check("NARRATIVE", "E12 hero journeys are long enough to show",
                float(per.min()) >= 5,
                f"min {per.min():.0f} touches, median {per.median():.0f}")

    # --- E13 saturation ------------------------------------------------------
    if s.event("saturation"):
        cur = t["fact_channel_response_curve"]
        r.check("NARRATIVE", "E13 some channels are past inflection, some below",
                int(cur["is_past_inflection"].sum()) >= 3
                and int((cur["is_past_inflection"] == 0).sum()) >= 3,
                f"{int(cur['is_past_inflection'].sum())} of {len(cur)} saturated")
        r.check("NARRATIVE", "E13 marginal return is always below average",
                bool((cur["marginal_pipeline_per_usd"]
                      < cur["average_pipeline_per_usd"]).all()),
                "diminishing returns hold for every channel")

    # --- E14 CPL anomaly -----------------------------------------------------
    ev = s.event("cpl_anomaly")
    if ev:
        c = camp[camp["campaign_name"] == ev["campaign_name"]]
        if len(c):
            cid = int(c["campaign_id"].iloc[0])
            d = t["fact_campaign_daily"]
            d = d[d["campaign_id"] == cid].copy()
            d["m"] = pd.to_datetime(d["activity_date"]).dt.to_period("M")
            g = d.groupby("m").agg(spend=("spend_usd", "sum"),
                                   leads=("leads", "sum"))
            g = g[g["leads"] > 0]
            cpl = g["spend"] / g["leads"]
            r.gap("NARRATIVE", "E14 CPL anomaly is a visible spike",
                  float(cpl.max()), float(cpl.median()), 1.6, "")

    # --- E15 web conversion drop --------------------------------------------
    ev = s.event("web_conversion_drop")
    if ev:
        w = t["fact_web_event"]
        w = w[w["page_path"].isin(ev["pages"])].copy()
        w["m"] = pd.to_datetime(w["event_date"]).dt.to_period("M")
        rate = w.groupby("m")["is_conversion_event"].mean()
        m0 = pd.Period(s.timeline.offset_month(int(ev["month_offset"])), "M")
        m1 = m0 + int(ev["duration_months"])
        during = rate[(rate.index >= m0) & (rate.index < m1)].mean()
        outside = rate[(rate.index < m0) | (rate.index >= m1)].mean()
        r.check("NARRATIVE", "E15 website conversion drop is visible",
                during < outside * 0.80,
                f"{during:.2%} during vs {outside:.2%} outside")

    # --- E16 sales execution gap --------------------------------------------
    ev = s.event("sales_execution_gap")
    if ev:
        o2 = opp[opp["is_closed"] == 1].copy()
        o2["m"] = pd.to_datetime(o2["actual_close_date"])
        start = pd.Timestamp(s.timeline.offset_month(
            int(ev["start_month_offset"])))
        # Twelve months either side of the ramp, not "everything before". With
        # a warm-up year in the data, "before" otherwise reaches back into the
        # left-censored quarters and compares two different eras.
        base_start = pd.Timestamp(s.timeline.offset_month(
            int(ev["start_month_offset"]) - 12))
        in_region = o2["region_name"] == ev["region"]
        hit = o2[in_region & (o2["m"] >= start)]
        base = o2[in_region & (o2["m"] >= base_start) & (o2["m"] < start)]
        r.check("NARRATIVE", f"E16 {ev['region']} win rate falls after the gap",
                float(hit["is_won"].mean()) < float(base["is_won"].mean()) - 0.03,
                f"{base['is_won'].mean():.1%} before -> "
                f"{hit['is_won'].mean():.1%} after")


def _region_roas(s, t: dict) -> dict:
    opp = t["fact_opportunity"].copy()
    opp["cd"] = pd.to_datetime(opp["actual_close_date"])
    ttm = pd.Timestamp(s.timeline.ttm_start)
    rev = opp[(opp["is_won"] == 1) & (opp["cd"] >= ttm)].groupby(
        "region_name")["won_amount_usd"].sum()
    bud = t["fact_marketing_budget"].copy()
    bud["m"] = pd.to_datetime(bud["month_start"])
    spend = bud[bud["m"] >= ttm].groupby("region_name")["actual_spend_usd"].sum()
    return {k: float(rev.get(k, 0) / v) for k, v in spend.items() if v > 0}


def _channel_spend_growth(s, t: dict) -> dict:
    bud = t["fact_marketing_budget"].copy()
    bud["m"] = pd.to_datetime(bud["month_start"])
    ttm = bud[bud["m"] >= pd.Timestamp(s.timeline.ttm_start)]
    prior = bud[(bud["m"] >= pd.Timestamp(s.timeline.prior_ttm_start))
                & (bud["m"] < pd.Timestamp(s.timeline.ttm_start))]
    a = ttm.groupby("channel_name")["actual_spend_usd"].sum()
    b = prior.groupby("channel_name")["actual_spend_usd"].sum()
    return {k: float(a[k] / b[k] - 1) for k in a.index if b.get(k, 0) > 0}


if __name__ == "__main__":
    raise SystemExit(main())
