# The eighteen planted events, as measured

Every figure below is from `data/full` and is asserted by `src/validate.py`. If
the build is green, these are the numbers on screen.

Two rules govern every event:

- **Scope is a fraction of the population**, resolved to concrete entities once
  in `events.py`, so a story stays proportionally visible at both tiers and every
  generator stage agrees on which supplier the story landed on.
- **Events ramp, they do not step.** A step change is findable by eye and makes
  the AI look clairvoyant rather than useful. A ramp has to be measured.

The hero supplier is **Northbeam Solutions** — resolved by name prefix, so it
survives a reseed even though supplier ids shuffle.

---

## The causal spine

Five events are one event seen five ways. This chain is generated in order, so
an unplanned drill-down cannot contradict the narrative:

```
E4  PO price drifts above the contracted price   (14 suppliers)
      ↓
E2  invoice breaches the price tolerance         (4.1% of PO invoices)
      ↓
     a PRICE_VAR hold is raised                  (7,283 holds, the largest category)
      ↓
E6  invoice approval is delayed                  (12.0 days average)
      ↓
E8  the 10-day discount window has already shut  ($912K missed, 88% for this reason)
      ↓
E9  payment lands past due                       (30% of open AP is overdue)
```

That is the demo. Everything else is supporting material.

---

## Measured magnitudes

| # | Event | Configured | Measured |
|---|---|---|---|
| 1 | Maverick spend | $12.8M TTM, 68% in a few departments | **$13.8M**, top 6 departments hold **71%** |
| 2 | Invoice amount variance | 4.1% of PO invoices | price/qty/amount variances on **7.7%** of matched lines |
| 3 | Quantity mismatch | 2.6% of lines, 3 categories | QTY_VAR holds raised, concentrated in the target categories |
| 4 | **Contract price drift** | 14 suppliers, hero at 18% | **$0.89M** paid above contract TTM; hero ranks **3rd** by spend |
| 5 | Delivery decay | 9 suppliers, 94% → 79% | **113 suppliers** down ≥8pt half-on-half (worst −43%) |
| 6 | Approval slowdown | one department, 9 → 24 days | company average **12.0 days** |
| 7 | **Duplicate invoices** | 412 suspected, 4 archetypes | **412 suspected, 51 PAID = $231K out the door** |
| 8 | Missed early-pay discount | $1.05M, 78% from slow approval | **$912K**, **88%** because approval was late |
| 9 | Late payment | 3 suppliers, +16 days | **30%** of open payables overdue ($11.0M) |
| 10 | Supplier concentration | one category at 42/31/15/12 | 4 suppliers hold that category outright |
| 11 | Shared bank accounts | 3 suspicious + 2 benign | **5 shared accounts**, 2 distinct reasons |
| 12 | Employee/supplier conflict | 4 real + 6 coincidental | full-name matches alongside surname collisions |
| 13 | PO splitting | 40 cases, 10-day window | **39 split groups across 87 POs** |
| 14 | Threshold clustering | excess mass in $45–50K | **217 POs just below vs 137 just above** |
| 15 | **GR/IR pile** | $18.7M, 62% aged >90d | **$15.3M**, **75%** aged >90d |
| 16 | Contract expiry wave | 340 within 90 days | **335 contracts** |
| 17 | FX red herring | EUR +9% over 12 months | **+9.0%**, exactly, every seed |
| 18 | Consolidation opportunity | 3 categories, 40+ suppliers | fragmented categories with top-5 share below 35% |

---

## The control groups

Four of the fraud events ship with innocent lookalikes. Without them, the
detection question is a filter that returns the answer key — with them, it is a
ranking problem with a false-positive rate, which is what the audience has at
home.

| Event | The planted case | The control group |
|---|---|---|
| E11 shared bank accounts | 3 clusters of unrelated suppliers | 2 clusters of subsidiaries under one parent, legitimately sharing a remit-to account |
| E12 employee/supplier | 4 full-name matches | 6 coincidental surname collisions |
| E13 PO splitting | 39 real split groups | every natural co-occurrence of the same buyer, supplier and category in a 10-day window |
| E14 threshold clustering | excess mass below the limit | the 137 POs that legitimately sit just above it |
| E7 duplicates | 3 genuine archetypes | `unapplied_credit_memo` — a rebill that looks like a duplicate and is not |

Fraud is **0.4% of the data**, not the 2% the original design note proposed. At
2%, "find suppliers sharing bank accounts" returns hundreds of rows, nobody in
the room believes it, and there is no detection story because detection is
trivial.

---

## The four duplicate archetypes

An exact repeat of an invoice number against the same supplier violates the
unique constraint in every real ERP. Real duplicates arrive through four doors:

| Archetype | Share | What it looks like |
|---|---:|---|
| `formatting_variant` | 38% | `INV-12345` / `INV12345` / `INV-012345` — same supplier, same amount, same PO |
| `duplicate_supplier_record` | 27% | The same invoice keyed against two master records for one vendor |
| `double_entry_channel` | 24% | Once through the supplier portal, once by email |
| `unapplied_credit_memo` | 11% | A rebill that *looks* like a duplicate. The honest false positive. |

Detection needs a fuzzy key the data supports: supplier **parent** + gross amount
±1% + invoice date within 10 days. Q19 in `sql/demo_questions.sql` does exactly
that.

**51 of them were paid.** "We have 412 suspected duplicates" is interesting.
"**We paid 51 of them, $231K left the building**" is the number people repeat
afterwards.

---

## Data condition mix

| Condition | Share |
|---|---:|
| Normal transactions | 84.0% |
| Minor anomalies (roundings, small variances, noise) | 10.0% |
| Operational problems (the ten planted events) | 5.5% |
| Fraud / risk scenarios | 0.4% |
| Extreme planted events | 0.1% |

The anomalies **cluster** rather than scattering. Northbeam Solutions carries
price drift, delivery decay, invoice exceptions and rising spend simultaneously,
which produces a story:

> *"Northbeam has become one of our fastest-growing suppliers, and its
> operational performance is deteriorating at the same time."*

That is a better sentence than "Northbeam has a high exception rate."
