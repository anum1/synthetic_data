"""Organization hierarchy and location dimension.

The hierarchy is emitted BOTH ways: `parent_organization_id` for anyone who
wants to walk it, and path-enumerated `org_level_1..6` columns for everyone
else. The flattened columns are not a convenience - Tableau, Power BI and most
NLQ layers cannot do a recursive CTE, and the org drill-down is the best part of
this demo. Same treatment is applied to the management chain in snapshots.py.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R

ORG_TYPES = ["Company", "Business Unit", "Function", "Division", "Department", "Team"]


def build_dim_organization(s, rng: np.random.Generator) -> pd.DataFrame:
    target = int(s.sizes["organizations"])
    start = s.timeline.start_date
    rows: list[dict] = []
    next_id = 1
    cc_counter = 4100

    def add(name, org_type, parent_id, levels, effective, cost_center):
        nonlocal next_id
        padded = list(levels) + [levels[-1]] * (6 - len(levels))
        rows.append({
            "organization_id": next_id,
            "organization_code": f"ORG{next_id:05d}",
            "organization_name": name,
            "organization_type": org_type,
            "parent_organization_id": parent_id,
            "org_level_1": padded[0], "org_level_2": padded[1],
            "org_level_3": padded[2], "org_level_4": padded[3],
            "org_level_5": padded[4], "org_level_6": padded[5],
            "org_depth": len(levels),
            "org_path": " > ".join(levels),
            "business_unit": levels[1] if len(levels) > 1 else "Corporate",
            "function_name": levels[2] if len(levels) > 2 else "Corporate",
            "division_name": levels[3] if len(levels) > 3 else "Not Applicable",
            "department_name": levels[4] if len(levels) > 4 else "Not Applicable",
            "cost_center": cost_center,
            "effective_date": effective,
            "is_leaf": 0,
            "is_active": 1,
        })
        next_id += 1
        return rows[-1]["organization_id"]

    company = s.company
    company_id = add(company, "Company", 0, [company], start, "CC-4000")

    # Business units and functions
    function_id: dict[str, int] = {}
    for bu, functions in R.BUSINESS_UNITS.items():
        bu_id = add(bu, "Business Unit", company_id, [company, bu], start, "CC-4000")
        for fn in functions:
            cc_counter += 10
            function_id[fn] = add(fn, "Function", bu_id, [company, bu, fn], start,
                                  f"CC-{cc_counter}")

    # Divisions and departments
    dept_rows: list[tuple[int, str, str, str, str]] = []   # id, bu, fn, div, dept
    for fn, divisions in R.DIVISIONS.items():
        bu = next(b for b, fs in R.BUSINESS_UNITS.items() if fn in fs)
        for div in divisions:
            cc_counter += 10
            div_cc = f"CC-{cc_counter}"
            div_id = add(div, "Division", function_id[fn], [company, bu, fn, div],
                         start, div_cc)
            for dept in R.DEPARTMENTS.get(div, []):
                cc_counter += 1
                dept_cc = f"CC-{cc_counter}"
                dept_id = add(dept, "Department", div_id,
                              [company, bu, fn, div, dept], start, dept_cc)
                dept_rows.append((dept_id, bu, fn, div, dept))

    # Marketing reorganisation (Event 8) creates three new divisions part-way
    # through history. They carry a later effective_date, and the divisions they
    # replace are retired on the same day.
    reorg = s.event("marketing_reorganization")
    if reorg:
        eff = s.event_month("marketing_reorganization", "month_offset")
        for div, depts in R.REORG_DIVISIONS.items():
            cc_counter += 10
            div_id = add(div, "Division", function_id["Marketing"],
                         [company, "Go-to-Market", "Marketing", div], eff,
                         f"CC-{cc_counter}")
            for dept in depts:
                cc_counter += 1
                dept_id = add(dept, "Department", div_id,
                              [company, "Go-to-Market", "Marketing", div, dept],
                              eff, f"CC-{cc_counter}")
                dept_rows.append((dept_id, "Go-to-Market", "Marketing", div, dept))

    # The acquisition (Event 7) arrives with its own division, which is how you
    # can still see the acquired population as a unit two years later.
    acq = s.event("acquisition")
    if acq:
        eff = s.event_month("acquisition", "month_offset")
        cc_counter += 10
        acq_name = acq["company_name"]
        div_id = add(f"{acq_name} Integration", "Division", function_id["Engineering"],
                     [company, "Technology & Product", "Engineering",
                      f"{acq_name} Integration"], eff, f"CC-{cc_counter}")
        for dept in [f"{acq_name} Platform", f"{acq_name} Applications",
                     f"{acq_name} Customer Operations"]:
            cc_counter += 1
            dept_id = add(dept, "Department", div_id,
                          [company, "Technology & Product", "Engineering",
                           f"{acq_name} Integration", dept], eff, f"CC-{cc_counter}")
            dept_rows.append((dept_id, "Technology & Product", "Engineering",
                              f"{acq_name} Integration", dept))

    # Teams fill the remainder of the tier's org budget, weighted so that the
    # functions carrying the most headcount also carry the most supervisory orgs.
    fn_weight = s.baseline["function_mix"]
    remaining = max(target - len(rows), len(dept_rows))
    dept_ids = np.array([d[0] for d in dept_rows])
    weights = np.array([fn_weight.get(d[2], 0.02) for d in dept_rows], dtype=float)
    weights = weights / weights.sum()
    picks = rng.choice(len(dept_rows), size=remaining, p=weights)
    by_dept: dict[int, int] = {}
    dept_lookup = {d[0]: d for d in dept_rows}
    parent_cc = {r["organization_id"]: r["cost_center"] for r in rows}
    parent_eff = {r["organization_id"]: r["effective_date"] for r in rows}
    for idx in picks:
        did, bu, fn, div, dept = dept_rows[idx]
        n = by_dept.get(did, 0)
        by_dept[did] = n + 1
        suffix = R.TEAM_SUFFIXES[n % len(R.TEAM_SUFFIXES)]
        wave = "" if n < len(R.TEAM_SUFFIXES) else f" {n // len(R.TEAM_SUFFIXES) + 1}"
        add(f"{dept} {suffix}{wave}", "Team", did,
            [company, bu, fn, div, dept, f"{dept} {suffix}{wave}"],
            parent_eff[did], parent_cc[did])

    df = pd.DataFrame(rows)

    # A leaf is an org with no children; employees are assigned to leaves only.
    has_child = set(df["parent_organization_id"])
    df["is_leaf"] = (~df["organization_id"].isin(has_child)).astype("int8")

    # Retire the pre-reorg Marketing divisions and their descendants.
    if reorg:
        eff = s.event_month("marketing_reorganization", "month_offset")
        retired = {"Brand & Creative", "Growth Marketing", "Field Marketing"}
        mask = df["division_name"].isin(retired) | df["organization_name"].isin(retired)
        df.loc[mask, "is_active"] = 0
        df["inactive_date"] = pd.NaT
        df.loc[mask, "inactive_date"] = pd.Timestamp(eff)
        df["inactive_date"] = pd.to_datetime(df["inactive_date"]).dt.date
    else:
        df["inactive_date"] = pd.NaT

    df["manager_employee_id"] = 0        # filled in by population.py
    return df


def build_dim_location(s, rng: np.random.Generator) -> pd.DataFrame:
    target = int(s.sizes["locations"])
    zones = s.comp["geo_zone"]
    country_mix = s.baseline["country_mix"]

    # Distribute site count across countries by headcount share, at least one
    # site per city so no city in the catalog is unreachable.
    slots: list[tuple[str, tuple]] = []
    for country, cities in R.CITIES.items():
        for c in cities:
            slots.append((country, c))
    extra = max(target - len(slots), 0)
    weights = np.array([country_mix.get(c, 0.05) * city[2]
                        for c, city in slots], dtype=float)
    weights /= weights.sum()
    picks = list(rng.choice(len(slots), size=extra, p=weights)) if extra else []
    counts: dict[int, int] = {i: 1 for i in range(len(slots))}
    for i in picks:
        counts[int(i)] += 1

    rows = []
    lid = 1
    for i, (country, (city, state, weight, is_hub)) in enumerate(slots):
        zone = zones[country]
        for n in range(counts[i]):
            site_type = ("Headquarters" if (country == "US" and city == "Dallas" and n == 0)
                         else R.SITE_TYPES[(n + i) % len(R.SITE_TYPES)])
            name = city if n == 0 else f"{city} {site_type} {n + 1}"
            rows.append({
                "location_id": lid,
                "location_code": f"LOC_{city.upper().replace(' ', '_')}_{n + 1:02d}",
                "location_name": name,
                "site_type": site_type,
                "city": city,
                "state_province": state,
                "country": country,
                "country_iso": R.COUNTRY_ISO[country],
                "region": R.COUNTRY_REGION[country],
                "geo_zone": country,
                "currency": zone["currency"],
                "pay_frequency": zone["pay_frequency"],
                "is_hub": int(is_hub) if n == 0 else 0,
                "is_remote_hub": int(site_type == "Remote Hub"),
                "headcount_capacity": int(rng.integers(60, 900)),
                "opened_date": s.timeline.start_date - dt.timedelta(
                    days=int(rng.integers(400, 4_000))),
                "is_active": 1,
            })
            lid += 1

    # Acquired locations arrive with the acquisition, not before it.
    acq = s.event("acquisition")
    if acq:
        eff = s.event_month("acquisition", "month_offset")
        for country, city, state in [("US", "Portland", "OR"), ("UK", "Leeds", "England"),
                                     ("India", "Noida", "Uttar Pradesh")]:
            zone = zones[country]
            rows.append({
                "location_id": lid,
                "location_code": f"LOC_{city.upper()}_01",
                "location_name": f"{city} ({acq['company_name']})",
                "site_type": "Engineering Center",
                "city": city, "state_province": state, "country": country,
                "country_iso": R.COUNTRY_ISO[country],
                "region": R.COUNTRY_REGION[country], "geo_zone": country,
                "currency": zone["currency"], "pay_frequency": zone["pay_frequency"],
                "is_hub": 0, "is_remote_hub": 0,
                "headcount_capacity": int(rng.integers(80, 400)),
                "opened_date": eff, "is_active": 1,
            })
            lid += 1

    return pd.DataFrame(rows)
