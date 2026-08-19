#!/usr/bin/env python3
"""Post-generation checks.

Two families:

  INTEGRITY - the dataset is internally consistent (keys resolve, the
              inventory balance closes, no negative money, dimensions agree
              with the facts they were derived from).
  NARRATIVE - each enabled event is actually VISIBLE in the aggregates, at
              the magnitude docs/EVENTS.md claims.

The narrative checks are the ones that matter. Random noise routinely swamps a
planted signal, and the failure mode is discovering that live in front of an
audience rather than here.

  python3 src/validate.py --tier small
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mgiconfig import PROJECT_ROOT, load_scenario


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, group, name, ok, detail=""):
        self.rows.append((group, name, bool(ok), detail))

    def between(self, group, name, value, lo, hi, fmt="{:.1%}"):
        ok = value is not None and not pd.isna(value) and lo <= value <= hi
        shown = "n/a" if value is None or pd.isna(value) else fmt.format(value)
        self.check(group, name, ok, f"{shown}  (want {fmt.format(lo)}..{fmt.format(hi)})")

    @property
    def failed(self):
        return [r for r in self.rows if not r[2]]

    def render(self):
        out, cur = [], None
        for g, n, ok, d in self.rows:
            if g != cur:
                out.append(f"\n{g}")
                cur = g
            out.append(f"  [{'PASS' if ok else 'FAIL'}] {n:<44s} {d}")
        out.append(f"\n{len(self.rows) - len(self.failed)}/{len(self.rows)} checks passed")
        return "\n".join(out)


def load(d: Path):
    return {p.stem: pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))}


def run(s, t, r: Report):
    asof = pd.Timestamp(s.timeline.as_of_date)
    sup, prd, inv = t["dim_supplier"], t["dim_product"], t["fact_inventory_snapshot"]
    dl, po, ship = t["fact_supplier_delivery"], t["fact_purchase_order"], t["fact_shipment"]
    fc, sol = t["fact_forecast"], t["fact_sales_order_line"]

    cur = inv[(inv.snapshot_grain == "D") & (inv.snapshot_date > asof - pd.Timedelta(days=90))]
    ly = inv[(inv.snapshot_grain == "W")
             & inv.snapshot_date.between(asof - pd.Timedelta(days=455), asof - pd.Timedelta(days=365))]

    # ---------------- INTEGRITY ----------------
    g = "INTEGRITY - referential"
    r.check(g, "product -> primary supplier resolves",
            prd.primary_supplier_id.isin(sup.supplier_id).all())
    r.check(g, "product -> secondary supplier resolves",
            prd.secondary_supplier_id.isin(sup.supplier_id).all())
    r.check(g, "no NULL foreign keys on dim_product",
            prd[["primary_supplier_id", "secondary_supplier_id", "product_category_id"]].notna().all().all())
    r.check(g, "inventory -> product resolves", inv.product_id.isin(prd.product_id).all())
    r.check(g, "inventory -> location resolves", inv.location_id.isin(t["dim_location"].location_id).all())
    r.check(g, "delivery -> PO line resolves", dl.po_line_id.isin(po.po_line_id).all())
    r.check(g, "shipment -> order resolves", ship.order_id.isin(sol.order_id).all())
    r.check(g, "forecast -> product resolves", fc.product_id.isin(prd.product_id).all())

    g = "INTEGRITY - business logic"
    r.check(g, "no negative on-hand", (inv.on_hand_qty >= -1e-6).all())
    r.check(g, "no negative money",
            (inv.inventory_value >= -1e-6).all() and (sol.net_revenue >= -1e-6).all())
    r.check(g, "received never exceeds ordered", (po.received_qty <= po.ordered_qty + 1e-6).all())
    r.check(g, "accepted + rejected == received",
            np.allclose(dl.accepted_qty + dl.rejected_qty, dl.received_qty, atol=1e-2))
    r.check(g, "cancelled PO lines received nothing",
            (po.loc[po.status == "Cancelled", "received_qty"] == 0).all())
    r.check(g, "lateness measured against PROMISED not requested",
            bool((dl.is_on_time == (pd.to_datetime(dl.actual_receipt_date)
                                    <= pd.to_datetime(dl.promised_date))).all()))
    r.check(g, "OTIF = on-time AND in-full",
            bool((ship.is_otif == (ship.is_on_time & ship.is_in_full)).all()))
    r.check(g, "both snapshot grains present", set(inv.snapshot_grain.unique()) == {"D", "W"})

    d = inv[inv.snapshot_grain == "D"].sort_values(["product_id", "location_id", "snapshot_date"])
    k = d.groupby(["product_id", "location_id"])
    resid = (k.on_hand_qty.shift(1) + d.receipt_qty - d.shipped_qty - d.on_hand_qty).abs()
    r.check(g, "inventory balance equation closes", np.nanmax(resid) < 0.01,
            f"max residual {np.nanmax(resid):.4f} units")

    g = "INTEGRITY - derived dimensions"
    d90 = dl[pd.to_datetime(dl.actual_receipt_date) > asof - pd.Timedelta(days=90)]
    fact_ot = d90.groupby("supplier_id").is_on_time.mean()
    dim_ot = sup.set_index("supplier_id").on_time_rate
    both = fact_ot.index.intersection(dim_ot.dropna().index)
    r.check(g, "dim_supplier.on_time_rate ties to the fact",
            np.allclose(dim_ot[both], fact_ot[both], atol=1e-3), f"{len(both)} suppliers")
    a_share = (prd[prd.abc_class == "A"].annual_demand_value.sum()
               / prd.annual_demand_value.sum())
    r.between(g, "ABC is a real Pareto (A holds ~80% value)", a_share, 0.74, 0.86)
    r.check(g, "every SKU classified",
            prd.abc_class.isin(list("ABC")).all() and prd.xyz_class.isin(list("XYZ")).all())

    # ---------------- NARRATIVE ----------------
    def mid(x):
        return pd.to_datetime(x).dt.to_period("M").dt.to_timestamp().dt.date

    # Supplier events are applied on the month an order is FULFILLED, so they
    # must be measured on that basis too. Grouping by po_date smears a
    # three-month disruption across the lead time either side of it and reads
    # back a diluted number that no amount of retuning will fix.
    # Group on the month the model resolved supplier events against.
    dl2 = dl.assign(m=dl.fulfilment_month_key)
    po2 = po.assign(m=po.fulfilment_month_key)

    e = s.event("supplier_disruption")
    if e:
        g = "NARRATIVE - Event 1 supplier disruption"
        w = s.event_window("supplier_disruption")
        sid = int(sup.loc[sup.supplier_master_id == e["supplier_master_id"], "supplier_id"].iloc[0])
        k0, k1 = w[0].year * 100 + w[0].month, w[1].year * 100 + w[1].month
        before = dl2[(dl2.supplier_id == sid) & (dl2.m < k0)]
        during = dl2[(dl2.supplier_id == sid) & (dl2.m >= k0) & (dl2.m <= k1)]
        r.between(g, "on-time before", before.is_on_time.mean(),
                  e["on_time_rate_from"] - 0.03, e["on_time_rate_from"] + 0.03)
        r.between(g, "on-time during", during.is_on_time.mean(),
                  e["on_time_rate_to"] - 0.03, e["on_time_rate_to"] + 0.03)
        lb = po2[(po2.supplier_id == sid) & (po2.m < k0)].actual_lead_time_days.mean()
        ld = po2[(po2.supplier_id == sid) & (po2.m >= k0) & (po2.m <= k1)].actual_lead_time_days.mean()
        r.between(g, "lead time before", lb, e["lead_time_days_from"] - 2,
                  e["lead_time_days_from"] + 2, "{:.1f}d")
        r.between(g, "lead time during", ld, e["lead_time_days_to"] - 2,
                  e["lead_time_days_to"] + 2, "{:.1f}d")
        s104 = set(prd.loc[prd.primary_supplier_id == sid, "product_id"])
        so_a = cur[cur.product_id.isin(s104) & (cur.demand_qty > 0)].stockout_flag.mean()
        so_b = cur[~cur.product_id.isin(s104) & (cur.demand_qty > 0)].stockout_flag.mean()
        r.check(g, "its SKUs stock out more than the rest", so_a > so_b,
                f"{so_a:.1%} vs {so_b:.1%}")

    e = s.event("quality_failure")
    if e:
        g = "NARRATIVE - Event 5 quality failure"
        w = s.event_window("quality_failure")
        sid = int(sup.loc[sup.supplier_master_id == e["supplier_master_id"], "supplier_id"].iloc[0])
        k0 = w[0].year * 100 + w[0].month
        t90 = dl2[(dl2.supplier_id == sid)
                  & (pd.to_datetime(dl2.actual_receipt_date) > asof - pd.Timedelta(days=90))]
        r.between(g, "defect before", dl2[(dl2.supplier_id == sid) & (dl2.m < k0)].defect_rate.mean(),
                  e["defect_rate_from"] - 0.005, e["defect_rate_from"] + 0.005)
        r.between(g, "defect trailing 90d", t90.defect_rate.mean(),
                  e["defect_rate_to"] - 0.007, e["defect_rate_to"] + 0.007)
        r.between(g, "rejected share of received",
                  t90.rejected_qty.sum() / max(t90.received_qty.sum(), 1e-9),
                  float(e["rejected_receipt_pct"]) - 0.02, 0.30)

    e = s.event("port_disruption")
    if e:
        g = "NARRATIVE - Event 6 port disruption"
        w = s.event_window("port_disruption")
        ap = sup.loc[sup.region == e["origin_region"], "supplier_id"]
        k0, k1 = w[0].year * 100 + w[0].month, w[1].year * 100 + w[1].month
        x = po2[po2.supplier_id.isin(ap) & (po2.m < k0)].actual_lead_time_days.mean()
        y = po2[po2.supplier_id.isin(ap) & (po2.m >= k0) & (po2.m <= k1)].actual_lead_time_days.mean()
        r.between(g, "APAC lead time change", y / x - 1, 0.22, 0.38, "{:+.0%}")

    e = s.event("single_source_risk")
    if e:
        g = "NARRATIVE - Event 10 single-source risk"
        d = s.event("supplier_disruption")
        crit = prd[(prd.criticality == "Critical") & (prd.single_source_flag == 1)]
        r.check(g, "critical single-sourced SKUs exist",
                len(crit) >= int(e["critical_single_sourced_count"]), f"{len(crit)} SKUs")
        if d:
            sid = int(sup.loc[sup.supplier_master_id == d["supplier_master_id"], "supplier_id"].iloc[0])
            n = int((crit.primary_supplier_id == sid).sum())
            r.check(g, "some sit on the disrupted supplier",
                    n >= int(e["on_disrupted_supplier"]), f"{n} SKUs")

    e = s.event("carrier_degradation")
    if e:
        g = "NARRATIVE - Event 4 carrier degradation"
        cid = int(t["dim_carrier"].loc[t["dim_carrier"].carrier_code == e["carrier_code"],
                                       "carrier_id"].iloc[0])
        # The event is GEOGRAPHICALLY concentrated, which is the whole point --
        # you have to drill to the sub-region to see it. Comparing the
        # carrier's global average against other carriers washes it out and
        # tests nothing.
        loc = t["dim_location"].set_index("location_id")
        sh = ship.assign(sub=ship.location_id.map(loc.sub_region))
        here = sh[(sh.carrier_id == cid) & (sh["sub"] == e["sub_region"])]
        elsewhere = sh[(sh.carrier_id == cid) & (sh["sub"] != e["sub_region"])]
        r.check(g, f"{e['carrier_code']} is worse in {e['sub_region']}",
                here.is_on_time.mean() < elsewhere.is_on_time.mean() - 0.02,
                f"{here.is_on_time.mean():.1%} vs {elsewhere.is_on_time.mean():.1%} elsewhere")
        others = sh[(sh.carrier_id != cid) & (sh["sub"] == e["sub_region"])]
        r.check(g, f"and worse than other carriers in {e['sub_region']}",
                here.is_on_time.mean() < others.is_on_time.mean() - 0.02,
                f"{here.is_on_time.mean():.1%} vs {others.is_on_time.mean():.1%}")

    e = s.event("forecast_model_failure")
    if e:
        g = "NARRATIVE - Event 7 forecast bias"
        cats = prd.set_index("product_id").category
        f = fc[fc.forecast_version == "ML"].assign(cat=lambda x: x.product_id.map(cats))
        b = f[f.cat == e["category"]].forecast_bias_pct.mean()
        o = f[f.cat != e["category"]].forecast_bias_pct.mean()
        r.check(g, f"{e['category']} is under-forecast vs the rest", b < o,
                f"{b:+.1%} vs {o:+.1%}")

    e = s.event("planner_override_win")
    if e:
        g = "NARRATIVE - Event 15 planner overrides"
        ov = fc[fc.forecast_version == "Planner Override"]
        ml = fc[fc.forecast_version == "ML"]
        a = ov.groupby("product_id").abs_pct_error.mean()
        b = ml.groupby("product_id").abs_pct_error.mean()
        delta = (b - a).dropna()
        r.check(g, "overrides help some SKUs", (delta > 0.01).sum() > 0,
                f"{int((delta > 0.01).sum())} SKUs better")
        r.check(g, "and hurt others (not uniformly good)", (delta < -0.005).sum() > 0,
                f"{int((delta < -0.005).sum())} SKUs worse")

    g = "INTEGRITY - risk layer"
    real = sup[sup.supplier_id > 0]
    r.check(g, "risk bands are not all one level", real.risk_level.nunique() > 2,
            ", ".join(f"{k}={v}" for k, v in real.risk_level.value_counts().items()))
    tgt = s.risk.get("target_supplier_distribution", {})
    if tgt:
        want_high = (tgt.get("Critical", 0) + tgt.get("High", 0)) / max(sum(tgt.values()), 1)
        got_high = real.risk_level.isin(["Critical", "High"]).mean()
        r.between(g, "share of suppliers at High or Critical", got_high,
                  want_high * 0.5, want_high * 1.8)

    # ---------------- HEADLINE ----------------
    g = "HEADLINE"
    h = s.headline
    tol = float(h["tolerance"])
    def band(x):
        return x * (1 - tol), x * (1 + tol)
    inv_now = cur.groupby("snapshot_date").inventory_value.sum().mean()
    inv_ly = ly.groupby("snapshot_date").inventory_value.sum().mean()
    r.between(g, "inventory YoY", inv_now / inv_ly - 1, *band(h["inventory_growth_yoy"]))
    r.between(g, "stockout rate", cur[cur.demand_qty > 0].stockout_flag.mean(),
              *band(h["stockout_rate"]))
    r.between(g, "unit fill rate",
              cur.served_current_qty.sum() / cur.demand_qty.sum(), *band(h["line_fill_rate"]))
    s90 = ship[pd.to_datetime(ship.ship_date) > asof - pd.Timedelta(days=90)]
    r.between(g, "OTIF", s90.is_otif.mean(), *band(h["otif"]))
    f90 = fc[(fc.forecast_version == "ML") & (fc.forecast_horizon_months == 1)]
    r.between(g, "forecast accuracy", f90.forecast_accuracy.mean(),
              *band(h["forecast_accuracy"]))
    dos = cur.on_hand_qty.sum() / cur.avg_daily_demand.sum()
    r.between(g, "days of supply", dos, 45, 95, "{:.0f}d")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    a = ap.parse_args(argv)

    s = load_scenario(a.scenario, a.tier)
    d = Path(a.data) if a.data else PROJECT_ROOT / "data" / a.tier
    t = load(d)
    if not t:
        print(f"no parquet found in {d}; run generate.py first")
        return 2
    r = Report()
    run(s, t, r)
    print(r.render())
    return 1 if r.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
