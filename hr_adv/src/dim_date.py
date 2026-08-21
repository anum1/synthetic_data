"""Calendar dimension: Gregorian + fiscal + the flags payroll and absence need.

Deliberately leaner than the sibling datasets' version - there is no retail
4-5-4 calendar here, because no HR question has ever been asked about one. What
this one adds instead is per-country working-day and holiday marking, which is
what absence duration and payroll hours are actually computed from.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]

COUNTRIES = ["US", "Canada", "UK", "Germany", "India", "Japan"]


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th `weekday` (Mon=0) of a month; n=-1 gives the last one."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    last = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            if month < 12 else dt.date(year, 12, 31))
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> dt.date:
    """Anonymous Gregorian algorithm - Germany and the UK both need Good Friday."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g, h = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3, (19 * a + b - d - ((b - (b + 8) // 25 + 1) // 3) + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = ((h + m - 7 * n + 114) % 31) + 1
    return dt.date(year, month, day)


def _holidays(year: int) -> dict[str, dict[dt.date, str]]:
    """Public holidays by country. Not exhaustive - enough to be plausible and
    to make the working-day counts differ between countries, which is the point."""
    easter = _easter(year)
    good_friday = easter - dt.timedelta(days=2)
    easter_monday = easter + dt.timedelta(days=1)
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    return {
        "US": {
            dt.date(year, 1, 1): "New Year's Day",
            _nth_weekday(year, 1, 0, 3): "Martin Luther King Jr. Day",
            _nth_weekday(year, 2, 0, 3): "Presidents' Day",
            _nth_weekday(year, 5, 0, -1): "Memorial Day",
            dt.date(year, 6, 19): "Juneteenth",
            dt.date(year, 7, 4): "Independence Day",
            _nth_weekday(year, 9, 0, 1): "Labor Day",
            _nth_weekday(year, 11, 1, 2): "Veterans Day",
            thanksgiving: "Thanksgiving",
            thanksgiving + dt.timedelta(days=1): "Day after Thanksgiving",
            dt.date(year, 12, 25): "Christmas Day",
        },
        "Canada": {
            dt.date(year, 1, 1): "New Year's Day",
            good_friday: "Good Friday",
            _nth_weekday(year, 5, 0, -1) - dt.timedelta(days=7): "Victoria Day",
            dt.date(year, 7, 1): "Canada Day",
            _nth_weekday(year, 9, 0, 1): "Labour Day",
            _nth_weekday(year, 10, 0, 2): "Thanksgiving",
            dt.date(year, 11, 11): "Remembrance Day",
            dt.date(year, 12, 25): "Christmas Day",
            dt.date(year, 12, 26): "Boxing Day",
        },
        "UK": {
            dt.date(year, 1, 1): "New Year's Day",
            good_friday: "Good Friday",
            easter_monday: "Easter Monday",
            _nth_weekday(year, 5, 0, 1): "Early May Bank Holiday",
            _nth_weekday(year, 5, 0, -1): "Spring Bank Holiday",
            _nth_weekday(year, 8, 0, -1): "Summer Bank Holiday",
            dt.date(year, 12, 25): "Christmas Day",
            dt.date(year, 12, 26): "Boxing Day",
        },
        "Germany": {
            dt.date(year, 1, 1): "Neujahr",
            good_friday: "Karfreitag",
            easter_monday: "Ostermontag",
            dt.date(year, 5, 1): "Tag der Arbeit",
            easter + dt.timedelta(days=39): "Christi Himmelfahrt",
            easter + dt.timedelta(days=50): "Pfingstmontag",
            dt.date(year, 10, 3): "Tag der Deutschen Einheit",
            dt.date(year, 12, 25): "Weihnachten",
            dt.date(year, 12, 26): "Zweiter Weihnachtsfeiertag",
        },
        "India": {
            dt.date(year, 1, 26): "Republic Day",
            dt.date(year, 8, 15): "Independence Day",
            dt.date(year, 10, 2): "Gandhi Jayanti",
            dt.date(year, 12, 25): "Christmas Day",
        },
        "Japan": {
            dt.date(year, 1, 1): "New Year's Day",
            _nth_weekday(year, 1, 0, 2): "Coming of Age Day",
            dt.date(year, 2, 11): "National Foundation Day",
            dt.date(year, 4, 29): "Showa Day",
            dt.date(year, 5, 3): "Constitution Memorial Day",
            dt.date(year, 5, 4): "Greenery Day",
            dt.date(year, 5, 5): "Children's Day",
            _nth_weekday(year, 7, 0, 3): "Marine Day",
            dt.date(year, 8, 11): "Mountain Day",
            _nth_weekday(year, 9, 0, 3): "Respect for the Aged Day",
            _nth_weekday(year, 10, 0, 2): "Sports Day",
            dt.date(year, 11, 3): "Culture Day",
            dt.date(year, 11, 23): "Labour Thanksgiving Day",
        },
    }


def build_dim_date(start: dt.date, end: dt.date, fiscal_start_month: int) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({"calendar_date": dates})
    d = df["calendar_date"].dt

    df["date_key"] = (d.year * 10_000 + d.month * 100 + d.day).astype("int32")
    df["day_of_week"] = (d.dayofweek + 1).astype("int8")     # Monday = 1
    df["day_name"] = d.day_name()
    df["day_of_month"] = d.day.astype("int8")
    df["day_of_year"] = d.dayofyear.astype("int16")
    df["week_of_year"] = d.isocalendar().week.to_numpy().astype("int8")
    df["month_number"] = d.month.astype("int8")
    df["month_name"] = d.month_name()
    df["month_abbr"] = df["month_name"].str[:3]
    df["quarter_number"] = d.quarter.astype("int8")
    df["quarter_name"] = "Q" + df["quarter_number"].astype(str)
    df["calendar_year"] = d.year.astype("int16")
    df["year_month_key"] = (d.year * 100 + d.month).astype("int32")
    df["year_month_name"] = df["month_abbr"] + " " + df["calendar_year"].astype(str)
    df["year_quarter_name"] = df["calendar_year"].astype(str) + "-" + df["quarter_name"]
    df["month_start_date"] = d.to_period("M").dt.start_time.dt.date
    df["month_end_date"] = d.to_period("M").dt.end_time.dt.date
    df["is_month_end"] = (d.days_in_month == d.day).astype("int8")
    df["is_weekend"] = (d.dayofweek >= 5).astype("int8")

    # Fiscal calendar
    shifted = df["month_number"].to_numpy().astype(int) - fiscal_start_month
    fiscal_month = (shifted % 12) + 1
    fiscal_year = df["calendar_year"].to_numpy().astype(int) + (shifted < 0).astype(int)
    df["fiscal_year"] = fiscal_year.astype("int16")
    df["fiscal_month_number"] = fiscal_month.astype("int8")
    df["fiscal_quarter_number"] = (((fiscal_month - 1) // 3) + 1).astype("int8")
    df["fiscal_quarter_name"] = ("FY" + df["fiscal_year"].astype(str)
                                 + "-Q" + df["fiscal_quarter_number"].astype(str))
    df["fiscal_period_key"] = (df["fiscal_year"].astype("int32") * 100
                               + df["fiscal_quarter_number"]).astype("int32")

    # Per-country holiday and working-day flags. Absence duration and payroll
    # hours are computed from these, so a UK vacation day really does cost fewer
    # working days than an Indian one.
    years = range(start.year, end.year + 1)
    cal = {c: {} for c in COUNTRIES}
    for y in years:
        for country, days in _holidays(y).items():
            cal[country].update(days)
    dates_only = np.array([x.date() for x in dates])
    holiday_any = np.zeros(len(df), dtype=bool)
    for country in COUNTRIES:
        flag = np.array([x in cal[country] for x in dates_only])
        df[f"is_holiday_{country.lower()}"] = flag.astype("int8")
        df[f"is_working_day_{country.lower()}"] = (
            (~flag) & (df["is_weekend"].to_numpy() == 0)).astype("int8")
        holiday_any |= flag
    df["is_holiday_any"] = holiday_any.astype("int8")
    df["holiday_name_us"] = [cal["US"].get(x, "Not a Holiday") for x in dates_only]

    # Relative-time flags let a dashboard filter "last 12 months" without the
    # author having to hard-code a date that goes stale.
    as_of = pd.Timestamp(end)
    df["days_from_as_of"] = (df["calendar_date"] - as_of).dt.days.astype("int32")
    df["months_from_as_of"] = ((df["calendar_year"] * 12 + df["month_number"])
                               - (as_of.year * 12 + as_of.month)).astype("int16")
    df["is_current_year"] = (df["calendar_year"] == as_of.year).astype("int8")
    df["is_prior_year"] = (df["calendar_year"] == as_of.year - 1).astype("int8")
    df["is_last_12_months"] = ((df["months_from_as_of"] > -12)
                               & (df["months_from_as_of"] <= 0)).astype("int8")
    df["is_ytd"] = ((df["is_current_year"] == 1)
                    & (df["calendar_date"] <= as_of)).astype("int8")

    df["calendar_date"] = d.date
    return df
