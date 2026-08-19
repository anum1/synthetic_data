"""Rich calendar dimension: Gregorian + fiscal + NRF 4-5-4 retail + holidays."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]

# Retail period patterns: weeks per period across the retail year.
# 4-5-4 is the NRF standard; 4-4-5 and 5-4-4 are the common variants; 13x4 is
# the thirteen-period calendar some manufacturers and utilities use.
RETAIL_PATTERNS = {
    "4-5-4": [4, 5, 4] * 4,
    "4-4-5": [4, 4, 5] * 4,
    "5-4-4": [5, 4, 4] * 4,
    "13x4": [4] * 13,
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th `weekday` (Mon=0) of a month; n=-1 gives the last one."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    last = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            if month < 12 else dt.date(year, 12, 31))
    offset = (last.weekday() - weekday) % 7
    return last - dt.timedelta(days=offset)


def _holidays(year: int) -> dict[dt.date, str]:
    thanksgiving = _nth_weekday(year, 11, 3, 4)          # 4th Thursday of Nov
    return {
        dt.date(year, 1, 1): "New Year's Day",
        _nth_weekday(year, 1, 0, 3): "Martin Luther King Jr. Day",
        _nth_weekday(year, 2, 0, 3): "Presidents' Day",
        _nth_weekday(year, 5, 0, -1): "Memorial Day",
        dt.date(year, 7, 4): "Independence Day",
        _nth_weekday(year, 9, 0, 1): "Labor Day",
        thanksgiving: "Thanksgiving",
        thanksgiving + dt.timedelta(days=1): "Black Friday",
        thanksgiving + dt.timedelta(days=4): "Cyber Monday",
        dt.date(year, 12, 24): "Christmas Eve",
        dt.date(year, 12, 25): "Christmas Day",
        dt.date(year, 12, 26): "Boxing Day",
        dt.date(year, 12, 31): "New Year's Eve",
    }


def _retail_year_start(year: int, start_month: int) -> dt.date:
    """First Sunday on or after the 1st of the retail start month (NRF style)."""
    anchor = dt.date(year, start_month, 1)
    return anchor + dt.timedelta(days=(6 - anchor.weekday()) % 7)


def _retail_calendar(dates: pd.Series, start_month: int,
                     pattern: str = "4-5-4") -> pd.DataFrame:
    """Map each date onto a retail year/quarter/period/week.

    `pattern` selects the period shape: 4-5-4 (NRF standard), 4-4-5, 5-4-4 or
    13x4. Every pattern is 52 weeks; the 53rd week of a long retail year is
    absorbed by the final period, which is what the NRF calendar does.
    """
    weeks_in_period = RETAIL_PATTERNS.get(pattern)
    if weeks_in_period is None:
        raise ValueError(f"unknown retail pattern {pattern!r}; "
                         f"expected one of {sorted(RETAIL_PATTERNS)}")
    n_periods = len(weeks_in_period)
    lo, hi = dates.min().year - 1, dates.max().year + 1
    starts = {y: _retail_year_start(y, start_month) for y in range(lo, hi + 2)}

    rows = []
    for d in dates.dt.date:
        ry = d.year if d >= starts[d.year] else d.year - 1
        week_index = (d - starts[ry]).days // 7          # 0-based
        # A 53-week retail year happens when the next year starts 371 days later.
        year_weeks = (starts[ry + 1] - starts[ry]).days // 7
        week_index = min(week_index, year_weeks - 1)

        remaining, period = week_index, 0
        for period, wks in enumerate(weeks_in_period, start=1):
            # The final period absorbs the 53rd week when there is one.
            span = wks + (1 if period == n_periods and year_weeks == 53 else 0)
            if remaining < span:
                break
            remaining -= span
        # A 13-period calendar has no quarters; report the period as its own.
        quarter = (period - 1) // 3 + 1 if n_periods == 12 else period
        rows.append((ry, week_index + 1, period, quarter))

    return pd.DataFrame(rows, columns=["retail_year", "retail_454_week",
                                       "retail_454_period", "retail_454_quarter"],
                        index=dates.index)


def build_dim_date(start: dt.date, end: dt.date, fiscal_start_month: int,
                   retail_start_month: int,
                   retail_pattern: str = "4-5-4") -> pd.DataFrame:
    rng = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({"calendar_date": rng})

    d = df["calendar_date"].dt
    df["date_key"] = (d.year * 10000 + d.month * 100 + d.day).astype("int32")
    df["day_of_month"] = d.day.astype("int16")
    df["day_of_week"] = (d.weekday + 1).astype("int16")        # 1=Monday
    df["day_of_year"] = d.dayofyear.astype("int16")
    df["day_name"] = d.weekday.map(dict(enumerate(DAY_NAMES)))
    df["is_weekend"] = (d.weekday >= 5).astype("int8")

    # ISO weeks belong to an ISO year that can differ from the calendar year:
    # 2024-12-30 is ISO week 1 of 2025. Without iso_year, grouping a weekly
    # trend by (year_number, week_of_year) silently splits that week in two.
    iso = d.isocalendar()
    df["week_of_year"] = iso.week.astype("int16").to_numpy()
    df["iso_year"] = iso.year.astype("int16").to_numpy()
    df["iso_year_week"] = (df["iso_year"].astype(str) + "-W"
                           + df["week_of_year"].astype(str).str.zfill(2))
    df["iso_year_week_key"] = (df["iso_year"].astype("int32") * 100
                               + df["week_of_year"]).astype("int32")
    df["week_start_date"] = (df["calendar_date"]
                             - pd.to_timedelta(d.weekday, unit="D")).dt.date
    df["week_end_date"] = (df["calendar_date"]
                           + pd.to_timedelta(6 - d.weekday, unit="D")).dt.date

    df["month_number"] = d.month.astype("int16")
    df["month_name"] = d.month.map(dict(enumerate(MONTH_NAMES, start=1)))
    df["month_short_name"] = df["month_name"].str[:3]
    df["quarter_number"] = d.quarter.astype("int16")
    df["quarter_name"] = "Q" + df["quarter_number"].astype(str)
    df["year_number"] = d.year.astype("int16")
    df["year_month"] = d.strftime("%Y-%m")
    df["year_month_key"] = (d.year * 100 + d.month).astype("int32")
    df["year_quarter"] = df["year_number"].astype(str) + "-Q" + df["quarter_number"].astype(str)
    df["month_start_date"] = d.to_period("M").dt.start_time.dt.date
    df["month_end_date"] = d.to_period("M").dt.end_time.dt.date

    # Fiscal year is labelled by the calendar year in which it ends.
    shifted = df["calendar_date"] - pd.DateOffset(months=fiscal_start_month - 1)
    fs = shifted.dt
    df["fiscal_year"] = (fs.year + 1).astype("int16")
    df["fiscal_quarter"] = fs.quarter.astype("int16")
    df["fiscal_quarter_name"] = "FQ" + df["fiscal_quarter"].astype(str)
    df["fiscal_month"] = fs.month.astype("int16")
    df["fiscal_week"] = fs.isocalendar().week.astype("int16").to_numpy()
    df["fiscal_year_month"] = df["fiscal_year"].astype(str) + "-FM" + \
        df["fiscal_month"].astype(str).str.zfill(2)

    df = pd.concat([df, _retail_calendar(df["calendar_date"], retail_start_month,
                                         retail_pattern)], axis=1)
    df["retail_pattern"] = retail_pattern
    df["retail_454_period_name"] = "P" + df["retail_454_period"].astype(str).str.zfill(2)

    df["is_month_end"] = d.is_month_end.astype("int8")
    df["is_month_start"] = d.is_month_start.astype("int8")
    df["is_quarter_end"] = d.is_quarter_end.astype("int8")
    df["is_year_end"] = d.is_year_end.astype("int8")

    hol: dict[dt.date, str] = {}
    for y in range(start.year, end.year + 1):
        hol.update(_holidays(y))
    names = df["calendar_date"].dt.date.map(hol)
    df["holiday_name"] = names.fillna("")
    df["is_holiday"] = names.notna().astype("int8")
    df["is_business_day"] = ((df["is_weekend"] == 0) & (df["is_holiday"] == 0)).astype("int8")

    df["calendar_date"] = df["calendar_date"].dt.date
    return df
