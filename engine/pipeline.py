"""The whole chain in one call: market -> demand -> M1 -> M2 -> M3 -> M4 -> baselines, KPIs and validation."""
import time
from dataclasses import dataclass, field

import pandas as pd

from .baselines import baseline_greedy, baseline_naive
from .config import cfg_with, default_config, validate_config
from .data import load_and_clean
from .demand import add_licensing_terms, build_demand
from .market import build_candidate_pool, build_weekly_market
from .metrics import kpis, validate_schedule
from .models import goal_report, goal_targets, solve_assignment, solve_goal_program, solve_knapsack, solve_transportation


@dataclass
class ChainResult:
    cfg: dict
    status: str = 'ok'
    failed_stage: str = None
    timings: dict = field(default_factory=dict)
    manual_licensing: bool = False
    market: pd.DataFrame = None
    films: pd.DataFrame = None
    dem: dict = None
    m1: dict = None
    licensed: list = None
    m2: dict = None
    prefs: dict = None
    quota: pd.DataFrame = None
    m3: dict = None
    R_star: float = None
    k_m3: dict = None
    targets: dict = None
    weights: dict = None
    m4: dict = None
    k_m4: dict = None
    b1_films: list = None
    sched_b1: pd.DataFrame = None
    sched_b2: pd.DataFrame = None
    kb1: dict = None
    kb2: dict = None
    validation: pd.DataFrame = None
    all_valid: bool = None

    @property
    def ok(self):
        return self.status == 'ok'

    @property
    def sched_m3(self):
        return None if self.m3 is None else self.m3.get('schedule')

    @property
    def sched_m4(self):
        return None if self.m4 is None else self.m4.get('schedule')


STAGES = ['m1', 'm2', 'm3', 'm4']


def run_chain(clean, cfg=None, licensed=None, weights=None, baselines=True, upto='m4'):
    # Full chain for one configuration. licensed: optional manual film choice (what-if) that replaces Model 1.
    # upto: stop after this model ('m1' … 'm4'); baselines and validation need the full chain.
    assert upto in STAGES, upto
    cfg = default_config() if cfg is None else cfg
    r = ChainResult(cfg=cfg, manual_licensing=licensed is not None)

    def timed(name, fn):
        t = time.perf_counter()
        out = fn()
        r.timings[name] = time.perf_counter() - t
        return out

    def fail(stage, status):
        r.status, r.failed_stage = f'{stage} {status}', stage
        return r

    problems = validate_config(cfg)
    if problems:
        return fail('Configuration', 'invalid: ' + '; '.join(problems))
    r.market = timed('market', lambda: build_weekly_market(clean, cfg['schedule_week_start'], cfg['window_weeks'], cfg['lam']))
    pool = build_candidate_pool(r.market, cfg)
    r.dem = timed('demand', lambda: build_demand(pool, cfg))
    r.films = add_licensing_terms(pool, r.dem, cfg)
    if len(r.films) == 0 or not r.films['fits'].any():
        return fail('Market', 'no schedulable films in the candidate window')

    if licensed is None:
        r.m1 = timed('M1', lambda: solve_knapsack(r.films, cfg))
        if r.m1['status'] != 'Optimal':
            return fail('Model 1', r.m1['status'])
        r.licensed = r.m1['selected']
    else:
        lic = [i for i in licensed if i in r.films.index and r.films.at[i, 'fits']]
        if not lic:
            return fail('Model 1', 'no schedulable film was chosen')
        r.licensed = lic
    if upto == 'm1':
        return r

    r.m2 = timed('M2', lambda: solve_transportation(r.films, r.licensed, r.dem, cfg))
    if r.m2['status'] != 'Optimal':
        return fail('Model 2', r.m2['status'])
    r.prefs = r.m2['prefs'] if cfg.get('use_c7', True) else None
    r.quota = r.m2['quota_matrix']
    if upto == 'm2':
        return r

    r.m3 = timed('M3', lambda: solve_assignment(r.films, r.licensed, r.dem, r.prefs, cfg))
    if r.m3['status'] != 'Optimal':
        return fail('Model 3', r.m3['status'])
    r.R_star = r.m3['R_star']
    r.k_m3 = kpis(r.m3['schedule'], r.films, cfg, r.licensed, r.quota)
    if upto == 'm3':
        return r

    r.targets = goal_targets(r.k_m3, r.quota.shape[1], r.R_star, cfg)
    r.weights = dict(weights if weights is not None else cfg['gp_weights'])
    r.m4 = timed('M4', lambda: solve_goal_program(r.films, r.licensed, r.dem, r.prefs, r.quota, r.targets, r.weights, cfg))
    if r.m4['status'] != 'Optimal':
        return fail('Model 4', r.m4['status'])
    r.k_m4 = kpis(r.m4['schedule'], r.films, cfg, r.licensed, r.quota)

    if baselines:
        def _baselines():
            b1f, sb1 = baseline_naive(r.films, r.dem, cfg)
            return b1f, sb1, baseline_greedy(r.films, r.licensed, r.dem, cfg)
        r.b1_films, r.sched_b1, r.sched_b2 = timed('baselines', _baselines)
        r.kb1 = kpis(r.sched_b1, r.films, cfg, r.b1_films)
        r.kb2 = kpis(r.sched_b2, r.films, cfg, r.licensed, r.quota)
        r.validation = pd.concat([
            validate_schedule(r.sched_b1, r.films, cfg, r.b1_films, None, 'B1'),
            validate_schedule(r.sched_b2, r.films, cfg, r.licensed, None, 'B2'),
            validate_schedule(r.sched_m3, r.films, cfg, r.licensed, r.prefs, 'M3'),
            validate_schedule(r.sched_m4, r.films, cfg, r.licensed, r.prefs, 'M4')])
        # valid = every physical check passes for all four schedules, and every plan check passes for M3/M4
        # (B1's budget check is reported separately: the naive baseline ignores the budget by definition)
        r.all_valid = bool((r.validation.loc[r.validation['scope'] == 'physical', 'result'] == 'PASS').all()
                           and (r.validation.loc[r.validation['schedule'].isin(['M3', 'M4']), 'result'] != 'FAIL').all())
    return r


def chain_summary(r):
    # Flat summary row of one chain run (the columns of the sensitivity tables).
    out = {'status': r.status}
    if r.films is not None:
        out.update(pool=len(r.films), schedulable=int(r.films['fits'].sum()))
    if not r.ok or r.kb1 is None:
        return out
    f, cfg, lic, q = r.films, r.cfg, r.licensed, r.quota
    gwd = lambda sc: goal_report(sc, f, r.targets, r.weights, q, cfg)['weighted'].sum()
    out.update({
        'B1_fee': f.loc[r.b1_films, 'fee'].sum(), 'B1_within_budget': bool(f.loc[r.b1_films, 'fee'].sum() <= cfg['budget']),
        'films_licensed': len(lic), 'fee_used': float(f.loc[lic, 'fee'].sum()),
        'licensed_avg_weeks_out': f.loc[lic, 'weeks_out'].mean(),
        'licensed_titles': ', '.join(f.loc[lic, 'title'].str[:18]),
        'R_B1': r.kb1['revenue'], 'R_B2': r.kb2['revenue'], 'R_M3': r.R_star, 'R_M4': r.k_m4['revenue'],
        'lift_M4_vs_B1': round(r.k_m4['revenue'] / r.kb1['revenue'] - 1, 6) + 0.0,
        'lift_M4_vs_B2': round(r.k_m4['revenue'] / r.kb2['revenue'] - 1, 6) + 0.0,
        'lift_M3_vs_B2': round(r.R_star / r.kb2['revenue'] - 1, 6) + 0.0,
        'price_of_balance': round(1 - r.k_m4['revenue'] / r.R_star, 6) + 0.0,
        'avg_occ_M3': r.k_m3['avg_occupancy'], 'avg_occ_M4': r.k_m4['avg_occupancy'], 'prime_occ_M4': r.k_m4['prime_occupancy'],
        'spill_M4': r.k_m4['spill'], 'prime_div_M3': r.k_m3['prime_genre_diversity'], 'prime_div_M4': r.k_m4['prime_genre_diversity'],
        'quota_dev_M3': r.k_m3['quota_deviation'], 'quota_dev_M4': r.k_m4['quota_deviation'],
        'weekly_gross_to_fee': r.k_m4['weekly_gross_to_fee'],
        'gwd_B2': gwd(r.sched_b2), 'gwd_M3': gwd(r.sched_m3), 'gwd_M4': gwd(r.sched_m4),
        'all_valid': bool(r.all_valid),
    })
    return out


def run_pipeline(overrides=None, clean=None, base=None):
    # Full chain for one configuration; returns a flat summary row (never raises).
    cfg = cfg_with(overrides, base)
    t0 = time.perf_counter()
    try:
        clean = load_and_clean(cfg)[0] if clean is None else clean
        out = chain_summary(run_chain(clean, cfg))
    except Exception as e:                       # record and carry on — a sweep must never crash
        out = {'status': f'error: {type(e).__name__}: {e}'}
    out['seconds'] = time.perf_counter() - t0
    return out


def sweep(clean, param, values, base=None, label=None, progress=None):
    # One end-to-end run per value of one parameter. progress: optional callback(k, n) for a UI progress bar.
    rows = []
    for k, v in enumerate(values):
        row = run_pipeline({param: v}, clean=clean, base=base)
        row[label or param] = v
        rows.append(row)
        if progress:
            progress(k + 1, len(values))
    df = pd.DataFrame(rows)
    first = [label or param, 'status']
    return df[first + [c for c in df.columns if c not in first]]


def revenue_bridge(r):
    # Splits the B1 -> M4 revenue gap: scheduling effect, selection effect (Model 1) and cost of balance (Model 4).
    opt_b1 = solve_assignment(r.films, r.b1_films, r.dem, None, r.cfg)
    R_b1, R_b1_opt, R_gp = r.kb1['revenue'], opt_b1['R_star'], r.k_m4['revenue']
    return pd.DataFrame([
        ('B1 naive: popular films, round-robin', R_b1, None),
        ('Scheduling effect: same films, optimal placement', R_b1_opt, R_b1_opt - R_b1),
        ('Selection effect: Model 1 films, optimal placement (= M3)', r.R_star, r.R_star - R_b1_opt),
        ('Cost of balance: Model 4 final schedule', R_gp, R_gp - r.R_star),
    ], columns=['step', 'daily revenue', 'change'])
