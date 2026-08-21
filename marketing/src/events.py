"""The sixteen planted events, resolved once into concrete targets.

Two rules govern this file, inherited from the Norvant P2P sibling because they
were the right rules there and nothing about marketing changes them.

**Scope is a fraction, resolved to entities once.** Resolving targets here,
once, means every downstream module agrees on which campaign, which region and
which accounts the stories land on - rather than each stage drawing its own
sample and the story landing on five different populations.

**Ramps, not step changes.** Events phase in linearly across their window. A
step change is findable by eye and makes the AI look clairvoyant rather than
useful; a ramp has to be measured. `ramp()` returns 0 before the window, 0..1
across it, and 1 after.

A third rule is specific to this dataset and is the reason Scenario 3 works at
all: **the attribution divergence is never drawn.** It emerges from touch
ORDERING - LinkedIn and paid social open journeys, webinars and events close
them - so first-touch and last-touch disagree because the journeys really are
shaped that way. Draw it as a number and the first drill into a customer
journey contradicts the chart above it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mktconfig import Scenario


def ramp(months: np.ndarray, start: int, duration: int) -> np.ndarray:
    """0 before `start`, 0..1 linearly across `duration`, 1 after.

    `months` is months-from-as-of, so it is <= 0 and increases toward now.
    """
    if duration <= 0:
        return (months >= start).astype(float)
    return np.clip((months - start) / duration, 0.0, 1.0)


class EventPlan:
    """Resolved targets for every enabled event."""

    def __init__(self, s: Scenario, accounts: pd.DataFrame,
                 reps: pd.DataFrame, rng: np.random.Generator):
        self.s = s
        self.tl = s.timeline
        self.rng = rng

        # -- E3 attribution divergence ----------------------------------------
        self.openers: list[str] = []
        self.closers: list[str] = []
        self.opener_bias = 1.0
        self.closer_bias = 1.0
        ev = s.event("attribution_divergence")
        if ev:
            self.openers = list(ev["opener_channels"])
            self.closers = list(ev["closer_channels"])
            self.opener_bias = float(ev["opener_first_bias"])
            self.closer_bias = float(ev["closer_last_bias"])

        # -- E6 / E16 the APAC pair -------------------------------------------
        ev = s.event("apac_underwater")
        self.apac_region = ev["region"] if ev else None
        self.apac_spend_growth = float(ev["spend_growth"]) if ev else 0.0

        ev = s.event("sales_execution_gap")
        self.exec_gap_region = ev["region"] if ev else None
        self.exec_gap_start = int(ev["start_month_offset"]) if ev else 0
        self.exec_gap_mult = float(ev["opp_to_won_mult"]) if ev else 1.0
        # The reps who carry it. Naming them once means the story survives a
        # reseed and stays on the same team through every downstream module.
        self.exec_gap_reps = np.array([], dtype=np.int64)
        if self.exec_gap_region:
            self.exec_gap_reps = reps.loc[
                reps["region_name"] == self.exec_gap_region,
                "sales_rep_id"].to_numpy()

        # -- E7 product launch -------------------------------------------------
        ev = s.event("product_launch")
        self.launch_line = ev["product_line"] if ev else None
        self.launch_month = int(ev["launch_month_offset"]) if ev else 0
        self.launch_pre = int(ev["pre_launch_months"]) if ev else 0
        self.launch_awareness = float(ev["awareness_mult"]) if ev else 1.0
        self.launch_pipeline = float(ev["pipeline_mult"]) if ev else 1.0

        # -- E12 hero journeys -------------------------------------------------
        # Chosen from Enterprise accounts in the region the demo drills into, so
        # the journey page and the regional story are about the same company.
        # Two stages, because five named accounts chosen before any lead exists
        # will almost all fail to produce an opportunity - 50,000 accounts and
        # ~10,000 deals means a 1-in-5 chance each, and the first build shipped
        # one hero journey out of five.
        #
        # So: a CANDIDATE pool is resolved here and journeys.py gives every
        # candidate a long journey, then opportunities.py settles the final five
        # from the candidates that actually closed something. The pool is a few
        # hundred Enterprise target accounts, small enough not to move any
        # aggregate and large enough that five of them will always convert.
        self.hero_candidate_ids = np.array([], dtype=np.int64)
        self.hero_customer_ids = np.array([], dtype=np.int64)
        self.hero_deal_usd = np.array([], dtype=float)
        self.hero_close_offsets = np.array([], dtype=int)
        self.hero_count = 0
        self.hero_touches = (7, 11)
        ev = s.event("hero_journeys")
        if ev:
            pool = accounts[(accounts["is_target_account"] == 1)
                            & (accounts["account_tier"] == "Named / ABM")]
            if len(pool) < 50:
                pool = accounts
            n = min(len(pool), max(int(ev["count"]) * 40, 200))
            self.hero_candidate_ids = pool.sample(
                n=n, random_state=int(s.seed) + 313)["customer_id"].to_numpy()
            self.hero_count = int(ev["count"])
            self.hero_deal_usd = np.array(ev["deal_usd"], dtype=float)
            self.hero_close_offsets = np.array(ev["close_month_offset"], dtype=int)
            self.hero_touches = (int(ev["touches"]["min"]),
                                 int(ev["touches"]["max"]))

        # -- E1 / E2 / E14 the named campaigns --------------------------------
        # Resolved to names here; campaigns.py creates them and every later
        # stage looks them up by campaign_id.
        self.flagship = s.event("wasteful_flagship")
        self.gem = s.event("hidden_gem")
        self.cpl_anomaly = s.event("cpl_anomaly")
        self.named_campaign_ids: dict[str, int] = {}

        # -- E15 web conversion drop ------------------------------------------
        ev = s.event("web_conversion_drop")
        self.web_drop = ev
        self.web_drop_pages = list(ev["pages"]) if ev else []

        # -- E5 lead quality decay --------------------------------------------
        # A dedicated multiplier on MQL->SQL, confined to the trailing twelve
        # months. It was originally folded into quality_index, which could not
        # work: that index compounds down four funnel steps, so a swing steep
        # enough to show 34% -> 21% within a year also collapsed revenue by 15%
        # instead of flattening it to +3%.
        self.mql_decay_swing = 0.0
        ev = s.event("lead_quality_decay")
        if ev:
            q1 = float(ev["target_q1_mql_to_sql"])
            q4 = float(ev["target_q4_mql_to_sql"])
            self.mql_decay_swing = (q1 - q4) / (q1 + q4)

        # -- E10 junk volume ---------------------------------------------------
        ev = s.event("junk_volume")
        self.junk_channel = ev["channel"] if ev else None
        self.junk_revenue_growth = float(ev["revenue_growth"]) if ev else 0.0

    # -- multipliers consumed by the funnel stages ----------------------------

    def region_quality_mult(self, region: np.ndarray,
                            months: np.ndarray) -> np.ndarray:
        """E16: one region's conversion decays from a start month.

        Applied on top of the region's own `quality_mult`, and only to the
        opportunity->won step, so marketing's numbers stay healthy while sales
        stops closing. That separation is the whole cross-functional argument.
        """
        out = np.ones(len(region))
        if not self.exec_gap_region:
            return out
        r = ramp(months, self.exec_gap_start, 5)
        hit = region == self.exec_gap_region
        out[hit] = 1.0 - (1.0 - self.exec_gap_mult) * r[hit]
        return out

    def launch_awareness_mult(self, product_line: np.ndarray,
                              months: np.ndarray) -> np.ndarray:
        """E7: awareness lifts BEFORE the launch, pipeline lifts after.

        The lag between the two is the campaign-impact timeline the note's §7
        asks for, and it only exists if the two multipliers are offset.
        """
        out = np.ones(len(product_line))
        if not self.launch_line:
            return out
        hit = product_line == self.launch_line
        r = ramp(months, self.launch_month - self.launch_pre, self.launch_pre)
        out[hit] = 1.0 + (self.launch_awareness - 1.0) * r[hit]
        return out

    def launch_pipeline_mult(self, product_line: np.ndarray,
                             months: np.ndarray) -> np.ndarray:
        out = np.ones(len(product_line))
        if not self.launch_line:
            return out
        hit = product_line == self.launch_line
        r = ramp(months, self.launch_month, 4)
        out[hit] = 1.0 + (self.launch_pipeline - 1.0) * r[hit]
        return out

    def mql_to_sql_decay(self, months: np.ndarray) -> np.ndarray:
        """E5: MQL->SQL deteriorates across the trailing twelve months.

        Linear from 1+swing at the start of the TTM window to 1-swing at
        as-of, flat at 1.0 before it. The mean over the window is 1.0 by
        construction, so the TTM headline still equals the channel mix table
        while the quarter-on-quarter slope is unmistakable.
        """
        if self.mql_decay_swing <= 0:
            return np.ones(len(months))
        frac = np.clip((months + 11) / 11.0, 0.0, 1.0)
        return np.where(months < -11, 1.0,
                        1.0 + self.mql_decay_swing * (1.0 - 2.0 * frac))

    def first_touch_bias(self, channel: np.ndarray) -> np.ndarray:
        """E3: how strongly a channel prefers to OPEN a journey.

        The configured bias is the TOTAL first-vs-last spread for a channel, so
        it is split as a square root across the two ends. Applying the full
        value at both ends compounds it - a 3.2x opener bias against a 3.6x
        closer penalty is an 11x spread, which puts LinkedIn at 44% of first
        touches and 4% of last ones. That is not a finding, it is a cartoon,
        and it makes the attribution scene unbelievable rather than surprising.
        """
        w = np.ones(len(channel))
        for c in self.openers:
            w[channel == c] = np.sqrt(self.opener_bias)
        for c in self.closers:
            w[channel == c] = 1.0 / np.sqrt(self.closer_bias)
        return w

    def last_touch_bias(self, channel: np.ndarray) -> np.ndarray:
        """E3: how strongly a channel prefers to CLOSE one."""
        w = np.ones(len(channel))
        for c in self.closers:
            w[channel == c] = np.sqrt(self.closer_bias)
        for c in self.openers:
            w[channel == c] = 1.0 / np.sqrt(self.opener_bias)
        return w

    def summary(self) -> str:
        n = sum(1 for k, v in self.s.cfg.get("events", {}).items()
                if isinstance(v, dict) and v.get("enabled", True))
        return (f"{n} events enabled | hero candidates "
                f"{len(self.hero_candidate_ids)} | "
                f"exec-gap reps {len(self.exec_gap_reps)} in "
                f"{self.exec_gap_region}")
