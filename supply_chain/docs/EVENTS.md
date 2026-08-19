# Planted events

15 events, each configured in `config/scenario_base.yaml` under `events:`.
Timing is **month offsets relative to the as-of date**, never absolute dates, so
the narrative stays correct whenever the dataset is regenerated.

Every event has an **expected effect** column. That column is not documentation —
it is the validator assertion. Random noise routinely swamps a planted signal,
and the failure mode is discovering it live in front of an audience.

Set any event's `enabled: false` to remove that story from the data entirely.

---

## The spine: build and validate these four first

Events 1, 5, 6 and 10 all converge on the same drill-down, and that drill-down is
the demo. If `Product A → S-104 → lead time 18→29 → OTIF 95%→71% → no alternate`
works end to end, the other eleven events are decoration on a working spine.
Build them first, validate them, then add the rest.

| # | Event | Window | Mechanism | Expected effect (= validator assertion) |
|---|---|---|---|---|
| 1 | **Supplier disruption** | −5 → −3 | S-104 capacity constrained for 8 weeks | Actual lead time 18 → 29 days (±2); on-time 95% → 71% (±3 pts); receipts −40% in window |
| 5 | **Quality failure** | −4 → 0 | S-137 defect rate ramps over 3 months, then holds | Defect rate 1.5% → 7.0% (±0.7 pts) **measured on the trailing 90 days**, not the window mean — the ramp is part of the story; rejected receipt qty ≥ 6% of received |
| 6 | **Port disruption** | −3 → −2 | Asia-origin inbound transit +12 days | Asia-sourced SKU lead time +30% (±8 pts) — 12 days on a ~36-day APAC baseline; expedite cost in window ≥ 3× baseline |
| 10 | **Single-source risk** | structural | 22 Critical SKUs get `secondary_supplier_id = 0`, 6 of them on S-104 | ≥ 6 Critical single-sourced SKUs map to S-104; their combined revenue-at-risk ≥ $9M |

Event 10 is structural rather than time-windowed — it is a property of
`dim_product` that makes events 1 and 5 *consequential*. Without it, every
disruption has an obvious mitigation and the AI drill-down has nothing to
conclude.

---

## The full set

| # | Event | Window | Mechanism | Expected effect |
|---|---|---|---|---|
| 2 | **Demand spike** | −6 → −2 | SmartHome family demand +28% | Family units +25–31% YoY; forecast MAPE on family +8 pts; expedited shipment share 2× |
| 3 | **Excess inventory** | −9 → 0 | 230 slow-moving C-class SKUs over-forecast by 35% | Their inventory value +30% (±5); turns 4.1 → 2.6; carrying cost +$1.4M |
| 4 | **Carrier degradation** | −5 → 0 | C-07 transit time drifts up in Northeast | C-07 Northeast transit +2.5 days (±0.4); C-07 OTIF ≥ 9 pts below carrier median; freight cost/unit +14% |
| 7 | **Forecast model failure** | −7 → 0 | Industrial Components systematically under-forecast | Category forecast bias ≤ −18%; emergency PO count 3×; category stockout rate ≥ 2× company |
| 8 | **Safety-stock policy change** | −4 onward | Planner raises safety stock 40% on 300 A-class SKUs | Their inventory value +22–28%; their stockout rate −1.2 pts; working capital +$6M — *net-negative trade, and the data should show it* |
| 9 | **Product substitution** | −6 onward | Demand shifts from Nimbus N3 → N4 | N3 demand −45%, N4 +60%; N3 days-of-supply > 180; N4 stockout rate ≥ 12% |
| 11 | **Cost inflation** | −12 onward | Raw-material category unit cost +18% stepped over 4 quarters | Category unit cost +16–20%; gross margin on affected SKUs −4.5 pts |
| 12 | **New DC ramp** | −8 | Phoenix DC opens; SKUs reallocated | Phoenix inventory 0 → $4M; West region fill rate dips 3 pts then recovers within 3 months |
| 13 | **Labour shortage** | −3 → −1 | Two DCs run at 70% pick capacity | Their outbound line-fill −6 pts; order-to-ship cycle +1.8 days |
| 14 | **Obsolescence** | −10 onward | 60 end-of-life SKUs keep stock, lose demand | Their demand → near 0; inventory holds; obsolete inventory value ≥ $2.2M at as-of |
| 15 | **Planner override win** | −6 onward | Overrides on 90 Y-class SKUs beat the ML forecast | Planner Override MAPE ≥ 6 pts better than ML on those SKUs — *and worse on 30 others, so the answer is not "overrides are always good"* |

---

## Notes on the ones that are easy to get wrong

**Event 8 must be net-negative.** The design note frames it as
*"Was the decision worth it?"* — that only works if the honest answer is
*"no"*. $6M of working capital to buy 1.2 points of stockout reduction on SKUs
that were not the ones stocking out. If the numbers are tuned so the policy
change looks good, the question has no tension and the demo flow dies at step 5.

**Event 15 must cut both ways.** *"Where are planner overrides improving
accuracy?"* is a weak question if the answer is "everywhere". 90 SKUs where
overrides help and 30 where they hurt makes the answer specific, and it makes
the follow-up — *"so which planners should we trust?"* — possible.

**Event 3 and Event 8 both inflate inventory, and that is the point.** The
executive headline is *inventory up 14%, service level down*. Event 3 puts the
money in slow movers; Event 8 puts it in the wrong A-class SKUs; Events 1, 5 and
6 starve the SKUs that are actually selling. The aggregate looks like one
problem and is really three, which is exactly what makes
*"why are stockouts increasing even though inventory is up 14%?"* a question the
AI has to decompose rather than look up.

**Events overlap on purpose.** Event 1 (S-104 disruption) sits inside Event 6
(port disruption) for Asia-sourced SKUs, and both touch SKUs affected by
Event 10 (single-source). Multipliers compose, the way they would in a real
business. The consequence for the validator: assertions must be written against
the *combined* expected effect on shared SKUs, not the isolated event.

---

## The executive headline these events must produce

Everything above is tuned to land on this, at the as-of date:

> Revenue **+6%** YoY. Inventory **+14.2%**. Fill rate **93.4%** (−2.1 pts).
> OTIF **87.2%** (−6.8 pts). Stockout rate **4.8%** (+1.7 pts).
> Forecast accuracy **81.6%** (−4.3 pts).

The validator's final check asserts these six numbers land within tolerance. If
they do not, the events need retuning — not the dashboard.
