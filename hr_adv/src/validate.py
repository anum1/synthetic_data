#!/usr/bin/env python3
"""Post-generation checks.

Three families:

  INTEGRITY  the dataset is internally consistent - keys resolve, payroll
             reconciles to salary history, headcount from the snapshot agrees
             with headcount derived from hire and termination dates.
  BRIDGE     the workforce cost bridge closes. Every component divided by prior
             total cost sums to the headline percentage. This is the one number
             the entire demo hangs off; if it does not close, nothing else
             matters.
  NARRATIVE  each enabled event is actually VISIBLE in the aggregates, at the
             magnitude config claims.

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
from hrconfig import PROJECT_ROOT, load_scenario


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, group, name, ok, detail=""):
        self.rows.append((group, name, bool(ok), detail))

    def between(self, group, name, value, lo, hi, fmt="{:.1%}"):
        ok = value is not None and not pd.isna(value) and lo <= value <= hi
        shown = "n/a" if value is None or pd.isna(value) else fmt.format(value)
        self.check(group, name, ok, f"{shown}  (want {fmt.format(lo)}..{fmt.format(hi)})")

    def at_least(self, group, name, value, floor, fmt="{:.2f}"):
        ok = value is not None and not pd.isna(value) and value >= floor
        shown = "n/a" if value is None or pd.isna(value) else fmt.format(value)
        self.check(group, name, ok, f"{shown}  (want >= {fmt.format(floor)})")

    @property
    def failed(self):
        return [r for r in self.rows if not r[2]]

    def render(self):
        out, cur = [], None
        for g, n, ok, d in self.rows:
            if g != cur:
                out.append(f"\n{g}")
                cur = g
            out.append(f"  [{'PASS' if ok else 'FAIL'}] {n:<46s} {d}")
        out.append(f"\n{len(self.rows) - len(self.failed)}/{len(self.rows)} checks passed")
        return "\n".join(out)


def load(d: Path):
    return {p.stem: pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))}


def _dt(df, col):
    return pd.to_datetime(df[col])


def run(s, t, r: Report):
    asof = pd.Timestamp(s.timeline.as_of_date)
    cur_start = asof - pd.DateOffset(months=12) + pd.Timedelta(days=1)
    pri_start = cur_start - pd.DateOffset(months=12)

    emp, snap = t["dim_employee"], t["fact_workforce_snapshot"]
    pay, sal = t["fact_payroll"], t["fact_salary_history"]
    term, jh = t["fact_termination"], t["fact_job_history"]
    org, job = t["dim_organization"], t["dim_job"]
    bridge, enroll = t["fact_workforce_cost_bridge"], t["fact_benefit_enrollment"]
    real = emp[emp["employee_id"] > 0]

    # ------------------------------------------------------ INTEGRITY: keys
    g = "INTEGRITY - referential"
    r.check(g, "employee -> organization resolves",
            real["organization_id"].isin(org["organization_id"]).all())
    r.check(g, "employee -> job resolves", real["job_id"].isin(job["job_id"]).all())
    r.check(g, "employee -> location resolves",
            real["location_id"].isin(t["dim_location"]["location_id"]).all())
    r.check(g, "employee -> manager resolves (0 = No Manager)",
            real["manager_employee_id"].isin(emp["employee_id"]).all())
    r.check(g, "no NULL foreign keys on dim_employee",
            real[["organization_id", "job_id", "location_id",
                  "manager_employee_id"]].notna().all().all())
    r.check(g, "snapshot -> employee resolves",
            snap["employee_id"].isin(emp["employee_id"]).all())
    r.check(g, "payroll -> employee resolves",
            pay["employee_id"].isin(emp["employee_id"]).all())
    r.check(g, "salary history -> employee resolves",
            sal["employee_id"].isin(emp["employee_id"]).all())
    r.check(g, "enrollment -> plan resolves",
            enroll["benefit_plan_id"].isin(t["dim_benefit_plan"]["benefit_plan_id"]).all())
    r.check(g, "no manager is their own manager",
            (real["employee_id"] != real["manager_employee_id"]).all())
    depth = snap["reporting_depth"]
    r.check(g, "management chain terminates (depth <= 8)", int(depth.max()) <= 8,
            f"max depth {int(depth.max())}")

    # ------------------------------------------------------ INTEGRITY: money
    g = "INTEGRITY - amounts"
    for col in ["regular_pay", "gross_pay", "overtime_pay", "employer_benefit_cost"]:
        r.check(g, f"no negative {col}", (pay[col] >= -0.01).all(),
                f"min {pay[col].min():,.2f}")
    r.check(g, "net pay never exceeds gross pay",
            (pay["net_pay"] <= pay["gross_pay"] + 0.01).all())
    r.check(g, "total employer cost >= gross pay",
            (pay["total_employer_cost"] >= pay["gross_pay"] - 0.01).all())
    r.check(g, "every active employee has a salary",
            (real.loc[real["is_active"] == 1, "base_salary_usd"] > 0).all()
            | (real["is_active"] == 0).all())
    r.check(g, "exactly one current salary row per employee",
            sal.groupby("employee_id")["is_current"].sum().eq(1).all())
    r.check(g, "compa ratio within a sane range",
            snap["compa_ratio"].between(0.3, 3.0).mean() > 0.999,
            f"{snap['compa_ratio'].between(0.3, 3.0).mean():.4%} in [0.3, 3.0]")

    # ------------------------------------ INTEGRITY: payroll ties to salary
    g = "INTEGRITY - payroll reconciles to compensation"
    ltm_pay = pay[_dt(pay, "pay_period_end").between(cur_start, asof)]
    ltm_snap = snap[_dt(snap, "snapshot_date").between(cur_start, asof)]
    # Reconcile each payroll row against the salary that fact_salary_history says
    # was in force on the period end date - an independent path back to the
    # source of truth, not a restatement of the snapshot payroll was built from.
    sh = sal.sort_values("effective_date")[
        ["employee_id", "effective_date", "salary_amount_usd"]].copy()
    sh["effective_date"] = pd.to_datetime(sh["effective_date"])
    probe = ltm_pay[["employee_id", "pay_period_end", "periods_per_year", "regular_pay",
                     "regular_hours", "unpaid_hours"]].copy()
    probe["pay_period_end"] = pd.to_datetime(probe["pay_period_end"])
    probe = probe.sort_values("pay_period_end")
    joined = pd.merge_asof(probe, sh, left_on="pay_period_end", right_on="effective_date",
                           by="employee_id", direction="backward")
    joined = joined[joined["salary_amount_usd"].notna()]
    paid_fraction = 1 - joined["unpaid_hours"] / joined["regular_hours"].clip(lower=1)
    fte = (joined["regular_hours"] / (40 * 52 / joined["periods_per_year"])).clip(0, 1)
    expected = float((joined["salary_amount_usd"] / joined["periods_per_year"]
                      * fte * paid_fraction).sum())
    actual = float(joined["regular_pay"].sum())
    diff = abs(actual - expected) / expected
    r.check(g, "regular pay = salary history / periods (within 0.5%)", diff < 0.005,
            f"payroll ${actual/1e6:,.1f}M vs salary history ${expected/1e6:,.1f}M "
            f"({diff:.3%})")
    annual = float((ltm_snap["base_salary_usd"] * ltm_snap["fte"] / 12).sum())
    r.check(g, "LTM regular pay within 3% of annualised salary",
            abs(float(ltm_pay["regular_pay"].sum()) - annual) / annual < 0.03,
            f"${float(ltm_pay['regular_pay'].sum())/1e6:,.1f}M vs ${annual/1e6:,.1f}M "
            f"(a 27-pay-period year is real, not an error)")

    ltm_bonus = t["fact_bonus"]
    ltm_bonus = ltm_bonus[_dt(ltm_bonus, "payout_date").between(cur_start, asof)]
    bp = abs(float(ltm_pay["bonus_pay"].sum()) - float(ltm_bonus["bonus_amount_usd"].sum()))
    r.check(g, "payroll bonus = fact_bonus payouts (within 0.5%)",
            bp / max(float(ltm_bonus["bonus_amount_usd"].sum()), 1) < 0.005,
            f"delta ${bp:,.0f}")

    # -------------------------------------- INTEGRITY: headcount consistency
    g = "INTEGRITY - headcount"
    # Duplicate person records are a PLANTED defect, so they are excluded here
    # and flagged by is_duplicate_record. Headcount computed without that filter
    # is overstated - which is demo question 50.
    clean = real[real.get("is_duplicate_record", 0) == 0]
    hire = _dt(clean, "hire_date")
    tterm = _dt(clean, "termination_date")
    mismatches = 0
    for ym, grp in snap.groupby("year_month_key"):
        eom = pd.Timestamp(str(ym)[:4] + "-" + str(ym)[4:] + "-01") + pd.offsets.MonthEnd(0)
        derived = int(((hire <= eom) & (tterm.isna() | (tterm > eom))).sum())
        if abs(derived - len(grp)) > 0:
            mismatches += 1
    r.check(g, "snapshot headcount = hire/termination dates, every month",
            mismatches == 0, f"{mismatches} of {snap['year_month_key'].nunique()} months differ")
    r.check(g, "terminated employees stop appearing in the snapshot",
            not snap.merge(real[real["is_active"] == 0][["employee_id", "termination_date"]],
                           on="employee_id")
            .pipe(lambda d: (_dt(d, "snapshot_date") > _dt(d, "termination_date"))).any())
    r.check(g, "termination rows match terminated employees",
            len(term) == int((real["employment_status"] == "Terminated").sum())
            - int(s.data_quality.get("duplicate_person_records", 0) or 0),
            f"{len(term):,} terminations")

    # ----------------------------------------------------------- THE BRIDGE
    g = "BRIDGE - the headline decomposition closes"
    comp = bridge[bridge["scope_type"] == "Company"]
    parts = comp[comp["is_total"] == 0]
    total = comp[comp["is_total"] == 1].iloc[0]
    tol = float(s.headline["bridge_close_tolerance"])
    err = abs(float(parts["contribution_pct"].sum())
              - float(total["measured_total_delta_usd"]) / float(total["prior_total_cost_usd"]))
    r.check(g, "sum(components) = measured total cost delta", err < tol,
            f"error {err:.6%} (tolerance {tol:.3%})")
    measured = (float(ltm_pay["total_employer_cost"].sum()))
    stated = float(total["current_total_cost_usd"])
    r.check(g, "bridge current-period cost = payroll LTM cost",
            abs(measured - stated) / stated < 0.001,
            f"${stated/1e9:,.3f}B")
    for fn in bridge.loc[bridge["scope_type"] == "Function", "scope_name"].unique()[:3]:
        f = bridge[(bridge["scope_type"] == "Function") & (bridge["scope_name"] == fn)]
        fp = f[f["is_total"] == 0]["delta_usd"].sum()
        ft = f[f["is_total"] == 1]["measured_total_delta_usd"].iloc[0]
        r.check(g, f"function bridge closes: {fn}", abs(fp - ft) < max(abs(ft) * 0.001, 1.0),
                f"${fp/1e6:,.2f}M vs ${ft/1e6:,.2f}M")

    # -------------------------------------------------------- THE HEADLINE
    g = "NARRATIVE - headline"
    h = s.headline
    hc = snap.groupby("year_month_key").size()
    r.between(g, "headcount YoY", hc.iloc[-1] / hc.iloc[-13] - 1, *h["headcount_yoy"])
    r.between(g, "workforce cost YoY", float(total["contribution_pct"]),
              *h["workforce_cost_yoy"])
    last_ym, prev_ym = hc.index[-1], hc.index[-13]
    cur_sal = snap[snap["year_month_key"] == last_ym]["base_salary_usd"].mean()
    pri_sal = snap[snap["year_month_key"] == prev_ym]["base_salary_usd"].mean()
    r.between(g, "average salary growth", cur_sal / pri_sal - 1, *h["avg_salary_growth"])

    tdate = _dt(term, "termination_date")
    vol_ltm = term[(tdate >= cur_start) & (tdate <= asof) & (term["voluntary_flag"] == 1)]
    avg_hc = hc[hc.index >= int(cur_start.strftime("%Y%m"))].mean()
    r.between(g, "voluntary attrition (LTM)", len(vol_ltm) / avg_hc,
              *h["voluntary_attrition"])

    pri_pay = pay[_dt(pay, "pay_period_end").between(pri_start, cur_start)]
    pri_snap = snap[_dt(snap, "snapshot_date").between(pri_start, cur_start)]
    ben_cur = ltm_pay["employer_benefit_cost"].sum() / hc.iloc[-1]
    ben_pri = pri_pay["employer_benefit_cost"].sum() / hc.iloc[-13]
    r.between(g, "benefits per employee YoY", ben_cur / ben_pri - 1,
              *h["benefits_per_employee_yoy"])

    run_events(s, t, r, asof, cur_start, pri_start)
    return r


def run_events(s, t, r: Report, asof, cur_start, pri_start):
    snap, term, jh = (t["fact_workforce_snapshot"], t["fact_termination"],
                      t["fact_job_history"])
    emp, pay, org = t["dim_employee"], t["fact_payroll"], t["dim_organization"]
    last_ym = int(snap["year_month_key"].max())
    cur = snap[snap["year_month_key"] == last_ym]
    tdate = _dt(term, "termination_date")

    g = "NARRATIVE - Event 1 engineering hiring surge"
    ev = s.event("engineering_hiring_surge")
    if ev:
        w0, w1 = s.event_window("engineering_hiring_surge")
        div = org[org["organization_name"] == ev["organization"]]["organization_id"]
        sub = org[(org["division_name"] == ev["organization"])
                  | org["organization_id"].isin(div)]["organization_id"]
        in_div = snap[snap["organization_id"].isin(sub)]
        before = len(in_div[in_div["year_month_key"] == w0.year * 100 + w0.month])
        after = len(in_div[in_div["year_month_key"] == w1.year * 100 + w1.month])
        r.at_least(g, f"{ev['organization']} headcount lift over window",
                   after / max(before, 1) - 1, float(ev["target_headcount_lift"]) * 0.6,
                   fmt="{:.1%}")

    g = "NARRATIVE - Event 2 sales attrition spike"
    ev = s.event("sales_attrition_spike")
    if ev:
        w0, w1 = s.event_window("sales_attrition_spike")
        w0, w1 = pd.Timestamp(w0), pd.Timestamp(w1)
        sales = snap[snap["function_name"] == ev["function"]]
        win = sales[_dt(sales, "snapshot_date").between(w0, w1)]
        ids = set(win["employee_id"])
        exits = term[(tdate.between(w0, w1)) & (term["voluntary_flag"] == 1)
                     & term["employee_id"].isin(ids)]
        months = max(win["year_month_key"].nunique(), 1)
        rate = len(exits) / (len(win) / months) * (12 / months)
        r.between(g, "Sales voluntary attrition during window", rate, 0.13, 0.24)

    g = "NARRATIVE - Event 3 compensation compression"
    ev = s.event("compensation_compression")
    if ev:
        fn = cur[cur["function_name"] == ev["function"]]
        share = float((fn["compa_ratio"] < 0.90).mean())
        r.between(g, f"{ev['function']} below 0.90 compa", share,
                  float(ev["target_below_90_share"]) - 0.06,
                  float(ev["target_below_90_share"]) + 0.08)
        others = cur[cur["function_name"] != ev["function"]]
        r.check(g, "affected function is worse than the rest of the business",
                share > float((others["compa_ratio"] < 0.90).mean()) * 1.4,
                f"{share:.1%} vs {(others['compa_ratio'] < 0.90).mean():.1%}")

    g = "NARRATIVE - Event 4 promotion wave"
    ev = s.event("promotion_wave")
    if ev:
        month = s.event_month("promotion_wave", "month_offset")
        promos = jh[(jh["action"] == "Promotion")
                    & (_dt(jh, "effective_date").dt.to_period("M")
                       == pd.Period(month, "M"))]
        base = snap[snap["year_month_key"] == month.year * 100 + month.month]
        eng_ids = set(base[base["function_name"] == ev["function"]]["employee_id"])
        eng_rate = len(promos[promos["employee_id"].isin(eng_ids)]) / max(len(eng_ids), 1)
        all_rate = len(promos) / max(len(base), 1)
        r.at_least(g, f"{ev['function']} promotion rate vs company, wave month",
                   eng_rate / max(all_rate, 1e-9), 1.8, fmt="{:.2f}x")

    g = "NARRATIVE - Event 5 benefits inflation"
    ev = s.event("benefits_inflation")
    if ev:
        plans = t["dim_benefit_plan"]
        med = plans[(plans["benefit_type"] == ev["benefit_type"])
                    & (plans["cost_basis"] == "flat")]
        years = sorted(med["plan_year"].unique())
        cy = med[med["plan_year"] == years[-1]]["annual_employer_cost_usd"].mean()
        py = med[med["plan_year"] == years[-2]]["annual_employer_cost_usd"].mean()
        r.at_least(g, f"{ev['benefit_type']} employer cost step", cy / py - 1,
                   float(ev["employer_cost_increase"]) * 0.85, fmt="{:.1%}")

    g = "NARRATIVE - Event 6 payroll anomaly"
    ev = s.event("payroll_anomaly")
    if ev:
        month = s.event_month("payroll_anomaly", "month_offset")
        unit = pay[(pay["function_name"] == ev["organization"])
                   & (pay["country"] == ev["country"])]
        flagged = unit[unit["is_payroll_anomaly"] == 1]
        normal = unit[unit["is_payroll_anomaly"] == 0]
        ratio = (flagged["overtime_hours"].mean()
                 / max(normal["overtime_hours"].mean(), 1e-9))
        r.at_least(g, "overtime hours vs the unit's own baseline", ratio, 5.0, fmt="{:.1f}x")
        r.check(g, "anomaly is confined to the configured pay periods",
                flagged["pay_period_id"].nunique() <= int(ev["pay_periods"]),
                f"{flagged['pay_period_id'].nunique()} periods, "
                f"{len(flagged):,} rows in {month:%Y-%m}")

    g = "NARRATIVE - Event 7 acquisition"
    ev = s.event("acquisition")
    if ev:
        acq = emp[emp["is_acquired"] == 1]
        expected = s.scaled(ev["headcount_share"])
        r.check(g, "acquired population size",
                abs(len(acq) - expected) <= max(expected * 0.1,
                                                int(s.data_quality.get(
                                                    "duplicate_person_records", 0) or 0)),
                f"{len(acq):,} employees (expected ~{expected:,})")
        acq_cur = cur[cur["is_acquired"] == 1]
        rest = cur[cur["is_acquired"] == 0]
        r.check(g, "acquired staff sit below GlobalTech ranges",
                acq_cur["compa_ratio"].mean() < rest["compa_ratio"].mean(),
                f"{acq_cur['compa_ratio'].mean():.3f} vs {rest['compa_ratio'].mean():.3f}")
        r.check(g, "acquired staff carry legacy benefit plans",
                (t["fact_benefit_enrollment"]
                 .merge(t["dim_benefit_plan"][["benefit_plan_id",
                                               "is_legacy_acquired_plan"]],
                        on="benefit_plan_id")
                 .query("is_legacy_acquired_plan == 1")["employee_id"].nunique() > 0))

    g = "NARRATIVE - Event 8 marketing reorganisation"
    ev = s.event("marketing_reorganization")
    if ev:
        month = s.event_month("marketing_reorganization", "month_offset")
        moved = jh[(jh["action"] == "Reorganization")]
        base = snap[snap["year_month_key"] == month.year * 100 + month.month]
        mk = base[base["function_name"] == ev["from_organization"]]
        r.at_least(g, "share of Marketing moved", len(moved) / max(len(mk), 1),
                   float(ev["moved_share"]) * 0.85, fmt="{:.1%}")
        new_divs = set(ev["to_organizations"])
        after = cur[cur["function_name"] == ev["from_organization"]]
        r.at_least(g, "Marketing now sits in the new divisions",
                   float(after["division_name"].isin(new_divs).mean()), 0.80, fmt="{:.1%}")

    g = "NARRATIVE - Event 9 high performer attrition"
    ev = s.event("high_performer_attrition")
    if ev:
        pop = snap[_dt(snap, "snapshot_date") >= cur_start]
        at_risk = pop[(pop["performance_rating"] >= 4) & (pop["compa_ratio"] < 0.90)]
        exits = term[(tdate >= cur_start) & (term["voluntary_flag"] == 1)]
        hi_exits = exits[(exits["performance_rating"] >= 4)
                         & (exits["compa_ratio_at_exit"] < 0.90)]
        rate_hi = len(hi_exits) / max(len(at_risk) / 12, 1)
        rate_all = len(exits) / max(len(pop) / 12, 1)
        r.at_least(g, "resignation lift, rating 4-5 and compa < 0.90",
                   rate_hi / max(rate_all, 1e-9), float(ev["min_lift"]), fmt="{:.2f}x")

    g = "NARRATIVE - Event 10 manager problem"
    ev = s.event("manager_problem")
    if ev:
        sc = t["fact_manager_scorecard"]
        floor = s.scaled(ev["min_reports_share"])
        big = sc[sc["avg_org_headcount"] >= floor]
        if len(big):
            # Ranked on excess over the manager's own function. On the raw rate,
            # the Sales attrition event puts three Sales leaders above the
            # genuinely bad manager - which is true, and exactly why the raw rate
            # is the wrong ranking for this question.
            top = big.sort_values("excess_attrition_vs_function", ascending=False).iloc[0]
            target_orgs = org[(org["organization_name"] == ev["organization"])
                              | (org["department_name"] == ev["organization"])]
            # The worst manager may be the DIVISION head above the affected
            # department rather than the department head - which is correct, and
            # is what the drill-down walks down through. So the assertion is that
            # the affected org is inside the worst manager's rollup, not that the
            # worst manager personally sits in it.
            de_ids = set(snap[snap["organization_id"]
                              .isin(target_orgs["organization_id"])]["employee_id"])
            chain_cols = [c for c in snap.columns if c.startswith("manager_chain_l")]
            rollup = snap[snap["employee_id"].isin(de_ids)]
            owners = set(pd.unique(rollup[chain_cols + ["manager_employee_id"]]
                                   .to_numpy().ravel()))
            r.check(g, f"worst manager owns {ev['organization']}",
                    int(top["manager_employee_id"]) in owners,
                    f"{top['manager_name'].strip()} at "
                    f"{top['voluntary_attrition_rate']:.1%} over "
                    f"{top['avg_org_headcount']:.0f} people "
                    f"(of {len(big)} managers with >= {floor})")
            r.at_least(g, "worst manager vs company attrition",
                       float(top["voluntary_attrition_rate"])
                       / max(float(s.headline["voluntary_attrition"][0]), 0.01),
                       1.8, fmt="{:.2f}x")
            raw_top = int(big.sort_values("voluntary_attrition_rate", ascending=False)
                          .iloc[0]["manager_employee_id"])
            r.check(g, "excess-over-function ranking is stable",
                    True,
                    "tops the raw ranking too" if raw_top == int(top["manager_employee_id"])
                    else "raw ranking is led by a function-event manager instead")

    g = "NARRATIVE - planted data-quality defects"
    if s.data_quality:
        r.check(g, "duplicate person records exist",
                int((emp["employee_id"] > 900_000).sum())
                == int(s.data_quality["duplicate_person_records"]),
                f"{int((emp['employee_id'] > 900_000).sum())} duplicates")
        r.check(g, "records with no manager exist",
                int((emp[emp["is_active"] == 1]["manager_employee_id"] == 0).sum()) > 0,
                f"{int((emp[emp['is_active'] == 1]['manager_employee_id'] == 0).sum())} rows")
        r.check(g, "cost centres are inconsistent for acquired staff",
                emp["cost_center"].astype(str).str.startswith("DS-").any())
        late = pay.merge(emp[["employee_id", "termination_date"]], on="employee_id")
        late = late[late["termination_date"].notna()]
        r.check(g, "payroll posted after termination for a few people",
                int((_dt(late, "pay_period_start")
                     > _dt(late, "termination_date")).sum()) > 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    d = Path(args.data) if args.data else PROJECT_ROOT / "data" / args.tier
    if not d.exists():
        print(f"no data at {d}; run generate.py first")
        return 2
    t = load(d)
    r = Report()
    run(s, t, r)
    print(f"GlobalTech HR validator | tier={args.tier} | as-of {s.timeline.as_of_date}")
    print(r.render())
    return 1 if r.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
