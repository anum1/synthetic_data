"""Scenario configuration loading and calendar anchoring."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Timeline:
    """Resolved demo timeline.

    as_of_date  - last date with actual sales; "today" in the demo
    start_date  - first date in the dataset
    end_date    - last date in dim_date (covers the forecast horizon)
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
    def sizes(self) -> dict:
        return self.cfg["tiers"][self.tier]

    @property
    def baseline(self) -> dict:
        return self.cfg["baseline"]

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

        Returns None when the event is disabled or the key is absent/null,
        which callers read as "no bound" (open-ended event).
        """
        block = self.event(name)
        if block is None or block.get(key) is None:
            return None
        return self.timeline.offset_month(int(block[key]))

    def event_window(self, name: str, start_key: str = "start_offset",
                     end_key: str = "end_offset") -> tuple[dt.date, dt.date] | None:
        """(start_month, end_month) for an event; end defaults to the horizon."""
        start = self.event_month(name, start_key)
        if start is None:
            return None
        end = self.event_month(name, end_key) or self.timeline.end_date.replace(day=1)
        return start, end


def _resolve_timeline(cal: dict) -> Timeline:
    anchor = cal.get("anchor", "today")
    if anchor == "fixed":
        raw = cal.get("as_of_date")
        if raw is None:
            raise ValueError("calendar.anchor is 'fixed' but as_of_date is null")
        as_of = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
    else:
        today = dt.date.today()
        # Land on the last day of the previous complete month so partial-month
        # noise never shows up as a fake decline in the trend charts.
        first_of_month = today.replace(day=1)
        as_of = first_of_month - dt.timedelta(days=1)

    history_years = int(cal.get("history_years", 2))
    start = dt.date(as_of.year - history_years, 1, 1)

    horizon = int(cal.get("forecast_months", 16))
    end_month_total = as_of.year * 12 + (as_of.month - 1) + horizon
    end_year, end_month = divmod(end_month_total, 12)
    end = _month_end(end_year, end_month + 1)

    return Timeline(as_of_date=as_of, start_date=start, end_date=end)


def _month_end(year: int, month: int) -> dt.date:
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def load_scenario(path: str | Path, tier: str) -> Scenario:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    if tier not in cfg["tiers"]:
        raise ValueError(f"unknown tier {tier!r}; expected one of {list(cfg['tiers'])}")
    return Scenario(cfg, tier)
