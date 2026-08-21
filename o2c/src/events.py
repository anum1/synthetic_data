"""The fifteen planted events, resolved once into concrete targets.

Two rules govern everything in this file.

**Scope is a fraction, resolved to entities once.** Event scope is configured as
a share of the population, so a story stays proportionally visible at both
tiers. Resolving the targets here, once, means every downstream module agrees on
which rep, which warehouse and which customers are affected - rather than each
one drawing its own sample and the story landing on five different populations.

**Ramps, not step changes.** Most events phase in linearly across their window.
A step change is trivially findable by eye and makes the AI look clairvoyant
rather than useful; a ramp has to be measured. `ramp()` returns 0 before the
window, 0..1 across it, and 1 after.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from o2cconfig import Scenario, month_end


class EventPlan:
    """Resolved targets for every enabled event.

    Built once in generate.py and passed to each stage, so "the affected
    customer" means the same customer in orders.py, billing.py and
    collections.py.
    """

    def __init__(self, s: Scenario, cust: pd.DataFrame, prod: pd.DataFrame,
                 reps: pd.DataFrame, wh: pd.DataFrame, rng: np.random.Generator):
        self.s = s
        self.tl = s.timeline

        # Customers ranked by expected spend. Events 6 and 10 are configured by
        # rank ("the third largest customer"), which keeps the config readable
        # and keeps the story pointed at an account big enough to matter.
        ranked = cust.sort_values("_spend_weight", ascending=False)
        self.ranked_customers = ranked["customer_id"].to_numpy()

        # Event 2: a handful of reps discounting hard.
        ev = s.event("discount_explosion")
        self.discount_reps = np.array([], dtype=np.int64)
        if ev:
            k = max(1, int(round(float(ev["rep_share"]) * len(reps))))
            self.discount_reps = reps.sample(
                n=k, random_state=int(s.seed) + 11)["sales_rep_id"].to_numpy()

        # Event 3: one warehouse, by code, so the story survives a reseed.
        ev = s.event("warehouse_bottleneck")
        self.bottleneck_warehouse_id = 0
        if ev:
            hit = wh[wh["warehouse_code"] == ev["warehouse_code"]]
            self.bottleneck_warehouse_id = int(hit["warehouse_id"].iloc[0]) if len(hit) \
                else int(wh["warehouse_id"].iloc[0])

        # Event 6: payment slowdown at one named-by-rank account.
        #
        # The config declares "this customer used to pay in 35 days and now
        # takes 67". For that to be true the BEFORE has to be true as well, so
        # the account's own behaviour is pinned to the configured starting
        # point. Left to the draw, a large account on Net 60 terms averages 90
        # days already, and the "slowdown" reads as a speed-up.
        ev = s.event("customer_payment_slowdown")
        self.slow_payer_id = (int(self.ranked_customers[int(ev["customer_rank"]) - 1])
                              if ev else 0)

        # Event 7: leakage concentrated in a couple of large accounts, so the
        # drill-down converges on a name rather than dissolving into a long tail.
        ev = s.event("pricing_leakage")
        self.leakage_customers = np.array([], dtype=np.int64)
        if ev:
            k = int(ev["concentrated_customers"])
            self.leakage_customers = self.ranked_customers[:k]

        # Event 9: customers whose limits are frozen while their volume grows.
        ev = s.event("credit_hold")
        self.credit_hold_customers = np.array([], dtype=np.int64)
        if ev:
            k = s.scaled(ev["customer_share"], "customers")
            # Drawn from the middle of the book: freezing a Strategic account's
            # limit would be noticed and overridden inside a day.
            pool = cust[cust["customer_segment"].isin(["Enterprise", "Mid-Market"])]
            self.credit_hold_customers = pool.sample(
                n=min(k, len(pool)), random_state=int(s.seed) + 13)["customer_id"].to_numpy()

        # Event 10: the dispute spike lands on the largest account, which is also
        # a leakage target. That overlap is deliberate - it is the causal chain
        # the root-cause scene walks.
        # Targeted at the largest GLOBAL ACCOUNT, not a single legal entity. One
        # customer is at most a few percent of revenue, so no single-entity
        # dispute spike can reach a headline number; an account with a dozen
        # ship-to entities under it can, and "this global account" is a better
        # drill-down target anyway.
        ev = s.event("dispute_spike")
        self.dispute_customer_id = 0
        self.dispute_customers = np.array([], dtype=np.int64)
        if ev:
            top = int(self.ranked_customers[int(ev["customer_rank"]) - 1])
            acct = cust.loc[cust["customer_id"] == top, "global_account_id"]
            acct_id = int(acct.iloc[0]) if len(acct) else 0
            if acct_id:
                self.dispute_customers = cust.loc[
                    cust["global_account_id"] == acct_id, "customer_id"].to_numpy()
            else:
                self.dispute_customers = np.array([top])
            self.dispute_customer_id = top
            self.dispute_account_id = acct_id

        # Event 11: a few high-margin SKUs run dry.
        ev = s.event("product_shortage")
        self.shortage_products = np.array([], dtype=np.int64)
        if ev:
            k = s.scaled(ev["sku_share"], "products")
            pool = prod[prod["abc_class"] == "A"].sort_values(
                "standard_margin_pct", ascending=False).head(max(k * 4, k))
            self.shortage_products = pool.sample(
                n=min(k, len(pool)), random_state=int(s.seed) + 17)["product_id"].to_numpy()

    # -- window helpers --------------------------------------------------------
    def in_window(self, name: str, dates) -> np.ndarray:
        """Boolean mask: is each date inside this event's window?"""
        win = self.s.event_window(name)
        d = _as_dates(dates)
        if win is None:
            return np.zeros(len(d), dtype=bool)
        start, end = win
        return (d >= np.datetime64(start)) & (d <= np.datetime64(month_end(end)))

    def ramp(self, name: str, dates) -> np.ndarray:
        """0 before the window, linear 0..1 across it, 1 after.

        Phasing an event in is what makes it a trend the audience has to measure
        rather than a cliff they can see from the back of the room.
        """
        win = self.s.event_window(name)
        d = _as_dates(dates)
        if win is None:
            return np.zeros(len(d), dtype=float)
        start = np.datetime64(win[0])
        end = np.datetime64(month_end(win[1]))
        span = max((end - start) / np.timedelta64(1, "D"), 1.0)
        frac = (d - start) / np.timedelta64(1, "D") / span
        return np.clip(frac, 0.0, 1.0)

    def blend(self, name: str, dates, value_from: float, value_to: float) -> np.ndarray:
        """Ramp a parameter from `value_from` to `value_to` across the window."""
        return value_from + (value_to - value_from) * self.ramp(name, dates)


def _as_dates(dates) -> np.ndarray:
    if isinstance(dates, (pd.Series, pd.Index)):
        return pd.to_datetime(dates).to_numpy(dtype="datetime64[D]")
    if isinstance(dates, np.ndarray) and dates.dtype.kind == "M":
        return dates.astype("datetime64[D]")
    if isinstance(dates, dt.date):
        return np.array([np.datetime64(dates)], dtype="datetime64[D]")
    return pd.to_datetime(pd.Series(list(dates))).to_numpy(dtype="datetime64[D]")
