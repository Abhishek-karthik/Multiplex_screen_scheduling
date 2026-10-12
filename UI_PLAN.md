# UI Plan — Multiplex Scheduling Decision-Support App

> **Goal.** Build a simple, genuine interface that does more than display final numbers. It should let a user (or examiner):
> - load the data;
> - generate statistics on demand;
> - choose and run the optimisations;
> - *see* how the problem is modelled, how each model turns inputs into decisions, and how the results compare.
>
> **Professor's brief (must be met):** a UI where (1) data can be loaded, (2) statistics about the data are generated on demand, and (3) at least two optimisations can be run, chosen by the user. The final presentation must show the UI and the code.
>
> Read `PROJECT_AUDIT.md` first: the UI should be built on the model *after* the recommended fixes.

---

## 0. TL;DR

- **Don't build the UI inside the notebook.** Extract the notebook's functions into a small Python package, `engine/`, as the single source of truth. The notebook and the app both import it, and a parity test checks that both produce the same numbers.
- **Build the UI in Streamlit.** It is pure Python, multipage, has built-in upload, data editor, caching and LaTeX, and charts come from Plotly.
- **No REST API or endpoints are needed.** Streamlit runs Python in the same process, so the engine's functions *are* the API (contract in Section 4.3). If a separate web frontend is ever wanted, the same functions map 1:1 to REST endpoints (Appendix A).
- **Eight pages that follow the OR chain:**

  | Page | What it shows |
  |---|---|
  | Overview | The problem |
  | Data | Load the data + statistics on demand |
  | Market & Demand | How demand is modelled |
  | Optimisation Studio | M1, M2, M3, M4, each runnable on its own or as a chain |
  | Compare & Validate | All schedules side by side, with the constraint checks |
  | Sensitivity Lab | Parameter sweeps |
  | Final Plan & Export | The manager's plan |
  | Under the Hood | The code, model files and solver statistics |

- **Every number is computed live** by the same engine as the notebook. Every solve shows the solver status, solve time, model size, and a downloadable `.lp` file of the exact model CBC solved.
- **Nine phases (U0–U8), roughly 28–35 hours in total.** U0 (engine extraction) comes first and protects consistency with the notebook.

---

## 1. Requirements → features

| Requirement | Feature in the app | Page |
|---|---|---|
| Data can be loaded | Use the bundled `tmdb_5000_movies.csv` **or** upload a TMDB-format CSV. A schema check names any missing columns; the cleaning funnel shows the rows left after each step | Data |
| Statistics generated on demand | A **Stats Builder**: choose the data scope, analysis type, columns and filters, then click *Generate*. Returns a table and chart with a CSV download | Data |
| ≥ 2 optimisations chosen by the user | The **Optimisation Studio**: run M1 Knapsack, M2 Transportation, M3 Assignment or M4 Goal Programming individually, with their own parameters, or run the whole chain. There are variants too: ILP / greedy / LP relaxation for M1; manual weights or AHP for M4 | Studio |
| Illustrate the problem | Decision-chain diagram; a "theatre at a glance" view (screens × slots, prices); plain-language questions | Overview |
| Illustrate the modelling | For each model: its formulation in LaTeX, the **actual instance data** fed in, model size, and a downloadable `.lp` file | Studio, Under the Hood |
| Illustrate the solution and results | Interactive Gantt chart, grid, Sankey flow diagram, binding constraints, duals, goal-attainment chart, before/after comparison, validation matrix | Studio, Compare |
| Show the code | Source code of each model function (`inspect.getsource`), the chain-verification table, environment versions | Under the Hood |

---

## 2. How the whole system is modelled (identified from the notebook)

### 2.1 End-to-end flow

```
 DATASET (TMDB CSV)
   │ load_and_clean(cfg.min_vote_count)                 4,803 → 2,571 films
   ▼
 CLEAN FILMS ──► build_weekly_market(week, window, λ)    weeks_out, decay e^(−λ·weeks), effective demand e_i, status
   ▼
 CANDIDATE POOL ──► build_candidate_pool(cfg)           films released in the last 8 weeks; fits (runtime ≤ 160); action/family/regional flags
   ▼
 DEMAND MODEL ──► build_demand(cfg)                     D[i,j] persons; att = min(D, C_s); occ; rev = P_j·att; spill
   │ add_licensing_terms(cfg)                           value v_i, weekly fee f_i
   ▼
 MODEL 1  Knapsack ILP ── solve_knapsack ──────────────► LICENSED FILMS (+ binding constraints, greedy & LP comparison)
   ▼
 MODEL 2  Transportation LP ── solve_transportation ───► QUOTA x[s,g], PREFERRED GENRE per screen, duals u_s, v_g
   ▼
 MODEL 3  Assignment ILP ── solve_assignment ──────────► REVENUE-OPTIMAL SCHEDULE, R*  (uses M2 preferences in C7)
   │ kpis(M3) → goal_targets(R*, M3 KPIs, steps)
   ▼
 MODEL 4  Goal Programming MILP ── solve_goal_program ─► FINAL SCHEDULE + goal report  (uses x[s,g], R*, weights)
   ▼
 EVALUATION: baseline_naive (B1), baseline_greedy (B2), kpis(), validate_schedule(), revenue bridge
   ▼
 SENSITIVITY: run_pipeline(overrides) re-runs everything; sweep(param, values)
```

### 2.2 Stages, inputs and outputs

| Stage | Engine function | User-controllable inputs | Output | Time (measured) |
|---|---|---|---|---|
| Data | `load_and_clean` | file, min vote count | clean films, cleaning steps | ~2.5 s (cache it) |
| Market | `build_weekly_market`, `build_candidate_pool` | week, window, λ | candidate pool | < 0.1 s |
| Demand | `build_demand`, `add_licensing_terms` | capacities, prices, slot factors, demand scale, fee formula | D/att/occ/rev/spill tensors, value, fee | < 0.1 s |
| M1 | `solve_knapsack` (+ `greedy_knapsack`, relax = True) | budget, films min/max, coverage rules, *or a manual film choice* | licensed set | 0.03–0.12 s |
| M2 | `solve_transportation` | empty-seat cost | x[s,g], preferred genres, duals | 0.02–0.7 s |
| M3 | `solve_assignment` | max shows per film, min screens per slot, use C7 on/off | schedule, R\* | 0.05–0.15 s |
| M4 | `goal_targets`, `solve_goal_program` | goal weights (manual or AHP), target steps | final schedule, deviations | 0.06–0.25 s |
| Evaluation | `baseline_*`, `kpis`, `validate_schedule` | — | KPI table, checks | < 0.1 s |
| Sensitivity | `run_pipeline`, `sweep` | parameter + range | sweep table | 0.4–1.5 s per point |

### 2.3 Invalidation rule (what must re-run when the user changes something)

```
file / min votes → Market → Demand → M1 → M2 → M3 → M4 → Compare / Final plan
week, window, λ  →          Demand → M1 → M2 → M3 → M4 → …
capacities, prices, demand scale →   M1 → M2 → M3 → M4 → …
budget, film limits, manual films →        M2 → M3 → M4 → …
empty-seat cost  →                               M3 → M4 → …
max shows, min screens, C7  →                          M4 → …
weights / targets  →                                      Compare / Final plan
```

Each stage's result is stored with a **hash of its inputs**. A page whose stored hash doesn't match the current inputs shows a **"stale — re-run"** badge, and never shows mismatched numbers silently.

### 2.4 Limits the UI must respect

- **Six slots, fixed.** `GENRE_AFFINITY` and the slot factors are 6-long. The UI lets the user edit the **prices and slot factors** of the 6 slots, but not the number of slots.
- **3–8 screens.** Screen count and capacities are editable. The engine is generic in the number of screens; Phase U0 tests this.
- **Week picker.** Limited to dates inside the dataset (2009–2016 is sensible). It shows the candidate-pool size live and warns if the pool has fewer than 10 schedulable films.
- **Infeasible inputs** (e.g. a budget too small for the film minimum) show the solver status and a hint, e.g. "the 8 cheapest schedulable films cost ₹X; raise the budget or lower the minimum".

---

## 3. Can we build it from the notebook? Options compared

| Option | How | Pros | Cons | Verdict |
|---|---|---|---|---|
| ipywidgets inside the notebook | Sliders and buttons in cells | Reuses cells directly | Still a notebook: code cells visible, fragile cell state, weak layout. Doesn't read as "a UI" | ✗ |
| Voilà (notebook rendered as an app) | Hide code, show widgets | Little new code | Needs a widget rewrite anyway; limited multi-page layout; one more tool to install and debug | ✗ |
| Gradio | Function → UI | Very quick for one function | Awkward for a multi-stage, stateful, multi-page workflow | ✗ |
| Plotly Dash | Callbacks | Powerful | Callback boilerplate; more code for the same result | ~ |
| FastAPI + React/HTML | REST API + separate frontend | "Real" web architecture | Two languages, build tooling, CORS, state handling. Effort goes into web plumbing, not OR | ✗ (for now) |
| **Streamlit on an `engine/` package** | Engine = the extracted notebook functions; Streamlit pages call them | Pure Python; multipage (`st.navigation`); upload, `st.data_editor`, `st.latex`, caching, `st.download_button`; Plotly charts; a test harness (`AppTest`); one-command demo | Re-runs the script on each interaction, so it needs caching and session state (planned below) | ✅ **Recommended** |

**Decision: Streamlit + `engine/`.** The notebook stays the analytical report; the app is the interactive decision-support tool; both run the *same* engine, so their numbers can't drift apart.

Verified available (installed in a scratch environment only): **Streamlit 1.65** (`st.navigation`, `st.Page`, `st.data_editor`, `st.file_uploader`, `st.cache_data`, `st.latex`, `st.graphviz_chart`, `st.download_button`, `st.status`, `st.fragment`, `st.dialog`, `AppTest`) and **Plotly 7.1** (Sankey, Waterfall). Node/React are not needed.

---

## 4. Architecture

### 4.1 Folder layout

```
Multiplex_screen_scheduling/
├── engine/                     # OR engine: the single source of truth (extracted from the notebook)
│   ├── __init__.py             # re-exports the public API
│   ├── config.py               # DEFAULT_CONFIG (incl. genre affinity, category sets), cfg_with(), validate_config()
│   ├── data.py                 # REQUIRED_COLUMNS, read_dataset(), check_schema(), load_and_clean()
│   ├── market.py               # build_weekly_market(), build_candidate_pool(), pool_size_by_week()
│   ├── demand.py               # build_demand(), add_licensing_terms(), explain_cell()
│   ├── models.py               # M1 knapsack/greedy/binding, M2 quotas/costs/transportation, M3 assignment, M4 GP + targets
│   ├── baselines.py            # baseline_naive(), baseline_greedy()
│   ├── metrics.py              # make_schedule(), schedule_grid(), quota_counts(), kpis(), validate_schedule(), goal_report()
│   ├── pipeline.py             # run_chain() → ChainResult; run_pipeline() (summary row); sweep(); revenue_bridge()
│   ├── analysis.py             # (audit C1/C2) ahp_weights(); sensitivity_report()
│   └── formulations.py         # LaTeX strings for each model (shared by the app's model cards)
├── app/
│   ├── streamlit_app.py        # entry point: st.navigation, sidebar scenario, chain-status bar
│   ├── pages/                  # overview, data, market_demand, studio_m1..m4, compare, sensitivity, final_plan, under_the_hood
│   └── components/             # charts.py (Plotly gantt/heatmap/sankey/waterfall), cards.py (model template), state.py (hashing, stale badges)
├── tests/
│   ├── test_engine_parity.py   # engine reproduces the notebook's numbers for the default scenario
│   └── test_app_smoke.py       # AppTest: every page renders, default solves are Optimal
├── multiplex_screen_scheduling.ipynb   # imports engine; keeps all formulation markdown and narrative
└── requirements.txt            # + streamlit, plotly (+ highspy if C2 is adopted)
```

### 4.2 Engine extraction (Phase U0): what changes versus the notebook code

The function bodies move over **unchanged**, except for these clean-ups that the UI needs:

1. **No hidden globals.**
   - `GENRE_AFFINITY`, `ACTION_LIKE`, `FAMILY_FRIENDLY` and `REGIONAL_LANGUAGES` move into the config.
   - `rupees()` moves into `metrics.py`; `validate_schedule` currently relies on it as a global.
   - `run_pipeline` takes `clean` explicitly instead of the global `clean_df`.
2. **`load_and_clean` accepts a DataFrame** (from upload or disk), not just a path. Parsing of unused JSON columns (`keywords`, `production_companies`) becomes optional, so an upload only needs the columns the models use.
3. **Every solver returns its `pulp.LpProblem`** (M1 already does). This enables `.lp` export, model-size display and the sensitivity report.
4. **New `run_chain(clean, cfg, licensed_override=None, weights=None) -> ChainResult`.** A dataclass holding every intermediate object, plus status and timing per stage. `run_pipeline` becomes a thin wrapper that returns today's summary row, so the notebook's Section 12 is unchanged.
5. **Matplotlib plotting stays notebook-only** (`plot_gantt`); the app uses Plotly equivalents.
6. **The notebook switches to `from engine import …`.**
   - Function-definition cells become one import cell plus a "source: `engine/models.py`" note.
   - All markdown, formulations and generated interpretations stay.
   - Re-run, and assert that the numbers are identical.

**Fallback, if time is short:** keep the notebook unchanged and treat `engine/` as a verified copy, guarded by the parity test. Any model fix then has to be applied twice. Not preferred.

### 4.3 Engine API contract (this *is* the "API")

| Function | Inputs | Returns | Used by page |
|---|---|---|---|
| `read_dataset(src)` / `check_schema(df)` | path or uploaded bytes | raw DataFrame / list of problems | Data |
| `load_and_clean(raw, cfg)` | raw df, `min_vote_count` | `(clean_df, steps_df)` | Data |
| `build_weekly_market(clean, week, window, lam)` | dates, λ | market df | Market |
| `build_candidate_pool(market, cfg)` | | pool df (`fits`, flags) | Market |
| `pool_size_by_week(clean, cfg, weeks)` | | df week → pool size | Market (week picker) |
| `build_demand(films, cfg)` | | dict `D, att, occ, rev, spill, cap, price` | Demand, all models |
| `explain_cell(films, dem, cfg, i, j, s)` | film, slot, screen | each factor and intermediate value | Demand explainer |
| `add_licensing_terms(films, dem, cfg)` | | films + `value`, `fee` | M1 |
| `solve_knapsack(films, cfg, relax=False)` | | `status, selected, objective, fee_used, y, constraints, prob, solve_s` | M1 |
| `greedy_knapsack(films, cfg)`, `binding_table(m)` | | comparison / binding table | M1 |
| `solve_transportation(films, lic, dem, cfg)` | | `quotas, cost, x, quota_matrix, prefs, u, v, reduced_cost, integral, total_cost, prob` | M2 |
| `solve_assignment(films, lic, dem, prefs, cfg)` | `prefs=None` disables C7 | `status, R_star, schedule, cells, n_vars, n_cons, prob` | M3 |
| `goal_targets(k_m3, n_genres, R_star, cfg)` | | targets dict | M4 |
| `solve_goal_program(films, lic, dem, prefs, quota, targets, weights, cfg)` | | `schedule, solver_dev, weighted_deviation, prob` | M4 |
| `goal_report(sched, films, targets, weights, quota, cfg)` | | goal table | M4, Compare |
| `baseline_naive(films, dem, cfg)`, `baseline_greedy(films, lic, dem, cfg)` | | schedules | Compare |
| `kpis(sched, films, cfg, licensed, quota)`, `validate_schedule(...)` | | KPI dict / checks df | everywhere |
| `run_chain(clean, cfg, ...)` | optional overrides | `ChainResult` | sidebar "Run full chain", Final plan |
| `run_pipeline(overrides, clean)`, `sweep(clean, param, values)` | | summary row / sweep df | Sensitivity |
| `ahp_weights(matrix)` *(C1)* | n×n pairwise matrix | `weights, lambda_max, CI, CR` | M4 |
| `sensitivity_report(prob)` *(C2)* | an LP | variable and constraint ranging tables | M2 (and the M1 LP relaxation) |

---

## 5. UI design

### 5.1 Global layout

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│  🎬 Multiplex Scheduling — OR Decision Support            [ Run full chain ▶ ]              │
├──────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ SIDEBAR (scenario)   │  PAGE CONTENT                                                         │
│ Dataset: bundled ▾   │                                                                       │
│ Week: 2014-07-16 📅  │                                                                       │
│ Window: 8 wks  λ:0.55│                                                                       │
│ ▸ Theatre (edit)     │                                                                       │
│ ▸ Demand & fees      │                                                                       │
│ ▸ Model limits       │                                                                       │
│ [Reset to defaults]  │                                                                       │
│ ──────────────────── │                                                                       │
│ CHAIN STATUS         │                                                                       │
│ Data ✔ Market ✔      │                                                                       │
│ Demand ✔ M1 ✔        │                                                                       │
│ M2 ✔ M3 ⚠ stale      │                                                                       │
│ M4 – not run         │                                                                       │
└──────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

- **Scenario:** one dict in `st.session_state`, defaulting to `engine.DEFAULT_CONFIG`. The sidebar edits it; theatre tables use `st.data_editor`.
- **Chain status:** shows, for every stage, whether it is ✔ fresh, ⚠ stale, ✖ infeasible or – not run. Clicking an item opens its page.
- **Run full chain:** calls `run_chain` and fills every stage; per-stage timings are shown in an `st.status` box.

### 5.2 Pages

**P1 · Overview — "what problem are we solving?"**
- The problem in plain words; the project question; the four decisions.
- Decision-chain diagram (`st.graphviz_chart`). Each node shows the model, its technique, and what it hands to the next; clicking a node opens that model's page.
- "Theatre at a glance": 5 screens (seat counts) × 6 slots grid, with slot prices and demand factors.
- An assumptions table, generated from the config, with a link to the notebook's justification.

**P2 · Data — load + statistics on demand** (*brief items 1 and 2*)
- **Load:** a "bundled TMDB 5000" / "upload CSV" toggle.
  - The schema check lists missing required columns (`title, genres, release_date, runtime, popularity, vote_count, vote_average, status, original_language`).
  - Shows a preview, plus row and column counts.
- **Cleaning funnel:** a step chart 4,803 → 4,795 → 2,571 …, recomputed for the uploaded file and the chosen minimum vote count.
- **Stats Builder (on demand):**
  - **Scope:** raw / cleaned / candidate pool (current week) / licensed films (if M1 has run).
  - **Analysis:** summary statistics · missing values · distribution (histogram + box) · category counts (genre, language, status, market status) · relationship (scatter x vs y, colour by genre) · trend by release year · correlation heatmap · top-N by a metric · group-by aggregate (e.g. genre → mean popularity / runtime / votes).
  - **Columns and filters**, then **[Generate]**.
  - Output: chart + table + CSV download + a one-line auto-summary (e.g. "correlation popularity–rating = 0.40").

**P3 · Market & Demand — "how do we turn TMDB into tickets?"**
- **Week picker** with a small chart of pool size by week, so the user sees thin and rich weeks.
- **Candidate pool table:** status, weeks out, decay, effective demand, runtime, and a schedulable ✔/✖ (films over 160 min are flagged).
- **Decay explainer:** the curve e^(−λ·weeks) with the pool's films plotted on it. A λ slider redraws it live.
- **Demand heatmap** D[i,j] (persons), plus an **occupancy by screen size** toggle (250 / 180 / 120).
- **Capacity-cap illustration:** for a chosen film, D across the 6 slots against horizontal lines at 120 / 180 / 250 seats. The shaded part above a line is spill (people turned away).
- **"Calculate one cell" explainer:** pick a film, slot and screen to see each factor:

  ```
  popularity_norm × decay = e
  e × scale × slot factor × affinity = D
  min(D, C) = attendance
  P × attendance = revenue
  max(D − C, 0) = spill
  ```

  The figures come from `explain_cell()` and match the engine exactly.

**P4 · Optimisation Studio** (*brief item 3*)

At the top, a **mode selector**:

| Mode | What it does |
|---|---|
| ① Single model | Pick M1 / M2 / M3 / M4 |
| ② Full chain | M1 → M4 in one click |
| ③ What-if | **I choose the films** (tick boxes in the pool), then run M2 → M4 on my choice and compare with Model 1's choice |

Every model sub-page uses the **same card template**, so the structure of OR modelling is visible each time:

```
┌─ 1. Question ─────────────── plain-language decision
├─ 2. Formulation ──────────── st.latex: sets, parameters, variables, objective, numbered constraints
├─ 3. Instance ─────────────── the actual numbers going in (tables), and where they came from (upstream model)
├─ 4. Controls ─────────────── this model's parameters / variant
├─ 5. Solve ▶ ──────────────── status · objective · #variables · #constraints · solve time · [⬇ .lp file]
├─ 6. Solution ─────────────── decision visual (see below)
├─ 7. Insights ─────────────── binding constraints, duals, comparisons, auto-written interpretation
└─ 8. Hand-off ─────────────── "this output feeds Model k+1: …"  [Next model →]
```

| Model | Controls / variants | Solution visual | Insights |
|---|---|---|---|
| **M1 Knapsack** | budget slider, film min/max, coverage toggles; variant: ILP / greedy / LP relaxation | Bar chart of value per film, coloured selected/not, sorted by value-per-rupee; a budget gauge (spent vs budget) | Binding-constraint table (slack); greedy feasibility check; integrality gap; LP shadow price of the budget; a mini budget sweep; **price of the film-count rule** (audit B1) |
| **M2 Transportation** | empty-seat cost h | **Sankey** screens → genres (width = shows), quota heatmap x[s,g], mismatch-cost heatmap c[s,g] | Integrality ✔ (TU explanation), MODI check, duals u_s / v_g with plain-language reading, savings vs a proportional split; **Solver-style sensitivity report** (audit C2) |
| **M3 Assignment** | max shows per film, min screens per slot, C7 on/off | 5×6 **grid** (title, coloured by genre; hover shows demand/attendance/revenue/spill) + **interactive Gantt** (show + cleanup blocks) | Constraint activity (C4/C5 binding per film; screens per slot vs C6); validator table (9 checks); KPIs; R\* passed to M4 |
| **M4 Goal Programming** | weights via **sliders or AHP** (audit C1: pairwise-comparison matrix → weights, λ_max, CI, CR, with a green/red CR < 0.10 badge); target steps | Goal-attainment bullet chart (target vs M3 vs M4); a **"what changed" grid** highlighting the cells that differ from M3; final Gantt | Price of balance; per-goal deviations from the solver *and* recomputed from the schedule (they must match); an on-demand **trade-off curve** (revenue weight sweep) |

**P5 · Compare & Validate — "is it feasible, and is it better?"**
- Four schedules: B1 naive, B2 greedy, M3 revenue optimum, M4 final. KPI table plus small-multiple bar charts (revenue, occupancy, variety, spill/idle).
- **Validation matrix** (check × schedule, PASS / FAIL / n/a, coloured).
- **Revenue bridge** (Plotly waterfall): B1 → scheduling effect → selection effect → cost of balance → M4.
- Side-by-side grids for any two chosen schedules.
- A fixed **honesty note**, generated: "greedy is within X% of M3 on revenue; the optimisation's value is in constraints and balance".

**P6 · Sensitivity Lab**
- Pick an experiment:
  - S1 λ · S2 budget · S3 demand scale · S4 GP revenue weight · S5 weeks (rule-based selection);
  - **S6 film-count policy** (`n_min`; audit B1).
- Edit its value range, then **[Run]**. An `st.progress` bar shows one point per full chain re-solve; results are cached by scenario hash.
- Output: line chart (B1/B2/M3/M4 revenue, plus a secondary metric), a table with an `all_valid` column, an auto-interpretation, and CSV download.

**P7 · Final Plan & Export — "the manager's sheet"**
- Licensed films (fee, shows per day, daily revenue).
- The 5×6 plan; the clock timetable (start, end with cleanup, expected attendance).
- Key figures; idle minutes per screen; goal attainment.
- Downloads: CSV per table, plus a single Excel workbook (optional `openpyxl`). A print-friendly layout.

**P8 · Under the Hood — "show me the real model and the code"** (*brief: "code shown"*)
- Model statistics for each solved model: variables (binary / continuous), constraints by family, solver, status, time, objective.
- **`.lp` file viewer and download** for M1–M4: the exact text model CBC solved.
- **Source viewer:** `inspect.getsource` of every engine function, grouped by model.
- Chain-verification table (as in the notebook's Section 10), live; environment and package versions; parity-test status.

### 5.3 Making it genuine (design rules)

1. **No hard-coded result numbers anywhere in the app.** Every figure comes from an engine call in this session; text is generated with f-strings, as in the notebook.
2. **Every solve shows** its solver status, solve time and model size, plus the `.lp` download. If a status isn't `Optimal`, the page shows that and offers a hint. It never falls back to old numbers.
3. **The validator runs on every schedule** that is displayed, and a FAIL is shown in red, never hidden.
4. **Default scenario = notebook scenario.** On first load, the app's numbers equal the notebook's (enforced by the parity test). This is the reproducibility guarantee shown in the demo.
5. **Cached sweeps are labelled** with their scenario hash and timestamp; changing an input marks them stale.
6. **Same KPI and validator definitions** everywhere (one `kpis()`, one `validate_schedule()`), so the comparisons are fair by construction.

---

## 6. State, caching and performance

| Item | Approach |
|---|---|
| Load + clean (~2.5 s) | `@st.cache_data`, keyed by file hash + minimum vote count |
| Market, pool, demand (< 0.1 s each) | Computed on demand; also `cache_data` |
| Model solves (≤ 0.7 s each) | Run on an explicit **Solve ▶** click; result stored in `st.session_state[stage] = {key: input_hash, result: …}` |
| Full chain (~0.5–1.5 s) | Button; `st.status` shows per-stage timing |
| Sweeps (S5 ≈ 10 chains ≈ 5–15 s) | `st.progress`; `cache_data` keyed by (scenario hash, param, values) |
| Heavy charts | Plotly figures built from small frames (≤ 30 cells, ≤ 15 films), so they are fast |
| Re-run behaviour | `st.fragment` for widgets that should only redraw their own chart (e.g. the λ slider on the decay curve) |

---

## 7. Dependencies

Add to `requirements.txt`, pinning exact versions at implementation time:

- `streamlit` (≥ 1.36 for `st.navigation`; tested on 1.65)
- `plotly` (tested on 7.1)
- `highspy` (only if audit C2 uses HiGHS ranging; otherwise use the scipy fallback)
- `openpyxl` (optional, for Excel export)
- `pytest` (tests)

Keep `pulp>=2.7,<3`.

Run:

```bash
pip install -r requirements.txt
```

```bash
streamlit run app/streamlit_app.py
```

---

## 8. Phased roadmap

| Phase | Work | Done when | Size |
|---|---|---|---|
| **U0 Engine extraction** | Create `engine/` (Section 4.1–4.2); remove globals; add `run_chain`, `explain_cell`, `prob` returns; notebook imports engine; `tests/test_engine_parity.py` | The notebook re-runs with **identical numbers**; parity test passes; a scenario with 4 or 6 screens solves | L (4–5 h) |
| **U1 App skeleton** | `st.navigation` with 8 pages; sidebar scenario editor; session-state helpers (hashing, stale badges); chain-status bar; "Run full chain" | The app starts; navigation works; the full chain runs from the sidebar and the status bar shows ✔ | M (2–3 h) |
| **U2 Data page** | Upload / bundled toggle, schema check, cleaning funnel, Stats Builder (≥ 8 analysis types) + downloads | Bundled and uploaded files both work; bad files give clear errors; every analysis type generates on demand | M (3 h) |
| **U3 Market & Demand** | Week picker with pool sizes, pool table, decay explainer, demand / occupancy heatmaps, capacity-cap chart, cell explainer | The explainer reproduces `build_demand` exactly for any cell; λ changes redraw live | M (3 h) |
| **U4 Studio: M1 + M2** | Card template; M1 variants and insights; M2 Sankey, heatmaps, duals (+ sensitivity report if C2) | Default results equal the notebook; `.lp` downloads open; "What-if" manual licensing runs M2 | L (4–5 h) |
| **U5 Studio: M3 + M4** | Grid + Gantt, constraint activity, validator; GP weights (sliders + AHP if C1), goal chart, diff grid, trade-off curve | Default results equal the notebook; solver deviations equal the recomputed ones; AHP gives a CR badge | L (4–5 h) |
| **U6 Compare + Final Plan** | KPI table and charts, validation matrix, waterfall, side-by-side grids; manager sheet + exports | Matches the notebook's Sections 11 and 13; downloads work | M (3 h) |
| **U7 Sensitivity Lab** | S1–S6 with progress, caching, charts, interpretation | Each experiment runs in ≤ 20 s and matches the notebook's sweep tables | M (3 h) |
| **U8 Under the Hood, polish, docs** | Model statistics, `.lp` viewer, source viewer, chain table; `AppTest` smoke tests; README "Run the app"; screenshots for the deck | All smoke tests pass; a fresh clone runs the app in one command; demo script rehearsed | M (3 h) |

**Order relative to the audit fixes:** U0 first (or the notebook fixes first; see `PROJECT_AUDIT.md` Section 6). Then put the expected numbers in the parity test **once, after the fixes**, and record them.

---

## 9. Testing

- **`tests/test_engine_parity.py`.** Default scenario: licensed titles, R\*, R_M4, price of balance, B1/B2 revenue, all validator checks PASS. Tolerance ±₹1.
- **`tests/test_app_smoke.py`** (`streamlit.testing.v1.AppTest`). Every page renders without exception; "Run full chain" leaves every stage ✔; an infeasible budget shows the status message and doesn't crash.
- **Manual checklist** before the demo:
  - upload a broken CSV → readable error;
  - change λ → downstream stages show stale;
  - What-if with 6 films → M2–M4 run;
  - AHP with an inconsistent matrix → red CR badge.

---

## 10. Demo script for the final presentation (≈ 6–7 min)

1. **Overview** (30 s): the problem, the four decisions, the chain diagram.
2. **Data** (60 s): load the bundled dataset → cleaning funnel → generate two statistics on demand (genre counts; popularity vs rating).
3. **Market & Demand** (45 s): week 2014-07-16; move λ to show decay; explain one cell (Lucy, 9 pm, screen 0: demand 363 → 250 seats sold, 113 turned away).
4. **M1** (60 s): solve. The budget binds; greedy is infeasible. Raise the budget to ₹45 L (or the scaled equivalent) and re-solve live. Show the price of the film-count rule.
5. **M2** (45 s): Sankey, duals, integral without integer constraints (TU).
6. **M3** (45 s): grid, Gantt, validator all PASS, R\*.
7. **M4** (60 s): set the weights with AHP (CR < 0.10) → solve → goal chart, changed cells, price of balance.
8. **Compare** (30 s): validation matrix and revenue bridge; the honest greedy comparison.
9. **Sensitivity** (30 s): run S6 or S2 live.
10. **Under the Hood** (20 s): open the `.lp` file and the `solve_assignment` source; note that the notebook and app numbers match.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Engine extraction introduces a silent change | The parity test is written *before* switching the notebook to the engine |
| Streamlit re-runs make the app slow or confusing | Cache data stages; solve only on button clicks; stale badges; `st.fragment` for live sliders |
| Stale or mismatched numbers across pages | Every stored result is keyed by its input hash; pages refuse to show stale numbers without a badge |
| A user's inputs make a model infeasible | Show the status and a hint (Section 2.4); never crash |
| CBC missing on another machine | PuLP bundles CBC for Windows, Linux and macOS; the Under the Hood page shows whether CBC is available |
| Scope creep (auth, database, deployment) | Out of scope (Section 12). Local demo first; Streamlit Community Cloud only if asked |

---

## 12. Out of scope

Logins, databases, multi-user state, a separate React frontend, cloud deployment infrastructure, live data feeds, editing the number of slots, and real-time collaborative editing.

---

## Appendix A — REST mapping (only if a separate frontend is ever wanted)

The engine contract maps 1:1 to a stateless FastAPI service (FastAPI 0.125 is already installed). The scenario is sent as JSON with each call:

| Endpoint | Body | Returns |
|---|---|---|
| `POST /datasets` | CSV upload | `dataset_id`, rows, schema problems |
| `GET /datasets/{id}/stats` | query: scope, kind, columns, filters | table + chart data |
| `POST /market` | dataset_id, week, window, λ | candidate pool |
| `POST /demand` | pool + theatre config | demand tensors (as lists) |
| `POST /solve/m1` … `/solve/m4` | scenario + upstream results | model result (+ `.lp` text) |
| `POST /chain` | scenario | full `ChainResult` |
| `POST /sensitivity` | scenario, param, values | sweep table |
| `POST /ahp` | pairwise matrix | weights, CI, CR |

Not recommended for this project's timeline. Streamlit calls the same functions directly.
