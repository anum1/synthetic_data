"""Dimension builders.

Base attributes only. Anything DERIVED from the facts -- ABC/XYZ class,
supplier on-time rate, defect rate, risk score -- is left blank here and
back-filled after generation. See docs/DATA_MODEL.md section 7 for why the
order is forced.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import reference as R


# ---------------------------------------------------------------------------
# Plan-grain conformed dimensions
# ---------------------------------------------------------------------------
def build_dim_region() -> pd.DataFrame:
    return pd.DataFrame({
        "region_id": np.arange(1, len(R.REGIONS) + 1, dtype="int32"),
        "region": R.REGIONS,
    })


def build_dim_product_category() -> pd.DataFrame:
    rows = R.flat_taxonomy()
    return pd.DataFrame({
        "product_category_id": np.arange(1, len(rows) + 1, dtype="int32"),
        "category": [c for c, _ in rows],
        "subcategory": [s for _, s in rows],
        "is_manufactured": [int(s in R.MANUFACTURED) for _, s in rows],
    })


# ---------------------------------------------------------------------------
# dim_location
# ---------------------------------------------------------------------------
def build_dim_location(n: int, rng, new_dc_enabled: bool) -> pd.DataFrame:
    base = R.LOCATIONS[:n]
    if new_dc_enabled:
        base = base + [R.NEW_DC]          # Event 12; opens mid-timeline
    c2r = R.country_region_map()

    city = [b[0] for b in base]
    country = [b[1] for b in base]
    sub = [b[2] for b in base]
    node = [b[3] for b in base]
    region = [c2r[c] for c in country]

    df = pd.DataFrame({
        "location_id": np.arange(1, len(base) + 1, dtype="int32"),
        "location_code": [f"LOC-{i:03d}" for i in range(1, len(base) + 1)],
        "location_name": [f"{c} {t}" for c, t in zip(city, node)],
        "city": city,
        "country": country,
        "sub_region": sub,
        "region": region,
        "node_type": node,
        "capacity_units": rng.integers(40_000, 260_000, len(base)).astype("int32"),
        "is_plant": [int(t == "Plant") for t in node],
        "opened_offset_months": 0,        # overwritten for the new DC by events
    })
    # Flattened hierarchy: Tableau cannot walk a parent-child path, Power BI can.
    # Emitting explicit levels means one definition works in both.
    df["geo_level1_global"] = "Global"
    df["geo_level2_region"] = df["region"]
    df["geo_level3_country"] = df["country"]
    df["geo_level4_sub_region"] = df["sub_region"].replace("", "National")
    df["geo_level5_location"] = df["location_name"]
    return df


# ---------------------------------------------------------------------------
# dim_carrier
# ---------------------------------------------------------------------------
def build_dim_carrier(n: int, rng) -> pd.DataFrame:
    names = R.CARRIER_NAMES[:n]
    codes = [f"C-{i:02d}" for i in range(1, n + 1)]
    modes = [R.CARRIER_MODES[i % len(R.CARRIER_MODES)] for i in range(n)]
    return pd.DataFrame({
        "carrier_id": np.arange(1, n + 1, dtype="int32"),
        "carrier_code": codes,
        "carrier_name": names,
        "transport_mode": modes,
        "base_cost_per_km": np.round(rng.uniform(0.06, 0.42, n), 4),
        "contracted_transit_days": rng.integers(2, 12, n).astype("int32"),
        # Blank until derived from fact_shipment.
        "on_time_rate": np.nan,
        "avg_transit_days": np.nan,
    })


# ---------------------------------------------------------------------------
# dim_supplier
# ---------------------------------------------------------------------------
def build_dim_supplier(n: int, rng, cfg) -> pd.DataFrame:
    """Row 0 is a real 'No Alternate Supplier' row so no FK is ever NULL."""
    stems = [R.SUPPLIER_STEMS[i % len(R.SUPPLIER_STEMS)] for i in range(n)]
    sfx = [R.SUPPLIER_SUFFIXES[i % len(R.SUPPLIER_SUFFIXES)] for i in range(n)]
    clean = [f"{s} {x}" for s, x in zip(stems, sfx)]
    # Repeated stems get a numeral so the clean names stay distinguishable.
    seen: dict[str, int] = {}
    for i, nm in enumerate(clean):
        seen[nm] = seen.get(nm, 0) + 1
        if seen[nm] > 1:
            clean[i] = f"{nm} {seen[nm]}"

    master = [f"SUP-{100 + i}" for i in range(n)]

    regions = list(cfg["baseline"]["region_mix"])
    weights = np.array(list(cfg["baseline"]["region_mix"].values()), dtype=float)
    weights = weights / weights.sum()
    src_region = rng.choice(regions, n, p=weights)
    c2r = R.country_region_map()
    by_region: dict[str, list[str]] = {}
    for c, r in c2r.items():
        by_region.setdefault(r, []).append(c)
    country = [rng.choice(by_region[r]) for r in src_region]

    lt_cfg = cfg["baseline"]["lead_time_days_by_region"]
    lead = np.array([rng.integers(*lt_cfg[r]) for r in src_region], dtype="int32")

    tier_mix = cfg["baseline"]["supplier_tier_mix"]
    tiers = rng.choice(list(tier_mix), n, p=np.array(list(tier_mix.values())))

    cats = list(R.TAXONOMY)
    supplies = rng.choice(cats, n)

    df = pd.DataFrame({
        "supplier_id": np.arange(1, n + 1, dtype="int32"),
        "supplier_master_id": master,
        "supplier_name": clean,          # dirt applied later, see apply_name_variants
        "supplier_name_clean": clean,
        "supplier_tier": tiers,
        "country": country,
        "region": src_region,
        "category": supplies,
        "payment_terms": rng.choice(R.PAYMENT_TERMS, n),
        "lead_time_days": lead,
        "minimum_order_qty": (rng.integers(1, 9, n) * 25).astype("int32"),
        "capacity_units_per_week": rng.integers(2_000, 40_000, n).astype("int32"),
        "financial_risk": rng.integers(5, 96, n).astype("int32"),
        "geopolitical_risk": np.nan,     # set from country below
        # Derived from fact_supplier_delivery after generation.
        "quality_score": np.nan,
        "on_time_rate": np.nan,
        "defect_rate": np.nan,
        "risk_score": np.nan,
        "risk_level": "",
    })

    geo_risk = {"North America": 22, "Europe": 28, "APAC": 61, "LATAM": 48, "MEA": 66}
    df["geopolitical_risk"] = (
        df["region"].map(geo_risk).to_numpy()
        + rng.integers(-8, 9, n)
    ).clip(0, 100).astype("int32")

    df["supplier_level1_region"] = df["region"]
    df["supplier_level2_category"] = df["category"]
    df["supplier_level3_tier"] = df["supplier_tier"]
    df["supplier_level4_name"] = df["supplier_name_clean"]

    unknown = pd.DataFrame([{
        "supplier_id": 0, "supplier_master_id": "SUP-000",
        "supplier_name": "No Alternate Supplier",
        "supplier_name_clean": "No Alternate Supplier",
        "supplier_tier": "None", "country": "None", "region": "None",
        "category": "None", "payment_terms": "None", "lead_time_days": 0,
        "minimum_order_qty": 0, "capacity_units_per_week": 0,
        "financial_risk": 0, "geopolitical_risk": 0, "quality_score": np.nan,
        "on_time_rate": np.nan, "defect_rate": np.nan, "risk_score": np.nan,
        "risk_level": "None", "supplier_level1_region": "None",
        "supplier_level2_category": "None", "supplier_level3_tier": "None",
        "supplier_level4_name": "No Alternate Supplier",
    }])
    return pd.concat([unknown, df], ignore_index=True)


def build_name_variants(dim_supplier: pd.DataFrame, count: int,
                        rng) -> dict[int, list[str]]:
    """Deliberate dirt: give `count` suppliers several name SPELLINGS.

    A dimension row can only carry one name, so renaming the dimension would
    just rename the supplier -- it would not split anything. The variants are
    therefore stamped per TRANSACTION (`supplier_name_raw` on the PO and
    delivery facts) while `supplier_id` / `supplier_master_id` stay clean.

    Grouping a dashboard on supplier_name_raw splits SUP-104's late deliveries
    across five strings and hides them; grouping on supplier_master_id shows
    the truth. Same dataset, two answers, one of them wrong.

    Returns {supplier_id: [spelling, ...]}. Suppliers not in the dict use their
    clean name for every transaction.
    """
    variants: dict[int, list[str]] = {}
    if count <= 0:
        return variants
    real = dim_supplier[dim_supplier["supplier_id"] > 0]
    pick = rng.choice(real["supplier_id"].to_numpy(),
                      size=min(count, len(real)), replace=False)
    clean_by_id = dict(zip(real["supplier_id"], real["supplier_name_clean"]))
    for sid in pick:
        clean = clean_by_id[sid]
        spellings = [clean]
        for rule in R.NAME_VARIANT_RULES:
            v = rule(clean)
            if v not in spellings:          # skip rules that are a no-op here
                spellings.append(v)
        variants[int(sid)] = spellings[:5]
    return variants


def force_variants_on(variants: dict[int, list[str]], dim_supplier: pd.DataFrame,
                      master_ids: list[str], rng) -> dict[int, list[str]]:
    """Guarantee the event-pinned suppliers are among the messy ones.

    Without this the dirt lands at random and the entity-resolution demo may
    not touch SUP-104 at all, which is the only supplier anyone drills into.
    """
    lookup = dict(zip(dim_supplier["supplier_master_id"], dim_supplier["supplier_id"]))
    for mid in master_ids:
        sid = lookup.get(mid)
        if sid is None or sid in variants:
            continue
        clean = dim_supplier.loc[dim_supplier["supplier_id"] == sid,
                                 "supplier_name_clean"].iloc[0]
        spellings = [clean]
        for rule in R.NAME_VARIANT_RULES:
            v = rule(clean)
            if v not in spellings:
                spellings.append(v)
        variants[int(sid)] = spellings[:5]
    return variants


# ---------------------------------------------------------------------------
# dim_product  (base attributes; abc/xyz and planning params filled later)
# ---------------------------------------------------------------------------
def build_dim_product(n: int, dim_supplier: pd.DataFrame, dim_cat: pd.DataFrame,
                      rng, cfg) -> pd.DataFrame:
    mix = cfg["baseline"]["category_mix"]
    cats = list(mix)
    p = np.array([mix[c] for c in cats], dtype=float)
    p = p / p.sum()
    category = rng.choice(cats, n, p=p)
    subcategory = np.array([rng.choice(R.TAXONOMY[c]) for c in category], dtype=object)

    fam = []
    for c in category:
        pool = R.FAMILIES.get(c, R.DEFAULT_FAMILIES)
        fam.append(rng.choice(pool))
    brand = rng.choice(R.BRANDS, n)

    cat_key = {f"{r.category}|{r.subcategory}": r.product_category_id
               for r in dim_cat.itertuples()}
    product_category_id = np.array(
        [cat_key[f"{c}|{s}"] for c, s in zip(category, subcategory)], dtype="int32")

    unit_cost = np.round(np.exp(rng.normal(3.0, 1.05, n)), 2).clip(0.75, 4_000)
    margin = cfg["baseline"]["base_gross_margin_pct"]
    price = np.round(unit_cost / (1 - margin) * rng.uniform(0.9, 1.15, n), 2)

    # Suppliers are matched on the category they actually supply where possible.
    real = dim_supplier[dim_supplier["supplier_id"] > 0]
    primary = np.empty(n, dtype="int32")
    secondary = np.zeros(n, dtype="int32")
    for c in cats:
        idx = np.flatnonzero(category == c)
        if idx.size == 0:
            continue
        pool = real.loc[real["category"] == c, "supplier_id"].to_numpy()
        if pool.size == 0:
            pool = real["supplier_id"].to_numpy()
        primary[idx] = rng.choice(pool, idx.size)
        if pool.size > 1:
            alt = rng.choice(pool, idx.size)
            # Only ~70% get a genuine alternate; the rest are single-sourced.
            has_alt = rng.random(idx.size) < 0.70
            secondary[idx] = np.where(has_alt & (alt != primary[idx]), alt, 0)

    is_mfg = np.isin(subcategory, list(R.MANUFACTURED))
    is_raw = category == R.RAW_MATERIAL_CATEGORY
    product_type = np.where(is_raw, "Raw Material",
                            np.where(is_mfg, "Finished Good", "Component"))

    crit_mix = cfg["classification"]["criticality_mix"]
    criticality = rng.choice(list(crit_mix), n, p=np.array(list(crit_mix.values())))

    sup_country = dim_supplier.set_index("supplier_id")["country"]

    df = pd.DataFrame({
        "product_id": np.arange(1, n + 1, dtype="int32"),
        "product_sku": [f"SKU-{i:06d}" for i in range(1, n + 1)],
        "product_name": "",
        "category": category,
        "subcategory": subcategory,
        "product_category_id": product_category_id,
        "brand": brand,
        "product_family": fam,
        "product_type": product_type,
        "material": rng.choice(R.MATERIALS, n),
        "unit_cost": unit_cost,
        "standard_price": price,
        "weight_kg": np.round(np.exp(rng.normal(0.4, 1.0, n)), 3).clip(0.01, 900),
        "volume_m3": np.round(np.exp(rng.normal(-3.2, 0.9, n)), 4).clip(0.0001, 12),
        "shelf_life_days": np.where(rng.random(n) < 0.14,
                                    rng.integers(90, 731, n), 0).astype("int32"),
        "criticality": criticality,
        "primary_supplier_id": primary,
        "secondary_supplier_id": secondary,
        "single_source_flag": (secondary == 0).astype("int8"),
        "country_of_origin": sup_country.reindex(primary).to_numpy(),
        # Derived after demand generation.
        "abc_class": "",
        "xyz_class": "",
        "lead_time_days": 0,
        "safety_stock_days": 0,
    })

    df["product_name"] = [
        f"{b} {f} {s[:-1] if s.endswith('s') else s} {i % 900 + 100}"
        for b, f, s, i in zip(brand, fam, subcategory, df["product_id"])
    ]

    df["product_level1_category"] = df["category"]
    df["product_level2_subcategory"] = df["subcategory"]
    df["product_level3_brand"] = df["brand"]
    df["product_level4_family"] = df["product_family"]
    df["product_level5_product"] = df["product_name"]
    df["product_level6_sku"] = df["product_sku"]
    return df


# ---------------------------------------------------------------------------
# dim_customer / dim_employee
# ---------------------------------------------------------------------------
def build_dim_customer(n: int, dim_location: pd.DataFrame, rng, cfg) -> pd.DataFrame:
    mix = cfg["baseline"]["region_mix"]
    p = np.array(list(mix.values()), dtype=float)
    p = p / p.sum()
    region = rng.choice(list(mix), n, p=p)

    loc_by_region: dict[str, np.ndarray] = {
        r: g["location_id"].to_numpy()
        for r, g in dim_location.groupby("region", observed=True)
    }
    all_loc = dim_location["location_id"].to_numpy()
    primary_loc = np.array(
        [rng.choice(loc_by_region.get(r, all_loc)) for r in region], dtype="int32")

    names = [f"{rng.choice(R.CUSTOMER_PREFIXES)} {rng.choice(R.CUSTOMER_SUFFIXES)}"
             for _ in range(n)]
    seen: dict[str, int] = {}
    for i, nm in enumerate(names):
        seen[nm] = seen.get(nm, 0) + 1
        if seen[nm] > 1:
            names[i] = f"{nm} {seen[nm]}"

    seg = rng.choice(R.CUSTOMER_SEGMENTS, n, p=[0.10, 0.22, 0.38, 0.18, 0.12])
    c2r = R.country_region_map()
    by_region: dict[str, list[str]] = {}
    for c, r in c2r.items():
        by_region.setdefault(r, []).append(c)

    return pd.DataFrame({
        "customer_id": np.arange(1, n + 1, dtype="int32"),
        "customer_name": names,
        "customer_segment": seg,
        "country": [rng.choice(by_region[r]) for r in region],
        "region": region,
        "primary_location_id": primary_loc,
        "service_level_agreement_days": rng.choice([2, 3, 5, 7, 10], n).astype("int32"),
        "cust_level1_segment": seg,
        "cust_level2_region": region,
        "cust_level3_customer": names,
    })


def build_dim_employee(n: int, dim_location: pd.DataFrame, rng) -> pd.DataFrame:
    names = [f"{rng.choice(R.FIRST_NAMES)} {rng.choice(R.LAST_NAMES)}" for _ in range(n)]
    return pd.DataFrame({
        "employee_id": np.arange(1, n + 1, dtype="int32"),
        "employee_name": names,
        "role": rng.choice(R.EMPLOYEE_ROLES, n),
        "region": rng.choice(dim_location["region"].unique(), n),
        "location_id": rng.choice(dim_location["location_id"].to_numpy(), n).astype("int32"),
        "hire_date": pd.to_datetime("2015-01-01")
                     + pd.to_timedelta(rng.integers(0, 3800, n), unit="D"),
    })
