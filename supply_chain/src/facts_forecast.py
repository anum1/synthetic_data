"""Forecast fact: month x product x region x version.

Four versions, each having seen progressively more of the planted events. That
is what makes forecast deterioration visible as a walk ACROSS versions rather
than as a single accuracy number that can only go up or down.

Grain is product x REGION, not product x location: statistical forecasting at
SKU x DC grain is not how planning organisations work, and it would have
produced 8.6M rows of mostly-zero series (docs/DATA_MODEL.md section 3.3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_fact_forecast(s, fact_demand, dim_product, dim_region, engine, rng):
    d = fact_demand.copy()
    d["month_start"] = pd.to_datetime(d["week_start_date"]).dt.to_period("M").dt.to_timestamp()
    actual = (d.groupby(["month_start", "product_id", "region_id"])["demand_qty"]
              .sum().reset_index().rename(columns={"demand_qty": "actual_qty"}))

    months = pd.to_datetime(actual["month_start"])
    mpos = engine.month_pos(months)
    ppos = actual["product_id"].to_numpy() - 1
    bias_all = engine.forecast_bias[ppos, mpos]
    noise_all = engine.forecast_noise_mult[ppos, mpos]

    improved = set(dim_product["product_id"].to_numpy()[
        engine.targets.get("override_improved", np.array([], dtype=int))].tolist())
    degraded = set(dim_product["product_id"].to_numpy()[
        engine.targets.get("override_degraded", np.array([], dtype=int))].tolist())
    ov = s.event("planner_override_win") or {}

    horizons = list(s.forecast.get("horizons_months", [1]))
    ci = float(s.forecast.get("confidence_interval_pct", 0.8))
    out = []

    for v in s.forecast["versions"]:
        name = v["name"]
        base_mape = float(v["base_mape"])
        # A version only "knows" events that started before its cutoff; the
        # rest of the movement lands on it as error.
        cutoff = s.timeline.offset_month(int(v["events_visible_before_offset"]))
        seen = (months.dt.date.to_numpy() < cutoff)

        sigma = np.full(len(actual), base_mape) * noise_all
        bias = np.where(seen, bias_all * 0.25, bias_all)

        if name == "Planner Override":
            pid = actual["product_id"].to_numpy()
            imp = np.isin(pid, list(improved))
            deg = np.isin(pid, list(degraded))
            sigma = sigma - imp * float(ov.get("mape_improvement_points", 0.0))
            sigma = sigma + deg * float(ov.get("mape_degradation_points", 0.0))
        sigma = np.clip(sigma, 0.02, 1.5)

        for h in horizons:
            # Longer horizons are less accurate; this is what makes
            # "accuracy by horizon" a real chart rather than a flat line.
            sig_h = sigma * (1 + 0.16 * (h - 1))
            err = rng.normal(0.0, sig_h)
            fc = np.clip(actual["actual_qty"].to_numpy() * (1 + bias + err), 0, None)
            gen = months - pd.to_timedelta(h * 30, unit="D")
            out.append(pd.DataFrame({
                "forecast_month": months,
                "forecast_generated_date": gen,
                "product_id": actual["product_id"].to_numpy().astype("int32"),
                "region_id": actual["region_id"].to_numpy().astype("int32"),
                "forecast_version": name,
                "forecast_horizon_months": np.int32(h),
                "forecast_qty": np.round(fc, 3),
                "actual_qty": np.round(actual["actual_qty"].to_numpy(), 3),
                "confidence_low": np.round(fc * (1 - (1 - ci) - sig_h), 3).clip(0),
                "confidence_high": np.round(fc * (1 + (1 - ci) + sig_h), 3),
            }))

    df = pd.concat(out, ignore_index=True)
    df["forecast_error"] = np.round(df["forecast_qty"] - df["actual_qty"], 3)
    denom = df["actual_qty"].replace(0, np.nan)
    df["abs_pct_error"] = (df["forecast_error"].abs() / denom).round(5)
    df["forecast_accuracy"] = (1 - df["abs_pct_error"]).clip(lower=0).round(5)
    df["forecast_bias_pct"] = (df["forecast_error"] / denom).round(5)
    df["year_month_key"] = (df["forecast_month"].dt.year * 100
                            + df["forecast_month"].dt.month).astype("int32")
    return df
