"""Fact table generation.

Orders are generated first and then exploded into lines, so the order header
total is an aggregate of its own lines by construction and can never drift.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventEngine, LineContext

ORDER_STATUS = ["Completed", "Shipped", "Invoiced", "Pending", "Cancelled"]
ORDER_STATUS_P = [0.62, 0.18, 0.12, 0.06, 0.02]
PAYMENT_METHODS = ["Credit Card", "Purchase Order", "Wire Transfer", "ACH", "Net Terms"]
PAYMENT_P = [0.31, 0.27, 0.13, 0.12, 0.17]
SHIP_METHODS = ["Ground", "Two-Day", "Overnight", "Freight", "Digital Delivery"]
SHIP_P = [0.47, 0.22, 0.09, 0.14, 0.08]
SHIP_DAYS = {"Ground": 5, "Two-Day": 2, "Overnight": 1, "Freight": 9, "Digital Delivery": 0}
PRIORITIES = ["Low", "Medium", "High", "Critical"]
PRIORITY_P = [0.22, 0.48, 0.24, 0.06]


def _lifecycle_curve(age_months: np.ndarray) -> np.ndarray:
    """Demand multiplier by product age: ramp, plateau, then decline.

    Roughly: three months to reach full availability, ~15 months at peak,
    then a steady fade as the next generation takes over.
    """
    return np.select(
        [age_months < 0,
         age_months < 3,
         age_months <= 18,
         age_months <= 32],
        [0.0,
         0.55 + 0.15 * np.clip(age_months, 0, None),
         1.0,
         1.0 - 0.62 * (age_months - 18) / 14.0],
        default=0.34)


def month_range(start: dt.date, end: dt.date) -> list[dt.date]:
    out, cur = [], start.replace(day=1)
    while cur <= end:
        out.append(cur)
        cur = (cur + dt.timedelta(days=32)).replace(day=1)
    return out


def _month_weights(months: list[dt.date], baseline: dict, as_of: dt.date) -> np.ndarray:
    """Seasonality x compound growth, with the final partial month pro-rated."""
    seasonality = np.asarray(baseline["seasonality"], dtype=float)
    growth = float(baseline["underlying_growth_yoy"])
    base_year = months[0].year
    w = []
    for m in months:
        years = (m.year - base_year) + (m.month - 1) / 12.0
        weight = seasonality[m.month - 1] * (1 + growth) ** years
        if m.year == as_of.year and m.month == as_of.month:
            days_in = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - m
            weight *= as_of.day / days_in.days
        w.append(weight)
    return np.asarray(w)


def _draw_days(month: dt.date, n: int, weekday_w: np.ndarray,
               rng: np.random.Generator, as_of: dt.date) -> np.ndarray:
    """Dates within a month, weighted by day of week, never past as-of."""
    last = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    last = min(last, as_of)
    days = pd.date_range(month, last, freq="D")
    if len(days) == 0:
        days = pd.DatetimeIndex([month])
    p = weekday_w[days.weekday]
    p = p / p.sum()
    return days.to_numpy()[rng.choice(len(days), size=n, p=p)]


class SalesGenerator:
    def __init__(self, scenario, dims: dict, rng: np.random.Generator):
        self.s = scenario
        self.d = dims
        self.rng = rng
        self.events = EventEngine(scenario, dims["dim_product"], rng)
        self._prepare_lookups()

    # ------------------------------------------------------------------ setup
    def _prepare_lookups(self):
        prod = self.d["dim_product"]
        cust = self.d["dim_customer"]
        loc = self.d["dim_location"]
        rep = self.d["dim_sales_rep"]
        sup = self.d["dim_supplier"]

        self.p_id = prod["product_id"].to_numpy()
        self.p_list = prod["list_price"].to_numpy(dtype=float)
        self.p_cost = prod["standard_cost"].to_numpy(dtype=float)
        self.p_cat = prod["category"].to_numpy()
        self.p_sub = prod["subcategory"].to_numpy()
        self.p_name = prod["product_name"].to_numpy()
        self.p_sup = prod["supplier_id"].to_numpy()
        self.p_catkey = prod["product_category_id"].to_numpy()
        self.p_launch = pd.to_datetime(prod["product_launch_date"]).to_numpy()
        self.p_end = pd.to_datetime(prod["product_end_date"]).to_numpy()
        self._p_cache: dict = {}

        sup_group = dict(zip(sup["supplier_id"], sup["supplier_group"]))
        sup_lead = dict(zip(sup["supplier_id"], sup["default_lead_time_days"]))
        self.p_sup_group = np.array([sup_group[s] for s in self.p_sup])
        self.p_lead = np.array([sup_lead[s] for s in self.p_sup], dtype=float)

        w = prod["demand_weight"].to_numpy(dtype=float)
        self.p_weight = w / w.sum()

        self.c_id = cust["customer_id"].to_numpy()
        self.c_name = cust["customer_name"].to_numpy()
        self.c_region = cust["region"].to_numpy()
        self.c_channel = cust["sales_channel"].to_numpy()
        cw = cust["_spend_weight"].to_numpy(dtype=float)
        self.c_weight = cw / cw.sum()

        self.l_id = loc["location_id"].to_numpy()
        self.l_region = loc["region"].to_numpy()
        self.l_country = loc["country"].to_numpy()
        self.l_currency = loc["currency_code"].to_numpy()
        self.l_countrykey = loc["country_id"].to_numpy()
        self.region_loc_idx = {r: np.flatnonzero(self.l_region == r)
                               for r in np.unique(self.l_region)}

        active_rep = rep[rep["is_active"] == 1]
        self.r_id = active_rep["sales_rep_id"].to_numpy()
        r_region = active_rep["sales_region"].to_numpy()
        self.region_rep_idx = {r: np.flatnonzero(r_region == r)
                               for r in np.unique(r_region)}
        self.all_rep_idx = np.arange(len(self.r_id))

        self.channels = self.d["dim_channel"]["sales_channel"].to_numpy()
        self.channel_ids = dict(zip(self.d["dim_channel"]["sales_channel"],
                                    self.d["dim_channel"]["channel_id"]))
        self.channel_p = self.d["dim_channel"]["target_mix_pct"].to_numpy(dtype=float)
        self.channel_p = self.channel_p / self.channel_p.sum()

        promo = self.d["dim_promotion"]
        self.promo = promo[promo["promotion_id"] > 0].reset_index(drop=True)

        fx = self.d["dim_exchange_rate"]
        self.fx = {(r.year_month_key, r.currency_code): r.rate_to_usd
                   for r in fx.itertuples()}

    # ------------------------------------------------------------- generation
    def generate(self) -> dict[str, pd.DataFrame]:
        t = self.s.timeline
        months = month_range(t.start_date, t.as_of_date)
        weights = _month_weights(months, self.s.baseline, t.as_of_date)
        weights = weights / weights.sum()

        total_lines = int(self.s.sizes["order_lines"])
        per_month = np.maximum((weights * total_lines).astype(int), 50)

        lo, hi = self.s.baseline["lines_per_order"]
        avg_lpo = (lo + hi) / 2.0
        weekday_w = np.asarray(self.s.baseline["weekday_weights"], dtype=float)

        order_parts, line_parts = [], []
        next_order_id, next_line_id = 1, 1

        for month, n_lines in zip(months, per_month):
            n_orders = max(int(round(n_lines / avg_lpo)), 10)
            orders, lines, next_line_id = self._build_month(
                month, n_orders, next_order_id, next_line_id, weekday_w, lo, hi)
            next_order_id += n_orders
            order_parts.append(orders)
            line_parts.append(lines)

        orders = pd.concat(order_parts, ignore_index=True)
        lines = pd.concat(line_parts, ignore_index=True)
        orders, lines = self._inject_anomaly(orders, lines)
        orders = self._reconcile_headers(orders, lines)
        orders, lines = self._inject_data_quality(orders, lines)
        return {"fact_sales_order": orders, "fact_sales_order_line": lines}

    def _build_month(self, month, n_orders, order_id0, line_id0, weekday_w, lo, hi):
        rng = self.rng
        t = self.s.timeline

        # ---- order header attributes
        c_w = self.events.customer_weight_multiplier(month, self.c_name)
        if c_w is None:
            c_p = self.c_weight
        else:
            c_p = self.c_weight * c_w
            c_p = c_p / c_p.sum()
        c_idx = rng.choice(len(self.c_id), size=n_orders, p=c_p)
        order_dates = _draw_days(month, n_orders, weekday_w, rng, t.as_of_date)

        regions = self.c_region[c_idx]
        loc_idx = self._pick_by_region(regions, self.region_loc_idx, len(self.l_id))
        rep_idx = self._pick_by_region(regions, self.region_rep_idx, len(self.r_id))

        # 70% of orders use the customer's default channel.
        rand_ch = self.channels[rng.choice(len(self.channels), size=n_orders, p=self.channel_p)]
        channel = np.where(rng.random(n_orders) < 0.70, self.c_channel[c_idx], rand_ch)

        ship_method = rng.choice(SHIP_METHODS, size=n_orders, p=SHIP_P)
        status = rng.choice(ORDER_STATUS, size=n_orders, p=ORDER_STATUS_P)

        # ---- explode to lines
        n_per_order = rng.integers(lo, hi + 1, size=n_orders)
        n_lines = int(n_per_order.sum())
        o_row = np.repeat(np.arange(n_orders), n_per_order)

        p_idx = rng.choice(len(self.p_id), size=n_lines, p=self._product_p(month))
        l_region = self.l_region[loc_idx][o_row]
        l_country = self.l_country[loc_idx][o_row]

        ctx = LineContext(
            month=month, n=n_lines,
            category=self.p_cat[p_idx], subcategory=self.p_sub[p_idx],
            product_name=self.p_name[p_idx], supplier_group=self.p_sup_group[p_idx],
            region=l_region, country=l_country,
            customer_name=self.c_name[c_idx][o_row], product_id=self.p_id[p_idx])
        mult = self.events.apply(ctx)

        # ---- economics
        base_qty = np.maximum(rng.poisson(2.6, n_lines), 1) * \
            np.where(self.p_cat[p_idx] == "Components", 3, 1)
        quantity = np.maximum(np.round(base_qty * mult.qty), 1).astype("int32")

        list_price = self.p_list[p_idx]
        unit_price = list_price * mult.price * rng.normal(1.0, 0.018, n_lines).clip(0.9, 1.1)

        base_disc = float(self.s.baseline["base_discount_pct"])
        promo_id, promo_disc = self._assign_promotions(month, ctx, n_lines)
        discount_pct = np.clip(
            base_disc + mult.disc_points + promo_disc
            + rng.normal(0, 0.022, n_lines), 0.0, 0.62)

        gross_sales = unit_price * quantity
        discount_amount = gross_sales * discount_pct
        net_sales = gross_sales - discount_amount

        unit_cost = self.p_cost[p_idx] * mult.cost * rng.normal(1.0, 0.012, n_lines).clip(0.92, 1.08)
        cost = unit_cost * quantity
        shipping_cost = np.where(self.p_cat[p_idx] == "Software & Services", 0.0,
                                 np.maximum(rng.normal(0.021, 0.006, n_lines), 0.004) * net_sales)
        tax_amount = net_sales * rng.choice([0.0, 0.07, 0.19, 0.20, 0.10], size=n_lines,
                                            p=[0.18, 0.30, 0.22, 0.18, 0.12])
        gross_profit = net_sales - cost - shipping_cost

        # ---- currency (resolved at order level, then broadcast to lines)
        ym_key = month.year * 100 + month.month
        order_currency = self.l_currency[loc_idx]
        order_fx = np.array([self.fx.get((ym_key, c), 1.0) for c in order_currency])
        currency = order_currency[o_row]
        fx_rate = order_fx[o_row]

        dates = order_dates[o_row]
        req_ship = order_dates + np.array(
            [np.timedelta64(SHIP_DAYS[s] + 1, "D") for s in ship_method])
        act_ship = req_ship + rng.choice([-1, 0, 0, 0, 1, 2, 5],
                                         size=n_orders).astype("timedelta64[D]")

        lines = pd.DataFrame({
            "order_line_id": np.arange(line_id0, line_id0 + n_lines, dtype="int64"),
            "order_id": (order_id0 + o_row).astype("int64"),
            "line_number": (np.arange(n_lines) - np.repeat(
                np.cumsum(n_per_order) - n_per_order, n_per_order) + 1).astype("int16"),
            "order_date": dates,
            "date_key": (pd.DatetimeIndex(dates).year * 10000
                         + pd.DatetimeIndex(dates).month * 100
                         + pd.DatetimeIndex(dates).day).astype("int32"),
            "year_month_key": np.int32(ym_key),
            "customer_id": self.c_id[c_idx][o_row].astype("int32"),
            "product_id": self.p_id[p_idx].astype("int32"),
            "supplier_id": self.p_sup[p_idx].astype("int32"),
            "location_id": self.l_id[loc_idx][o_row].astype("int32"),
            "sales_rep_id": self.r_id[rep_idx][o_row].astype("int32"),
            "promotion_id": promo_id.astype("int32"),
            "channel_id": np.array([self.channel_ids[c] for c in channel])[o_row].astype("int16"),
            # Conformed plan keys, denormalised onto the line so plan-vs-actual
            # joins directly instead of snowflaking through the dimensions.
            "product_category_id": self.p_catkey[p_idx].astype("int32"),
            "country_id": self.l_countrykey[loc_idx][o_row].astype("int32"),
            "sales_channel": channel[o_row],
            "order_status": status[o_row],
            "quantity": quantity,
            "list_price": list_price.round(2),
            "unit_price": unit_price.round(2),
            "unit_cost": unit_cost.round(2),
            "discount_pct": discount_pct.round(6),
            "gross_sales": gross_sales.round(2),
            "discount_amount": discount_amount.round(2),
            "net_sales": net_sales.round(2),
            "cost": cost.round(2),
            "shipping_cost": shipping_cost.round(2),
            "tax_amount": tax_amount.round(2),
            "gross_profit": gross_profit.round(2),
            "currency_code": currency[o_row],
            "exchange_rate": fx_rate[o_row].round(8),
            "lead_time_days": np.round(self.p_lead[p_idx]
                                       + rng.normal(0, 3, n_lines)).clip(0, 120).astype("int16"),
        })
        lines["gross_margin_pct"] = (lines["gross_profit"] /
                                     lines["net_sales"].replace(0, np.nan)).round(6)

        # Local-currency mirrors of the reporting (USD) amounts.
        for col in ("gross_sales", "net_sales", "gross_profit", "cost", "discount_amount"):
            lines[f"{col}_lc"] = (lines[col] / lines["exchange_rate"]).round(2)

        orders = pd.DataFrame({
            "order_id": np.arange(order_id0, order_id0 + n_orders, dtype="int64"),
            "order_date": order_dates,
            "date_key": (pd.DatetimeIndex(order_dates).year * 10000
                         + pd.DatetimeIndex(order_dates).month * 100
                         + pd.DatetimeIndex(order_dates).day).astype("int32"),
            "year_month_key": np.int32(ym_key),
            "customer_id": self.c_id[c_idx].astype("int32"),
            "location_id": self.l_id[loc_idx].astype("int32"),
            "sales_rep_id": self.r_id[rep_idx].astype("int32"),
            "channel_id": np.array([self.channel_ids[c] for c in channel]).astype("int16"),
            "sales_channel": channel,
            "order_status": status,
            "payment_method": rng.choice(PAYMENT_METHODS, size=n_orders, p=PAYMENT_P),
            "ship_method": ship_method,
            "order_priority": rng.choice(PRIORITIES, size=n_orders, p=PRIORITY_P),
            "requested_ship_date": req_ship,
            "actual_ship_date": act_ship,
            "currency_code": order_currency,
            "exchange_rate": order_fx.round(8),
            "line_count": n_per_order.astype("int16"),
        })
        return orders, lines, line_id0 + n_lines

    def _product_p(self, month: dt.date) -> np.ndarray:
        """Sampling weights restricted to products on sale during this month.

        Without this gate a product would record sales before it launched,
        which breaks both realism and the launch/cannibalisation story.
        """
        cached = self._p_cache.get(month)
        if cached is not None:
            return cached
        month_end = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1) \
            - dt.timedelta(days=1)
        live = (self.p_launch <= np.datetime64(month_end)) & \
               (pd.isna(self.p_end) | (self.p_end >= np.datetime64(month)))

        # Age in months at THIS month, not at the as-of date.
        age = ((month.year - pd.DatetimeIndex(self.p_launch).year) * 12
               + (month.month - pd.DatetimeIndex(self.p_launch).month)).to_numpy()
        w = np.where(live, self.p_weight * _lifecycle_curve(age), 0.0)
        if w.sum() == 0:
            w = self.p_weight
        w = w / w.sum()
        self._p_cache[month] = w
        return w

    def _pick_by_region(self, regions: np.ndarray, pools: dict, n_all: int) -> np.ndarray:
        """Pick an index inside the customer's region 85% of the time."""
        out = self.rng.integers(0, n_all, size=len(regions))
        for region, pool in pools.items():
            if len(pool) == 0:
                continue
            mask = regions == region
            k = int(mask.sum())
            if k:
                local = pool[self.rng.integers(0, len(pool), size=k)]
                keep_local = self.rng.random(k) < 0.85
                out[mask] = np.where(keep_local, local, out[mask])
        return out

    def _assign_promotions(self, month, ctx, n_lines):
        """Attach an active, category-matching promotion to a share of lines."""
        rng = self.rng
        promo_id = np.zeros(n_lines, dtype="int64")
        promo_disc = np.zeros(n_lines)

        month_end = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        active = self.promo[(self.promo["start_date"] <= month_end)
                            & (self.promo["end_date"] >= month)]
        if active.empty:
            return promo_id, promo_disc

        ids = active["promotion_id"].to_numpy()
        discs = active["discount_pct"].to_numpy(dtype=float)
        targets = active["target_category"].to_numpy()

        for i in range(len(ids)):
            eligible = (targets[i] == "All Categories") | (ctx.category == targets[i])
            take = eligible & (promo_id == 0) & (rng.random(n_lines) < 0.30)
            promo_id[take] = ids[i]
            # Only part of the headline promo discount lands on any given line.
            promo_disc[take] = discs[i] * rng.uniform(0.25, 0.60, int(take.sum()))
        return promo_id, promo_disc

    def _inject_anomaly(self, orders: pd.DataFrame, lines: pd.DataFrame):
        cfg = self.s.event("sales_anomaly")
        month = self.s.event_month("sales_anomaly", "offset")
        if not cfg or month is None:
            return orders, lines

        target_amount = float(cfg["order_amount"])
        # Reuse a real strategic customer so the anomaly is drillable.
        cust = self.d["dim_customer"]
        strategic = cust[cust["is_strategic_customer"] == 1]
        row = strategic.iloc[len(strategic) // 2] if len(strategic) else cust.iloc[0]

        pool = lines[(lines["order_date"] >= np.datetime64(month))]
        template = pool.iloc[len(pool) // 2].copy() if len(pool) else lines.iloc[-1].copy()

        order_id = int(orders["order_id"].max()) + 1
        line_id0 = int(lines["order_line_id"].max()) + 1
        n_new = 14
        prod = self.d["dim_product"]
        picks = prod.nlargest(n_new, "list_price").reset_index(drop=True)

        anomaly_date = np.datetime64(min(
            month + dt.timedelta(days=17), self.s.timeline.as_of_date))
        discount_rate = 0.16
        gross_target = target_amount / (1 - discount_rate)
        per_line_value = gross_target / n_new
        qty = np.maximum((per_line_value / picks["list_price"].to_numpy()).round(), 1).astype("int32")
        unit_price = picks["list_price"].to_numpy()
        gross = unit_price * qty
        # Scale to land exactly on the configured order amount.
        gross = gross * (gross_target / gross.sum())
        unit_price = (gross / qty).round(2)
        gross = (unit_price * qty).round(2)
        disc = np.full(n_new, discount_rate)
        net = (gross * (1 - disc)).round(2)
        unit_cost = picks["standard_cost"].to_numpy() * (unit_price / picks["list_price"].to_numpy())
        cost = (unit_cost * qty).round(2)
        ship = (net * 0.012).round(2)

        new_lines = pd.DataFrame({
            "order_line_id": np.arange(line_id0, line_id0 + n_new, dtype="int64"),
            "order_id": order_id, "line_number": np.arange(1, n_new + 1, dtype="int16"),
            "order_date": anomaly_date,
            "date_key": int(pd.Timestamp(anomaly_date).strftime("%Y%m%d")),
            "year_month_key": np.int32(month.year * 100 + month.month),
            "customer_id": np.int32(row["customer_id"]),
            "product_id": picks["product_id"].to_numpy().astype("int32"),
            "supplier_id": picks["supplier_id"].to_numpy().astype("int32"),
            "location_id": np.int32(row["primary_location_id"]),
            "sales_rep_id": np.int32(row["account_manager_id"]),
            "promotion_id": np.int32(0), "channel_id": np.int16(1),
            "product_category_id": picks["product_category_id"].to_numpy().astype("int32"),
            "country_id": np.int32(
                self.d["dim_location"].set_index("location_id")
                .loc[int(row["primary_location_id"]), "country_id"]),
            "sales_channel": "Direct Sales", "order_status": "Completed",
            "quantity": qty,
            "list_price": picks["list_price"].to_numpy().round(2),
            "unit_price": unit_price, "unit_cost": unit_cost.round(2),
            "discount_pct": disc, "gross_sales": gross,
            "discount_amount": (gross - net).round(2), "net_sales": net,
            "cost": cost, "shipping_cost": ship,
            "tax_amount": (net * 0.07).round(2),
            "gross_profit": (net - cost - ship).round(2),
            "currency_code": "USD", "exchange_rate": 1.0,
            "lead_time_days": np.int16(21),
        })
        new_lines["gross_margin_pct"] = (new_lines["gross_profit"] / new_lines["net_sales"]).round(6)
        for col in ("gross_sales", "net_sales", "gross_profit", "cost", "discount_amount"):
            new_lines[f"{col}_lc"] = new_lines[col]

        new_order = pd.DataFrame([{
            "order_id": order_id, "order_date": anomaly_date,
            "date_key": int(pd.Timestamp(anomaly_date).strftime("%Y%m%d")),
            "year_month_key": np.int32(month.year * 100 + month.month),
            "customer_id": np.int32(row["customer_id"]),
            "location_id": np.int32(row["primary_location_id"]),
            "sales_rep_id": np.int32(row["account_manager_id"]),
            "channel_id": np.int16(1), "sales_channel": "Direct Sales",
            "order_status": "Completed", "payment_method": "Wire Transfer",
            "ship_method": "Freight", "order_priority": "Critical",
            "requested_ship_date": anomaly_date + np.timedelta64(21, "D"),
            "actual_ship_date": anomaly_date + np.timedelta64(24, "D"),
            "currency_code": "USD", "exchange_rate": 1.0,
            "line_count": np.int16(n_new),
        }])
        return (pd.concat([orders, new_order], ignore_index=True),
                pd.concat([lines, new_lines], ignore_index=True))

    def _reconcile_headers(self, orders: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
        agg = lines.groupby("order_id").agg(
            total_order_amount=("net_sales", "sum"),
            total_gross_amount=("gross_sales", "sum"),
            total_discount_amount=("discount_amount", "sum"),
            total_cost_amount=("cost", "sum"),
            total_tax_amount=("tax_amount", "sum"),
            total_gross_profit=("gross_profit", "sum"),
            total_quantity=("quantity", "sum"),
            line_count_actual=("order_line_id", "size"))
        out = orders.merge(agg, on="order_id", how="left")
        out["line_count"] = out["line_count_actual"].astype("int16")
        money = ["total_order_amount", "total_gross_amount", "total_discount_amount",
                 "total_cost_amount", "total_tax_amount", "total_gross_profit"]
        out[money] = out[money].round(2)
        return out.drop(columns=["line_count_actual"])

    def _inject_data_quality(self, orders: pd.DataFrame, lines: pd.DataFrame):
        """Controlled, documented dirt so a data-quality demo has something to find."""
        dq = self.s.baseline.get("data_quality", {})
        rng = self.rng

        pct = float(dq.get("null_ship_date_pct", 0))
        if pct > 0:
            mask = rng.random(len(orders)) < pct
            orders.loc[mask, "actual_ship_date"] = pd.NaT

        n_dup = int(dq.get("duplicate_order_count", 0))
        if n_dup > 0:
            src = orders.sample(n=min(n_dup, len(orders)), random_state=self.s.seed)
            dup = src.copy()
            dup["order_id"] = np.arange(int(orders["order_id"].max()) + 1,
                                        int(orders["order_id"].max()) + 1 + len(dup))
            dup_lines = lines[lines["order_id"].isin(src["order_id"])].copy()
            id_map = dict(zip(src["order_id"], dup["order_id"]))
            dup_lines["order_id"] = dup_lines["order_id"].map(id_map)
            dup_lines["order_line_id"] = np.arange(
                int(lines["order_line_id"].max()) + 1,
                int(lines["order_line_id"].max()) + 1 + len(dup_lines))
            orders = pd.concat([orders, dup], ignore_index=True)
            lines = pd.concat([lines, dup_lines], ignore_index=True)
        return orders, lines
