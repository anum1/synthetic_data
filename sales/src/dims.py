"""Dimension builders. Every hierarchy is emitted both as keys and as
flattened level columns, because Tableau cannot walk a parent-child column.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import catalog as cat
import geography as geo

# Categories whose SKUs come in colors; software/services do not.
_PHYSICAL = {"Electronics", "Peripherals", "Networking", "Components"}

# Product generation cadence, in months.
REFRESH_MONTHS = 14        # gap between consecutive generations of a family
NEWEST_AGE_MONTHS = 6      # how long ago the current generation launched
LIFESPAN_MONTHS = 42       # how long a generation stays on sale after launch
GEN_PRICE_UPLIFT = 1.025   # price uplift per generation refresh


def _add_months(d: dt.date, months: int) -> dt.date:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 or not year % 400) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month])
    return dt.date(year, month + 1, day)


def _months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


# ------------------------------------------------- conformed plan dimensions --
def build_dim_country() -> pd.DataFrame:
    """Country-grain geography dimension.

    Budget and forecast sit at region x country grain, coarser than the sales
    fact. Both need to relate to ONE shared dimension or plan-vs-actual breaks:
    dim_location has repeated region values, so it cannot be the "one" side of
    a relationship at that grain. This table can.
    """
    seen, rows = set(), []
    for region, country, code, currency, *_ in geo.CITIES:
        if country in seen:
            continue
        seen.add(country)
        rows.append({"country": country, "country_code": code, "region": region,
                     "market": geo.MARKETS.get(country, "Other"),
                     "currency_code": currency})
    df = pd.DataFrame(rows).sort_values(["region", "country"]).reset_index(drop=True)
    df.insert(0, "country_id", np.arange(1, len(df) + 1, dtype="int32"))
    df["geo_level1_global"] = "Global"
    df["geo_level2_region"] = df["region"]
    df["geo_level3_country"] = df["country"]
    return df


def build_dim_product_category() -> pd.DataFrame:
    """Category/subcategory dimension at the planning grain, for the same
    reason as dim_country: dim_product repeats subcategory values."""
    rows = [{"category": category, "subcategory": subcategory}
            for category, subs in cat.TAXONOMY.items() for subcategory in subs]
    df = pd.DataFrame(rows).reset_index(drop=True)
    df.insert(0, "product_category_id", np.arange(1, len(df) + 1, dtype="int32"))
    df["product_level1_category"] = df["category"]
    df["product_level2_subcategory"] = df["subcategory"]
    return df


# ---------------------------------------------------------------- channels --
def build_dim_channel(mix: dict) -> pd.DataFrame:
    groups = {"Direct Sales": "Direct", "Online": "Digital", "Partner": "Indirect",
              "Retail Store": "Physical", "Distributor": "Indirect"}
    rows = [{"channel_id": i,
             "sales_channel": name,
             "channel_group": groups.get(name, "Other"),
             "is_digital": int(name in ("Online",)),
             "target_mix_pct": round(share, 4)}
            for i, (name, share) in enumerate(mix.items(), start=1)]
    return pd.DataFrame(rows)


# -------------------------------------------------------------- currencies --
def build_dim_currency() -> pd.DataFrame:
    used = sorted({c[3] for c in geo.CITIES})
    return pd.DataFrame([{"currency_code": c,
                          "currency_name": geo.CURRENCY_NAMES[c],
                          "is_reporting_currency": int(c == "USD")}
                         for c in used])


def build_dim_exchange_rate(months: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    """Monthly rate per currency, as a gentle random walk off the base rate."""
    rows = []
    for code, base in geo.BASE_FX.items():
        if code not in {c[3] for c in geo.CITIES}:
            continue
        drift = 1.0
        for m in months:
            if code != "USD":
                drift *= float(np.exp(rng.normal(0.0, 0.011)))
                drift = min(max(drift, 0.80), 1.25)
            rate = base * drift
            rows.append({
                "year_month_key": m.year * 100 + m.month,
                "year_month": f"{m.year}-{m.month:02d}",
                "currency_code": code,
                "rate_to_usd": round(1.0 / rate, 8),   # multiply local -> USD
                "usd_to_local": round(rate, 6),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------- suppliers --
def build_dim_supplier(n: int, rng: np.random.Generator, timeline) -> pd.DataFrame:
    groups = cat.SUPPLIER_GROUPS
    regions = ["APAC", "North America", "Europe", "LATAM"]
    tiers = ["Tier 1", "Tier 2", "Tier 3"]
    categories = ["Components", "Assembly", "Logistics", "Packaging",
                  "Software Licensing", "Contract Manufacturing"]
    terms = ["Net 30", "Net 45", "Net 60", "Net 90", "2/10 Net 30"]

    grp = rng.choice(groups, size=n, p=_group_weights(len(groups)))
    reg = rng.choice(regions, size=n, p=[0.46, 0.24, 0.22, 0.08])
    tier = rng.choice(tiers, size=n, p=[0.28, 0.45, 0.27])
    quality = np.clip(rng.normal(88, 7, n), 55, 99.5).round(1)
    risk = np.select(
        [quality >= 92, quality >= 82, quality >= 70],
        ["Low", "Moderate", "Elevated"], default="High")

    start = timeline.start_date - dt.timedelta(days=1500)
    contract_start = [start + dt.timedelta(days=int(x)) for x in rng.integers(0, 1400, n)]

    df = pd.DataFrame({
        "supplier_id": np.arange(1, n + 1),
        "supplier_name": [f"{grp[i]} {chr(65 + i % 26)}{i + 101:04d}" for i in range(n)],
        "supplier_group": grp,
        "supplier_region": reg,
        "country": [rng.choice([c[1] for c in geo.CITIES if c[0] == r]) for r in reg],
        "supplier_tier": tier,
        "supplier_category": rng.choice(categories, size=n),
        "payment_terms": rng.choice(terms, size=n, p=[0.34, 0.22, 0.26, 0.10, 0.08]),
        "contract_start_date": contract_start,
        "contract_end_date": [d + dt.timedelta(days=int(x))
                              for d, x in zip(contract_start, rng.integers(900, 2600, n))],
        "quality_rating": quality,
        "risk_rating": risk,
        "default_lead_time_days": np.clip(rng.normal(21, 9, n), 3, 75).astype(int),
        "is_strategic_supplier": (rng.random(n) < 0.18).astype("int8"),
    })
    # Flattened hierarchy: Region > Group > Tier > Supplier
    df["supplier_level1_region"] = df["supplier_region"]
    df["supplier_level2_group"] = df["supplier_group"]
    df["supplier_level3_tier"] = df["supplier_tier"]
    df["supplier_level4_name"] = df["supplier_name"]
    return df


def _group_weights(k: int) -> np.ndarray:
    """Front-loaded weights so the first group (Global Components) is dominant."""
    w = np.array([0.26] + [(1 - 0.26) / (k - 1)] * (k - 1))
    return w / w.sum()


# ---------------------------------------------------------------- products --
def build_dim_product(n_target: int, supplier_ids: np.ndarray, supplier_groups: np.ndarray,
                      rng: np.random.Generator, timeline, launch_cfg: dict | None,
                      target_margin: float, expected_discount: float,
                      shipping_rate: float,
                      shock_group: str | None = None,
                      shock_subcategories: tuple[str, ...] = (),
                      category_key: dict | None = None) -> pd.DataFrame:
    rows = []
    pid = 0
    for category, subs in cat.TAXONOMY.items():
        for subcategory, families in subs.items():
            variants = cat.VARIANTS.get(subcategory, cat.DEFAULT_VARIANTS)
            colors = cat.COLORS if category in _PHYSICAL else ["-"]
            # Price variety comes from the variant ladder (entry -> top of range),
            # not from the generation. Real refreshes hold the price point, so a
            # generation only carries a small uplift; otherwise average selling
            # price would climb every year and swamp the configured growth rate.
            vmax = max(v[2] for v in variants)
            for brand, family, prefix, n_models, lo, hi, margin in families:
                v_span = ((hi / lo) - 1) / (vmax - 1) if vmax > 1 else 0.0
                for gen in range(1, n_models + 1):
                    product_name = f"{family} {prefix}{gen}"
                    base_price = lo * GEN_PRICE_UPLIFT ** (gen - 1)
                    for vsuffix, vlabel, vmult in variants:
                        for color in colors:
                            pid += 1
                            csuffix = "" if color == "-" else f"-{color[:3].upper()}"
                            rows.append({
                                "product_id": pid,
                                "sku": f"{prefix}{gen}-{vsuffix}{csuffix}",
                                "product_name": product_name,
                                "sku_description": f"{product_name} {vlabel}"
                                                   + ("" if color == "-" else f" {color}"),
                                "category": category,
                                "subcategory": subcategory,
                                "brand": brand,
                                "product_family": family,
                                "variant": vlabel,
                                "color": None if color == "-" else color,
                                "generation": gen,
                                "list_price": round(base_price * (1 + (vmult - 1) * v_span), 2),
                                "_margin": margin,
                                "_n_models": n_models,
                            })

    df = pd.DataFrame(rows)
    df = _sample_products(df, n_target, launch_cfg, rng)
    _SHOCK_SUBCATS.clear()
    _SHOCK_SUBCATS.update(shock_subcategories)

    n = len(df)

    # Product generations follow a refresh cadence: generation g of n launched
    # (n - g) refresh cycles ago. Launch date, lifecycle stage and retirement
    # are all derived from that one timeline so they can never disagree.
    refresh = REFRESH_MONTHS
    months_ago = (df["_n_models"] - df["generation"]) * refresh + NEWEST_AGE_MONTHS
    jitter = rng.integers(-45, 46, n)
    df["product_launch_date"] = [
        _add_months(timeline.as_of_date, -int(m)) + dt.timedelta(days=int(j))
        for m, j in zip(months_ago, jitter)
    ]
    df["product_end_date"] = [
        _add_months(d0, LIFESPAN_MONTHS) for d0 in df["product_launch_date"]
    ]

    # The launch event's hero product must go on sale exactly when the event says.
    if launch_cfg:
        launch_month = timeline.offset_month(int(launch_cfg["launch_offset"]))
        is_new = df["product_name"] == launch_cfg["new_product"]
        df.loc[is_new, "product_launch_date"] = launch_month
        df.loc[is_new, "product_end_date"] = _add_months(launch_month, LIFESPAN_MONTHS)

    age_months = np.array([_months_between(d0, timeline.as_of_date)
                           for d0 in df["product_launch_date"]])
    retired = np.array([d1 <= timeline.as_of_date for d1 in df["product_end_date"]])
    df["product_lifecycle_stage"] = np.select(
        [retired, age_months <= 9, age_months <= 26],
        ["End of Life", "Growth", "Mature"], default="Decline")
    # Retired products keep an end date; live ones leave it open.
    df["product_end_date"] = [d1 if r else None
                              for d1, r in zip(df["product_end_date"], retired)]

    # Intrinsic appeal of the SKU, independent of where it sits in its life.
    # The age-dependent part of demand is applied per month during fact
    # generation, so a product that is end-of-life today still sold well in
    # the year it launched.
    price_w = (df["list_price"].max() / df["list_price"].clip(lower=1.0)) ** 0.42
    df["demand_weight"] = (price_w * rng.lognormal(0, 0.55, n)).round(6)

    # Cost is calibrated against the price actually realised (list less the
    # expected discount), so the blended REALISED margin matches the scenario
    # target instead of a list-price margin the dashboards never see.
    margins = _calibrate_margins(df["_margin"].to_numpy(),
                                 df["demand_weight"].to_numpy() * df["list_price"].to_numpy(),
                                 target_margin, shipping_rate)
    df["target_margin_pct"] = margins.round(6)
    net_price = df["list_price"] * (1 - expected_discount)
    noise = rng.normal(0, 0.018, n)
    df["standard_cost"] = (net_price * (1 - margins - shipping_rate + noise)).round(2)
    df["standard_cost"] = df["standard_cost"].clip(lower=(df["list_price"] * 0.06).round(2))

    df["supplier_id"] = _assign_suppliers(df, supplier_ids, supplier_groups,
                                          rng, shock_group)

    df["is_premium"] = (df["list_price"] > df.groupby("subcategory")["list_price"]
                        .transform("median") * 1.4).astype("int8")
    df["is_new_product"] = (pd.to_datetime(df["product_launch_date"])
                            >= pd.Timestamp(timeline.as_of_date) - pd.Timedelta(days=365)
                            ).astype("int8")
    df["is_discontinued"] = (df["product_lifecycle_stage"] == "End of Life").astype("int8")
    df["is_active"] = (1 - df["is_discontinued"]).astype("int8")

    # Flattened hierarchy: Category > Subcategory > Brand > Family > Product > SKU
    df["product_category_id"] = (df["category"] + "|" + df["subcategory"]) \
        .map(category_key).astype("int32")

    df["product_level1_category"] = df["category"]
    df["product_level2_subcategory"] = df["subcategory"]
    df["product_level3_brand"] = df["brand"]
    df["product_level4_family"] = df["product_family"]
    df["product_level5_product"] = df["product_name"]
    df["product_level6_sku"] = df["sku"]

    return df.drop(columns=["_margin", "_n_models"]).reset_index(drop=True)


_SHOCK_SUBCATS: set[str] = set()


def _assign_suppliers(df: pd.DataFrame, supplier_ids: np.ndarray,
                      supplier_groups: np.ndarray, rng: np.random.Generator,
                      shock_group: str | None) -> np.ndarray:
    """Sourcing model: each product family has a primary supplier, with a
    minority of SKUs dual-sourced to a secondary.

    Families in the shock subcategories are pinned to the shock supplier group,
    so a cost increase there is material enough to move the company margin and
    traces cleanly through to the affected products.
    """
    families = df["product_family"].to_numpy()
    subcats = df["subcategory"].to_numpy()
    uniq = pd.unique(families)

    in_group = np.flatnonzero(supplier_groups == shock_group) if shock_group else np.array([])
    out_group = np.flatnonzero(supplier_groups != shock_group) if shock_group \
        else np.arange(len(supplier_ids))

    primary: dict[str, int] = {}
    for i, fam in enumerate(uniq):
        fam_sub = subcats[families == fam][0]
        pinned = len(in_group) and fam_sub in _SHOCK_SUBCATS
        pool = in_group if pinned else out_group
        # Round-robin over the pool so every supplier picks up products;
        # a purely random draw would leave many suppliers orphaned.
        primary[fam] = int(supplier_ids[pool[i % len(pool)]])
    # Secondary sourcing is drawn per SKU across the whole base, so suppliers
    # outside the 31 family primaries still carry product volume.
    use_primary = rng.random(len(df)) < 0.78
    fallback = supplier_ids[rng.integers(0, len(supplier_ids), len(df))]
    return np.where(use_primary, np.array([primary[f] for f in families]), fallback)


def _calibrate_margins(family_margins: np.ndarray, revenue_weight: np.ndarray,
                       target: float, shipping_rate: float,
                       iterations: int = 12) -> np.ndarray:
    """Shift every family margin by a constant so the blended margin hits target.

    A uniform additive shift preserves the relative ordering of categories
    (software stays the most profitable, budget hardware the least) while
    letting one config knob move the company-wide margin.
    """
    w = revenue_weight / revenue_weight.sum()
    m = family_margins.copy()
    for _ in range(iterations):
        blended = float((m * w).sum())
        gap = target - blended
        if abs(gap) < 1e-5:
            break
        m = np.clip(m + gap, 0.04, 0.85)
    return m


def _sample_products(df: pd.DataFrame, n_target: int, launch_cfg: dict | None,
                     rng: np.random.Generator) -> pd.DataFrame:
    """Trim the full catalog to the tier size, protecting event-critical products."""
    if n_target >= len(df):
        return df
    protected = set()
    if launch_cfg:
        protected |= {launch_cfg.get("new_product"), launch_cfg.get("incumbent_product")}
    keep_mask = df["product_name"].isin(protected)
    # Keep at least one SKU of every product so no hierarchy branch goes empty.
    first_of_product = ~df.duplicated("product_name")
    must_keep = keep_mask | first_of_product

    pool = df.index[~must_keep].to_numpy()
    n_extra = max(n_target - int(must_keep.sum()), 0)
    chosen = rng.choice(pool, size=min(n_extra, len(pool)), replace=False)
    out = df.loc[sorted(set(df.index[must_keep]) | set(chosen))].copy()
    out["product_id"] = np.arange(1, len(out) + 1)
    return out


# --------------------------------------------------------------- locations --
def build_dim_location(n: int, region_mix: dict, rng: np.random.Generator,
                       country_key: dict) -> pd.DataFrame:
    cities = pd.DataFrame(geo.CITIES, columns=geo.COLUMNS)
    # Draw cities in proportion to the configured region mix.
    weights = cities["region"].map(region_mix).fillna(0.05)
    weights = (weights / cities.groupby("region")["region"].transform("size")).to_numpy()
    weights = weights / weights.sum()
    idx = rng.choice(len(cities), size=n, p=weights)
    df = cities.iloc[idx].reset_index(drop=True)

    loc_types = ["Distribution Center", "Retail Store", "Sales Office",
                 "Warehouse", "Service Center"]
    store_types = ["Flagship", "Standard", "Outlet", "Kiosk", "N/A"]
    lt = rng.choice(loc_types, size=n, p=[0.14, 0.42, 0.22, 0.14, 0.08])

    df["location_id"] = np.arange(1, n + 1)
    df["location_type"] = lt
    df["store_type"] = np.where(lt == "Retail Store",
                                rng.choice(store_types[:4], size=n, p=[0.12, 0.56, 0.24, 0.08]),
                                "N/A")
    df["location_name"] = [f"{c} {t.split()[0]} {i:03d}"
                           for c, t, i in zip(df["city"], lt, df["location_id"])]
    df["market"] = df["country"].map(geo.MARKETS).fillna("Other")
    df["territory"] = df["market"] + " - " + df["state"]
    # Jitter coordinates so co-located rows do not stack on the map.
    df["latitude"] = (df["latitude"] + rng.normal(0, 0.06, n)).round(5)
    df["longitude"] = (df["longitude"] + rng.normal(0, 0.06, n)).round(5)
    df["opened_date"] = None
    df["is_active"] = (rng.random(n) > 0.04).astype("int8")

    df["geo_level1_global"] = "Global"
    df["geo_level2_region"] = df["region"]
    df["geo_level3_country"] = df["country"]
    df["geo_level4_state"] = df["state"]
    df["geo_level5_city"] = df["city"]
    df["geo_level6_location"] = df["location_name"]

    df["country_id"] = df["country"].map(country_key).astype("int32")

    cols = ["location_id", "location_name", "location_type", "store_type",
            "country_id", "region", "country", "country_code", "state", "city",
            "market", "territory", "currency_code", "latitude", "longitude",
            "is_active"] + [c for c in df.columns if c.startswith("geo_level")]
    return df[cols]


# --------------------------------------------------------------- customers --
_LEGAL = ["Corp", "Inc", "Group", "Holdings", "Systems", "Solutions",
          "Industries", "Partners", "Labs", "Technologies", "Networks", "Global"]
_STEM = ["Global", "Apex", "Vertex", "Summit", "Pinnacle", "Northstar", "Blue Ridge",
         "Silverline", "Ironwood", "Cobalt", "Redwood", "Harbor", "Lighthouse",
         "Quantum", "Meridian", "Catalyst", "Beacon", "Cornerstone", "Evergreen",
         "Falcon", "Granite", "Horizon", "Keystone", "Lakeshore", "Momentum",
         "Nova", "Orchard", "Paramount", "Riverstone", "Sterling", "Trailhead",
         "Unity", "Vantage", "Westgate", "Zenith", "Anchor", "Bridgeport"]
_SUFFIX = ["Tech", "Med", "Manufacturing", "Financial", "Retail", "Energy",
           "Logistics", "Data", "Cloud", "Digital", "Works", "Dynamics"]


def build_dim_customer(n: int, locations: pd.DataFrame, rep_ids: np.ndarray,
                       channels: list[str], rng: np.random.Generator,
                       timeline, contraction_cfg: dict | None) -> pd.DataFrame:
    seg = rng.choice(cat.CUSTOMER_SEGMENTS, size=n, p=[0.14, 0.26, 0.38, 0.22])
    tier = np.where(
        seg == "Enterprise",
        rng.choice(cat.CUSTOMER_TIERS, size=n, p=[0.42, 0.34, 0.16, 0.08]),
        rng.choice(cat.CUSTOMER_TIERS, size=n, p=[0.06, 0.46, 0.30, 0.18]))
    industry = rng.choice(cat.INDUSTRIES, size=n)

    stems = rng.choice(_STEM, size=n)
    sufs = rng.choice(_SUFFIX, size=n)
    legal = rng.choice(_LEGAL, size=n)
    names = [f"{a}{b} {c}" for a, b, c in zip(stems, sufs, legal)]
    # Guarantee uniqueness without losing the readable style.
    seen: dict[str, int] = {}
    for i, nm in enumerate(names):
        if nm in seen:
            seen[nm] += 1
            names[i] = f"{nm} {seen[nm] + 1}"
        else:
            seen[nm] = 1

    loc_idx = rng.integers(0, len(locations), n)
    home = locations.iloc[loc_idx].reset_index(drop=True)

    since_span = (timeline.as_of_date - (timeline.start_date - dt.timedelta(days=3650))).days
    since = [timeline.start_date - dt.timedelta(days=3650) + dt.timedelta(days=int(x))
             for x in rng.integers(0, since_span, n)]

    rev_band_by_seg = {
        "Enterprise": ["$500M-$1B", "$1B+", "$250M-$500M"],
        "Mid-Market": ["$50M-$250M", "$250M-$500M", "$10M-$50M"],
        "SMB": ["$1M-$10M", "$10M-$50M", "<$1M"],
        "Consumer": ["<$1M", "<$1M", "$1M-$10M"],
    }
    bands = [rng.choice(rev_band_by_seg[s]) for s in seg]

    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "customer_name": names,
        "customer_type": np.where(seg == "Consumer", "Individual", "Business"),
        "customer_segment": seg,
        "industry": np.where(seg == "Consumer", "Consumer", industry),
        "customer_tier": tier,
        "country": home["country"], "region": home["region"],
        "state": home["state"], "city": home["city"],
        "currency_code": home["currency_code"],
        "primary_location_id": home["location_id"],
        "sales_channel": rng.choice(channels, size=n),
        "account_manager_id": rng.choice(rep_ids, size=n),
        "customer_since_date": since,
        "credit_rating": rng.choice(["AAA", "AA", "A", "BBB", "BB", "B"], size=n,
                                    p=[0.06, 0.14, 0.26, 0.29, 0.17, 0.08]),
        "payment_terms": rng.choice(["Net 30", "Net 45", "Net 60", "Prepaid", "Credit Card"],
                                    size=n, p=[0.38, 0.16, 0.14, 0.10, 0.22]),
        "annual_revenue_band": bands,
        "is_active": (rng.random(n) > 0.05).astype("int8"),
    })
    df["is_strategic_customer"] = ((df["customer_tier"] == "Strategic") &
                                   (df["customer_segment"] == "Enterprise")).astype("int8")

    # Spend propensity drives how much of total volume each customer absorbs.
    seg_weight = df["customer_segment"].map(
        {"Enterprise": 12.0, "Mid-Market": 4.0, "SMB": 1.4, "Consumer": 0.35})
    df["_spend_weight"] = seg_weight * rng.lognormal(0, 0.75, n)

    # The contraction event needs a specific, large, named customer.
    if contraction_cfg:
        target = contraction_cfg["customer_name"]
        i = int(df["_spend_weight"].idxmax())
        df.loc[i, ["customer_name", "customer_segment", "customer_tier",
                   "industry", "is_strategic_customer", "customer_type",
                   "annual_revenue_band", "is_active"]] = \
            [target, "Enterprise", "Strategic", "Technology", 1, "Business", "$1B+", 1]
        # Force this customer to the configured share of company revenue.
        share = float(contraction_cfg.get("revenue_share", 0.04))
        others = df["_spend_weight"].drop(index=i).sum()
        df.loc[i, "_spend_weight"] = others * share / (1 - share)

    ltv = df["_spend_weight"] * rng.uniform(18_000, 42_000, n)
    df["customer_lifetime_value"] = ltv.round(2)

    df["cust_level1_segment"] = df["customer_segment"]
    df["cust_level2_industry"] = df["industry"]
    df["cust_level3_tier"] = df["customer_tier"]
    df["cust_level4_customer"] = df["customer_name"]
    return df


# -------------------------------------------------------------- promotions --
def build_dim_promotion(n: int, timeline, rng: np.random.Generator,
                        promo_cfg: dict | None) -> pd.DataFrame:
    tpl = cat.PROMOTION_TEMPLATES
    categories = list(cat.TAXONOMY)
    segments = cat.CUSTOMER_SEGMENTS + ["All Segments"]
    rows = []
    span_days = (timeline.end_date - timeline.start_date).days

    for i in range(1, n + 1):
        name, pcat, ptype, disc, channel = tpl[(i - 1) % len(tpl)]
        start = timeline.start_date + dt.timedelta(days=int(rng.integers(0, span_days - 40)))
        length = int(rng.integers(7, 46))
        rows.append({
            "promotion_id": i,
            "promotion_name": f"{name} {start.year} #{i:03d}",
            "promotion_type": ptype,
            "promotion_category": pcat,
            "start_date": start,
            "end_date": start + dt.timedelta(days=length),
            "discount_pct": round(float(np.clip(disc + rng.normal(0, 0.025), 0.02, 0.45)), 4),
            "promotion_budget": float(round(rng.uniform(25_000, 1_200_000), 2)),
            "target_category": rng.choice(categories + ["All Categories"]),
            "target_segment": rng.choice(segments),
            "campaign_channel": channel,
        })

    df = pd.DataFrame(rows)
    # promotion_id 0 = "no promotion", so the fact table never needs a NULL key.
    none_row = {"promotion_id": 0, "promotion_name": "No Promotion",
                "promotion_type": "None", "promotion_category": "None",
                "start_date": timeline.start_date, "end_date": timeline.end_date,
                "discount_pct": 0.0, "promotion_budget": 0.0,
                "target_category": "All Categories", "target_segment": "All Segments",
                "campaign_channel": "None"}
    df = pd.concat([pd.DataFrame([none_row]), df], ignore_index=True)

    # The promotion-surge event gets a real, findable campaign row.
    if promo_cfg:
        start = timeline.offset_month(int(promo_cfg["start_offset"]))
        end_m = timeline.offset_month(int(promo_cfg["end_offset"]))
        end = (end_m + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        df.loc[len(df)] = {
            "promotion_id": int(df["promotion_id"].max()) + 1,
            "promotion_name": f"{promo_cfg['category']} Momentum {start.year}",
            "promotion_type": "Deep Discount", "promotion_category": "Seasonal",
            "start_date": start, "end_date": end,
            "discount_pct": round(float(promo_cfg["extra_discount_points"]), 4),
            "promotion_budget": 4_800_000.0,
            "target_category": promo_cfg["category"], "target_segment": "All Segments",
            "campaign_channel": "Multi-Channel",
        }
    return df


# ------------------------------------------------------------- sales reps ---
_FIRST = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery",
          "Quinn", "Rowan", "Skyler", "Emerson", "Harper", "Reese", "Devon", "Kai",
          "Sasha", "Noor", "Ines", "Mateo", "Lena", "Hugo", "Priya", "Yuki",
          "Omar", "Sofia", "Liam", "Nina", "Diego", "Anika", "Felix", "Mira"]
_LAST = ["Nguyen", "Okafor", "Silva", "Kowalski", "Ahmed", "Fischer", "Rossi",
         "Dubois", "Larsen", "Novak", "Reyes", "Tanaka", "Kim", "Patel", "Costa",
         "Weber", "Moreau", "Hansen", "Ivanov", "Muller", "Santos", "Bergman",
         "Alvarez", "Chen", "Osei", "Vargas", "Lindqvist", "Haddad", "Romano", "Park"]


def build_dim_sales_rep(n: int, regions: list[str], rng: np.random.Generator,
                        timeline) -> pd.DataFrame:
    """Four-level org: VP > Director (region) > Manager (team) > Rep."""
    def person(i: int) -> str:
        return f"{_FIRST[i % len(_FIRST)]} {_LAST[(i * 7 + 3) % len(_LAST)]}"

    vp = "Dana Whitfield"
    rows = []
    rid = 0
    reps_per_region = max(n // len(regions), 4)

    for r_i, region in enumerate(regions):
        director = person(r_i * 13 + 5) + " (Dir)"
        n_teams = max(reps_per_region // 8, 2)
        for t in range(n_teams):
            manager = person(r_i * 29 + t * 11 + 7) + " (Mgr)"
            team = f"{region} Team {t + 1}"
            for _ in range(max(reps_per_region // n_teams, 1)):
                rid += 1
                if rid > n:
                    break
                rows.append({
                    "sales_rep_id": rid,
                    "sales_rep_name": person(rid * 3 + r_i),
                    "sales_region": region,
                    "sales_team": team,
                    "territory": f"{region} T{(rid % 9) + 1}",
                    "manager_name": manager,
                    "director_name": director,
                    "vp_name": vp,
                })
    # Top up if integer division left us short.
    while len(rows) < n:
        rid += 1
        base = dict(rows[-1])
        base.update({"sales_rep_id": rid, "sales_rep_name": person(rid * 3 + 1)})
        rows.append(base)

    df = pd.DataFrame(rows).head(n)
    n = len(df)
    hire_span = (timeline.as_of_date - (timeline.start_date - dt.timedelta(days=4000))).days
    df["hire_date"] = [timeline.start_date - dt.timedelta(days=4000) + dt.timedelta(days=int(x))
                       for x in rng.integers(0, hire_span, n)]
    df["annual_quota"] = (rng.choice([600_000, 900_000, 1_200_000, 1_800_000, 2_400_000],
                                     size=n, p=[0.18, 0.28, 0.28, 0.18, 0.08])).astype(float)
    df["employment_status"] = np.where(rng.random(n) < 0.05, "Terminated", "Active")
    df["is_active"] = (df["employment_status"] == "Active").astype("int8")

    df["rep_level1_vp"] = df["vp_name"]
    df["rep_level2_region"] = df["sales_region"]
    df["rep_level3_director"] = df["director_name"]
    df["rep_level4_manager"] = df["manager_name"]
    df["rep_level5_rep"] = df["sales_rep_name"]
    return df
