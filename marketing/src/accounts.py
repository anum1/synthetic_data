"""Accounts, contacts and sales reps.

`dim_contact` is separated from `dim_customer` because the note conflated them
(PLAN 2.8). In B2B the buying unit is an account with several people in it, and
the journey page has to stitch touches across those people - the economic
buyer downloads the ROI calculator, the architect reads the reference
architecture, and neither of them alone looks like a journey worth showing.
Keeping them as one table makes that stitch impossible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mktconfig import Scenario

PREFIX = ["Ardent", "Northwind Bay", "Calder", "Meridian Peak", "Summit Row",
          "Larkfield", "Ironvale", "Brightline", "Waypoint", "Kestrel",
          "Havenstone", "Redpoint", "Silverbrook", "Thornhill", "Vantage Hill",
          "Aldergrove", "Blackmoor", "Cobalt", "Dunmore", "Eastgate",
          "Fairhaven", "Glenmark", "Holbrook", "Inverness", "Junipero",
          "Kingsford", "Lindale", "Marchmont", "Norbury", "Oakhurst",
          "Pinecrest", "Quarrydale", "Rosewood", "Stanmore", "Tidewater",
          "Ullswater", "Veremont", "Westbourne", "Yarrow", "Zephyr"]
SUFFIX_BY_INDUSTRY = {
    "Manufacturing": ["Industries", "Manufacturing", "Works", "Fabrication"],
    "Financial Services": ["Capital", "Financial", "Bancorp", "Advisors"],
    "Technology": ["Systems", "Software", "Technologies", "Labs"],
    "Retail": ["Retail Group", "Stores", "Commerce", "Brands"],
    "Healthcare": ["Health", "Medical Group", "Care Systems", "Diagnostics"],
    "Professional Services": ["Partners", "Consulting", "Advisory", "Group"],
    "Telecommunications": ["Telecom", "Communications", "Networks", "Mobile"],
    "Energy": ["Energy", "Resources", "Power", "Utilities"],
    "Public Sector": ["Authority", "Council", "Agency", "Trust"],
}
FIRST = ["Amara", "Brendan", "Chidi", "Daniela", "Elias", "Farah", "Grigor",
         "Hana", "Ines", "Jarrah", "Kavi", "Lucia", "Mateo", "Nadia", "Omar",
         "Priya", "Quinn", "Rowan", "Sana", "Tomas", "Ulla", "Viktor", "Wren",
         "Xiulan", "Yusuf", "Zara", "Adaeze", "Bo", "Camille", "Dmitri",
         "Esme", "Felix", "Gita", "Hugo", "Ivy", "Joon", "Kira", "Liam"]
LAST = ["Adeyemi", "Berger", "Costa", "Duarte", "Eriksen", "Fontaine", "Gupta",
        "Hollis", "Ibrahim", "Jensen", "Kowalski", "Laurent", "Moreau",
        "Nakamura", "Okafor", "Petrov", "Quintero", "Rahman", "Silva",
        "Tanaka", "Ustinov", "Vargas", "Whitfield", "Xu", "Yilmaz", "Zhou",
        "Almeida", "Bianchi", "Chen", "Delgado", "Esposito", "Fischer"]
# Persona drives which assets a contact touches and how much score they carry.
PERSONAS = [
    ("Economic Buyer", ["CFO", "VP Finance", "Chief Data Officer", "CIO"], 0.14, 1.55),
    ("Technical Buyer", ["Data Architect", "Head of Platform",
                         "Principal Engineer"], 0.24, 1.20),
    ("Champion", ["Director of Analytics", "Head of BI",
                  "Analytics Manager"], 0.27, 1.35),
    ("End User", ["Data Analyst", "BI Developer", "Reporting Lead"], 0.28, 0.65),
    ("Procurement", ["Procurement Manager", "Vendor Manager"], 0.07, 0.45),
]


def build_dim_customer(s: Scenario, geo: pd.DataFrame, industries: pd.DataFrame,
                       segments: pd.DataFrame,
                       rng: np.random.Generator) -> pd.DataFrame:
    """Accounts. Geography is assigned by the region spend split, so the region
    that gets the money is the region that has the accounts to spend it on."""
    n = int(s.universe["accounts"])

    reg_names = list(s.regions)
    reg_p = np.array([s.regions[r]["spend_share"] for r in reg_names])
    region = rng.choice(reg_names, size=n, p=reg_p / reg_p.sum())

    geo_key = np.zeros(n, dtype=np.int64)
    for r in reg_names:
        pool = geo[geo["region_name"] == r]
        m = region == r
        w = pool["_weight"].to_numpy()
        geo_key[m] = rng.choice(pool["geo_key"].to_numpy(), size=int(m.sum()),
                                p=w / w.sum())

    ind_p = industries["lead_share"].to_numpy()
    industry_id = rng.choice(industries["industry_id"].to_numpy(), size=n,
                             p=ind_p / ind_p.sum())
    ind_name = industries.set_index("industry_id")["industry_name"].to_dict()

    seg_p = segments["planned_account_share"].to_numpy()
    segment_id = rng.choice(segments["segment_id"].to_numpy(), size=n,
                            p=seg_p / seg_p.sum())
    seg_name = segments.set_index("segment_id")["segment_name"].to_dict()

    names, seen = [], {}
    pre = rng.choice(len(PREFIX), size=n)
    for i in range(n):
        ind = ind_name[industry_id[i]]
        suf = SUFFIX_BY_INDUSTRY[ind]
        nm = f"{PREFIX[pre[i]]} {suf[i % len(suf)]}"
        c = seen.get(nm, 0)
        seen[nm] = c + 1
        names.append(nm if c == 0 else f"{nm} {_roman(c + 1)}")

    seg_names = np.array([seg_name[x] for x in segment_id])
    emp = np.where(seg_names == "Enterprise",
                   rng.integers(2_001, 90_000, n),
                   np.where(seg_names == "Mid-Market",
                            rng.integers(201, 2_000, n),
                            rng.integers(12, 200, n)))
    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "account_name": names,
        "industry_id": industry_id.astype(np.int32),
        "segment_id": segment_id.astype(np.int32),
        "geo_key": geo_key.astype(np.int32),
        "region_name": region,
        "employee_count": emp.astype(np.int32),
        "annual_revenue_usd": (emp * rng.uniform(180_000, 420_000, n)).round(0),
        "account_type": "Prospect",
        "is_target_account": (rng.random(n) < 0.18).astype(np.int8),
        "is_hero_account": np.int8(0),
        "_quality": np.clip(rng.normal(1.0, 0.30, n), 0.15, 2.6),
    })
    df["account_tier"] = np.where(df["is_target_account"] == 1, "Named / ABM",
                                  np.where(seg_names == "Enterprise",
                                           "Strategic", "Volume"))
    return df


def _roman(n: int) -> str:
    return {2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII",
            8: "VIII", 9: "IX"}.get(n, str(n))


def build_dim_contact(s: Scenario, accounts: pd.DataFrame, n_contacts: int,
                      segments: pd.DataFrame,
                      rng: np.random.Generator) -> pd.DataFrame:
    """Several people per account, each with a persona.

    `n_contacts` is sized by the leads the spend acquires, not configured
    (PLAN 2.2): a contact exists because a campaign found them. Larger accounts
    get more of them, because a 40,000-person manufacturer really does have
    more people filling in forms than a 30-person agency - which is also why
    Enterprise accounts dominate the journey page.

    Consent is modelled here rather than assumed (PLAN 2.9): EMEA is
    consent-gated, which is why EMEA email reach is lower - a real answer to a
    real question instead of an unexplained dip.
    """
    w = (np.log1p(accounts["employee_count"].to_numpy())
         * accounts["_quality"].to_numpy())
    # Rescale per segment so each segment's contacts - and therefore its leads -
    # land on the configured lead_share, while the within-segment spread from
    # headcount survives. Without this, log1p(headcount) alone pulls Enterprise
    # to 14% of won deals against the 8% the mix derives, and the average deal
    # size lands 50% high. Relative effects preserved, levels pinned. (PLAN 1)
    seg_id = accounts["segment_id"].to_numpy()
    lead_share = dict(zip(segments["segment_id"], segments["planned_lead_share"]))
    for sid, share in lead_share.items():
        m = seg_id == sid
        if m.any() and w[m].sum() > 0:
            w[m] = w[m] / w[m].sum() * float(share)
    w = w / w.sum()
    # Every account gets at least one contact, then the rest go where the
    # people are.
    base = accounts["customer_id"].to_numpy()
    extra = rng.choice(base, size=max(0, n_contacts - len(base)), p=w)
    cust = np.concatenate([base, extra])
    cust.sort(kind="stable")
    n = len(cust)

    p_names = [p[0] for p in PERSONAS]
    p_w = np.array([p[2] for p in PERSONAS])
    persona = rng.choice(len(PERSONAS), size=n, p=p_w / p_w.sum())
    titles = np.array([PERSONAS[p][1][rng.integers(len(PERSONAS[p][1]))]
                       for p in persona])

    first = rng.choice(FIRST, n)
    last = rng.choice(LAST, n)
    acc = accounts.set_index("customer_id")
    region = acc.loc[cust, "region_name"].to_numpy()

    ev = s.event("consent_gap")
    consent_rate = np.full(n, 0.94)
    if ev:
        consent_rate[region == ev["region"]] = float(ev["consent_rate"])
    has_consent = rng.random(n) < consent_rate

    domain = (pd.Series(acc.loc[cust, "account_name"].to_numpy())
              .str.lower().str.replace(r"[^a-z0-9]+", "", regex=True)
              .str[:18] + ".example")
    df = pd.DataFrame({
        "contact_id": np.arange(1, n + 1),
        "customer_id": cust.astype(np.int32),
        "first_name": first, "last_name": last,
        "full_name": pd.Series(first) + " " + pd.Series(last),
        "job_title": titles,
        "persona": [p_names[p] for p in persona],
        "seniority": np.where(np.isin(titles, sum([PERSONAS[0][1], PERSONAS[1][1]], [])),
                              "Executive", "Manager / IC"),
        "email_address": (pd.Series(first).str.lower() + "."
                          + pd.Series(last).str.lower() + "@" + domain),
        "region_name": region,
        "consent_status": np.where(has_consent, "Opted In", "No Consent"),
        "is_email_subscribed": has_consent.astype(np.int8),
        "is_primary_contact": np.int8(0),
        "_persona_weight": np.array([PERSONAS[p][3] for p in persona]),
    })
    df.loc[df.groupby("customer_id")["contact_id"].head(1).index,
           "is_primary_contact"] = 1

    # A slice of the list unsubscribes over history. Suppression is a real
    # constraint on reach and it belongs in the data, not in a footnote.
    unsub = has_consent & (rng.random(n) < 0.09)
    tl = s.timeline
    span = (tl.as_of_date - tl.start_date).days
    off = rng.integers(30, max(span, 60), n)
    df["suppression_date"] = pd.NaT
    df.loc[unsub, "suppression_date"] = pd.to_datetime(
        [tl.start_date + pd.Timedelta(days=int(d)) for d in off[unsub]])
    df.loc[unsub, "consent_status"] = "Unsubscribed"
    df.loc[unsub, "is_email_subscribed"] = 0
    return df


TEAMS = ["Enterprise East", "Enterprise West", "Mid-Market North",
         "Mid-Market South", "SMB Velocity", "EMEA Enterprise", "EMEA Growth",
         "APAC Enterprise", "APAC Growth", "Strategic Accounts"]


def build_dim_sales_rep(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    """Sales ownership, with a per-rep effectiveness dial.

    `_effectiveness` is how the APAC sales-execution gap (E16) is expressed:
    marketing hands over the same SQLs, and one region converts fewer of them.
    That separation - good leads, poor conversion - is the cross-functional
    story in Scenario 4, and it needs a rep-level dial to be visible at all.
    """
    n = int(s.universe["sales_reps"])
    reg_names = list(s.regions)
    reg_p = np.array([s.regions[r]["spend_share"] for r in reg_names])
    region = rng.choice(reg_names, size=n, p=reg_p / reg_p.sum())
    seg = rng.choice(["SMB", "Mid-Market", "Enterprise"], size=n,
                     p=[0.45, 0.35, 0.20])
    team = np.array([TEAMS[i % len(TEAMS)] for i in range(n)])
    hire_off = rng.integers(0, 2_400, n)
    tl = s.timeline
    df = pd.DataFrame({
        "sales_rep_id": np.arange(1, n + 1),
        "rep_name": (pd.Series(rng.choice(FIRST, n)) + " "
                     + pd.Series(rng.choice(LAST, n))),
        "sales_team": team,
        "region_name": region,
        "segment_focus": seg,
        "rep_role": np.where(seg == "SMB", "Account Executive",
                             np.where(seg == "Mid-Market", "Senior AE",
                                      "Strategic Account Director")),
        "hire_date": [tl.start_date - pd.Timedelta(days=int(d)) for d in hire_off],
        "quota_usd": np.where(seg == "Enterprise", 1_800_000,
                              np.where(seg == "Mid-Market", 950_000, 520_000)),
        "is_active": (rng.random(n) > 0.06).astype(np.int8),
        "_effectiveness": np.clip(rng.normal(1.0, 0.22, n), 0.35, 1.9),
    })
    return df
