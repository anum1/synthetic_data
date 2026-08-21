"""Policy and reference dimensions: terms, currency, rates, holds, tolerances.

`dim_match_tolerance` is the one that matters. The match verdict on every
invoice line is computed against these rows, so the tolerance has to be data
that a viewer can read and reproduce - not a constant buried in the generator
(PLAN 2.3).
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np
import pandas as pd

import reference as ref
from p2pconfig import Scenario, month_end

CURRENCY_NAMES = {"USD": "US Dollar", "EUR": "Euro", "GBP": "Pound Sterling",
                  "SGD": "Singapore Dollar", "CAD": "Canadian Dollar",
                  "JPY": "Japanese Yen", "MXN": "Mexican Peso"}


def parse_terms(code: str) -> tuple[float, int, int]:
    """'2/10 Net 30' -> (0.02, 10, 30). 'Net 45' -> (0.0, 0, 45)."""
    if code.strip().lower() == "immediate":
        return 0.0, 0, 0
    disc_pct, disc_days = 0.0, 0
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*/\s*(\d+)", code)
    if m:
        disc_pct, disc_days = float(m.group(1)) / 100.0, int(m.group(2))
    m2 = re.search(r"[Nn]et\s*(\d+)", code)
    net = int(m2.group(1)) if m2 else 30
    return disc_pct, disc_days, net


def build_dim_payment_terms(s: Scenario) -> pd.DataFrame:
    rows = []
    for i, (code, weight) in enumerate(s.payment["terms_mix"].items(), start=1):
        pct, days, net = parse_terms(code)
        rows.append({
            "payment_terms_id": i,
            "payment_terms_code": code,
            "payment_terms_name": code,
            "discount_percent": round(pct, 4),
            "discount_days": days,
            "net_days": net,
            "is_discount_eligible": int(pct > 0),
            # Annualised value of taking the discount. 2/10 Net 30 is ~36.7% a
            # year, which is the sentence that makes a CFO sit up.
            "implied_annual_rate": round(
                (pct / (1 - pct)) * (365 / max(net - days, 1)), 4) if pct > 0 else 0.0,
            "_weight": float(weight),
        })
    return pd.DataFrame(rows)


def build_dim_currency(s: Scenario) -> pd.DataFrame:
    rows = []
    for i, (code, rate) in enumerate(s.currency["rates"].items(), start=1):
        rows.append({"currency_id": i, "currency_code": code,
                     "currency_name": CURRENCY_NAMES.get(code, code),
                     "units_per_usd": float(rate),
                     "is_base_currency": int(code == s.currency["base"])})
    return pd.DataFrame(rows)


def build_dim_exchange_rate(s: Scenario, rng: np.random.Generator) -> pd.DataFrame:
    """Daily rates as a random walk, plus the FX red herring.

    Event 17 moves EUR far enough that a European supplier's USD spend appears
    to rise 9% while its EUR price list never changes. The analyst who checks
    the rate gets it right; the one who reads the USD trend does not.
    """
    days = pd.date_range(s.timeline.start_date, s.timeline.end_date, freq="D")
    n = len(days)
    ev = s.event("fx_red_herring")
    fx_start = s.timeline.offset_month(int(ev["start_offset"])) if ev else None

    frames = []
    for code, units_per_usd in s.currency["rates"].items():
        base_to_usd = 1.0 / float(units_per_usd)
        vol = float(s.currency["volatility"].get(code, 0.03))
        if code == s.currency["base"]:
            series = np.ones(n)
        else:
            step = rng.normal(0, vol / np.sqrt(252), size=n)
            walk = np.cumsum(step)
            walk -= walk.mean()
            series = base_to_usd * np.exp(walk)
            if ev and code == ev["currency"] and fx_start is not None:
                # Ramp the currency across the event window so the apparent price
                # increase is entirely rate. The correction has to CONTROL the
                # total move, not add to it: the walk carries its own drift, and
                # a multiplicative +9% on top of a walk that already drifted 10%
                # lands on 20% - which is a different story from the one the
                # config asked for.
                d = np.array([(x.date() - fx_start).days for x in days], dtype=float)
                span = max((s.timeline.as_of_date - fx_start).days, 1)
                ramp = np.clip(d / span, 0.0, 1.0)
                i0 = int(np.argmin(np.abs(d)))
                i1 = int(np.argmin(np.abs(d - span)))
                actual = np.log(series[i1] / series[i0])
                desired = np.log(1.0 + float(ev["apparent_increase"]))
                series = series * np.exp((desired - actual) * ramp)
        frames.append(pd.DataFrame({
            "currency_code": code,
            "rate_date": [x.date() for x in days],
            "rate_to_usd": np.round(series, 6),
        }))
    df = pd.concat(frames, ignore_index=True)
    df["exchange_rate_id"] = np.arange(1, len(df) + 1, dtype=np.int64)
    df["units_per_usd"] = np.round(1.0 / df["rate_to_usd"], 6)
    return df


def build_dim_hold_reason() -> pd.DataFrame:
    rows = []
    for i, (code, desc, owner, blocks) in enumerate(ref.HOLD_REASONS, start=1):
        rows.append({"hold_reason_id": i, "hold_reason_code": code,
                     "hold_reason_description": desc, "owning_team": owner,
                     "blocks_payment": blocks,
                     "hold_category": _hold_category(code)})
    return pd.DataFrame(rows)


def _hold_category(code: str) -> str:
    if code in ("PRICE_VAR", "QTY_VAR", "AMT_VAR", "FX_VAR", "FREIGHT_VAR"):
        return "Match Variance"
    if code in ("NO_RECEIPT", "NO_PO", "PO_CLOSED", "EARLY_INVOICE", "QUALITY_HOLD"):
        return "Document Missing"
    if code in ("DUP_SUSPECT",):
        return "Duplicate"
    if code in ("BANK_MISSING", "SUPPLIER_BLOCK", "TAX_ID_MISSING", "REMIT_MISMATCH",
                "CONTRACT_EXP"):
        return "Supplier Master"
    return "Coding and Approval"


def build_dim_match_tolerance(s: Scenario) -> pd.DataFrame:
    """One default row plus per-segment overrides, effective-dated.

    Direct materials are held to 1% on price because the contract is
    negotiated to the cent; Travel is held to 5% because nobody wants an AP
    clerk chasing a $12 hotel variance.
    """
    d = s.matching["default_tolerance"]
    rows = [{
        "match_tolerance_id": 1, "scope_type": "Default", "segment_name": "All",
        "price_tolerance_pct": float(d["price_tolerance_pct"]),
        "price_tolerance_abs_usd": float(d["price_tolerance_abs_usd"]),
        "qty_tolerance_pct": float(d["qty_tolerance_pct"]),
        "qty_tolerance_abs_units": float(d["qty_tolerance_abs_units"]),
        "total_variance_cap_usd": float(d["total_variance_cap_usd"]),
        "effective_from_date": s.timeline.start_date, "is_current": 1,
    }]
    for i, (segment, over) in enumerate(s.matching["tolerance_overrides"].items(),
                                        start=2):
        merged = dict(d)
        merged.update(over)
        rows.append({
            "match_tolerance_id": i, "scope_type": "Segment", "segment_name": segment,
            "price_tolerance_pct": float(merged["price_tolerance_pct"]),
            "price_tolerance_abs_usd": float(merged["price_tolerance_abs_usd"]),
            "qty_tolerance_pct": float(merged["qty_tolerance_pct"]),
            "qty_tolerance_abs_units": float(merged["qty_tolerance_abs_units"]),
            "total_variance_cap_usd": float(merged["total_variance_cap_usd"]),
            "effective_from_date": s.timeline.start_date, "is_current": 1,
        })
    _ = (dt, month_end)
    return pd.DataFrame(rows)


def tolerance_lookup(tol: pd.DataFrame) -> dict:
    """segment_name -> tolerance dict, with the default under key '*'."""
    out = {"*": tol[tol["scope_type"] == "Default"].iloc[0].to_dict()}
    for _, r in tol[tol["scope_type"] == "Segment"].iterrows():
        out[r["segment_name"]] = r.to_dict()
    return out
