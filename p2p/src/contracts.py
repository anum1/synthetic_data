"""Supplier coverage, contracts, and the contracted price list.

`contract_price` is the source of truth for what Norvant *should* be paying.
Event 4 - the root cause the whole demo hangs off - is defined as the gap
between this table and `purchase_order_line.unit_price`, so it has to exist and
be independently readable before any of that story can be told (PLAN 2.3).

Coverage is built first: which suppliers can sell which category. Without it,
sourcing is a uniform draw and every supplier sells everything, which destroys
both the concentration story (E10) and the consolidation story (E18).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from events import EventPlan
from p2pconfig import Scenario, add_month

CONTRACT_TYPES = ["Framework Agreement", "Rate Card", "Blanket PO",
                  "Master Services Agreement", "Spot Agreement"]


def build_supplier_coverage(s: Scenario, sup: pd.DataFrame, cats: pd.DataFrame,
                            ep: EventPlan, rng: np.random.Generator):
    """Which supplier can sell which category leaf, and with what weight.

    Returns (coverage_df, sampler) where `sampler` maps category_id ->
    (supplier_ids, probabilities) so requisition sourcing is one draw rather
    than a filter over 2,400 suppliers per line.
    """
    families = cats["family_name"].unique()
    fam_weight = (cats.groupby("family_name")["_spend_weight"].sum()
                  .reindex(families).to_numpy())
    fam_weight = fam_weight / fam_weight.sum()

    rows = []
    leaves_by_family = {f: g["category_id"].to_numpy()
                        for f, g in cats.groupby("family_name")}

    # Breadth scales with size. Giving every supplier one to four random leaves
    # regardless of weight decouples intended spend from received spend - the
    # supplier the demo script names ends up ranked 90th, because its weight is
    # high but the leaves it happens to cover are small. A large supplier sells
    # across more of its family, and across the family's bigger categories.
    leaf_rank_in_family = {}
    for f, g in cats.groupby("family_name"):
        ordered = g.sort_values("_spend_weight", ascending=False)
        leaf_rank_in_family[f] = ordered["category_id"].to_numpy()

    w = sup["_spend_weight"].to_numpy()
    w_rel = w / w.max()
    breadth = np.clip(np.round(14.0 * w_rel ** 0.32), 1, 16).astype(int)

    for (_, r), n_leaf in zip(sup.iterrows(), breadth):
        sid = int(r["supplier_id"])
        k = 1 + int(rng.random() < 0.28)
        if w_rel[sid - 1] > 0.25:
            # A top-30 supplier sells into a top family. Left to the general
            # draw it can land in Trade Services, and the supplier the demo
            # names by name is then ranked fortieth by actual spend.
            top_fam = families[np.argsort(fam_weight)[::-1][:8]]
            picked = rng.choice(top_fam, size=min(k, len(top_fam)), replace=False)
        else:
            picked = rng.choice(families, size=k, replace=False, p=fam_weight)
        per_family = max(1, int(np.ceil(n_leaf / k)))
        for fam in picked:
            ordered = leaf_rank_in_family[fam]
            take = min(len(ordered), per_family)
            # Big suppliers take from the head of the family (its biggest
            # categories); small ones are scattered through the tail.
            if w_rel[sid - 1] > 0.25:
                head_n = min(len(ordered), max(take, int(len(ordered) * 0.5)))
                chosen = rng.choice(ordered[:head_n], size=take, replace=False)
            else:
                chosen = rng.choice(ordered, size=take, replace=False)
            for leaf in chosen:
                rows.append((sid, int(leaf), float(r["_spend_weight"])))

    cov = pd.DataFrame(rows, columns=["supplier_id", "category_id", "_weight"])

    # -- E10: force the concentration category onto four suppliers -------------
    if len(ep.concentration_leaf_ids):
        cov = cov[~cov["category_id"].isin(ep.concentration_leaf_ids)]
        extra = []
        for leaf in ep.concentration_leaf_ids:
            for sid, share in zip(ep.concentration_suppliers, ep.concentration_shares):
                extra.append((int(sid), int(leaf), float(share)))
        cov = pd.concat([cov, pd.DataFrame(
            extra, columns=["supplier_id", "category_id", "_weight"])],
            ignore_index=True)

    # -- E18: fragment the consolidation categories across many suppliers ------
    ev = s.event("consolidation_opportunity")
    if ev is not None and len(ep.consolidation_categories):
        min_sup = int(ev["min_suppliers"])
        extra = []
        for leaf in ep.consolidation_categories:
            have = cov[cov["category_id"] == leaf]["supplier_id"].nunique()
            need = max(0, min_sup - have)
            if need:
                pool = sup[~sup["supplier_id"].isin(
                    cov[cov["category_id"] == leaf]["supplier_id"])]
                pick = pool.sample(n=min(need, len(pool)),
                                   random_state=int(s.seed) + 201 + int(leaf))
                for sid in pick["supplier_id"]:
                    extra.append((int(sid), int(leaf), 0.0))
        if extra:
            cov = pd.concat([cov, pd.DataFrame(
                extra, columns=["supplier_id", "category_id", "_weight"])],
                ignore_index=True)
        # Flatten the weights so no supplier dominates - that is what "fragmented"
        # means, and it is what makes top-5 share fall below 35%.
        frag = cov["category_id"].isin(ep.consolidation_categories)
        cov.loc[frag, "_weight"] = rng.uniform(0.8, 1.2, size=int(frag.sum()))

    # Every leaf needs at least one supplier or its requisitions cannot source.
    missing = set(cats["category_id"]) - set(cov["category_id"])
    if missing:
        filler = []
        for leaf in missing:
            pick = sup.sample(n=3, weights=sup["_spend_weight"],
                              random_state=int(s.seed) + 301 + int(leaf))
            for _, r in pick.iterrows():
                filler.append((int(r["supplier_id"]), int(leaf),
                               float(r["_spend_weight"])))
        cov = pd.concat([cov, pd.DataFrame(
            filler, columns=["supplier_id", "category_id", "_weight"])],
            ignore_index=True)

    cov = cov.groupby(["category_id", "supplier_id"], as_index=False)["_weight"].max()
    # Flatten the within-leaf weight. Concentration is already carried by
    # breadth - big suppliers cover more categories - so applying the full
    # weight again inside each leaf compounds it, and the top 20% end up with
    # 88% of spend instead of the 72% the config asks for.
    flat = float(s.demand.get("supplier_within_leaf_exponent", 0.55))
    sampler = {}
    for leaf, g in cov.groupby("category_id"):
        w = g["_weight"].to_numpy().astype(float)
        w = np.where(w <= 0, w[w > 0].min() * 0.05 if (w > 0).any() else 1.0, w)
        w = w ** flat
        sampler[int(leaf)] = (g["supplier_id"].to_numpy(), w / w.sum())
    return cov, sampler


def build_contracts(s: Scenario, sup: pd.DataFrame, cats: pd.DataFrame,
                    items: pd.DataFrame, coverage: pd.DataFrame,
                    terms: pd.DataFrame, employees: pd.DataFrame, ep: EventPlan,
                    rng: np.random.Generator):
    """Returns (contract, contract_price).

    Contracts are handed out in supplier spend order until the configured share
    of expected spend is covered, so `contracted_spend %` lands where the
    headline says it does rather than wherever a uniform draw happens to put it.
    """
    n_target = int(s.sizes["contracts"])
    tl = s.timeline

    # Rank supplier x family pairs by supplier spend and take from the top until
    # the coverage target is met.
    cov = coverage.merge(cats[["category_id", "family_name", "segment_name"]],
                         on="category_id", how="left")
    pair = (cov.groupby(["supplier_id", "family_name"], as_index=False)["_weight"]
            .max().sort_values("_weight", ascending=False).reset_index(drop=True))
    pair["_cum"] = pair["_weight"].cumsum() / pair["_weight"].sum()
    target = float(s.sourcing["contract_coverage"])
    contracted = pair[pair["_cum"] <= target].head(n_target)
    if len(contracted) < n_target:
        contracted = pair.head(n_target)
    if len(contracted) < n_target:
        # Fewer distinct supplier x family pairs than contracts asked for. Give
        # the largest relationships a second agreement, which is what they carry
        # in reality - a master services agreement and a rate card underneath it.
        extra = contracted.head(n_target - len(contracted))
        contracted = pd.concat([contracted, extra], ignore_index=True)

    n = len(contracted)
    owners = employees[employees["is_buyer"] == 1]
    if not len(owners):
        owners = employees
    owner_ids = owners.sample(n=n, replace=True,
                              random_state=int(s.seed) + 401)["employee_id"].to_numpy()

    term_months = int(s.sourcing["contract_term_months"])
    # Start dates spread across history and a little before it, so contracts are
    # at every point in their life cycle.
    # Contracts are at every point in their life, but most are live: a master
    # where 79% of agreements have expired is a company that has stopped buying.
    # Draw the start inside the last two terms, then let auto-renew roll the
    # ones that reached their end date.
    horizon = int(term_months * 31 * 1.7)
    start = [tl.as_of_date - dt.timedelta(days=int(d))
             for d in rng.integers(20, horizon, size=n)]
    end = []
    for st, renew in zip(start, rng.random(n) < 0.42):
        e_ = add_month(st, term_months)
        while renew and e_ < tl.as_of_date:
            e_ = add_month(e_, term_months)
        end.append(e_)

    tw = terms["_weight"].to_numpy() / terms["_weight"].sum()
    term_code = rng.choice(terms["payment_terms_code"].to_numpy(), size=n, p=tw)

    sup_idx = sup.set_index("supplier_id")
    df = pd.DataFrame({
        "contract_id": np.arange(1, n + 1, dtype=np.int64),
        "contract_number": [f"CTR-{i:06d}" for i in range(1, n + 1)],
        "supplier_id": contracted["supplier_id"].to_numpy(),
        "family_name": contracted["family_name"].to_numpy(),
        "contract_type": rng.choice(CONTRACT_TYPES, size=n,
                                    p=[0.34, 0.22, 0.18, 0.20, 0.06]),
        "contract_start_date": start,
        "contract_end_date": end,
        "payment_terms_code": term_code,
        "owner_employee_id": owner_ids,
        "auto_renew_flag": (pd.to_datetime(end) - pd.to_datetime(start)).days
                           .to_numpy() > term_months * 31,
    })
    df["auto_renew_flag"] = df["auto_renew_flag"].astype("int8")
    df["company_code"] = sup_idx.loc[df["supplier_id"], "company_code"].to_numpy() \
        if "company_code" in sup_idx.columns else "NG100"
    df["currency_code"] = sup_idx.loc[df["supplier_id"], "currency_code"].to_numpy()
    # Committed value scales with the supplier's spend weight, so a framework
    # with a top-10 supplier is worth more than one with a tail vendor.
    w = sup_idx.loc[df["supplier_id"], "_spend_weight"].to_numpy()
    df["committed_value_usd"] = np.round(
        w / w.sum() * 620_000_000 * s.tier_scale * rng.uniform(0.5, 1.6, size=n), 2)

    # -- E16: the contract expiry wave ----------------------------------------
    ev = s.event("contract_expiry_wave")
    if ev:
        horizon_days = int(ev["horizon_days"])
        natural = int(((pd.to_datetime(df["contract_end_date"])
                        > pd.Timestamp(tl.as_of_date))
                       & (pd.to_datetime(df["contract_end_date"])
                          <= pd.Timestamp(tl.as_of_date
                                          + dt.timedelta(days=horizon_days)))).sum())
        k = min(max(int(ev["expiring_count"] * s.tier_scale) - natural, 0), n)
        # Expire the LARGEST contracts, so "spend at risk" is a real number.
        idx = df.nlargest(k * 3, "committed_value_usd").sample(
            n=k, random_state=int(s.seed) + 402).index
        horizon = int(ev["horizon_days"])
        df.loc[idx, "contract_end_date"] = [
            tl.as_of_date + dt.timedelta(days=int(d))
            for d in rng.integers(1, horizon + 1, size=k)]

    df["is_expired"] = (pd.to_datetime(df["contract_end_date"])
                        < pd.Timestamp(tl.as_of_date)).astype("int8")
    df["days_to_expiry"] = (pd.to_datetime(df["contract_end_date"])
                            - pd.Timestamp(tl.as_of_date)).dt.days.astype("int32")
    df["contract_status"] = np.where(df["is_expired"] == 1, "Expired", "Active")

    prices = _build_contract_prices(s, df, items, coverage, ep, rng)
    return df, prices


def _build_contract_prices(s: Scenario, contracts: pd.DataFrame, items: pd.DataFrame,
                           coverage: pd.DataFrame, ep: EventPlan,
                           rng: np.random.Generator) -> pd.DataFrame:
    """The agreed unit price per contract x item.

    Priced off list with a negotiated discount. This is what the PO price is
    later compared against, and the gap is Event 4.
    """
    items_by_leaf = {int(k): g for k, g in items.groupby("category_id")}
    leaves_by_supplier: dict[int, set[int]] = {}
    for sid, leaf in zip(coverage["supplier_id"], coverage["category_id"]):
        leaves_by_supplier.setdefault(int(sid), set()).add(int(leaf))
    leaf_family = dict(zip(items["category_id"], items["family_name"]))

    frames = []
    lo, hi = s.sourcing["contract_price_discount_range"]
    for _, c in contracts.iterrows():
        # Only the leaves this supplier covers, inside this contract's family.
        leaves = [l for l in leaves_by_supplier.get(int(c["supplier_id"]), ())
                  if leaf_family.get(l) == c["family_name"]]
        pool = pd.concat([items_by_leaf[l] for l in leaves
                          if l in items_by_leaf], ignore_index=True) \
            if leaves else None
        if pool is None or pool.empty:
            continue
        k = int(rng.integers(14, 60))
        pick = pool.sample(n=min(k, len(pool)),
                           random_state=int(rng.integers(1, 10**9)))
        disc = rng.uniform(lo, hi, size=len(pick))
        frames.append(pd.DataFrame({
            "contract_id": int(c["contract_id"]),
            "supplier_id": int(c["supplier_id"]),
            "item_id": pick["item_id"].to_numpy(),
            "category_id": pick["category_id"].to_numpy(),
            "contract_unit_price_usd": np.round(
                pick["list_price_usd"].to_numpy() * (1 - disc), 4),
            "list_price_usd": pick["list_price_usd"].to_numpy(),
            "discount_off_list": np.round(disc, 4),
            "minimum_quantity": rng.choice([1, 1, 1, 5, 10, 25], size=len(pick)),
            "valid_from_date": c["contract_start_date"],
            "valid_to_date": c["contract_end_date"],
            "currency_code": c["currency_code"],
        }))
    if not frames:
        return pd.DataFrame(columns=["contract_price_id", "contract_id", "supplier_id",
                                     "item_id", "contract_unit_price_usd"])
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(["supplier_id", "item_id"]).reset_index(drop=True)
    df["contract_price_id"] = np.arange(1, len(df) + 1, dtype=np.int64)
    return df
