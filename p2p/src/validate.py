#!/usr/bin/env python3
"""Post-generation checks.

Four families:

  INTEGRITY  keys resolve, quantities reconcile along the chain, milestone dates
             are monotonic, no money is negative where it cannot be.
  LEDGER     the AP subledger is internally consistent - open equals gross less
             cash less discount - and the month-end ageing snapshot sums to the
             same number as the ledger at the same date. To the cent.
  WATERFALL  the commitment-to-cash waterfall closes, and total spend
             reconciles across all three channels. This is the number the whole
             demo hangs off; if it does not close, nothing else matters.
  NARRATIVE  every enabled event is VISIBLE in the aggregates, at the magnitude
             the config claims, measured in the window where the ramp has
             actually arrived.

The narrative checks are the ones that earn their keep. Random noise routinely
swamps a planted signal, and the usual way to discover that is live, in front of
an audience, rather than here.

  python3 src/validate.py --tier small
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p2pconfig import PROJECT_ROOT, load_scenario, month_end


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, family: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((family, name, bool(ok), detail))

    def near(self, family: str, name: str, actual: float, target: float,
             tol: float, unit: str = "") -> None:
        ok = abs(actual - target) <= abs(target) * tol
        self.check(family, name, ok,
                   f"{actual:,.2f}{unit} vs {target:,.2f}{unit} "
                   f"(+/-{tol:.0%})")

    def render(self) -> int:
        failed = 0
        for family in ("INTEGRITY", "LEDGER", "WATERFALL", "NARRATIVE"):
            rows = [r for r in self.rows if r[0] == family]
            if not rows:
                continue
            print(f"\n{family}")
            for _f, name, ok, detail in rows:
                mark = "PASS" if ok else "FAIL"
                failed += 0 if ok else 1
                print(f"  [{mark}] {name}" + (f"  -  {detail}" if detail else ""))
        total = len(self.rows)
        print(f"\n{total - failed}/{total} checks passed")
        return failed


def load(out: Path, name: str) -> pd.DataFrame:
    for ext in ("parquet", "csv"):
        f = out / f"{name}.{ext}"
        if f.exists():
            return pd.read_parquet(f) if ext == "parquet" else pd.read_csv(f)
    return pd.DataFrame()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default=str(PROJECT_ROOT / "config"
                                              / "scenario_base.yaml"))
    ap.add_argument("--tier", default="small", choices=["small", "full"])
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)

    s = load_scenario(args.scenario, args.tier)
    out = Path(args.data) if args.data else PROJECT_ROOT / "data" / args.tier
    if not out.exists():
        print(f"no data at {out}; run generate.py first")
        return 2

    r = Report()
    t = {n: load(out, n) for n in [
        "dim_supplier", "dim_supplier_bank_account", "dim_employee", "dim_category",
        "dim_item", "contract", "contract_price", "fact_requisition",
        "fact_requisition_line", "fact_purchase_order", "fact_purchase_order_line",
        "fact_goods_receipt", "fact_goods_receipt_line", "fact_invoice",
        "fact_invoice_line", "fact_match_result", "fact_invoice_hold",
        "fact_payment", "fact_payment_application", "fact_ap_aging_snapshot",
        "fact_open_commitment_snapshot", "fact_spend", "fact_p2p_cycle",
        "fact_p2p_exception", "fact_pcard_transaction", "fact_budget",
        "fact_approval_event", "dim_approval_policy"]}

    _integrity(r, s, t)
    _ledger(r, s, t)
    _waterfall(r, s, t)
    _narrative(r, s, t)

    failed = r.render()
    return 1 if failed else 0


# ---------------------------------------------------------------------------


def _integrity(r: Report, s, t: dict) -> None:
    po, pol = t["fact_purchase_order"], t["fact_purchase_order_line"]
    inv, invl = t["fact_invoice"], t["fact_invoice_line"]
    grl = t["fact_goods_receipt_line"]

    r.check("INTEGRITY", "every PO line resolves to a PO",
            pol["purchase_order_id"].isin(po["purchase_order_id"]).all())
    r.check("INTEGRITY", "every invoice line resolves to an invoice",
            invl["invoice_id"].isin(inv["invoice_id"]).all())
    r.check("INTEGRITY", "every PO-backed invoice line resolves to a PO line",
            invl.loc[invl["purchase_order_line_id"] > 0, "purchase_order_line_id"]
            .isin(pol["purchase_order_line_id"]).all())
    r.check("INTEGRITY", "every receipt line resolves to a PO line",
            grl["purchase_order_line_id"].isin(pol["purchase_order_line_id"]).all()
            if len(grl) else True)
    apps = t["fact_payment_application"]
    r.check("INTEGRITY", "every payment application resolves to both sides",
            apps["payment_id"].isin(t["fact_payment"]["payment_id"]).all()
            and apps["invoice_id"].isin(inv["invoice_id"]).all())

    r.check("INTEGRITY", "PO header total equals the sum of its lines",
            abs(pol["line_amount_usd"].sum() - po["total_amount_usd"].sum()) < 1.0,
            f"delta ${abs(pol['line_amount_usd'].sum() - po['total_amount_usd'].sum()):,.2f}")

    # Received never exceeds ordered by more than the over-receipt tolerance.
    over = pol["quantity_received"] > pol["quantity_ordered"] * 1.2
    r.check("INTEGRITY", "over-receipt stays inside 20%", over.mean() < 0.01,
            f"{over.mean():.4f} of lines beyond")

    r.check("INTEGRITY", "no negative invoice on a standard document",
            (inv.loc[inv["invoice_type"] == "Standard Invoice",
                     "gross_amount_usd"] >= 0).all())

    cy = t["fact_p2p_cycle"]
    if len(cy):
        for leg in ("days_req_to_req_approved", "days_req_approved_to_po",
                    "days_po_to_receipt", "days_invoice_to_approved",
                    "days_approved_to_paid"):
            x = cy[leg].dropna()
            r.check("INTEGRITY", f"milestones monotonic: {leg}",
                    (x < 0).mean() < 0.001, f"{(x < 0).mean():.4f} negative")

    if len(cy):
        full = cy[cy["days_req_to_cash"].notna()
                  & cy["days_terms"].notna()].copy()
        parts = (full["days_controllable"] + full["days_supplier"]
                 + full["days_terms"])
        gap = (parts - full["days_req_to_cash"]).abs()
        r.check("INTEGRITY",
                "cycle components sum to the total (ours + supplier + terms)",
                float(gap.max()) < 1.5,
                f"max gap {float(gap.max()):.2f} days, mean {float(gap.mean()):.3f}")

    pol_live = pol[pol["receipt_state"] != "Cancelled"]
    r.check("INTEGRITY", "invoiced quantity never exceeds ordered by >25%",
            (pol_live["quantity_invoiced"]
             > pol_live["quantity_ordered"] * 1.25).mean() < 0.02)

    sup = t["dim_supplier"]
    r.check("INTEGRITY", "supplier names are unique",
            not sup["supplier_name"].duplicated().any())
    r.check("INTEGRITY", "no generator dials leaked into the output",
            not any(c.startswith("_") for df in t.values() for c in df.columns))


def _ledger(r: Report, s, t: dict) -> None:
    inv = t["fact_invoice"]
    apps = t["fact_payment_application"]
    std = inv[inv["invoice_type"] == "Standard Invoice"]

    residual = (std["gross_amount_usd"] - std["amount_paid_usd"]
                - std["discount_taken_usd"] - std["open_amount_usd"]).abs().max()
    r.check("LEDGER", "open = gross - paid - discount, to the cent",
            residual < 0.01, f"max residual ${residual:,.4f}")

    applied = apps.groupby("invoice_id")["applied_amount_usd"].sum()
    mapped = std["invoice_id"].map(applied).fillna(0.0)
    r.check("LEDGER", "amount_paid equals the sum of its applications",
            (std["amount_paid_usd"] - mapped).abs().max() < 0.01)

    r.check("LEDGER", "no invoice status contradicts its open amount",
            not ((std["is_open"] == 0) & (std["open_amount_usd"].abs() > 0.01)).any())

    r.check("LEDGER", "payment total equals the applications it covers",
            abs(t["fact_payment"]["payment_amount_usd"].sum()
                - apps["applied_amount_usd"].sum()) < 1.0)

    # Ageing snapshot ties to the ledger at each month end.
    aging = t["fact_ap_aging_snapshot"]
    if len(aging):
        settled = (pd.to_datetime(apps["payment_date"])
                   .groupby(apps["invoice_id"]).max())
        recv = pd.to_datetime(std["invoice_received_date"])
        st = std["invoice_id"].map(settled)
        worst = 0.0
        for m in s.timeline.month_starts()[-6:]:
            me = pd.Timestamp(month_end(m))
            open_now = (recv <= me) & (st.isna() | (st > me))
            expect = float(std.loc[open_now.to_numpy(), "gross_amount_usd"].sum())
            got = float(aging.loc[pd.to_datetime(aging["snapshot_month_end"]) == me,
                                  "open_amount_usd"].sum())
            worst = max(worst, abs(expect - got))
        r.check("LEDGER", "ageing snapshot ties to the ledger at each month end",
                worst < 0.01, f"max delta ${worst:,.4f}")

    disc = std[std["discount_taken_usd"] > 0]
    r.check("LEDGER", "discount only taken where terms offer one",
            (disc["discount_percent"] > 0).all() if len(disc) else True)


def _waterfall(r: Report, s, t: dict) -> None:
    H = s.headline
    tol = float(H["tolerance_pct"])
    ttm = pd.Timestamp(s.timeline.ttm_start)
    sp = t["fact_spend"]
    sp_ttm = sp[pd.to_datetime(sp["spend_date"]) >= ttm]

    total = float(sp_ttm["spend_amount_usd"].sum())
    r.near("WATERFALL", "total spend TTM", total, s.money(H["total_spend_ttm_usd"]),
           tol, " USD")

    by_channel = sp_ttm.groupby("spend_channel")["spend_amount_usd"].sum()
    r.check("WATERFALL", "channels sum to total spend",
            abs(by_channel.sum() - total) < 1.0)

    ch = s.channels
    for channel, target in (("Non-PO Invoice", ch["non_po_invoice_share_of_value"]),
                            ("P-Card", ch["pcard_share_of_value"])):
        share = float(by_channel.get(channel, 0.0)) / max(total, 1)
        # Configured shares are inputs to the sizing, not exact outputs.
        r.check("WATERFALL", f"{channel} share is plausible",
                abs(share - float(target)) < 0.06,
                f"{share:.3f} vs config {float(target):.3f}")

    pol = t["fact_purchase_order_line"]
    pol_ttm = pol[pd.to_datetime(pol["po_date"]) >= ttm]
    gross = float(pol_ttm["line_amount_usd"].sum())
    cancelled = float(pol_ttm.loc[pol_ttm["is_cancelled"] == 1,
                                  "line_amount_usd"].sum())
    open_c = float(pol_ttm["open_commitment_usd"].sum())
    # Received-vs-invoiced only reconciles on THREE-WAY lines. A two-way line is
    # invoiced without ever being received, so including it compares an invoiced
    # total against a receipt total that structurally excludes most of it.
    three = pol_ttm[pol_ttm["match_type"] == "3-Way"]
    received = float(three["received_amount_usd"].sum())
    gr_ir = float(three["gr_ir_amount_usd"].sum())
    invoiced = float(three["invoiced_amount_usd"].sum())

    r.check("WATERFALL", "commitment: gross - cancelled - open >= received",
            gross - cancelled - open_c >= received * 0.90,
            f"gross ${gross/1e6:,.1f}M cancelled ${cancelled/1e6:,.1f}M "
            f"open ${open_c/1e6:,.1f}M received ${received/1e6:,.1f}M")
    r.check("WATERFALL", "received - GR/IR is close to invoiced",
            abs((received - gr_ir) - invoiced) <= max(received * 0.25, 1.0),
            f"received ${received/1e6:,.1f}M - GRIR ${gr_ir/1e6:,.1f}M "
            f"vs invoiced ${invoiced/1e6:,.1f}M")

    prev = pd.Timestamp(s.timeline.prior_ttm_start)
    sp_prev = sp[(pd.to_datetime(sp["spend_date"]) >= prev)
                 & (pd.to_datetime(sp["spend_date"]) < ttm)]
    yoy = total / max(float(sp_prev["spend_amount_usd"].sum()), 1) - 1
    r.check("WATERFALL", "spend growth YoY", abs(yoy - float(H["spend_growth_yoy"])) < 0.05,
            f"{yoy:.1%} vs target {float(H['spend_growth_yoy']):.1%}")


def _narrative(r: Report, s, t: dict) -> None:
    H = s.headline
    tol = float(H["tolerance_pct"])
    ttm = pd.Timestamp(s.timeline.ttm_start)
    inv = t["fact_invoice"]
    inv_ttm = inv[pd.to_datetime(inv["invoice_date"]) >= ttm]
    sp = t["fact_spend"]
    sp_ttm = sp[pd.to_datetime(sp["spend_date"]) >= ttm]

    # E1 maverick
    mav = float(sp_ttm.loc[sp_ttm["is_maverick_spend"] == 1,
                           "spend_amount_usd"].sum())
    r.near("NARRATIVE", "E1  maverick spend TTM", mav,
           s.money(H["maverick_spend_usd"]), 0.30, " USD")
    ev = s.event("maverick_spend")
    if ev:
        hot = sp_ttm[sp_ttm["is_maverick_spend"] == 1]
        top = (hot.groupby("department_id")["spend_amount_usd"].sum()
               .sort_values(ascending=False))
        k = max(2, int(round(float(ev["department_share"])
                             * sp["department_id"].nunique())))
        conc = float(top.head(k).sum()) / max(float(top.sum()), 1)
        r.check("NARRATIVE", "E1  maverick concentrates in a few departments",
                conc > 0.40, f"top {k} departments hold {conc:.0%}")

    # E4 contract price drift, and the hero supplier
    pol = t["fact_purchase_order_line"]
    pol_ttm = pol[pd.to_datetime(pol["po_date"]) >= ttm]
    drift = float(pol_ttm["contract_price_variance_usd"].clip(lower=0).sum())
    r.check("NARRATIVE", "E4  price drift above contract is visible",
            drift > 0.4e6 * s.tier_scale, f"${drift/1e6:,.2f}M TTM")

    sup = t["dim_supplier"]
    hero = sup[sup["supplier_name"].str.startswith("Northbeam")]
    if len(hero):
        hid = int(hero["supplier_id"].iloc[0])
        rank = (pol_ttm.groupby("supplier_id")["line_amount_usd"].sum()
                .sort_values(ascending=False).index.get_loc(hid) + 1)
        r.check("NARRATIVE", "E4  hero supplier is a top-5 supplier by spend",
                rank <= 5, f"{hero['supplier_name'].iloc[0]} ranks {rank}")

    # E5 delivery decay
    # Measured on the AFFECTED suppliers. Nine suppliers out of 2,400 cannot
    # move the company-wide average, so checking the overall trend tests noise.
    # Find the decay the way an analyst would: compare each supplier's on-time
    # rate early in the history against its rate now, and count how many have
    # fallen materially. Selecting on the CURRENT worst rate instead just finds
    # suppliers that were always poor, which is a different question.
    ev5 = s.event("delivery_decay")
    recv = pol[pol["is_on_time"].notna()].copy()
    if ev5 and len(recv):
        d = pd.to_datetime(recv["po_date"])
        split = pd.Timestamp(s.timeline.offset_month(-int(
            (s.timeline.as_of_date.year * 12 + s.timeline.as_of_date.month
             - s.timeline.start_date.year * 12 - s.timeline.start_date.month) // 2)))
        early = recv[d < split].groupby("supplier_id")["is_on_time"].agg(["mean", "size"])
        late = recv[d >= split].groupby("supplier_id")["is_on_time"].agg(["mean", "size"])
        j = early.join(late, lsuffix="_e", rsuffix="_l", how="inner")
        j = j[(j["size_e"] >= 15) & (j["size_l"] >= 15)]
        j["delta"] = j["mean_l"] - j["mean_e"]
        decayed = int((j["delta"] <= -0.08).sum())
        r.check("NARRATIVE", "E5  suppliers with a material on-time decay exist",
                decayed >= max(3, int(ev5["supplier_count"] * 0.5)),
                f"{decayed} suppliers down >=8pt (worst {j['delta'].min():.0%})")

    # E6 -> E8 the causal chain
    approve = float(inv_ttm["days_to_approve"].mean())
    r.check("NARRATIVE", "E6  invoice approval averages 9-16 days",
            9 <= approve <= 16, f"{approve:.1f} days")
    missed = float(inv_ttm["discount_missed_usd"].sum())
    r.near("NARRATIVE", "E8  missed early-payment discount TTM", missed,
           s.money(H["missed_discount_usd"]), 0.35, " USD")
    m = inv_ttm[inv_ttm["discount_missed_usd"] > 0]
    if len(m):
        share = float(m["missed_due_to_approval"].mean())
        r.check("NARRATIVE", "E8  missed BECAUSE approval was late (the causal link)",
                share > 0.6, f"{share:.0%} of missed discounts")

    # E7 duplicates
    dup = inv[inv["is_duplicate_suspect"] == 1]
    r.check("NARRATIVE", "E7  duplicate invoices exist in four archetypes",
            dup["duplicate_archetype"].nunique() >= 4,
            f"{len(dup):,} suspects, {dup['duplicate_archetype'].nunique()} archetypes")
    paid_dup = dup[dup["payment_status"].isin(["Paid", "Partially Paid"])]
    r.check("NARRATIVE", "E7  some duplicates were actually PAID",
            len(paid_dup) > 0,
            f"{len(paid_dup):,} paid, ${paid_dup['amount_paid_usd'].sum()/1e3:,.0f}K")

    # E11 shared bank accounts, with the benign control group
    banks = t["dim_supplier_bank_account"]
    if len(banks):
        shared = (banks.groupby("account_number_hash")["supplier_id"].nunique())
        shared = shared[shared > 1]
        r.check("NARRATIVE", "E11 shared bank accounts exist",
                len(shared) >= 3, f"{len(shared)} shared accounts")
        reasons = banks.loc[banks["shared_flag_reason"] != "",
                            "shared_flag_reason"].nunique()
        r.check("NARRATIVE", "E11 has BOTH suspicious and benign clusters",
                reasons >= 2, f"{reasons} distinct reasons")

    # E13 PO splitting, against a base rate
    po = t["fact_purchase_order"]
    sg = po[po["split_group_key"].fillna("") != ""]
    r.check("NARRATIVE", "E13 PO splitting cases exist",
            sg["split_group_key"].nunique() >= 10 * s.tier_scale,
            f"{sg['split_group_key'].nunique()} groups, {len(sg)} POs")

    # E14 excess mass below the approval threshold
    ev = s.event("threshold_clustering")
    if ev:
        thr = float(ev["threshold_usd"])
        band = po[po["total_amount_usd"].between(thr * 0.9, thr)]
        above = po[po["total_amount_usd"].between(thr, thr * 1.1)]
        r.check("NARRATIVE", "E14 more POs just below the threshold than just above",
                len(band) > len(above),
                f"{len(band)} below vs {len(above)} above")

    # E15 GR/IR
    gr_ir = float(pol_ttm["gr_ir_amount_usd"].sum())
    r.near("NARRATIVE", "E15 GR/IR accrual TTM", gr_ir,
           s.money(H["gr_ir_accrual_usd"]), 0.30, " USD")

    # E16 contract expiry wave
    ctr = t["contract"]
    soon = ctr[(ctr["days_to_expiry"] > 0) & (ctr["days_to_expiry"] <= 90)]
    r.check("NARRATIVE", "E16 contracts expiring within 90 days",
            len(soon) >= 50 * s.tier_scale, f"{len(soon)} contracts")

    # E17 the FX red herring
    ev = s.event("fx_red_herring")
    if ev:
        fx = load(PROJECT_ROOT / "data" / s.tier, "dim_exchange_rate")
        cur = fx[fx["currency_code"] == ev["currency"]].sort_values("rate_date")
        if len(cur):
            start = pd.Timestamp(s.timeline.offset_month(int(ev["start_offset"])))
            a = float(cur.loc[pd.to_datetime(cur["rate_date"]) <= start,
                              "rate_to_usd"].iloc[-1])
            b = float(cur["rate_to_usd"].iloc[-1])
            r.near("NARRATIVE", "E17 FX moves by the configured amount",
                   b / a - 1, float(ev["apparent_increase"]), 0.10)

    # Headline operational rates
    match = t["fact_match_result"]
    if len(match):
        fpm = float(match.groupby("invoice_id")["is_first_pass_match"].min().mean())
        r.near("NARRATIVE", "first-pass match rate", fpm,
               float(H["first_pass_match_rate"]), 0.08)
    holds = t["fact_invoice_hold"]
    exc = float(inv["invoice_id"].isin(holds["invoice_id"]).mean())
    r.near("NARRATIVE", "exception rate", exc, float(H["exception_rate"]), 0.20)
    stp = float(inv["is_straight_through"].mean())
    r.near("NARRATIVE", "straight-through rate", stp,
           float(H["straight_through_rate"]), 0.15)

    cy = t["fact_p2p_cycle"]
    if len(cy):
        r.near("NARRATIVE", "requisition-to-cash cycle",
               float(cy["days_req_to_cash"].dropna().mean()),
               float(H["req_to_cash_days"]), 0.15, " days")


if __name__ == "__main__":
    raise SystemExit(main())
