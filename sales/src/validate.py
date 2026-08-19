#!/usr/bin/env python3
"""Post-generation checks.

Two families of check:

  INTEGRITY  - the dataset is internally consistent (keys resolve, headers
               tie to lines, no negative money, no sales before launch).
  NARRATIVE  - each enabled event is actually VISIBLE in the aggregates.

The narrative checks matter most. Random noise routinely swamps a planted
signal, and the failure mode is discovering it live in front of an audience
rather than here.

  python3 src/validate.py --tier small
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apexconfig import PROJECT_ROOT, load_scenario


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, group: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((group, name, bool(ok), detail))

    @property
    def failed(self) -> list[tuple]:
        return [r for r in self.rows if not r[2]]

    def render(self) -> str:
        out, current = [], None
        for group, name, ok, detail in self.rows:
            if group != current:
                out.append(f"\n{group}")
                current = group
            mark = "PASS" if ok else "FAIL"
            out.append(f"  [{mark}] {name:<52s} {detail}")
        n = len(self.rows)
        out.append(f"\n{n - len(self.failed)}/{n} checks passed")
        return "\n".join(out)


def load(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted(data_dir.glob("*.parquet"))}


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


# --------------------------------------------------------------- integrity --
def check_integrity(t: dict, s, r: Report) -> None:
    g = "INTEGRITY"
    lines, orders = t["fact_sales_order_line"], t["fact_sales_order"]

    for fk, dim, key in [
        ("customer_id", "dim_customer", "customer_id"),
        ("product_id", "dim_product", "product_id"),
        ("location_id", "dim_location", "location_id"),
        ("sales_rep_id", "dim_sales_rep", "sales_rep_id"),
        ("supplier_id", "dim_supplier", "supplier_id"),
        ("promotion_id", "dim_promotion", "promotion_id"),
        ("product_category_id", "dim_product_category", "product_category_id"),
        ("country_id", "dim_country", "country_id"),
    ]:
        orphans = int((~lines[fk].isin(t[dim][key])).sum())
        r.check(g, f"order lines: {fk} resolves to {dim}", orphans == 0,
                f"{orphans:,} orphans")

    missing = int((~lines["order_id"].isin(orders["order_id"])).sum())
    r.check(g, "order lines: order_id resolves to header", missing == 0,
            f"{missing:,} orphans")

    dk = int((~lines["date_key"].isin(t["dim_date"]["date_key"])).sum())
    r.check(g, "order lines: date_key resolves to dim_date", dk == 0, f"{dk:,} orphans")

    agg = lines.groupby("order_id")["net_sales"].sum().round(2)
    hdr = orders.set_index("order_id")["total_order_amount"].round(2)
    joined = pd.concat([agg, hdr], axis=1, join="inner")
    worst = float((joined.iloc[:, 0] - joined.iloc[:, 1]).abs().max())
    r.check(g, "order header total ties to sum of its lines", worst < 0.011,
            f"max delta ${worst:.4f}")

    for col in ("net_sales", "gross_sales", "quantity", "cost"):
        neg = int((lines[col] < 0).sum())
        r.check(g, f"order lines: no negative {col}", neg == 0, f"{neg:,} rows")

    dup = int(lines["order_line_id"].duplicated().sum())
    r.check(g, "order_line_id is unique", dup == 0, f"{dup:,} dupes")

    launch = t["dim_product"].set_index("product_id")["product_launch_date"]
    lm = lines[["product_id", "order_date"]].copy()
    lm["launch"] = lm["product_id"].map(launch)
    early = int((pd.to_datetime(lm["order_date"]) <
                 pd.to_datetime(lm["launch"]).dt.to_period("M").dt.start_time).sum())
    r.check(g, "no sales before the product launch month", early == 0, f"{early:,} rows")

    late = int((pd.to_datetime(lines["order_date"]).dt.date > s.timeline.as_of_date).sum())
    r.check(g, "no actuals after the as-of date", late == 0, f"{late:,} rows")

    if len(t.get("fact_returns", [])):
        orphan_r = int((~t["fact_returns"]["order_line_id"]
                        .isin(lines["order_line_id"])).sum())
        r.check(g, "returns: order_line_id resolves to a sold line", orphan_r == 0,
                f"{orphan_r:,} orphans")

    # Plan facts must relate to the SAME conformed dimensions as the sales
    # fact, or plan-vs-actual needs a bridge table in Power BI.
    for plan in ("fact_budget", "fact_forecast"):
        df = t.get(plan)
        if df is None or not len(df):
            continue
        for fk, dim in (("country_id", "dim_country"),
                        ("product_category_id", "dim_product_category"),
                        ("channel_id", "dim_channel")):
            bad = int((~df[fk].isin(t[dim][fk])).sum())
            r.check(g, f"{plan}: {fk} resolves to {dim}", bad == 0, f"{bad:,} orphans")
        r.check(g, f"{plan}: shares conformed keys with the sales fact",
                {"country_id", "product_category_id", "channel_id"} <= set(df.columns),
                "country_id + product_category_id + channel_id")

    fc = t.get("fact_forecast")
    if fc is not None and len(fc):
        as_of_key = s.timeline.as_of_date.year * 100 + s.timeline.as_of_date.month
        past = int((fc["year_month_key"] <= as_of_key).sum())
        r.check(g, "forecast covers only future months", past == 0, f"{past:,} rows")


# --------------------------------------------------------------- narrative --
def _enrich(t: dict) -> pd.DataFrame:
    lines = t["fact_sales_order_line"]
    return (lines
            .merge(t["dim_product"][["product_id", "category", "subcategory",
                                     "product_name"]], on="product_id")
            .merge(t["dim_supplier"][["supplier_id", "supplier_group"]], on="supplier_id")
            .merge(t["dim_location"][["location_id", "region", "country"]], on="location_id")
            .merge(t["dim_customer"][["customer_id", "customer_name"]], on="customer_id"))


def shift_key(ym_key: int, months: int) -> int:
    """Offset a YYYYMM key by N months.

    Plain integer arithmetic on these keys is wrong: 202601 - 3 is 202598,
    which is not a month. Every relative window in the checks goes through here.
    """
    total = (ym_key // 100) * 12 + (ym_key % 100 - 1) + months
    y, m = divmod(total, 12)
    return y * 100 + m + 1


def _window_keys(s, name, start_key="start_offset", end_key="end_offset"):
    w = s.event_window(name, start_key, end_key)
    if w is None:
        return None
    return (w[0].year * 100 + w[0].month, min(w[1].year * 100 + w[1].month,
            s.timeline.as_of_date.year * 100 + s.timeline.as_of_date.month))


def _shortage_skus(t: dict, s) -> set:
    """Recreate the event engine's SKU selection without generating data."""
    cfg = s.event("inventory_shortage")
    if not cfg:
        return set()
    p = t["dim_product"]
    pool = p[(p["subcategory"] == "Laptops") & (p["is_discontinued"] == 0)]
    return set(pool.nlargest(int(cfg["affected_sku_count"]),
                             "demand_weight")["product_id"].astype(int))


def check_narrative(t: dict, s, r: Report) -> None:
    g = "NARRATIVE"
    L = _enrich(t)
    as_of = s.timeline.as_of_date
    cur_year, cur_month = as_of.year, as_of.month
    ytd = L[(L["year_month_key"] // 100 == cur_year)]
    pytd = L[(L["year_month_key"] // 100 == cur_year - 1)
             & (L["year_month_key"] % 100 <= cur_month)]

    # -- headline -----------------------------------------------------------
    rev_yoy = ytd["net_sales"].sum() / pytd["net_sales"].sum() - 1
    prof_yoy = ytd["gross_profit"].sum() / pytd["gross_profit"].sum() - 1
    m_now = ytd["gross_profit"].sum() / ytd["net_sales"].sum()
    m_pri = pytd["gross_profit"].sum() / pytd["net_sales"].sum()
    r.check(g, "headline: revenue grows YTD vs PYTD", rev_yoy > 0.02, pct(rev_yoy))
    r.check(g, "headline: profit declines YTD vs PYTD", prof_yoy < -0.02, pct(prof_yoy))
    r.check(g, "headline: margin declines by at least 1.0 pt",
            (m_now - m_pri) < -0.010, f"{(m_now - m_pri) * 100:+.1f} pts")

    # -- E1 supplier cost shock ---------------------------------------------
    cfg = s.event("supplier_cost_shock")
    if cfg:
        w = _window_keys(s, "supplier_cost_shock")
        grp = cfg["supplier_group"]
        hit = L[L["supplier_group"] == grp]
        pre = hit[hit["year_month_key"] < w[0]]
        post = hit[(hit["year_month_key"] >= w[0]) & (hit["year_month_key"] <= w[1])]
        uc_pre = pre["cost"].sum() / pre["quantity"].sum()
        uc_post = post["cost"].sum() / post["quantity"].sum()
        target = float(cfg["cost_increase_pct"])

        # Compare like with like: a blended unit cost also moves when the
        # product mix moves, so measure the median change PER PRODUCT.
        def median_unit_cost_change(df):
            pre_p = (df[df["year_month_key"] < w[0]].groupby("product_id")
                     .apply(lambda x: x["cost"].sum() / x["quantity"].sum(),
                            include_groups=False))
            post_p = (df[(df["year_month_key"] >= w[0])
                         & (df["year_month_key"] <= w[1])].groupby("product_id")
                      .apply(lambda x: x["cost"].sum() / x["quantity"].sum(),
                             include_groups=False))
            both = pd.concat([pre_p, post_p], axis=1, join="inner")
            return float((both.iloc[:, 1] / both.iloc[:, 0] - 1).median())

        shocked = median_unit_cost_change(hit)
        control = median_unit_cost_change(L[L["supplier_group"] != grp])
        r.check(g, f"E1 {grp} per-product unit cost rises ~{target:.0%}",
                abs(shocked - target) < max(target * 0.5, 0.03), pct(shocked))
        r.check(g, "E1 unshocked suppliers' per-product unit cost is stable",
                abs(control) < 0.04, pct(control))
        share = post["cost"].sum() / L[(L["year_month_key"] >= w[0])
                                       & (L["year_month_key"] <= w[1])]["cost"].sum()
        r.check(g, "E1 shocked group is material (>15% of COGS)", share > 0.15,
                f"{share:.0%} of COGS")

    # -- E2 promotion --------------------------------------------------------
    cfg = s.event("promotion_surge")
    if cfg:
        w = _window_keys(s, "promotion_surge")
        c = L[L["category"] == cfg["category"]]
        during = c[(c["year_month_key"] >= w[0]) & (c["year_month_key"] <= w[1])]
        before = c[(c["year_month_key"] >= shift_key(w[0], -3)) & (c["year_month_key"] < w[0])]
        u = (during["quantity"].sum() / max(during["year_month_key"].nunique(), 1)) / \
            (before["quantity"].sum() / max(before["year_month_key"].nunique(), 1)) - 1
        d_now = during["discount_amount"].sum() / during["gross_sales"].sum()
        d_pre = before["discount_amount"].sum() / before["gross_sales"].sum()
        m_d = during["gross_profit"].sum() / during["net_sales"].sum()
        m_b = before["gross_profit"].sum() / before["net_sales"].sum()
        r.check(g, f"E2 {cfg['category']} units lift during promo", u > 0.10, pct(u))
        r.check(g, "E2 discount rate rises during promo", (d_now - d_pre) > 0.02,
                f"{(d_now - d_pre) * 100:+.1f} pts")
        r.check(g, "E2 margin falls at least 3 pts during promo",
                (m_d - m_b) < -0.03, f"{(m_d - m_b) * 100:+.1f} pts")

    # -- E3 launch / cannibalisation ----------------------------------------
    cfg = s.event("product_launch")
    lm = s.event_month("product_launch", "launch_offset")
    if cfg and lm:
        key = lm.year * 100 + lm.month
        new, old = cfg["new_product"], cfg["incumbent_product"]
        n_post = L[(L["product_name"] == new) & (L["year_month_key"] >= key)]["quantity"].sum()
        n_pre = L[(L["product_name"] == new) & (L["year_month_key"] < key)]["quantity"].sum()
        r.check(g, f"E3 {new} has no sales before launch", n_pre == 0, f"{int(n_pre)} units")
        r.check(g, f"E3 {new} sells after launch", n_post > 0, f"{int(n_post):,} units")

        def unit_rate_change(df):
            post = df[df["year_month_key"] >= key]
            pre = df[(df["year_month_key"] < key)
                     & (df["year_month_key"] >= shift_key(key, -4))]
            rp = post["quantity"].sum() / max(post["year_month_key"].nunique(), 1)
            rb = pre["quantity"].sum() / max(pre["year_month_key"].nunique(), 1)
            return rp / rb - 1 if rb else 0.0

        incumbent = unit_rate_change(L[L["product_name"] == old])
        # Control group: other laptops that are neither the new product nor the
        # incumbent. They sit in the same promotion and the same seasonality,
        # so the gap is the cannibalisation and nothing else.
        sub = t["dim_product"].loc[t["dim_product"]["product_name"] == old,
                                   "subcategory"].iloc[0]
        peers = L[(L["subcategory"] == sub)
                  & (~L["product_name"].isin([new, old]))]
        control = unit_rate_change(peers)
        r.check(g, f"E3 {old} declines after the launch", incumbent < 0, pct(incumbent))
        r.check(g, f"E3 {old} underperforms peer {sub.lower()} (cannibalisation)",
                incumbent - control < -0.08,
                f"{pct(incumbent)} vs peers {pct(control)} "
                f"(gap {(incumbent - control) * 100:+.0f} pts)")

    # -- E4 regional erosion -------------------------------------------------
    cfg = s.event("region_margin_erosion")
    if cfg:
        w = _window_keys(s, "region_margin_erosion")
        sel = L[(L["region"] == cfg["region"]) & (L["subcategory"] == cfg["subcategory"])]
        during = sel[(sel["year_month_key"] >= w[0]) & (sel["year_month_key"] <= w[1])]
        before = sel[(sel["year_month_key"] >= shift_key(w[0], -3)) & (sel["year_month_key"] < w[0])]
        m_d = during["gross_profit"].sum() / during["net_sales"].sum()
        m_b = before["gross_profit"].sum() / before["net_sales"].sum()
        r.check(g, f"E4 {cfg['region']} {cfg['subcategory']} margin erodes",
                (m_d - m_b) < -0.03, f"{(m_d - m_b) * 100:+.1f} pts")

        # The named region must be the worst profit contributor YoY.
        pr = (ytd.groupby("region")["gross_profit"].sum()
              - pytd.groupby("region")["gross_profit"].sum()).sort_values()
        worst = pr.index[0]
        r.check(g, f"E4 {cfg['region']} is the largest profit decline by region",
                worst == cfg["region"], f"worst={worst} (${pr.iloc[0] / 1e6:,.1f}M)")

    # -- E5 customer contraction --------------------------------------------
    cfg = s.event("customer_contraction")
    if cfg:
        w = _window_keys(s, "customer_contraction")
        c = L[L["customer_name"] == cfg["customer_name"]]
        r.check(g, f"E5 {cfg['customer_name']} exists in the data", len(c) > 0,
                f"{len(c):,} lines")
        if len(c):
            share = c["net_sales"].sum() / L["net_sales"].sum()
            target = float(cfg["revenue_share"])
            r.check(g, f"E5 customer is ~{target:.0%} of revenue",
                    abs(share - target) < target * 0.5, f"{share:.2%}")
            # Measure SHARE of company, not absolute: a company-wide promotion
            # running in the same months would otherwise mask the contraction.
            def share(lo, hi, col, how):
                cust = c[(c["year_month_key"] >= lo) & (c["year_month_key"] <= hi)]
                allc = L[(L["year_month_key"] >= lo) & (L["year_month_key"] <= hi)]
                f = (lambda x: x[col].sum()) if how == "sum" else \
                    (lambda x: x[col].nunique())
                return f(cust) / f(allc)

            ord_pre, ord_post = share(shift_key(w[0], -6), shift_key(w[0], -1),
                                      "order_id", "nunique"), \
                share(w[0], w[1], "order_id", "nunique")
            r.check(g, "E5 the customer's order SHARE contracts",
                    ord_post / ord_pre - 1 < -0.10,
                    f"{ord_pre:.2%} -> {ord_post:.2%} ({pct(ord_post / ord_pre - 1)})")

            # Peer control: other strategic enterprise accounts sit in the same
            # promotions and seasonality, so the gap isolates the contraction.
            peers = set(t["dim_customer"][
                (t["dim_customer"]["is_strategic_customer"] == 1)
                & (t["dim_customer"]["customer_name"] != cfg["customer_name"])
            ]["customer_name"])
            p_lines = L[L["customer_name"].isin(peers)]

            def growth(df):
                pre_rows = df[(df["year_month_key"] >= shift_key(w[0], -6))
                              & (df["year_month_key"] < w[0])]
                post_rows = df[(df["year_month_key"] >= w[0])
                               & (df["year_month_key"] <= w[1])]
                n_pre = max(pre_rows["year_month_key"].nunique(), 1)
                n_post = max(post_rows["year_month_key"].nunique(), 1)
                return ((post_rows["net_sales"].sum() / n_post)
                        / (pre_rows["net_sales"].sum() / n_pre) - 1)

            gap = growth(c) - growth(p_lines)
            r.check(g, "E5 the customer underperforms peer strategic accounts",
                    gap < -0.10,
                    f"{pct(growth(c))} vs peers {pct(growth(p_lines))} (gap {gap * 100:+.0f} pts)")

    # -- E6 inventory shortage ----------------------------------------------
    cfg = s.event("inventory_shortage")
    inv = t.get("fact_inventory")
    if cfg and inv is not None and len(inv):
        w = _window_keys(s, "inventory_shortage")
        # Only the affected SKUs are supposed to move; averaging over the whole
        # grid dilutes the signal below the noise floor.
        skus = _shortage_skus(t, s)
        aff = inv[inv["product_id"].isin(skus)] if skus else inv
        during = aff[(aff["year_month_key"] >= w[0]) & (aff["year_month_key"] <= w[1])]
        before = aff[aff["year_month_key"] < w[0]]
        others = inv[~inv["product_id"].isin(skus)] if skus else inv.iloc[0:0]
        if len(others):
            o_d = others[(others["year_month_key"] >= w[0])
                         & (others["year_month_key"] <= w[1])]["stockout_flag"].mean()
            r.check(g, "E6 unaffected SKUs do NOT stock out", o_d < 0.01, f"{o_d:.2%}")
        so_d, so_b = during["stockout_flag"].mean(), before["stockout_flag"].mean()
        r.check(g, "E6 stockout rate spikes during the shortage", so_d > max(so_b * 3, 0.01),
                f"{so_b:.2%} -> {so_d:.2%}")
        r.check(g, "E6 lost sales are recorded", during["lost_sales_units"].sum() > 0,
                f"{during['lost_sales_units'].sum():,.0f} units")
        dos_d, dos_b = during["days_of_supply"].mean(), before["days_of_supply"].mean()
        r.check(g, "E6 days of supply falls", dos_d < dos_b * 0.9,
                f"{dos_b:.1f} -> {dos_d:.1f} days")

    # -- E7 quality failure --------------------------------------------------
    cfg = s.event("quality_failure")
    ret = t.get("fact_returns")
    if cfg and ret is not None and len(ret):
        w = _window_keys(s, "quality_failure")
        sup = t["dim_supplier"][["supplier_id", "supplier_group"]]
        rr = ret.merge(sup, on="supplier_id")
        grp = (s.event("supplier_cost_shock") or {}).get("supplier_group")
        sold = L.groupby(["year_month_key", "supplier_group"])["quantity"].sum()
        retd = rr.groupby(["year_month_key", "supplier_group"])["return_quantity"].sum()
        rate = (retd / sold).dropna().reset_index(name="rate")
        during = rate[(rate["year_month_key"] >= w[0]) & (rate["year_month_key"] <= w[1])
                      & (rate["supplier_group"] == grp)]["rate"].mean()
        before = rate[(rate["year_month_key"] < w[0])
                      & (rate["supplier_group"] == grp)]["rate"].mean()
        r.check(g, f"E7 {grp} return rate rises", during > before * 1.6,
                f"{before:.2%} -> {during:.2%}")

        perf = t.get("fact_supplier_performance")
        if perf is not None and len(perf):
            p = perf.merge(sup, on="supplier_id")
            p = p[p["supplier_group"] == grp]
            d_d = p[(p["year_month_key"] >= w[0])
                    & (p["year_month_key"] <= w[1])]["defect_rate"].mean()
            d_b = p[p["year_month_key"] < w[0]]["defect_rate"].mean()
            r.check(g, "E7 supplier defect rate rises", d_d > d_b * 1.6,
                    f"{d_b:.2%} -> {d_d:.2%}")

    # -- E8 anomaly ----------------------------------------------------------
    cfg = s.event("sales_anomaly")
    am = s.event_month("sales_anomaly", "offset")
    if cfg and am:
        by_order = L.groupby("order_id")["net_sales"].sum()
        top = by_order.max()
        p999 = by_order.quantile(0.999)
        target = float(cfg["order_amount"])
        r.check(g, "E8 anomalous order is close to its configured value",
                abs(top / target - 1) < 0.05, f"${top / 1e6:.2f}M vs ${target / 1e6:.2f}M")
        r.check(g, "E8 anomaly is a clear outlier (>10x p99.9)", top > p999 * 10,
                f"{top / p999:.0f}x p99.9")

    # -- E9/E10 forecast -----------------------------------------------------
    fc = t.get("fact_forecast")
    if fc is not None and len(fc):
        by_v = fc.groupby("forecast_version")[["forecast_sales", "forecast_profit"]].sum()
        have = set(by_v.index)
        r.check(g, "E9 all forecast versions present",
                {"Original Budget", "Latest Forecast", "Recovery Scenario"} <= have,
                ", ".join(sorted(have)))
        if {"Original Budget", "Latest Forecast"} <= have:
            gap = by_v.loc["Latest Forecast", "forecast_profit"] - \
                  by_v.loc["Original Budget", "forecast_profit"]
            r.check(g, "E9 latest forecast is below original budget on profit",
                    gap < 0, f"${gap / 1e6:,.1f}M")
        if {"Latest Forecast", "Recovery Scenario"} <= have:
            rec = by_v.loc["Recovery Scenario", "forecast_profit"] - \
                  by_v.loc["Latest Forecast", "forecast_profit"]
            r.check(g, "E10 recovery scenario improves on latest forecast",
                    rec > 0, f"+${rec / 1e6:,.1f}M")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    data_dir = Path(args.data) if args.data else PROJECT_ROOT / "data" / args.tier
    if not data_dir.exists():
        print(f"no data at {data_dir}; run generate.py first")
        return 2

    t = load(data_dir)
    r = Report()
    check_integrity(t, s, r)
    check_narrative(t, s, r)
    print(r.render())
    return 1 if r.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
