#!/usr/bin/env python3
"""Novareach Software - Marketing Performance & Attribution : dataset generator.

  python3 src/generate.py --tier small
  python3 src/generate.py --tier full --scenario config/my_scenario.yaml

The stages run in dependency order because the demo's causal chain runs in that
order too: budget buys media, media produces impressions, impressions produce
clicks, clicks at a cost-per-lead produce leads, leads convert at rates that
decay over time, opportunities open a sales cycle later and close a sales cycle
after that, and only then can attribution be replayed over the touch history and
response curves fitted to what actually happened.

Nothing downstream may assert a number the stage above it cannot account for.
That single rule is why the headline on the README is defensible.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accounts as accounts_mod
import advertising as advertising_mod
import attribution as attribution_mod
import campaigns as campaigns_mod
import derived as derived_mod
import dims as dims_mod
import emails as email_mod
import journeys as journeys_mod
import leads as leads_mod
import opportunities as opportunities_mod
import response as response_mod
import web as web_mod
from dim_date import build_dim_date
from events import EventPlan
from mktconfig import PROJECT_ROOT, load_scenario


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config"
                                              / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--out", default=None, help="output directory (default data/<tier>)")
    ap.add_argument("--formats", default=None, help="comma list: parquet,csv")
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    t0 = time.time()

    # One independent random stream per subsystem, all derived from the single
    # configured seed. Sharing one generator means changing a webinar knob
    # reshuffles every draw downstream of it, so tuning one number moves five
    # unrelated numbers and the dataset never converges.
    def stream(tag: int) -> np.random.Generator:
        return np.random.default_rng([s.seed, tag])

    print(f"{s.company} marketing generator | "
          f"scenario={s.cfg['meta']['scenario_name']} tier={args.tier}")
    print(f"  history {s.timeline.start_date} -> as-of {s.timeline.as_of_date} "
          f"({len(s.timeline.month_starts())} months)")
    print(s.funnel.render())

    t: dict[str, pd.DataFrame] = {}

    print("  building reference data...")
    t["dim_date"] = build_dim_date(s.timeline.start_date, s.timeline.end_date,
                                   int(s.calendar["fiscal_year_start_month"]))
    geo = dims_mod.build_dim_geography(s)
    industries = dims_mod.build_dim_industry(s)
    segments = dims_mod.build_dim_segment(s)
    products = dims_mod.build_dim_product(s)
    channels = dims_mod.build_dim_channel(s)
    sources = dims_mod.build_dim_lead_source(s)
    assets = dims_mod.build_dim_content_asset(s, stream(1))
    activity_types = dims_mod.build_dim_activity_type(s)
    models = dims_mod.build_dim_attribution_model(s)
    stage_dim = dims_mod.build_dim_opportunity_stage(s)
    lost_reasons = dims_mod.build_dim_lost_reason(s)

    print("  building accounts and sales coverage...")
    acct = accounts_mod.build_dim_customer(s, geo, industries, segments, stream(2))
    reps = accounts_mod.build_dim_sales_rep(s, stream(3))

    # Events resolve to concrete targets once, before anything is drawn, so
    # every stage downstream agrees which campaigns, regions and accounts the
    # stories land on.
    ep = EventPlan(s, acct, reps, stream(4))
    print(f"    accounts={len(acct):,} reps={len(reps):,} | {ep.summary()}")

    print("  allocating spend and cutting campaigns...")
    plan = campaigns_mod.build_spend_plan(s, ep)
    camp, cm = campaigns_mod.build_campaigns(s, plan, products, segments,
                                             industries, channels, ep, stream(5))
    creatives = campaigns_mod.build_dim_ad_creative(s, camp, stream(6))
    budget = campaigns_mod.build_fact_marketing_budget(s, cm, camp, channels,
                                                       stream(7))
    ttm_spend = cm.loc[pd.to_datetime(cm["month_start"])
                       >= pd.Timestamp(s.timeline.ttm_start), "spend_usd"].sum()
    print(f"    campaigns={len(camp):,} creatives={len(creatives):,} "
          f"TTM spend=${ttm_spend / 1e6:,.2f}M")

    print("  buying media...")
    ad = advertising_mod.build_fact_ad_performance(s, camp, creatives, cm, ep,
                                                   stream(8))
    print(f"    ad rows={len(ad):,} impressions={ad['impressions'].sum() / 1e6:,.1f}M "
          f"clicks={ad['clicks'].sum():,}")

    print("  generating leads from spend...")
    counts = leads_mod.plan_lead_counts(s, camp, cm, ep, stream(9))
    demand = leads_mod.contact_demand(s, counts)
    contacts = accounts_mod.build_dim_contact(s, acct, sum(demand.values()),
                                              segments, stream(10))
    lead = leads_mod.build_leads(s, counts, camp, contacts, acct, sources, ep,
                                 stream(11))
    ttm = pd.to_datetime(lead["lead_date"]) >= pd.Timestamp(s.timeline.ttm_start)
    print(f"    contacts={len(contacts):,} leads={len(lead):,} "
          f"(TTM {int(ttm.sum()):,}, MQL {int(lead.loc[ttm, 'is_mql'].sum()):,}, "
          f"SQL {int(lead.loc[ttm, 'is_sql'].sum()):,})")

    print("  assembling journeys...")
    act = journeys_mod.build_lead_activity(s, lead, camp, cm, assets,
                                           activity_types, ep, stream(12))
    print(f"    touches={len(act):,} ({len(act) / len(lead):.1f} per lead)")

    print("  web and email behaviour...")
    sessions, web_events = web_mod.build_web(s, lead, act, contacts, assets,
                                             activity_types, ep, stream(13))
    sends, email_events = email_mod.build_email(s, contacts, camp, cm, lead, ep,
                                                stream(14))
    print(f"    sessions={len(sessions):,} web_events={len(web_events):,} "
          f"sends={len(sends):,} email_events={len(email_events):,}")

    print("  opening and closing opportunities...")
    opp, opp_stage, lead = opportunities_mod.build_opportunities(
        s, lead, camp, acct, reps, products, lost_reasons, ep, stream(15))
    won = opp[(opp["is_won"] == 1)
              & (pd.to_datetime(opp["actual_close_date"])
                 >= pd.Timestamp(s.timeline.ttm_start))]
    print(f"    opportunities={len(opp):,} stage_rows={len(opp_stage):,} "
          f"TTM won={len(won):,} revenue=${won['won_amount_usd'].sum() / 1e6:,.2f}M")

    # dim_customer.is_hero_account is stamped after the heroes are settled, so
    # the journey page can pin them to the top of its account selector.
    acct["is_hero_account"] = acct["customer_id"].isin(
        ep.hero_customer_ids).astype(np.int8)

    print("  replaying attribution...")
    attrib = attribution_mod.build_attribution(s, opp, act, lead, models,
                                               camp, channels)
    print(f"    attribution rows={len(attrib):,} across {len(models)} models")

    print("  fitting response curves...")
    curves, scenarios = response_mod.build_response_curves(s, opp, cm, camp,
                                                           channels)
    print(f"    curves={len(curves):,} scenario grid={len(scenarios):,}")

    # dim_channel carries the recommendation for convenience, but the solve
    # lives in the response curves. Back-fill rather than compute it twice.
    rec = curves.set_index("channel_name")
    channels["recommended_spend_usd"] = channels["channel_name"].map(
        rec["recommended_spend_usd"]).fillna(0.0).round(2)
    channels["recommended_delta_usd"] = (channels["recommended_spend_usd"]
                                         - channels["planned_spend_usd"]).round(2)

    print("  deriving rollups, cohorts and scores...")
    lead = derived_mod.build_lead_score(lead, act, web_events)
    daily = derived_mod.build_campaign_daily(s, ad, cm, camp, lead, stream(16))
    summary = derived_mod.build_campaign_summary(s, camp, cm, lead, opp, products)
    snapshot = derived_mod.build_funnel_snapshot(s, lead, opp, channels)
    print(f"    campaign_daily={len(daily):,} campaign_summary={len(summary):,} "
          f"funnel_snapshot={len(snapshot):,}")

    t.update({
        "dim_geography": geo, "dim_industry": industries,
        "dim_segment": segments, "dim_product": products,
        "dim_channel": channels, "dim_lead_source": sources,
        "dim_content_asset": assets, "dim_activity_type": activity_types,
        "dim_attribution_model": models, "dim_opportunity_stage": stage_dim,
        "dim_lost_reason": lost_reasons, "dim_customer": acct,
        "dim_contact": contacts, "dim_sales_rep": reps,
        "dim_campaign": camp, "dim_ad_creative": creatives,
        "fact_marketing_budget": budget,
        "fact_ad_performance": ad, "fact_campaign_daily": daily,
        "fact_web_session": sessions, "fact_web_event": web_events,
        "fact_email_send": sends, "fact_email_event": email_events,
        "fact_lead": lead, "fact_lead_activity": act,
        "fact_opportunity": opp, "fact_opportunity_stage": opp_stage,
        "fact_attribution_touch": attrib,
        "fact_channel_response_curve": curves,
        "fact_budget_scenario": scenarios,
        "fact_campaign_summary": summary,
        "fact_funnel_snapshot": snapshot,
    })

    drop_internal(t)
    normalize_types(t)

    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "data" / args.tier
    formats = (args.formats.split(",") if args.formats else s.output["formats"])
    write_tables(t, out_dir, formats, s, args.tier)
    print(f"  done in {time.time() - t0:,.1f}s -> {out_dir}")
    return 0


def drop_internal(tables: dict[str, pd.DataFrame]) -> None:
    """Remove the generator's own dials.

    Columns like `_quality` and `_ctr_mult` are how the events are steered.
    Publishing them hands the audience the answer key, and an AI asked to find
    the under-performing channel would read the column rather than work it out.
    """
    for name, df in tables.items():
        if df is None or df.empty:
            continue
        drop = [c for c in df.columns if c.startswith("_")]
        if drop:
            tables[name] = df.drop(columns=drop)


DATE_SUFFIX = ("_date", "date", "_month_end", "month_start")


def normalize_types(tables: dict[str, pd.DataFrame]) -> None:
    """Give every written column a deliberate type.

    Without this the output inherits whatever pandas inferred during
    concatenation - int64 surrogate keys, timestamps for plain dates - and the
    generated DDL inherits the same sloppiness.
    """
    id32 = {
        "geo_key", "industry_id", "segment_id", "product_id", "channel_id",
        "lead_source_id", "content_asset_id", "activity_type_id",
        "attribution_model_id", "stage_id", "stage_order", "lost_reason_id",
        "customer_id", "contact_id", "sales_rep_id", "campaign_id",
        "ad_creative_id", "marketing_budget_id", "ad_performance_id",
        "campaign_daily_id", "web_session_id", "web_event_id", "email_send_id",
        "email_event_id", "lead_id", "lead_activity_id", "opportunity_id",
        "opportunity_stage_id", "attribution_id", "budget_scenario_id",
        "funnel_snapshot_id", "date_key", "year_month_key",
        "converted_opportunity_id", "lead_score",
    }
    for name, df in tables.items():
        if df is None or df.empty:
            continue
        for col in df.columns:
            ser = df[col]
            if col in id32 and pd.api.types.is_numeric_dtype(ser):
                df[col] = ser.fillna(0).astype("int32")
            elif col.startswith("is_") and pd.api.types.is_bool_dtype(ser):
                df[col] = ser.astype("int8")
            elif (col.startswith("is_") and pd.api.types.is_integer_dtype(ser)):
                # Flags built as plain Python ints arrive as int64 and the
                # emitted DDL inherits BIGINT for a column holding 0 and 1.
                df[col] = ser.astype("int8")
            elif col.endswith("_points") and pd.api.types.is_integer_dtype(ser):
                df[col] = ser.astype("int16")
            elif any(col.endswith(sfx) for sfx in DATE_SUFFIX):
                if pd.api.types.is_datetime64_any_dtype(ser):
                    # Dates, not timestamps: no BI tool benefits from a 00:00:00.
                    df[col] = ser.dt.date
                elif ser.dtype == object:
                    # Stages hand dates over in whichever form they held them -
                    # Timestamp from one table, datetime.date from another - and
                    # a column carrying both is an object column that parquet
                    # refuses to write. Coerce once, here, for every table.
                    try:
                        df[col] = pd.to_datetime(ser, errors="coerce").dt.date
                    except (TypeError, ValueError):
                        pass
            elif pd.api.types.is_float_dtype(ser) and col.endswith("_usd"):
                df[col] = ser.round(2)
        tables[name] = df


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path,
                 formats: list[str], s, tier: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_ok = "csv" in formats and tier == s.output.get("csv_max_tier", "small")
    total = written = 0
    for name, df in sorted(tables.items()):
        if df is None or df.empty:
            print(f"    WARNING: {name} is empty, not written")
            continue
        if "parquet" in formats:
            df.to_parquet(out_dir / f"{name}.parquet", index=False,
                          compression="snappy")
        if csv_ok:
            df.to_csv(out_dir / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        total += len(df)
        written += 1
    print(f"  wrote {written} tables, {total:,} rows "
          f"({'parquet' if 'parquet' in formats else ''}{'+csv' if csv_ok else ''})")


if __name__ == "__main__":
    raise SystemExit(main())
