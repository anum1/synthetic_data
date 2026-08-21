"""Calendar dimension: Gregorian + fiscal + the flags marketing actually needs.

Ported from the Norvant P2P sibling so all six datasets share one calendar
contract. What earns its keep here is `months_from_as_of` and the relative-time
flags: every cohort view in this dataset is "campaigns that started N months
ago, measured to date" (PLAN 2.5), and a dashboard that hard-codes a date to
express that goes stale the month after it is built.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th `weekday` (Mon=0) of a month; n=-1 gives the last one."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    last = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            if month < 12 else dt.date(year, 12, 31))
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _holidays(year: int) -> dict[dt.date, str]:
    """US public holidays. Not exhaustive - enough that the business-day count
    is plausible, which is all the ageing calculations need."""
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    return {
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
    df["is_quarter_end"] = ((df["is_month_end"] == 1)
                            & (df["month_number"].isin([3, 6, 9, 12]))).astype("int8")
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

    # Business days. `business_day_index` is a running count, so the number of
    # business days between any two dates is one subtraction rather than a
    # correlated subquery.
    cal: dict[dt.date, str] = {}
    for y in range(start.year, end.year + 1):
        cal.update(_holidays(y))
    dates_only = np.array([x.date() for x in dates])
    is_holiday = np.array([x in cal for x in dates_only])
    df["is_holiday"] = is_holiday.astype("int8")
    df["holiday_name"] = [cal.get(x, "Not a Holiday") for x in dates_only]
    business = (~is_holiday) & (df["is_weekend"].to_numpy() == 0)
    df["is_business_day"] = business.astype("int8")
    df["business_day_index"] = np.cumsum(business).astype("int32")

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
    df["is_prior_12_months"] = ((df["months_from_as_of"] > -24)
                                & (df["months_from_as_of"] <= -12)).astype("int8")
    df["is_ytd"] = ((df["is_current_year"] == 1)
                    & (df["calendar_date"] <= as_of)).astype("int8")

    df["calendar_date"] = d.date
    return df
