"""Scenario configuration, calendar anchoring and the derived funnel plan.

Timeline semantics are shared with the sibling ApexTech (sales), Meridian
(supply chain), GlobalTech (HR), Vantage (O2C) and Norvant (P2P) datasets, so
all six anchor to the same as-of convention: the last day of the previous
complete month. Event timing is expressed in months relative to that date,
never as absolute dates, so regenerating next year still tells this year's
story.

`FunnelPlan` is the piece specific to this dataset, and it is PLAN 1 in code:
the blended headline is COMPUTED from the channel mix, never configured next to
it. Nothing downstream may assert a rate the mix does not produce.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Timeline:
    """Resolved demo timeline.

    as_of_date  - last date with actual activity; "today" in the demo
    start_date  - first date in the dataset
    end_date    - last date in dim_date
    """

    as_of_date: dt.date
    start_date: dt.date
    end_date: dt.date

    @property
    def current_year(self) -> int:
        return self.as_of_date.year

    def offset_month(self, offset: int) -> dt.date:
        """First day of the month `offset` months from the as-of month."""
        total = self.as_of_date.year * 12 + (self.as_of_date.month - 1) + offset
        year, month = divmod(total, 12)
        return dt.date(year, month + 1, 1)

    @property
    def as_of_month(self) -> dt.date:
        return self.as_of_date.replace(day=1)

    def month_starts(self) -> list[dt.date]:
        """Every month start from history start through the as-of month."""
        out, cur = [], self.start_date.replace(day=1)
        while cur <= self.as_of_month:
            out.append(cur)
            cur = add_month(cur, 1)
        return out

    @property
    def ttm_start(self) -> dt.date:
        """First day of the trailing-twelve-month window ending at as-of.

        Every headline in this dataset is measured on this window. Say so on
        the tile; a TTM number sitting next to a YTD number is how demos die.
        """
        return self.offset_month(-11)

    @property
    def prior_ttm_start(self) -> dt.date:
        return self.offset_month(-23)


def add_month(d: dt.date, n: int) -> dt.date:
    total = d.year * 12 + (d.month - 1) + n
    year, month = divmod(total, 12)
    return dt.date(year, month + 1, 1)


def month_end(d: dt.date) -> dt.date:
    return add_month(d.replace(day=1), 1) - dt.timedelta(days=1)


def lognormal_from_median(rng, median: float, sigma: float, size):
    """Lognormal parameterised by MEDIAN, not mean.

    Deal sizes and cycle times are quoted by median in every real sales
    organisation, and a lognormal's mean sits well above its median - so
    configuring `mean` and drawing `exp(normal(log(mean)))` silently inflates
    every total by exp(sigma^2/2). Doing it here, once, keeps the config
    honest.
    """
    return np.exp(rng.normal(np.log(median), sigma, size))


class Scenario:
    def __init__(self, cfg: dict, tier: str):
        self.cfg = cfg
        self.tier = tier
        self.timeline = _resolve_timeline(cfg["calendar"])
        self.funnel = FunnelPlan(cfg)

    # -- convenience accessors -------------------------------------------------
    @property
    def seed(self) -> int:
        return int(self.cfg["meta"]["seed"])

    @property
    def company(self) -> str:
        return str(self.cfg["meta"]["company"])

    @property
    def sizes(self) -> dict:
        return self.cfg["tiers"][self.tier]

    @property
    def universe(self) -> dict:
        return self.cfg["universe"]

    @property
    def calendar(self) -> dict:
        return self.cfg["calendar"]

    @property
    def spend(self) -> dict:
        return self.cfg["spend"]

    @property
    def deal(self) -> dict:
        return self.cfg["deal"]

    @property
    def channels(self) -> dict:
        return self.cfg["channels"]

    @property
    def regions(self) -> dict:
        return self.cfg["regions"]

    @property
    def segments(self) -> dict:
        return self.cfg["segments"]

    @property
    def lifecycle(self) -> dict:
        return self.cfg["lifecycle"]

    @property
    def products(self) -> list:
        return self.cfg["products"]

    @property
    def industries(self) -> dict:
        return self.cfg["industries"]

    @property
    def attribution(self) -> dict:
        return self.cfg["attribution"]

    @property
    def response_curve(self) -> dict:
        return self.cfg["response_curve"]

    @property
    def output(self) -> dict:
        return self.cfg["output"]

    def event(self, name: str) -> dict | None:
        ev = self.cfg.get("events", {}).get(name)
        if ev and ev.get("enabled", True):
            return ev
        return None

    # -- quality index ---------------------------------------------------------
    def quality_index(self, months: np.ndarray) -> np.ndarray:
        """Lead-quality multiplier by `months_from_as_of` (<= 0).

        Declines across history so volume rises while quality falls - the §19
        story - and is normalised so the TTM mean is exactly 1.0. That
        normalisation is what keeps the blended TTM headline equal to the
        channel mix table, which is the invariant PLAN 1 is built on. Without
        it, tuning the decay silently moves every headline in the dataset.
        """
        q = self.cfg["quality_index"]
        span = len(self.timeline.month_starts()) - 1
        frac = np.clip((months + span) / max(span, 1), 0.0, 1.0)
        raw = q["start"] + (q["as_of"] - q["start"]) * frac ** float(q["curve"])
        ttm = np.arange(-11, 1)
        ttm_frac = np.clip((ttm + span) / max(span, 1), 0.0, 1.0)
        ttm_raw = q["start"] + (q["as_of"] - q["start"]) * ttm_frac ** float(q["curve"])
        return raw / ttm_raw.mean()


class FunnelPlan:
    """The blended headline, derived from the channel mix. (PLAN 1, PLAN 2.1)

    Nothing here is configured. Every number is the weighted result of
    `channels:` in the scenario file, which is why `validate.py` can assert the
    blend without the assertion being circular: the config supplies parts, this
    supplies the whole, and the generated data has to agree with both.
    """

    def __init__(self, cfg: dict):
        ch = cfg["channels"]
        spend = float(cfg["spend"]["ttm_total_usd"])
        names = list(ch)
        self.channel_spend = {c: spend * ch[c]["spend_share"] for c in names}
        self.channel_leads = {c: self.channel_spend[c] / ch[c]["cpl_usd"] for c in names}
        self.channel_mqls = {c: self.channel_leads[c] * ch[c]["lead_to_mql"] for c in names}
        self.channel_sqls = {c: self.channel_mqls[c] * ch[c]["mql_to_sql"] for c in names}
        self.channel_opps = {c: self.channel_sqls[c] * ch[c]["sql_to_opp"] for c in names}
        self.channel_won = {c: self.channel_opps[c] * ch[c]["opp_to_won"] for c in names}

        self.spend = spend
        self.leads = sum(self.channel_leads.values())
        self.mqls = sum(self.channel_mqls.values())
        self.sqls = sum(self.channel_sqls.values())
        self.opps = sum(self.channel_opps.values())
        self.won = sum(self.channel_won.values())

        # The won-deal segment mix is DERIVED, not configured (PLAN 1). A
        # segment's quality multiplier applies at lead->MQL, MQL->SQL and (as a
        # square root) at the two sales steps, so its share of won deals moves
        # as roughly the cube of it. Configuring both lead_share and won_share
        # lets them disagree, and the one that loses is always the one the
        # headline was built on.
        mix = cfg["deal"]["segment_mix"]
        seg = cfg["segments"]
        w = {k: seg[k]["lead_share"] * seg[k]["quality_mult"] ** 3 for k in mix}
        tot = sum(w.values())
        self.segment_won_share = {k: v / tot for k, v in w.items()}
        self.avg_won_usd = sum(self.segment_won_share[k] * mix[k]["mean_usd"]
                               for k in mix)
        self.revenue = self.won * self.avg_won_usd
        # Opportunity value is larger than won value because losses skew small:
        # a deal that dies usually dies early and small.
        self.avg_opp_usd = self.avg_won_usd * 1.02
        self.pipeline = self.opps * self.avg_opp_usd

        self.cpl = spend / self.leads
        self.cost_per_mql = spend / self.mqls
        self.cost_per_sql = spend / self.sqls
        self.cac = spend / self.won
        self.roas = self.revenue / spend
        self.lead_to_mql = self.mqls / self.leads
        self.mql_to_sql = self.sqls / self.mqls
        self.sql_to_opp = self.opps / self.sqls
        self.opp_to_won = self.won / self.opps

        gm = sum(p["margin"] * p["share"] for p in cfg["products"])
        self.gross_margin = gm
        self.marketing_roi = (self.revenue * gm - spend) / spend

    def render(self) -> str:
        return (
            f"    derived headline: spend ${self.spend / 1e6:,.1f}M  "
            f"leads {self.leads:,.0f}  MQL {self.mqls:,.0f}  SQL {self.sqls:,.0f}\n"
            f"                      opps {self.opps:,.0f}  won {self.won:,.0f}  "
            f"pipeline ${self.pipeline / 1e6:,.1f}M  revenue ${self.revenue / 1e6:,.1f}M\n"
            f"                      CPL ${self.cpl:,.0f}  cost/MQL ${self.cost_per_mql:,.0f}  "
            f"CAC ${self.cac:,.0f}  ROAS {self.roas:.2f}x  ROI {self.marketing_roi:.2f}x")


def _resolve_timeline(cal: dict) -> Timeline:
    if cal.get("anchor", "today") == "fixed" and cal.get("as_of_date"):
        as_of = cal["as_of_date"]
        as_of = as_of if isinstance(as_of, dt.date) else dt.date.fromisoformat(str(as_of))
    else:
        today = dt.date.today()
        as_of = today.replace(day=1) - dt.timedelta(days=1)
    start = add_month(as_of.replace(day=1), -12 * int(cal["history_years"]) + 1)
    return Timeline(as_of_date=as_of, start_date=start, end_date=month_end(as_of))


def load_scenario(path: str | Path, tier: str) -> Scenario:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    if tier not in cfg["tiers"]:
        raise SystemExit(f"unknown tier {tier!r}; have {list(cfg['tiers'])}")
    return Scenario(cfg, tier)
