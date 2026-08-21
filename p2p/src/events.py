"""The eighteen planted events, resolved once into concrete targets.

Two rules govern this file.

**Scope is a fraction, resolved to entities once.** Event scope is configured as
a share of the population so a story stays proportionally visible at both tiers.
Resolving the targets here, once, means every downstream module agrees on which
supplier, which buyer and which department the stories land on - rather than
each stage drawing its own sample and the story landing on five populations.

**Ramps, not step changes.** Events phase in linearly across their window. A
step change is findable by eye and makes the AI look clairvoyant rather than
useful; a ramp has to be measured. `ramp()` returns 0 before the window, 0..1
across it, and 1 after.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from p2pconfig import Scenario, month_end

# The supplier the fifteen-minute demo drills into. Resolved by name prefix so
# the story survives a reseed - ids shuffle, the hand-written name does not.
HERO_SUPPLIER_PREFIX = "Northbeam"


class EventPlan:
    """Resolved targets for every enabled event."""

    def __init__(self, s: Scenario, suppliers: pd.DataFrame, depts: pd.DataFrame,
                 cats: pd.DataFrame, employees: pd.DataFrame,
                 rng: np.random.Generator):
        self.s = s
        self.tl = s.timeline

        sup_ranked = suppliers.sort_values("_spend_weight", ascending=False)
        self.ranked_suppliers = sup_ranked["supplier_id"].to_numpy()

        hero = suppliers[suppliers["supplier_name"].str.startswith(HERO_SUPPLIER_PREFIX)]
        self.hero_supplier_id = int(hero["supplier_id"].iloc[0]) if len(hero) \
            else int(self.ranked_suppliers[0])
        self.hero_supplier_name = (hero["supplier_name"].iloc[0] if len(hero)
                                   else suppliers["supplier_name"].iloc[0])

        # -- E1 maverick spend: a few departments carrying most of it ----------
        self.maverick_departments = np.array([], dtype=np.int64)
        ev = s.event("maverick_spend")
        if ev:
            k = max(2, int(round(float(ev["department_share"]) * len(depts))))
            self.maverick_departments = depts.sample(
                n=k, weights=depts["_demand_weight"],
                random_state=int(s.seed) + 101)["department_id"].to_numpy()

        # -- E3 quantity mismatch: three categories ---------------------------
        self.qty_mismatch_categories = np.array([], dtype=np.int64)
        ev = s.event("quantity_mismatch")
        if ev:
            self.qty_mismatch_categories = cats.sample(
                n=int(ev["category_count"]), weights=cats["_spend_weight"],
                random_state=int(s.seed) + 102)["category_id"].to_numpy()

        # -- E4 contract price drift: THE root cause --------------------------
        #
        # The hero supplier is always in the set, at the configured drift, and
        # is always first - the demo script names it out loud.
        self.price_drift: dict[int, float] = {}
        ev = s.event("contract_price_drift")
        if ev:
            k = int(ev["supplier_count"])
            # Drawn from the top of the spend distribution: drift on a $9K
            # supplier is not a $2.1M savings story.
            pool = [int(x) for x in self.ranked_suppliers[:max(k * 12, 40)]
                    if int(x) != self.hero_supplier_id]
            picked = rng.choice(pool, size=min(k - 1, len(pool)), replace=False)
            lo, hi = ev["drift_pct_range"]
            self.price_drift[self.hero_supplier_id] = float(ev["hero_supplier_drift"])
            for sid in picked:
                self.price_drift[int(sid)] = float(rng.uniform(lo, hi))

        # -- E5 delivery decay -------------------------------------------------
        self.delivery_decay: dict[int, tuple[float, float]] = {}
        ev = s.event("delivery_decay")
        if ev:
            k = int(ev["supplier_count"])
            pool = [int(x) for x in self.ranked_suppliers[:max(k * 14, 50)]]
            # The hero supplier deteriorates on delivery too - one supplier,
            # four symptoms, which is the story in PLAN 2.6.
            picked = [self.hero_supplier_id] + [
                int(x) for x in rng.choice([p for p in pool
                                            if p != self.hero_supplier_id],
                                           size=k - 1, replace=False)]
            for sid in picked:
                self.delivery_decay[sid] = (float(ev["on_time_from"]),
                                            float(ev["on_time_to"]))

        # -- E6 approval slowdown: one department ------------------------------
        self.slow_approval_departments = np.array([], dtype=np.int64)
        ev = s.event("approval_slowdown")
        if ev:
            k = max(1, int(round(float(ev["department_share"]) * len(depts))))
            self.slow_approval_departments = depts.sample(
                n=k, random_state=int(s.seed) + 103)["department_id"].to_numpy()

        # -- E9 late payment: the suppliers we serve worst ---------------------
        self.late_paid_suppliers = np.array([], dtype=np.int64)
        ev = s.event("late_payment")
        if ev:
            pool = [int(x) for x in self.ranked_suppliers[10:200]]
            self.late_paid_suppliers = rng.choice(
                pool, size=int(ev["supplier_count"]), replace=False)

        # -- E10 supplier concentration in one named category ------------------
        self.concentration_category_id = 0
        self.concentration_suppliers = np.array([], dtype=np.int64)
        self.concentration_shares = np.array([], dtype=float)
        ev = s.event("supplier_concentration")
        if ev:
            hit = cats[cats["category_name"] == ev["category_name"]]
            if len(hit):
                # The named category has several leaves; concentrate all of them.
                self.concentration_category_id = int(hit["category_id"].iloc[0])
                self.concentration_leaf_ids = hit["category_id"].to_numpy()
                shares = np.array(ev["shares"], dtype=float)
                pool = [int(x) for x in self.ranked_suppliers[5:120]]
                self.concentration_suppliers = rng.choice(
                    pool, size=len(shares), replace=False)
                self.concentration_shares = shares / shares.sum()
            else:
                self.concentration_leaf_ids = np.array([], dtype=np.int64)
        else:
            self.concentration_leaf_ids = np.array([], dtype=np.int64)

        # -- E13/E14 the buyers who split POs and hug the threshold ------------
        buyers = employees[employees["is_buyer"] == 1]
        self.splitting_buyers = np.array([], dtype=np.int64)
        self.threshold_buyers = np.array([], dtype=np.int64)
        if len(buyers):
            ev = s.event("po_splitting")
            if ev:
                k = max(2, int(round(0.08 * len(buyers))))
                self.splitting_buyers = buyers.sample(
                    n=k, random_state=int(s.seed) + 104)["employee_id"].to_numpy()
            ev = s.event("threshold_clustering")
            if ev:
                k = max(2, int(round(float(ev["buyer_share"]) * len(buyers))))
                self.threshold_buyers = buyers.sample(
                    n=k, random_state=int(s.seed) + 105)["employee_id"].to_numpy()

        # -- E18 consolidation: fragmented categories --------------------------
        self.consolidation_categories = np.array([], dtype=np.int64)
        ev = s.event("consolidation_opportunity")
        if ev:
            self.consolidation_categories = cats.sample(
                n=int(ev["category_count"]), weights=cats["_spend_weight"],
                random_state=int(s.seed) + 106)["category_id"].to_numpy()

        # -- approver absence window (drives approval delay spikes) ------------
        lo, hi = s.approval["approver_absence_months"]
        self.absence_start = self.tl.offset_month(-int(hi))
        self.absence_end = month_end(self.tl.offset_month(-int(lo)))

    # -- helpers ---------------------------------------------------------------

    def ramp(self, name: str, when) -> float:
        """0 before the window, 0..1 across it, 1 after. 0 when disabled."""
        win = self.s.event_window(name)
        if win is None:
            return 0.0
        start, end = win
        end_d = month_end(end)
        d = _as_date(when)
        if d < start:
            return 0.0
        if d >= end_d:
            return 1.0
        span = max((end_d - start).days, 1)
        return (d - start).days / span

    def ramp_series(self, name: str, when: np.ndarray) -> np.ndarray:
        """Vectorised `ramp` over an array of dates."""
        win = self.s.event_window(name)
        if win is None:
            return np.zeros(len(when), dtype=float)
        start, end = win
        end_d = month_end(end)
        span = max((end_d - start).days, 1)
        days = (pd.to_datetime(pd.Series(when)) - pd.Timestamp(start)).dt.days
        return np.clip(days.to_numpy() / span, 0.0, 1.0)

    def price_drift_for(self, supplier_ids: np.ndarray) -> np.ndarray:
        if not self.price_drift:
            return np.zeros(len(supplier_ids), dtype=float)
        return pd.Series(supplier_ids).map(self.price_drift).fillna(0.0).to_numpy()

    def on_time_target(self, supplier_ids: np.ndarray, when: np.ndarray) -> np.ndarray:
        """Supplier on-time rate at a point in time, with the decay applied."""
        base = float(self.s.receiving["base_on_time_rate"])
        out = np.full(len(supplier_ids), base, dtype=float)
        if not self.delivery_decay:
            return out
        r = self.ramp_series("delivery_decay", when)
        hit = pd.Series(supplier_ids).isin(list(self.delivery_decay)).to_numpy()
        if hit.any():
            frm = float(self.s.event("delivery_decay")["on_time_from"])
            to = float(self.s.event("delivery_decay")["on_time_to"])
            out[hit] = frm + (to - frm) * r[hit]
        return out


def _as_date(x) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return pd.Timestamp(x).date()
