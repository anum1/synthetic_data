"""Pay calendar and derived payroll.

Payroll is DERIVED, never drawn. `fact_salary_history` (via the month-end
snapshot that reflects it) is the only source of base pay, `fact_bonus` is the
only source of bonus, and `fact_benefit_enrollment` is the only source of the
benefit deduction. Generate any of those independently and the Compensation page
stops agreeing with the Payroll page, which is the fastest way to lose a room.

Employer benefit cost and employer payroll tax are carried as their own columns.
They are part of total workforce cost but they are NOT part of gross pay, and
conflating the two is how workforce-cost numbers end up 20% too high.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = {"Biweekly": 26, "Monthly": 12, "Semimonthly": 24, "Weekly": 52}


def build_pay_calendar(s) -> pd.DataFrame:
    """Pay periods per pay group across the timeline.

    US and Canada run biweekly; the UK, Germany, India and Japan run monthly.
    The design note assumed 26 periods for everyone, which is both wrong and a
    missed opportunity - the mixed frequency is what makes the payroll anomaly
    hard to spot by eye.
    """
    zones = s.comp["geo_zone"]
    groups: dict[str, list[str]] = {}
    for country, z in zones.items():
        groups.setdefault(z["pay_frequency"], []).append(country)

    start = s.timeline.start_date
    end = s.timeline.as_of_date
    rows = []
    pid = 1
    for freq, countries in groups.items():
        ppy = PERIODS_PER_YEAR[freq]
        if freq == "Biweekly":
            # Anchor on the first Friday of the timeline and step 14 days.
            anchor = start + dt.timedelta(days=(4 - start.weekday()) % 7)
            cur = anchor
            while cur <= end:
                p_start = cur - dt.timedelta(days=13)
                rows.append((pid, freq, ",".join(countries), p_start, cur,
                             cur + dt.timedelta(days=5), ppy))
                pid += 1
                cur += dt.timedelta(days=14)
        else:
            cur = start.replace(day=1)
            while cur <= end:
                nxt = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
                p_end = nxt - dt.timedelta(days=1)
                rows.append((pid, freq, ",".join(countries), cur, p_end,
                             p_end, ppy))
                pid += 1
                cur = nxt

    cal = pd.DataFrame(rows, columns=[
        "pay_period_id", "pay_frequency", "pay_group_countries",
        "pay_period_start", "pay_period_end", "pay_date", "periods_per_year"])
    cal = cal[pd.to_datetime(cal["pay_period_end"]) <= pd.Timestamp(end)].copy()
    pe = pd.to_datetime(cal["pay_period_end"])
    cal["year_month_key"] = (pe.dt.year * 100 + pe.dt.month).astype("int32")
    cal["pay_period_name"] = (cal["pay_frequency"].str[:1] + pe.dt.strftime("%Y-%m-%d"))
    return cal.reset_index(drop=True)


def build_payroll(s, snap: pd.DataFrame, cal: pd.DataFrame, jobs: pd.DataFrame,
                  bonus: pd.DataFrame, enroll: pd.DataFrame, absence: pd.DataFrame,
                  emp: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    zones = s.comp["geo_zone"]
    freq_of_country = {c: z["pay_frequency"] for c, z in zones.items()}
    fx_of_country = {c: float(z["fx_to_usd"]) for c, z in zones.items()}

    base = snap[["employee_id", "year_month_key", "organization_id", "job_id",
                 "job_level", "function_name", "country", "location_id",
                 "base_salary_usd", "fte", "currency", "cost_center",
                 "manager_employee_id", "is_acquired"]].copy()
    base["pay_frequency"] = base["country"].map(freq_of_country)

    periods = cal[["pay_period_id", "pay_frequency", "pay_period_start",
                   "pay_period_end", "pay_date", "periods_per_year",
                   "year_month_key"]]
    pay = base.merge(periods, on=["pay_frequency", "year_month_key"], how="inner")

    ppy = pay["periods_per_year"].to_numpy()
    fte = pay["fte"].to_numpy()
    salary = pay["base_salary_usd"].to_numpy()
    n = len(pay)

    exempt = pay["job_id"].map(dict(zip(jobs["job_id"], jobs["exempt_status"])))
    pay["exempt_status"] = exempt.fillna("Exempt")
    std_hours = 40.0
    weeks = 52.0 / ppy
    pay["regular_hours"] = np.round(std_hours * weeks * fte, 2)

    # Unpaid leave really reduces paid hours.
    if len(absence):
        unpaid = (absence.groupby(["employee_id", "year_month_key"])["unpaid_hours"]
                  .sum().rename("unpaid_month_hours").reset_index())
        pay = pay.merge(unpaid, on=["employee_id", "year_month_key"], how="left")
        pay["unpaid_month_hours"] = pay["unpaid_month_hours"].fillna(0.0)
    else:
        pay["unpaid_month_hours"] = 0.0
    periods_in_month = np.where(pay["pay_frequency"].to_numpy() == "Biweekly", 2.17, 1.0)
    pay["unpaid_hours"] = np.minimum(pay["unpaid_month_hours"] / periods_in_month,
                                     pay["regular_hours"]).round(2)
    paid_fraction = 1 - pay["unpaid_hours"].to_numpy() / np.maximum(
        pay["regular_hours"].to_numpy(), 1)
    pay["regular_pay"] = np.round(salary / ppy * fte * paid_fraction, 2)

    # Overtime: non-exempt employees only.
    lo, hi = s.baseline["overtime_hours_per_period"]
    participation = float(s.baseline.get("overtime_participation", 0.55))
    non_exempt = (pay["exempt_status"].to_numpy() == "Non-Exempt")
    ot_hours = np.where(non_exempt & (rng.random(n) < participation),
                        rng.uniform(lo, hi, n), 0.0)

    # Event 6 - a payroll anomaly in one business unit for two pay periods.
    ev = s.event("payroll_anomaly")
    pay["is_payroll_anomaly"] = 0
    if ev:
        month = s.timeline.offset_month(int(ev["month_offset"]))
        ym = month.year * 100 + month.month
        hit = ((pay["year_month_key"].to_numpy() == ym)
               & (pay["function_name"].to_numpy() == ev["organization"])
               & (pay["country"].to_numpy() == ev["country"]))
        if hit.any():
            affected_periods = np.unique(pay.loc[hit, "pay_period_id"])[
                :int(ev["pay_periods"])]
            hit = hit & np.isin(pay["pay_period_id"].to_numpy(), affected_periods)
            # The anomaly reaches everyone in the unit, exempt or not - that is
            # what makes it an error rather than a busy month.
            ot_hours = np.where(hit,
                                np.maximum(ot_hours, 1.0) * float(ev["overtime_multiplier"]),
                                ot_hours)
            pay["is_payroll_anomaly"] = hit.astype("int8")

    hourly = salary / (std_hours * 52.0)
    pay["overtime_hours"] = np.round(ot_hours, 2)
    pay["overtime_pay"] = np.round(ot_hours * hourly * 1.5, 2)

    # Bonus rows land in the period containing their payout date.
    if len(bonus):
        b = (bonus.groupby(["employee_id", "year_month_key"])["bonus_amount_usd"]
             .sum().rename("bonus_month").reset_index())
        pay = pay.merge(b, on=["employee_id", "year_month_key"], how="left")
        pay["bonus_month"] = pay["bonus_month"].fillna(0.0)
    else:
        pay["bonus_month"] = 0.0
    # Pay the whole bonus in the FIRST period of its month, not smeared across
    # both - a bonus that arrives in two equal halves is not a bonus.
    first_period = pay.groupby(["employee_id", "year_month_key"])["pay_period_id"] \
        .transform("min")
    pay["bonus_pay"] = np.where(pay["pay_period_id"] == first_period,
                                pay["bonus_month"], 0.0).round(2)

    # Commission, for the functions that earn it.
    comm_lo, comm_hi = s.payroll["commission_pct_of_base"]
    is_comm = pay["function_name"].isin(s.payroll["commission_functions"]).to_numpy()
    comm_rate = rng.uniform(comm_lo, comm_hi, n)
    attainment = np.clip(rng.normal(1.0, 0.34, n), 0.0, 2.4)
    pay["commission"] = np.round(np.where(is_comm,
                                          salary * comm_rate / ppy * attainment, 0.0), 2)

    allowance_share = pay["country"].map(s.payroll["allowance_share_of_base"]).fillna(0.005)
    pay["allowance"] = np.round(salary * allowance_share.to_numpy() / ppy * fte, 2)

    pay["gross_pay"] = (pay["regular_pay"] + pay["overtime_pay"] + pay["bonus_pay"]
                        + pay["commission"] + pay["allowance"]).round(2)

    # Benefit deductions come from the enrolment fact, never from a fresh draw.
    if len(enroll):
        pay["plan_year"] = (pay["year_month_key"] // 100).astype(int)
        contrib = (enroll.groupby(["employee_id", "plan_year"])
                   [["annual_employee_contribution_usd",
                     "annual_employer_contribution_usd"]].sum().reset_index())
        pay = pay.merge(contrib, on=["employee_id", "plan_year"], how="left")
        pay[["annual_employee_contribution_usd", "annual_employer_contribution_usd"]] = \
            pay[["annual_employee_contribution_usd",
                 "annual_employer_contribution_usd"]].fillna(0.0)
    else:
        pay["annual_employee_contribution_usd"] = 0.0
        pay["annual_employer_contribution_usd"] = 0.0
    pay["benefit_deduction"] = (pay["annual_employee_contribution_usd"] / ppy).round(2)
    pay["employer_benefit_cost"] = (pay["annual_employer_contribution_usd"] / ppy).round(2)

    tax_rate = pay["country"].map(s.payroll["effective_tax_rate"]).fillna(0.25).to_numpy()
    pay["tax"] = np.round(pay["gross_pay"].to_numpy() * tax_rate, 2)
    pay["employer_tax"] = np.round(pay["gross_pay"].to_numpy()
                                   * float(s.payroll["employer_tax_rate"]), 2)
    pay["other_deduction"] = np.round(pay["gross_pay"].to_numpy() * 0.004, 2)
    pay["net_pay"] = (pay["gross_pay"] - pay["tax"] - pay["benefit_deduction"]
                      - pay["other_deduction"]).round(2)
    pay["total_employer_cost"] = (pay["gross_pay"] + pay["employer_tax"]
                                  + pay["employer_benefit_cost"]).round(2)

    fx = pay["country"].map(fx_of_country).to_numpy()
    for col in ["gross_pay", "net_pay", "regular_pay"]:
        pay[f"{col}_local"] = np.round(pay[col].to_numpy() / fx, 2)

    pay = _plant_late_terminations(s, pay, emp, rng)

    pay.insert(0, "payroll_id", np.arange(1, len(pay) + 1, dtype="int64"))
    drop = ["bonus_month", "unpaid_month_hours", "annual_employee_contribution_usd",
            "annual_employer_contribution_usd", "plan_year"]
    return pay.drop(columns=[c for c in drop if c in pay.columns])


def _plant_late_terminations(s, pay: pd.DataFrame, emp: pd.DataFrame,
                             rng: np.random.Generator) -> pd.DataFrame:
    """Deliberate defect: payroll kept running for a few people after they left.

    A real and expensive thing that happens in real HR systems, and a good
    question for an audience that thinks synthetic data is always tidy.
    """
    cfg = s.data_quality
    if not cfg or not int(cfg.get("late_termination_posting", 0)):
        return pay
    left = emp[(emp["employment_status"] == "Terminated")
               & emp["termination_date"].notna()]
    if left.empty:
        return pay
    k = min(int(cfg["late_termination_posting"]), len(left))
    chosen = left.sample(k, random_state=int(s.seed))
    extra = []
    for _, r in chosen.iterrows():
        last = pay[pay["employee_id"] == r["employee_id"]]
        if last.empty:
            continue
        row = last.sort_values("pay_period_end").iloc[-1].copy()
        # Anchor the ghost periods on the TERMINATION date, not on the last real
        # period. The last real period usually ends before the leaving date, so
        # shifting from there lands the extra runs on or before it and the defect
        # never actually appears in the data.
        left_on = pd.Timestamp(r["termination_date"]).date()
        for shift in (1, 2):
            new = row.copy()
            new["pay_period_start"] = left_on + dt.timedelta(days=14 * shift - 6)
            new["pay_period_end"] = left_on + dt.timedelta(days=14 * shift + 7)
            new["pay_date"] = left_on + dt.timedelta(days=14 * shift + 12)
            new["bonus_pay"] = 0.0
            new["overtime_pay"] = 0.0
            extra.append(new)
    if not extra:
        return pay
    return pd.concat([pay, pd.DataFrame(extra)], ignore_index=True)
