# Project Audit — Multiplex Screen Scheduling (pre-final review)

> **Scope.** This audit covers the whole implementation as it stands on branch `ramesh` (uncommitted working tree, 12 Oct 2026). It checks it against three things:
> - the professor's brief,
> - the first-review PPT (`ppt_or.pptx`),
> - the course syllabus.
>
> It answers two questions: *is this a strong, genuine OR project?* and *what is still missing or should change before the final review?*
>
> **Nothing in the repo was modified.** All checks and experiments ran on a copy in a scratch environment.

---

## Status update — recommendations implemented (12 Oct 2026)

| Item | Status | Where | Result |
|---|---|---|---|
| A1 User interface | ✅ Done | `app/` (Streamlit, 12 pages), `tests/test_app.py` | Load data + statistics on demand; each of M1–M4 solvable on its own page; what-if; compare; sensitivity lab; final plan export; source and `.lp` viewer |
| A2 Final deck | ⏳ Open | — | Still to do (Phase 9) |
| A3 Commit | ✅ Done | branch `ramesh` | Work committed (not pushed) |
| B1 Price of the variety policy | ✅ Done | notebook 6.4 + 12.6 (S6); app Sensitivity lab | The 8-film rule costs ₹44,251/day (9.5%); free up to 6 films |
| B2 Fees and budget halved | ✅ Done | `engine/config.py`; notebook Section 14 | Identical decisions in 14/14 checked runs (plus 36 runs in development); weekly gross / licensing 0.72 → 1.46 |
| B3 Film-level quotas | ✅ Done | `engine/models.py` (`quota_rule='film'`) | Price of balance 1.47% → **0.83%** (the 0.42% in Appendix A came from a probe that solved to a different, equally optimal transportation plan); quota deviation 2 → 0 |
| B4 Honest framing | ✅ Done | notebook 9.3, 11.1, conclusion; app M4 and Compare pages | The weighted deviation is labelled as Model 4's own objective; the evidence is the per-goal changes |
| C1 AHP weights | ✅ Done | `engine/ahp.py`, `AHP_JUDGMENTS`; notebook 9.1; app M4 page (interactive) | CR = 0.004; weights G1 0.399 · G6 0.190 · G5 0.170 · G2/G3 0.095 · G4 0.051; same schedule as before this week |
| C2 Sensitivity reports | ✅ Done | `engine/analysis.py`; notebook 6.4, 7.2; app M1/M2 pages | Exact ranging from the LP optimality conditions, verified by brute-force re-solves in `tests/test_engine.py`; shows alternative optima in Model 2 |

Final main-week numbers: R\* ₹4,19,711; final plan ₹4,16,230 (+61.8% vs naive); 9 of 10 test weeks won; all schedules pass validation. The engine reproduces the first version's numbers exactly when run with `PRE_REVIEW_OVERRIDES` (tested).

---

## 0. Verdict at a glance

**Overall.** The OR core is **complete, strong and genuine**. Four correctly formulated models, solved exactly, chained in code, validated, benchmarked against two baselines, and stress-tested end to end. The honesty of the reporting is unusually good for a semester project.

The **project as a deliverable is not complete yet.** The professor's brief requires a **user interface**, and none exists. The final presentation is also not prepared yet. No rebuild is needed: four moderate fixes (Section 5B) plus two course-aligned additions (Section 5C) would make the model side strong in a viva.

| Component | Status | Completion |
|---|---|---|
| Data loading, cleaning, weekly market, demand model | Done, verified | ✅ ~100% |
| Model 1 Knapsack (ILP) + greedy + LP relaxation + budget sweep | Done; one framing gap (B1) and one economic inconsistency (B2) | ✅ ~95% |
| Model 2 Transportation (LP) + TU integrality + duals/MODI | Done; quota aggregation weakness (B3); no ranging report (C2) | ✅ ~90% |
| Model 3 Assignment (binary ILP), Gantt, validator | Done | ✅ ~100% |
| Model 4 Weighted Goal Programming (MILP) | Done; one circular claim (B4); weights ad hoc (C1) | ✅ ~90% |
| Validation, baselines, revenue bridge, chain verification | Done | ✅ ~100% |
| Sensitivity S1–S5 (end-to-end) + multi-week robustness | Done | ✅ ~100% |
| Reproducibility (pinned deps, generated narrative, exports) | Done; **work not committed** | ✅ ~95% |
| **User interface** (load data, stats on demand, ≥ 2 user-chosen optimisations) | **Not started** | ❌ 0% |
| **Final presentation** (results, methodology, UI demo, code) | Only the first-review deck exists | ❌ ~10% |

**Top actions, in order:**

1. Commit the current work.
2. Apply the four "should-fix" items (Section 5B). They are small, and two of them change nothing in the decisions.
3. Optionally add AHP weights and an LP sensitivity report (5C).
4. Build the UI (see `UI_PLAN.md`).
5. Build the final deck.

---

## 1. How this audit was done

1. **Read** all 69 notebook cells (code, markdown and saved outputs), the README, `requirements.txt`, `.gitignore`, `outputs/` and the first-review PPT.
2. **Re-ran** the notebook headlessly in a fresh, isolated environment (Python 3.13.5, pandas 2.3.1, numpy 2.5.2, **PuLP 2.9.0**).
   - Every headline number reproduced exactly: R\* = ₹4,19,711, final = ₹4,13,524, +60.7% vs naive, 9/10 weeks.
   - Full run ≈ 43 s (≈ 13 s of that is library import); one end-to-end chain ≈ 0.4–1.5 s.
3. **Ran probe experiments** using the notebook's own functions, to test concerns that only show up when you read the final schedule closely (Appendix A).
4. **Mapped** the work against the professor's brief, the PPT promises and the syllabus.

---

## 2. Requirement coverage

### 2.1 Professor's brief

| Requirement | Status | Notes |
|---|---|---|
| Publicly available dataset | ✅ | TMDB 5000 (Kaggle) |
| Optimisation using course techniques | ✅ | ILP knapsack, transportation LP, assignment ILP, goal programming |
| **UI: data can be loaded** | ❌ | Notebook only (path in CONFIG) |
| **UI: statistics about the data generated on demand** | ❌ | EDA is fixed in the notebook, not on demand |
| **UI: at least two optimisations, chosen by the user** | ❌ | All four models run in a fixed sequence; there is no choice |
| Presentation: what / why / dataset / questions / methodology / results / interpretation / conclusion | ⚠️ | All the *content* exists in the notebook. The deck is still the first-review version (3-model chain, no results) |
| Presentation: UI and code shown | ❌ | Depends on the UI |

### 2.2 First-review PPT commitments

Every commitment from the first review is now implemented: the 4-model chain, cleaning 4,803 → 2,571, weekly synthesis with λ-decay, the demand bridge formula, all M1/M2/M3 constraints, the goal-attainment report, the naive baseline, the hard-constraint check, sensitivity on λ and budget, Gantt and idle time.

Slide 13's limitation "end-to-end re-optimisation is future work" has been **removed by doing it** (S1–S5).

Two assumptions were changed, both justified and documented in the notebook:
- the late slot moved from 23:00 to 00:00, so every slot is 180 min;
- the budget is now binding.

### 2.3 Syllabus coverage

| Syllabus topic | Used? | Where / how well |
|---|---|---|
| LP formulation & solution | ✅ | M2 transportation, M1 LP relaxation |
| LP sensitivity analysis, *interpretation of sensitivity reports* | ⚠️ Partial | Duals (shadow prices), reduced costs, MODI check, binding-constraint table, parametric sweeps. **Missing: a Solver-style report with allowable increase/decrease (ranging)** → C2 |
| Transportation & transshipment — formulation, solution, *sensitivity* | ✅ (sensitivity partial) | Balanced transportation, dummy column for dark screens, TU ⇒ integral, MODI potentials. VAM/MODI hand iterations not shown (optional D4) |
| Assignment models with different constraints | ✅ Strong | 3-index assignment with 7 side-constraint families (C1–C7) |
| Integer programming / knapsack | ✅ Strong | 0/1 knapsack with count, coverage and forced-zero constraints; greedy vs ILP vs LP bound; integrality gap |
| Goal programming | ✅ Strong | 6 normalised goals, linearised ratio goals, binary diversity indicators, weight trade-off curve |
| **AHP (formulation, solution, consistency check)** | ❌ | **A natural fit:** derive the GP weights by AHP instead of by judgement → C1 |
| Network models, NLP, other specialised IPs | — | Not needed; don't force them in |

---

## 3. Is it a strong OR project? — Yes. Strengths, with evidence

1. **Real decomposition with real hand-offs.** Each model's output is consumed *in code* by the next, and an automated chain-verification table checks it (Section 10: 6/6 hand-offs verified).
2. **Every model does non-trivial work.**
   - **M1:** the budget binds (₹39.99 L of ₹40 L). The greedy value/fee rule is **infeasible**: it picks 6 films and breaks the 8-film minimum. The LP relaxation gap is 4.77%, with fractional Lucy/Maleficent.
   - **M2:** the solution is integral without integer constraints (total unimodularity, explained correctly). The MODI optimality check passes. It saves ₹38,706/day (23%) of mismatch cost against a proportional split.
   - **M3:** 240 binaries and 105 constraints, solved to proven optimality in 0.05 s. The C4 cap binds for 5 films, and C5 binds for 2.
   - **M4:** a genuine trade-off. It gives up 1.47% of revenue and changes 22 of 30 cells. The solver's deviations are re-computed from the schedule and asserted equal.
3. **Feasibility is proven, not assumed.** One `validate_schedule()` runs 9 checks on every schedule (M3, M4, B1, B2) and on every sensitivity run.
4. **Fair evaluation.** All schedules share one demand model and one KPI function. Two baselines are used:
   - naive (B1), the one promised in the PPT;
   - greedy (B2), which is the *honest* benchmark.

   A revenue bridge separates the selection effect from the scheduling effect.
5. **End-to-end sensitivity and robustness.** λ, budget, demand scale ±30%, GP weight frontier, and 10 weeks chosen by a fixed rule. Every setting is fully re-optimised and re-validated.
6. **Reproducible and self-documenting.** CONFIG holds every assumption; deps are pinned; all narrative numbers are generated in code; the exports match the run.

---

## 4. Is it genuine? — Yes. Integrity review

**Genuine:**
- No hard-coded results.
- A fresh re-run reproduces every number.
- `DEMAND_SCALE` was calibrated *before* any comparison: the smallest value inside a declared occupancy band, with the grid shown. It was then frozen and swept ±30%.
- **Negative findings are reported, not hidden:**
  - greedy matches M3 on revenue (+0.0% this week; +0.39% on average across weeks);
  - M1 loses to naive at ₹35 L;
  - naive wins in 1 of 10 weeks (it would be over budget there).

**Engineered, but legitimate because declared:**
- GP targets = "M3 + one step". This guarantees the goals conflict, so M4 can't simply return M3. Acceptable as aspiration levels; it is stated in the notebook.
- B1 uses raw popularity and ignores decay, so the **+60.7% headline is mostly "use decay-aware demand"**. The notebook makes this transparent with B2 and the revenue bridge; keep presenting it that way.

**Over-claims to fix (narrative only; see B4):**
- "Where the optimisation clearly wins is the multi-goal balance: weighted deviation 0.030 (M4) vs 0.305 (M3) vs 0.356 (greedy)". This is **circular**. M4 is *by definition* the minimiser of that exact metric, and the targets were built from M3's own KPIs. It is not evidence that M4 is better; it is what M4 optimises.

---

## 5. Findings and recommendations

### A. Critical (must do for the final review)

| # | Finding | Action |
|---|---|---|
| **A1** | **No UI.** The brief requires a UI that loads data, generates statistics on demand, and runs ≥ 2 optimisations chosen by the user | Build it per `UI_PLAN.md` (Streamlit on an extracted `engine/` package) |
| **A2** | **Final deck not prepared.** `ppt_or.pptx` is the first-review deck (3-model chain, no results). The brief lists the required sections, plus the UI and code | Phase 9 of `IMPLEMENTATION_PLAN.md`: results slides, 4-model chain, UI screenshots/demo, code excerpts, viva Q&A |
| **A3** | **Work is uncommitted.** The notebook is modified, and `requirements.txt`, `outputs/` and the plan are untracked on `ramesh` | Commit now (and push the branch) before any further change |

### B. Should fix (moderate; small effort; these are what an examiner will probe)

**B1 — The cost of the "8–12 films" policy is invisible (framing gap).**
- *Evidence.* With λ = 0.55, films 5+ weeks old keep ~2–4% of their demand. Without the 8-film minimum, Model 1 would license 6 films (Tammy and Think Like a Man Too among them). With it, those two make way for **4 weak films** (Earth to Echo, Maleficent, Jersey Boys, Edge of Tomorrow). Together they cost **₹9.6 L of fees** and earn **₹270–₹12k a day each**. The final schedule has **8 shows with fewer than 10 viewers** (e.g. *Jersey Boys* at 9 am with 2 people, *Edge of Tomorrow* on the 250-seat screen three times).
- End to end, relaxing the minimum gives (Appendix A, P9):

  | `n_min` | R\* (₹/day) |
  |---|---|
  | ≤ 6 | 4,63,961 |
  | 7 | 4,61,144 |
  | **8 (current)** | **4,19,711** |
  | 9 | 3,74,925 |
  | 10 | 2,47,784 |

  So the rule costs **≈ ₹44,250/day**, about 9.5% of the revenue available without it.
- *Why it matters.* The first viva question on the final schedule will be "why show a film to 2 people?". The answer is a *policy constraint*, and an OR project should **price** its policy constraints.
- A related insight to state honestly: without the count rule, Model 1 picks exactly the films a simple *decay-aware ranking* would pick. **M1's value lies in satisfying the combinatorial side constraints (budget + count + coverage) exactly**, not in out-ranking a sensible ranking.
- *Fix (≈ 1 h).* Add one sensitivity experiment, **S6 "price of the variety policy"** (`n_min` 4…10, end to end), and one sentence each in the M1 interpretation and the conclusion. Decisions and headline numbers are unchanged.

**B2 — Weekly ticket revenue is below the licensing spend (economic inconsistency).**
- *Evidence.* The KPI table prints `weekly_gross_to_fee = 0.72`: ₹28.9 L of weekly gross against ₹40 L of fees. Per film, Lucy is 1.03, Dawn 0.93, … Maleficent 0.01. As modelled, the theatre loses money on licensing.
- The cause: the fee formula was calibrated only so that the budget binds.
- *Fix (≈ 30 min, decision-invariant — verified).* Scale `fee_floor`, `fee_premium` and `budget` by **α = 0.5**: fees ₹1–8 L, budget ₹20 L, budget sweep ₹12.5–27.5 L.
  - Because the knapsack constraint Σ f·y ≤ B scales linearly, this gives the **identical licensed set and identical R_M4**, and the budget sweep picks the same set at all 7 budgets.
  - The overall ratio becomes **1.45**.
  - (α = 0.4 or 0.3 is *not* invariant, because fees are rounded to ₹1,000.)
  - Document it as a units/consistency correction.
- *Alternative.* Keep ₹40 L but state explicitly that ticket revenue excludes F&B and distributor revenue-share terms. Weaker; the inconsistency stays visible.

**B3 — Model 2's quota is computed per genre, so it can force near-empty shows.**
- *Evidence.* The current quota gives Action **10** shows (2 films × K_MAX = 5) because Lucy alone carries 60% of total demand. But the second Action film (*Edge of Tomorrow*) draws 2–6 viewers per show.
- Goal G6 (follow the M2 plan, weight 0.20) then pushes M4 to show *Edge of Tomorrow* 4 times. **G6 is the main driver of M4's revenue sacrifice**: with G6's weight set to 0, the price of balance falls from 1.47% to 0.42% and occupancy *rises* above M3's.
- *Fix (≈ 1–2 h).* Water-fill the quota **per film** (each film clipped to [1, K_MAX]), then sum per genre.
  - Probe result: Action 10 → 7, Fantasy 6 → 7, Family 3 → 4, Music 1 → 2.
  - M4's price of balance drops from **1.47% to 0.42%**, and **G6 is met exactly** (deviation 0).
  - The few near-empty shows that remain are structural (B1), not artefacts.
  - Optionally weight the cost c_sg by each film's quota share instead of a plain average.
- *Integrity note.* This changes M2/M4 numbers. Record the before/after in the notebook as a post-review formulation correction. Calibration is unaffected.

**B4 — A circular "M4 wins" claim (narrative only).**
- *Evidence.* Section 11.1, S3/S5 and the conclusion cite "weighted goal deviation 0.030 (M4) vs 0.356 (greedy)" as proof that optimisation wins. M4 minimises exactly this quantity, and the targets are derived from M3.
- *Fix (≈ 30 min).* Present M4 as a **trade-off tool**:
  - report the *individual* KPI changes: prime genres 5 → 6, idle −7.3 min, quota deviation 41 → 2, at −1.47% revenue, −1.2 pt average occupancy and −3.2 pt prime occupancy;
  - point to the **S4 frontier** as the managerial output;
  - keep the weighted-deviation number, but label it "objective value (by construction lowest for M4)".

### C. Recommended additions (course alignment; moderate effort; high marks value)

**C1 — Derive Model 4's weights with AHP (syllabus: AHP with consistency check).**
- The notebook lists "weights are judgement calls" as a limitation. AHP is the course's own answer to that.
- Build a 6×6 pairwise comparison matrix of the goals (Saaty 1–9 scale). Compute the priority vector (principal eigenvector), λ_max, CI = (λ_max − n)/(n − 1) and CR = CI/RI with RI(6) = 1.24. Accept the weights if CR < 0.10.
- Use them as the GP weights. Keep the S4 sweep as robustness.
- Effort ≈ 2 h (small `ahp()` function + markdown). In the UI this becomes an interactive pairwise-comparison widget. This is the strongest single addition for the syllabus.

**C2 — A Solver-style sensitivity report for Model 2 (and the M1 LP relaxation).**
- The syllabus stresses "interpretation of sensitivity reports". The notebook already has shadow prices and reduced costs, but not **ranging**.
- Produce the two classic tables:
  - **Variable cells:** final value, reduced cost, cost coefficient, allowable increase/decrease.
  - **Constraints:** final value, shadow price, RHS, allowable increase/decrease.
- Implementation options:
  - **Recommended:** `highspy` (HiGHS) `getRanging()`. Exact, instant, one small dependency.
  - **Fallback:** parametric bisection using in-process `scipy.optimize.linprog(method="highs")` (scipy 1.18 is available).
- Add 3–4 interpretation sentences, e.g. "the Action–Screen 0 cost can rise by ₹X before the plan changes".
- Effort ≈ 2–3 h.

### D. Minor / optional (fine to ignore or mention as limitations)

| # | Finding | Suggestion |
|---|---|---|
| D1 | **G4 (idle time) is cosmetic under fixed slots.** It can only be lowered by choosing *longer* films (e.g. *Jersey Boys*, 134 min). Dropping it changes nothing in the base run (Appendix A, P6) | Keep idle time as a reported KPI (the PPT promised it). Either cut G4's weight or add one honest sentence: "with fixed slot starts, idle minutes have no direct cost; G4 is a tie-breaker towards fuller screen use" |
| D2 | **G3 counts a genre in prime time even if its show is nearly empty** (*Jersey Boys* at 9 pm, 6 viewers) | Optional: link z_g only to prime cells with occupancy ≥ θ (e.g. 20%) |
| D3 | M1's value proxy over-states weak films (*Maleficent*: value ₹7.4 k vs realised ₹1.1 k), because it assumes one show per slot on an average screen. Already disclosed in the notebook | Optional "net contribution" variant (7·v − f) as a what-if; not required |
| D4 | VAM + MODI iterations for M2 (the classroom algorithm) are listed as future work | Optional. Good as a step-by-step view in the UI |
| D5 | `outputs/` is untracked, but the README says outputs are exported | Decide: commit the figures used in the deck; keep CSVs regenerated |
| D6 | The notebook is 1.8 MB (embedded images) | Fine. Clear outputs only if the repo size matters |

### What should *not* change

- `DEMAND_SCALE = 650`: frozen by the calibration rule.
- The chain order and the four model families.
- The B1/B2 definitions.
- The calibration and target rules.
- The fixed 6-slot grid.

Changes B2 (invariant), B3 and C1 must be recorded as **post-review corrections**, with before/after numbers.

---

## 6. Recommended order of work

```
1. Commit current state (A3)
2. Model fixes in the notebook: B2 (scale fees) → B3 (film-level quota) → B1 (S6 policy sweep) → B4 (narrative)
3. Optional course additions: C1 (AHP weights) → C2 (sensitivity report)
4. Extract engine/ package from the notebook (UI_PLAN Phase U0) — notebook then imports it
5. Build the UI (UI_PLAN Phases U1–U8)
6. Final deck + viva notes (A2), using UI screenshots and the generated figures
```

Doing 2–3 *before* 4 means each fix is written once. Doing them after the engine extraction is also fine, as long as the notebook imports the engine; then each fix is still written once.

---

## 7. Viva risk list (likely questions the current results invite)

| Likely question | Answer, after the fixes |
|---|---|
| "Why does *Jersey Boys* play to 2 people?" | The 8-film variety policy plus "every licensed film is shown". S6 prices it at ≈ ₹44 k/day; the manager can relax it |
| "A greedy manager gets the same revenue — why use an ILP?" | For pure revenue, greedy is near-optimal here (≤ 0.9% gap across 10 weeks), and we report that. The ILP's value is: (i) proven optimality, which gives R\* as a bound; (ii) exact handling of side constraints (budget, count, coverage, C5–C7), which greedy breaks; (iii) the multi-goal trade-off in M4 |
| "Your theatre loses money on licensing" | Fixed by B2 (decision-invariant rescale); weekly gross/fee ≈ 1.45 |
| "Where do the goal weights come from?" | AHP with CR < 0.10 (C1), plus the S4 frontier showing all balances |
| "Why is the transportation solution integral?" | Total unimodularity with integer supplies and demands; the MODI check confirms optimality |
| "What if the cost of putting Action on Screen 0 changed?" | Read it off the sensitivity report's allowable increase/decrease (C2) |
| "Isn't +60.7% vs naive unfair?" | It is the baseline the PPT promised. The bridge splits it into selection (₹61 k) and placement (₹101 k), and B2 is the honest benchmark |
| "Is the main week cherry-picked?" | No. 10 weeks chosen by a fixed rule; wins in 9 (the loss is in a week where the naive plan is over budget) |

---

## Appendix A — Probe evidence (scratch runs using the notebook's own functions)

| Probe | Result |
|---|---|
| P0 Reproducibility | Fresh run: identical R\* ₹4,19,711, M4 ₹4,13,524, lift +60.7%, S5 9/10, all asserts pass; 43 s total |
| P1 Near-empty shows | M4 has 8 shows with < 10 viewers (M3 has 5). *Edge of Tomorrow*: 4 shows in M4 (1 in M3), 3 of them on the 250-seat screen. *Jersey Boys* at 9 pm, 6 viewers |
| P2 Economics | Weekly gross ₹28.9 L vs fees ₹40.0 L → 0.72. Per film: Lucy 1.03, Dawn 0.93, Deliver 0.87, HTTYD2 0.51, Earth 0.17, Edge 0.07, Jersey 0.06, Maleficent 0.01 |
| P3 Fee and budget scaling | α = 0.5: same licensed set, same R_M4 (₹4,13,524), same set at all 7 budgets in the sweep, gross/fee 1.45. α = 0.4 / 0.3: not invariant (₹1,000 fee rounding) |
| P4 Film-level quota | Quotas: Action 7, Fantasy 7, Science Fiction 5, Thriller 5, Family 4, Music 2. M4 price of balance 0.42% (was 1.47%); G6 met (deviation 0); near-empty shows unchanged (structural) |
| P5 M4 vs M3 per KPI | Revenue −1.47%, average occupancy 36.6 → 35.4%, prime occupancy 54.6 → 51.4%, prime genres 5 → 6, idle 58.0 → 50.7 min, quota deviation 41 → 2, spill unchanged |
| P6 Drop one goal | Without G6: price of balance 0.42%, occupancy 37.6%, prime 54.3%. Without G4: no change. Without G3: price of balance 1.39% |
| P8 Timing | M1 0.12 s · M2 0.66 s · M3 0.15 s · M4 0.23 s · full chain ≈ 1.5 s · load + clean 2.5 s (cache it in the UI) |
| P9 `n_min` sweep | R\*: ≤ 6 → ₹4,63,961; 7 → ₹4,61,144; 8 → ₹4,19,711; 9 → ₹3,74,925; 10 → ₹2,47,784 |
| P10 Decay-aware ranking | Films taken by effective demand within the budget (6 films, ₹38.5 L), optimally placed: ₹4,63,961 = the ILP result when `n_min` ≤ 6 (but it breaks the 8-film rule) |
