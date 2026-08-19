"""Planted business events.

Each event resolves into dense multiplier MATRICES indexed by
(entity, month), which the fact generators read. Products x months is only
~1,500 x 43 even at full tier, so materialising the whole grid is cheaper and
far easier to reason about than per-row predicates -- and it makes overlapping
events compose by simple multiplication, the way they would in a real business.

Timing is month offsets relative to as-of; see docs/EVENTS.md for the expected
effect of each event, which validate.py asserts.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


def month_index(start: dt.date, end: dt.date) -> list[dt.date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(dt.date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _ramp(n: int, kind: str = "step") -> np.ndarray:
    """Shape of an event's onset across its own window."""
    if n <= 1:
        return np.ones(max(n, 1))
    if kind == "linear":
        return np.linspace(1.0 / n, 1.0, n)
    return np.ones(n)


def ramp_hold(n: int, ramp_months: int = 3) -> np.ndarray:
    """Ramp to full effect over `ramp_months`, then HOLD at full.

    Most of these events are open-ended (end_offset: null), so a linear ramp
    across the whole window spreads the onset over three years and the event
    never reaches the size the config states. Ramp in, then hold.
    """
    if n <= 1:
        return np.ones(max(n, 1))
    k = max(1, min(ramp_months, n))
    return np.concatenate([np.linspace(1.0 / k, 1.0, k), np.ones(n - k)])


class EventEngine:
    """Materialises every planted event as multiplier arrays."""

    def __init__(self, scenario, dim_product: pd.DataFrame,
                 dim_supplier: pd.DataFrame, dim_location: pd.DataFrame,
                 dim_carrier: pd.DataFrame, rng):
        self.s = scenario
        self.rng = rng
        self.months = month_index(scenario.timeline.start_date,
                                  scenario.timeline.end_date)
        self.mi = {m: i for i, m in enumerate(self.months)}
        self.nm = len(self.months)

        self.products = dim_product
        self.suppliers = dim_supplier
        self.locations = dim_location
        self.carriers = dim_carrier

        P = len(dim_product)
        S = len(dim_supplier)
        L = len(dim_location)
        C = len(dim_carrier)

        # --- the matrices every fact generator reads -----------------------
        self.demand_mult = np.ones((P, self.nm))
        self.unit_cost_mult = np.ones((P, self.nm))
        self.safety_stock_mult = np.ones((P, self.nm))
        self.forecast_bias = np.zeros((P, self.nm))     # signed, fraction
        self.forecast_noise_mult = np.ones((P, self.nm))

        self.supplier_lead_add = np.zeros((S, self.nm))   # days
        self.supplier_on_time = np.ones((S, self.nm))     # multiplier on base
        self.supplier_defect_abs = np.zeros((S, self.nm)) # absolute rate override
        self.supplier_capacity = np.ones((S, self.nm))

        self.carrier_transit_add = np.zeros((C, self.nm)) # days
        self.carrier_cost_mult = np.ones((C, self.nm))
        self.carrier_region = {}                          # carrier_idx -> region

        self.location_open = np.ones((L, self.nm))
        self.location_pick_capacity = np.ones((L, self.nm))

        self.expedite_mult = np.ones(self.nm)

        # Which SKUs each event touched, for the validator and the docs.
        self.targets: dict[str, np.ndarray] = {}
        self.notes: list[str] = []

        self._pid = {p: i for i, p in enumerate(dim_product["product_id"])}
        self._sid = {s: i for i, s in enumerate(dim_supplier["supplier_id"])}
        self._lid = {l: i for i, l in enumerate(dim_location["location_id"])}
        self._cid = {c: i for i, c in enumerate(dim_carrier["carrier_id"])}

        self._apply_all()

    # -- helpers ------------------------------------------------------------
    def _window(self, name):
        w = self.s.event_window(name)
        if w is None:
            return None
        a = self.mi.get(w[0], 0)
        b = self.mi.get(w[1], self.nm - 1)
        return max(a, 0), min(b, self.nm - 1)

    def _prod_idx(self, mask) -> np.ndarray:
        return np.flatnonzero(mask.to_numpy() if hasattr(mask, "to_numpy") else mask)

    def _sup_idx_by_master(self, master_id) -> int | None:
        row = self.suppliers.index[self.suppliers["supplier_master_id"] == master_id]
        if len(row) == 0:
            return None
        return int(row[0])

    def _sample(self, pool: np.ndarray, k: int) -> np.ndarray:
        if pool.size == 0:
            return pool
        return self.rng.choice(pool, size=min(k, pool.size), replace=False)

    # -- the events ---------------------------------------------------------
    def _apply_all(self):
        for fn in (self._supplier_disruption, self._quality_failure,
                   self._port_disruption, self._single_source_risk,
                   self._demand_spike, self._excess_inventory,
                   self._carrier_degradation, self._forecast_model_failure,
                   self._safety_stock_policy_change, self._product_substitution,
                   self._cost_inflation, self._new_dc_ramp,
                   self._labour_shortage, self._obsolescence,
                   self._planner_override_win):
            fn()

    # Event 1 --------------------------------------------------------------
    def _supplier_disruption(self):
        e = self.s.event("supplier_disruption")
        w = self._window("supplier_disruption")
        if not e or not w:
            return
        si = self._sup_idx_by_master(e["supplier_master_id"])
        if si is None:
            return
        a, b = w
        # Pin the contracted lead time so the event's stated 18 -> 29 day
        # movement is measurable; otherwise it starts from a random regional
        # draw and the assertion in docs/EVENTS.md cannot hold.
        self.suppliers.loc[self.suppliers.index[si], "lead_time_days"] = int(
            e["lead_time_days_from"])
        gap = e["lead_time_days_to"] - e["lead_time_days_from"]
        base = float(self.s.baseline["base_supplier_on_time"])
        # Pin the pre-event on-time rate as well. Without this the supplier
        # starts at the company baseline and the "95% -> 71%" movement in the
        # config is not what the data shows.
        self.supplier_on_time[si, :] = e["on_time_rate_from"] / base

        n = b - a + 1
        # Reach the full lead-time gap in two months, then HOLD. A linear ramp
        # across the whole window makes the disruption a triangle whose mean is
        # only half the stated peak, so the headline number never appears.
        ramp_n = min(2, n)
        self.supplier_lead_add[si, a:b + 1] += np.concatenate([
            np.linspace(gap / ramp_n, gap, ramp_n), np.full(n - ramp_n, gap)])
        self.supplier_on_time[si, a:b + 1] = e["on_time_rate_to"] / base
        self.supplier_capacity[si, a:b + 1] = 1 + e["capacity_change"]

        # Recovery is partial and slow: lead time does NOT snap back.
        rec_n = int(e.get("recovery_months", 0))
        frac = float(e.get("recovery_fraction", 1.0))
        if rec_n > 0:
            end = min(b + 1 + rec_n, self.nm)
            n = end - (b + 1)
            if n > 0:
                decay = np.linspace(1.0, 1.0 - frac, n)
                self.supplier_lead_add[si, b + 1:end] += gap * decay
                lo = e["on_time_rate_to"] / base
                hi = e["on_time_rate_from"] / base
                self.supplier_on_time[si, b + 1:end] = np.linspace(
                    lo, lo + (hi - lo) * frac, n)
        self.targets["supplier_disruption"] = np.array([si])
        self.notes.append(
            f"Event 1: {e['supplier_master_id']} lead time "
            f"{e['lead_time_days_from']}->{e['lead_time_days_to']}d, "
            f"on-time {e['on_time_rate_from']:.0%}->{e['on_time_rate_to']:.0%}")

    # Event 5 --------------------------------------------------------------
    def _quality_failure(self):
        e = self.s.event("quality_failure")
        w = self._window("quality_failure")
        if not e or not w:
            return
        si = self._sup_idx_by_master(e["supplier_master_id"])
        if si is None:
            return
        a, b = w
        n = b - a + 1
        # Ramp to the target over a few months and then HOLD. Spreading the
        # linspace across an open-ended window means the rate never actually
        # arrives at defect_rate_to, and the event silently does not happen.
        ramp_n = min(3, n)
        prof = np.concatenate([
            np.linspace(e["defect_rate_from"], e["defect_rate_to"], ramp_n),
            np.full(n - ramp_n, e["defect_rate_to"])])
        self.supplier_defect_abs[si, a:b + 1] = prof
        self.targets["quality_failure"] = np.array([si])
        self.notes.append(
            f"Event 5: {e['supplier_master_id']} defect rate "
            f"{e['defect_rate_from']:.1%}->{e['defect_rate_to']:.1%}")

    # Event 6 --------------------------------------------------------------
    def _port_disruption(self):
        e = self.s.event("port_disruption")
        w = self._window("port_disruption")
        if not e or not w:
            return
        a, b = w
        origin = e["origin_region"]
        sup_mask = (self.suppliers["region"] == origin).to_numpy()
        idx = np.flatnonzero(sup_mask)
        self.supplier_lead_add[np.ix_(idx, range(a, b + 1))] += e["transit_days_added"]
        self.expedite_mult[a:b + 1] *= e["expedite_multiple"]
        self.targets["port_disruption"] = idx
        self.notes.append(
            f"Event 6: {origin}-sourced inbound +{e['transit_days_added']}d transit")

    # Event 10 -------------------------------------------------------------
    def _single_source_risk(self):
        """Structural, not time-windowed: it makes events 1 and 5 consequential.

        Rewrites dim_product in place -- the only event that does.
        """
        e = self.s.event("single_source_risk")
        if not e:
            return
        p = self.products
        # Restrict to purchased SKUs: the drill-down from a single-sourced item
        # goes to a SUPPLIER, so a manufactured SKU has nothing to point at.
        purchased = (p["replenishment_source"] == "Purchase"
                     if "replenishment_source" in p.columns
                     else p["product_type"] != "Finished Good")
        crit = self._prod_idx((p["criticality"] == "Critical") & purchased)
        if crit.size == 0:
            return
        pick = self._sample(crit, int(e["critical_single_sourced_count"]))
        p.loc[p.index[pick], "secondary_supplier_id"] = 0
        p.loc[p.index[pick], "single_source_flag"] = 1

        # Force N of them onto the disrupted supplier so the drill-down lands.
        d = self.s.event("supplier_disruption")
        if d:
            si = self._sup_idx_by_master(d["supplier_master_id"])
            if si is not None:
                sid = int(self.suppliers.iloc[si]["supplier_id"])
                k = int(e["on_disrupted_supplier"])
                onto = pick[:k]
                p.loc[p.index[onto], "primary_supplier_id"] = sid
                self.targets["single_source_on_disrupted"] = onto
        self.targets["single_source_risk"] = pick
        self.notes.append(
            f"Event 10: {pick.size} Critical SKUs single-sourced, "
            f"{int(e['on_disrupted_supplier'])} on the disrupted supplier")

    # Event 2 --------------------------------------------------------------
    def _demand_spike(self):
        e = self.s.event("demand_spike")
        w = self._window("demand_spike")
        if not e or not w:
            return
        a, b = w
        idx = self._prod_idx(self.products["category"] == e["product_family"])
        if idx.size == 0:
            idx = self._prod_idx(self.products["product_family"] == e["product_family"])
        n = b - a + 1
        self.demand_mult[np.ix_(idx, range(a, b + 1))] *= (
            1 + e["demand_change"] * ramp_hold(n))
        self.forecast_noise_mult[np.ix_(idx, range(a, b + 1))] *= (
            1 + e["forecast_error_points"] * 4)
        self.expedite_mult[a:b + 1] *= e["expedite_share_multiple"]
        self.targets["demand_spike"] = idx
        self.notes.append(f"Event 2: {e['product_family']} demand +{e['demand_change']:.0%}")

    # Event 3 --------------------------------------------------------------
    def _excess_inventory(self):
        e = self.s.event("excess_inventory")
        w = self._window("excess_inventory")
        if not e or not w:
            return
        a, b = w
        # ABC is not derived yet at construction time, so target the cheap,
        # low-volume tail by unit cost as a stand-in; reconciled after
        # classification by validate.py.
        cost = self.products["unit_cost"].to_numpy()
        pool = np.flatnonzero(cost <= np.quantile(cost, 0.55))
        pick = self._sample(pool, int(e["affected_sku_count"]))
        self.forecast_bias[np.ix_(pick, range(a, b + 1))] += e["over_forecast_pct"]
        self.safety_stock_mult[np.ix_(pick, range(a, b + 1))] *= (1 + e["inventory_change"])
        self.targets["excess_inventory"] = pick
        self.notes.append(
            f"Event 3: {pick.size} slow movers over-forecast +{e['over_forecast_pct']:.0%}")

    # Event 4 --------------------------------------------------------------
    def _carrier_degradation(self):
        e = self.s.event("carrier_degradation")
        w = self._window("carrier_degradation")
        if not e or not w:
            return
        a, b = w
        row = self.carriers.index[self.carriers["carrier_code"] == e["carrier_code"]]
        if len(row) == 0:
            return
        ci = int(row[0])
        n = b - a + 1
        self.carrier_transit_add[ci, a:b + 1] += e["transit_days_added"] * ramp_hold(n)
        self.carrier_cost_mult[ci, a:b + 1] *= 1 + e["freight_cost_change"]
        # Concentrated geographically: the fact generator applies it only to
        # shipments in this sub-region.
        self.carrier_region[ci] = (e.get("region"), e.get("sub_region"))
        self.targets["carrier_degradation"] = np.array([ci])
        self.notes.append(
            f"Event 4: carrier {e['carrier_code']} +{e['transit_days_added']}d "
            f"in {e.get('sub_region')}")

    # Event 7 --------------------------------------------------------------
    def _forecast_model_failure(self):
        e = self.s.event("forecast_model_failure")
        w = self._window("forecast_model_failure")
        if not e or not w:
            return
        a, b = w
        idx = self._prod_idx(self.products["category"] == e["category"])
        self.forecast_bias[np.ix_(idx, range(a, b + 1))] += e["forecast_bias"]
        self.targets["forecast_model_failure"] = idx
        self.notes.append(
            f"Event 7: {e['category']} forecast bias {e['forecast_bias']:+.0%}")

    # Event 8 --------------------------------------------------------------
    def _safety_stock_policy_change(self):
        e = self.s.event("safety_stock_policy_change")
        w = self._window("safety_stock_policy_change")
        if not e or not w:
            return
        a, b = w
        cost = self.products["unit_cost"].to_numpy()
        pool = np.flatnonzero(cost >= np.quantile(cost, 0.70))   # A-class proxy
        pick = self._sample(pool, int(e["affected_sku_count"]))
        self.safety_stock_mult[np.ix_(pick, range(a, b + 1))] *= (1 + e["safety_stock_change"])
        self.targets["safety_stock_policy_change"] = pick
        self.notes.append(
            f"Event 8: safety stock +{e['safety_stock_change']:.0%} on {pick.size} "
            f"A-class SKUs (net-negative by design)")

    # Event 9 --------------------------------------------------------------
    def _product_substitution(self):
        e = self.s.event("product_substitution")
        w = self._window("product_substitution")
        if not e or not w:
            return
        a, b = w
        n = b - a + 1
        # The two named products must exist; claim two Controllers and rename.
        pool = self._prod_idx(self.products["subcategory"] == "Controllers")
        if pool.size < 2:
            pool = np.arange(len(self.products))[:2]
        dec, gro = int(pool[0]), int(pool[1])
        self.products.loc[self.products.index[dec], "product_name"] = e["declining_product"]
        self.products.loc[self.products.index[gro], "product_name"] = e["growing_product"]
        self.products.loc[self.products.index[[dec, gro]], "product_level5_product"] = [
            e["declining_product"], e["growing_product"]]
        self.demand_mult[dec, a:b + 1] *= 1 + e["declining_change"] * ramp_hold(n, 6)
        self.demand_mult[gro, a:b + 1] *= 1 + e["growing_change"] * ramp_hold(n, 6)
        self.targets["product_substitution"] = np.array([dec, gro])
        self.notes.append(
            f"Event 9: {e['declining_product']} -> {e['growing_product']} substitution")

    # Event 11 -------------------------------------------------------------
    def _cost_inflation(self):
        e = self.s.event("cost_inflation")
        w = self._window("cost_inflation")
        if not e or not w:
            return
        a, b = w
        idx = self._prod_idx(self.products["category"] == e["category"])
        n = b - a + 1
        steps = int(e.get("step_quarters", 4))
        # Stepped, not smooth: cost increases land as discrete price letters.
        prof = np.repeat(np.linspace(1 / steps, 1.0, steps),
                         int(np.ceil(n / steps)))[:n]
        self.unit_cost_mult[np.ix_(idx, range(a, b + 1))] *= 1 + e["unit_cost_change"] * prof
        self.targets["cost_inflation"] = idx
        self.notes.append(
            f"Event 11: {e['category']} unit cost +{e['unit_cost_change']:.0%} "
            f"over {steps} steps")

    # Event 12 -------------------------------------------------------------
    def _new_dc_ramp(self):
        e = self.s.event("new_dc_ramp")
        if not e:
            return
        row = self.locations.index[
            self.locations["location_name"].str.startswith(e["location_name"].split()[0])]
        if len(row) == 0:
            return
        li = int(row[-1])
        open_m = self.mi.get(self.s.timeline.offset_month(int(e["open_offset"])), 0)
        self.location_open[li, :open_m] = 0.0
        ramp_n = int(e.get("ramp_months", 3))
        end = min(open_m + ramp_n, self.nm)
        if end > open_m:
            self.location_open[li, open_m:end] = np.linspace(0.25, 1.0, end - open_m)
        self.locations.loc[self.locations.index[li], "opened_offset_months"] = int(e["open_offset"])
        self.targets["new_dc_ramp"] = np.array([li])
        self.notes.append(f"Event 12: {e['location_name']} opens at offset {e['open_offset']}")

    # Event 13 -------------------------------------------------------------
    def _labour_shortage(self):
        e = self.s.event("labour_shortage")
        w = self._window("labour_shortage")
        if not e or not w:
            return
        a, b = w
        dcs = np.flatnonzero((self.locations["node_type"] == "DC").to_numpy())
        pick = self._sample(dcs, int(e["affected_location_count"]))
        self.location_pick_capacity[np.ix_(pick, range(a, b + 1))] = e["pick_capacity"]
        self.targets["labour_shortage"] = pick
        self.notes.append(
            f"Event 13: {pick.size} DCs at {e['pick_capacity']:.0%} pick capacity")

    # Event 14 -------------------------------------------------------------
    def _obsolescence(self):
        e = self.s.event("obsolescence")
        w = self._window("obsolescence")
        if not e or not w:
            return
        a, b = w
        n = b - a + 1
        used = set()
        for k in ("excess_inventory", "safety_stock_policy_change"):
            used.update(self.targets.get(k, np.array([], dtype=int)).tolist())
        pool = np.array([i for i in range(len(self.products)) if i not in used])
        pick = self._sample(pool, int(e["affected_sku_count"]))
        self.demand_mult[np.ix_(pick, range(a, b + 1))] *= (
            1 + e["demand_change"] * ramp_hold(n, 6))
        self.targets["obsolescence"] = pick
        self.notes.append(f"Event 14: {pick.size} SKUs going end-of-life")

    # Event 15 -------------------------------------------------------------
    def _planner_override_win(self):
        """Must cut both ways -- see docs/EVENTS.md."""
        e = self.s.event("planner_override_win")
        w = self._window("planner_override_win")
        if not e or not w:
            return
        pool = np.arange(len(self.products))
        pick = self._sample(pool, int(e["improved_sku_count"]) + int(e["degraded_sku_count"]))
        k = int(e["improved_sku_count"])
        self.targets["override_improved"] = pick[:k]
        self.targets["override_degraded"] = pick[k:]
        self.notes.append(
            f"Event 15: overrides help {pick[:k].size} SKUs, hurt {pick[k:].size}")

    # -- lookups used by the fact generators --------------------------------
    def month_pos(self, dates: pd.Series) -> np.ndarray:
        """Map a datetime series to column positions in the matrices."""
        per = pd.to_datetime(dates).dt.to_period("M").dt.to_timestamp().dt.date
        return per.map(self.mi).fillna(0).astype(int).to_numpy()

    def retarget_after_classification(self, dim_product) -> None:
        """Re-pick the ABC-targeted events once ABC actually exists.

        The engine is constructed before demand is generated, so events 3 and 8
        initially target a unit-cost proxy for value class. Once ABC is derived
        the proxy can be replaced with the real thing, which is what makes
        "excess inventory sits in C-class slow movers" true rather than
        approximately true.
        """
        for key, event_name, cls in (
                ("excess_inventory", "excess_inventory", None),
                ("safety_stock_policy_change", "safety_stock_policy_change", None)):
            e = self.s.event(event_name)
            w = self._window(event_name)
            if not e or not w:
                continue
            target_cls = e.get("target_abc_class")
            if not target_cls:
                continue
            a, b = w
            old = self.targets.get(key)
            if old is not None:            # undo the proxy-based application
                if event_name == "excess_inventory":
                    self.forecast_bias[np.ix_(old, range(a, b + 1))] -= e["over_forecast_pct"]
                    self.safety_stock_mult[np.ix_(old, range(a, b + 1))] /= (
                        1 + e["inventory_change"])
                else:
                    self.safety_stock_mult[np.ix_(old, range(a, b + 1))] /= (
                        1 + e["safety_stock_change"])
            pool = np.flatnonzero((dim_product["abc_class"] == target_cls).to_numpy())
            if pool.size == 0:
                continue
            pick = self._sample(pool, int(e["affected_sku_count"]))
            if event_name == "excess_inventory":
                self.forecast_bias[np.ix_(pick, range(a, b + 1))] += e["over_forecast_pct"]
                self.safety_stock_mult[np.ix_(pick, range(a, b + 1))] *= (
                    1 + e["inventory_change"])
            else:
                self.safety_stock_mult[np.ix_(pick, range(a, b + 1))] *= (
                    1 + e["safety_stock_change"])
            self.targets[key] = pick

    def summary(self) -> str:
        return "\n".join(f"  - {n}" for n in self.notes)
