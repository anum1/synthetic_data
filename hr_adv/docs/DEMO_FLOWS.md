# Demo flows

**GlobalTech — HR / Workforce Analytics**

Five dashboard pages, one scripted flow, and 50 questions the dataset can
actually answer. Every number quoted below is **measured from the small tier**,
not written from intent — regenerate and run `src/run_questions.py` to reproduce
them. Absolute figures move a little with the as-of date; the relationships
between them are what the events guarantee.

---

## The headline

At the as-of date the executive row reads:

| KPI | Value |
|---|---:|
| Headcount | **6,000** (+2.8% YoY) |
| Total workforce cost, last 12 months | **$977M** (**+9.6%** YoY) |
| Average salary | $124,940 (+3.0%) |
| Voluntary attrition | 12.0% |
| Regrettable attrition | 5.8% |
| Benefits per employee | $9,876 (+13.3%) |
| Average compa-ratio | 0.976 |

Workforce cost is up **9.6%** while headcount is up **2.8%**. That gap is the
whole demo. Every flow below is a different way of answering *why*.

---

## The scripted flow

### Step 1 — "Cost is up three times faster than headcount"

Open the Workforce Executive page. Headcount is up modestly, attrition looks
ordinary, and total cost is up nearly 10%. Nothing on this page says where to
look, which is the point.

Ask the killer question.

### Step 2 — The bridge (**Q11**)

`fact_workforce_cost_bridge` answers it as a table, not a calculation:

| Component | $M | Contribution |
|---|---:|---:|
| Rate (merit, promotion, market) | 40.3 | **+4.33%** |
| Volume (headcount) | 23.4 | +2.51% |
| Benefits | 10.3 | +1.10% |
| Other (commission, allowance, employer tax) | 8.8 | +0.94% |
| Bonus | 6.8 | +0.73% |
| Overtime | 0.1 | +0.01% |
| **Mix** | **−0.6** | **−0.06%** |
| **Total** | **89.0** | **+9.57%** |

Two things to say out loud here.

**It sums exactly.** Every line is divided by prior-period total cost, so the
column adds to the headline by construction. `validate.py` asserts it closes to
0.0001pt, at company level and inside every function.

**Mix is negative.** Hiring is weighted towards India, so average cost per FTE is
falling even while everybody's pay rises. That is also why *average salary* is up
only 3.0% while the *rate* people actually received is up 4.3% — a distinction
most HR dashboards quietly get wrong.

### Step 3 — "Rate is the biggest line. Where?" (**Q12**)

The same bridge by function. Engineering carries it. Drill in.

### Step 4 — "Why is Engineering's rate up so much?" (**Q18, Q19**)

Two reasons in `fact_salary_history`: a promotion wave (Event 4, 2.2× the
company promotion rate in one month), and market adjustments chasing a range
that is moving at 6.2% a year.

Then the turn: **if ranges are moving that fast and merit is not, what happened
to everyone who did not get promoted?**

### Step 5 — Compression (**Q13, Q14, Q20**)

**30.3%** of Engineering now sits below 0.90 compa-ratio, against **9.6%** in the
rest of the business. Q14 shows the mechanism directly — within the same job
family, new hires arrive above midpoint while three-year incumbents sit below it.

Nobody was tagged as compressed. It accumulated out of a capped merit budget
fighting a fast-moving range.

### Step 6 — "Does that cost us anything?" (**Q41**)

This is the moment the demo is built around.

| Segment | Avg headcount | Voluntary exits | Rate |
|---|---:|---:|---:|
| **High performer, below 0.90 compa** | 274 | 100 | **36.5%** |
| Other, below 0.90 compa | 737 | 198 | 26.9% |
| High performer, paid at market | 1,104 | 126 | 11.4% |
| Everyone else | 3,831 | 292 | 7.6% |

A **4.8× spread**. Underpaying good people costs almost five times the
resignation rate of paying them properly — and because the mechanism is a real
hazard model rather than a tag, this holds up under any cut the audience asks
for.

### Step 7 — The named list (**Q43**)

`fact_workforce_risk` scores every current employee from the same drivers the
simulation actually used. Filter to Critical risk and regrettable-if-lost, and
you have a list a manager can act on this week, each row carrying its own
`primary_risk_driver`.

### Step 8 — The manager problem (**Q38 vs Q39**)

Rank managers by raw attrition (**Q39**) and the Sales attrition event puts Sales
leaders at the top. Rank them by **excess over their own function** (**Q38**) and
one manager separates from the pack: **30.0% voluntary attrition over 87 people,
2.9× the company rate**, with depressed ratings and double the absence (**Q40**).

That contrast is worth doing deliberately. It is the difference between a
dashboard that lists numbers and one that answers a question.

### Step 9 — The payroll anomaly (**Q25**)

Nobody is told where it is. Group overtime by unit and month, compare against
each unit's own median, and one cell comes back at **9.2× normal** — including
exempt staff, which is what makes it an error rather than a busy month.

### Step 10 — "How clean is this data, really?" (**Q50**)

One query, five planted defects: duplicate person records inflating headcount,
active employees with no manager, cost centres in two conventions after the
acquisition, payroll that kept running after people left, and inconsistent name
casing. A good place to end, because every prospect believes their own data is
worse than the demo's.

---

## The five pages

### Page 1 — Workforce Executive
Headcount and FTE trend, headcount by function and geography, attrition trend,
hires vs terminations, tenure profile, span of control.
**Questions 1–10.**

### Page 2 — Compensation
The cost bridge, compa-ratio distribution, salary against range (min / mid /
max / actual), compression by job family, pay vs performance, what drove salary
growth.
**Questions 11–21.**

### Page 3 — Payroll & Workforce Cost
Cost by component, by function and country, the monthly trend, the overtime
anomaly, cost per FTE by division, pay-frequency mix, and the payroll-to-
compensation reconciliation.
**Questions 22–30.**

### Page 4 — Benefits
Cost per employee and its growth, cost by benefit type and plan year, medical as
a share of the book, cost by country, fastest-growing plans, coverage mix, and
what the acquisition added.
**Questions 31–37.**

### Page 5 — Workforce Risk / AI
Manager scorecard (raw and function-benchmarked), the high-performer attrition
finding, the risk register by driver, the named critical-risk list, exit reasons
against what the data says, and absence hot spots.
**Questions 38–45.**

Plus **Questions 46–50** on organisation history, the acquisition, and data
quality.

---

## Running the questions

```bash
python3 src/run_questions.py --tier small
```

Every question is in `sql/demo_questions.sql`, written for DuckDB and portable
to Snowflake and Databricks with no change beyond the catalog prefix. All 50
return rows on both tiers; the runner fails loudly if any stops doing so.

For one question:

```bash
python3 src/run_questions.py --tier small --only 41
```

---

## Fifteen-minute version

If you have fifteen minutes rather than forty:

1. **Q11** — the bridge. Two minutes. It is the whole value proposition.
2. **Q13** — compression, 30% of Engineering below 0.90.
3. **Q41** — the 4.8× spread. This is the one people remember.
4. **Q38 vs Q39** — the manager problem, and why the obvious ranking is wrong.
5. **Q50** — data quality, to close.

Skip pages 3 and 4 entirely. They matter to a payroll or benefits audience and
to almost nobody else in a first meeting.
