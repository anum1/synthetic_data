"""Scenario configuration loading and calendar anchoring.

Timeline semantics are shared with the sibling ApexTech (sales), Meridian
(supply chain), GlobalTech (HR) and Vantage (O2C) datasets, so all five anchor
to the same as-of convention: the last day of the previous complete month.
Event timing is expressed in months relative to that date, never as absolute
dates, so regenerating next year still tells this year's story.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Timeline:
    """Resolved demo timeline.

    as_of_date  - last date with actual transactions; "today" in the demo
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

        The booking cohort the whole waterfall is measured on.
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


class Scenario:
    def __init__(self, cfg: dict, tier: str):
        self.cfg = cfg
        self.tier = tier
        self.timeline = _resolve_timeline(cfg["calendar"])

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
    def calendar(self) -> dict:
        return self.cfg["calendar"]

    @property
    def demand(self) -> dict:
        return self.cfg["demand"]

    @property
    def entities(self) -> list:
        return self.cfg["entities"]

    @property
    def channels(self) -> dict:
        return self.cfg["channels"]

    @property
    def requisitioning(self) -> dict:
        return self.cfg["requisitioning"]

    @property
    def sourcing(self) -> dict:
        return self.cfg["sourcing"]

    @property
    def receiving(self) -> dict:
        return self.cfg["receiving"]

    @property
    def invoicing(self) -> dict:
        return self.cfg["invoicing"]

    @property
    def matching(self) -> dict:
        return self.cfg["matching"]

    @property
    def approval(self) -> dict:
        return self.cfg["approval"]

    @property
    def payment(self) -> dict:
        return self.cfg["payment"]

    @property
    def doa(self) -> dict:
        return self.cfg["doa"]

    @property
    def currency(self) -> dict:
        return self.cfg["currency"]

    @property
    def supplier_master(self) -> dict:
        return self.cfg["supplier_master"]

    @property
    def data_quality(self) -> dict:
        block = self.cfg.get("data_quality", {})
        return block if block.get("enabled", False) else {}

    @property
    def headline(self) -> dict:
        return self.cfg["headline"]

    @property
    def output(self) -> dict:
        return self.cfg["output"]

    def event(self, name: str) -> dict | None:
        """Return an event block only if it is enabled, else None."""
        block = self.cfg.get("events", {}).get(name)
        if not block or not block.get("enabled", False):
            return None
        return block

    def event_month(self, name: str, key: str) -> dt.date | None:
        """Resolve an event's offset key to a concrete month start.

        None means the event is disabled or the key is absent, which callers
        read as "no bound".
        """
        block = self.event(name)
        if block is None or block.get(key) is None:
            return None
        return self.timeline.offset_month(int(block[key]))

    def event_window(self, name: str, start_key: str = "start_offset",
                     end_key: str = "end_offset") -> tuple[dt.date, dt.date] | None:
        """(start_month, end_month) for an event; end defaults to the as-of month."""
        start = self.event_month(name, start_key)
        if start is None:
            return None
        end = self.event_month(name, end_key) or self.timeline.as_of_month
        return start, end

    def in_event(self, name: str, when: dt.date) -> bool:
        """Is `when` inside this event's window? False when the event is off."""
        win = self.event_window(name)
        if win is None:
            return False
        start, end = win
        return start <= when <= month_end(end)

    @property
    def tier_scale(self) -> float:
        """This tier's transaction volume relative to `full`.

        Assertions written in dollars are quoted at full tier, because that is
        the dataset the demo is given on. Checking those same absolute numbers
        against `small` fails every one of them for the wrong reason, so they
        are scaled here rather than duplicated per tier in the config.
        """
        full = float(self.cfg["tiers"]["full"]["requisitions_per_month_base"])
        return float(self.sizes["requisitions_per_month_base"]) / max(full, 1.0)

    def money(self, value: float) -> float:
        """Scale a full-tier dollar assertion to this tier."""
        return float(value) * self.tier_scale

    def money_range(self, pair) -> tuple[float, float]:
        return self.money(pair[0]), self.money(pair[1])

    def scaled(self, share: float, of: str = "suppliers") -> int:
        """Turn a population fraction into a count at this tier.

        Event scope is configured as a fraction rather than an absolute count so
        that every planted story stays proportionally visible at both tiers.
        """
        return max(1, int(round(float(share) * int(self.sizes[of]))))


def _resolve_timeline(cal: dict) -> Timeline:
    anchor = cal.get("anchor", "today")
    if anchor == "fixed":
        raw = cal.get("as_of_date")
        if raw is None:
            raise ValueError("calendar.anchor is 'fixed' but as_of_date is null")
        as_of = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
    else:
        today = dt.date.today()
        # Land on the last day of the previous complete month so a partial month
        # never shows up as a fake collapse in the spend trend.
        as_of = today.replace(day=1) - dt.timedelta(days=1)

    history_years = int(cal.get("history_years", 3))
    start = dt.date(as_of.year - history_years, 1, 1)

    horizon = int(cal.get("forecast_months", 0))
    end = month_end(add_month(as_of.replace(day=1), horizon))
    return Timeline(as_of_date=as_of, start_date=start, end_date=end)


def load_scenario(path: str | Path, tier: str) -> Scenario:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    if tier not in cfg["tiers"]:
        raise ValueError(f"unknown tier {tier!r}; expected one of {list(cfg['tiers'])}")
    return Scenario(cfg, tier)
