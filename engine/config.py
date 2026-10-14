"""Every modelling assumption in one place.

TMDB has no ticket sales, so the theatre and demand parameters are declared synthetic assumptions.
The defaults reproduce the notebook's main scenario (after the post-review corrections in PROJECT_AUDIT.md).
"""
from copy import deepcopy
from pathlib import Path

from .ahp import ahp_weights, judgments_to_matrix

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / 'tmdb_5000_movies.csv'

# Genre x slot affinity (hand-built from common programming practice; slots 9am..12am)
GENRE_AFFINITY = {
    'Action':          [0.55, 0.70, 0.80, 1.00, 1.00, 0.75],
    'Adventure':       [0.60, 0.85, 0.95, 1.00, 0.90, 0.65],
    'Animation':       [0.85, 1.00, 1.00, 0.85, 0.60, 0.30],
    'Comedy':          [0.65, 0.90, 0.90, 0.85, 0.75, 0.55],
    'Crime':           [0.45, 0.60, 0.70, 0.90, 1.00, 0.85],
    'Documentary':     [0.60, 0.70, 0.75, 0.75, 0.65, 0.40],
    'Drama':           [0.60, 0.75, 0.85, 0.85, 0.75, 0.55],
    'Family':          [0.85, 1.00, 1.00, 0.85, 0.60, 0.30],
    'Fantasy':         [0.60, 0.85, 0.95, 1.00, 0.90, 0.65],
    'History':         [0.55, 0.70, 0.80, 0.90, 0.85, 0.55],
    'Horror':          [0.35, 0.45, 0.55, 0.75, 0.95, 1.00],
    'Music':           [0.55, 0.75, 0.85, 0.90, 0.80, 0.50],
    'Mystery':         [0.45, 0.60, 0.70, 0.85, 1.00, 0.85],
    'Romance':         [0.50, 0.70, 0.80, 0.95, 0.90, 0.60],
    'Science Fiction': [0.55, 0.70, 0.80, 1.00, 1.00, 0.80],
    'Thriller':        [0.45, 0.60, 0.70, 0.90, 1.00, 0.90],
    'War':             [0.55, 0.70, 0.80, 0.90, 0.85, 0.55],
    'Western':         [0.55, 0.70, 0.80, 0.90, 0.85, 0.55],
    'Default':         [0.50, 0.65, 0.75, 0.85, 0.85, 0.65],
}

# Content categories for Model 1, matched against a film's FULL genre list (not just the first genre)
ACTION_LIKE = ['Action', 'Crime', 'Horror', 'Mystery', 'Thriller', 'War']
FAMILY_FRIENDLY = ['Animation', 'Family']
REGIONAL_LANGUAGES = ['bn', 'cn', 'hi', 'ja', 'kn', 'ko', 'ml', 'mr', 'ta', 'te', 'zh']

GOALS = ['G1', 'G2', 'G3', 'G4', 'G5', 'G6']
GOAL_LABELS = {
    'G1': 'Daily revenue',
    'G2': 'Average occupancy',
    'G3': 'Prime-time genre variety',
    'G4': 'Idle time',
    'G5': 'Prime-time occupancy',
    'G6': 'Follow the Model 2 capacity plan',
}

# AHP pairwise judgments for the Model 4 goal weights (Saaty 1-9 scale; "a is v times as important as b").
# Declared once, from the manager's stated priorities, before looking at any Model 4 result:
#   revenue first; following the capacity plan second; prime-time occupancy third (prime seats are the most
#   valuable); average occupancy and prime-time variety equal; idle time last (with fixed slot starts, idle
#   minutes have little direct cost). Only the consistency ratio (CR < 0.10) was checked.
AHP_JUDGMENTS = [
    ('G1', 'G2', 4), ('G1', 'G3', 4), ('G1', 'G4', 7), ('G1', 'G5', 3), ('G1', 'G6', 2),
    ('G2', 'G3', 1), ('G2', 'G4', 2), ('G5', 'G2', 2), ('G6', 'G2', 2),
    ('G3', 'G4', 2), ('G5', 'G3', 2), ('G6', 'G3', 2),
    ('G5', 'G4', 3), ('G6', 'G4', 4),
    ('G6', 'G5', 1),
]

# Weights used in the first post-implementation run (before the review); kept for the before/after ledger
PRE_REVIEW_WEIGHTS = {'G1': 0.40, 'G2': 0.10, 'G3': 0.10, 'G4': 0.10, 'G5': 0.10, 'G6': 0.20}


def ahp_goal_weights(judgments=None):
    res = ahp_weights(judgments_to_matrix(GOALS, judgments or AHP_JUDGMENTS))
    return {g: float(w) for g, w in res['weights'].items()}, res


DEFAULT_CONFIG = {
    # data and weekly market
    'data_path': str(DATA_PATH),
    'min_vote_count': 200,
    'schedule_week_start': '2014-07-16',
    'window_weeks': 8,
    'lam': 0.55,                                   # weekly demand decay rate λ
    # theatre: screens x 6 slots
    'capacities': [250, 180, 180, 120, 120],       # seats per screen
    'slot_labels': ['9am', '12pm', '3pm', '6pm', '9pm', '12am'],
    'slot_start_min': [9 * 60, 12 * 60, 15 * 60, 18 * 60, 21 * 60, 24 * 60],
    'slot_length': 180,                            # Λ, minutes per slot
    'cleanup': 20,                                 # B, cleanup buffer after each show
    'prices': [120, 150, 180, 250, 280, 200],      # ticket price per slot (₹)
    'slot_factor': [0.55, 0.70, 0.75, 0.95, 1.00, 0.65],
    'prime_slots': [3, 4],                         # 6 pm and 9 pm
    # demand model
    'demand_scale': 650,                           # persons per unit of effective demand (calibrated, then frozen)
    'genre_affinity': GENRE_AFFINITY,
    'action_like': ACTION_LIKE,
    'family_friendly': FAMILY_FRIENDLY,
    'regional_languages': REGIONAL_LANGUAGES,
    # Model 1 — knapsack. Post-review correction B2: fees and budget are half the first values, so weekly
    # ticket revenue covers the licensing spend. Fees are rounded to ₹500 so that every decision is
    # exactly the same as with the first values (the knapsack constraint scales linearly).
    'c_ref': 170,                                  # reference (average) screen size for the film value
    'fee_floor': 100_000,                          # ₹ weekly minimum guarantee, floor
    'fee_premium': 1_250_000,                      # ₹ extra per unit of effective demand
    'fee_round': 500,                              # fees rounded to the nearest ₹500
    'budget': 2_000_000,                           # ₹20 L weekly licensing budget
    'n_min': 8,                                    # variety policy: license 8-12 films
    'n_max': 12,
    # Model 2 — transportation. Post-review correction B3: quotas are set per film, then summed per genre.
    'empty_seat_cost': 20,                         # h, ₹ cost of one empty seat in one show
    'quota_rule': 'film',                          # 'film' (post-review) or 'genre' (first version)
    # Model 3 — assignment
    'k_max': 5,                                    # max showings per film per day
    'm_min': 4,                                    # min operating screens per slot
    'use_c7': True,                                # each screen shows its Model 2 preferred genre
    # Model 4 — goal programming. Post-review addition C1: weights from AHP (see AHP_JUDGMENTS).
    'gp_weights': ahp_goal_weights()[0],
    'gp_occ_step': 0.03,                           # G2 target = M3 avg occupancy + 3 points
    'gp_prime_step': 0.03,                         # G5 target = M3 prime-time occupancy + 3 points
    'gp_idle_step': 5,                             # G4 target = M3 avg idle - 5 minutes
    'gp_div_step': 1,                              # G3 target = M3 prime-time genre count + 1 (max: licensed genres)
    'gp_time_limit': 60,                           # seconds
}

# The configuration of the first implementation (before the review), for the before/after ledger and tests
PRE_REVIEW_OVERRIDES = {
    'fee_floor': 200_000, 'fee_premium': 2_500_000, 'fee_round': 1000, 'budget': 4_000_000,
    'quota_rule': 'genre', 'gp_weights': PRE_REVIEW_WEIGHTS,
}


def default_config():
    return deepcopy(DEFAULT_CONFIG)


def cfg_with(overrides=None, base=None):
    # A copy of the base configuration (default: DEFAULT_CONFIG) with some values replaced.
    cfg = deepcopy(base if base is not None else DEFAULT_CONFIG)
    cfg.update(deepcopy(overrides or {}))
    return cfg


def validate_config(cfg):
    # Problems that would make the models meaningless or crash; [] means the configuration is usable.
    p = []
    T = len(cfg['slot_labels'])
    for key in ('slot_start_min', 'prices', 'slot_factor'):
        if len(cfg[key]) != T:
            p.append(f'{key} must have {T} values (one per slot)')
    if T != 6:
        p.append('the genre-slot affinity table is defined for exactly 6 slots')
    if not 1 <= len(cfg['capacities']) <= 10 or any(c <= 0 for c in cfg['capacities']):
        p.append('need 1-10 screens with positive capacities')
    if any(j < 0 or j >= T for j in cfg['prime_slots']):
        p.append('prime slots must be valid slot indices')
    if cfg['m_min'] > len(cfg['capacities']):
        p.append('minimum operating screens per slot exceeds the number of screens')
    if cfg['n_min'] > cfg['n_max']:
        p.append('minimum films exceeds maximum films')
    if cfg['budget'] <= 0 or cfg['demand_scale'] <= 0:
        p.append('budget and demand scale must be positive')
    if cfg['k_max'] < 1:
        p.append('each film needs at least one allowed show')
    if sum(cfg['gp_weights'].values()) <= 0:
        p.append('goal weights must not all be zero')
    if cfg['slot_length'] <= cfg['cleanup']:
        p.append('slot length must exceed the cleanup time')
    return p
