"""fact_channel_response_curve - the model behind every what-if in the demo.

PLAN 2.7, and the largest thing the design note was missing. Four of its own
questions (Q15-Q18: "if we cut LinkedIn 20%...", "where should we invest an
extra $1M", "which campaigns have the best marginal ROI", "what should we scale
next quarter") cannot be answered from any table the note described. They need
a response model, and without one the "+$12.4M incremental pipeline" on the
optimisation page is a number someone typed.

The model is the standard diminishing-returns form:

    pipeline(spend) = a * ln(1 + spend / b)
    marginal(spend) = a / (b + spend)

`b` is the half-saturation constant. `spend / b` is the saturation ratio: above
1 the channel is past its inflection and the next dollar buys less than the
last. LinkedIn is configured at 3.4 and Webinar at 0.35, which is E8/E9 stated
as a mechanism rather than as an assertion - and it means the recommended
reallocation FALLS OUT of the model instead of being asserted alongside it.

`a` is then fitted so the curve passes exactly through each channel's OBSERVED
(spend, pipeline) point. The curve therefore cannot disagree with the actuals:
at current spend it reproduces them to the cent, and it only extrapolates away
from what really happened as you move the slider.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mktconfig import Scenario


def build_response_curves(s: Scenario, opp: pd.DataFrame, cm: pd.DataFrame,
                          camp: pd.DataFrame, channels: pd.DataFrame
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (fact_channel_response_curve, fact_budget_scenario)."""
    tl = s.timeline
    cmx = cm.merge(camp[["campaign_id", "channel_name"]], on="campaign_id",
                   how="left")
    cmx["m"] = pd.to_datetime(cmx["month_start"])
    ttm_spend = (cmx[cmx["m"] >= pd.Timestamp(tl.ttm_start)]
                 .groupby("channel_name")["spend_usd"].sum())

    o = opp.copy()
    o["od"] = pd.to_datetime(o["opportunity_date"])
    o["cd"] = pd.to_datetime(o["actual_close_date"])
    ttm_o = o[o["od"] >= pd.Timestamp(tl.ttm_start)]
    pipeline = ttm_o.groupby("source_channel")["amount_usd"].sum()
    revenue = (o[(o["is_won"] == 1) & (o["cd"] >= pd.Timestamp(tl.ttm_start))]
               .groupby("source_channel")["won_amount_usd"].sum())

    sat = s.response_curve["saturation"]
    rows = []
    for _, ch in channels.iterrows():
        name = ch["channel_name"]
        spend = float(ttm_spend.get(name, 0.0))
        pipe = float(pipeline.get(name, 0.0))
        rev = float(revenue.get(name, 0.0))
        if spend <= 0 or pipe <= 0:
            continue
        ratio = float(sat.get(name, 1.0))
        b = spend / ratio
        # a fitted so the curve reproduces the observed point exactly.
        a = pipe / np.log1p(spend / b)
        marginal = a / (b + spend)
        rows.append({
            "channel_id": int(ch["channel_id"]), "channel_name": name,
            "ttm_spend_usd": round(spend, 2),
            "ttm_pipeline_usd": round(pipe, 2),
            "ttm_revenue_usd": round(rev, 2),
            "curve_a": round(a, 4), "curve_b_usd": round(b, 2),
            "saturation_ratio": ratio,
            "marginal_pipeline_per_usd": round(marginal, 4),
            "average_pipeline_per_usd": round(pipe / spend, 4),
            "is_past_inflection": int(ratio > 1.0),
            "recommended_spend_usd": float(ch["recommended_spend_usd"]),
            "recommended_delta_usd": float(ch["recommended_delta_usd"]),
        })
    curves = pd.DataFrame(rows)
    if curves.empty:
        return curves, pd.DataFrame()
    curves["marginal_rank"] = curves["marginal_pipeline_per_usd"].rank(
        ascending=False).astype(np.int16)
    curves = _recommend(s, curves)
    return curves, _scenario_grid(s, curves)


def _recommend(s: Scenario, curves: pd.DataFrame) -> pd.DataFrame:
    """Solve the zero-sum reallocation instead of asserting it. (PLAN 2.7)

    Water-filling: at the optimum every channel returns the same marginal
    pipeline per dollar, so spend_i = a_i / lambda - b_i for a single shadow
    price lambda, found by bisection on the budget constraint. Each channel is
    capped at +/- `move_limit_pct` because no marketing organisation reallocates
    a third of its budget in one quarter, and an uncapped optimum empties four
    channels entirely - which is a correct answer to the wrong question.
    """
    cfg = s.cfg.get("reallocation", {})
    limit = float(cfg.get("move_limit_pct", 0.40))
    floor_usd = float(cfg.get("min_spend_usd", 0.0))
    a = curves["curve_a"].to_numpy()
    b = curves["curve_b_usd"].to_numpy()
    cur = curves["ttm_spend_usd"].to_numpy()
    budget = float(cur.sum())
    lo_cap = np.maximum(cur * (1 - limit), floor_usd)
    hi_cap = cur * (1 + limit)

    def spend_at(lam: float) -> np.ndarray:
        return np.clip(a / lam - b, lo_cap, hi_cap)

    lam_lo, lam_hi = 1e-9, float((a / np.maximum(b, 1.0)).max()) * 10
    for _ in range(200):
        lam = (lam_lo + lam_hi) / 2
        if spend_at(lam).sum() > budget:
            lam_lo = lam            # too much spend -> raise the price
        else:
            lam_hi = lam
    rec = spend_at((lam_lo + lam_hi) / 2)
    # Bisection lands within a rounding error of the budget; settle the residual
    # on the channels that are not sitting on a cap, so the plan is exactly
    # zero-sum and validate.py can assert it rather than tolerate it.
    free = (rec > lo_cap + 1) & (rec < hi_cap - 1)
    residual = budget - rec.sum()
    if free.any() and abs(residual) > 0.005:
        rec[free] += residual * rec[free] / rec[free].sum()
    curves["recommended_spend_usd"] = rec.round(2)
    curves["recommended_delta_usd"] = (rec - cur).round(2)
    return curves


def _scenario_grid(s: Scenario, curves: pd.DataFrame) -> pd.DataFrame:
    """Pre-computed what-ifs at +/-50% spend in 5% steps.

    A grid rather than a live solver, so any BI tool can answer "what if we cut
    LinkedIn 20%" with a lookup. Q15 and Q16 have to survive being asked by
    someone clicking a slicer, not by someone writing Python.
    """
    g = s.response_curve["scenario_grid"]
    mults = np.round(np.arange(float(g["min_mult"]),
                               float(g["max_mult"]) + 1e-9,
                               float(g["step"])), 4)
    out = []
    for _, c in curves.iterrows():
        spend = c["ttm_spend_usd"] * mults
        pipe = c["curve_a"] * np.log1p(spend / c["curve_b_usd"])
        out.append(pd.DataFrame({
            "channel_id": int(c["channel_id"]),
            "channel_name": c["channel_name"],
            "spend_multiplier": mults,
            "scenario_spend_usd": spend.round(2),
            "scenario_pipeline_usd": pipe.round(2),
            "delta_spend_usd": (spend - c["ttm_spend_usd"]).round(2),
            "delta_pipeline_usd": (pipe - c["ttm_pipeline_usd"]).round(2),
        }))
    df = pd.concat(out, ignore_index=True)
    df["incremental_pipeline_per_usd"] = np.where(
        df["delta_spend_usd"].abs() > 1,
        (df["delta_pipeline_usd"] / df["delta_spend_usd"]).round(4), np.nan)
    df.insert(0, "budget_scenario_id", np.arange(1, len(df) + 1))
    return df
