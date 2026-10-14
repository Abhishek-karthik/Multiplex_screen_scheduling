"""Session state: the scenario (configuration), the dataset, and model results with stale detection.

Every stored result carries a hash of the inputs it was computed from. A page shows a result as current only if
that hash matches the current inputs; otherwise it is marked stale. Numbers from different inputs are never mixed.
"""
import hashlib
import json
import time
from copy import deepcopy

import streamlit as st

import engine as E

STAGES = ['m1', 'm2', 'm3', 'm4']
STAGE_LABELS = {'m1': 'Model 1 · Knapsack', 'm2': 'Model 2 · Transportation', 'm3': 'Model 3 · Assignment',
                'm4': 'Model 4 · Goal programming'}
# configuration keys each stage depends on (in addition to everything upstream of it)
STAGE_PARAMS = {
    'market': ['min_vote_count', 'schedule_week_start', 'window_weeks', 'lam', 'cleanup', 'slot_length',
               'action_like', 'family_friendly', 'regional_languages'],
    'demand': ['capacities', 'slot_labels', 'slot_start_min', 'prices', 'slot_factor', 'prime_slots', 'demand_scale',
               'genre_affinity', 'c_ref', 'fee_floor', 'fee_premium', 'fee_round'],
    'm1': ['budget', 'n_min', 'n_max'],
    'm2': ['empty_seat_cost', 'quota_rule', 'k_max'],
    'm3': ['m_min', 'use_c7'],
    'm4': ['gp_weights', 'gp_occ_step', 'gp_prime_step', 'gp_idle_step', 'gp_div_step', 'gp_time_limit'],
}
ORDER = ['market', 'demand'] + STAGES


def init():
    ss = st.session_state
    if 'cfg' not in ss:
        ss.cfg = E.default_config()
    ss.setdefault('upload', None)          # (file name, bytes, sha1) of an uploaded dataset
    ss.setdefault('use_upload', False)
    ss.setdefault('runs', {})              # stage -> run record (see run())
    ss.setdefault('sweeps', {})
    ss.setdefault('whatif', None)
    ss.setdefault('ahp_judgments', [list(j) for j in E.AHP_JUDGMENTS])
    ss.setdefault('weights_mode', 'AHP')


def cfg():
    return st.session_state.cfg


def _hash(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def data_key():
    up = st.session_state.upload
    return f'upload:{up[2]}' if st.session_state.use_upload and up else 'bundled'


def stage_key(stage, c=None):
    c = c or cfg()
    parts = [data_key()]
    for s in ORDER:
        parts.append({k: c[k] for k in STAGE_PARAMS[s]})
        if s == stage:
            break
    return _hash(parts)


def scenario_hash():
    return _hash([data_key(), cfg()])


# ---------------------------------------------------------------- data (cached: cleaning takes ~1-3 s)

@st.cache_resource(max_entries=4, show_spinner='Loading and cleaning the dataset…')
def _load(key, min_vote_count, _raw_bytes):
    raw = E.read_dataset(_raw_bytes) if _raw_bytes is not None else E.read_dataset(E.DATA_PATH)
    problems = E.check_schema(raw)
    if problems:
        return raw, None, None, problems
    clean, steps = E.load_and_clean({'data_path': None, 'min_vote_count': min_vote_count}, raw=raw)
    if clean.empty:
        problems = ['no films are left after cleaning (check the minimum vote count)']
    return raw, clean, steps, problems


def dataset():
    # The current dataset. Treat the returned frames as read-only (they are shared by the cache).
    ss = st.session_state
    key = data_key()
    up = ss.upload
    raw_bytes = up[1] if key.startswith('upload') else None
    raw, clean, steps, problems = _load(key, cfg()['min_vote_count'], raw_bytes)
    name = up[0] if key.startswith('upload') else 'tmdb_5000_movies.csv (bundled TMDB 5000)'
    return {'key': key, 'name': name, 'raw': raw, 'clean': clean, 'steps': steps, 'problems': problems}


@st.cache_resource(max_entries=16)
def _base(key, _clean, cfg_json):
    c = json.loads(cfg_json)
    market = E.build_weekly_market(_clean, c['schedule_week_start'], c['window_weeks'], c['lam'])
    pool = E.build_candidate_pool(market, c)
    dem = E.build_demand(pool, c)
    films = E.add_licensing_terms(pool, dem, c)
    return {'market': market, 'films': films, 'dem': dem}


def base():
    # Weekly market, candidate pool, demand tensors and licensing terms for the current scenario (or None).
    ds = dataset()
    if ds['clean'] is None:
        return None
    c = cfg()
    sub = {k: c[k] for k in STAGE_PARAMS['market'] + STAGE_PARAMS['demand']}
    return _base(stage_key('demand'), ds['clean'], json.dumps(sub, sort_keys=True, default=str))


# ---------------------------------------------------------------- model runs

def run(upto):
    # Solve Models 1..upto for the current scenario and store the result. Returns the run record.
    ds = dataset()
    if ds['clean'] is None:
        return None
    c = deepcopy(cfg())
    t = time.perf_counter()
    result = E.run_chain(ds['clean'], c, upto=upto, baselines=(upto == 'm4'))
    record = {'upto': upto, 'result': result, 'keys': {s: stage_key(s, c) for s in STAGES[:STAGES.index(upto) + 1]},
              'seconds': time.perf_counter() - t, 'when': time.strftime('%H:%M:%S'), 'ts': time.time()}
    st.session_state.runs[upto] = record
    return record


def latest(stage):
    # (record, fresh) for the most recent run that reached `stage`, or (None, False).
    runs = [r for u, r in st.session_state.runs.items() if STAGES.index(u) >= STAGES.index(stage)]
    if not runs:
        return None, False
    current = stage_key(stage)
    fresh = [r for r in runs if r['keys'].get(stage) == current]
    pick = max(fresh or runs, key=lambda r: r['ts'])
    return pick, bool(fresh)


def stage_status(stage):
    # 'ok' | 'failed' | 'stale' | 'not run'
    rec, fresh = latest(stage)
    if rec is None:
        return 'not run'
    if not fresh:
        return 'stale'
    return 'ok' if stage_ok(rec['result'], stage) else 'failed'


def stage_ok(result, stage):
    # Did `result` successfully produce `stage`?
    attr = {'m1': 'licensed', 'm2': 'quota', 'm3': 'k_m3', 'm4': 'k_m4'}[stage]
    return getattr(result, attr) is not None


def reset_scenario():
    ss = st.session_state
    ss.cfg = E.default_config()
    ss.runs, ss.sweeps, ss.whatif = {}, {}, None
    ss.ahp_judgments = [list(j) for j in E.AHP_JUDGMENTS]
    ss.weights_mode = 'AHP'
    for k in [k for k in ss.keys() if str(k).startswith('w_')]:
        del ss[k]


def bind(key, default):
    # Widget value persisted in session_state under `key` (initialised once from `default`).
    if key not in st.session_state:
        st.session_state[key] = default
    return key
