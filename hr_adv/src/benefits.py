"""Benefit plans and enrolment.

Enrolment is per employee PER PLAN YEAR, not once per employee. It is the only
grain that lets "benefits cost per employee" be compared year over year, which
is the question Event 5 exists to answer.

Employee contributions computed here are the same numbers payroll later deducts
- payroll does not draw its own. That is the rule the whole dataset follows:
one source of truth per amount.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R

# Total plan cost varies by country: healthcare in the US costs a multiple of
# what it costs where there is a national system.
COUNTRY_COST_FACTOR = {"US": 1.00, "Canada": 0.58, "UK": 0.47,
                       "Germany": 0.62, "India": 0.29, "Japan": 0.53}
# Percentage-of-salary plans (retirement) are NOT scaled by the country factor:
# a match is a match wherever the employee sits.


def build_dim_benefit_plan(s, rng: np.random.Generator) -> pd.DataFrame:
    years = list(range(s.timeline.start_date.year, s.timeline.as_of_date.year + 1))
    infl = float(s.benefits["annual_cost_inflation"])
    base_year = years[0]
    ev = s.event("benefits_inflation")
    ev_year = None
    if ev:
        ev_month = s.timeline.offset_month(int(ev["plan_year_offset"]) * 12)
        ev_year = s.timeline.as_of_date.year if ev["plan_year_offset"] == 0 else ev_month.year

    catalog = list(R.BENEFIT_CATALOG)
    acq = s.event("acquisition")
    if acq and acq.get("own_benefit_plans"):
        # Event 7 - the acquired company brings its own plans, which is exactly
        # how a benefits book gets expensive without anyone deciding to make it so.
        name = acq["company_name"]
        catalog += [("Medical", f"{name} Legacy PPO", "Harborline Benefits", 4, 13_900, "flat"),
                    ("Dental", f"{name} Legacy Dental", "Harborline Benefits", 4, 1_050, "flat"),
                    ("401K", f"{name} Legacy Match", "Cardinal Retirement", 1, 0.070, "pct")]

    rows = []
    pid = 1
    for year in years:
        for btype, plan_name, provider, tiers, cost, basis in catalog:
            employer_share = float(s.benefits["employer_share"].get(btype, 0.6))
            total = (cost if basis == "pct"
                     else cost * ((1 + infl) ** (year - base_year)))
            emp_bump = 1.0
            if ev and ev_year is not None and year >= ev_year and btype == ev["benefit_type"]:
                total *= (1 + float(ev["employer_cost_increase"]))
                emp_bump = (1 + float(ev["employee_cost_increase"])) / \
                           (1 + float(ev["employer_cost_increase"]))
            employer = total * employer_share
            employee = (total - employer) * emp_bump
            rows.append({
                "benefit_plan_id": pid,
                "plan_code": f"BEN{pid:04d}",
                "benefit_type": btype,
                "plan_name": plan_name,
                "provider": provider,
                "plan_year": year,
                "supports_dependents": int(tiers > 1),
                "cost_basis": basis,
                "salary_pct": round(total, 4) if basis == "pct" else 0.0,
                "annual_total_cost_usd": round(total if basis == "flat" else 0.0, 2),
                "annual_employer_cost_usd": round(employer if basis == "flat" else 0.0, 2),
                "annual_employee_cost_usd": round(employee if basis == "flat" else 0.0, 2),
                "employer_cost_pct_of_salary": round(
                    total * employer_share, 4) if basis == "pct" else 0.0,
                "employer_cost_share": round(employer_share, 4),
                "effective_date": dt.date(year, int(s.calendar["benefit_plan_year_start"]), 1),
                "end_date": dt.date(year, 12, 31),
                "is_legacy_acquired_plan": int(plan_name.startswith(
                    acq["company_name"] if acq else "\0")),
                "is_active": int(year == years[-1]),
            })
            pid += 1
    return pd.DataFrame(rows)


def build_benefit_enrollment(s, snap: pd.DataFrame, plans: pd.DataFrame,
                             rng: np.random.Generator) -> pd.DataFrame:
    """One row per employee per plan per plan year they were enrolled."""
    cfg = s.benefits
    lo, hi = cfg["plans_per_participant"]
    years = sorted(plans["plan_year"].unique())
    coverage_mix = cfg["coverage_mix"]

    # Enrolment is decided at the start of each plan year, from whoever is on the
    # books in January (or the first month of history).
    snap = snap.copy()
    snap["year"] = (snap["year_month_key"] // 100).astype(int)
    snap["month"] = (snap["year_month_key"] % 100).astype(int)

    frames = []
    eid = 1
    for year in years:
        pool = snap[(snap["year"] == year)]
        if pool.empty:
            continue
        # Each employee's FIRST month in the plan year, so a mid-year hire elects
        # at hire instead of going a year with no benefits at all. Enrolling only
        # the January population silently leaves ~15% of the workforce with zero
        # benefit cost and understates cost per employee by the same margin.
        pool = pool.loc[pool.groupby("employee_id")["month"].idxmin()]
        n = len(pool)
        take = rng.random(n) < float(cfg["participation_rate"])
        pool = pool[take]
        if pool.empty:
            continue

        year_plans = plans[plans["plan_year"] == year]
        acq_plans = year_plans[year_plans["is_legacy_acquired_plan"] == 1]
        std_plans = year_plans[year_plans["is_legacy_acquired_plan"] == 0]

        months_covered = (13 - pool["month"].to_numpy()).clip(1, 12)
        counts = rng.integers(lo, hi + 1, len(pool))
        coverage = R.weighted_choice(rng, coverage_mix, len(pool))
        rows = []
        std_ids = std_plans["benefit_plan_id"].to_numpy()
        acq_ids = acq_plans["benefit_plan_id"].to_numpy()
        plan_lookup = year_plans.set_index("benefit_plan_id")

        for k, (_, emp) in enumerate(pool.iterrows()):
            # Acquired employees stay on their legacy plans while they exist.
            pool_ids = (np.concatenate([acq_ids, std_ids])
                        if emp["is_acquired"] == 1 and len(acq_ids) else std_ids)
            picked = rng.choice(pool_ids, size=min(int(counts[k]), len(pool_ids)),
                                replace=False)
            cov = coverage[k]
            cov_factor = R.COVERAGE_COST_FACTOR[cov]
            country_factor = COUNTRY_COST_FACTOR.get(emp["country"], 0.5)
            salary = float(emp["base_salary_usd"])
            for pid in picked:
                p = plan_lookup.loc[pid]
                if p["cost_basis"] == "pct":
                    total = salary * float(p["salary_pct"])
                    employer = total * float(p["employer_cost_share"])
                    employee = total - employer
                else:
                    factor = (cov_factor if p["supports_dependents"] == 1 else 1.0)
                    factor *= country_factor
                    employer = float(p["annual_employer_cost_usd"]) * factor
                    employee = float(p["annual_employee_cost_usd"]) * factor
                months = int(months_covered[k])
                rows.append((eid, int(emp["employee_id"]), int(pid), year,
                             p["benefit_type"], p["plan_name"],
                             cov if p["supports_dependents"] == 1 else "Employee Only",
                             round(employee, 2), round(employer, 2),
                             round(employee + employer, 2), months,
                             round(employee * months / 12, 2),
                             round(employer * months / 12, 2),
                             int(emp["organization_id"]), emp["country"],
                             int(emp["is_acquired"])))
                eid += 1
        frames.append(pd.DataFrame(rows, columns=[
            "benefit_enrollment_id", "employee_id", "benefit_plan_id", "plan_year",
            "benefit_type", "plan_name", "coverage_level",
            "annual_employee_contribution_usd", "annual_employer_contribution_usd",
            "annual_total_cost_usd", "months_covered",
            "prorated_employee_contribution_usd", "prorated_employer_contribution_usd",
            "organization_id", "country", "is_acquired"]))

    out = pd.concat(frames, ignore_index=True)
    out["effective_date"] = pd.to_datetime(
        out["plan_year"].astype(str) + "-"
        + (13 - out["months_covered"]).astype(str).str.zfill(2) + "-01").dt.date
    out["end_date"] = pd.to_datetime(out["plan_year"].astype(str) + "-12-31").dt.date
    out["enrollment_status"] = "Enrolled"
    out["enrollment_reason"] = np.where(
        rng.random(len(out)) < float(s.benefits["life_event_rate_annual"]),
        "Life Event", "Open Enrollment")
    out["monthly_employee_contribution_usd"] = (
        out["annual_employee_contribution_usd"] / 12).round(2)
    out["monthly_employer_contribution_usd"] = (
        out["annual_employer_contribution_usd"] / 12).round(2)
    return out
