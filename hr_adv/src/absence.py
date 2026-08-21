"""Absence occurrences, and the unpaid-leave hours payroll subtracts.

Absence is only decorative unless something depends on it. Here unpaid leave
really does reduce paid hours in payroll, and the manager-problem org really
does run hot on sick days, so the table earns its place in two separate demo
flows instead of sitting on a page nobody clicks.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R

STATUS = ["Approved", "Approved", "Approved", "Approved", "Taken", "Cancelled"]


def build_absence(s, snap: pd.DataFrame, rng: np.random.Generator,
                  manager_problem_orgs: np.ndarray) -> pd.DataFrame:
    cfg = s.absence
    per_year = cfg["days_per_employee_year"]
    type_mix = cfg["type_mix"]

    # One draw per employee-month keeps the volume proportional to time employed
    # rather than to headcount at a point in time.
    base = snap[["employee_id", "year_month_key", "country", "organization_id",
                 "fte", "job_level"]].copy()
    n = len(base)
    monthly_days = base["country"].map(per_year).fillna(18).to_numpy() / 12.0
    mult = np.ones(n)
    if len(manager_problem_orgs):
        hit = np.isin(base["organization_id"].to_numpy(), manager_problem_orgs)
        mult = np.where(hit, float(s.event("manager_problem")["absence_multiplier"])
                        if s.event("manager_problem") else 1.0, 1.0)

    month = (base["year_month_key"].to_numpy() % 100)
    # Vacation clusters in the summer and around year end.
    season = np.array([0.7, 0.7, 0.9, 1.0, 1.0, 1.3, 1.6, 1.5, 0.9, 0.9, 0.8, 1.5])[month - 1]
    lam = monthly_days * mult * season * base["fte"].to_numpy() / 2.6
    occurrences = rng.poisson(np.clip(lam, 0, 6))

    keep = occurrences > 0
    idx = np.repeat(np.arange(n)[keep], occurrences[keep])
    if len(idx) == 0:
        return pd.DataFrame()

    k = len(idx)
    rows = base.iloc[idx].reset_index(drop=True)
    atype = R.weighted_choice(rng, type_mix, k)
    # Parental leave is long; bereavement is short; vacation is a few days.
    length = np.where(atype == "Parental", rng.integers(20, 90, k),
             np.where(atype == "Unpaid Leave", rng.integers(3, 25, k),
             np.where(atype == "Bereavement", rng.integers(1, 4, k),
             np.where(atype == "Sick", rng.integers(1, 4, k),
                      rng.integers(1, 9, k)))))
    ym = rows["year_month_key"].to_numpy()
    start_day = rng.integers(1, 26, k)
    start = [dt.date(int(v // 100), int(v % 100), int(d)) for v, d in zip(ym, start_day)]
    end = [srt + dt.timedelta(days=int(l) - 1) for srt, l in zip(start, length)]

    out = pd.DataFrame({
        "absence_id": np.arange(1, k + 1, dtype="int64"),
        "employee_id": rows["employee_id"].astype("int32"),
        "organization_id": rows["organization_id"].astype("int32"),
        "country": rows["country"],
        "absence_type": atype,
        "start_date": start,
        "end_date": end,
        "year_month_key": ym.astype("int32"),
        "calendar_days": length.astype("int16"),
    })
    # Working days, not calendar days: a five-day absence spanning a weekend is
    # not five days of lost capacity.
    out["absence_days"] = np.maximum(np.round(out["calendar_days"] * 5 / 7), 1).astype("int16")
    out["absence_hours"] = (out["absence_days"] * 8 * rows["fte"].to_numpy()).round(1)
    out["is_paid"] = (out["absence_type"] != "Unpaid Leave").astype("int8")
    out["unpaid_hours"] = np.where(out["is_paid"] == 0, out["absence_hours"], 0.0)
    out["absence_status"] = rng.choice(STATUS, size=k)
    out.loc[out["absence_status"] == "Cancelled", ["absence_hours", "unpaid_hours"]] = 0.0
    return out
