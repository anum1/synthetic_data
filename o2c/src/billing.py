"""Invoicing: billing rules, invoice lines, price variance and duplicates.

The billing rule is set per customer - per shipment, or consolidated monthly -
and it drives the invoice count, the invoice lag and the shape of Event 5. That
matters because duplicate billing (Event 13) is then a defect on top of a
defined rule, which is a far more convincing finding than a random duplicate
that nobody can explain the origin of.

`fact_invoice_line` carries BOTH `order_line_id` and `shipment_line_id`. Without
them, line-level price variance and "which shipment did this billing error come
from" are unanswerable, and those are the two best drill-downs in the demo.

Event 7 lives here: the invoiced price is compared against `contract_pricing`,
and the variance is a stored column rather than an assertion. Nothing about it
is a flag - a share of lines are billed off a stale price, and the money falls
out of the subtraction.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from o2cconfig import Scenario
from pricing import lookup_contract_price

_DAY = np.timedelta64(1, "D")


def build_invoices(s: Scenario, orders: pd.DataFrame, order_lines: pd.DataFrame,
                   shipments: pd.DataFrame, shipment_lines: pd.DataFrame,
                   contracts: pd.DataFrame, terms: pd.DataFrame,
                   cust: pd.DataFrame, ep: EventPlan, rng: np.random.Generator):
    """Return (invoices, invoice_lines)."""
    as_of = np.datetime64(s.timeline.as_of_date, "D")

    # Only delivered goods get billed. That single rule is what creates the
    # "delivered but not invoiced" pool the executive page is built on.
    dlv = shipments[shipments["is_delivered"] == 1]
    if dlv.empty:
        return pd.DataFrame(), pd.DataFrame()

    sl = shipment_lines[shipment_lines["shipment_id"].isin(dlv["shipment_id"])].copy()
    smap = dlv.set_index("shipment_id")
    sl["_delivered"] = pd.to_datetime(
        smap["actual_delivery_date"].reindex(sl["shipment_id"])).to_numpy().astype("datetime64[D]")
    sl["_customer_id"] = smap["customer_id"].reindex(sl["shipment_id"]).to_numpy()

    o = orders.set_index("order_id")
    for col in ("_billing_lag_days", "billing_rule", "payment_terms_code",
                "business_unit", "region", "currency_code", "bill_to_site_id",
                "sales_rep_id", "customer_segment", "po_number"):
        sl[col] = o[col].reindex(sl["order_id"]).to_numpy()

    lag = sl["_billing_lag_days"].to_numpy().astype("int64")
    invoice_date = sl["_delivered"].to_numpy() + lag.astype("timedelta64[D]")

    # Consolidated customers are billed once a month, on the first of the
    # following month, for everything delivered in it.
    consolidated = sl["billing_rule"].to_numpy() == "consolidated_monthly"
    month_end_bill = (invoice_date.astype("datetime64[M]") + 1).astype("datetime64[D]")
    invoice_date = np.where(consolidated, month_end_bill, invoice_date)
    sl["_invoice_date"] = invoice_date

    # Anything whose invoice date has not arrived yet is delivered-not-invoiced.
    billable = invoice_date <= as_of
    sl = sl[billable].copy()
    if sl.empty:
        return pd.DataFrame(), pd.DataFrame()

    # ---- group lines into invoices ------------------------------------------
    # Per-shipment customers get one invoice per shipment; consolidated ones get
    # one per month. Both are keyed so the grouping is explicit rather than
    # emergent.
    key_ship = sl["shipment_id"].astype(str)
    key_month = (pd.to_datetime(sl["_invoice_date"]).dt.strftime("%Y%m")
                 if len(sl) else pd.Series([], dtype=str))
    grp_key = np.where(sl["billing_rule"].to_numpy() == "consolidated_monthly",
                       "C" + sl["_customer_id"].astype(str) + "-" + key_month.to_numpy(),
                       "S" + key_ship.to_numpy())
    sl["_grp"] = grp_key
    codes, uniques = pd.factorize(sl["_grp"])
    sl["invoice_id"] = codes + 1
    n_inv = len(uniques)

    # ---- price on the invoice, and where it differs from the contract -------
    unit_price = sl["unit_price_usd"].to_numpy().astype(float)
    contract_price = lookup_contract_price(contracts, sl["_customer_id"].to_numpy(),
                                           sl["product_id"].to_numpy(),
                                           sl["_invoice_date"].to_numpy())

    # Event 7: a share of lines are billed off a stale price list. Concentrated
    # in two large accounts so the drill-down converges on a name instead of
    # dissolving into a long tail.
    ev = s.event("pricing_leakage")
    billed_price = unit_price.copy()
    if ev is not None:
        lo, hi = ev["variance_range"]
        share = float(ev["invoice_line_share"])
        big = np.isin(sl["_customer_id"].to_numpy(), ep.leakage_customers)
        # Weighted heavily toward the named accounts, with a thin tail elsewhere
        # so the finding is a concentration rather than an on/off switch.
        p_hit = np.where(big, share * 3.0, share * 0.55)
        hit = (rng.random(len(sl)) < np.clip(p_hit, 0, 0.85)) & \
              ep.in_window("pricing_leakage", sl["_invoice_date"].to_numpy()) & \
              (sl["is_contract_price"].to_numpy() == 1)
        under = 1.0 - rng.uniform(lo, hi, len(sl))
        billed_price = np.where(hit, np.round(unit_price * under, 2), billed_price)

    qty = sl["quantity_shipped"].to_numpy().astype(float)
    extended = np.round(billed_price * qty, 2)
    # The baseline is the price on the ORDER. The order is the agreement, so
    # "invoice price does not match order price" is unambiguous and one-sided:
    # anything non-zero is a billing error, full stop.
    #
    # Contract compliance is a second, separate measure - the order price
    # against the contracted price - because an order can be correctly billed
    # and still have been priced below contract by the rep who took it. Rolling
    # the two together produces a two-sided variance nobody can act on.
    expected = unit_price
    variance = np.round((expected - billed_price) * qty, 2)
    contract_var = np.where(np.isnan(contract_price), 0.0,
                            np.round((np.nan_to_num(contract_price) - billed_price)
                                     * qty, 2))

    inv_lines = pd.DataFrame({
        "invoice_line_id": np.arange(1, len(sl) + 1, dtype="int64"),
        "invoice_id": sl["invoice_id"].astype("int32"),
        "order_id": sl["order_id"].astype("int32"),
        # Both parents, deliberately. Price variance is an order-line question;
        # "which consignment did this come from" is a shipment-line question.
        "order_line_id": sl["order_line_id"].astype("int64"),
        "shipment_line_id": sl["shipment_line_id"].astype("int64"),
        "shipment_id": sl["shipment_id"].astype("int32"),
        "product_id": sl["product_id"].astype("int32"),
        "quantity_invoiced": qty.astype("int64"),
        "unit_price_usd": np.round(billed_price, 2),
        "order_unit_price_usd": np.round(unit_price, 2),
        "contract_price_usd": np.round(np.nan_to_num(contract_price, nan=0.0), 2),
        "extended_amount_usd": extended,
        "unit_cost_usd": sl["unit_cost_usd"].to_numpy(),
        "extended_cost_usd": np.round(sl["unit_cost_usd"].to_numpy() * qty, 2),
        "price_variance_usd": variance,
        "contract_variance_usd": contract_var,
        "underbilled_amount_usd": np.round(np.maximum(variance, 0.0), 2),
        "has_price_variance": (np.abs(variance) > 0.005).astype("int8"),
        "is_below_contract": (contract_var > 0.005).astype("int8"),
        "is_contract_line": (~np.isnan(contract_price)).astype("int8"),
    })

    # ---- invoice headers ----------------------------------------------------
    g = sl.assign(_ext=extended).groupby("invoice_id", sort=True)
    hdr = g.agg(customer_id=("_customer_id", "first"),
                order_id=("order_id", "first"),
                invoice_date=("_invoice_date", "max"),
                bill_to_site_id=("bill_to_site_id", "first"),
                sales_rep_id=("sales_rep_id", "first"),
                payment_terms_code=("payment_terms_code", "first"),
                billing_rule=("billing_rule", "first"),
                business_unit=("business_unit", "first"),
                region=("region", "first"),
                currency_code=("currency_code", "first"),
                customer_segment=("customer_segment", "first"),
                po_number=("po_number", "first"),
                net_amount_usd=("_ext", "sum"),
                line_count=("order_line_id", "count"),
                order_count=("order_id", "nunique"),
                first_delivery=("_delivered", "min")).reset_index()

    inv_date = pd.to_datetime(hdr["invoice_date"]).to_numpy().astype("datetime64[D]")
    tax_rate = hdr["region"].map(s.billing["tax_rate_by_region"]).fillna(0.08).to_numpy()
    net = hdr["net_amount_usd"].to_numpy()

    # Freight is billed on the invoice that carries the consignment.
    fr = shipments.groupby("order_id")["freight_cost_usd"].sum()
    freight = np.round(fr.reindex(hdr["order_id"]).fillna(0.0).to_numpy()
                       / np.maximum(hdr["order_count"].to_numpy(), 1), 2)
    tax = np.round(net * tax_rate, 2)
    total = np.round(net + tax + freight, 2)

    due_map = terms.set_index("payment_terms_code")["due_days"]
    due_days = due_map.reindex(hdr["payment_terms_code"]).fillna(30).to_numpy()
    due_date = inv_date + np.maximum(due_days, 0).astype("timedelta64[D]")

    invoices = pd.DataFrame({
        "invoice_id": hdr["invoice_id"].astype("int32"),
        "invoice_number": [f"INV-{i:07d}" for i in hdr["invoice_id"]],
        "customer_id": hdr["customer_id"].astype("int32"),
        "order_id": hdr["order_id"].astype("int32"),
        "bill_to_site_id": hdr["bill_to_site_id"].fillna(0).astype("int32"),
        "sales_rep_id": hdr["sales_rep_id"].fillna(0).astype("int32"),
        "invoice_date": inv_date,
        "due_date": due_date,
        "first_delivery_date": pd.to_datetime(hdr["first_delivery"]
                                              ).to_numpy().astype("datetime64[D]"),
        "payment_terms_code": hdr["payment_terms_code"].to_numpy(),
        "billing_rule": hdr["billing_rule"].to_numpy(),
        "business_unit": hdr["business_unit"].to_numpy(),
        "region": hdr["region"].to_numpy(),
        "customer_segment": hdr["customer_segment"].to_numpy(),
        "currency_code": hdr["currency_code"].to_numpy(),
        "po_number": hdr["po_number"].to_numpy(),
        "line_count": hdr["line_count"].astype("int16"),
        "order_count": hdr["order_count"].astype("int16"),
        "net_amount_usd": np.round(net, 2),
        "tax_amount_usd": tax,
        "freight_amount_usd": freight,
        "total_amount_usd": total,
        "is_duplicate": 0,
        "duplicate_of_invoice_id": 0,
    })
    invoices["days_delivery_to_invoice"] = (
        (inv_date - invoices["first_delivery_date"].to_numpy()) / _DAY).astype("int16")
    od = o["order_date"].reindex(invoices["order_id"])
    invoices["days_order_to_invoice"] = (
        (inv_date - pd.to_datetime(od).to_numpy().astype("datetime64[D]")) / _DAY
    ).astype("int16")

    invoices, inv_lines = _plant_duplicates(s, invoices, inv_lines, ep, rng)
    return invoices, inv_lines


def _plant_duplicates(s: Scenario, invoices: pd.DataFrame, inv_lines: pd.DataFrame,
                      ep: EventPlan, rng: np.random.Generator):
    """Event 13: a small number of orders are billed twice.

    The duplicate is a genuine copy - same customer, same amount, an invoice
    date a few days later, its own invoice number - because that is what makes
    it findable by the same query a real AR team would write, rather than by
    reading a flag the generator left behind.
    """
    ev = s.event("duplicate_billing")
    if ev is None or invoices.empty:
        return invoices, inv_lines
    in_win = ep.in_window("duplicate_billing", invoices["invoice_date"].to_numpy())
    pool = np.where(in_win)[0]
    if len(pool) == 0:
        return invoices, inv_lines
    k = max(1, int(round(float(ev["order_share"]) * len(invoices))))
    pick = rng.choice(pool, size=min(k, len(pool)), replace=False)

    dup = invoices.iloc[pick].copy()
    next_id = int(invoices["invoice_id"].max()) + 1
    dup["duplicate_of_invoice_id"] = dup["invoice_id"].to_numpy()
    dup["invoice_id"] = np.arange(next_id, next_id + len(dup), dtype="int32")
    dup["invoice_number"] = [f"INV-{i:07d}" for i in dup["invoice_id"]]
    dup["is_duplicate"] = 1
    shift = rng.integers(1, 12, len(dup)).astype("timedelta64[D]")
    dup["invoice_date"] = pd.to_datetime(dup["invoice_date"]).to_numpy().astype("datetime64[D]") + shift
    dup["due_date"] = pd.to_datetime(dup["due_date"]).to_numpy().astype("datetime64[D]") + shift

    src = inv_lines[inv_lines["invoice_id"].isin(invoices.iloc[pick]["invoice_id"])].copy()
    remap = pd.Series(dup["invoice_id"].to_numpy(),
                      index=invoices.iloc[pick]["invoice_id"].to_numpy())
    src["invoice_id"] = remap.reindex(src["invoice_id"]).to_numpy()
    src["invoice_line_id"] = np.arange(int(inv_lines["invoice_line_id"].max()) + 1,
                                       int(inv_lines["invoice_line_id"].max()) + 1 + len(src),
                                       dtype="int64")

    out_inv = pd.concat([invoices, dup], ignore_index=True)
    out_lines = pd.concat([inv_lines, src], ignore_index=True)
    keep = out_inv["invoice_date"].to_numpy() <= np.datetime64(s.timeline.as_of_date, "D")
    out_inv = out_inv[keep].reset_index(drop=True)
    out_lines = out_lines[out_lines["invoice_id"].isin(out_inv["invoice_id"])].reset_index(drop=True)
    return out_inv, out_lines
