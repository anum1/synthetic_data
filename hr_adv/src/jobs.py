"""Job catalog and geo-differentiated salary ranges.

The design note gave every job a single min/mid/max. Across six countries that
makes every employee in India look catastrophically underpaid against a USD
midpoint, and compa-ratio is the backbone of two of the planted events, so the
range has to be per job PER GEOGRAPHY.

Money is carried in both local currency and USD, converted at a FIXED budget
rate. Fixing the rate is deliberate: a floating one would put FX movement into
the workforce cost bridge, and this is an HR demo, not a treasury one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import reference as R

# Levels open to each career track.
IC_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
MGMT_LEVELS = ["L4", "L5", "L6", "L7"]
EXEC_LEVELS = ["L8", "L9"]

STANDARD_HOURS = {"US": 40, "Canada": 37.5, "UK": 37.5,
                  "Germany": 40, "India": 45, "Japan": 40}


def build_dim_job(s, rng: np.random.Generator) -> pd.DataFrame:
    cap = int(s.sizes["jobs"])
    rows = []

    def add(family, subfamily, function, level, track, title):
        rows.append({
            "job_family": family, "job_subfamily": subfamily,
            "function_name": function, "job_level": level,
            "career_track": track,
            "management_level": R.MANAGEMENT_LEVEL[track],
            "job_title": title,
            "is_people_manager": int(track != "Individual Contributor"),
        })

    for function, families in R.JOB_FAMILIES.items():
        for family, subfamilies in families.items():
            is_mgmt_family = family in R.MANAGEMENT_FAMILIES
            for subfamily in subfamilies:
                levels = MGMT_LEVELS if is_mgmt_family else IC_LEVELS
                for level in levels:
                    for track, prefix in R.LEVEL_TRACKS[level]:
                        if is_mgmt_family and track == "Individual Contributor":
                            continue
                        if not is_mgmt_family and track != "Individual Contributor" \
                                and level in ("L4", "L5"):
                            # A Manager-track job exists for every family, but the
                            # title comes from the family it manages.
                            pass
                        title = (f"{prefix}{subfamily}" if track == "Individual Contributor"
                                 else f"{prefix}{subfamily}")
                        add(family, subfamily, function, level, track, title)
        # Executive jobs sit at the function, not the subfamily.
        for level in EXEC_LEVELS:
            track, prefix = R.LEVEL_TRACKS[level][0]
            add(f"{function} Leadership", function, function, level, track,
                f"{prefix}{function}")

    df = pd.DataFrame(rows).drop_duplicates(
        subset=["job_title", "job_level", "career_track"]).reset_index(drop=True)

    if len(df) > cap:
        # Keep every level of every family so no band goes missing, then thin the
        # subfamilies. Sampling rows at random would leave holes in the ladder.
        keep = df.groupby(["job_family", "job_level"], observed=True).head(1).index
        rest = df.index.difference(keep)
        extra = rng.choice(rest, size=max(cap - len(keep), 0), replace=False)
        df = df.loc[sorted(set(keep) | set(extra))].reset_index(drop=True)

    df.insert(0, "job_id", np.arange(1, len(df) + 1, dtype="int32"))
    df["job_code"] = "JOB_" + df["job_id"].astype(str).str.zfill(4)
    df["job_family_premium"] = df["job_family"].map(R.JOB_FAMILY_PREMIUM).fillna(0.95)
    # Exempt status drives overtime eligibility, so the payroll anomaly lands on
    # a population that could plausibly earn overtime. Junior non-engineering
    # roles are non-exempt; engineers and lawyers are exempt at every level,
    # which is both true under FLSA and what keeps Event 6 credible.
    df["exempt_status"] = np.where(
        df["job_level"].isin(["L1", "L2", "L3"])
        & ~df["function_name"].isin(["Engineering", "Legal"]),
        "Non-Exempt", "Exempt")
    df["job_profile_status"] = "Active"
    df["effective_date"] = s.timeline.start_date
    return df


def build_job_salary_range(s, jobs: pd.DataFrame) -> pd.DataFrame:
    comp = s.comp
    zones = comp["geo_zone"]
    mid_usd = comp["level_midpoint_usd"]
    spread = float(comp["range_spread"])
    movement = float(comp["range_movement_annual"])
    base_year = s.timeline.start_date.year
    years = list(range(base_year, s.timeline.as_of_date.year + 1))

    by_function = comp.get("range_movement_by_function", {}) or {}
    frames = []
    for year in years:
        for country, zone in zones.items():
            f = jobs[["job_id", "job_level", "job_family", "job_family_premium",
                      "function_name"]].copy()
            rate = f["function_name"].map(by_function).fillna(movement).astype(float)
            drift = (1 + rate) ** (year - base_year)
            f["effective_year"] = year
            f["geo_zone"] = country
            f["currency"] = zone["currency"]
            f["fx_rate_to_usd"] = float(zone["fx_to_usd"])
            anchor = f["job_level"].map(mid_usd).astype(float)
            mid = anchor * float(zone["factor"]) * f["job_family_premium"] * drift
            f["midpoint_usd"] = (mid).round(0)
            f["minimum_usd"] = (mid * (1 - spread / 2)).round(0)
            f["maximum_usd"] = (mid * (1 + spread / 2)).round(0)
            for col in ["minimum", "midpoint", "maximum"]:
                f[f"{col}_local"] = (f[f"{col}_usd"] / f["fx_rate_to_usd"]).round(0)
            f["range_spread_pct"] = spread
            f["standard_hours"] = STANDARD_HOURS[country]
            f["range_movement_pct"] = rate
            frames.append(f.drop(columns=["job_family", "job_family_premium",
                                          "function_name"]))

    out = pd.concat(frames, ignore_index=True)
    out.insert(0, "job_salary_range_id", np.arange(1, len(out) + 1, dtype="int32"))
    return out
