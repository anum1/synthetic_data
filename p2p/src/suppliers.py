"""Supplier master, and the master-data defects that make it worth analysing.

Two thousand clean suppliers is a dimension table. What makes this a demo is the
mess: the same vendor onboarded four times under four spellings, a supplier that
went inactive two years ago and is still being raised POs against, three
suppliers quietly sharing one bank account, and a contact whose name matches an
employee in the department that keeps buying from them.

Every one of those is planted deliberately and *with a control group*. Three
suspicious bank-account clusters are accompanied by two benign ones - two
subsidiaries of a common parent legitimately sharing a remit-to account - so
"find suppliers sharing bank accounts" is an analysis with a false-positive
rate, not a filter that happens to return the answer key (PLAN 2.7).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as ref
from p2pconfig import Scenario, add_month, month_end

RISK_TIERS = [(0, 25, "Low"), (25, 55, "Medium"), (55, 80, "High"), (80, 101, "Critical")]

# How a duplicate record differs from the original. These are the four ways a
# vendor genuinely ends up in the master twice.
VARIANT_STYLES = ["legal_suffix", "abbreviation", "punctuation", "trading_name"]

# How the corporate form is shortened when a vendor is re-keyed by hand. Chopping
# the last word at four characters produces "Selton Ente", which reads as a bug
# rather than as a data-entry variant.
FORM_ABBREV = {
    "Technologies": "Tech", "Manufacturing": "Mfg", "Industrial": "Ind",
    "Enterprises": "Ent", "Solutions": "Solns", "Systems": "Sys",
    "Services": "Svcs", "Logistics": "Log", "Associates": "Assoc",
    "Holdings": "Hldgs", "Partners": "Ptnrs", "Supply Co": "Supply",
    "Labs": "Labs", "Group": "Grp",
}


def _tier(score: float) -> str:
    for lo, hi, name in RISK_TIERS:
        if lo <= score < hi:
            return name
    return "Critical"


def _variant_name(base: str, style: str, rng: np.random.Generator) -> str:
    words = base.split()
    if style == "legal_suffix":
        return f"{base} {rng.choice(['Inc', 'LLC', 'Ltd', 'GmbH', 'BV'])}"
    if style == "abbreviation":
        # "Northbeam Technologies" -> "Northbeam Tech", or initials on the stem
        # when the form has no accepted short version.
        if words[-1] in FORM_ABBREV:
            return " ".join(words[:-1] + [FORM_ABBREV[words[-1]]])
        stem = words[:-1] or words
        initials = ".".join(w[0] for w in stem) + "."
        return f"{initials} {words[-1]}"
    if style == "punctuation":
        return base.replace(" ", "-", 1) + " Co."
    return f"{words[0]} {rng.choice(['Group', 'Holdings', 'International', 'Partners'])}"


def build_supplier_master(s: Scenario, entities: pd.DataFrame,
                          employees: pd.DataFrame, rng: np.random.Generator):
    """Returns (suppliers, parents, sites, bank_accounts, status_history)."""
    n = int(s.sizes["suppliers"])
    sm = s.supplier_master
    names = ref.build_supplier_names(n, rng)

    countries = [c for c, _ in ref.SUPPLIER_COUNTRIES]
    cprob = np.array([p for _, p in ref.SUPPLIER_COUNTRIES], dtype=float)
    cprob /= cprob.sum()
    country = rng.choice(countries, size=n, p=cprob)

    df = pd.DataFrame({
        "supplier_id": np.arange(1, n + 1, dtype=np.int64),
        "supplier_code": [f"SUP{i:06d}" for i in range(1, n + 1)],
        "supplier_name": names,
        "country_code": country,
        "currency_code": [ref.COUNTRY_CURRENCY.get(c, "USD") for c in country],
    })

    # Spend weight: rank-based power law, so the top 20% of suppliers carry
    # ~72% of spend at BOTH tiers and the number is stable across seeds.
    rank = np.arange(1, n + 1, dtype=float)
    k = float(s.demand["supplier_zipf_exponent"])
    shift = float(s.demand["supplier_zipf_shift_frac"]) * n
    jitter = rng.lognormal(0, float(s.demand["supplier_weight_jitter_sigma"]), size=n)
    df["_spend_weight"] = ((rank + shift) ** -k) * jitter
    df = df.sort_values("_spend_weight", ascending=False).reset_index(drop=True)
    # Re-issue ids in spend order so the hand-written names land on the big
    # suppliers, which are the rows a demo actually puts on screen.
    df["supplier_id"] = np.arange(1, n + 1, dtype=np.int64)
    df["supplier_code"] = [f"SUP{i:06d}" for i in df["supplier_id"]]
    df["supplier_name"] = names
    df["_spend_weight"] /= df["_spend_weight"].sum()

    # --- duplicate families ---------------------------------------------------
    # A share of the master is variant records of a supplier that already exists.
    # They keep their own id, their own site and often their own bank account,
    # which is precisely why the spend fragments.
    df["is_duplicate_variant"] = 0
    df["duplicate_of_supplier_id"] = 0
    df["variant_style"] = ""
    n_dup = int(round(float(sm["duplicate_family_share"]) * n))
    lo, hi = sm["variants_per_family"]
    # Duplicate families are drawn from the top third of the spend distribution:
    # nobody notices a fragmented $4K vendor, and the demo needs the fragments to
    # add up to something worth consolidating.
    pool = np.arange(0, max(int(n * 0.34), 8))
    bases = rng.choice(pool, size=max(1, n_dup // int((lo + hi) / 2)), replace=False)
    taken = set(df["supplier_name"])
    cursor = n - 1
    for b in bases:
        k = int(rng.integers(lo, hi + 1)) - 1
        for _ in range(k):
            if cursor <= max(pool):        # do not overwrite the head of the list
                break
            base_name = df.loc[b, "supplier_name"]
            name = None
            for style in rng.permutation(VARIANT_STYLES):
                cand = _variant_name(base_name, str(style), rng)
                if cand not in taken:
                    name, chosen_style = cand, str(style)
                    break
            if name is None:               # every style already used for this base
                continue
            taken.add(name)
            style = chosen_style
            df.loc[cursor, "supplier_name"] = name
            df.loc[cursor, "country_code"] = df.loc[b, "country_code"]
            df.loc[cursor, "currency_code"] = df.loc[b, "currency_code"]
            df.loc[cursor, "is_duplicate_variant"] = 1
            df.loc[cursor, "duplicate_of_supplier_id"] = int(df.loc[b, "supplier_id"])
            df.loc[cursor, "variant_style"] = style
            cursor -= 1

    df["normalized_supplier_name"] = [ref.normalize_name(x) for x in df["supplier_name"]]

    # --- corporate hierarchy --------------------------------------------------
    # Duplicate variants always roll to their original's parent. Everyone else
    # either heads their own parent or joins one, so the hierarchy has both
    # single-entity suppliers and genuine multi-entity groups.
    parent_of = {}
    parent_rows, next_parent = [], 0
    for i in range(len(df)):
        sid = int(df.loc[i, "supplier_id"])
        dup_of = int(df.loc[i, "duplicate_of_supplier_id"])
        if dup_of:
            parent_of[sid] = parent_of[dup_of]
            continue
        if next_parent and rng.random() < 0.22:
            # Join an existing group, preferring one nearby in spend rank.
            pick = parent_rows[int(rng.integers(max(0, next_parent - 40), next_parent))]
            parent_of[sid] = pick["supplier_parent_id"]
            continue
        next_parent += 1
        root = df.loc[i, "supplier_name"].split()[0]
        parent_rows.append({
            "supplier_parent_id": next_parent,
            "parent_code": f"PAR{next_parent:05d}",
            "parent_name": f"{root} Holding Group",
            "normalized_parent_name": ref.normalize_name(root),
            "headquarters_country": df.loc[i, "country_code"],
        })
        parent_of[sid] = next_parent
    parents = pd.DataFrame(parent_rows)
    df["supplier_parent_id"] = df["supplier_id"].map(parent_of).astype("int64")

    # --- identifiers, status, risk -------------------------------------------
    tax = [f"{c}{int(v):09d}" for c, v in
           zip(df["country_code"], rng.integers(10**8, 10**9 - 1, size=n))]
    # A variant record frequently carries the SAME tax id as its original - the
    # strongest available evidence that two supplier records are one vendor.
    tax_by_sid = dict(zip(df["supplier_id"], tax))
    for i in range(len(df)):
        dup_of = int(df.loc[i, "duplicate_of_supplier_id"])
        if dup_of and rng.random() < 0.55:
            tax[i] = tax_by_sid[dup_of]
    missing_tax = rng.random(n) < float(sm["missing_tax_id_share"])
    df["tax_id"] = np.where(missing_tax, None, tax)
    df["has_tax_id"] = (~missing_tax).astype("int8")
    df["duns_number"] = [f"{int(v):09d}" for v in rng.integers(10**8, 10**9 - 1, size=n)]

    onboard_span = (s.timeline.as_of_date - s.timeline.start_date).days + 2500
    df["onboarded_date"] = [s.timeline.as_of_date - dt.timedelta(days=int(d))
                            for d in rng.integers(60, onboard_span, size=n)]

    score = rng.uniform(*sm["risk_score_range"], size=n)
    df["risk_score"] = np.round(score, 1)
    df["risk_tier"] = [_tier(x) for x in score]
    df["is_diverse_supplier"] = (rng.random(n)
                                 < float(sm["diversity_flag_share"])).astype("int8")
    df["diversity_classification"] = np.where(
        df["is_diverse_supplier"] == 1,
        rng.choice(["Minority Owned", "Women Owned", "Veteran Owned",
                    "Small Business"], size=n), "Not Classified")

    inactive = rng.random(n) < float(sm["inactive_share"])
    blocked = inactive & (rng.random(n) < 0.18)
    df["supplier_status"] = np.where(blocked, "Blocked",
                                     np.where(inactive, "Inactive", "Active"))

    # Contacts. Real conflicts of interest are planted here (PLAN 2.7).
    people = ref.build_person_names(n, np.random.default_rng(int(s.seed) + 77))
    df["primary_contact_name"] = [f"{f} {l}" for f, l in people]
    df["is_preferred_supplier"] = (
        rng.random(n) < float(s.sourcing["preferred_supplier_share"])).astype("int8")

    sites = _build_sites(s, df, rng)
    banks = _build_bank_accounts(s, df, parents, rng)
    history = _build_status_history(s, df, rng)
    df = _plant_employee_conflicts(s, df, sites, employees, rng)
    return df, parents, sites, banks, history


def _build_sites(s: Scenario, sup: pd.DataFrame,
                 rng: np.random.Generator) -> pd.DataFrame:
    """Order-from and remit-to sites. Roughly 1.8 per supplier."""
    rows, sid = [], 0
    for _, r in sup.iterrows():
        k = 1 + int(rng.random() < 0.55) + int(rng.random() < 0.22)
        country = r["country_code"]
        cities = ref.CITIES.get(country, ["Springfield"])
        for j in range(k):
            sid += 1
            purpose = "Order From" if j == 0 else (
                "Remit To" if j == 1 else "Ship From")
            rows.append({
                "supplier_site_id": sid,
                "supplier_site_code": f"SITE{sid:07d}",
                "supplier_id": int(r["supplier_id"]),
                "site_purpose": purpose,
                "address_line": f"{int(rng.integers(1, 999))} "
                                f"{ref.STREETS[int(rng.integers(0, len(ref.STREETS)))]}",
                "city_name": cities[int(rng.integers(0, len(cities)))],
                "country_code": country,
                "site_tax_id": r["tax_id"] if j == 0 else (
                    r["tax_id"] if rng.random() < 0.7 else None),
                "is_primary_site": int(j == 0),
                "is_pay_site": int(purpose == "Remit To" or k == 1),
                "is_active": int(rng.random() > 0.06),
            })
    return pd.DataFrame(rows)


def _build_bank_accounts(s: Scenario, sup: pd.DataFrame, parents: pd.DataFrame,
                         rng: np.random.Generator) -> pd.DataFrame:
    n = len(sup)
    sm = s.supplier_master
    rows, bid = [], 0
    for _, r in sup.iterrows():
        if rng.random() < float(sm["missing_bank_detail_share"]):
            continue                      # no active remit-to: a BANK_MISSING hold
        k = 1 + int(rng.random() < 0.18)
        for j in range(k):
            bid += 1
            rows.append({
                "bank_account_id": bid,
                "supplier_id": int(r["supplier_id"]),
                "bank_name": f"{ref.HERO_SUPPLIER_ROOTS[bid % len(ref.HERO_SUPPLIER_ROOTS)]} Bank",
                "bank_country_code": r["country_code"],
                "account_number_masked": f"****{int(rng.integers(1000, 9999))}",
                "account_number_hash": f"BA{int(rng.integers(10**9, 10**10 - 1))}",
                "iban_prefix": f"{r['country_code']}{int(rng.integers(10, 99))}",
                "is_primary_account": int(j == 0),
                "is_active": int(rng.random() > 0.05),
                "shared_flag_reason": "",
            })
    banks = pd.DataFrame(rows)

    ev = s.event("shared_bank_accounts")
    if ev is None or banks.empty:
        return banks

    lo, hi = ev["suppliers_per_cluster"]
    parent_of = dict(zip(sup["supplier_id"], sup["supplier_parent_id"]))
    # Suspicious: suppliers from DIFFERENT parents sharing one account.
    mid = sup[(sup["_spend_weight"].rank(ascending=False) > 30)
              & (sup["_spend_weight"].rank(ascending=False) < n * 0.6)]
    used: set[int] = set()
    n_clusters = int(ev["suspicious_clusters"])
    # Spread the configured sizes deterministically rather than drawing three
    # independent integers and hoping for variety - with three clusters, a draw
    # lands on all-twos often enough to look like the range is being ignored.
    sizes = [lo + (i % (hi - lo + 1)) for i in range(n_clusters)]
    for c in range(n_clusters):
        k = int(sizes[c])
        cand = [x for x in mid["supplier_id"].to_numpy() if x not in used]
        chosen, seen_parents = [], set()
        for sid in rng.permutation(cand):
            p = parent_of[sid]
            if p in seen_parents:
                continue
            seen_parents.add(p)
            chosen.append(int(sid))
            if len(chosen) == k:
                break
        used.update(chosen)
        shared_hash = f"BA{int(rng.integers(10**9, 10**10 - 1))}"
        shared_mask = f"****{int(rng.integers(1000, 9999))}"
        hit = banks["supplier_id"].isin(chosen) & (banks["is_primary_account"] == 1)
        banks.loc[hit, "account_number_hash"] = shared_hash
        banks.loc[hit, "account_number_masked"] = shared_mask
        banks.loc[hit, "shared_flag_reason"] = "Unrelated suppliers"

    # Benign: subsidiaries of ONE parent legitimately sharing a remit-to account.
    grouped = sup.groupby("supplier_parent_id")["supplier_id"].apply(list)
    multi = [g for g in grouped if len(g) >= 2]
    rng.shuffle(multi)
    for g in multi[:int(ev["benign_clusters"])]:
        chosen = [int(x) for x in g[:3]]
        shared_hash = f"BA{int(rng.integers(10**9, 10**10 - 1))}"
        shared_mask = f"****{int(rng.integers(1000, 9999))}"
        hit = banks["supplier_id"].isin(chosen) & (banks["is_primary_account"] == 1)
        banks.loc[hit, "account_number_hash"] = shared_hash
        banks.loc[hit, "account_number_masked"] = shared_mask
        banks.loc[hit, "shared_flag_reason"] = "Same corporate parent"
    return banks


def _build_status_history(s: Scenario, sup: pd.DataFrame,
                          rng: np.random.Generator) -> pd.DataFrame:
    """Effective-dated supplier status.

    A current-state flag cannot answer "was this supplier inactive on the day the
    PO was raised", which is the only version of the question worth asking.
    """
    far_future = dt.date(9999, 12, 31)
    rows, hid = [], 0
    for _, r in sup.iterrows():
        onboard = r["onboarded_date"]
        status = r["supplier_status"]
        if status == "Active":
            hid += 1
            rows.append({"status_history_id": hid, "supplier_id": int(r["supplier_id"]),
                         "supplier_status": "Active", "effective_from_date": onboard,
                         "effective_to_date": far_future, "is_current": 1,
                         "change_reason": "Onboarded"})
            continue
        span = max((s.timeline.as_of_date - onboard).days, 30)
        changed = onboard + dt.timedelta(days=int(rng.integers(span // 3, span)))
        hid += 1
        rows.append({"status_history_id": hid, "supplier_id": int(r["supplier_id"]),
                     "supplier_status": "Active", "effective_from_date": onboard,
                     "effective_to_date": changed - dt.timedelta(days=1),
                     "is_current": 0, "change_reason": "Onboarded"})
        hid += 1
        rows.append({"status_history_id": hid, "supplier_id": int(r["supplier_id"]),
                     "supplier_status": status, "effective_from_date": changed,
                     "effective_to_date": far_future, "is_current": 1,
                     "change_reason": "Dormant - no spend" if status == "Inactive"
                                      else "Compliance block"})
    return pd.DataFrame(rows)


def _plant_employee_conflicts(s: Scenario, sup: pd.DataFrame, sites: pd.DataFrame,
                              employees: pd.DataFrame,
                              rng: np.random.Generator) -> pd.DataFrame:
    """Employee/supplier relationships, plus lookalikes that are not.

    Without the coincidental matches the question "find employees connected to
    suppliers" is a join that returns exactly the planted rows. With them, it is
    a ranking problem - which is what the audience actually has at home.
    """
    sup["conflict_flag"] = 0
    ev = s.event("employee_supplier_conflict")
    if ev is None or employees.empty:
        return sup

    mid = sup[sup["supplier_id"] > 40].sample(
        n=int(ev["real_conflicts"]) + int(ev["coincidental_matches"]),
        random_state=int(s.seed) + 51)
    real = mid.index[:int(ev["real_conflicts"])]
    coincidental = mid.index[int(ev["real_conflicts"]):]

    # Real: full name match AND a shared address with the employee's site.
    picks = employees[employees["is_active"] == 1].sample(
        n=len(real), random_state=int(s.seed) + 52)
    for idx, (_, emp) in zip(real, picks.iterrows()):
        sup.loc[idx, "primary_contact_name"] = emp["full_name"]
        sup.loc[idx, "conflict_flag"] = 1

    # Coincidental: surname only. Common surnames collide in any real directory.
    picks2 = employees.sample(n=len(coincidental), random_state=int(s.seed) + 53)
    for idx, (_, emp) in zip(coincidental, picks2.iterrows()):
        other_first = ref.FIRST_NAMES[int(rng.integers(0, len(ref.FIRST_NAMES)))]
        sup.loc[idx, "primary_contact_name"] = f"{other_first} {emp['last_name']}"
    return sup


def build_supplier_risk_snapshot(s: Scenario, sup: pd.DataFrame,
                                 rng: np.random.Generator) -> pd.DataFrame:
    """Monthly risk score per supplier.

    A single current score cannot show deterioration, and "this supplier's risk
    has been climbing for nine months" is a better sentence than "this supplier
    is high risk".
    """
    months = s.timeline.month_starts()
    n, m = len(sup), len(months)
    base = sup["risk_score"].to_numpy()[:, None]
    # A slow random walk per supplier, ending at the current score.
    drift = np.cumsum(rng.normal(0, 1.6, size=(n, m)), axis=1)
    drift -= drift[:, -1][:, None]
    score = np.clip(base + drift, 1, 100)

    out = pd.DataFrame({
        "supplier_id": np.repeat(sup["supplier_id"].to_numpy(), m),
        "snapshot_month": np.tile([month_end(x) for x in months], n),
        "risk_score": np.round(score.ravel(), 1),
    })
    out["risk_tier"] = [_tier(x) for x in out["risk_score"]]
    out["supplier_risk_id"] = np.arange(1, len(out) + 1, dtype=np.int64)
    _ = add_month
    return out
