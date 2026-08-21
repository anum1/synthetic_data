"""Variable compensation: annual incentive, signing, retention and spot awards.

Bonus is a separate cost component in the workforce cost bridge, so it has to be
its own fact rather than a column smeared into payroll. Payroll picks these rows
up by payout date; it never invents a bonus of its own.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


def build_bonus(s, snap: pd.DataFrame, emp: pd.DataFrame,
                rng: np.random.Generator) -> pd.DataFrame:
    targets = s.baseline["bonus_target_pct_by_track"]
    lo, hi = s.baseline["bonus_payout_factor"]
    payout_month = int(s.calendar["merit_cycle_month"]) - 1 or 12
    years = sorted({int(k) // 100 for k in snap["year_month_key"].unique()})
    as_of = s.timeline.as_of_date

    rows = []
    for year in years[:-1] if len(years) > 1 else years:
        # Everyone on the books at the end of the plan year is eligible; the
        # payout lands in the following March.
        pool = snap[snap["year_month_key"] == year * 100 + 12]
        if pool.empty:
            pool = snap[(snap["year_month_key"] // 100) == year]
            if pool.empty:
                continue
            pool = pool[pool["year_month_key"] == pool["year_month_key"].max()]
        payout_date = dt.date(year + 1, payout_month, 15)
        if payout_date > as_of:
            continue
        n = len(pool)
        target_pct = pool["career_track"].map(targets).fillna(0.10).to_numpy()
        rating = pool["performance_rating"].to_numpy()
        # Payout factor tracks the rating, so "are high performers paid more"
        # has an answer in the data and not just in the slide.
        factor = np.clip((rating - 1) / 4 * (hi - lo) + lo
                         + rng.normal(0, 0.06, n), 0.0, 1.8)
        factor = np.where(rating <= 1, 0.0, factor)
        target_amt = pool["base_salary_usd"].to_numpy() * target_pct * pool["fte"].to_numpy()
        amount = target_amt * factor
        for k, (_, r) in enumerate(pool.iterrows()):
            if amount[k] <= 0:
                continue
            rows.append((int(r["employee_id"]), "Annual Incentive", year, payout_date,
                         round(float(target_pct[k]), 4), round(float(target_amt[k]), 2),
                         round(float(factor[k]), 4), round(float(amount[k]), 2),
                         r["currency"], int(r["organization_id"]),
                         int(r["performance_rating"]), int(r["is_acquired"])))

    # Signing bonuses for external hires, retention for the acquired population,
    # and spot awards scattered through the year.
    hires = emp[(emp["employee_id"] > 0)].copy()
    hires["hire_date"] = pd.to_datetime(hires["hire_date"], errors="coerce")
    recent = hires[hires["hire_date"] >= pd.Timestamp(s.timeline.start_date)]
    sign = recent[rng.random(len(recent)) < 0.34]
    for _, r in sign.iterrows():
        amt = float(r["base_salary_usd"]) * rng.uniform(0.04, 0.13)
        rows.append((int(r["employee_id"]), "Signing Bonus", int(r["hire_date"].year),
                     (r["hire_date"] + pd.Timedelta(days=30)).date(),
                     0.0, round(amt, 2), 1.0, round(amt, 2), r["currency"],
                     int(r["organization_id"]), int(r["performance_rating"]),
                     int(r["is_acquired"])))

    acq_ev = s.event("acquisition")
    if acq_ev:
        acq = hires[hires["is_acquired"] == 1]
        for _, r in acq.iterrows():
            if rng.random() > 0.55:
                continue
            amt = float(r["base_salary_usd"]) * rng.uniform(0.08, 0.22)
            pay = (r["hire_date"] + pd.Timedelta(days=365)).date()
            if pay > as_of:
                continue
            rows.append((int(r["employee_id"]), "Retention Bonus", pay.year, pay,
                         0.0, round(amt, 2), 1.0, round(amt, 2), r["currency"],
                         int(r["organization_id"]), int(r["performance_rating"]), 1))

    spot = snap.sample(frac=0.012, random_state=int(s.seed))
    for _, r in spot.iterrows():
        amt = float(rng.choice([500, 1000, 2500, 5000]))
        ym = int(r["year_month_key"])
        pay = dt.date(ym // 100, ym % 100, 20)
        if pay > as_of:
            continue
        rows.append((int(r["employee_id"]), "Spot Award", ym // 100, pay,
                     0.0, amt, 1.0, amt, r["currency"], int(r["organization_id"]),
                     int(r["performance_rating"]), int(r["is_acquired"])))

    out = pd.DataFrame(rows, columns=[
        "employee_id", "bonus_type", "plan_year", "payout_date", "target_pct",
        "target_amount_usd", "payout_factor", "bonus_amount_usd", "currency",
        "organization_id", "performance_rating", "is_acquired"])
    # Bonus carries a currency, so it has to carry a local amount too. Every
    # other money fact in the dataset does; a row reading currency = INR with
    # only a USD figure on it is the kind of inconsistency an audience spots.
    fx = {c: float(z["fx_to_usd"]) for c, z in s.comp["geo_zone"].items()}
    rate = out["currency"].map({z["currency"]: float(z["fx_to_usd"])
                                for z in s.comp["geo_zone"].values()}).fillna(1.0)
    out["bonus_amount_local"] = (out["bonus_amount_usd"] / rate).round(2)
    out["target_amount_local"] = (out["target_amount_usd"] / rate).round(2)

    out["year_month_key"] = (pd.to_datetime(out["payout_date"]).dt.year * 100
                             + pd.to_datetime(out["payout_date"]).dt.month).astype("int32")

    # A bonus is only paid to someone still on the books in the payout month,
    # which is how most plans work - and it is what keeps fact_bonus and the
    # bonus line in fact_payroll equal to the cent. A leaver forfeits.
    on_books = snap[["employee_id", "year_month_key"]].drop_duplicates()
    out = out.merge(on_books, on=["employee_id", "year_month_key"], how="inner")

    out = out.reset_index(drop=True)
    out.insert(0, "bonus_id", np.arange(1, len(out) + 1, dtype="int64"))
    out["award_date"] = out["payout_date"]
    return out
