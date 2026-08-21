"""The month-by-month workforce simulator.

This is the part that departs from the sibling ApexTech and Meridian datasets.
Those build dimensions and then draw facts against them, which works because
nothing there feeds back. Here it does: compa-ratio drives attrition, attrition
drives hiring, hiring at midpoint drives compression, compression drives
compa-ratio. Generating one table at a time cannot produce that loop, and the
loop is exactly what makes the demo worth watching.

Each month, in order:

  1  hires            baseline growth + backfill + Event 1 surge + Event 7 acquisition
  2  terminations     hazard model evaluated for every active employee
  3  performance      annual review cycle, with persistence
  4  promotions       rate x rating odds, plus the Event 4 wave
  5  merit            annual cycle, capped for Event 3 incumbents
  6  market adjust    biased towards employees deep below midpoint
  7  transfers        ordinary moves plus the Event 8 reorganisation
  8  manager refresh  org -> manager map, emitting Manager Change history
  9  snapshot         month-end state of everyone active

Nothing about who leaves is stamped on. Terminations fall out of the hazard
model in config, so the correlations the AI "discovers" survive being sliced any
way the audience asks.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from hrconfig import _add_month, month_end

WORKER_TYPES = ["Regular", "Fixed Term", "Contingent"]


def _band_lookup(bands: list[dict], values: np.ndarray) -> np.ndarray:
    """Map values onto multipliers using ordered {max, mult} bands."""
    out = np.full(len(values), float(bands[-1]["mult"]))
    assigned = np.zeros(len(values), dtype=bool)
    for band in bands:
        hit = (~assigned) & (values < float(band["max"]))
        out[hit] = float(band["mult"])
        assigned |= hit
    return out


class Workforce:
    """Simulates the population and emits every employee-grain fact."""

    def __init__(self, s, tables: dict[str, pd.DataFrame], rng: np.random.Generator):
        self.s = s
        self.rng = rng
        self.orgs = tables["dim_organization"]
        self.locs = tables["dim_location"]
        self.jobs = tables["dim_job"]
        self.ranges = tables["job_salary_range"]
        self.months = s.timeline.month_starts()
        self.month_index = {m: i for i, m in enumerate(self.months)}

        self._prepare_lookups()
        self._prepare_events()

        # Emitted rows
        self.job_history: list[dict] = []
        self.salary_history: list[dict] = []
        self.terminations: list[dict] = []
        self.reviews: list[dict] = []
        self.snapshots: list[dict] = []

    # ------------------------------------------------------------------ setup
    def _prepare_lookups(self):
        s, jobs, ranges = self.s, self.jobs, self.ranges
        self.zone_cfg = s.comp["geo_zone"]

        # Salary range midpoint by (job_id, zone, year). Every compa-ratio in the
        # dataset resolves through this, so it has to be a dict, not a merge.
        self.mid_usd = {}
        self.min_usd = {}
        for jid, zone, year, mid, lo in zip(
                ranges["job_id"], ranges["geo_zone"], ranges["effective_year"],
                ranges["midpoint_usd"], ranges["minimum_usd"]):
            self.mid_usd[(int(jid), zone, int(year))] = float(mid)
            self.min_usd[(int(jid), zone, int(year))] = float(lo)
        self.range_years = sorted({int(y) for y in ranges["effective_year"]})

        # Jobs indexed by (function, level, track) so promotions and hires can
        # pick a job that actually exists in the catalog.
        self.job_by_slot: dict[tuple, np.ndarray] = {}
        for (fn, lvl, track), grp in jobs.groupby(
                ["function_name", "job_level", "career_track"], observed=True):
            self.job_by_slot[(fn, lvl, track)] = grp["job_id"].to_numpy()
        self.job_family = dict(zip(jobs["job_id"], jobs["job_family"]))
        self.job_level_of = dict(zip(jobs["job_id"], jobs["job_level"]))
        self.job_track_of = dict(zip(jobs["job_id"], jobs["career_track"]))
        self.job_function_of = dict(zip(jobs["job_id"], jobs["function_name"]))
        self.job_exempt_of = dict(zip(jobs["job_id"], jobs["exempt_status"]))
        # Job families available per function, for transfers within a function.
        self.jobs_by_family_level: dict[tuple, np.ndarray] = {}
        for (fam, lvl), grp in jobs.groupby(["job_family", "job_level"], observed=True):
            self.jobs_by_family_level[(fam, lvl)] = grp["job_id"].to_numpy()

        # Leaf orgs by function, for placement.
        leaves = self.orgs[self.orgs["is_leaf"] == 1]
        self.leaf_by_function = {
            fn: grp["organization_id"].to_numpy()
            for fn, grp in leaves.groupby("function_name", observed=True)}
        self.org_function = dict(zip(self.orgs["organization_id"],
                                     self.orgs["function_name"]))
        self.org_effective = dict(zip(self.orgs["organization_id"],
                                      self.orgs["effective_date"]))
        self.org_active = dict(zip(self.orgs["organization_id"], self.orgs["is_active"]))
        self.org_parent = dict(zip(self.orgs["organization_id"],
                                   self.orgs["parent_organization_id"]))
        self.org_cost_center = dict(zip(self.orgs["organization_id"],
                                        self.orgs["cost_center"]))
        self.org_children: dict[int, list[int]] = {}
        for oid, parent in zip(self.orgs["organization_id"],
                               self.orgs["parent_organization_id"]):
            self.org_children.setdefault(int(parent), []).append(int(oid))
        self.org_by_depth = [int(o) for o in self.orgs.sort_values(
            "org_depth", ascending=False)["organization_id"]]
        self.org_name = dict(zip(self.orgs["organization_id"],
                                 self.orgs["organization_name"]))
        self.org_division = dict(zip(self.orgs["organization_id"],
                                     self.orgs["division_name"]))
        self.org_department = dict(zip(self.orgs["organization_id"],
                                       self.orgs["department_name"]))

        # Locations by country.
        self.loc_by_country = {
            c: grp["location_id"].to_numpy()
            for c, grp in self.locs.groupby("country", observed=True)}
        self.loc_weight = {}
        for c, grp in self.locs.groupby("country", observed=True):
            w = np.ones(len(grp))
            self.loc_weight[c] = w / w.sum()
        self.loc_country = dict(zip(self.locs["location_id"], self.locs["country"]))
        self.acquired_locs = set(
            self.locs.loc[self.locs["location_name"].str.contains(r"\(", regex=True),
                          "location_id"])

    def _prepare_events(self):
        s = self.s
        self.ev_surge = s.event("engineering_hiring_surge")
        self.ev_surge_window = s.event_window("engineering_hiring_surge")
        self.ev_sales = s.event("sales_attrition_spike")
        self.ev_sales_window = s.event_window("sales_attrition_spike")
        self.ev_compress = s.event("compensation_compression")
        self.ev_compress_start = s.event_month("compensation_compression", "start_offset")
        self.ev_promo = s.event("promotion_wave")
        self.ev_promo_month = s.event_month("promotion_wave", "month_offset")
        self.ev_acq = s.event("acquisition")
        self.ev_acq_month = s.event_month("acquisition", "month_offset")
        self.ev_reorg = s.event("marketing_reorganization")
        self.ev_reorg_month = s.event_month("marketing_reorganization", "month_offset")
        self.ev_mgr = s.event("manager_problem")
        self.hp_attrition = s.event("high_performer_attrition")

        # Orgs the events reach into.
        self.surge_orgs = self._subtree_leaves(
            self.ev_surge["organization"]) if self.ev_surge else np.array([], dtype=int)
        self.mgr_problem_orgs = self._subtree_leaves(
            self.ev_mgr["organization"]) if self.ev_mgr else np.array([], dtype=int)
        self.acq_orgs = (self._subtree_leaves(f"{self.ev_acq['company_name']} Integration")
                         if self.ev_acq else np.array([], dtype=int))
        self.reorg_target_orgs = (
            np.concatenate([self._subtree_leaves(o) for o in self.ev_reorg["to_organizations"]])
            if self.ev_reorg else np.array([], dtype=int))

    def _subtree_leaves(self, org_name: str) -> np.ndarray:
        """Leaf org ids beneath a named org (inclusive if it is itself a leaf)."""
        root = self.orgs[self.orgs["organization_name"] == org_name]
        if root.empty:
            return np.array([], dtype=int)
        ids = set(root["organization_id"])
        frontier = set(ids)
        while frontier:
            children = self.orgs[self.orgs["parent_organization_id"].isin(frontier)]
            frontier = set(children["organization_id"]) - ids
            ids |= frontier
        leaves = self.orgs[self.orgs["organization_id"].isin(ids)
                           & (self.orgs["is_leaf"] == 1)]
        return leaves["organization_id"].to_numpy()

    # ------------------------------------------------------------ state arrays
    def _alloc(self, n: int):
        z = lambda dtype: np.zeros(n, dtype=dtype)                       # noqa: E731
        self.e = {
            "employee_id": z("int32"), "first_name": np.empty(n, object),
            "last_name": np.empty(n, object), "country": np.empty(n, object),
            "location_id": z("int32"), "organization_id": z("int32"),
            "function_name": np.empty(n, object), "job_id": z("int32"),
            "job_level": np.empty(n, object), "career_track": np.empty(n, object),
            "hire_month": z("int16"), "term_month": np.full(n, -1, dtype="int16"),
            "hire_date": np.empty(n, object), "term_date": np.empty(n, object),
            "active": z("int8"), "fte": np.ones(n), "worker_type": np.empty(n, object),
            "manager_id": z("int32"), "salary_usd": z("float64"),
            "salary_local": z("float64"), "currency": np.empty(n, object),
            "rating": np.full(n, 3, dtype="int8"),
            "prior_rating": np.full(n, 3, dtype="int8"),
            "last_promo_month": z("int16"), "birth_date": np.empty(n, object),
            "is_acquired": z("int8"), "gender": np.empty(n, object),
            "ethnicity": np.empty(n, object), "veteran_status": np.empty(n, object),
            "disability_status": np.empty(n, object),
            "reviewed": z("int8"),
        }
        self.n = 0
        self.capacity = n

    def _new_rows(self, k: int) -> np.ndarray:
        idx = np.arange(self.n, self.n + k)
        self.n += k
        self.e["employee_id"][idx] = idx + 1001
        return idx

    # ------------------------------------------------------------------- money
    def _range_year(self, year: int) -> int:
        return min(max(year, self.range_years[0]), self.range_years[-1])

    def midpoints(self, job_ids: np.ndarray, zones: np.ndarray, year: int) -> np.ndarray:
        y = self._range_year(year)
        return np.array([self.mid_usd[(int(j), z, y)] for j, z in zip(job_ids, zones)])

    def _compa(self, idx: np.ndarray, year: int) -> np.ndarray:
        mids = self.midpoints(self.e["job_id"][idx], self.e["country"][idx], year)
        return self.e["salary_usd"][idx] / mids

    def _set_salary_usd(self, idx: np.ndarray, salary_usd: np.ndarray):
        self.e["salary_usd"][idx] = np.round(salary_usd, 2)
        fx = np.array([float(self.zone_cfg[c]["fx_to_usd"]) for c in self.e["country"][idx]])
        self.e["salary_local"][idx] = np.round(salary_usd / fx, 2)

    def _record_salary(self, idx: np.ndarray, eff: dt.date, reason: str,
                       old_usd: np.ndarray, merit=0.0, promo=0.0, market=0.0):
        new_usd = self.e["salary_usd"][idx]
        pct = np.where(old_usd > 0, new_usd / np.maximum(old_usd, 1) - 1, 0.0)
        year = self._range_year(eff.year)
        mids = self.midpoints(self.e["job_id"][idx], self.e["country"][idx], year)
        merit_a = np.broadcast_to(np.asarray(merit, dtype=float), pct.shape)
        promo_a = np.broadcast_to(np.asarray(promo, dtype=float), pct.shape)
        market_a = np.broadcast_to(np.asarray(market, dtype=float), pct.shape)
        for k, i in enumerate(idx):
            self.salary_history.append({
                "employee_id": int(self.e["employee_id"][i]),
                "effective_date": eff,
                "change_reason": reason,
                "salary_amount_local": float(self.e["salary_local"][i]),
                "salary_amount_usd": float(new_usd[k]),
                "prior_salary_usd": float(old_usd[k]),
                "currency": self.e["currency"][i],
                "salary_basis": "Annual",
                "change_percentage": round(float(pct[k]), 6),
                "merit_percentage": round(float(merit_a[k]), 6),
                "promotion_percentage": round(float(promo_a[k]), 6),
                "market_adjustment_percentage": round(float(market_a[k]), 6),
                "job_id": int(self.e["job_id"][i]),
                "job_level": self.e["job_level"][i],
                "organization_id": int(self.e["organization_id"][i]),
                "compa_ratio": round(float(new_usd[k] / mids[k]), 4),
            })

    def _record_job_event(self, idx: np.ndarray, eff: dt.date, action: str, reason: str,
                          old_job=None, old_org=None, old_mgr=None, old_loc=None,
                          old_level=None):
        for k, i in enumerate(idx):
            self.job_history.append({
                "employee_id": int(self.e["employee_id"][i]),
                "effective_date": eff,
                "action": action,
                "reason": reason,
                "old_job_id": int(old_job[k]) if old_job is not None else 0,
                "new_job_id": int(self.e["job_id"][i]),
                "old_job_level": old_level[k] if old_level is not None else "Not Applicable",
                "new_job_level": self.e["job_level"][i],
                "old_organization_id": int(old_org[k]) if old_org is not None else 0,
                "new_organization_id": int(self.e["organization_id"][i]),
                "old_manager_employee_id": int(old_mgr[k]) if old_mgr is not None else 0,
                "new_manager_employee_id": int(self.e["manager_id"][i]),
                "old_location_id": int(old_loc[k]) if old_loc is not None else 0,
                "new_location_id": int(self.e["location_id"][i]),
                "salary_usd": float(self.e["salary_usd"][i]),
            })

    # --------------------------------------------------------------- seeding
    def _draw_attributes(self, idx: np.ndarray, month_idx: int, countries=None,
                         functions=None, orgs=None, is_acquired=0):
        rng, s = self.rng, self.s
        k = len(idx)
        e = self.e

        if countries is None:
            countries = R.weighted_choice(rng, s.baseline["country_mix"], k)
        e["country"][idx] = countries
        e["currency"][idx] = [self.zone_cfg[c]["currency"] for c in countries]

        if orgs is None:
            if functions is None:
                functions = R.weighted_choice(rng, s.baseline["function_mix"], k)
            eff_month = self.months[month_idx]
            orgs = np.empty(k, dtype="int32")
            for fn in np.unique(functions):
                pool = self.leaf_by_function.get(fn, np.array([], dtype=int))
                pool = np.array([o for o in pool
                                 if self.org_effective[o] <= eff_month
                                 and self.org_active[o] == 1])
                if len(pool) == 0:
                    pool = self.leaf_by_function[fn]
                hit = functions == fn
                orgs[hit] = rng.choice(pool, size=int(hit.sum()))
        e["organization_id"][idx] = orgs
        e["function_name"][idx] = [self.org_function[int(o)] for o in orgs]

        # Location: a site in the employee's country.
        locs = np.empty(k, dtype="int32")
        for c in np.unique(countries):
            hit = countries == c
            pool = self.loc_by_country[c]
            if is_acquired:
                acq_pool = np.array([l for l in pool if l in self.acquired_locs])
                pool = acq_pool if len(acq_pool) else pool
            else:
                trimmed = np.array([l for l in pool if l not in self.acquired_locs])
                pool = trimmed if len(trimmed) else pool
            locs[hit] = rng.choice(pool, size=int(hit.sum()))
        e["location_id"][idx] = locs

        levels = R.weighted_choice(rng, s.baseline["level_mix"], k)
        e["job_level"][idx] = levels
        job_ids = np.zeros(k, dtype="int32")
        tracks = np.empty(k, dtype=object)
        for i, (fn, lvl) in enumerate(zip(e["function_name"][idx], levels)):
            job_ids[i], tracks[i] = self._pick_job(fn, lvl)
        e["job_id"][idx] = job_ids
        e["career_track"][idx] = tracks
        e["job_level"][idx] = [self.job_level_of[int(j)] for j in job_ids]

        e["fte"][idx] = np.where(rng.random(k) < s.baseline["fte_part_time_share"],
                                 rng.choice([0.5, 0.6, 0.8], size=k), 1.0)
        e["worker_type"][idx] = np.where(
            rng.random(k) < s.baseline["contingent_worker_share"],
            rng.choice(["Fixed Term", "Contingent"], size=k, p=[0.55, 0.45]), "Regular")
        e["is_acquired"][idx] = is_acquired
        e["active"][idx] = 1

        # Names matched to the country's name culture.
        for c in np.unique(countries):
            hit = np.where(countries == c)[0]
            first, last = R.make_name_pool(rng, R.COUNTRY_NAME_CULTURE[c], len(hit))
            e["first_name"][idx[hit]] = first
            e["last_name"][idx[hit]] = last

        # Age rises with level; a Distinguished Engineer is not 24.
        lvl_num = np.array([int(l[1]) for l in e["job_level"][idx]])
        age = 23 + lvl_num * 2.6 + rng.normal(0, 4.5, k)
        age = np.clip(age, 20, 66)
        return age

    def _pick_job(self, function: str, level: str):
        rng = self.rng
        for track in ("Individual Contributor", "Manager", "Director", "Executive"):
            pool = self.job_by_slot.get((function, level, track))
            if pool is not None and len(pool):
                # Senior levels are more likely to be management-track.
                if track == "Individual Contributor" and level in ("L4", "L5", "L6", "L7"):
                    mgmt = self.job_by_slot.get((function, level, "Manager"))
                    if mgmt is None or not len(mgmt):
                        mgmt = self.job_by_slot.get((function, level, "Director"))
                    if mgmt is not None and len(mgmt) and rng.random() < 0.28:
                        jid = int(rng.choice(mgmt))
                        return jid, self.job_track_of[jid]
                jid = int(rng.choice(pool))
                return jid, self.job_track_of[jid]
        any_pool = self.jobs["job_id"].to_numpy()
        jid = int(rng.choice(any_pool))
        return jid, self.job_track_of[jid]

    def seed(self):
        s, rng = self.s, self.rng
        target = int(s.sizes["employees_at_as_of"])
        years = len(self.months) / 12.0
        g = float(s.baseline["headcount_growth_yoy"])
        n0 = int(round(target / ((1 + g) ** years)))

        self._alloc(int(target * 3.2))
        idx = self._new_rows(n0)
        age = self._draw_attributes(idx, 0)

        # Tenure at the start of history: lognormal, median ~2.5 years.
        tenure_months = np.clip(rng.lognormal(3.3, 0.85, n0), 1, 300).astype(int)
        start = self.months[0]
        hire_dates = [_add_month(start, -int(t)) + dt.timedelta(days=int(rng.integers(0, 27)))
                      for t in tenure_months]
        self.e["hire_date"][idx] = hire_dates
        self.e["hire_month"][idx] = -tenure_months
        self.e["birth_date"][idx] = [
            h - dt.timedelta(days=int(a * 365.25)) for h, a in zip(hire_dates, age)]
        self.e["last_promo_month"][idx] = -np.clip(
            rng.integers(1, 40, n0), 1, tenure_months).astype("int16")
        self.e["rating"][idx] = R.weighted_choice(
            rng, {int(k): v for k, v in s.performance["rating_distribution"].items()},
            n0).astype("int8")
        self.e["prior_rating"][idx] = self.e["rating"][idx]
        self._draw_demographics(idx)

        # Starting salaries, placed across the range.
        lo, hi = s.comp["starting_compa"]
        compa = rng.uniform(lo, hi, n0)
        # Long-tenure employees drift up the range; new joiners sit lower.
        compa *= 1 + np.clip(tenure_months / 240, 0,
                             float(s.comp.get("tenure_compa_uplift_max", 0.08)))
        mids = self.midpoints(self.e["job_id"][idx], self.e["country"][idx],
                              self.months[0].year)
        self._set_salary_usd(idx, compa * mids)
        self._backfill_salary_history(idx)
        self._record_job_event(idx, self.months[0], "Hire", "Existing Employee")

    def _draw_demographics(self, idx: np.ndarray):
        rng, k = self.rng, len(idx)
        self.e["gender"][idx] = rng.choice(
            ["Female", "Male", "Non-Binary", "Not Declared"], size=k,
            p=[0.402, 0.571, 0.012, 0.015])
        eth = np.empty(k, dtype=object)
        for c in np.unique(self.e["country"][idx]):
            hit = self.e["country"][idx] == c
            eth[hit] = R.weighted_choice(rng, R.ETHNICITY_MIX[c], int(hit.sum()))
        self.e["ethnicity"][idx] = eth
        self.e["veteran_status"][idx] = np.where(
            (self.e["country"][idx] == "US") & (rng.random(k) < 0.061),
            "Veteran", "Not a Veteran")
        self.e["disability_status"][idx] = rng.choice(
            ["No Disability", "Has Disability", "Not Declared"], size=k,
            p=[0.874, 0.046, 0.080])

    def _backfill_salary_history(self, idx: np.ndarray):
        """Give the seeded population a plausible salary trail before day one.

        Without it every pre-existing employee has exactly one salary row and
        "salary progression" is a question the dataset cannot answer.
        """
        rng, s = self.rng, self.s
        merit_month = int(s.calendar["merit_cycle_month"])
        merit = float(s.baseline["merit_budget_pct"])
        start = self.months[0]
        for i in idx:
            hire = self.e["hire_date"][i]
            cycles = []
            year = hire.year if hire.month <= merit_month else hire.year + 1
            while dt.date(year, merit_month, 1) < start:
                cycles.append(dt.date(year, merit_month, 1))
                year += 1
            cycles = cycles[-4:]                      # four years of trail is plenty
            current = float(self.e["salary_usd"][i])
            steps = []
            for _ in cycles:
                pct = max(rng.normal(merit, 0.012), 0.0)
                steps.append(pct)
                current /= (1 + pct)
            fx = float(self.zone_cfg[self.e["country"][i]]["fx_to_usd"])
            eid = int(self.e["employee_id"][i])
            running = current
            self.salary_history.append({
                "employee_id": eid, "effective_date": hire,
                "change_reason": "New Hire",
                "salary_amount_local": round(running / fx, 2),
                "salary_amount_usd": round(running, 2),
                "prior_salary_usd": 0.0, "currency": self.e["currency"][i],
                "salary_basis": "Annual", "change_percentage": 0.0,
                "merit_percentage": 0.0, "promotion_percentage": 0.0,
                "market_adjustment_percentage": 0.0,
                "job_id": int(self.e["job_id"][i]), "job_level": self.e["job_level"][i],
                "organization_id": int(self.e["organization_id"][i]),
                "compa_ratio": 0.0,
            })
            for eff, pct in zip(cycles, steps):
                prior = running
                running *= (1 + pct)
                self.salary_history.append({
                    "employee_id": eid, "effective_date": eff,
                    "change_reason": "Annual Merit",
                    "salary_amount_local": round(running / fx, 2),
                    "salary_amount_usd": round(running, 2),
                    "prior_salary_usd": round(prior, 2),
                    "currency": self.e["currency"][i], "salary_basis": "Annual",
                    "change_percentage": round(pct, 6), "merit_percentage": round(pct, 6),
                    "promotion_percentage": 0.0, "market_adjustment_percentage": 0.0,
                    "job_id": int(self.e["job_id"][i]), "job_level": self.e["job_level"][i],
                    "organization_id": int(self.e["organization_id"][i]),
                    "compa_ratio": 0.0,
                })

    # ---------------------------------------------------------- monthly steps
    def _active(self) -> np.ndarray:
        return np.where(self.e["active"][:self.n] == 1)[0]

    def _hazard(self, idx: np.ndarray, m: int) -> np.ndarray:
        """Monthly voluntary-resignation probability for each active employee."""
        s, a = self.s, self.s.attrition
        e = self.e
        month = self.months[m]
        flat = self.hp_attrition is None      # disabling Event 9 flattens the drivers

        compa = self._compa(idx, month.year)
        mult = np.ones(len(idx))
        if not flat:
            mult *= _band_lookup(a["compa_multiplier"], compa)
            rating_map = {int(k): float(v) for k, v in a["rating_multiplier"].items()}
            mult *= np.array([rating_map[int(r)] for r in e["rating"][idx]])
        since_promo = (m - e["last_promo_month"][idx]).astype(float)
        mult *= _band_lookup(a["months_since_promotion_multiplier"], since_promo)
        tenure = (m - e["hire_month"][idx]).astype(float)
        mult *= _band_lookup(a["tenure_multiplier"], tenure)
        mult *= np.array([a["country_multiplier"][c] for c in e["country"][idx]])
        mult *= np.array([a["function_multiplier"].get(f, 1.0)
                          for f in e["function_name"][idx]])
        mult *= float(a["seasonality"][month.month - 1])

        # Event 2 - sales attrition spike, on the named job families only.
        if self.ev_sales and self.ev_sales_window[0] <= month <= self.ev_sales_window[1]:
            fam = np.array([self.job_family[int(j)] for j in e["job_id"][idx]])
            in_function = e["function_name"][idx] == self.ev_sales["function"]
            hit = np.isin(fam, self.ev_sales["job_families"]) & in_function
            boost = np.where(
                hit, float(self.ev_sales["hazard_multiplier"]),
                np.where(in_function,
                         float(self.ev_sales.get("function_hazard_multiplier", 1.0)), 1.0))
            # The leavers skew good, which is the part that hurts.
            good = np.isin(e["rating"][idx], [4, 5])
            boost = np.where(hit & good, boost * float(self.ev_sales["high_performer_bias"]),
                             boost)
            mult *= boost

        # Event 10 - the manager problem.
        if self.ev_mgr is not None and len(self.mgr_problem_orgs):
            hit = np.isin(e["organization_id"][idx], self.mgr_problem_orgs)
            mult *= np.where(hit, float(self.ev_mgr["hazard_multiplier"]), 1.0)

        # Event 7 - acquired employees are a retention risk for two years.
        if self.ev_acq is not None:
            months_since = m - self.month_index.get(self.ev_acq_month, 0)
            if 0 <= months_since <= 24:
                mult *= np.where(e["is_acquired"][idx] == 1,
                                 float(self.ev_acq["retention_hazard_multiplier"]), 1.0)

        base = float(s.baseline["voluntary_attrition_annual"]) / 12.0
        # New joiners in their first weeks essentially never resign.
        mult *= np.where(tenure < 2, 0.15, 1.0)
        return np.clip(base * mult, 0.0, 0.08)

    def _terminate(self, m: int):
        rng, s, e = self.rng, self.s, self.e
        idx = self._active()
        if len(idx) == 0:
            return
        month = self.months[m]
        p_vol = self._hazard(idx, m)
        vol = rng.random(len(idx)) < p_vol

        inv_base = float(s.baseline["involuntary_attrition_annual"]) / 12.0
        rating_mult = {1: 4.2, 2: 2.0, 3: 0.55, 4: 0.18, 5: 0.10}
        tenure = (m - e["hire_month"][idx]).astype(float)
        p_inv = np.clip(inv_base * np.array([rating_mult[int(r)] for r in e["rating"][idx]])
                        * np.where(tenure < 4, 0.2, 1.0), 0, 0.05)
        inv = (~vol) & (rng.random(len(idx)) < p_inv)

        leaving = idx[vol | inv]
        if len(leaving) == 0:
            return
        is_vol = vol[vol | inv]
        days = rng.integers(0, 27, len(leaving))
        term_dates = [month + dt.timedelta(days=int(d)) for d in days]
        e["active"][leaving] = 0
        e["term_month"][leaving] = m
        e["term_date"][leaving] = term_dates

        regret_cfg = {int(k): float(v)
                      for k, v in s.attrition["regrettable_share_by_rating"].items()}
        compa = self._compa(leaving, month.year)
        for k, i in enumerate(leaving):
            voluntary = bool(is_vol[k])
            rating = int(e["rating"][i])
            if voluntary:
                # The stated reason lines up with the driver, so "why are people
                # leaving" has a real answer and not just a random label.
                if compa[k] < 0.92 and rng.random() < 0.55:
                    reason = "Compensation"
                elif (self.ev_mgr and e["organization_id"][i] in self.mgr_problem_orgs
                      and rng.random() < 0.5):
                    reason = "Manager"
                elif (m - e["last_promo_month"][i]) > 30 and rng.random() < 0.45:
                    reason = "Career Growth"
                else:
                    reason = str(rng.choice(R.TERMINATION_REASONS_VOLUNTARY))
                regrettable = int(rng.random() < regret_cfg[rating])
            else:
                reason = "Performance" if rating <= 2 else str(
                    rng.choice(R.TERMINATION_REASONS_INVOLUNTARY))
                regrettable = 0
            hire = e["hire_date"][i]
            yos = (term_dates[k] - hire).days / 365.25
            self.terminations.append({
                "employee_id": int(e["employee_id"][i]),
                "termination_date": term_dates[k],
                "termination_type": "Voluntary" if voluntary else "Involuntary",
                "termination_reason": reason,
                "termination_category": ("Resignation" if voluntary and reason != "Retirement"
                                         else "Retirement" if reason == "Retirement"
                                         else "Layoff" if reason in ("Layoff", "Restructuring")
                                         else "Termination"),
                "voluntary_flag": int(voluntary),
                "regrettable_flag": regrettable,
                "years_of_service": round(float(yos), 2),
                "organization_id": int(e["organization_id"][i]),
                "job_id": int(e["job_id"][i]),
                "job_level": e["job_level"][i],
                "manager_employee_id": int(e["manager_id"][i]),
                "location_id": int(e["location_id"][i]),
                "country": e["country"][i],
                "performance_rating": rating,
                "compa_ratio_at_exit": round(float(compa[k]), 4),
                "salary_usd_at_exit": float(e["salary_usd"][i]),
                "is_acquired": int(e["is_acquired"][i]),
            })
        self._record_job_event(leaving, month, "Termination", "Exit",
                               old_job=e["job_id"][leaving],
                               old_level=e["job_level"][leaving],
                               old_org=e["organization_id"][leaving],
                               old_mgr=e["manager_id"][leaving],
                               old_loc=e["location_id"][leaving])

    def _review(self, m: int):
        """Annual performance cycle, with persistence from the prior rating."""
        rng, s, e = self.rng, self.s, self.e
        month = self.months[m]
        if month.month != int(s.calendar["review_cycle_month"]):
            return
        idx = self._active()
        idx = idx[(m - e["hire_month"][idx]) >= 6]
        if len(idx) == 0:
            return
        dist = {int(k): float(v) for k, v in s.performance["rating_distribution"].items()}
        drawn = R.weighted_choice(rng, dist, len(idx)).astype(int)
        prior = e["rating"][idx].astype(int)
        keep = rng.random(len(idx)) < 0.45          # ratings are sticky
        new = np.where(keep, prior, drawn)

        if self.ev_mgr is not None and len(self.mgr_problem_orgs):
            hit = np.isin(e["organization_id"][idx], self.mgr_problem_orgs)
            shift = float(self.ev_mgr["rating_shift"])
            nudged = np.clip(np.round(new + shift), 1, 5).astype(int)
            new = np.where(hit, nudged, new)

        e["prior_rating"][idx] = prior
        e["rating"][idx] = new.astype("int8")
        e["reviewed"][idx] = 1

        potential = np.clip(np.round(
            new * s.performance["potential_correlation"]
            + rng.normal(3, 1.1, len(idx)) * (1 - s.performance["potential_correlation"])),
            1, 5).astype(int)
        goal = np.clip(new * 18 + rng.normal(8, 7, len(idx)), 20, 100)
        comp = np.clip(new * 17 + rng.normal(12, 8, len(idx)), 20, 100)
        review_date = month + dt.timedelta(days=14)
        merit_rec = {1: 0.0, 2: 0.5, 3: 0.9, 4: 1.35, 5: 1.85}
        for k, i in enumerate(idx):
            self.reviews.append({
                "employee_id": int(e["employee_id"][i]),
                "review_year": month.year,
                "review_date": review_date,
                "review_period": f"FY{month.year - 1}",
                "performance_rating": int(new[k]),
                "performance_rating_label": {1: "Needs Improvement", 2: "Developing",
                                             3: "Successful", 4: "Exceeds Expectations",
                                             5: "Exceptional"}[int(new[k])],
                "potential_rating": int(potential[k]),
                "goal_score": round(float(goal[k]), 1),
                "competency_score": round(float(comp[k]), 1),
                "overall_score": round(float(goal[k] * 0.6 + comp[k] * 0.4), 1),
                "promotion_recommendation": int(new[k] >= 4 and rng.random() < 0.42),
                "merit_recommendation_pct": round(
                    float(s.baseline["merit_budget_pct"] * merit_rec[int(new[k])]), 4),
                "review_status": "Completed",
                "organization_id": int(e["organization_id"][i]),
                "job_id": int(e["job_id"][i]),
                "job_level": e["job_level"][i],
                "manager_employee_id": int(e["manager_id"][i]),
            })

    def _promote(self, m: int):
        rng, s, e = self.rng, self.s, self.e
        month = self.months[m]
        idx = self._active()
        idx = idx[((m - e["hire_month"][idx]) >= 12)
                  & ((m - e["last_promo_month"][idx]) >= 12)
                  & (e["job_level"][idx] != "L9")]
        if len(idx) == 0:
            return
        odds = {int(k): float(v) for k, v in s.performance["promotion_odds_by_rating"].items()}
        base = float(s.baseline["promotion_rate_annual"]) / 12.0
        p = base * np.array([odds[int(r)] for r in e["rating"][idx]])
        chosen = idx[rng.random(len(idx)) < np.clip(p, 0, 0.2)]

        # Event 4 - the promotion wave, on top of the ordinary cycle.
        if self.ev_promo and month == self.ev_promo_month:
            pool = self._active()
            pool = pool[(e["function_name"][pool] == self.ev_promo["function"])
                        & (e["job_level"][pool] == self.ev_promo["from_level"])]
            k = min(self.s.scaled(self.ev_promo["promoted_share"]), len(pool))
            if k:
                chosen = np.union1d(chosen, rng.choice(pool, size=k, replace=False))

        if len(chosen) == 0:
            return
        old_job = e["job_id"][chosen].copy()
        old_level = e["job_level"][chosen].copy()
        old_usd = e["salary_usd"][chosen].copy()
        wave = (self.ev_promo and month == self.ev_promo_month)
        lo, hi = (self.ev_promo["increase_pct"] if wave
                  else s.baseline["promotion_increase_pct"])
        bump = rng.uniform(lo, hi, len(chosen))
        for k, i in enumerate(chosen):
            lvl = e["job_level"][i]
            nxt = f"L{min(int(lvl[1]) + 1, 9)}"
            fam = self.job_family[int(e["job_id"][i])]
            pool = self.jobs_by_family_level.get((fam, nxt))
            if pool is None or not len(pool):
                jid, track = self._pick_job(e["function_name"][i], nxt)
            else:
                jid = int(rng.choice(pool))
                track = self.job_track_of[jid]
            e["job_id"][i] = jid
            e["job_level"][i] = self.job_level_of[jid]
            e["career_track"][i] = track
            e["last_promo_month"][i] = m
        self._set_salary_usd(chosen, old_usd * (1 + bump))
        self._record_salary(chosen, month, "Promotion", old_usd, promo=bump)
        self._record_job_event(chosen, month, "Promotion",
                               "Promotion Wave" if wave else "Annual Promotion Cycle",
                               old_job=old_job, old_level=old_level,
                               old_org=e["organization_id"][chosen],
                               old_mgr=e["manager_id"][chosen],
                               old_loc=e["location_id"][chosen])

    def _merit(self, m: int):
        rng, s, e = self.rng, self.s, self.e
        month = self.months[m]
        if month.month != int(s.calendar["merit_cycle_month"]):
            return
        idx = self._active()
        idx = idx[(m - e["hire_month"][idx]) >= 6]
        if len(idx) == 0:
            return
        mult = {int(k): float(v)
                for k, v in s.performance["merit_multiplier_by_rating"].items()}
        budget = float(s.baseline["merit_budget_pct"])
        pct = budget * np.array([mult[int(r)] for r in e["rating"][idx]])
        pct = np.clip(pct * rng.normal(1.0, 0.16, len(idx)), 0.0, 0.14)

        # Event 3 - incumbents in the affected function are capped below market
        # movement while new hires arrive at midpoint. Compression is not tagged
        # onto chosen employees; it accumulates out of this cap.
        if self.ev_compress and month >= self.ev_compress_start:
            hit = ((e["function_name"][idx] == self.ev_compress["function"])
                   & (e["hire_month"][idx] < self.month_index.get(
                       self.ev_compress_start, 0)))
            pct = np.where(hit, np.minimum(pct, float(self.ev_compress["incumbent_merit_cap"])),
                           pct)

        old_usd = e["salary_usd"][idx].copy()
        self._set_salary_usd(idx, old_usd * (1 + pct))
        self._record_salary(idx, month, "Annual Merit", old_usd, merit=pct)

    def _market_adjust(self, m: int):
        rng, s, e = self.rng, self.s, self.e
        month = self.months[m]
        idx = self._active()
        idx = idx[(m - e["hire_month"][idx]) >= 9]
        if len(idx) == 0:
            return
        compa = self._compa(idx, month.year)
        # Targeted at employees deep below midpoint - which is the intervention a
        # real comp team would make, and it deliberately does not reach everyone.
        pressure = np.clip((0.95 - compa) / 0.15, 0, 1.4)
        intensity = float(s.comp.get("market_adjustment_intensity", 0.35))
        p = (float(s.baseline["market_adjustment_rate_annual"]) / 12.0) * pressure * intensity
        # Event 3 - the company is NOT fixing the compression, which is the whole
        # question the demo asks. Off-cycle corrections stop reaching the
        # affected function while the event runs.
        if self.ev_compress and month >= self.ev_compress_start:
            p = np.where(e["function_name"][idx] == self.ev_compress["function"],
                         p * 0.15, p)
        chosen = idx[rng.random(len(idx)) < np.clip(p, 0, 0.02)]
        if len(chosen) == 0:
            return
        old_usd = e["salary_usd"][chosen].copy()
        mids = self.midpoints(e["job_id"][chosen], e["country"][chosen], month.year)
        target = mids * rng.uniform(0.93, 1.00, len(chosen))
        new = np.maximum(old_usd * 1.005, target)
        self._set_salary_usd(chosen, new)
        pct = new / old_usd - 1
        self._record_salary(chosen, month, "Market Adjustment", old_usd, market=pct)

    def _transfer(self, m: int):
        rng, e = self.rng, self.e
        month = self.months[m]
        idx = self._active()

        # Event 8 - the Marketing reorganisation. Everyone in the retired
        # divisions moves in one month, which is what makes the hierarchy history
        # worth querying.
        if self.ev_reorg and month == self.ev_reorg_month and len(self.reorg_target_orgs):
            pool = idx[e["function_name"][idx] == self.ev_reorg["from_organization"]]
            k = int(round(len(pool) * float(self.ev_reorg["moved_share"])))
            movers = rng.choice(pool, size=k, replace=False) if k else np.array([], int)
            if len(movers):
                old_org = e["organization_id"][movers].copy()
                e["organization_id"][movers] = rng.choice(self.reorg_target_orgs, size=len(movers))
                self._record_job_event(movers, month, "Reorganization",
                                       "Marketing Reorganization",
                                       old_job=e["job_id"][movers],
                                       old_level=e["job_level"][movers],
                                       old_org=old_org,
                                       old_mgr=e["manager_id"][movers],
                                       old_loc=e["location_id"][movers])
            idx = np.setdiff1d(idx, movers)

        # Ordinary internal mobility.
        movers = idx[rng.random(len(idx)) < 0.004]
        if len(movers) == 0:
            return
        old_org = e["organization_id"][movers].copy()
        old_job = e["job_id"][movers].copy()
        old_loc = e["location_id"][movers].copy()
        cross = rng.random(len(movers)) < 0.28
        for k, i in enumerate(movers):
            fn = e["function_name"][i]
            if cross[k]:
                fn = str(rng.choice(list(self.leaf_by_function)))
            pool = [o for o in self.leaf_by_function.get(fn, [])
                    if self.org_effective[o] <= month and self.org_active[o] == 1]
            if not pool:
                continue
            e["organization_id"][i] = int(rng.choice(pool))
            e["function_name"][i] = self.org_function[int(e["organization_id"][i])]
            if cross[k]:
                jid, track = self._pick_job(e["function_name"][i], e["job_level"][i])
                e["job_id"][i] = jid
                e["career_track"][i] = track
        self._record_job_event(movers, month, "Transfer",
                               "Internal Mobility", old_job=old_job,
                               old_level=e["job_level"][movers], old_org=old_org,
                               old_mgr=e["manager_id"][movers], old_loc=old_loc)

    def _hire(self, m: int):
        rng, s, e = self.rng, self.s, self.e
        month = self.months[m]
        target_total = int(s.sizes["employees_at_as_of"])
        g = float(s.baseline["headcount_growth_yoy"])
        years_from_end = (len(self.months) - 1 - m) / 12.0
        target_now = target_total / ((1 + g) ** years_from_end)
        gap = int(round(target_now - len(self._active())))

        batches: list[tuple[int, dict]] = []

        # Keep the manager-problem org staffed to the size the event needs. It
        # churns at several times the company rate, so left alone it bleeds down
        # to a handful of people and the signal disappears into small-sample
        # noise. These hires come OUT of the ordinary gap, not on top of it.
        mgr_fill = 0
        if self.ev_mgr is not None and len(self.mgr_problem_orgs) and gap > 0:
            here = int(np.isin(e["organization_id"][self._active()],
                               self.mgr_problem_orgs).sum())
            want = self.s.scaled(self.ev_mgr.get("min_org_headcount_share", 0.0))
            if here < want:
                mgr_fill = min(gap, max(int(np.ceil((want - here) / 3)), 1))
                gap -= mgr_fill

        if gap > 0:
            batches.append((gap, {"functions": self._backfill_functions(gap, target_now)}))
        if mgr_fill > 0:
            batches.append((mgr_fill, {"orgs": self.mgr_problem_orgs}))

        # Event 1 - the engineering hiring surge, spread over its window.
        if self.ev_surge and self.ev_surge_window[0] <= month <= self.ev_surge_window[1]:
            span = max(self.month_index[self.ev_surge_window[1]]
                       - self.month_index[self.ev_surge_window[0]] + 1, 1)
            per = int(round(s.scaled(self.ev_surge["extra_hires_share"]) / span))
            if per and len(self.surge_orgs):
                batches.append((per, {"orgs": self.surge_orgs}))

        # Event 7 - the acquisition arrives in a single month.
        if self.ev_acq and month == self.ev_acq_month and len(self.acq_orgs):
            n = s.scaled(self.ev_acq["headcount_share"])
            batches.append((n, {"orgs": self.acq_orgs, "acquired": True,
                                "country_mix": self.ev_acq["countries"],
                                "compa_shift": float(self.ev_acq["compa_shift"])}))

        for count, opts in batches:
            if count <= 0:
                continue
            self._hire_batch(m, count, **opts)

    def _backfill_functions(self, count: int, target_total: float) -> np.ndarray:
        """Weight backfill hiring towards whichever functions are short.

        Drawing hires straight from the target mix lets high-attrition functions
        bleed out permanently - Sales ends the run five points light and the
        headcount-by-function chart drifts away from the story on its own.
        """
        rng, e = self.rng, self.e
        idx = self._active()
        mix = self.s.baseline["function_mix"]
        current = pd.Series(e["function_name"][idx]).value_counts()
        deficit = {fn: max(share * target_total - float(current.get(fn, 0)), 0.0)
                   for fn, share in mix.items()}
        total = sum(deficit.values())
        weights = ({fn: d / total for fn, d in deficit.items()} if total > 0 else mix)
        return R.weighted_choice(rng, weights, count)

    def _hire_batch(self, m: int, count: int, orgs=None, acquired=False,
                    country_mix=None, compa_shift=0.0, functions=None):
        rng, s, e = self.rng, self.s, self.e
        month = self.months[m]
        if self.n + count > self.capacity:
            count = self.capacity - self.n
        if count <= 0:
            return
        idx = self._new_rows(count)
        if country_mix is None:
            country_mix = s.baseline.get("hiring_country_mix")
        countries = (R.weighted_choice(rng, country_mix, count)
                     if country_mix else None)
        org_pick = rng.choice(orgs, size=count) if orgs is not None else None
        if functions is not None:
            functions = np.asarray(functions)[:count]
        age = self._draw_attributes(idx, m, countries=countries, orgs=org_pick,
                                    functions=functions, is_acquired=int(acquired))
        hire_dates = [month + dt.timedelta(days=int(d))
                      for d in rng.integers(0, 27, count)]
        e["hire_date"][idx] = hire_dates
        e["hire_month"][idx] = m
        e["last_promo_month"][idx] = m
        e["birth_date"][idx] = [h - dt.timedelta(days=int(a * 365.25))
                                for h, a in zip(hire_dates, age)]
        e["rating"][idx] = 3
        e["prior_rating"][idx] = 3
        self._draw_demographics(idx)

        lo, hi = s.comp["new_hire_compa"]
        # Event 3 - new hires into the affected function come in at midpoint
        # while incumbents are capped. That gap IS the compression.
        if self.ev_compress and month >= self.ev_compress_start:
            hit = e["function_name"][idx] == self.ev_compress["function"]
            elo, ehi = self.ev_compress["new_hire_compa"]
            compa = np.where(hit, rng.uniform(elo, ehi, count), rng.uniform(lo, hi, count))
        else:
            compa = rng.uniform(lo, hi, count)
        compa = compa + compa_shift
        mids = self.midpoints(e["job_id"][idx], e["country"][idx], month.year)
        self._set_salary_usd(idx, compa * mids)
        reason = "Acquisition" if acquired else "New Hire"
        self._record_salary(idx, month, "New Hire", np.zeros(count))
        self._record_job_event(idx, month, "Hire", reason)

    def _refresh_managers(self, m: int) -> np.ndarray:
        """Rebuild the org -> manager map and return employees whose manager moved.

        An org's manager is the most senior person anywhere in its SUBTREE,
        preferring management-track jobs. Picking from direct members only looks
        equivalent and is not: employees sit in leaf teams, so every department,
        division and function comes back empty, every team lead reports to
        nobody, and the whole hierarchy collapses to one level deep.

        The assignment is also STICKY - a sitting manager keeps the org until
        they leave it. Recomputing from scratch each month breaks ties
        differently every time and fills the history with tens of thousands of
        phantom Manager Change rows no real HR system would produce.
        """
        e = self.e
        idx = self._active()
        if len(idx) == 0:
            return np.array([], dtype=int)

        level_rank = np.array([int(l[1]) for l in e["job_level"][idx]])
        mgr_bonus = np.array([0.5 if self.job_track_of[int(j)] != "Individual Contributor"
                              else 0.0 for j in e["job_id"][idx]])
        score = {int(i): float(r + b) for i, r, b in zip(idx, level_rank, mgr_bonus)}

        direct: dict[int, list[int]] = {}
        for i in idx:
            direct.setdefault(int(e["organization_id"][i]), []).append(int(i))

        sitting = getattr(self, "org_manager", {})
        active_set = set(int(i) for i in idx)

        best: dict[int, int] = {}
        for org in self.org_by_depth:                 # deepest first
            pool = list(direct.get(org, []))
            for child in self.org_children.get(org, []):
                if child in best:
                    pool.append(best[child])
            if not pool:
                continue
            incumbent = sitting.get(org)
            if incumbent in active_set and incumbent in pool:
                best[org] = int(incumbent)            # sticky
            else:
                best[org] = max(pool, key=lambda i: (score.get(i, 0.0), -i))
        self.org_manager = best

        def manager_for(org: int, exclude: int) -> int:
            seen = 0
            while org and seen < 12:
                who = best.get(org)
                if who is not None and who != exclude:
                    return int(e["employee_id"][who])
                org = int(self.org_parent.get(org, 0))
                seen += 1
            return 0

        old = e["manager_id"][idx].copy()
        for i in idx:
            org = int(e["organization_id"][i])
            # Walk up from the first org this person does NOT already head.
            while best.get(org) == int(i):
                org = int(self.org_parent.get(org, 0))
                if not org:
                    break
            e["manager_id"][i] = manager_for(org, int(i)) if org else 0
        return idx[(old != e["manager_id"][idx]) & (old != 0)]

    def _snapshot(self, m: int):
        e = self.e
        idx = self._active()
        if len(idx) == 0:
            return
        month = self.months[m]
        eom = month_end(month)
        compa = self._compa(idx, month.year)
        mids = self.midpoints(e["job_id"][idx], e["country"][idx], month.year)
        tenure = np.array([(eom - h).days / 365.25 for h in e["hire_date"][idx]])
        orgs = e["organization_id"][idx]
        self.snapshots.append({
            "employee_id": e["employee_id"][idx].copy(),
            "snapshot_date": np.array([eom] * len(idx), dtype=object),
            "year_month_key": np.full(len(idx), month.year * 100 + month.month, "int32"),
            "organization_id": orgs.copy(),
            "job_id": e["job_id"][idx].copy(),
            "job_level": e["job_level"][idx].copy(),
            "career_track": e["career_track"][idx].copy(),
            "function_name": e["function_name"][idx].copy(),
            "location_id": e["location_id"][idx].copy(),
            "country": e["country"][idx].copy(),
            "manager_employee_id": e["manager_id"][idx].copy(),
            "fte": e["fte"][idx].copy(),
            "worker_type": e["worker_type"][idx].copy(),
            "base_salary_usd": np.round(e["salary_usd"][idx], 2),
            "base_salary_local": np.round(e["salary_local"][idx], 2),
            "currency": e["currency"][idx].copy(),
            "range_midpoint_usd": mids,
            "compa_ratio": np.round(compa, 4),
            "performance_rating": e["rating"][idx].copy(),
            "tenure_years": np.round(tenure, 2),
            "months_since_promotion": (m - e["last_promo_month"][idx]).astype("int16"),
            "is_acquired": e["is_acquired"][idx].copy(),
            "is_people_manager": np.array(
                [self.job_track_of[int(j)] != "Individual Contributor"
                 for j in e["job_id"][idx]], dtype="int8"),
            "cost_center": np.array([self.org_cost_center[int(o)] for o in orgs],
                                    dtype=object),
        })

    # -------------------------------------------------------------------- run
    def run(self) -> dict:
        self.seed()
        self._refresh_managers(0)
        for m, month in enumerate(self.months):
            self._terminate(m)
            self._review(m)
            self._promote(m)
            self._merit(m)
            self._market_adjust(m)
            self._transfer(m)
            self._hire(m)
            changed = self._refresh_managers(m)
            if len(changed):
                self._record_job_event(changed, month, "Manager Change",
                                       "Supervisory Organization Change",
                                       old_job=self.e["job_id"][changed],
                                       old_level=self.e["job_level"][changed],
                                       old_org=self.e["organization_id"][changed],
                                       old_loc=self.e["location_id"][changed])
            self._snapshot(m)
        return self._emit()

    # ------------------------------------------------------------------ emit
    def _emit(self) -> dict:
        s, e, rng = self.s, self.e, self.rng
        n = self.n
        sl = slice(0, n)
        as_of = self.s.timeline.as_of_date

        loc = self.locs.set_index("location_id")
        emp = pd.DataFrame({
            "employee_id": e["employee_id"][sl].astype("int32"),
            "first_name": e["first_name"][sl],
            "last_name": e["last_name"][sl],
            "country": e["country"][sl],
            "location_id": e["location_id"][sl].astype("int32"),
            "organization_id": e["organization_id"][sl].astype("int32"),
            "function_name": e["function_name"][sl],
            "job_id": e["job_id"][sl].astype("int32"),
            "job_level": e["job_level"][sl],
            "career_track": e["career_track"][sl],
            "manager_employee_id": e["manager_id"][sl].astype("int32"),
            "hire_date": e["hire_date"][sl],
            "termination_date": e["term_date"][sl],
            "employment_status": np.where(e["active"][sl] == 1, "Active", "Terminated"),
            "worker_type": e["worker_type"][sl],
            "fte": np.round(e["fte"][sl], 2),
            "base_salary_local": np.round(e["salary_local"][sl], 2),
            "base_salary_usd": np.round(e["salary_usd"][sl], 2),
            "currency": e["currency"][sl],
            "performance_rating": e["rating"][sl].astype("int8"),
            "birth_date": e["birth_date"][sl],
            "is_acquired": e["is_acquired"][sl].astype("int8"),
            "gender": e["gender"][sl],
            "ethnicity": e["ethnicity"][sl],
            "veteran_status": e["veteran_status"][sl],
            "disability_status": e["disability_status"][sl],
        })
        emp["employee_number"] = "EMP" + emp["employee_id"].astype(str).str.zfill(6)
        emp["employment_type"] = np.where(emp["fte"] >= 1.0, "Full-Time", "Part-Time")
        emp["pay_frequency"] = emp["country"].map(
            {c: z["pay_frequency"] for c, z in self.zone_cfg.items()})
        emp["cost_center"] = emp["organization_id"].map(self.org_cost_center)
        emp["exempt_status"] = emp["job_id"].map(self.job_exempt_of)
        emp["city"] = emp["location_id"].map(loc["city"])
        emp["state_province"] = emp["location_id"].map(loc["state_province"])
        emp["region"] = emp["location_id"].map(loc["region"])
        emp["organization_name"] = emp["organization_id"].map(self.org_name)
        emp["division_name"] = emp["organization_id"].map(self.org_division)
        emp["department_name"] = emp["organization_id"].map(self.org_department)
        emp["is_people_manager"] = emp["job_id"].map(
            lambda j: int(self.job_track_of[int(j)] != "Individual Contributor")
        ).astype("int8")
        term = pd.to_datetime(emp["termination_date"], errors="coerce")
        hire = pd.to_datetime(emp["hire_date"])
        end = term.fillna(pd.Timestamp(as_of))
        emp["tenure_years"] = ((end - hire).dt.days / 365.25).round(2)
        emp["age_years"] = ((pd.Timestamp(as_of) - pd.to_datetime(emp["birth_date"])).dt.days
                            / 365.25).round(1)
        emp["age_band"] = pd.cut(emp["age_years"], [0, 25, 35, 45, 55, 120],
                                 labels=["Under 25", "25-34", "35-44", "45-54", "55+"]
                                 ).astype(str)
        emp["tenure_band"] = pd.cut(emp["tenure_years"], [-0.01, 1, 3, 5, 10, 100],
                                    labels=["<1 year", "1-3 years", "3-5 years",
                                            "5-10 years", "10+ years"]).astype(str)
        emp["work_email"] = self._emails(emp)
        emp["is_active"] = (emp["employment_status"] == "Active").astype("int8")
        emp["is_duplicate_record"] = 0

        emp = self._plant_defects(emp)

        # The "No Manager" row. No foreign key in this dataset is ever NULL - an
        # employee at the top of the tree points here instead, which keeps the
        # 40 deliberately manager-less records queryable rather than invisible.
        placeholder = {c: "Not Applicable" for c in emp.columns}
        placeholder.update({
            "employee_id": 0, "first_name": "No", "last_name": "Manager",
            "employee_number": "EMP000000", "location_id": 0, "organization_id": 0,
            "job_id": 0, "manager_employee_id": 0, "hire_date": None,
            "termination_date": None, "employment_status": "Not Applicable",
            "fte": 0.0, "base_salary_local": 0.0, "base_salary_usd": 0.0,
            "performance_rating": 0, "birth_date": None, "is_acquired": 0,
            "is_people_manager": 0, "tenure_years": 0.0, "age_years": 0.0,
            "is_active": 0, "is_duplicate_record": 0,
            "work_email": "no.manager@globaltech.example",
        })
        emp = pd.concat([pd.DataFrame([placeholder]), emp], ignore_index=True)

        snap = pd.DataFrame({k: np.concatenate([b[k] for b in self.snapshots])
                             for k in self.snapshots[0]})
        snap.insert(0, "workforce_snapshot_id",
                    np.arange(1, len(snap) + 1, dtype="int64"))
        snap["organization_name"] = snap["organization_id"].map(self.org_name)
        snap["division_name"] = snap["organization_id"].map(self.org_division)
        snap["department_name"] = snap["organization_id"].map(self.org_department)
        snap["headcount"] = 1
        snap["fte_count"] = snap["fte"]

        jh = pd.DataFrame(self.job_history)
        jh.insert(0, "job_history_id", np.arange(1, len(jh) + 1, dtype="int64"))
        sh = pd.DataFrame(self.salary_history).sort_values(
            ["employee_id", "effective_date"]).reset_index(drop=True)
        sh.insert(0, "salary_history_id", np.arange(1, len(sh) + 1, dtype="int64"))
        # end_date closes each salary band so "salary on date X" is a range scan.
        sh["end_date"] = sh.groupby("employee_id")["effective_date"].shift(-1)
        sh["end_date"] = sh["end_date"].where(sh["end_date"].isna(),
                                              sh["end_date"] - pd.Timedelta(days=1))
        sh["end_date"] = sh["end_date"].fillna(pd.Timestamp("2099-12-31"))
        sh["end_date"] = pd.to_datetime(sh["end_date"]).dt.date
        sh["is_current"] = (pd.to_datetime(sh["end_date"])
                            >= pd.Timestamp("2099-01-01")).astype("int8")

        term_df = pd.DataFrame(self.terminations)
        term_df.insert(0, "termination_id", np.arange(1, len(term_df) + 1, dtype="int32"))
        rev = pd.DataFrame(self.reviews)
        rev.insert(0, "review_id", np.arange(1, len(rev) + 1, dtype="int32"))

        return {
            "dim_employee": emp,
            "fact_workforce_snapshot": snap,
            "fact_job_history": jh,
            "fact_salary_history": sh,
            "fact_termination": term_df,
            "fact_performance_review": rev,
        }

    def _emails(self, emp: pd.DataFrame) -> pd.Series:
        base = (emp["first_name"].str.lower() + "." + emp["last_name"].str.lower())
        dup = base.groupby(base).cumcount()
        return np.where(dup == 0, base, base + (dup + 1).astype(str)) + "@globaltech.example"

    def _plant_defects(self, emp: pd.DataFrame) -> pd.DataFrame:
        """Deliberate data-quality issues, carried mostly by the acquisition.

        Real HR data gets dirty exactly this way: a company is bought, its
        records are loaded under a second numbering scheme, and nobody
        reconciles the overlap. Question 50 in the demo pack is finding them.
        """
        cfg = self.s.data_quality
        if not cfg:
            return emp
        rng = self.rng
        emp = emp.copy()

        # Cost centres for acquired staff keep the acquired company's format.
        acq = emp.index[emp["is_acquired"] == 1]
        if len(acq):
            k = int(len(acq) * float(cfg["inconsistent_cost_center_share"]))
            hit = rng.choice(acq, size=k, replace=False)
            emp.loc[hit, "cost_center"] = ("DS-" + emp.loc[hit, "cost_center"]
                                           .str.replace("CC-", "", regex=False))

        # A handful of records never got a manager assigned.
        active = emp.index[emp["is_active"] == 1]
        k = min(int(cfg["missing_manager_count"]), len(active))
        if k:
            emp.loc[rng.choice(active, size=k, replace=False), "manager_employee_id"] = 0

        # The same human, loaded twice under two employee numbers.
        k = int(cfg["duplicate_person_records"])
        if k and len(acq):
            src = rng.choice(acq, size=min(k, len(acq)), replace=False)
            dupes = emp.loc[src].copy()
            dupes["employee_id"] = dupes["employee_id"] + 900_000
            dupes["employee_number"] = ("EMP" + dupes["employee_id"].astype(str).str.zfill(6))
            dupes["work_email"] = (dupes["first_name"].str.lower() + "."
                                   + dupes["last_name"].str.lower()
                                   + ".ds@globaltech.example")
            dupes["employment_status"] = "Terminated"
            dupes["is_duplicate_record"] = 1
            dupes["is_active"] = 0
            dupes["base_salary_usd"] = 0.0
            dupes["base_salary_local"] = 0.0
            emp = pd.concat([emp, dupes], ignore_index=True)

        # Inconsistent name casing, as though loaded from two source systems.
        k = int(len(emp) * float(cfg["name_case_noise_share"]))
        if k:
            hit = rng.choice(emp.index, size=k, replace=False)
            emp.loc[hit, "last_name"] = emp.loc[hit, "last_name"].str.upper()
        return emp
