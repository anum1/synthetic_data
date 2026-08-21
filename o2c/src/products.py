"""Product master: the four-level hierarchy, cost, list price and lead time.

List price is the anchor for everything downstream. `contract_pricing` is
expressed as a discount off it, quoted price as a discount off that, and the
Event 7 leakage test is invoice price against contract price - so if list price
is not stable and sensible, none of the pricing story means anything.

Cost is drawn to hit a target gross margin, not independently. Margin is a
headline KPI and "which products have the highest quote loss rate" is only
interesting next to it.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from o2cconfig import Scenario


def build_dim_product(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    n = int(s.sizes["products"])

    # Expand the taxonomy into product lines, then spread SKUs across the lines
    # in proportion to how many lines each family has. Families with more lines
    # end up with more SKUs, which is why Fluid Handling is a big category and
    # Safety & PPE is not.
    lines: list[tuple[str, str, str]] = []
    for category, families in R.PRODUCT_TAXONOMY.items():
        for family, n_lines in families.items():
            for i in range(n_lines):
                qual = R.LINE_QUALIFIER[i % len(R.LINE_QUALIFIER)]
                lines.append((category, family, f"{family} - {qual}"))

    idx = rng.integers(0, len(lines), n)
    cat = [lines[i][0] for i in idx]
    fam = [lines[i][1] for i in idx]
    line = [lines[i][2] for i in idx]

    mu, sigma = s.pricing["list_price_lognorm"]
    list_price = np.exp(rng.normal(mu, sigma, n))
    # Made-to-order families are capital equipment, not consumables.
    mto = np.array([f in R.MADE_TO_ORDER_FAMILIES for f in fam])
    list_price = np.where(mto, list_price * 6.5, list_price)
    list_price = np.round(np.clip(list_price, 4.0, 90_000.0), 2)

    lo, hi = s.pricing["gross_margin_range"]
    margin = rng.uniform(lo, hi, n)
    unit_cost = np.round(list_price * (1.0 - margin), 2)

    # ABC class by revenue potential: A moves, C sits. Used by inventory
    # position and by the shortage event, which targets high-margin A items.
    score = list_price * np.exp(rng.normal(0, 1.0, n))
    rank = pd.Series(score).rank(pct=True, ascending=False)
    abc = np.where(rank <= 0.20, "A", np.where(rank <= 0.50, "B", "C"))

    lead = np.where(mto, rng.integers(21, 75, n), rng.integers(1, 21, n))
    launch = [s.timeline.start_date - dt.timedelta(days=int(rng.integers(60, 3600)))
              for _ in range(n)]

    lifecycle = rng.choice(["Active", "Active", "Active", "Active", "Active",
                            "New", "End of Life", "Discontinued"], size=n,
                           p=[0.19, 0.19, 0.19, 0.19, 0.10, 0.08, 0.04, 0.02])

    df = pd.DataFrame({
        "product_id": np.arange(1, n + 1, dtype="int32"),
        "sku": [f"VI-{i:06d}" for i in range(1, n + 1)],
        "product_name": [f"{l} {int(rng.integers(100, 999))}" for l in line],
        "product_category": cat,
        "product_family": fam,
        "product_line": line,
        "unit_of_measure": rng.choice(R.UOM, size=n,
                                      p=[0.46, 0.13, 0.11, 0.10, 0.06, 0.05, 0.05, 0.04]),
        "list_price_usd": list_price,
        "unit_cost_usd": unit_cost,
        "standard_margin_pct": np.round(margin, 4),
        "abc_class": abc,
        "is_made_to_order": mto.astype("int8"),
        "lead_time_days": lead.astype("int16"),
        "weight_kg": np.round(np.clip(np.exp(rng.normal(1.2, 1.3, n)), 0.05, 2500), 3),
        "is_hazmat": (rng.random(n) < 0.06).astype("int8"),
        "lifecycle_status": lifecycle,
        "launch_date": launch,
    })
    df["product_path"] = (df["product_category"] + " > " + df["product_family"]
                          + " > " + df["product_line"] + " > " + df["sku"])
    df["product_level_1"] = df["product_category"]
    df["product_level_2"] = df["product_family"]
    df["product_level_3"] = df["product_line"]
    df["product_level_4"] = df["sku"]
    return df
