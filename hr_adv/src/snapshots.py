"""Post-processing of the month-end workforce snapshot.

Adds the flattened management chain. `manager_employee_id` alone answers "who
does this person report to"; it does not answer "show me everything under this
VP", which is the question every workforce review actually asks. Walking the
chain at query time needs a recursive CTE, and the tools this dataset targets
either cannot do that or do it slowly enough to spoil a live demo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAX_DEPTH = 6


def add_manager_chain(snap: pd.DataFrame) -> pd.DataFrame:
    """manager_chain_l1..l6 (top-down) and reporting depth, per month."""
    out = []
    for ym, grp in snap.groupby("year_month_key", sort=True):
        parent = dict(zip(grp["employee_id"].to_numpy(),
                          grp["manager_employee_id"].to_numpy()))
        ids = grp["employee_id"].to_numpy()

        # Walk up to the root, capping the depth so a cycle can never hang the
        # generator - the manager assignment cannot create one, but a dataset
        # that silently loops forever is a bad way to find that out.
        chains = [[] for _ in ids]
        cur = ids.copy()
        for _ in range(MAX_DEPTH + 4):
            nxt = np.array([parent.get(int(c), 0) for c in cur])
            moving = (nxt != 0) & (nxt != cur)
            if not moving.any():
                break
            for k in np.where(moving)[0]:
                chains[k].append(int(nxt[k]))
            cur = np.where(moving, nxt, cur)

        depth = np.array([len(c) for c in chains], dtype="int16")
        cols = {}
        for lvl in range(MAX_DEPTH):
            cols[f"manager_chain_l{lvl + 1}"] = np.array(
                [c[::-1][lvl] if len(c) > lvl else 0 for c in chains], dtype="int32")
        block = grp.copy()
        for name, vals in cols.items():
            block[name] = vals
        block["reporting_depth"] = depth
        out.append(block)
    return pd.concat(out, ignore_index=True)
