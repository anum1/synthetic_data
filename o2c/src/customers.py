"""Customer master: hierarchy, sites, credit limits and behaviour parameters.

Two things here are load-bearing for the demo and worth calling out.

`spend_weight` is a Pareto draw that decides how much of the order stream each
customer takes. It is *not* written to disk - it is the generator's dial, and
publishing it would hand the audience the answer key. What is written is the
consequence: a customer base where the top 20% take roughly 70% of revenue,
which is what an industrial distributor actually looks like and what makes a
"top customers" cut interesting rather than flat.

`days_to_pay_mean` is likewise internal. Event 6 shifts it for one customer part
way through the timeline, and the visible consequence is the payment dates.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from o2cconfig import Scenario


def _weighted_choice(rng, options, weights, size):
    w = np.asarray(weights, dtype=float)
    return rng.choice(options, size=size, p=w / w.sum())


def expected_monthly_bookings_usd(s: Scenario) -> float:
    """Expected company-wide bookings per month at the as-of date.

    Derived from the demand and pricing knobs rather than from the headline
    target, so it stays correct at both tiers and after any config change.
    Credit limits are sized off this, and they have to exist before the first
    order is booked - which is why this is an estimate rather than a lookback
    over orders that do not exist yet.
    """
    d, p = s.demand, s.pricing
    mu_q, sig_q = d["order_line_qty_lognorm"]
    mu_p, sig_p = p["list_price_lognorm"]
    e_qty = float(np.exp(mu_q + sig_q ** 2 / 2))
    e_price = float(np.exp(mu_p + sig_p ** 2 / 2))
    e_lines = float(d["lines_per_order_lambda"]) + 1.0
    avg_disc = float(np.mean(p["standard_discount_range"])) + 0.05
    e_order = e_lines * e_qty * e_price * (1.0 - avg_disc)
    months = len(s.timeline.month_starts())
    growth = float(d["annual_growth"]) ** 0 * (1.0 + float(d["annual_growth"])) ** (months / 12.0)
    return float(s.sizes["orders_per_month_base"]) * growth * e_order


def build_dim_customer(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    """One row per customer, with the hierarchy flattened for BI drill-down.

    The path columns matter: a parent pointer alone will not give you
    "roll everything up to this global account" as a single filter, and the
    Customer 360 scene depends on exactly that.
    """
    n = int(s.sizes["customers"])
    tl = s.timeline

    # Region mix: NA-weighted, as an industrial distributor headquartered there.
    regions = _weighted_choice(rng, ["NA", "EMEA", "APAC", "LATAM"],
                               [0.52, 0.26, 0.16, 0.06], n)
    countries, states, cities = [], [], []
    for reg in regions:
        cs = list(R.GEOGRAPHY[reg])
        country = cs[int(rng.integers(len(cs)))]
        st = R.GEOGRAPHY[reg][country]
        state = st[int(rng.integers(len(st)))]
        countries.append(country)
        states.append(state)
        cities.append(f"{state.split()[0]} City" if rng.random() < 0.25 else None)

    # Names. 1,298 prefix x suffix combinations do not cover 5,000 customers, so
    # a locality is appended once a base name is taken. Nothing is a real firm.
    used: set[str] = set()
    names, legal_names = [], []
    for i in range(n):
        for _ in range(40):
            base = (f"{R.NAME_PREFIX[int(rng.integers(len(R.NAME_PREFIX)))]} "
                    f"{R.NAME_SUFFIX[int(rng.integers(len(R.NAME_SUFFIX)))]}")
            if base not in used:
                break
        if base in used:
            base = f"{base} {states[i].split()[0]}"
        k = 2
        while base in used:
            base = f"{base} {k}"
            k += 1
        used.add(base)
        names.append(base)
        legal_names.append(f"{base} {R.LEGAL_FORM.get(countries[i], 'Ltd.')}")

    segments = _weighted_choice(rng, R.SEGMENTS, R.SEGMENT_MIX, n)
    industries = rng.choice(R.INDUSTRIES, size=n)
    channels = _weighted_choice(rng, R.CHANNELS, R.CHANNEL_MIX, n)

    # Spend concentration. A Pareto tail, then a segment multiplier so that the
    # big spenders are also the ones labelled Strategic - otherwise "top
    # customers" and "Strategic accounts" are two unrelated lists and every
    # segment cut looks like noise.
    alpha = float(s.demand["customer_pareto_alpha"])
    weight = rng.pareto(alpha, n) + 1.0
    seg_mult = pd.Series(segments).map(
        {"Strategic": 9.0, "Enterprise": 3.4, "Mid-Market": 1.3,
         "Small Business": 0.45}).to_numpy()
    weight = weight * seg_mult

    terms_codes = [t[0] for t in R.PAYMENT_TERMS]
    terms_weights = [t[5] for t in R.PAYMENT_TERMS]
    terms = _weighted_choice(rng, terms_codes, terms_weights, n)
    # Big accounts negotiate longer terms. This is why DSO and segment correlate.
    # Big accounts negotiate longer terms, but they are also the accounts
    # finance pushes hardest on, so the override is a minority of them rather
    # than a rule. Set too high, the value-weighted terms run 20 days longer
    # than the headline terms mix suggests and DSO drifts with it.
    long_terms = {"Strategic": "N60", "Enterprise": "N45"}
    for i, seg in enumerate(segments):
        if seg in long_terms and rng.random() < 0.30:
            terms[i] = long_terms[seg]

    billing_rule = _weighted_choice(
        rng, list(s.billing["rule_mix"]), list(s.billing["rule_mix"].values()), n)

    currency = pd.Series(countries).map(R.COUNTRY_CURRENCY).fillna("USD").to_numpy()
    bu = [R.business_unit(c, st) for c, st in zip(countries, states)]

    ratings = _weighted_choice(rng, list(s.credit["rating_mix"]),
                               list(s.credit["rating_mix"].values()), n)
    # Weaker ratings cluster in the smaller segments, as they do in life.
    for i, seg in enumerate(segments):
        if seg == "Strategic" and ratings[i] in ("BB", "B", "CCC"):
            ratings[i] = "A"
        elif seg == "Small Business" and ratings[i] in ("AAA", "AA"):
            ratings[i] = "BBB"

    since = [tl.start_date - dt.timedelta(days=int(rng.integers(30, 4400)))
             for _ in range(n)]

    # Payment behaviour: a per-customer mean lateness multiplier on the terms'
    # due days. Internal - Event 6 moves it, the payment dates show it.
    beh = s.collections["payment_behaviour_by_segment"]
    dtp_mult = np.array([beh[seg] for seg in segments], dtype=float)
    dtp_mult *= np.exp(rng.normal(0.0, 0.14, n))
    rating_drag = pd.Series(ratings).map(
        {"AAA": 0.93, "AA": 0.96, "A": 1.00, "BBB": 1.05,
         "BB": 1.13, "B": 1.24, "CCC": 1.42}).to_numpy()
    dtp_mult *= rating_drag

    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1, dtype="int32"),
        "customer_number": [f"CUST-{i:06d}" for i in range(1, n + 1)],
        "customer_name": names,
        "legal_name": legal_names,
        "customer_segment": segments,
        "industry": industries,
        "preferred_channel": channels,
        "region": regions,
        "country": countries,
        "state_province": states,
        "city": [c if c else f"{st.split()[0]}ville" for c, st in zip(cities, states)],
        "business_unit": bu,
        "currency_code": currency,
        "payment_terms_code": terms,
        "billing_rule": billing_rule,
        "credit_rating": ratings,
        "customer_since_date": since,
        "is_active": 1,
        # internal generator dials, dropped before write
        "_spend_weight": weight,
        "_days_to_pay_mult": dtp_mult,
    })

    # Global accounts: the largest customers become parents, and same-name-ish
    # mid-size customers in the same region are attached beneath them. This is
    # what makes "roll up to the global account" a real question.
    df = df.sort_values("_spend_weight", ascending=False).reset_index(drop=True)
    n_accounts = max(6, n // 60)
    parents = df.head(n_accounts).copy()
    acct_name = parents["customer_name"].str.split().str[0] + " Global"
    df["global_account_id"] = 0
    df["global_account_name"] = "Unaffiliated"
    df.loc[: n_accounts - 1, "global_account_id"] = np.arange(1, n_accounts + 1)
    df.loc[: n_accounts - 1, "global_account_name"] = acct_name.to_numpy()
    rest = df.index[n_accounts:]
    affiliated = rest[rng.random(len(rest)) < 0.30]
    pick = rng.integers(0, n_accounts, len(affiliated))
    df.loc[affiliated, "global_account_id"] = pick + 1
    df.loc[affiliated, "global_account_name"] = acct_name.to_numpy()[pick]

    # Credit limits scale with expected monthly spend, so the credit-hold story
    # lands on customers that actually order enough to breach a limit.
    lo, hi = s.credit["limit_multiple_of_monthly_spend"]
    share = df["_spend_weight"] / df["_spend_weight"].sum()
    monthly_orders_usd = share * expected_monthly_bookings_usd(s)
    mult = rng.uniform(lo, hi, len(df))
    # A segment floor, so the median customer does not sit pinned to a single
    # global minimum. Without it, "available credit" is a constant for half the
    # base and the credit page has nothing to show.
    floor = df["customer_segment"].map(
        {"Strategic": 400_000.0, "Enterprise": 120_000.0,
         "Mid-Market": 40_000.0, "Small Business": 15_000.0}).to_numpy()
    limit = np.maximum(floor, monthly_orders_usd * mult)
    df["credit_limit_usd"] = np.round(limit / 5_000.0) * 5_000.0
    df["credit_status"] = "Active"
    df["last_credit_review_date"] = [
        s.timeline.as_of_date - dt.timedelta(days=int(rng.integers(20, 700)))
        for _ in range(len(df))]

    df = df.sort_values("customer_id").reset_index(drop=True)
    df["customer_path"] = (df["global_account_name"] + " > " + df["region"] + " > "
                           + df["country"] + " > " + df["state_province"] + " > "
                           + df["customer_name"])
    df["customer_level_1"] = df["global_account_name"]
    df["customer_level_2"] = df["region"]
    df["customer_level_3"] = df["country"]
    df["customer_level_4"] = df["state_province"]
    df["customer_level_5"] = df["customer_name"]
    return df


def plant_name_variants(s: Scenario, cust: pd.DataFrame,
                        rng: np.random.Generator) -> pd.DataFrame:
    """Same legal entity, spelled differently across records.

    A deliberate data-quality defect: the audience is asked to notice that
    "Redstone Industrial Inc." and "REDSTONE INDUSTRIAL, INC" are one customer
    with two AR balances. `duplicate_of_customer_id` is the answer, carried on
    the record so the exercise has a verifiable end.
    """
    cust["duplicate_of_customer_id"] = 0
    dq = s.data_quality
    if not dq:
        return cust
    k = int(dq.get("customer_name_variants", 0))
    if k <= 0:
        return cust
    # Draw from mid-sized customers: a duplicated Strategic account would be
    # noticed instantly, and a duplicated dormant one is not worth finding.
    pool = cust[cust["customer_segment"].isin(["Enterprise", "Mid-Market"])]
    pick = pool.sample(n=min(k, len(pool)), random_state=int(s.seed)).index
    for idx in pick:
        name = cust.at[idx, "customer_name"]
        style = int(rng.integers(0, 3))
        if style == 0:
            variant = name.upper() + ","
        elif style == 1:
            variant = name.replace(" ", "  ").title()
        else:
            variant = name + " (formerly " + name.split()[0] + " Corp)"
        cust.at[idx, "customer_name"] = variant
        cust.at[idx, "duplicate_of_customer_id"] = int(cust.at[idx, "customer_id"])
    return cust


def pin_event_baselines(s, cust, ep):
    """Make each event's declared BEFORE state true in the data.

    Event 6 says a customer went from 35 days to 67. The 67 is produced by the
    event; the 35 has to be produced here, or the "before" is whatever the draw
    happened to give that account and the story reads backwards.
    """
    ev = s.event("customer_payment_slowdown")
    if ev is None or not getattr(ep, "slow_payer_id", 0):
        return cust
    row = cust["customer_id"] == ep.slow_payer_id
    terms_due = {t[0]: t[2] for t in R.PAYMENT_TERMS}
    cust.loc[row, "payment_terms_code"] = "N30"
    cust.loc[row, "_days_to_pay_mult"] = (float(ev["days_to_pay_from"])
                                          / max(terms_due["N30"], 1))
    return cust


def build_dim_customer_site(s: Scenario, cust: pd.DataFrame,
                            rng: np.random.Generator) -> pd.DataFrame:
    """Ship-to and bill-to sites. Every order ships to one and bills to another,
    which is what makes the geography of delivery differ from the geography of
    the invoice - and that difference is a real question in a tax discussion."""
    per = float(s.sizes["sites_per_customer"])
    counts = 1 + rng.poisson(max(per - 1.0, 0.05), len(cust))
    counts = np.clip(counts, 1, 6)

    rows = []
    site_id = 1
    for cid, cname, region, country, state, city, n_sites in zip(
            cust["customer_id"], cust["customer_name"], cust["region"],
            cust["country"], cust["state_province"], cust["city"], counts):
        for j in range(int(n_sites)):
            stype = R.SITE_TYPES[int(rng.integers(len(R.SITE_TYPES)))]
            primary = 1 if j == 0 else 0
            rows.append((
                site_id, int(cid), f"SITE-{site_id:07d}",
                f"{cname} - {stype}" if j else f"{cname} - Main",
                stype,
                f"{int(rng.integers(100, 9999))} {R.NAME_PREFIX[int(rng.integers(len(R.NAME_PREFIX)))]} Road",
                city, state, country, region,
                f"{int(rng.integers(10000, 99999)):05d}",
                1, primary if j == 0 else int(rng.random() < 0.25), primary,
            ))
            site_id += 1

    df = pd.DataFrame(rows, columns=[
        "site_id", "customer_id", "site_code", "site_name", "site_type",
        "address_line_1", "city", "state_province", "country", "region",
        "postal_code", "is_ship_to", "is_bill_to", "is_primary_site"])
    df["site_id"] = df["site_id"].astype("int32")
    # Every customer needs at least one bill-to, or invoices have nowhere to go.
    first_of = df.groupby("customer_id")["site_id"].transform("min")
    df.loc[df["site_id"] == first_of, "is_bill_to"] = 1
    return df
