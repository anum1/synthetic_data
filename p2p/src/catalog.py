"""Procurement hierarchy, item master and GL accounts.

Two decisions here carry demo weight.

**The leaf grain is subcategory.** `dim_category` is one row per leaf with the
whole path denormalised onto it, so a drill from segment to subcategory is four
columns of one table rather than a self-join, in every BI tool.

**Items carry `normalized_item_key` as well as `item_id`.** That is what makes
"where are we paying different prices for the same thing" answerable at two
levels of difficulty: the easy one (same item, two suppliers, two prices) and
the real one (two different item codes that are the same specification, because
someone onboarded the part twice).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import reference as ref
from p2pconfig import Scenario

UOM_BY_FAMILY = {
    "Raw Materials": ["KG", "TONNE", "M", "SHEET"],
    "Components": ["EA", "BOX", "SET"],
    "Packaging": ["ROLL", "CASE", "EA", "PALLET"],
    "Process Chemicals": ["L", "DRUM", "PAIL", "KG"],
    "Hardware": ["EA", "UNIT"],
    "Software": ["LICENCE", "SEAT", "MONTH"],
    "Network": ["EA", "PORT", "MONTH"],
    "IT Services": ["DAY", "MONTH", "SERVICE"],
    "Maintenance": ["VISIT", "SERVICE", "MONTH"],
    "Security": ["SHIFT", "MONTH", "EA"],
    "Cleaning": ["MONTH", "SERVICE", "VISIT"],
    "Utilities": ["MONTH", "KWH", "M3"],
    "Consulting": ["DAY", "WEEK", "SERVICE"],
    "Legal": ["HOUR", "MATTER", "MONTH"],
    "Finance and Audit": ["PHASE", "DAY", "SERVICE"],
    "Marketing": ["CAMPAIGN", "SERVICE", "MONTH"],
    "HR Services": ["WEEK", "PLACEMENT", "SEAT"],
    "Air Travel": ["TICKET", "TRIP"],
    "Lodging": ["NIGHT", "STAY"],
    "Ground Transportation": ["DAY", "TRIP", "TICKET"],
    "Meals and Entertainment": ["COVER", "SERVICE"],
    "Freight": ["MOVE", "SHIPMENT", "CONTAINER"],
    "Warehousing": ["PALLET-MONTH", "MONTH"],
    "Trade Services": ["ENTRY", "DECLARATION"],
}

# Typical unit price by unit of measure, in USD. A single global lognormal puts
# a consulting phase and a kilo of resin in the same price band, which makes
# "spend by category" nonsense the moment anyone looks at a unit price. Anchor
# the draw per UOM instead and let the sigma do the spreading.
UOM_PRICE_SCALE = {
    "KG": 4.0, "TONNE": 900.0, "M": 12.0, "SHEET": 45.0, "EA": 85.0, "BOX": 140.0,
    "SET": 260.0, "ROLL": 95.0, "CASE": 60.0, "PALLET": 22.0, "L": 9.0,
    "DRUM": 380.0, "PAIL": 120.0, "UNIT": 900.0, "LICENCE": 620.0, "SEAT": 240.0,
    "MONTH": 2_600.0, "PORT": 45.0, "DAY": 1_250.0, "SERVICE": 6_500.0,
    "VISIT": 480.0, "SHIFT": 320.0, "KWH": 0.14, "M3": 3.2, "WEEK": 4_200.0,
    "HOUR": 285.0, "PHASE": 18_000.0, "MATTER": 7_000.0, "CAMPAIGN": 28_000.0,
    "PLACEMENT": 5_500.0, "NIGHT": 210.0, "STAY": 640.0, "TICKET": 520.0,
    "TRIP": 88.0, "COVER": 95.0, "MOVE": 2_400.0, "SHIPMENT": 1_800.0,
    "CONTAINER": 3_100.0, "PALLET-MONTH": 28.0, "ENTRY": 240.0, "DECLARATION": 180.0,
}

# Service UOMs mark an item as a service line: no goods receipt, 2-way match.
# Deliberately narrow. Licences, tickets, freight moves and metered utilities all
# get receipted in a real ERP one way or another; only genuinely unreceiptable
# effort belongs here. Casting the net wider put 40% of purchase order lines
# outside three-way matching, which is not a company anyone would recognise.
SERVICE_UOMS = {"DAY", "MONTH", "SERVICE", "HOUR", "WEEK", "VISIT", "SHIFT",
                "PHASE", "CAMPAIGN", "MATTER", "PLACEMENT", "COVER", "STAY"}

# Segments whose spend is production, not overhead. Drives GL block, tolerance
# policy and lead-time behaviour downstream.
DIRECT_SEGMENTS = {"Direct Materials"}


def build_dim_category(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    cid = 0
    for segment, families in ref.HIERARCHY.items():
        for family, categories in families.items():
            for category in categories:
                # 3-6 leaves per category gets the leaf count to ~340 without
                # hand-typing 340 noun phrases.
                k = int(rng.integers(3, 7))
                mods = rng.choice(ref.SUBCATEGORY_MODIFIERS, size=k, replace=False)
                for mod in mods:
                    cid += 1
                    rows.append({
                        "category_id": cid,
                        "category_code": f"CAT{cid:04d}",
                        "segment_name": segment,
                        "family_name": family,
                        "category_name": category,
                        "subcategory_name": f"{category} - {mod}",
                        "is_direct_spend": int(segment in DIRECT_SEGMENTS),
                        "category_path": f"{segment} > {family} > {category} > {mod}",
                    })
    df = pd.DataFrame(rows)

    # Spend weight: how much of the requisition stream lands on each leaf.
    # Normalised WITHIN each segment to the configured segment share, so the
    # spend mix is a decision rather than an artefact of how many subcategories
    # each part of the taxonomy happens to carry.
    df["_spend_weight"] = rng.gamma(2.0, 1.0, size=len(df))
    shares = s.demand["segment_spend_share"]
    for segment, share in shares.items():
        m = (df["segment_name"] == segment).to_numpy()
        if not m.any():
            continue
        df.loc[m, "_spend_weight"] = (df.loc[m, "_spend_weight"]
                                      / df.loc[m, "_spend_weight"].sum()
                                      * float(share))
    df["_spend_weight"] /= df["_spend_weight"].sum()
    return df


def build_dim_gl_account(s: Scenario, cats: pd.DataFrame,
                         rng: np.random.Generator) -> pd.DataFrame:
    """Natural accounts, with a family -> account mapping the coding uses."""
    rows = []
    fam_to_acct: dict[str, int] = {}
    for base, block_name, families in ref.GL_ACCOUNT_BLOCKS:
        for i, family in enumerate(families):
            acct = base + (i + 1) * 10
            fam_to_acct[family] = acct
            rows.append({"gl_account_id": acct, "gl_account_code": f"{acct}",
                         "gl_account_name": f"{family} Expense",
                         "gl_block_name": block_name,
                         "account_type": "COGS" if base == 5000 else "Operating Expense",
                         "is_capex": 0})
            # Sub-accounts give the coding some texture and the account count
            # something like the 240 a real chart of accounts carries.
            for j in range(1, int(rng.integers(6, 13))):
                rows.append({"gl_account_id": acct + j, "gl_account_code": f"{acct + j}",
                             "gl_account_name": f"{family} - Sub {j}",
                             "gl_block_name": block_name,
                             "account_type": "COGS" if base == 5000 else "Operating Expense",
                             "is_capex": int(j == 1 and base in (6100, 6200))})
    df = pd.DataFrame(rows).drop_duplicates("gl_account_id").reset_index(drop=True)
    df.attrs["family_to_account"] = fam_to_acct
    return df


def build_dim_item(s: Scenario, cats: pd.DataFrame, gl: pd.DataFrame,
                   rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["items"])
    # Sample on a flattened weight: a direct catalogue is a few thousand parts
    # carrying half the spend, while the indirect tail is many items each worth
    # little. Using the spend weight directly would make 56% of the item master
    # direct material, which no manufacturer's catalogue looks like.
    item_weight = cats["_spend_weight"] ** 0.35
    leaf = cats.sample(n=n, replace=True, weights=item_weight,
                       random_state=int(s.seed) + 21).reset_index(drop=True)

    nouns = []
    for fam in leaf["family_name"]:
        pool = ref.ITEM_NOUNS.get(fam, ["Item"])
        nouns.append(pool[int(rng.integers(0, len(pool)))])

    fam_map = gl.attrs["family_to_account"]
    df = pd.DataFrame({
        "item_id": np.arange(1, n + 1, dtype=np.int64),
        "item_code": [f"ITM-{i:06d}" for i in range(1, n + 1)],
        "item_name": [f"{n_} {g}" for n_, g in
                      zip(nouns, rng.integers(100, 999, size=n))],
        "category_id": leaf["category_id"].to_numpy(),
        "segment_name": leaf["segment_name"].to_numpy(),
        "family_name": leaf["family_name"].to_numpy(),
        "category_name": leaf["category_name"].to_numpy(),
        "is_direct_spend": leaf["is_direct_spend"].to_numpy(),
        "unit_of_measure": [UOM_BY_FAMILY.get(f, ["EA"])[
            int(rng.integers(0, len(UOM_BY_FAMILY.get(f, ["EA"]))))]
            for f in leaf["family_name"]],
        "list_price_usd": 0.0,      # filled below, once the UOM is known
        "gl_account_id": [fam_map.get(f, 6110) for f in leaf["family_name"]],
    })
    sigma = float(s.sourcing["item_price_sigma"])
    scale = df["unit_of_measure"].map(UOM_PRICE_SCALE).fillna(85.0).to_numpy()
    price = scale * np.exp(rng.normal(0.0, sigma, size=n))
    df["list_price_usd"] = np.round(np.maximum(price, 0.05), 2)
    df["is_service_item"] = df["unit_of_measure"].isin(SERVICE_UOMS).astype("int8")

    # Specification key. Most items are their own spec; ~12% are a second item
    # code for a specification that already exists - the master-data defect that
    # makes the price-comparison question interesting rather than trivial.
    spec = np.arange(1, n + 1)
    dup_n = int(round(0.12 * n))
    if dup_n:
        dup_idx = rng.choice(n, size=dup_n, replace=False)
        # Point each duplicate at an earlier item in the same category, so the
        # collision is plausible rather than a laptop matching a pallet.
        by_cat: dict[int, list[int]] = {}
        for i, c in enumerate(df["category_id"].to_numpy()):
            by_cat.setdefault(int(c), []).append(i)
        for i in dup_idx:
            peers = [p for p in by_cat.get(int(df["category_id"].iloc[i]), []) if p < i]
            if peers:
                spec[i] = spec[peers[int(rng.integers(0, len(peers)))]]
    df["normalized_item_key"] = [f"SPEC-{v:06d}" for v in spec]
    return df
