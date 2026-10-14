"""OR engine for multiplex screen scheduling: the single source of truth used by the notebook and the app.

Chain: load_and_clean -> build_weekly_market -> build_candidate_pool -> build_demand -> add_licensing_terms
       -> M1 solve_knapsack -> M2 solve_transportation -> M3 solve_assignment -> M4 solve_goal_program
       -> baselines, kpis, validate_schedule.  run_chain() runs all of it; run_pipeline()/sweep() for sensitivity.
"""
from .ahp import RANDOM_INDEX, SAATY_SCALE, ahp_weights, judgments_to_matrix
from .analysis import lp_sensitivity_report
from .baselines import baseline_greedy, baseline_naive
from .config import (AHP_JUDGMENTS, DATA_PATH, DEFAULT_CONFIG, GOAL_LABELS, GOALS, PRE_REVIEW_OVERRIDES,
                     PRE_REVIEW_WEIGHTS, PROJECT_ROOT, ahp_goal_weights, cfg_with, default_config, validate_config)
from .data import REQUIRED_COLUMNS, check_schema, load_and_clean, read_dataset
from .demand import add_licensing_terms, build_demand, explain_cell
from .market import build_candidate_pool, build_weekly_market, pool_size_by_week
from .metrics import (kpis, make_schedule, minutes_to_clock, n_screens, n_slots, quota_counts, rupees, schedule_grid,
                      screen_names, signed_pct, validate_schedule)
from .models import (binding_table, build_assignment_core, chosen_cells, film_quotas, fmt_goal_value, genre_quotas,
                     goal_report, goal_targets, greedy_knapsack, solve_assignment, solve_goal_program, solve_knapsack,
                     solve_transportation, transport_costs)
from .pipeline import STAGES, ChainResult, chain_summary, revenue_bridge, run_chain, run_pipeline, sweep
from . import formulations  # noqa: F401  (LaTeX formulations shown by the app)

__version__ = '1.0.0'
