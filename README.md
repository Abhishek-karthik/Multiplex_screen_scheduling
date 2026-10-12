# Multiplex Screen Scheduling — a four-model Operations Research pipeline

**Operations Research project — Group 14**
Abhishek Karthik (CB.SC.U4AIE23010) · Abhishek R (CB.SC.U4AIE23011) · M P Mothiswaran (CB.SC.U4AIE23041) · M S Bavesh Reddy (CB.SC.U4AIE23044)

A decision-support pipeline that builds a feasible one-day operating plan for a 5-screen multiplex from real TMDB movie metadata and a transparent synthetic theatre configuration. It then tests whether the plan beats a simple popularity-based schedule.

## The model chain

| # | Model | OR technique | Decides | Output → consumed by |
|---|---|---|---|---|
| 1 | Film selection | 0/1 Knapsack (binary ILP) | which films to license under the ₹40 L weekly budget (8–12 films, content coverage, only films that fit a slot) | licensed films → Models 2, 3, 4 |
| 2 | Screen–genre capacity planning | Transportation LP (balanced; spill + empty-seat cost) | how many shows of each genre go on each screen | quota `x[s,g]` → Model 4 goal G6; preferred genre per screen → Model 3 constraint C7 |
| 3 | Film–screen–slot assignment | Binary ILP | revenue-maximising 5 × 6 timetable (one film per cell, runtime + cleanup fit, no simulcast, ≤ 5 shows per film, ≥ 4 screens per slot, every licensed film shown) | optimal revenue R\* → Model 4 goal G1 |
| 4 | Multi-objective reconciliation | Weighted goal programming (MILP) | final schedule balancing revenue, occupancy, prime-time variety, idle time and the Model 2 plan | **final schedule** + goal-attainment report |

The pipeline is evaluated with:
- a hard-constraint validator for every schedule;
- two baselines: B1 naive popularity, and B2 a greedy manager;
- a revenue bridge (selection vs scheduling effect);
- end-to-end sensitivity on λ, budget and demand scale;
- a goal-programming weight trade-off curve;
- a robustness test over 10 schedule weeks chosen by a fixed rule.

## Files

| Path | Contents |
|---|---|
| `multiplex_screen_scheduling.ipynb` | Main notebook. Each model has its formulation, code, results and a generated interpretation. |
| `tmdb_5000_movies.csv` | TMDB 5000 dataset ([Kaggle](https://www.kaggle.com/datasets/tmdb/tmdb-movie-metadata)) |
| `requirements.txt` | Python dependencies (PuLP pinned below 3) |
| `outputs/` | Exported results: final schedule and grid, licensed films, KPI comparison, goal report, validation, chain verification, sensitivity tables, and all figures (Gantt charts, comparison, revenue bridge, sensitivity, trade-off, robustness) |
| `IMPLEMENTATION_PLAN.md` | Audit of the first-review version and the phased plan that this version implements |
| `ppt_or.pptx` | First-review presentation |

`weekly_market_synthesized.csv` and `weekly_candidate_pool.csv` are regenerated on every run and are not tracked.

## How to run

```bash
pip install -r requirements.txt
jupyter notebook multiplex_screen_scheduling.ipynb      # then Kernel → Restart & Run All
```

Or run it headless (about 30–40 s; every model solves in well under a second with the bundled CBC solver):

```bash
python -m nbconvert --to notebook --execute multiplex_screen_scheduling.ipynb --output _executed_check.ipynb
```

> **PuLP version:** PuLP 3.x/4.x removed `LpVariable.dicts`, so `requirements.txt` pins `pulp>=2.7,<3`.

## Changing the scenario

Every assumption lives in the `CONFIG` dictionary (Section 1.1 of the notebook): schedule week, λ, screens, slots, prices, demand scale, fee formula, budget, film limits and goal weights. Change a value and re-run. To test many settings without editing, call `run_pipeline({'budget': 4_500_000})` or `run_pipeline({'schedule_week_start': '2012-10-10'})` (Section 12). It re-solves the whole chain and returns a summary row.

## Key modelling assumptions

- **Slots:** six fixed 180-minute slots: 09:00, 12:00, 15:00, 18:00, 21:00 and 00:00. With a 20-minute cleanup, a film must be ≤ 160 minutes long.
- **Demand in persons:** `D = DEMAND_SCALE × effective_demand × slot_factor × genre_slot_affinity`. Seats sold = `min(D, screen capacity)`; the excess is spill.
  - `effective_demand = normalised popularity × exp(−λ · weeks since release)`, with λ = 0.55.
  - `DEMAND_SCALE` is calibrated once (Section 8.2) to an average occupancy of 35–45%, then frozen.
- **Licensing fee:** a weekly minimum guarantee of ₹2 L + ₹25 L × effective demand.
- **Goal targets:** each is one step better than the revenue-only schedule, so the goals genuinely conflict.

All revenue and occupancy figures are model estimates built on these declared assumptions, not observed ticket sales. Limitations and future work are discussed in Section 14 of the notebook.
