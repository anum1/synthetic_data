"""Shipments, carrier performance, and the delivery event trail.

Three of the fifteen events live here and none of them is a flag.

Event 8 (partial shipments) raises the split rate on one product family, and the
freight consequence follows arithmetically: two shipments cost more than one.
Event 14 (freight leakage) raises the expedite rate, weighted three-to-one
toward lines that were backordered - which is what physically happens, and which
is why it is downstream of Event 3 rather than independent of it.
Event 4 (carrier deterioration) moves one carrier's on-time rate and stretches
its transit times, across every service level it offers.

`fact_delivery_event` is what turns "the shipment was late" into "the shipment
sat in Memphis for four days with a WEATHER code on it", and that difference is
most of the value of a logistics drill-down.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import reference as R
from events import EventPlan
from o2cconfig import Scenario

_DAY = np.timedelta64(1, "D")


def build_shipments(s: Scenario, orders: pd.DataFrame, lines: pd.DataFrame,
                    fulfillment: pd.DataFrame, carriers: pd.DataFrame,
                    wh: pd.DataFrame, prod: pd.DataFrame, ep: EventPlan,
                    rng: np.random.Generator):
    """Return (shipments, shipment_lines, delivery_events)."""
    sh = s.shipping
    as_of = np.datetime64(s.timeline.as_of_date, "D")

    fam = prod.set_index("product_id")["product_family"]
    lines = lines.assign(_family=fam.reindex(lines["product_id"]).to_numpy())

    ship_date_of = fulfillment.set_index(["order_id", "warehouse_id"])["actual_ship_date"]

    # ---- which lines ship, and in how many consignments ---------------------
    ok = (lines["quantity_allocated"].to_numpy() > 0)
    base = lines[ok].copy()
    base["_ship_date"] = ship_date_of.reindex(
        pd.MultiIndex.from_arrays([base["order_id"], base["warehouse_id"]])).to_numpy()
    base = base[pd.notna(base["_ship_date"])]
    base["_ship_date"] = pd.to_datetime(base["_ship_date"]).to_numpy().astype("datetime64[D]")
    base = base[base["_ship_date"] <= as_of]
    base["_qty"] = base["quantity_allocated"]
    base["_leg"] = 0

    # Backordered quantity ships later, as its own consignment. This is the
    # second root of a split shipment, and the honest one: the customer really
    # does get two deliveries.
    bo = lines[(lines["quantity_backordered"].to_numpy() > 0)].copy()
    bo["_ship_date"] = pd.to_datetime(bo["backorder_expected_date"]
                                      ).to_numpy().astype("datetime64[D]")
    bo = bo[pd.notna(bo["_ship_date"]) & (bo["_ship_date"] <= as_of)]
    bo["_qty"] = bo["quantity_backordered"]
    bo["_leg"] = 1

    sl = pd.concat([base, bo], ignore_index=True)

    # Event 8: one family gets split across consignments far more often.
    #
    # The decision is per (order, warehouse) picking group, not per line. Per
    # line, a four-line order splits into four consignments on a coin flip and
    # the baseline split rate drowns out the event entirely.
    grp_keys = list(zip(sl["order_id"], sl["warehouse_id"]))
    sl["_grp"] = pd.factorize(pd.Index(grp_keys))[0]
    grp = sl.groupby("_grp")
    grp_rate = np.full(grp.ngroups, float(s.fulfillment["split_shipment_base_rate"]))
    ev = s.event("partial_shipment_problem")
    if ev is not None:
        has_family = grp["_family"].apply(
            lambda x: bool((x == ev["product_family"]).any())).to_numpy()
        first_date = grp["order_date"].first().to_numpy()
        target = ep.blend("partial_shipment_problem", first_date,
                          float(ev["split_rate_from"]), float(ev["split_rate_to"]))
        grp_rate = np.where(has_family
                            & ep.in_window("partial_shipment_problem", first_date),
                            target, grp_rate)
    # Only groups with more than one line can meaningfully split.
    multi = grp.size().to_numpy() > 1
    split_grp = (rng.random(grp.ngroups) < grp_rate) & multi
    is_split_line = split_grp[sl["_grp"].to_numpy()]
    sl["_leg"] = sl["_leg"].to_numpy() + (
        is_split_line & (rng.random(len(sl)) < 0.45)).astype(int) * 2

    # A shipment is one warehouse, one order, one consignment leg, one day.
    sl["_key"] = list(zip(sl["order_id"], sl["warehouse_id"], sl["_leg"]))
    keys = pd.unique(sl["_key"])
    key_to_id = pd.Series(np.arange(1, len(keys) + 1, dtype=np.int64), index=keys)
    sl["shipment_id"] = key_to_id.reindex(sl["_key"]).to_numpy()

    # ---- shipment headers ----------------------------------------------------
    g = sl.groupby("shipment_id", sort=True)
    hdr = g.agg(order_id=("order_id", "first"),
                warehouse_id=("warehouse_id", "first"),
                customer_id=("customer_id", "first"),
                region=("region", "first"),
                ship_date=("_ship_date", "max"),
                line_count=("order_line_id", "count"),
                shipped_quantity=("_qty", "sum"),
                leg=("_leg", "first")).reset_index()
    n = len(hdr)

    o = orders.set_index("order_id")
    for col in ("promised_delivery_date", "shipping_priority", "site_id",
                "net_order_amount_usd", "total_quantity", "freight_amount_usd",
                "business_unit", "customer_segment"):
        hdr[col] = o[col].reindex(hdr["order_id"]).to_numpy()

    # ---- carrier and service level ------------------------------------------
    had_backorder = hdr["leg"].to_numpy() % 2 == 1
    expedite = np.full(n, float(sh["expedite_base_rate"]))
    ev = s.event("freight_leakage")
    if ev is not None:
        target = ep.blend("freight_leakage", hdr["ship_date"],
                          float(ev["expedite_rate_from"]), float(ev["expedite_rate_to"]))
        bias = np.where(had_backorder, float(ev["backorder_expedite_bias"]), 1.0)
        expedite = np.where(ep.in_window("freight_leakage", hdr["ship_date"]),
                            np.clip(target * bias, 0.0, 0.85), expedite)
    # A Critical order is expedited regardless of what month it is.
    expedite = np.where(hdr["shipping_priority"].to_numpy() == "Critical",
                        np.maximum(expedite, 0.62), expedite)
    is_exp = rng.random(n) < expedite

    exp_pool = carriers[carriers["is_expedited"] == 1]
    std_pool = carriers[carriers["is_expedited"] == 0]
    carrier_id = np.where(
        is_exp,
        exp_pool["carrier_id"].to_numpy()[rng.integers(0, len(exp_pool), n)],
        std_pool["carrier_id"].to_numpy()[rng.integers(0, len(std_pool), n)])

    cmap = carriers.set_index("carrier_id")
    carrier_name = cmap["carrier_name"].reindex(carrier_id).to_numpy()
    service = cmap["service_level"].reindex(carrier_id).to_numpy()
    transit_mult = cmap["transit_multiplier"].reindex(carrier_id).to_numpy()
    cost_mult = cmap["cost_multiplier"].reindex(carrier_id).to_numpy()
    on_time_base = cmap["baseline_on_time_rate"].reindex(carrier_id).to_numpy()

    # ---- transit, and whether it held ---------------------------------------
    tr = sh["transit_days_by_region"]
    base_transit = np.array([rng.integers(*tr.get(r, [3, 7])) for r in hdr["region"]],
                            dtype=float)
    ship_date = pd.to_datetime(hdr["ship_date"]).to_numpy().astype("datetime64[D]")

    ev = s.event("carrier_deterioration")
    on_time = on_time_base.copy()
    if ev is not None:
        hit = carrier_name == ev["carrier_name"]
        ramp = ep.ramp("carrier_deterioration", ship_date)
        on_time = np.where(hit, on_time_base * (1.0 + (float(ev["on_time_multiplier"]) - 1.0) * ramp),
                           on_time)
        transit_mult = np.where(
            hit, transit_mult * (1.0 + (float(ev["transit_multiplier"]) - 1.0) * ramp),
            transit_mult)

    planned_transit = np.maximum(1, np.round(base_transit * transit_mult)).astype(int)
    expected_delivery = ship_date + planned_transit.astype("timedelta64[D]")

    late = rng.random(n) >= on_time
    dlo, dhi = sh["delay_days"]
    delay = np.where(late, rng.integers(dlo, dhi + 1, n), 0)
    actual_delivery = expected_delivery + delay.astype("timedelta64[D]")

    lost = rng.random(n) < float(sh["lost_rate"])
    delivered = (actual_delivery <= as_of) & ~lost

    status = np.full(n, "In Transit", dtype=object)
    status[delivered] = "Delivered"
    status[~delivered & late & ~lost] = "Delayed"
    status[lost] = "Lost"
    just_shipped = (~delivered & ~lost
                    & (ship_date > as_of - np.timedelta64(2, "D")))
    status[just_shipped] = "Picked Up"

    # ---- freight -------------------------------------------------------------
    # Freight is charged per consignment, so splitting an order really does cost
    # more. Event 8's cost consequence is arithmetic, not a second multiplier.
    order_freight = hdr["freight_amount_usd"].to_numpy()
    legs = hdr.groupby("order_id")["shipment_id"].transform("count").to_numpy()
    share = np.where(hdr["total_quantity"].to_numpy() > 0,
                     hdr["shipped_quantity"].to_numpy()
                     / np.maximum(hdr["total_quantity"].to_numpy(), 1), 1.0)
    # Every consignment pays a carrier minimum whatever it weighs, plus a
    # handling charge once an order needs more than one. That is where the money
    # actually leaks when an order splits: two half-loads do not cost what one
    # full load costs, they cost more.
    min_charge = float(sh["min_freight_charge_usd"])
    handling = float(sh["split_handling_charge_usd"])
    freight = np.maximum(order_freight * np.clip(share, 0.05, 1.0), min_charge)
    freight = freight + np.where(legs > 1, handling, 0.0)
    freight = np.round(freight * cost_mult, 2)

    shipments = pd.DataFrame({
        "shipment_id": hdr["shipment_id"].astype("int32"),
        "shipment_number": [f"SH-{i:07d}" for i in hdr["shipment_id"]],
        "order_id": hdr["order_id"].astype("int32"),
        "customer_id": hdr["customer_id"].astype("int32"),
        "site_id": hdr["site_id"].fillna(0).astype("int32"),
        "warehouse_id": hdr["warehouse_id"].astype("int32"),
        "carrier_id": carrier_id.astype("int32"),
        "carrier_name": carrier_name,
        "service_level": service,
        "tracking_number": [f"1Z{int(x):011d}" for x in
                            rng.integers(10 ** 10, 10 ** 11 - 1, n)],
        "ship_date": ship_date,
        "expected_delivery_date": expected_delivery,
        "actual_delivery_date": np.where(delivered, actual_delivery,
                                         np.datetime64("NaT")).astype("datetime64[D]"),
        "promised_delivery_date": pd.to_datetime(
            hdr["promised_delivery_date"]).to_numpy().astype("datetime64[D]"),
        "shipping_priority": hdr["shipping_priority"].to_numpy(),
        "region": hdr["region"].to_numpy(),
        "business_unit": hdr["business_unit"].to_numpy(),
        "line_count": hdr["line_count"].astype("int16"),
        "shipped_quantity": hdr["shipped_quantity"].astype("int64"),
        "planned_transit_days": planned_transit.astype("int16"),
        "actual_transit_days": np.where(
            delivered, ((actual_delivery - ship_date) / _DAY), -1).astype("int16"),
        "delay_days": np.where(delivered, delay, 0).astype("int16"),
        "freight_cost_usd": freight,
        "is_expedited": is_exp.astype("int8"),
        "is_backorder_shipment": had_backorder.astype("int8"),
        "is_split_shipment": (legs > 1).astype("int8"),
        "shipment_status": status,
        "is_delivered": delivered.astype("int8"),
        # Two different questions, and conflating them is how a logistics page
        # ends up arguing with a customer-service page. Carrier performance is
        # against the transit time the carrier quoted; promise performance is
        # against the date the customer was given, which also absorbs warehouse
        # queues, backorders and credit holds.
        "is_on_time_carrier": np.where(
            delivered, actual_delivery <= expected_delivery, False).astype("int8"),
        "is_on_time_promise": np.where(
            delivered,
            actual_delivery <= pd.to_datetime(hdr["promised_delivery_date"])
            .to_numpy().astype("datetime64[D]"), False).astype("int8"),
        "is_lost": lost.astype("int8"),
    })

    shipment_lines = pd.DataFrame({
        "shipment_line_id": np.arange(1, len(sl) + 1, dtype="int64"),
        "shipment_id": sl["shipment_id"].astype("int32"),
        "order_id": sl["order_id"].astype("int32"),
        "order_line_id": sl["order_line_id"].astype("int64"),
        "product_id": sl["product_id"].astype("int32"),
        "warehouse_id": sl["warehouse_id"].astype("int32"),
        "quantity_shipped": sl["_qty"].astype("int64"),
        "unit_price_usd": sl["unit_price_usd"].to_numpy(),
        "extended_amount_usd": np.round(sl["unit_price_usd"].to_numpy()
                                        * sl["_qty"].to_numpy(), 2),
        "unit_cost_usd": sl["unit_cost_usd"].to_numpy(),
        # Carried forward so billing can compare what was billed against what
        # was AGREED, rather than against whatever contract happens to be in
        # force on the invoice date - which is a different question, and one
        # whose answer is mostly noise.
        "agreed_price_usd": np.where(sl["is_contract_price"].to_numpy() == 1,
                                     sl["contract_price_usd"].to_numpy(),
                                     sl["unit_price_usd"].to_numpy()),
        "is_contract_price": sl["is_contract_price"].to_numpy().astype("int8"),
        "is_backorder_line": (sl["_leg"].to_numpy() % 2 == 1).astype("int8"),
    })

    events = _delivery_events(s, shipments, wh, rng)
    return shipments, shipment_lines, events


def _delivery_events(s: Scenario, ship: pd.DataFrame, wh: pd.DataFrame,
                     rng: np.random.Generator) -> pd.DataFrame:
    """The carrier scan trail: 4-7 events per shipment, in order.

    A late shipment carries a Delayed scan with an exception code, so "why was
    it late" resolves to a reason and a place rather than to a number of days.
    """
    n = len(ship)
    lo, hi = s.shipping["events_per_shipment"]
    n_ev = rng.integers(lo, hi + 1, n)
    # A shipment still in transit has not been delivered or gone out for it.
    delivered = ship["is_delivered"].to_numpy() == 1
    n_ev = np.where(delivered, n_ev, np.maximum(2, n_ev - 2))

    idx = np.repeat(np.arange(n), n_ev)
    pos = np.arange(len(idx)) - np.repeat(np.concatenate([[0], np.cumsum(n_ev)[:-1]]), n_ev)
    last = np.repeat(n_ev - 1, n_ev)

    city_of = wh.set_index("warehouse_id")["city"]
    origin = city_of.reindex(ship["warehouse_id"]).fillna("Origin").to_numpy()
    hub = np.array(["Memphis", "Louisville", "Cologne", "Singapore", "Dallas",
                    "Rotterdam", "Osaka", "Panama City", "Chicago", "Dubai"])

    etype = np.full(len(idx), "In Transit", dtype=object)
    etype[pos == 0] = "Label Created"
    etype[pos == 1] = "Picked Up"
    dlv = np.repeat(delivered, n_ev)
    etype[(pos == last) & dlv] = "Delivered"
    etype[(pos == last - 1) & dlv] = "Out for Delivery"

    # One mid-route Delayed scan on the shipments that actually ran late.
    was_late = np.repeat(ship["delay_days"].to_numpy() > 0, n_ev)
    mid = (pos == 2) & (last >= 4)
    etype[mid & was_late] = "Delayed"

    exception = np.full(len(idx), "None", dtype=object)
    sel = etype == "Delayed"
    exception[sel] = rng.choice(R.EXCEPTION_CODES, size=int(sel.sum()),
                                p=[0.26, 0.17, 0.14, 0.11, 0.13, 0.09, 0.06, 0.04])

    location = hub[rng.integers(0, len(hub), len(idx))]
    location[pos == 0] = np.repeat(origin, n_ev)[pos == 0]
    location[pos == 1] = np.repeat(origin, n_ev)[pos == 1]

    # Spread the scans between despatch and delivery.
    start = np.repeat(pd.to_datetime(ship["ship_date"]).to_numpy()
                      .astype("datetime64[D]"), n_ev)
    end_src = np.where(delivered,
                       pd.to_datetime(ship["actual_delivery_date"]).to_numpy()
                       .astype("datetime64[D]"),
                       pd.to_datetime(ship["expected_delivery_date"]).to_numpy()
                       .astype("datetime64[D]"))
    end = np.repeat(end_src, n_ev)
    span = np.maximum((end - start) / _DAY, 1.0)
    frac = np.where(last > 0, pos / np.maximum(last, 1), 0.0)
    ts = start + np.round(frac * span).astype("timedelta64[D]")

    return pd.DataFrame({
        "delivery_event_id": np.arange(1, len(idx) + 1, dtype="int64"),
        "shipment_id": ship["shipment_id"].to_numpy()[idx].astype("int32"),
        "order_id": ship["order_id"].to_numpy()[idx].astype("int32"),
        "event_sequence": (pos + 1).astype("int16"),
        "event_date": ts,
        "event_type": etype,
        "location_city": location,
        "carrier_name": ship["carrier_name"].to_numpy()[idx],
        "exception_code": exception,
        "is_exception": (exception != "None").astype("int8"),
    })
