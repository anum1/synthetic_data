"""fact_attribution_touch - five models, stored long, replayed over real touches.

PLAN 2.4. The invariant, which the design note never stated and without which
the whole attribution scene collapses:

    for every (opportunity, model):
        sum(attribution_weight)     = 1.0
        sum(attributed_pipeline_usd) = opportunity.amount_usd
        sum(attributed_revenue_usd)  = opportunity.won_amount_usd

Total revenue is therefore IDENTICAL under all five models. Only its
distribution across channels moves. That is what makes the attribution slicer
worth showing: the grand total is visibly pinned while every channel bar
re-ranks, so the audience can see that the disagreement is about credit, not
about arithmetic.

Journeys are gathered at ACCOUNT level, not lead level, because B2B buying is a
committee: the champion downloads the reference architecture, the CFO reads the
ROI piece, and neither of them alone is a journey worth showing. This is what
`dim_contact` was separated from `dim_customer` for (PLAN 2.8).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mktconfig import Scenario

LOOKBACK_DAYS = 365
MAX_TOUCHES = 12


def build_attribution(s: Scenario, opp: pd.DataFrame, act: pd.DataFrame,
                      lead: pd.DataFrame, models: pd.DataFrame,
                      camp: pd.DataFrame, channels: pd.DataFrame) -> pd.DataFrame:
    """One row per (opportunity, touch, model)."""
    j = _gather_journeys(opp, act, lead)
    if j.empty:
        return pd.DataFrame()
    j["channel_id"] = j["channel_name"].map(
        channels.set_index("channel_name")["channel_id"]).fillna(0).astype(int)

    n_touch = j.groupby("opportunity_id")["touch_rank"].transform("max")
    j["touches_in_journey"] = n_touch.astype(np.int16)
    pos = j["touch_rank"].to_numpy() - 1
    k = n_touch.to_numpy()
    is_first = pos == 0
    is_last = pos == k - 1
    is_sql = j["is_sql_touch"].to_numpy() == 1
    # Dense group ids, computed once and shared by all five models. Journeys
    # are contiguous, so this is a factorize rather than a groupby.
    gid = pd.factorize(j["opportunity_id"].to_numpy())[0]

    frames = []
    for _, m in models.iterrows():
        w = _weights(m["model_rule"], gid, pos, k, is_first, is_last, is_sql, m)
        f = j[["opportunity_id", "customer_id", "lead_id", "contact_id",
               "campaign_id", "channel_id", "channel_name", "activity_type",
               "activity_date", "touch_rank", "touches_in_journey",
               "region_name", "segment_id", "amount_usd", "won_amount_usd",
               "is_won"]].copy()
        f["attribution_model_id"] = np.int32(m["attribution_model_id"])
        f["model_code"] = m["model_code"]
        f["attribution_weight"] = w
        f["attributed_pipeline_usd"] = (f["amount_usd"] * w).round(2)
        f["attributed_revenue_usd"] = (f["won_amount_usd"] * w).round(2)
        frames.append(f)

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"activity_type": "touch_type",
                              "activity_date": "touch_date",
                              "touch_rank": "touch_sequence"})
    out = out.drop(columns=["amount_usd", "won_amount_usd"])
    out.insert(0, "attribution_id", np.arange(1, len(out) + 1))
    return out


def _gather_journeys(opp: pd.DataFrame, act: pd.DataFrame,
                     lead: pd.DataFrame) -> pd.DataFrame:
    """Every touch at the account in the year before the opportunity opened.

    Capped at the most recent MAX_TOUCHES so one very active account cannot
    dominate the table, and so the journey page has something a human can read.
    """
    o = opp[["opportunity_id", "customer_id", "lead_id", "opportunity_date",
             "amount_usd", "won_amount_usd", "is_won", "region_name",
             "segment_id"]].copy()
    o["opp_dt"] = pd.to_datetime(o["opportunity_date"])
    o["window_start"] = o["opp_dt"] - pd.Timedelta(days=LOOKBACK_DAYS)

    a = act[["lead_id", "contact_id", "customer_id", "activity_date",
             "campaign_id", "channel_name", "activity_type"]].copy()
    a["act_dt"] = pd.to_datetime(a["activity_date"])

    j = o.merge(a, on="customer_id", how="inner", suffixes=("", "_a"))
    j = j[(j["act_dt"] <= j["opp_dt"]) & (j["act_dt"] >= j["window_start"])]
    if j.empty:
        return j

    # The SQL-creation touch, for W-shaped: the last touch on or before the
    # date the lead became an SQL. Real W-shaped attribution rewards whatever
    # was in front of the buyer at the moment sales accepted them.
    sqld = pd.to_datetime(
        lead.set_index("lead_id")["sql_date"]).reindex(j["lead_id"]).to_numpy()
    j["_before_sql"] = (j["act_dt"].to_numpy() <= sqld) & ~pd.isna(sqld)

    j = j.sort_values(["opportunity_id", "act_dt", "lead_id_a"]
                      if "lead_id_a" in j.columns
                      else ["opportunity_id", "act_dt"])
    # Keep the most recent MAX_TOUCHES per opportunity.
    j["_r"] = j.groupby("opportunity_id").cumcount(ascending=False)
    j = j[j["_r"] < MAX_TOUCHES].copy()
    j["touch_rank"] = j.groupby("opportunity_id").cumcount() + 1

    last_before = j[j["_before_sql"]].groupby("opportunity_id")["touch_rank"].max()
    j["is_sql_touch"] = (
        j["touch_rank"] == j["opportunity_id"].map(last_before)).astype(np.int8)

    j["lead_id"] = j["lead_id_a"] if "lead_id_a" in j.columns else j["lead_id"]
    return j.drop(columns=["_r", "_before_sql", "window_start"])


def _weights(rule: str, gid: np.ndarray, pos: np.ndarray, k: np.ndarray,
             is_first: np.ndarray, is_last: np.ndarray, is_sql: np.ndarray,
             m) -> np.ndarray:
    """Model weights that sum to exactly 1.0 per journey, at every length.

    The edge cases are the whole job. A one-touch journey has no middle to
    spread 20% across; a two-touch journey has no distinct SQL touch. The final
    renormalisation covers every branch, so the invariant holds for k = 1 as
    reliably as for k = 12 - and a model that leaks 0.4 of a weight on
    single-touch journeys breaks the totals on precisely the deals a demo
    drills into.
    """
    n = len(pos)
    if rule == "first":
        w = is_first.astype(float)
    elif rule == "last":
        w = is_last.astype(float)
    elif rule == "linear":
        w = 1.0 / k
    elif rule == "u":
        fp, lp = float(m.get("first_pct", 0.40)), float(m.get("last_pct", 0.40))
        mid = np.maximum(k - 2, 0)
        w = np.where(is_first, fp, np.where(is_last, lp,
                     np.divide(1.0 - fp - lp, mid,
                               out=np.zeros(n), where=mid > 0)))
        w = np.where(k == 1, 1.0, w)
    elif rule == "w":
        fp = float(m.get("first_pct", 0.30))
        sp = float(m.get("sql_pct", 0.30))
        lp = float(m.get("last_pct", 0.30))
        sql_only = is_sql.astype(bool) & ~is_first & ~is_last
        anchor = is_first | is_last | sql_only
        n_rest = k - _sum_per_group(anchor.astype(float), gid)
        w = (np.where(is_first, fp, 0.0)
             + np.where(is_last & ~is_first, lp, 0.0)
             + np.where(sql_only, sp, 0.0)
             + np.where(~anchor,
                        np.divide(1.0 - fp - sp - lp, np.maximum(n_rest, 1),
                                  out=np.zeros(n), where=n_rest > 0), 0.0))
    else:
        w = 1.0 / k
    # Final renormalisation: whatever the branch produced, the journey's
    # weights sum to 1.0. This is the line the invariant actually rests on.
    tot = _sum_per_group(w, gid)
    return np.divide(w, tot, out=np.zeros(n), where=tot > 0)


def _sum_per_group(x: np.ndarray, gid: np.ndarray) -> np.ndarray:
    """Sum of `x` within each journey, broadcast back to every row."""
    return np.bincount(gid, weights=x)[gid]
