"""Legal entities, departments, cost centres, people and the approval policy.

`dim_approval_policy` is the table the whole fraud page depends on. "Buyers are
raising POs just below the approval threshold" is not a claim the data can
support unless the threshold exists as a row, varies by role and entity, and is
effective-dated - because the policy changed nineteen months ago, and an analyst
who compares POs from before and after the revision against today's limit will
reach the wrong conclusion (PLAN 2.7).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as ref
from p2pconfig import Scenario, add_month

# Share of the population at each level of authority. Requesters raise most of
# the requisitions; the tail is what approves the large ones.
ROLE_MIX = [
    ("Requester", 0.620),
    ("Manager", 0.200),
    ("Senior Manager", 0.090),
    ("Director", 0.055),
    ("VP", 0.026),
    ("SVP", 0.008),
    ("C-Suite", 0.001),
]

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]


def build_dim_company_code(s: Scenario) -> pd.DataFrame:
    rows = []
    for i, e in enumerate(s.entities, start=1):
        rows.append({
            "company_code_id": i,
            "company_code": e["code"],
            "company_name": e["name"],
            "country_code": e["country"],
            "functional_currency": e["currency"],
            "is_primary": int(i == 1),
        })
    df = pd.DataFrame(rows)
    df["_weight"] = [float(e["weight"]) for e in s.entities]
    return df


def build_dim_department(s: Scenario, entities: pd.DataFrame,
                         rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["departments"])
    names, regions = [], []
    i = 0
    # Cycle the name pool, qualifying by region on the second pass onward, so a
    # 96-department org does not need 96 hand-typed names.
    while len(names) < n:
        base = ref.DEPARTMENT_NAMES[i % len(ref.DEPARTMENT_NAMES)]
        lap = i // len(ref.DEPARTMENT_NAMES)
        region = REGIONS[lap % len(REGIONS)]
        names.append(base if lap == 0 else f"{base} - {region}")
        regions.append(region if lap else "North America")
        i += 1

    ent = entities.sample(n=n, replace=True, weights=entities["_weight"],
                          random_state=int(s.seed) + 31).reset_index(drop=True)
    df = pd.DataFrame({
        "department_id": np.arange(1, n + 1, dtype=np.int64),
        "department_code": [f"DEP{i:04d}" for i in range(1, n + 1)],
        "department_name": names,
        "region_name": regions,
        "company_code": ent["company_code"].to_numpy(),
        "function_name": [_function_of(x) for x in names],
    })
    # Requisition volume is not uniform across departments: IT and Operations
    # raise far more than Investor Relations.
    df["_demand_weight"] = rng.gamma(2.2, 1.0, size=n) * np.where(
        df["function_name"].isin(["Operations", "IT", "Facilities"]), 2.4, 1.0)
    df["_demand_weight"] /= df["_demand_weight"].sum()
    return df


def _function_of(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("manufactur", "plant", "quality", "supply", "logistic",
                            "warehouse", "field service")):
        return "Operations"
    if any(k in n for k in ("information technology", "applications", "infrastructure",
                            "security", "data and analytics")):
        return "IT"
    if any(k in n for k in ("finance", "treasury", "audit", "tax", "payable",
                            "planning")):
        return "Finance"
    if any(k in n for k in ("human resources", "talent", "learning")):
        return "HR"
    if any(k in n for k in ("facilities", "real estate", "environment")):
        return "Facilities"
    if any(k in n for k in ("legal", "compliance")):
        return "Legal"
    if any(k in n for k in ("marketing", "communications", "product", "research")):
        return "Marketing"
    if any(k in n for k in ("procurement",)):
        return "Procurement"
    return "Corporate"


def build_dim_cost_center(s: Scenario, depts: pd.DataFrame,
                          rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["cost_centers"])
    parent = depts.sample(n=n, replace=True, weights=depts["_demand_weight"],
                          random_state=int(s.seed) + 32).reset_index(drop=True)
    df = pd.DataFrame({
        "cost_center_id": np.arange(1, n + 1, dtype=np.int64),
        "cost_center_code": [f"CC{i:05d}" for i in range(1, n + 1)],
        "cost_center_name": [f"{d} {i}" for i, d in
                             zip(range(1, n + 1), parent["department_name"])],
        "department_id": parent["department_id"].to_numpy(),
        "company_code": parent["company_code"].to_numpy(),
        "region_name": parent["region_name"].to_numpy(),
        "is_active": (rng.random(n) > 0.04).astype("int8"),
    })
    df["_demand_weight"] = rng.gamma(2.0, 1.0, size=n)
    df["_demand_weight"] /= df["_demand_weight"].sum()
    return df


def build_dim_employee(s: Scenario, depts: pd.DataFrame, ccs: pd.DataFrame,
                       rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["employees"])
    names = ref.build_person_names(n, rng)

    roles = np.array([r for r, _ in ROLE_MIX])
    probs = np.array([p for _, p in ROLE_MIX], dtype=float)
    probs /= probs.sum()
    role = rng.choice(roles, size=n, p=probs)
    role[0] = "C-Suite"                  # guarantee the top of the chain exists

    cc = ccs.sample(n=n, replace=True, weights=ccs["_demand_weight"],
                    random_state=int(s.seed) + 33).reset_index(drop=True)
    dept_lookup = depts.set_index("department_id")

    first = [f for f, _ in names]
    last = [l for _, l in names]
    full = [f"{f} {l}" for f, l in names]
    # Email collisions are resolved with an ordinal, exactly as a real directory
    # does it - and the collisions themselves are useful noise.
    email, seen = [], {}
    for f, l in names:
        base = f"{f.split()[0].lower()}.{l.lower()}".replace(" ", "")
        k = seen.get(base, 0)
        seen[base] = k + 1
        email.append(f"{base}{'' if k == 0 else k}@norvantgroup.com")

    limits = {lvl["role"]: float(lvl["limit_usd"]) for lvl in s.doa["levels"]}
    mult = s.doa["entity_multiplier"]

    df = pd.DataFrame({
        "employee_id": np.arange(1, n + 1, dtype=np.int64),
        "employee_code": [f"EMP{i:06d}" for i in range(1, n + 1)],
        "first_name": first,
        "last_name": last,
        "full_name": full,
        "email_address": email,
        "role_name": role,
        "department_id": cc["department_id"].to_numpy(),
        "cost_center_id": cc["cost_center_id"].to_numpy(),
        "company_code": cc["company_code"].to_numpy(),
        "region_name": cc["region_name"].to_numpy(),
    })
    # Seat the senior bands in Finance or Corporate. Left to the draw, the
    # person holding a $100M approval limit ends up running Facilities, and the
    # first screenshot of the approval hierarchy is a distraction.
    senior = df["role_name"].isin(["SVP", "C-Suite"]).to_numpy()
    corporate = depts[depts["function_name"].isin(["Finance", "Corporate"])]
    if senior.any() and len(corporate):
        pick = corporate.sample(n=int(senior.sum()), replace=True,
                                random_state=int(s.seed) + 34)
        df.loc[senior, "department_id"] = pick["department_id"].to_numpy()
        df.loc[senior, "company_code"] = pick["company_code"].to_numpy()

    df["department_name"] = df["department_id"].map(dept_lookup["department_name"])
    df["function_name"] = df["department_id"].map(dept_lookup["function_name"])
    df["approval_limit_usd"] = [
        round(limits[r] * float(mult.get(cc_, 1.0)), 2)
        for r, cc_ in zip(df["role_name"], df["company_code"])]

    # Buyers sit in Procurement, plus a few embedded in Operations and IT. The
    # PO-splitting and threshold-clustering stories are about buyers, so the
    # population has to be small enough that concentration is meaningful.
    proc = (df["function_name"] == "Procurement").to_numpy()
    df["is_buyer"] = ((proc & (rng.random(n) < 0.72))
                      | (~proc & (rng.random(n) < 0.012))).astype("int8")
    df["is_approver"] = (df["role_name"] != "Requester").astype("int8")

    span = (s.timeline.as_of_date - s.timeline.start_date).days
    df["hire_date"] = [s.timeline.start_date - dt.timedelta(days=int(d))
                       for d in rng.integers(30, 3800, size=n)]
    df["is_active"] = (rng.random(n) > 0.075).astype("int8")

    # Manager chain: everyone reports to a random person one level up in the
    # same entity, so approval routing has somewhere to escalate to.
    order = {r: i for i, (r, _) in enumerate(ROLE_MIX)}
    lvl = df["role_name"].map(order).to_numpy()
    df["_level"] = lvl
    manager = np.zeros(n, dtype=np.int64)
    ids = df["employee_id"].to_numpy()
    for level in range(len(ROLE_MIX) - 1, 0, -1):
        subordinate = np.where(lvl == level)[0]
        superior = np.where(lvl == level - 1)[0]
        if len(subordinate) == 0 or len(superior) == 0:
            continue
        manager[subordinate] = ids[rng.choice(superior, size=len(subordinate))]
    df["manager_employee_id"] = manager
    _ = span
    return df


def build_dim_approval_policy(s: Scenario, entities: pd.DataFrame) -> pd.DataFrame:
    """Effective-dated delegation of authority.

    Two versions per role x entity: the original, and the revision that lifted
    every limit 25% nineteen months ago. An analyst who ignores the effective
    dating and tests every PO against today's limit gets the threshold-clustering
    answer wrong, which is exactly the kind of thing worth showing.
    """
    rev_month = s.timeline.offset_month(int(s.doa["revision_offset_month"]))
    uplift = float(s.doa["revision_uplift"])
    mult = s.doa["entity_multiplier"]
    far_future = dt.date(9999, 12, 31)

    rows, pid = [], 0
    for _, ent in entities.iterrows():
        m = float(mult.get(ent["company_code"], 1.0))
        for level in s.doa["levels"]:
            base = float(level["limit_usd"]) * m
            pid += 1
            rows.append({
                "approval_policy_id": pid, "company_code": ent["company_code"],
                "role_name": level["role"], "approval_limit_usd": round(base, 2),
                "effective_from_date": s.timeline.start_date,
                "effective_to_date": rev_month - dt.timedelta(days=1),
                "policy_version": 1, "is_current": 0,
            })
            pid += 1
            rows.append({
                "approval_policy_id": pid, "company_code": ent["company_code"],
                "role_name": level["role"],
                "approval_limit_usd": round(base * uplift, 2),
                "effective_from_date": rev_month,
                "effective_to_date": far_future,
                "policy_version": 2, "is_current": 1,
            })
    _ = add_month
    return pd.DataFrame(rows)
