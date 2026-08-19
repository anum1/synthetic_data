"""Planted business events.

Each event resolves to multiplier arrays applied to the per-line economics:
    line_mult   - relative number of order lines generated (demand volume)
    qty_mult    - units per line
    price_mult  - unit selling price before discount
    cost_mult   - unit cost
    disc_points - additional discount, in percentage points

Multipliers compose, so overlapping events (e.g. a supplier shock inside the
European erosion window) layer the way they would in a real business.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class LineContext:
    """Per-line attribute arrays for one generation month."""
    month: dt.date
    n: int
    category: np.ndarray
    subcategory: np.ndarray
    product_name: np.ndarray
    supplier_group: np.ndarray
    region: np.ndarray
    country: np.ndarray
    customer_name: np.ndarray
    product_id: np.ndarray


@dataclass
class Multipliers:
    qty: np.ndarray
    price: np.ndarray
    cost: np.ndarray
    disc_points: np.ndarray
    flags: dict[str, np.ndarray] = field(default_factory=dict)


def _in_window(month: dt.date, window: tuple[dt.date, dt.date] | None) -> bool:
    return window is not None and window[0] <= month <= window[1]


class EventEngine:
    def __init__(self, scenario, product_dim: pd.DataFrame, rng: np.random.Generator):
        self.s = scenario
        self.rng = rng
        self.base_margin = float(scenario.baseline["base_gross_margin_pct"])

        self.w_shock = scenario.event_window("supplier_cost_shock")
        self.w_promo = scenario.event_window("promotion_surge")
        self.w_region = scenario.event_window("region_margin_erosion")
        self.w_contract = scenario.event_window("customer_contraction")
        self.w_shortage = scenario.event_window("inventory_shortage")
        self.w_quality = scenario.event_window("quality_failure")
        self.launch_month = scenario.event_month("product_launch", "launch_offset")

        # SKUs hit by the inventory shortage: the top sellers in Laptops.
        cfg = scenario.event("inventory_shortage")
        self.shortage_skus: set[int] = set()
        if cfg:
            # Pick high-demand laptops that are still on sale: a shortage of
            # an end-of-life SKU is not a story anyone cares about.
            pool = product_dim[(product_dim["subcategory"] == "Laptops")
                               & (product_dim["is_discontinued"] == 0)]
            pool = pool.nlargest(int(cfg["affected_sku_count"]), "demand_weight")
            self.shortage_skus = set(pool["product_id"].astype(int).tolist())

        # Supplier group blamed for the quality failure: the cost-shock group,
        # so the demo can tie cost AND quality back to one supplier.
        qcfg = scenario.event("quality_failure")
        scfg = scenario.event("supplier_cost_shock")
        self.quality_group = scfg["supplier_group"] if (qcfg and scfg) else None

    # -- volume ---------------------------------------------------------------
    def customer_weight_multiplier(self, month: dt.date,
                                   customer_names: np.ndarray) -> np.ndarray | None:
        """Per-customer multiplier on order volume for this month.

        This is what actually makes a contracting customer place fewer orders;
        a per-line multiplier could only change what is on each order.
        """
        cfg = self.s.event("customer_contraction")
        if not cfg or not _in_window(month, self.w_contract):
            return None
        mult = np.ones(len(customer_names))
        mult[customer_names == cfg["customer_name"]] = 1.0 + float(cfg["order_change"])

        rec = self.s.event("recovery_scenario")
        rec_start = self.s.event_month("recovery_scenario", "start_offset")
        if rec and rec_start and month >= rec_start:
            mult[customer_names == cfg["customer_name"]] *= 1.0 + float(rec["customer_recovery"])
        return mult

    # -- per-line effects -----------------------------------------------------
    def apply(self, ctx: LineContext) -> Multipliers:
        n = ctx.n
        m = Multipliers(qty=np.ones(n), price=np.ones(n),
                        cost=np.ones(n), disc_points=np.zeros(n))
        month = ctx.month

        self._supplier_cost_shock(m, ctx, month)
        self._promotion_surge(m, ctx, month)
        self._product_launch(m, ctx, month)
        self._region_erosion(m, ctx, month)
        self._customer_contraction(m, ctx, month)
        self._inventory_shortage(m, ctx, month)
        self._recovery(m, ctx, month)
        return m

    def _supplier_cost_shock(self, m, ctx, month):
        cfg = self.s.event("supplier_cost_shock")
        if not cfg or not _in_window(month, self.w_shock):
            return
        hit = ctx.supplier_group == cfg["supplier_group"]
        m.cost[hit] *= 1.0 + float(cfg["cost_increase_pct"])
        m.price[hit] *= 1.0 + float(cfg.get("revenue_impact_pct", 0.0))
        m.flags["supplier_shock"] = hit

    def _promotion_surge(self, m, ctx, month):
        cfg = self.s.event("promotion_surge")
        if not cfg or not _in_window(month, self.w_promo):
            return
        hit = ctx.category == cfg["category"]
        m.qty[hit] *= 1.0 + float(cfg["unit_lift_pct"])
        m.disc_points[hit] += float(cfg["extra_discount_points"])
        m.flags["promotion_surge"] = hit

    def _product_launch(self, m, ctx, month):
        cfg = self.s.event("product_launch")
        if not cfg or self.launch_month is None or month < self.launch_month:
            return
        # Ramp the launch over three months rather than switching on instantly.
        months_in = (month.year - self.launch_month.year) * 12 + \
                    (month.month - self.launch_month.month)
        ramp = min(1.0, 0.45 + 0.275 * months_in)

        new_hit = ctx.product_name == cfg["new_product"]
        old_hit = ctx.product_name == cfg["incumbent_product"]
        m.qty[new_hit] *= 1.0 + float(cfg["new_product_lift"]) * ramp
        m.qty[old_hit] *= 1.0 + float(cfg["incumbent_decline"]) * ramp
        m.flags["launch_new"] = new_hit
        m.flags["launch_incumbent"] = old_hit

    def _region_erosion(self, m, ctx, month):
        cfg = self.s.event("region_margin_erosion")
        if not cfg or not _in_window(month, self.w_region):
            return
        in_region = ctx.region == cfg["region"]
        in_cat = ctx.category == cfg["category"]
        in_country = ctx.country == cfg["country"]
        in_sub = ctx.subcategory == cfg["subcategory"]
        scope = in_region & in_cat

        qty_m, price_m, cost_m = _solve_erosion(
            self.base_margin, float(cfg["revenue_change"]),
            float(cfg["unit_change"]), float(cfg["profit_change"]))

        # Concentric intensity: the drill-down should converge on the focus
        # country and subcategory, with the rest of the region visibly weaker.
        tiers = [
            (scope & in_country & in_sub, float(cfg.get("focus_weight", 1.8))),
            (scope & in_country & ~in_sub, float(cfg.get("country_weight", 0.9))),
            (scope & ~in_country & in_sub, float(cfg.get("subcategory_weight", 0.9))),
            (scope & ~in_country & ~in_sub, float(cfg.get("region_weight", 0.45))),
        ]
        for mask, weight in tiers:
            m.qty[mask] *= 1 + (qty_m - 1) * weight
            m.price[mask] *= 1 + (price_m - 1) * weight
            m.cost[mask] *= 1 + (cost_m - 1) * weight
        m.flags["region_erosion"] = scope

    def _customer_contraction(self, m, ctx, month):
        cfg = self.s.event("customer_contraction")
        if not cfg or not _in_window(month, self.w_contract):
            return
        hit = ctx.customer_name == cfg["customer_name"]
        order_chg = float(cfg["order_change"])
        rev_chg = float(cfg["revenue_change"])
        m.qty[hit] *= (1 + rev_chg) / (1 + order_chg)   # fewer, slightly bigger
        m.flags["customer_contraction"] = hit

    def _inventory_shortage(self, m, ctx, month):
        cfg = self.s.event("inventory_shortage")
        if not cfg or not _in_window(month, self.w_shortage):
            return
        hit = np.isin(ctx.product_id, list(self.shortage_skus))
        demand = 1 + float(cfg["demand_change"])
        supply = 1 + float(cfg["inventory_change"])
        # Sales are capped by availability: demand rises, fulfilment does not.
        m.qty[hit] *= min(demand, max(supply, 0.0) + 0.75)
        m.flags["inventory_shortage"] = hit

    def _recovery(self, m, ctx, month):
        """Applies only in the forecast horizon; actuals stop at as-of."""
        cfg = self.s.event("recovery_scenario")
        start = self.s.event_month("recovery_scenario", "start_offset")
        if not cfg or start is None or month < start:
            return
        m.cost *= 1.0 + float(cfg["supplier_cost_change"])
        m.disc_points += float(cfg["discount_change"])
        m.flags["recovery"] = np.ones(ctx.n, dtype=bool)

    # -- rates consumed by returns / supplier performance ----------------------
    def return_rate(self, month: dt.date, supplier_group: np.ndarray) -> np.ndarray:
        base = float(self.s.baseline["return_rate"])
        rate = np.full(len(supplier_group), base)
        cfg = self.s.event("quality_failure")
        if cfg and _in_window(month, self.w_quality) and self.quality_group:
            hit = supplier_group == self.quality_group
            rate[hit] = float(cfg["return_rate_to"])
        return rate

    def defect_rate(self, month: dt.date, supplier_group: np.ndarray) -> np.ndarray:
        cfg = self.s.event("quality_failure")
        base = float(cfg["defect_rate_from"]) if cfg else 0.02
        rate = np.full(len(supplier_group), base)
        if cfg and _in_window(month, self.w_quality) and self.quality_group:
            hit = supplier_group == self.quality_group
            rate[hit] = float(cfg["defect_rate_to"])
        return rate


def _solve_erosion(margin: float, rev_chg: float, unit_chg: float,
                   profit_chg: float) -> tuple[float, float, float]:
    """Closed form for the qty/price/cost multipliers that hit all three targets.

    Working from a unit-revenue base: revenue 1, profit = margin, cost = 1-margin.
    """
    qty_m = 1.0 + unit_chg
    rev_new = 1.0 + rev_chg
    price_m = rev_new / qty_m
    profit_new = margin * (1.0 + profit_chg)
    cost_new = rev_new - profit_new
    cost_m = cost_new / ((1.0 - margin) * qty_m)
    return qty_m, price_m, cost_m
