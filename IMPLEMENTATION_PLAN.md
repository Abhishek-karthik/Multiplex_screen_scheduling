# Implementation Plan — Multiplex Screen Scheduling (OR Project, Group 14)

> **Purpose of this document.** This plan guides the rest of the implementation. It records what the first-review PPT committed to, what the code does today (checked by actually running it), what is missing or wrong, and a phased roadmap to a complete, defensible Operations Research project.
>
> **How to use it.** Read Sections 1–3 first. Confirm the decisions in Section 3. Then implement one phase from Section 7 at a time (e.g. *"Implement Phase 1 of IMPLEMENTATION_PLAN.md"*). Each phase has a clear "done when" check.

---

## 0. TL;DR

- **Most of the skeleton already exists.** Data cleaning, weekly market synthesis, and all four models (Knapsack → Transportation → Assignment → Goal Programming) are coded, as are a baseline and a sensitivity section.
- **But the models are not yet doing real OR work, and the evaluation can't be trusted yet.** The audit (Section 1.2) found:
  - Occupancy is capped at 100% for almost every film, so the models can't tell the good films apart.
  - The licensing budget never binds, so the knapsack is really just "pick the top 12".
  - The 9 pm prime-time slot is only 120 min long, so only 4 of 12 films fit.
  - The transportation cost is arbitrary.
  - Goal Programming returns exactly the same revenue as Model 3.
  - The baseline schedules shows that physically can't run.
  - Sensitivity uses proxies rather than re-optimising.
  - Much of the markdown is stale.
  - A fresh `pip install pulp` (v4.0) breaks the notebook.
- **The fix is targeted, not a rewrite.** Keep the pipeline and the PPT's structure. Correct the time grid, read the demand formula as *people* (capped by screen size), recalibrate fees, give Model 2 a real mismatch cost, tie Model 4 to Models 2 and 3, add a feasibility validator, fix the baselines, and re-run the whole chain for each sensitivity case. Every solve takes under 0.2 s, so this is cheap.
- **Nine phases** (0–8) plus an optional Phase 9 for final-review material.

---

## 1. Where we are — audit

### 1.1 PPT commitments vs. current code

| # | What the first-review PPT committed to | Slide | Status in code | Action |
|---|---|---|---|---|
| 1 | Clean TMDB: Released, vote_count ≥ 200, valid runtime/date (4,803 → 2,571) | 4–5 | ✅ Done, numbers match | Keep |
| 2 | Weekly market: `weeks_out`, `weekly_decay = exp(−λ·weeks_out)`, `effective_demand`, `market_status` | 5 | ✅ Done | Keep |
| 3 | Demand bridge: `synthetic_demand = effective_demand × slot_factor × genre_slot_affinity × demand_scale` | 12 | ⚠️ Treated as a *unitless occupancy* capped at 1.0. It saturates and doesn't depend on the screen | Read it as **persons**, capped by screen capacity (Section 4.1) |
| 4 | 5 screens 250/180/180/120/120; 6 slots; **180-min slots**; 20-min cleanup | 12 | 🐞 Slots at 21:00 and 23:00 leave only **120 min** for the 9 pm prime slot | Fix the time grid (Decision D1) |
| 5 | Prices ₹120–₹280 by slot; λ = 0.55; budget ₹40 L | 12 | ✅ | Keep |
| 6 | **M1 Knapsack**: budget, 8 ≤ films ≤ 12, content coverage, yᵢ = 0 for non-selectable films | 7 | ⚠️ Runs, but the budget never binds and it licenses 2 films that can't be scheduled | Recalibrate fees and value; force yᵢ = 0 for films that can't be scheduled |
| 7 | **M2 Transportation**: screen capacities, balanced genre demand, minimise capacity–demand mismatch → preferred genre per screen | 8 | ⚠️ Cost = \|capacity rank − genre rank\| (arbitrary); the output barely affects M3 | Show-slot transportation with a spill + empty-seat cost; quotas; duals (Section 4.3) |
| 8 | **M3 Assignment**: ≤ 1 film per cell, runtime fit, no simulcast, max showings, min screens per slot, preferred genre per screen | 9 | ✅ Mostly. ⚠️ A 5% "genre bonus" changes the objective; Drama coverage is silently skipped; a prime cell is left empty | Clean up constraints; every licensed film shown ≥ 1 time |
| 9 | **Goal-attainment report** (4th model: Goal Programming) | 2, 11, 14 | ⚠️ GP exists but gives the same revenue as M3; the idle-time metric differs between model and report; "avg_idle passed to M4" is not true in code | Redesign goals anchored to M3's optimum and M2's quotas (Section 4.5) |
| 10 | Baseline: naive top-5 popularity schedule | 10–11 | 🐞 Schedules physically impossible shows (Transformers, 165 min; a 130-min film in the 120-min 9 pm slot) | Feasible naive baseline + greedy baseline |
| 11 | "Check all hard constraints" | 11 | ❌ No validator | Add `validate_schedule()` |
| 12 | Sensitivity on λ and budget | 11 | ⚠️ Proxy only (sum over the pool, or the knapsack score). The budget curve is flat. It uses a different film minimum (5) than M1 (8) | Re-run the whole chain end to end (Phase 7) |
| 13 | Idle time per screen + Gantt chart | 11 | ⚠️ Cells 46–47 have no saved output; `gantt_chart.png` is from an older run | Regenerate from final schedule |
| 14 | Final one-day plan + revenue / occupancy / genre / goal report | 2, 11 | ⚠️ Exists, but the numbers in the markdown are hard-coded and stale | Generate the numbers from code |
| 15 | Chain diagram shows **Knapsack → Transportation → Assignment** (3 models) but slide 14 says "four models" | 6, 10, 14 | ⚠️ Inconsistent | Final deck shows the 4-model chain with GP |

### 1.2 Issues confirmed by running the current notebook

I ran the current code in an isolated scratch environment. Nothing in the repo was changed. Key evidence:

| Area | Finding | Evidence |
|---|---|---|
| Environment | `pip install pulp` now installs **PuLP 4.0**, which removed `LpVariable.dicts` → the notebook crashes at Model 1 | `AttributeError: type object 'LpVariable' has no attribute 'dicts'`; works with PuLP 2.9.0 |
| Stale outputs | The outputs saved in the notebook don't match what the code produces now | Saved: 30/30 cells, ₹8,53,948. Current code: **29/30 cells, ₹7,93,753** |
| Stale markdown | Text refers to week `2016-08-24` and 13 films (code: `2014-07-16`, 15 films); "Models 1–6", "Model 6", "set covering", "sequencing"; EDA text says "action-heavy … horror, mystery" (actual: Comedy is the largest genre); headline +22.7% vs +14.1% | Cells 07, 13, 23, 32, 53, 61 |
| Time grid | 9 pm slot = 21:00 → 23:00 = 120 min → only **4/12** licensed films fit the highest-priced slot; the 11 pm show ends at 01:30 | `Slot 9pm (120min): 4/12 films fit` |
| Demand saturation | `occ = min(demand × 15 × …, 1.0)` → Lucy is 100% full in all 6 slots; the top-5 films' knapsack scores are nearly tied (₹9.3–10.0 L); average occupancy is 75%, far above the ~25–40% usually reported for multiplexes | Demand table and Model 1 output |
| Screen size ignored | Occupancy doesn't depend on screen size, and revenue just scales with capacity. Nobody is ever turned away, so "capacity allocation" (M2) has nothing to optimise | `rev[i,j,s] = price × capacity × occ[i,j]` |
| Knapsack trivial | 12 films cost ₹29.2 L against a ₹40 L budget. The **count limit (≤ 12) binds, not the budget**. Budget sensitivity is flat from ₹30 L to ₹45 L | Model 1 and sensitivity output |
| Wasted licences | M1 licenses **Transformers (165 min)** and **Boyhood (164 min)**, which can't fit any slot (160-min max) → ₹4.89 L wasted; Drama coverage is then skipped in M3 | `Skipped impossible genre constraints: ['Drama']` |
| M2 weak | Screens 0 and 2 both get "Action" (only 2 Action films exist); the output is just "≥ 1 show of the preferred genre", so it hardly constrains anything | Transportation table |
| GP = M3 | GP revenue equals M3 revenue exactly (₹7,93,753); goals are trivially met or not in conflict | Goal report |
| Idle-time mismatch | GP's internal idle measure (≈ 45.9 min, d⁺₄ > 0) differs from the reported 40.2 min. The checklist says avg_idle is passed to M4, but the target is hard-coded at 45 | `d_plus[4] = 0.0196` while "achieved 40.2 ≤ 45" |
| Baseline infeasible | Naive top-5 includes Transformers (165 min) and schedules a 130-min film at 9 pm | Baseline cell |
| Content categories | "Family-friendly" includes all Comedies (e.g. R-rated *Tammy*, *22 Jump Street*); only the *primary* genre is checked | `FAMILY_GENRES = {'Adventure','Comedy','Animation','Family'}` |
| Housekeeping | `_validate.py` is a stale harness from the older 6-model version; `weekly_candidate_pool.csv` is generated but tracked; `scipy` is installed but unused | Repo |

### 1.3 What is already good and stays

- Cleaning pipeline and the weekly-market idea (new / running / catalogue / future), with λ-decay. This is a strong, defensible bridge from static TMDB data to weekly demand.
- The four-model decomposition and its order: selection → allocation → assignment → multi-objective reconciliation.
- PuLP + CBC tooling; the 5 screens × 6 slots structure; prices; λ = 0.55; ₹40 L budget; 8–12 films; max showings; min operating screens.
- The Gantt chart, heatmaps and baseline idea. These just need correct inputs.

---

## 2. Target end state ("complete" means …)

**Deliverables**

1. `multiplex_screen_scheduling.ipynb`: one clean notebook that runs top to bottom on a fresh kernel without errors. It follows the PPT flow, each model has a written formulation, and all numbers in the text come from code.
2. A final one-day operating plan: licensed films, a 5×6 film–screen–slot grid, clock times (start, end, cleanup), revenue, occupancy, genre coverage, idle time per screen, and a goal-attainment report.
3. Evaluation:
   - a hard-constraint validation table for every schedule;
   - baseline comparison (naive and greedy) against M3 and M4;
   - end-to-end sensitivity on λ, budget and demand scale;
   - a GP weight trade-off curve;
   - a robustness check across several schedule weeks.
4. `outputs/`: final schedule CSV, KPI tables, figures for the final review.
5. `requirements.txt` with pinned versions, and an updated `README.md`.
6. (Phase 9, optional) Results slides content and viva Q&A notes for the final review.

**Success criteria**

- Every model is non-trivial, meaning its constraints actually bind:
  - M1: the budget binds.
  - M2: high-demand genres go to big screens.
  - M3: capacity and runtime decide placement.
  - M4: at least one goal visibly trades off against revenue.
- Every model's output is consumed by the next model in code, not just described in text. Section 6 has a chain-verification table.
- All produced schedules pass the validator; the baselines are feasible.
- Conclusions hold across sensitivity ranges and across weeks, not just for one hand-picked setting.

---

## 3. Decisions to confirm before implementing

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | **Fix the time grid** (9 pm → 11 pm is only 120 min) | **(B)** 09:00, 12:00, 15:00, 18:00, 21:00, **00:00** (uniform 180-min slots; the 6th slot becomes a "late-night 12 am" show)  •  (A) 08:00, 11:00, 14:00, 17:00, 20:00, 23:00  •  (C) keep as is and document the 9 pm limit | **B.** Changes only one label, keeps 9 am and the 6 pm/9 pm prime slots the PPT and GP use, and matches the PPT's own "180-minute slots, runtime ≤ 160" assumption. Lower the late slot's demand factor 0.80 → ~0.65 to reflect midnight. |
| **D2** | **Demand units** | (a) persons, capped by screen capacity  •  (b) keep the unitless occupancy | **(a).** Same PPT formula, but `demand_scale` is in people. This makes screen size matter, creates spill, and makes M2 meaningful. |
| **D3** | **Code organisation** | (a) one notebook, each model written as a function inside its section  •  (b) notebook + `src/` package | **(a).** Examiners read the notebook; functions allow `run_pipeline()` for sensitivity without splitting files. |
| **D4** | **Main schedule week** | keep `2014-07-16` (15 candidates: Lucy, Dawn of the Planet of the Apes, How to Train Your Dragon 2 …)  •  another week | **Keep**, and add a multi-week robustness test (Phase 7). |
| **D5** | **Optional extras** (only if time permits) | lexicographic GP • VAM/MODI demo for M2 • daily-demand cap (cannibalisation) • ipywidgets week picker | Decide after Phase 6. None are needed for a complete project. |

---

## 4. Revised model design (the OR core)

**Notation used throughout**

```
i ∈ F        candidate films (8-week window, released, schedulable);  F_L ⊆ F licensed films (M1 output)
j ∈ T        time slots {0..5}; T_prime = {18:00, 21:00}
s ∈ S        screens {0..4}, capacity C_s ∈ {250, 180, 180, 120, 120}
g ∈ G        genres (primary genre g(i))
P_j          ticket price of slot j        σ_j  slot demand factor       α_{g,j}  genre–slot affinity
L_i          runtime of film i              B = 20 min cleanup            Λ = 180 min slot length
e_i          effective_demand = popularity_norm_i · exp(−λ · weeks_out_i)
```

### 4.1 Demand model (PPT slide 12 formula, read as persons)

```
D_ij     = DEMAND_SCALE · e_i · σ_j · α_{g(i),j}        persons who want film i at slot j
att_ijs  = min(D_ij, C_s)                               seats sold if shown on screen s
occ_ijs  = att_ijs / C_s                                occupancy (now depends on screen)
rev_ijs  = P_j · att_ijs                                ticket revenue
spill_ijs= max(D_ij − C_s, 0)                           people turned away
fits_i   = (L_i + B ≤ Λ)                                schedulable (runtime ≤ 160 min)
```

- **Calibration rule** (fix this *before* looking at the comparisons): choose `DEMAND_SCALE` so that (i) the optimised schedule's average occupancy is about 35–45%, and (ii) the strongest film's prime-time demand exceeds the 250-seat screen, so spill exists.
  - Scratch prototype, current week: 550 → 34% average / 50% prime; 700 → 41% / 58%.
  - **Start at ≈ 600.**
- Extend `GENRE_AFFINITY` to every genre in the pool. Science Fiction, Fantasy, Thriller, Family, Animation, Drama, Music, Romance and others currently fall back to "Default".
- Build the content categories (action-like, family-friendly, regional) from the full TMDB `genres` list, not just the primary genre. "Family-friendly" means the film has the *Family* or *Animation* genre.

### 4.2 Model 1 — Film selection (0/1 Knapsack ILP)

**Question:** with a ₹40 L weekly licensing budget, which films should we license?

```
Variables   y_i ∈ {0,1}
Maximise    Σ_i v_i · y_i
s.t.        Σ_i f_i · y_i ≤ BUDGET                              (budget)
            N_MIN ≤ Σ_i y_i ≤ N_MAX            (8 ≤ · ≤ 12)       (film count)
            Σ_{i ∈ Action-like} y_i ≥ 1                         (coverage)
            Σ_{i ∈ Family-friendly} y_i ≥ 1                     (coverage)
            Σ_{i ∈ Regional} y_i ≥ 1     only if any exist        (coverage)
            y_i = 0   for every film with fits_i = False           (PPT: "non-selected films yᵢ = 0")
```

- **Value** `v_i = Σ_j P_j · min(D_ij, C_ref)` with `C_ref = 170` (average screen). This is "daily revenue potential of one show per slot on an average screen". It is still a ranking proxy, but it no longer saturates and it is on the right scale.
- **Fee (weekly minimum guarantee)** `f_i = FEE_FLOOR + FEE_PREMIUM · e_i`, so fresh, popular films cost more, as with real distributor terms.
  - Start at FEE_FLOOR = ₹2 L and FEE_PREMIUM = ₹25 L. That gives fees of ₹2.1–16 L; all 13 schedulable films together cost ₹55 L, which is more than the budget.
  - Prototype result: at ₹40 L the budget binds (8 films, ₹40.0 L spent); at ₹25–30 L the model has to drop Lucy; at ₹50 L it licenses 10.
- **Supporting analysis** (cheap, high-value OR content):
  - Greedy value/fee heuristic. The prototype shows greedy breaks the 8-film minimum, so it is infeasible: side constraints are exactly why an ILP is needed.
  - LP relaxation and the integrality gap.
  - A budget sweep, with the marginal value per extra ₹5 L as a shadow-price-like measure.
- **Output → M2, M3, M4:** `licensed_films` (with `fee`, `value`).

### 4.3 Model 2 — Screen–genre capacity planning (Transportation LP)

**Question:** how should the 5 screens' daily show capacity be split across genres so that large screens carry the high-demand genres?

Unit of flow = **show-slots** (one screen for one slot). Supply = 6 per screen (30 in total). Screen capacity enters through the cost.

```
Variables   x_sg ≥ 0              shows of genre g placed on screen s
Minimise    Σ_s Σ_g c_sg · x_sg
s.t.        Σ_g x_sg = 6        ∀ s     (supply: every screen-slot planned)
            Σ_s x_sg = b_g      ∀ g     (demand: genre show quota; Σ b_g = 30 → balanced)
```

- **Genre quota** `b_g`: share of total genre demand `E_g = Σ_{i∈g} Σ_j D_ij`, rounded with the largest-remainder method so that the quotas sum to 30.
  - Then clip to `[n_g, K_MAX · n_g]`, where `n_g` = licensed films in genre g, and redistribute what is left over. Without this clip, the Action quota came out at 15 in the prototype, but 2 Action films × 5 shows = 10 at most.
- **Mismatch cost** `c_sg` = expected ₹ cost of putting a genre-g show on screen s, averaged over that genre's (film, slot) demand values:
  `c_sg = mean_{i∈g, j} [ P_j · max(D_ij − C_s, 0)  +  h · max(C_s − D_ij, 0) ]`
  - The first term is lost ticket revenue from people turned away; the second is the cost of empty seats, with h ≈ ₹20 per empty seat-show (declared assumption).
  - This is exactly the PPT's "capacity–demand mismatch".
  - Prototype: Action went to the 250- and 180-seat screens, and low-demand genres to the 120-seat screens.
- **OR talking points:** the solution is integral without integer constraints, because the transportation matrix is totally unimodular. The **dual values** give the marginal value of one extra show-slot on each screen and the marginal cost of each genre's quota.
- **Outputs:**
  - `x_sg` quota matrix → soft goal in M4.
  - `preferred_genre[s] = argmax_g x_sg` → hard constraint in M3, as in the PPT.
- **Edge case:** if no genre ever exceeds any screen's capacity, every allocation costs the same. That correctly means "screen size doesn't matter this week". Note it and break ties by demand rank.

### 4.4 Model 3 — Film–screen–slot assignment (Binary ILP)

**Question:** which licensed film plays on which screen, in which slot, to maximise ticket revenue?

```
Variables   a_ijs ∈ {0,1}      i ∈ F_L
Maximise    R = Σ rev_ijs · a_ijs
s.t.  C1  Σ_i a_ijs ≤ 1                      ∀ j,s   at most one film per screen-slot
      C2  Σ_s a_ijs ≤ 1                      ∀ i,j   no simultaneous simulcast
      C3  a_ijs = 0  if L_i + B > Λ                  runtime + cleanup must fit
      C4  Σ_{j,s} a_ijs ≤ K_MAX (=5)         ∀ i     max showings per film
      C5  Σ_{j,s} a_ijs ≥ 1                  ∀ i∈F_L every licensed film is shown (we paid for it)   [new]
      C6  Σ_{i,s} a_ijs ≥ M_MIN (=4)         ∀ j     minimum operating screens per slot
      C7  Σ_{i: g(i)=g*(s)} Σ_j a_ijs ≥ 1    ∀ s     screen shows its M2 preferred genre  (M2 → M3)
```

- **Remove** the 5% "genre bonus" from the objective (M3 becomes pure revenue; quota-following moves to M4). Remove the separate genre-coverage constraint, which C5 already implies.
- **Outputs:** the optimal revenue **R\*** (→ M4 goal target), the schedule, KPIs, and a Gantt chart. These are the "revenue-only optimum".

### 4.5 Model 4 — Multi-objective reconciliation (Weighted Goal Programming MILP)

**Question:** what final schedule best balances revenue against occupancy, prime-time performance, diversity, screen utilisation and the M2 capacity plan, and how much revenue does that balance cost?

Hard constraints = **C1–C7** from M3. Goals use normalised deviations (d⁻ = under-achievement, d⁺ = over-achievement, all ≥ 0):

```
G1 Revenue        Σ rev·a / R*                                   + d1⁻ − d1⁺ = 1     penalise d1⁻   (R* from M3 → "revenue sacrificed")
G2 Avg occupancy  Σ (occ_ijs − τ_occ)·a_ijs / 30                 + d2⁻ − d2⁺ = 0     penalise d2⁻   (linearised ratio: avg ≥ τ ⇔ Σ occ·a ≥ τ·Σ a)
G3 Prime-time     Σ_g z_g / τ_div ,  z_g ≤ Σ_{i∈g, j∈T_prime, s} a_ijs, z_g ∈{0,1}
   genre diversity                                               + d3⁻ − d3⁺ = 1     penalise d3⁻
G4 Idle time      Σ_{j,s} [Λ − Σ_i (L_i + B)·a_ijs] / (30·τ_idle) + d4⁻ − d4⁺ = 1    penalise d4⁺
G5 Prime-time occ Σ_{j∈T_prime} (occ_ijs − τ_prime)·a_ijs / 10   + d5⁻ − d5⁺ = 0     penalise d5⁻
G6 M2 quota       Σ_{i∈g} Σ_j a_ijs − x_sg = e⁺_sg − e⁻_sg  ∀ s,g;  dev6 = Σ (e⁺ + e⁻) / 30      penalise dev6   (M2 → M4)
Minimise   w1·d1⁻ + w2·d2⁻ + w3·d3⁻ + w4·d4⁺ + w5·d5⁻ + w6·dev6
```

- **Why G3 changed:** C5 already guarantees every licensed genre appears, so "genres covered" is always met. Diversity *in prime time* actually competes with revenue.
- **One idle definition everywhere** (model and report): idle of a cell = Λ − L − B for a filled cell, Λ for an empty one. Also report **screen utilisation** = Σ runtime / (30·Λ).
- **Targets** (aspiration levels) are set by a declared rule after Phase 4:
  - G1: target R\*.
  - G2/G5: a few points above M3's achieved occupancy.
  - G3: ≥ 4 genres in the 10 prime cells.
  - G4: slightly better than M3.
  - G6: 0.
  - The aim is that the goals genuinely conflict. Otherwise GP just returns M3's schedule, which is the current problem.
- **Weights:** start at w = (0.40, 0.10, 0.10, 0.10, 0.10, 0.20), in the spirit of the PPT/notebook's 0.50/0.20/0.15/0.10/0.05. Then **sweep the revenue weight** 0.1 → 0.9 to draw a revenue-vs-balance trade-off curve.
- **Headline metric — "price of balance"** = (R\* − R_GP) / R\*: the percentage of revenue given up to meet the other goals.
- **Output:** the **final schedule** and the goal-attainment report (target, achieved, d⁻, d⁺, weighted deviation, met?).

---

## 5. Evaluation design

### 5.1 One KPI function and one validator for every schedule

`kpis(schedule)` returns:

- daily revenue, seats sold, average occupancy, seat-weighted occupancy, prime-time occupancy;
- spill (people turned away);
- genres covered, films shown, prime-time genre diversity;
- average idle per show, screen utilisation, empty cells;
- licensing cost of the films used, and M2 quota deviation.
- Optional: an approximate weekly ROI = 7 × daily revenue / licensing spend, clearly labelled.

`validate_schedule(schedule)` checks and reports pass/fail for:

1. ≤ 1 film per cell
2. runtime + cleanup ≤ slot length
3. no simulcast
4. showings ≤ K_MAX
5. ≥ M_MIN screens per slot
6. only licensed films
7. every licensed film shown
8. preferred genre on each screen

It runs on M3, M4 and both baselines (PPT: "check all hard constraints").

### 5.2 Baselines (same demand model, same KPIs)

| Baseline | Definition | Why |
|---|---|---|
| **B1 Naive popularity** (PPT) | Top-5 films by raw popularity among *schedulable* window films (ignores decay, budget and diversity), placed round-robin across the 30 cells | The "floor" the PPT promised; fixed so it is physically feasible |
| **B2 Greedy manager** | Sort (film, slot, screen) by revenue; fill cells greedily while respecting C1–C6 | Shows how much of the gain comes from *optimisation* rather than from simply being sensible. Makes the claims honest. |

Compare **B1, B2, M3 and M4** in one table and one chart (revenue, occupancy, prime-time occupancy, genres, spill, utilisation, violations).

### 5.3 Sensitivity and robustness (end to end)

`run_pipeline(config_overrides)` runs demand → M1 → M2 → M3 → M4 → KPIs and returns everything. Each run takes well under a second. This **removes the PPT's slide-13 limitation** ("end-to-end reoptimisation is future work").

| Exp. | Vary | Report |
|---|---|---|
| S1 | λ ∈ {0.25, 0.35, …, 0.85} | Final revenue (M4, M3, B1), films licensed, average age of licensed films |
| S2 | Budget ∈ {₹25 L, 30, 35, 40, 45, 50, 55 L} | Films licensed, final revenue, marginal revenue per extra ₹5 L (the "elbow") |
| S3 | DEMAND_SCALE ±30% | Occupancy and revenue; does the lift over the baselines survive? (tests the biggest synthetic assumption) |
| S4 | GP revenue weight 0.1 → 0.9 | Trade-off curve: revenue vs quota deviation / prime-time diversity |
| S5 | 8–10 schedule weeks across 2010–2016 (pools of 15+ films) | Distribution of M4 lift over B1/B2 (mean / min / max); all schedules feasible |

If a setting is infeasible (e.g. too little budget for 8 films), record it and carry on. Don't crash.

---

## 6. Target notebook structure

Each model section follows the same pattern: **Question → Formulation** (sets, parameters, variables, objective, constraints numbered as in the code comments) **→ Code** (`solve_model_k()` function and its call) **→ Results → Interpretation** (numbers printed by code, never hard-coded). This replaces today's duplicated "Code Guide" / "Output Meaning" pairs.

```
 0. Title, team, problem statement, project question            (PPT 1–3)
 1. Setup & CONFIG  — every assumption in one dict, printed as a table
    + shared helpers: kpis(), validate_schedule(), plot_gantt(), schedule_df()
 2. Data loading & cleaning  (4,803 → 2,571)                    (PPT 4–5)
 3. Weekly market synthesis & candidate pool (+ schedulable flag)
 4. EDA  (genres, runtime with 160-min limit line, popularity vs rating, normalisation)
 5. Demand model  (D / att / occ / rev / spill tensors, calibration check, heatmaps)  (PPT 12)
 6. Model 1 — Knapsack            (+ greedy, LP relaxation, budget-binding check)    (PPT 7)
 7. Model 2 — Transportation      (+ quotas, preferred genre, duals)                  (PPT 8)
 8. Model 3 — Assignment          (+ grid, Gantt, KPIs, validation)                    (PPT 9)
 9. Model 4 — Goal Programming    (+ goal report, price of balance, final Gantt)
10. Chain verification table      (model → output → consumed by → cell)               (PPT 10)
11. Baselines & comparison        (B1, B2, M3, M4 + validation table)                  (PPT 11)
12. Sensitivity & robustness      (run_pipeline; S1–S5)                                (PPT 11)
13. Final operating plan          (grid, clock table, KPIs, goal report, exports to outputs/)
14. Limitations, conclusion (generated numbers), future work                           (PPT 13–14)
```

---

## 7. Phased roadmap

Implement one phase per prompt, in order. After each phase, the notebook must still pass **Restart & Run All**:

```bash
jupyter nbconvert --to notebook --execute multiplex_screen_scheduling.ipynb --output _executed_check.ipynb
```

### Phase 0 — Groundwork and reproducibility · *size S*
- [ ] `requirements.txt`: pandas, numpy, matplotlib, seaborn, `pulp>=2.7,<3`, jupyter, nbconvert. Drop scipy unless it ends up being used.
- [ ] Replace cell 00 (unpinned pip installer) with `%pip install -r requirements.txt` (commented) plus a version-print cell.
- [ ] Add the **CONFIG** cell (all constants from cells 08 and 26 in one place) and a skeleton **helpers** cell.
- [ ] Delete `_validate.py` (stale 6-model harness); verification is now nbconvert execution.
- [ ] Untrack the generated `weekly_candidate_pool.csv` and add it to `.gitignore`; create the `outputs/` folder.
- **Done when:** the notebook runs top to bottom in a fresh environment with pinned PuLP. Model behaviour is unchanged.

### Phase 1 — Time grid and demand model · *size M*
- [ ] Apply D1 (uniform 180-min slots); one `SLOT_LENGTH`; `fits` flag on the candidate pool; EDA runtime chart shows the 160-min line.
- [ ] Extend `GENRE_AFFINITY`; build the category sets from full genre lists.
- [ ] Build the `D`, `att`, `occ`, `rev` and `spill` tensors (n × 6 × 5) as in Section 4.1; set DEMAND_SCALE ≈ 600, to be confirmed after Phase 4.
- [ ] Update the heatmaps: demand (persons), occupancy on each screen size, revenue.
- **Done when:** occupancy only hits 100% where demand really exceeds capacity; screen size changes revenue; heatmaps show the new values.

### Phase 2 — Model 1 Knapsack · *size M*
- [ ] New `value` and `fee`; yᵢ = 0 for unschedulable films; coverage from full genre lists; `solve_knapsack(films, cfg)`.
- [ ] Greedy comparison (report feasibility, not just score) and LP relaxation / integrality gap.
- [ ] Print the budget used vs available and which constraints bind.
- **Done when:** the budget binds at ₹40 L, no unschedulable film is licensed, and greedy vs ILP is explained.

### Phase 3 — Model 2 Transportation · *size M*
- [ ] Quotas `b_g` (largest remainder, clipped to `[n_g, K_MAX·n_g]`); cost `c_sg` (spill + empty seats); `solve_transportation(licensed, cfg)`.
- [ ] Output the `x_sg` matrix, `preferred_genre`, total mismatch cost, and dual values with plain-language interpretation; quota heatmap.
- **Done when:** the solution is integral, big screens carry the high-demand genres, and the duals are printed and explained.

### Phase 4 — Model 3 Assignment · *size M*
- [ ] Constraints C1–C7 (add C5; remove the bonus and the separate coverage constraint); `solve_assignment(licensed, prefs, cfg)` returns R\* and the schedule.
- [ ] Clock table, Gantt chart, idle/utilisation from the shared helper; run the validator.
- [ ] **Calibration checkpoint:** confirm DEMAND_SCALE meets the Section 4.1 rule. Adjust it once if needed and record why.
- **Done when:** the schedule is optimal and passes all validator checks, the 9 pm slot holds blockbusters, and R\* is stored.

### Phase 5 — Model 4 Goal Programming · *size L*
- [ ] Goals G1–G6 as in Section 4.5 (R\* anchor, linearised ratio goals, quota deviation variables, one idle definition); `solve_goal_program(...)`.
- [ ] Set targets with the declared rule; goal-attainment table and chart; "price of balance"; final Gantt chart.
- **Done when:** GP's schedule differs from M3's where the goals conflict, every reported deviation matches the solver's values, and the goal table is generated by code.

### Phase 6 — Validation and baselines · *size M*
- [ ] B1 (feasible naive top-5) and B2 (greedy) through the same `kpis()` and `validate_schedule()`.
- [ ] Comparison table and charts: B1, B2, M3, M4; validation table for all four.
- [ ] Chain-verification table (Section 6, item 10).
- **Done when:** the baselines are feasible, and the headline lift is computed against both baselines and printed by code.

### Phase 7 — Sensitivity and robustness · *size M*
- [ ] `run_pipeline(overrides)` that reuses the solve functions.
- [ ] Experiments S1–S5 with clean plots and tables; graceful handling of infeasible settings.
- **Done when:** all five experiments run in about a minute and each plot has a one-paragraph interpretation.

### Phase 8 — Final output, narrative, README · *size M*
- [ ] Final operating plan section; export `outputs/final_schedule.csv`, `outputs/kpi_comparison.csv` and figures (Gantt, comparison, sensitivity, trade-off).
- [ ] Rewrite stale markdown: remove all references to "Models 1–6", sequencing and set covering; fix the week and counts; EDA text generated from data.
- [ ] Conclusion numbers generated in code (e.g. an `IPython.display.Markdown` summary); update the limitations (end-to-end sensitivity is now done); move the pre-submission checklist to README or delete it.
- [ ] Update `README.md` (models, how to run, outputs, assumptions); final Restart & Run All with outputs saved.
- **Done when:** no hard-coded result numbers remain in the markdown, and a fresh clone runs end to end.

### Phase 9 — Final-review material (optional) · *size S–M*
- [ ] Slide content for the new results:
  - revised assumptions (time grid, demand calibration);
  - one result slide per model;
  - the 4-model chain diagram (with GP);
  - validation table, baseline comparison, sensitivity, multi-week robustness, GP trade-off curve;
  - limitations and future work.
- [ ] Viva prep: about 10 likely questions, each with a short answer and a pointer to the notebook section. Examples: "Why is M2 integral?", "Why GP and not a single objective?", "How did you calibrate demand?", "What if there's a 170-min film?"

---

## 8. Parameter table (single CONFIG)

| Parameter | Current | Proposed | Rationale |
|---|---|---|---|
| `SCHEDULE_WEEK_START` | 2014-07-16 | keep | 15 candidates, recognisable films (D4) |
| `WINDOW_WEEKS` | 8 | keep | PPT |
| `LAMBDA` | 0.55 | keep | ≈ 42% week-on-week drop; sensitivity-tested |
| Screens / capacities | 250/180/180/120/120 | keep | PPT |
| Slot starts | 9, 12, 15, 18, 21, 23 h | 9, 12, 15, 18, 21, **24** h | Uniform 180-min slots (D1) |
| `SLOT_LENGTH` | 180 (effectively 120 at 9 pm) | 180 for all slots | PPT: max runtime 160 |
| `CLEANUP_BUFFER` | 20 | keep | PPT |
| `PRICES` | 120/150/180/250/280/200 | keep | PPT |
| `SLOT_FACTOR` | .55/.70/.75/.95/1.0/.80 | keep; late slot ≈ .65 | Midnight demand |
| `GENRE_AFFINITY` | 7 genres + default | all genres in the pool | Sci-Fi/Fantasy/Thriller/Family currently use the default |
| `DEMAND_SCALE` | 15 (unitless; saturates) | ≈ 600 **persons** | Calibration rule (Section 4.1) |
| Licensing fee | ₹3 L·(0.5+0.5·pop)·(1+0.3·decay) → ₹2.0–3.1 L | ₹2 L + ₹25 L·e_i → ₹2.1–16 L | Budget must bind (Section 4.2) |
| `LICENSING_BUDGET` | ₹40 L | keep | PPT; swept ₹25–55 L |
| `N_MIN`, `N_MAX` | 8, 12 | keep | PPT |
| `K_MAX` (shows per film) | 5 | keep | PPT |
| `M_MIN` (screens per slot) | 4 | keep | PPT |
| `EMPTY_SEAT_COST` h | — | ₹20 per seat-show | M2 mismatch cost (new, declared) |
| GP targets | ₹8.5 L, 65%, 6 genres, 45 min, 80% | R\* (M3), occupancy targets from the new calibration, ≥ 4 prime genres, idle from M3, quota deviation 0 | Targets must be meaningful under the new demand scale |
| GP weights | .50/.20/.15/.10/.05 | .40/.10/.10/.10/.10/.20 (six goals) | Plus the S4 weight sweep |

> **Integrity rule:** calibration rules (Sections 4.1 and 4.5) are fixed before the baseline comparison is run. Parameters are not re-tuned afterwards to make the headline look better. The multi-week test (S5) is the check on this.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Infeasible model for some week or parameter (e.g. budget too low for 8 films; quota impossible) | Check solver status everywhere; clip quotas (Section 4.3); `run_pipeline` records infeasibility instead of crashing |
| GP goals trivially met, so GP = M3 again | Targets set from M3's achieved values (Section 4.5); the S4 weight sweep shows the trade-off |
| M2 allocation degenerate in a weak week (no spill anywhere) | Detect it, explain it ("screen size irrelevant this week"), break ties by demand rank |
| PuLP API changes | Pin `pulp>=2.7,<3` |
| Stale numbers creeping back into the markdown | All result numbers printed or rendered from code (Phase 8) |
| Over-tuning to inflate the headline | Integrity rule (Section 8) + multi-week robustness (S5) |

---

## 10. Explicitly out of scope (to avoid over-complication)

- Real ticket or booking data, and demand forecasting with machine learning.
- Flexible (non-slot) start times, sequencing models, or staggering start times across screens.
- Multi-day or rolling weekly schedules, and stochastic or robust optimisation.
- Metaheuristics (GA, simulated annealing), since the exact solvers already finish in under a second.
- A web dashboard (Streamlit or similar). At most an ipywidgets week picker, if D5 allows.

---

## Appendix A — Audit run details

- Environment: Python 3.13.5, pandas 2.3.1, **PuLP 2.9.0** (PuLP 4.0.0 fails), CBC solver.
- Week `2014-07-16`: 15 candidates in the 8-week window; 13 are schedulable (Transformers 165 min and Boyhood 164 min exceed 160).
- Solve times: M1 0.05 s, M2 0.04 s, M3 0.09 s, GP 0.14 s, so end-to-end sweeps are cheap.
- Candidate pool size across 100 weeks (2009–2016): median 21, min 12, max 33. That is enough weeks with pools of 15+ for S5.
- Scratch prototypes (not in the repo) confirmed:
  - Capacity-capped demand at scale 550–700 → 34–41% average occupancy, 50–58% prime-time occupancy.
  - The demand-linked fee makes the ₹40 L budget bind, and greedy breaks the 8-film minimum.
  - The spill + empty-seat transportation cost gives a non-degenerate, integral allocation with interpretable duals.
