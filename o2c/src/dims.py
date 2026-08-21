"""The small dimensions: warehouses, carriers, sales reps, terms, currency.

`dim_carrier` is one row per carrier x service level rather than per carrier.
Event 4 degrades a carrier across all of its services, and the demo question is
"which carriers have deteriorated" - but the follow-up is always "on which
service", and a carrier-only grain cannot answer it.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from o2cconfig import Scenario


def _expected_lines_per_warehouse_day(s: Scenario) -> float:
    """Average order lines per warehouse per day at the as-of date."""
    months = len(s.timeline.month_starts())
    growth = (1.0 + float(s.demand["annual_growth"])) ** (months / 12.0)
    orders_per_day = float(s.sizes["orders_per_month_base"]) * growth / 30.4
    lines = orders_per_day * (float(s.demand["lines_per_order_lambda"]) + 1.0)
    return lines / max(int(s.sizes["warehouses"]), 1)


def build_dim_warehouse(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["warehouses"])
    # Distribution roughly follows where the customers are.
    region_mix = {"NA": 0.50, "EMEA": 0.27, "APAC": 0.16, "LATAM": 0.07}
    regions, cities = [], []
    used = set()
    for i in range(n):
        reg = rng.choice(list(region_mix), p=list(region_mix.values()))
        pool = [c for c in R.WAREHOUSE_CITIES[reg] if (reg, c) not in used]
        if not pool:
            pool = R.WAREHOUSE_CITIES[reg]
        city = pool[int(rng.integers(len(pool)))]
        used.add((reg, city))
        regions.append(reg)
        cities.append(city)

    wtype = rng.choice(["Regional DC", "National DC", "Cross-Dock", "Branch"],
                       size=n, p=[0.46, 0.16, 0.12, 0.26])
    df = pd.DataFrame({
        "warehouse_id": np.arange(1, n + 1, dtype="int32"),
        "warehouse_code": [f"WH-{i:02d}" for i in range(1, n + 1)],
        "warehouse_name": [f"{c} {t}" for c, t in zip(cities, wtype)],
        "warehouse_type": wtype,
        "city": cities,
        "region": regions,
        "country": [{"NA": "United States", "EMEA": "Germany",
                     "APAC": "Singapore", "LATAM": "Brazil"}[r] for r in regions],
        # Daily order-line throughput, sized off the volume this tier actually
        # generates rather than a fixed range. A capacity number chosen in the
        # abstract is either never binding (and Event 3 does nothing) or always
        # binding (and every warehouse is late) - and which one it is changes
        # silently with the tier.
        "daily_line_capacity": np.maximum(
            4, np.round(_expected_lines_per_warehouse_day(s)
                        * rng.uniform(2.2, 3.6, n))).astype("int32"),
        "storage_sqft": (rng.integers(20, 420, n) * 1000).astype("int32"),
        "opened_date": [dt.date(2005, 1, 1) + dt.timedelta(days=int(rng.integers(0, 6000)))
                        for _ in range(n)],
        "is_active": 1,
    })
    return df


def build_dim_carrier(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    """Carrier x service level. Event 4 targets a carrier name across services."""
    target = int(s.sizes["carriers"])
    rows = []
    cid = 1
    for name in R.CARRIER_NAMES:
        for svc, transit_mult, cost_mult, expedited in R.SERVICE_LEVELS:
            rows.append((cid, f"CAR-{cid:03d}", name, svc,
                         f"{name} {svc}", transit_mult, cost_mult, expedited))
            cid += 1
    df = pd.DataFrame(rows, columns=[
        "carrier_id", "carrier_code", "carrier_name", "service_level",
        "carrier_service_name", "transit_multiplier", "cost_multiplier",
        "is_expedited"])

    # Trim to the tier size, but never drop the carrier the event targets, and
    # never leave a carrier with no ground service to fall back on.
    ev = s.event("carrier_deterioration")
    protected = ev["carrier_name"] if ev else R.CARRIER_NAMES[0]
    keep = df["carrier_name"].eq(protected) | df["service_level"].eq("Ground")
    extra = df[~keep]
    room = max(0, target - int(keep.sum()))
    if room and len(extra):
        chosen = extra.sample(n=min(room, len(extra)), random_state=int(s.seed)).index
        keep = keep | df.index.isin(chosen)
    df = df[keep].reset_index(drop=True)
    df["carrier_id"] = np.arange(1, len(df) + 1, dtype="int32")

    # Baseline reliability differs by carrier, before any event is applied. The
    # carrier Event 4 degrades is pinned to the network average rather than left
    # to the draw, so the documented before/after ("94% -> 71%") is the number
    # the data actually shows instead of whatever the seed happened to produce.
    names = df["carrier_name"].unique()
    base = {nm: float(np.clip(rng.normal(0.94, 0.028), 0.88, 0.975)) for nm in names}
    if protected in base:
        base[protected] = 0.94
    df["baseline_on_time_rate"] = np.round(df["carrier_name"].map(base), 4)
    df["is_expedited"] = df["is_expedited"].astype("int8")
    df["is_active"] = 1
    return df


def build_dim_sales_rep(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["sales_reps"])
    region_mix = {"NA": 0.52, "EMEA": 0.26, "APAC": 0.16, "LATAM": 0.06}
    regions = rng.choice(list(region_mix), size=n, p=list(region_mix.values()))

    first = rng.choice(R.FIRST_NAMES, size=n)
    last = rng.choice(R.LAST_NAMES, size=n)
    names = [f"{f} {l}" for f, l in zip(first, last)]

    # Territories inside a region, and a manager per territory. This is the
    # rollup the discount event is discovered against: one rep in one territory.
    terr_per_region = max(2, n // 24)
    territory = [f"{r}-{int(rng.integers(1, terr_per_region + 1)):02d}" for r in regions]
    mgr_pool = {t: f"{R.FIRST_NAMES[int(rng.integers(len(R.FIRST_NAMES)))]} "
                   f"{R.LAST_NAMES[int(rng.integers(len(R.LAST_NAMES)))]}"
                for t in sorted(set(territory))}

    df = pd.DataFrame({
        "sales_rep_id": np.arange(1, n + 1, dtype="int32"),
        "sales_rep_number": [f"REP-{i:04d}" for i in range(1, n + 1)],
        "sales_rep_name": names,
        "email": [f"{f}.{l}@vantage-industrial.example".lower().replace(" ", "")
                  for f, l in zip(first, last)],
        "region": regions,
        "territory": territory,
        "sales_team": rng.choice(["Field Sales", "Inside Sales", "Key Accounts",
                                  "Channel"], size=n, p=[0.46, 0.28, 0.16, 0.10]),
        "manager_name": [mgr_pool[t] for t in territory],
        "hire_date": [s.timeline.start_date
                      - dt.timedelta(days=int(rng.integers(0, 3800))) for _ in range(n)],
        "annual_quota_usd": (rng.integers(60, 400, n) * 10_000).astype("int32"),
        "is_active": 1,
    })
    return df


def build_dim_payment_terms() -> pd.DataFrame:
    df = pd.DataFrame(R.PAYMENT_TERMS, columns=[
        "payment_terms_code", "payment_terms_name", "due_days",
        "discount_pct", "discount_days", "_weight"]).drop(columns="_weight")
    df.insert(0, "payment_terms_id", np.arange(1, len(df) + 1, dtype="int32"))
    df["is_early_discount"] = (df["discount_pct"] > 0).astype("int8")
    df["terms_group"] = np.where(df["due_days"] <= 0, "Immediate",
                        np.where(df["due_days"] <= 30, "Short",
                        np.where(df["due_days"] <= 60, "Standard", "Extended")))
    return df


def build_dim_currency(s: Scenario) -> pd.DataFrame:
    rates = s.currency["rates"]
    names = {"USD": "US Dollar", "EUR": "Euro", "GBP": "Pound Sterling",
             "CAD": "Canadian Dollar", "JPY": "Japanese Yen",
             "AUD": "Australian Dollar", "MXN": "Mexican Peso",
             "SGD": "Singapore Dollar"}
    symbols = {"USD": "$", "EUR": "EUR", "GBP": "GBP", "CAD": "C$", "JPY": "JPY",
               "AUD": "A$", "MXN": "MX$", "SGD": "S$"}
    df = pd.DataFrame({
        "currency_code": list(rates),
        "currency_name": [names.get(c, c) for c in rates],
        "currency_symbol": [symbols.get(c, c) for c in rates],
        "budget_rate_per_usd": [float(v) for v in rates.values()],
        "is_reporting_currency": [1 if c == s.currency["reporting"] else 0
                                  for c in rates],
        "decimal_places": [0 if c == "JPY" else 2 for c in rates],
    })
    df.insert(0, "currency_id", np.arange(1, len(df) + 1, dtype="int32"))
    return df


def build_dim_exchange_rate(s: Scenario) -> pd.DataFrame:
    """Currency x month, held at the budget rate.

    Deliberately flat. A floating rate would put FX movement inside the
    bookings-to-cash waterfall, and then "where did the money go" has an answer
    nobody in the room wants to talk about. The table exists so the model looks
    like a real one and so a scenario can turn rate movement on if it wants to.
    """
    months = s.timeline.month_starts()
    rows = []
    for code, rate in s.currency["rates"].items():
        for m in months:
            rows.append((code, m, m.year * 100 + m.month, float(rate),
                         round(1.0 / float(rate), 8)))
    df = pd.DataFrame(rows, columns=["currency_code", "month_start_date",
                                     "year_month_key", "rate_per_usd",
                                     "usd_per_unit"])
    df.insert(0, "exchange_rate_id", np.arange(1, len(df) + 1, dtype="int32"))
    df["year_month_key"] = df["year_month_key"].astype("int32")
    df["rate_type"] = "Budget"
    return df
