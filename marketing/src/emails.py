"""fact_email_send and fact_email_event.

Named `emails.py`, not `email.py`: `src/` goes on sys.path, so a module called
`email` shadows the standard library's `email` package for everything imported
afterwards. The generator survived it because nothing in its path touches
stdlib email - but duckdb does, so `run_questions.py` failed with a bare
"duckdb is required" that had nothing to do with duckdb.

The note modelled email as one row per activity carrying `sent`, `delivered`,
`opened`, `clicked`, `unsubscribed`, `bounced` as flags. That shape cannot
represent three clicks on one email, or an unsubscribe three weeks after the
open, and it forces open rate and click rate onto the same denominator when
CTOR - clicks over OPENS - is the metric email teams actually manage. (PLAN 2.9)

So: `fact_email_send` is one row per recipient per send, and
`fact_email_event` is one row per thing that happened. Rates are then
divisions, and every one of them has an unambiguous denominator.

Consent is a hard constraint, not a rate. An EMEA contact without consent is
never sent to, which is why EMEA reach is lower - E11, and a real answer to a
question a dashboard would otherwise leave hanging.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from events import EventPlan
from mktconfig import Scenario

EMAIL_TYPES = [
    ("Newsletter", 0.26, 0.22, 0.09), ("Product Announcement", 0.14, 0.31, 0.14),
    ("Webinar Invitation", 0.16, 0.28, 0.17), ("Nurture Drip", 0.20, 0.24, 0.11),
    ("Event Invitation", 0.09, 0.26, 0.15), ("Case Study", 0.08, 0.29, 0.13),
    ("Re-engagement", 0.05, 0.14, 0.06), ("Demo Follow-up", 0.02, 0.44, 0.28),
]
SUBJECTS = {
    "Newsletter": "The Analytics Brief - {mon}",
    "Product Announcement": "New in Novareach: {theme}",
    "Webinar Invitation": "Live {mon}: {theme}",
    "Nurture Drip": "A practical guide to {theme}",
    "Event Invitation": "Join us at Novareach Summit - {theme} track",
    "Case Study": "How one team cut reporting time by 60%",
    "Re-engagement": "Still thinking about {theme}?",
    "Demo Follow-up": "Your Novareach demo - next steps",
}
THEMES = ["modern analytics", "data consolidation", "AI adoption",
          "real-time decisions", "governed data", "forecast accuracy",
          "analytics ROI", "self-service BI"]


def build_email(s: Scenario, contacts: pd.DataFrame, camp: pd.DataFrame,
                cm: pd.DataFrame, lead: pd.DataFrame, ep: EventPlan,
                rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (fact_email_send, fact_email_event)."""
    email_camps = camp[camp["channel_name"] == "Email"]
    if email_camps.empty:
        return pd.DataFrame(), pd.DataFrame()

    months = cm[cm["campaign_id"].isin(email_camps["campaign_id"])].copy()
    months["month_start"] = pd.to_datetime(months["month_start"])

    # Only subscribed contacts, and only those already acquired: you cannot
    # email someone before marketing found them.
    first_seen = (lead.groupby("contact_id")["lead_date"].min()
                  .pipe(pd.to_datetime))
    sub = contacts[contacts["is_email_subscribed"] == 1].copy()
    sub["first_seen"] = sub["contact_id"].map(first_seen)
    sub = sub[sub["first_seen"].notna()]

    per = float(s.sizes["email_sends_per_contact_month"])
    by_region = {r: g for r, g in sub.groupby("region_name")}

    rows = []
    for _, m in months.iterrows():
        pool = by_region.get(m["region_name"])
        if pool is None or pool.empty:
            continue
        m0 = m["month_start"]
        # Eligible: acquired, and not yet suppressed.
        elig = pool[(pool["first_seen"] <= m0)
                    & (pool["suppression_date"].isna()
                       | (pd.to_datetime(pool["suppression_date"]) > m0))]
        if elig.empty:
            continue
        n = int(min(len(elig), rng.poisson(per * len(elig))))
        if n <= 0:
            continue
        pick = elig.sample(n=n, random_state=int(rng.integers(0, 2 ** 31)))
        et_i = rng.choice(len(EMAIL_TYPES), n,
                          p=[e[1] for e in EMAIL_TYPES])
        day = rng.integers(1, m0.days_in_month + 1, n)
        rows.append(pd.DataFrame({
            "campaign_id": np.int32(m["campaign_id"]),
            "contact_id": pick["contact_id"].to_numpy(),
            "customer_id": pick["customer_id"].to_numpy(),
            "region_name": m["region_name"],
            "send_date": m0 + pd.to_timedelta(day - 1, unit="D"),
            "email_type": np.array([EMAIL_TYPES[i][0] for i in et_i]),
            "_open_p": np.array([EMAIL_TYPES[i][2] for i in et_i]),
            "_click_p": np.array([EMAIL_TYPES[i][3] for i in et_i]),
        }))
    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    snd = pd.concat(rows, ignore_index=True)
    snd = snd[snd["send_date"] <= pd.Timestamp(s.timeline.as_of_date)]
    snd = snd.sort_values("send_date").reset_index(drop=True)
    n = len(snd)
    snd.insert(0, "email_send_id", np.arange(1, n + 1))

    theme = rng.choice(THEMES, n)
    mon = snd["send_date"].dt.strftime("%B")
    snd["subject_line"] = [
        SUBJECTS[t].format(mon=mo, theme=th)
        for t, mo, th in zip(snd["email_type"], mon, theme)]

    # Delivery, then engagement conditional on delivery. Bounce rate climbs on
    # older list segments, which is what makes list hygiene visible.
    delivered = rng.random(n) > np.clip(rng.normal(0.022, 0.010, n), 0.002, 0.12)
    snd["is_delivered"] = delivered.astype(np.int8)
    snd["is_bounced"] = (~delivered).astype(np.int8)
    snd["bounce_type"] = np.where(
        delivered, "", np.where(rng.random(n) < 0.34, "Hard", "Soft"))
    snd["send_month"] = snd["send_date"].dt.to_period("M").dt.start_time.dt.date
    snd["send_date"] = snd["send_date"].dt.date

    ev = _events(s, snd, delivered, rng)
    snd = snd.drop(columns=["_open_p", "_click_p"])
    return snd, ev


def _events(s: Scenario, snd: pd.DataFrame, delivered: np.ndarray,
            rng: np.random.Generator) -> pd.DataFrame:
    """Opens, clicks, unsubscribes - as rows, with their own dates.

    Clicks are conditional on opens, so CTOR is a real ratio rather than two
    independent draws that can produce more clicks than opens.
    """
    n = len(snd)
    sent_dt = pd.to_datetime(snd["send_date"])
    opened = delivered & (rng.random(n) < snd["_open_p"].to_numpy())
    clicked = opened & (rng.random(n) < snd["_click_p"].to_numpy()
                        / np.maximum(snd["_open_p"].to_numpy(), 1e-6) * 0.42)
    unsub = opened & (rng.random(n) < 0.006)

    frames = []
    as_of = pd.Timestamp(s.timeline.as_of_date)
    for kind, mask, lag_med in (("Delivered", delivered, 0.0),
                                ("Opened", opened, 0.9),
                                ("Clicked", clicked, 1.4),
                                ("Unsubscribed", unsub, 3.0)):
        if not mask.any():
            continue
        k = int(mask.sum())
        lag = np.round(rng.exponential(lag_med, k)) if lag_med > 0 else np.zeros(k)
        when = sent_dt[mask] + pd.to_timedelta(lag, unit="D")
        when = np.minimum(when, as_of)
        sub = snd[mask]
        frames.append(pd.DataFrame({
            "email_send_id": sub["email_send_id"].to_numpy(),
            "campaign_id": sub["campaign_id"].to_numpy(),
            "contact_id": sub["contact_id"].to_numpy(),
            "customer_id": sub["customer_id"].to_numpy(),
            "region_name": sub["region_name"].to_numpy(),
            "email_type": sub["email_type"].to_numpy(),
            "event_date": pd.DatetimeIndex(when).date,
            "event_type": kind,
        }))
    ev = pd.concat(frames, ignore_index=True).sort_values(
        ["email_send_id", "event_date"]).reset_index(drop=True)
    ev.insert(0, "email_event_id", np.arange(1, len(ev) + 1))
    return ev
