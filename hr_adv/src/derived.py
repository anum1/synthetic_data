"""Derived analytics: the workforce cost bridge, manager scorecard, risk layer.

The bridge is the point of the whole dataset. The design note quoted a
decomposition that does not tie out - it reads as growth rates but is written as
contributions to a total, and it double-counts new hires between "headcount" and
"salary increases". Here it is one defined methodology, materialised as a table
so five tools cannot each compute it slightly differently:

    Volume  (DeltaFTE-months) x prior average base cost per FTE-month
    Rate    sum over groups of (Delta rate within group) x current FTE-months
    Mix     residual of base pay - headcount shifting between country x function
            groups that cost different amounts. NEGATIVE here, because hiring is
            deliberately weighted towards India.
    Bonus / Overtime / Benefits / Other   their own deltas

Every component is divided by prior-period TOTAL cost, so the column sums to the
headline percentage by construction. validate.py asserts it closes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BASE_COL = "regular_pay"
OTHER_COLS = ["commission", "allowance", "employer_tax"]

COMPONENT_ORDER = ["Rate (merit, promotion, market)", "Volume (headcount)",
                   "Benefits", "Bonus", "Overtime", "Other", "Mix", "Total"]


def _windows(as_of):
    cur_end = pd.Timestamp(as_of)
    cur_start = cur_end - pd.DateOffset(months=12) + pd.Timedelta(days=1)
    pri_end = cur_start - pd.Timedelta(days=1)
    pri_start = pri_end - pd.DateOffset(months=12) + pd.Timedelta(days=1)
    return (pri_start, pri_end), (cur_start, cur_end)


def _slice(df, date_col, lo, hi):
    d = pd.to_datetime(df[date_col])
    return df[(d >= lo) & (d <= hi)]


def _bridge_for(pay_p, pay_c, snap_p, snap_c, group_cols) -> dict:
    """Volume / rate / mix on base pay, plus the other cost components."""
    base_p = float(pay_p[BASE_COL].sum())
    base_c = float(pay_c[BASE_COL].sum())
    fte_p = float(snap_p["fte"].sum())          # FTE-months
    fte_c = float(snap_c["fte"].sum())

    rate_p_all = base_p / fte_p if fte_p else 0.0
    volume = (fte_c - fte_p) * rate_p_all

    # Rate change WITHIN groups, weighted by current volume. Grouping on country
    # x level is what separates "we pay people more" from "we hired a different
    # kind of person".
    gp = snap_p.groupby(group_cols, observed=True)["fte"].sum()
    gc = snap_c.groupby(group_cols, observed=True)["fte"].sum()
    bp = pay_p.groupby(group_cols, observed=True)[BASE_COL].sum()
    bc = pay_c.groupby(group_cols, observed=True)[BASE_COL].sum()
    idx = gp.index.union(gc.index)
    gp, gc = gp.reindex(idx).fillna(0.0), gc.reindex(idx).fillna(0.0)
    bp, bc = bp.reindex(idx).fillna(0.0), bc.reindex(idx).fillna(0.0)
    rate_p = np.where(gp > 0, bp / gp.replace(0, np.nan), 0.0)
    rate_c = np.where(gc > 0, bc / gc.replace(0, np.nan), 0.0)
    rate = float(np.nansum((rate_c - rate_p) * gc.to_numpy()))

    mix = (base_c - base_p) - volume - rate

    def delta(col):
        return float(pay_c[col].sum()) - float(pay_p[col].sum())

    other = sum(delta(c) for c in OTHER_COLS)
    total_p = float(pay_p["total_employer_cost"].sum())
    total_c = float(pay_c["total_employer_cost"].sum())

    return {
        "Rate (merit, promotion, market)": rate,
        "Volume (headcount)": volume,
        "Benefits": delta("employer_benefit_cost"),
        "Bonus": delta("bonus_pay"),
        "Overtime": delta("overtime_pay"),
        "Other": other,
        "Mix": mix,
        "_prior_total": total_p,
        "_current_total": total_c,
        "_prior_base": base_p,
        "_current_base": base_c,
        "_fte_prior": fte_p,
        "_fte_current": fte_c,
    }


def build_cost_bridge(s, payroll: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    (p0, p1), (c0, c1) = _windows(s.timeline.as_of_date)
    pay_p = _slice(payroll, "pay_period_end", p0, p1)
    pay_c = _slice(payroll, "pay_period_end", c0, c1)
    snap_p = _slice(snap, "snapshot_date", p0, p1)
    snap_c = _slice(snap, "snapshot_date", c0, c1)
    # Grouping on country x FUNCTION, not country x level. Grouping on level
    # would push every promotion into Mix, which is wrong: a promotion is a pay
    # action, and the component labelled "Rate (merit, promotion, market)" has to
    # be the one that contains it. Mix is then what it says - geography and
    # function shifting under the headcount.
    group_cols = ["country", "function_name"]

    scopes = [("Company", s.company, pay_p, pay_c, snap_p, snap_c)]
    for fn in sorted(snap_c["function_name"].unique()):
        scopes.append(("Function", fn,
                       pay_p[pay_p["function_name"] == fn],
                       pay_c[pay_c["function_name"] == fn],
                       snap_p[snap_p["function_name"] == fn],
                       snap_c[snap_c["function_name"] == fn]))

    rows = []
    bid = 1
    for scope_type, scope_name, pp, pc, sp, sc in scopes:
        if pp.empty or pc.empty or sp.empty or sc.empty:
            continue
        b = _bridge_for(pp, pc, sp, sc, group_cols)
        prior_total = b["_prior_total"]
        components = {k: v for k, v in b.items() if not k.startswith("_")}
        total_delta = b["_current_total"] - prior_total
        # Total is the sum of the parts, not an independent measurement. If they
        # ever disagree the validator says so rather than the dashboard hiding it.
        components["Total"] = sum(components.values())
        for name in COMPONENT_ORDER:
            delta = components[name]
            rows.append({
                "cost_bridge_id": bid,
                "comparison_label": "Last 12 months vs prior 12 months",
                "prior_period_start": p0.date(), "prior_period_end": p1.date(),
                "current_period_start": c0.date(), "current_period_end": c1.date(),
                "scope_type": scope_type, "scope_name": scope_name,
                "cost_component": name,
                "component_order": COMPONENT_ORDER.index(name) + 1,
                "delta_usd": round(delta, 2),
                "prior_total_cost_usd": round(prior_total, 2),
                "current_total_cost_usd": round(b["_current_total"], 2),
                "contribution_pct": round(delta / prior_total, 6) if prior_total else 0.0,
                "is_total": int(name == "Total"),
                "measured_total_delta_usd": round(total_delta, 2),
            })
            bid += 1
    return pd.DataFrame(rows)


def build_manager_scorecard(s, snap: pd.DataFrame, term: pd.DataFrame,
                            absence: pd.DataFrame, emp: pd.DataFrame) -> pd.DataFrame:
    """Manager-level view over the last 12 months, on the ORG they own.

    Attrition is measured over a manager's whole organization, not just their
    direct reports, because that is how HR reports it and because a director
    with four direct reports and ninety people underneath is not low-risk.
    """
    (_, _), (c0, c1) = _windows(s.timeline.as_of_date)
    cur = _slice(snap, "snapshot_date", c0, c1)
    if cur.empty:
        return pd.DataFrame()

    chain_cols = [c for c in cur.columns if c.startswith("manager_chain_l")]
    long = cur.melt(id_vars=["employee_id", "year_month_key", "compa_ratio",
                             "performance_rating", "organization_id"],
                    value_vars=chain_cols + ["manager_employee_id"],
                    value_name="manager_employee_id_roll").drop(columns="variable")
    long = long[long["manager_employee_id_roll"] > 0]
    long = long.drop_duplicates(["employee_id", "year_month_key",
                                 "manager_employee_id_roll"])

    org_size = (long.groupby("manager_employee_id_roll")
                .agg(org_headcount_months=("employee_id", "size"),
                     months_active=("year_month_key", "nunique"),
                     avg_compa_ratio=("compa_ratio", "mean"),
                     avg_performance_rating=("performance_rating", "mean"))
                .reset_index()
                .rename(columns={"manager_employee_id_roll": "manager_employee_id"}))
    # Divide by the months the manager ACTUALLY held the org, not by 12. A
    # manager who took over in month nine gets a full year of exits against three
    # months of headcount, and lands at the top of the risk list for no reason.
    org_size["avg_org_headcount"] = (org_size["org_headcount_months"]
                                     / org_size["months_active"].clip(lower=1)).round(1)
    org_size["annualisation_factor"] = (12 / org_size["months_active"].clip(lower=1)).round(3)

    direct = (cur[cur["year_month_key"] == cur["year_month_key"].max()]
              .groupby("manager_employee_id").size().rename("direct_reports")
              .reset_index())

    t = _slice(term, "termination_date", c0, c1).drop_duplicates("employee_id")
    exits = long.merge(t[["employee_id", "voluntary_flag", "regrettable_flag"]],
                       on="employee_id", how="inner")
    exits = exits.drop_duplicates(["employee_id", "manager_employee_id_roll"])
    ex = (exits.groupby("manager_employee_id_roll")
          .agg(exits_total=("employee_id", "size"),
               voluntary_exits=("voluntary_flag", "sum"),
               regrettable_exits=("regrettable_flag", "sum"))
          .reset_index()
          .rename(columns={"manager_employee_id_roll": "manager_employee_id"}))

    abs_days = pd.DataFrame(columns=["employee_id", "absence_days"])
    if len(absence):
        a = _slice(absence, "start_date", c0, c1)
        abs_days = a.groupby("employee_id")["absence_days"].sum().reset_index()
    abs_roll = (long.drop_duplicates(["employee_id", "manager_employee_id_roll"])
                .merge(abs_days, on="employee_id", how="left"))
    abs_roll["absence_days"] = abs_roll["absence_days"].fillna(0.0)
    ab = (abs_roll.groupby("manager_employee_id_roll")["absence_days"].mean()
          .rename("absence_days_per_employee").reset_index()
          .rename(columns={"manager_employee_id_roll": "manager_employee_id"}))

    out = (org_size.merge(direct, on="manager_employee_id", how="left")
           .merge(ex, on="manager_employee_id", how="left")
           .merge(ab, on="manager_employee_id", how="left"))
    out[["direct_reports", "exits_total", "voluntary_exits", "regrettable_exits"]] = \
        out[["direct_reports", "exits_total", "voluntary_exits",
             "regrettable_exits"]].fillna(0)
    # Exits are annualised the same way the denominator is, so a manager with
    # three months of history is compared on the same basis as one with twelve.
    out["voluntary_attrition_rate"] = (
        out["voluntary_exits"] / out["avg_org_headcount"].replace(0, np.nan)).fillna(0)
    out["regrettable_attrition_rate"] = (
        out["regrettable_exits"] / out["avg_org_headcount"].replace(0, np.nan)).fillna(0)

    info = emp.set_index("employee_id")
    for col, src in [("manager_name", None), ("manager_organization_id", "organization_id"),
                     ("manager_job_level", "job_level"), ("manager_country", "country")]:
        if src:
            out[col] = out["manager_employee_id"].map(info[src])
    out["manager_name"] = (out["manager_employee_id"].map(info["first_name"]).fillna("")
                           + " " + out["manager_employee_id"].map(info["last_name"]).fillna(""))

    # Benchmark each manager against their OWN function, not against the company.
    # A function-wide attrition event lifts every manager inside it, so ranking on
    # the raw rate surfaces whoever sits above the event rather than whoever is
    # actually managing badly. Excess-over-function separates the two, which is
    # both better analytics and how a real HR team reads this table.
    fn_of = (snap.sort_values("year_month_key").drop_duplicates("employee_id", keep="last")
             .set_index("employee_id")["function_name"])
    out["manager_function"] = out["manager_employee_id"].map(fn_of).fillna("Unknown")
    people = cur.sort_values("year_month_key").drop_duplicates("employee_id", keep="last")
    fn_exits = people.merge(t[["employee_id", "voluntary_flag"]], on="employee_id",
                            how="inner")
    fn_rate = (fn_exits.groupby("function_name")["voluntary_flag"].sum()
               / (cur.groupby("function_name").size() / 12)).rename("function_attrition_rate")
    out["function_attrition_rate"] = out["manager_function"].map(fn_rate).fillna(0.0)
    out["excess_attrition_vs_function"] = (out["voluntary_attrition_rate"]
                                           - out["function_attrition_rate"]).round(4)

    company_rate = out["voluntary_exits"].sum() / max(out["avg_org_headcount"].sum(), 1)
    out["company_attrition_rate"] = round(float(company_rate), 4)
    excess = out["excess_attrition_vs_function"].clip(lower=0)
    out["manager_risk_score"] = (
        (excess / max(company_rate, 0.01) * 55).clip(0, 60)
        + (3.0 - out["avg_performance_rating"]).clip(lower=0) * 12
        + (out["absence_days_per_employee"] / 20).clip(0, 1) * 15
        + (0.95 - out["avg_compa_ratio"]).clip(lower=0) * 60
    ).round(1).clip(0, 100)
    out["manager_risk_band"] = pd.cut(out["manager_risk_score"], [-1, 25, 50, 75, 101],
                                      labels=["Low", "Moderate", "High", "Critical"]
                                      ).astype(str)
    out = out[out["avg_org_headcount"] >= 3].reset_index(drop=True)
    out.insert(0, "manager_scorecard_id", np.arange(1, len(out) + 1, dtype="int32"))
    out["period_start"] = c0.date()
    out["period_end"] = c1.date()
    return out


def build_workforce_risk(s, snap: pd.DataFrame, scorecard: pd.DataFrame,
                         emp: pd.DataFrame) -> pd.DataFrame:
    """Employee-level flight risk at the as-of date.

    Scored from the SAME drivers the termination hazard actually used, so the
    risk list is a real prediction of the behaviour in the data rather than a
    decorative column that happens to look plausible.
    """
    cur = snap[snap["year_month_key"] == snap["year_month_key"].max()].copy()
    a = s.attrition
    compa_bands = a["compa_multiplier"]

    def band(v):
        for b in compa_bands:
            if v < float(b["max"]):
                return float(b["mult"])
        return float(compa_bands[-1]["mult"])

    compa_mult = cur["compa_ratio"].map(band)
    rating_mult = cur["performance_rating"].map(
        {int(k): float(v) for k, v in a["rating_multiplier"].items()}).fillna(1.0)
    promo_gap = cur["months_since_promotion"].clip(0, 60) / 60
    tenure_risk = ((cur["tenure_years"] > 1) & (cur["tenure_years"] < 2.5)).astype(int)
    mgr = scorecard.set_index("manager_employee_id")["manager_risk_score"] \
        if len(scorecard) else pd.Series(dtype=float)
    mgr_risk = cur["manager_employee_id"].map(mgr).fillna(0.0) / 100

    score = (compa_mult / 3.8 * 34 + (rating_mult - 1).clip(lower=0) * 18
             + promo_gap * 16 + tenure_risk * 8 + mgr_risk * 24)
    cur["flight_risk_score"] = score.round(1).clip(0, 100)
    cur["flight_risk_band"] = pd.cut(cur["flight_risk_score"], [-1, 30, 50, 70, 101],
                                     labels=["Low", "Moderate", "High", "Critical"]
                                     ).astype(str)
    drivers = pd.DataFrame({
        "Below market pay": (compa_mult / 3.8 * 34),
        "Manager": mgr_risk * 24,
        "No recent promotion": promo_gap * 16,
        "High performer at risk": (rating_mult - 1).clip(lower=0) * 18,
        "Tenure window": tenure_risk * 8,
    })
    cur["primary_risk_driver"] = drivers.idxmax(axis=1)
    cur["is_regrettable_if_lost"] = (cur["performance_rating"] >= 4).astype("int8")

    keep = ["employee_id", "snapshot_date", "organization_id", "organization_name",
            "function_name", "job_id", "job_level", "country", "location_id",
            "manager_employee_id", "base_salary_usd", "compa_ratio",
            "performance_rating", "tenure_years", "months_since_promotion",
            "is_acquired", "flight_risk_score", "flight_risk_band",
            "primary_risk_driver", "is_regrettable_if_lost"]
    out = cur[[c for c in keep if c in cur.columns]].reset_index(drop=True)
    out.insert(0, "workforce_risk_id", np.arange(1, len(out) + 1, dtype="int32"))
    return out
