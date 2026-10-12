"""The four OR models: knapsack (M1), transportation (M2), assignment (M3) and weighted goal programming (M4)."""
import time

import numpy as np
import pandas as pd
import pulp

from .metrics import kpis, make_schedule, n_screens, n_slots, quota_counts, rupees


def _solver(time_limit=None):
    return pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit) if time_limit else pulp.PULP_CBC_CMD(msg=False)


# ---------------------------------------------------------------- Model 1 — film selection (0/1 knapsack ILP)

def solve_knapsack(films, cfg, relax=False):
    # Model 1. relax=True solves the LP relaxation (0 <= y <= 1) for the integrality-gap / sensitivity analysis.
    idx = list(films.index)
    prob = pulp.LpProblem('M1_Knapsack', pulp.LpMaximize)
    y = pulp.LpVariable.dicts('y', idx, lowBound=0, upBound=1, cat='Continuous' if relax else 'Binary')
    prob += pulp.lpSum(films.at[i, 'value'] * y[i] for i in idx)

    n_min = min(cfg['n_min'], int(films['fits'].sum()))       # a very thin week cannot demand more films than exist
    con = {
        'K1 budget':    (pulp.lpSum(films.at[i, 'fee'] * y[i] for i in idx) <= cfg['budget']),
        'K2 min films': (pulp.lpSum(y[i] for i in idx) >= n_min),
        'K2 max films': (pulp.lpSum(y[i] for i in idx) <= cfg['n_max']),
    }
    for name, col in [('K3 action-like', 'is_action'), ('K4 family', 'is_family'), ('K5 regional', 'is_regional')]:
        members = [i for i in idx if films.at[i, col] and films.at[i, 'fits']]
        if members:
            con[name] = pulp.lpSum(y[i] for i in members) >= 1
    for i in idx:
        if not films.at[i, 'fits']:
            con[f'K6 unschedulable {i}'] = y[i] == 0
    for name, c in con.items():
        prob += c, name.replace(' ', '_').replace('-', '_')

    t = time.perf_counter()
    prob.solve(_solver())
    status = pulp.LpStatus[prob.status]
    out = {'status': status, 'solve_s': time.perf_counter() - t, 'prob': prob, 'n_min': n_min,
           'var_labels': {y[i].name: films.at[i, 'title'] for i in idx},
           'con_labels': {name.replace(' ', '_').replace('-', '_'): name for name in con}}
    if status != 'Optimal':
        return out
    yv = pd.Series({i: y[i].value() for i in idx})
    out.update({
        'y': yv,
        'selected': [i for i in idx if yv[i] > 0.5],
        'objective': pulp.value(prob.objective),
        'fee_used': float((films['fee'] * yv).sum()),
        'n_selected': float(yv.sum()),
        'constraints': {name: prob.constraints[name.replace(' ', '_').replace('-', '_')] for name in con},
    })
    return out


def greedy_knapsack(films, cfg):
    # Classic value-per-rupee greedy: add films in order of v/f while they fit the budget (max N_MAX films).
    chosen, spent = [], 0.0
    for i in (films[films['fits']].assign(ratio=lambda d: d['value'] / d['fee']).sort_values('ratio', ascending=False).index):
        if len(chosen) < cfg['n_max'] and spent + films.at[i, 'fee'] <= cfg['budget']:
            chosen.append(i)
            spent += films.at[i, 'fee']
    sel = films.loc[chosen]
    checks = {
        'K1 budget': spent <= cfg['budget'],
        f"K2 film count {cfg['n_min']}-{cfg['n_max']}": cfg['n_min'] <= len(chosen) <= cfg['n_max'],
        'K3 action-like': bool(sel['is_action'].any()) or not films.loc[films['fits'], 'is_action'].any(),
        'K4 family': bool(sel['is_family'].any()) or not films.loc[films['fits'], 'is_family'].any(),
    }
    return {'selected': chosen, 'value': sel['value'].sum(), 'fee_used': spent, 'checks': checks, 'feasible': all(checks.values())}


def binding_table(m):
    # Slack of every Model 1 constraint at the optimum; binding = holds with equality.
    rows = []
    for name, c in m['constraints'].items():
        lhs = sum(coef * v.value() for v, coef in c.items())
        rhs = -c.constant
        sense = {pulp.LpConstraintLE: '≤', pulp.LpConstraintGE: '≥', pulp.LpConstraintEQ: '='}[c.sense]
        slack = rhs - lhs if c.sense == pulp.LpConstraintLE else lhs - rhs
        rows.append({'constraint': name, 'lhs': round(lhs, 2), 'sense': sense, 'rhs': rhs, 'slack': round(slack, 2),
                     'binding': abs(slack) < 1e-6})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Model 2 — screen-genre capacity planning (transportation LP)

def _water_fill(E, lo, hi, target):
    # Integer quotas proportional to E, each clipped to [lo, hi], summing to target (largest-remainder rounding).
    k_lo, k_hi = 0.0, float(hi.max() / max(E.min(), 1e-9)) + 1.0
    for _ in range(200):                                   # sum_g clip(k * E_g, lo_g, hi_g) is monotone in k -> bisection
        k = (k_lo + k_hi) / 2
        k_lo, k_hi = (k, k_hi) if (k * E).clip(lo, hi).sum() < target else (k_lo, k)
    q = (k_hi * E).clip(lo, hi)
    b = np.floor(q + 1e-9)
    order = (q - b).sort_values(ascending=False).index     # largest remainders get the leftover shows
    for g in [g for g in order if b[g] < hi[g]][: int(round(target - b.sum()))]:
        b[g] += 1
    return b


def film_quotas(films, lic, dem, cfg):
    # Shows each licensed film "deserves": proportional to its daily demand, each film clipped to [1, K_MAX].
    total = n_screens(cfg) * n_slots(cfg)
    E = pd.Series({i: dem['D'][i].sum() for i in lic})
    lo, hi = pd.Series(1.0, index=E.index), pd.Series(float(cfg['k_max']), index=E.index)
    return _water_fill(E, lo, hi, min(total, int(hi.sum()))).astype(int)


def genre_quotas(films, lic, dem, cfg):
    # Genre quota b_g. quota_rule 'film' (post-review): sum of the film quotas of the genre's films.
    # quota_rule 'genre' (first version): water-fill on genre demand, clipped to [n_g, K_MAX * n_g].
    total = n_screens(cfg) * n_slots(cfg)
    genre_of = films.loc[lic, 'primary_genre']
    E = pd.Series({g: dem['D'][[i for i in lic if genre_of[i] == g]].sum() for g in genre_of.unique()}).sort_values(ascending=False)
    n_g = genre_of.value_counts().reindex(E.index)
    lo, hi = n_g.astype(float), (cfg['k_max'] * n_g).astype(float)
    if cfg.get('quota_rule', 'film') == 'film':
        fq = film_quotas(films, lic, dem, cfg)
        b = fq.groupby(genre_of.reindex(fq.index)).sum().reindex(E.index).astype(float)
    else:
        b = _water_fill(E, lo, hi, min(total, int(hi.sum())))
    return pd.DataFrame({'films': n_g, 'demand_E': E.round(0), 'share': E / E.sum(), 'raw_quota': total * E / E.sum(),
                         'min': lo, 'max': hi, 'quota_b': b.astype(int)})


def transport_costs(films, lic, dem, cfg, genres):
    # c_sg = mean over the genre's (film, slot) demand values of P_j*max(D - C_s, 0) + h*max(C_s - D, 0).
    cap, price, h = dem['cap'], dem['price'], cfg['empty_seat_cost']
    genre_of = films.loc[lic, 'primary_genre']
    c = pd.DataFrame(0.0, index=range(n_screens(cfg)), columns=genres)
    spill_part = c.copy()
    for g in genres:
        Dg = dem['D'][[i for i in lic if genre_of[i] == g]]          # (films of g, slots)
        for s in range(n_screens(cfg)):
            spill = (price[None, :] * np.maximum(Dg - cap[s], 0)).mean()
            empty = (h * np.maximum(cap[s] - Dg, 0)).mean()
            c.at[s, g], spill_part.at[s, g] = spill + empty, spill
    return c, spill_part


def solve_transportation(films, lic, dem, cfg):
    S, T = n_screens(cfg), n_slots(cfg)
    quotas = genre_quotas(films, lic, dem, cfg)
    genres = list(quotas.index)
    c, spill_part = transport_costs(films, lic, dem, cfg, genres)
    b = quotas['quota_b'].copy()
    if b.sum() < S * T:                                     # unbalanced: dummy genre absorbs unused show-slots (dark screens)
        b['(dark)'] = S * T - b.sum()
        c['(dark)'] = [cfg['empty_seat_cost'] * cap for cap in cfg['capacities']]
        spill_part['(dark)'] = 0.0
    cols = list(b.index)
    degenerate = bool((spill_part.values == 0).all())       # no spill anywhere -> every allocation costs the same
    cost = c.copy()
    if degenerate:                                          # tie-break: larger screens to higher-demand genres
        rank = {g: r for r, g in enumerate(cols)}
        cost = c + pd.DataFrame([[1e-3 * rank[g] * cfg['capacities'][s] / 100 for g in cols] for s in range(S)], columns=cols)

    prob = pulp.LpProblem('M2_Transportation', pulp.LpMinimize)
    x = pulp.LpVariable.dicts('x', [(s, g) for s in range(S) for g in cols], lowBound=0, cat='Continuous')
    prob += pulp.lpSum(cost.at[s, g] * x[(s, g)] for s in range(S) for g in cols)
    for s in range(S):
        prob += pulp.lpSum(x[(s, g)] for g in cols) == T, f'supply_s{s}'
    for k, g in enumerate(cols):
        prob += pulp.lpSum(x[(s, g)] for s in range(S)) == int(b[g]), f'demand_g{k}'
    t = time.perf_counter()
    prob.solve(_solver())
    status = pulp.LpStatus[prob.status]
    out = {'status': status, 'solve_s': time.perf_counter() - t, 'quotas': quotas, 'cost': c, 'degenerate': degenerate,
           'prob': prob,
           'var_labels': {x[(s, g)].name: f"Screen {s} ({cfg['capacities'][s]}) → {g}" for s in range(S) for g in cols},
           'con_labels': {**{f'supply_s{s}': f"Supply: Screen {s} ({cfg['capacities'][s]}) = {T} shows" for s in range(S)},
                          **{f'demand_g{k}': f'Demand: {g} = {int(b[g])} shows' for k, g in enumerate(cols)}}}
    if cfg.get('quota_rule', 'film') == 'film':
        out['film_quota'] = film_quotas(films, lic, dem, cfg)
    if status != 'Optimal':
        return out
    X = pd.DataFrame([[x[(s, g)].value() for g in cols] for s in range(S)], index=range(S), columns=cols)
    demand_rank = {g: r for r, g in enumerate(cols)}
    prefs = {}
    for s in range(S):
        row = X.loc[s, [g for g in cols if g != '(dark)']]
        prefs[s] = sorted(row.index, key=lambda g: (-round(row[g], 6), demand_rank[g]))[0]
    u = pd.Series({s: prob.constraints[f'supply_s{s}'].pi for s in range(S)})
    v = pd.Series({g: prob.constraints[f'demand_g{k}'].pi for k, g in enumerate(cols)})
    out.update({'x': X, 'quota_matrix': X[[g for g in cols if g != '(dark)']].round().astype(int), 'prefs': prefs,
                'total_cost': float((c * X).sum().sum()), 'u': u, 'v': v, 'b': b,
                'reduced_cost': cost - np.add.outer(u.values, v.values),
                'integral': bool(np.allclose(X.values, X.values.round(), atol=1e-6))})
    return out


# ---------------------------------------------------------------- Model 3 — film-screen-slot assignment (binary ILP)

def build_assignment_core(prob, films, lic, prefs, cfg, name='a'):
    # Variables and hard constraints C1-C7 (shared by Model 3 and Model 4).
    S, T = n_screens(cfg), n_slots(cfg)
    a = pulp.LpVariable.dicts(name, [(i, j, s) for i in lic for j in range(T) for s in range(S)], cat='Binary')
    for j in range(T):
        for s in range(S):
            prob += pulp.lpSum(a[(i, j, s)] for i in lic) <= 1, f'C1_cell_{j}_{s}'
    for i in lic:
        for j in range(T):
            prob += pulp.lpSum(a[(i, j, s)] for s in range(S)) <= 1, f'C2_nosimulcast_{i}_{j}'
        if films.at[i, 'runtime'] + cfg['cleanup'] > cfg['slot_length']:
            for j in range(T):
                for s in range(S):
                    prob += a[(i, j, s)] == 0, f'C3_runtime_{i}_{j}_{s}'
        prob += pulp.lpSum(a[(i, j, s)] for j in range(T) for s in range(S)) <= cfg['k_max'], f'C4_maxshows_{i}'
        prob += pulp.lpSum(a[(i, j, s)] for j in range(T) for s in range(S)) >= 1, f'C5_shown_{i}'
    for j in range(T):
        prob += pulp.lpSum(a[(i, j, s)] for i in lic for s in range(S)) >= cfg['m_min'], f'C6_minscreens_{j}'
    if prefs:
        for s, g in prefs.items():
            members = [i for i in lic if films.at[i, 'primary_genre'] == g]
            if members:
                prob += pulp.lpSum(a[(i, j, s)] for i in members for j in range(T)) >= 1, f'C7_pref_{s}'
    return a


def chosen_cells(a):
    return [k for k, v in a.items() if v.value() is not None and v.value() > 0.5]


def solve_assignment(films, lic, dem, prefs, cfg):
    prob = pulp.LpProblem('M3_Assignment', pulp.LpMaximize)
    a = build_assignment_core(prob, films, lic, prefs, cfg)
    prob += pulp.lpSum(dem['rev'][i, j, s] * a[(i, j, s)] for (i, j, s) in a)
    t = time.perf_counter()
    prob.solve(_solver())
    status = pulp.LpStatus[prob.status]
    out = {'status': status, 'solve_s': time.perf_counter() - t, 'n_vars': len(a), 'n_cons': len(prob.constraints),
           'prob': prob}
    if status == 'Optimal':
        cells = chosen_cells(a)
        out.update({'cells': cells, 'R_star': pulp.value(prob.objective), 'schedule': make_schedule(cells, films, dem, cfg)})
    return out


# ---------------------------------------------------------------- Model 4 — weighted goal programming (MILP)

def goal_targets(k_m3, n_genres, R_star, cfg):
    # Each target is one declared step better than what the revenue-only Model 3 achieves (so goals conflict).
    return {
        'G1': R_star,
        'G2': k_m3['avg_occupancy'] + cfg['gp_occ_step'],
        'G3': min(k_m3['prime_genre_diversity'] + cfg['gp_div_step'], n_genres),
        'G4': k_m3['avg_idle_min'] - cfg['gp_idle_step'],
        'G5': k_m3['prime_occupancy'] + cfg['gp_prime_step'],
        'G6': 0.0,
    }


def solve_goal_program(films, lic, dem, prefs, quota, targets, weights, cfg, time_limit=None):
    S, T = n_screens(cfg), n_slots(cfg)
    NC, prime = S * T, cfg['prime_slots']
    n_prime = S * len(prime)
    genres = list(quota.columns)
    prob = pulp.LpProblem('M4_Goal_Programming', pulp.LpMinimize)
    a = build_assignment_core(prob, films, lic, prefs, cfg, name='gp')
    dm = pulp.LpVariable.dicts('d_minus', range(1, 6), lowBound=0)
    dp = pulp.LpVariable.dicts('d_plus', range(1, 6), lowBound=0)
    z = pulp.LpVariable.dicts('z_prime_genre', genres, cat='Binary')
    ep = pulp.LpVariable.dicts('e_plus', [(s, g) for s in range(S) for g in genres], lowBound=0)
    em = pulp.LpVariable.dicts('e_minus', [(s, g) for s in range(S) for g in genres], lowBound=0)
    genre_of = {i: films.at[i, 'primary_genre'] for i in lic}
    occ, rev = dem['occ'], dem['rev']

    revenue = pulp.lpSum(rev[i, j, s] * a[(i, j, s)] for (i, j, s) in a)
    prob += revenue / targets['G1'] + dm[1] - dp[1] == 1, 'G1_revenue'
    prob += pulp.lpSum((occ[i, j, s] - targets['G2']) * a[(i, j, s)] for (i, j, s) in a) / NC + dm[2] - dp[2] == 0, 'G2_avg_occupancy'
    for g in genres:
        prob += z[g] <= pulp.lpSum(a[(i, j, s)] for (i, j, s) in a if genre_of[i] == g and j in prime), f'G3_link_{g}'.replace(' ', '_')
    prob += pulp.lpSum(z[g] for g in genres) / targets['G3'] + dm[3] - dp[3] == 1, 'G3_prime_diversity'
    busy = pulp.lpSum((films.at[i, 'runtime'] + cfg['cleanup']) * a[(i, j, s)] for (i, j, s) in a)
    prob += (NC * cfg['slot_length'] - busy) / (NC * targets['G4']) + dm[4] - dp[4] == 1, 'G4_idle'
    prob += pulp.lpSum((occ[i, j, s] - targets['G5']) * a[(i, j, s)] for (i, j, s) in a if j in prime) / n_prime + dm[5] - dp[5] == 0, 'G5_prime_occupancy'
    for s in range(S):
        for g in genres:
            prob += (pulp.lpSum(a[(i, j, s)] for i in lic if genre_of[i] == g for j in range(T)) - float(quota.at[s, g])
                     == ep[(s, g)] - em[(s, g)]), f'G6_quota_{s}_{g}'.replace(' ', '_')
    dev6 = pulp.lpSum(ep[k] + em[k] for k in ep) / NC

    w = weights
    prob += (w['G1'] * dm[1] + w['G2'] * dm[2] + w['G3'] * dm[3] + w['G4'] * dp[4] + w['G5'] * dm[5] + w['G6'] * dev6
             - 1e-6 * revenue / targets['G1'])
    t = time.perf_counter()
    prob.solve(_solver(time_limit or cfg['gp_time_limit']))
    status = pulp.LpStatus[prob.status]
    out = {'status': status, 'solve_s': time.perf_counter() - t, 'n_vars': len(prob.variables()), 'n_cons': len(prob.constraints),
           'prob': prob}
    if status != 'Optimal':
        return out
    cells = chosen_cells(a)
    dev = {'G1': dm[1].value(), 'G2': dm[2].value(), 'G3': dm[3].value(), 'G4': dp[4].value(), 'G5': dm[5].value(),
           'G6': pulp.value(dev6)}
    out.update({
        'cells': cells, 'schedule': make_schedule(cells, films, dem, cfg),
        'solver_dev': dev,
        'solver_dev_other_side': {'G1': dp[1].value(), 'G2': dp[2].value(), 'G3': dp[3].value(), 'G4': dm[4].value(),
                                  'G5': dp[5].value(), 'G6': 0.0},
        'weighted_deviation': sum(w[k] * v for k, v in dev.items()),
    })
    return out


def goal_report(sched, films, targets, weights, quota, cfg, solver_dev=None):
    # Achieved value and penalised deviation of every goal, recomputed from the schedule itself.
    S, T = n_screens(cfg), n_slots(cfg)
    NC, n_prime = S * T, S * len(cfg['prime_slots'])
    k = kpis(sched, films, cfg, quota=quota)
    prime = sched[sched['slot'].isin(cfg['prime_slots'])]
    dev = {
        'G1': max(0.0, 1 - k['revenue'] / targets['G1']),
        'G2': max(0.0, -((sched['occupancy'] - targets['G2']).sum()) / NC),
        'G3': max(0.0, 1 - k['prime_genre_diversity'] / targets['G3']),
        'G4': max(0.0, k['avg_idle_min'] / targets['G4'] - 1),
        'G5': max(0.0, -((prime['occupancy'] - targets['G5']).sum()) / n_prime),
        'G6': k['quota_deviation'] / NC,
    }
    rows = [
        ('G1', 'Daily revenue (₹)', '≥', targets['G1'], k['revenue']),
        ('G2', 'Average occupancy', '≥', targets['G2'], k['avg_occupancy']),
        ('G3', f'Prime-time genres (of {n_prime} shows)', '≥', targets['G3'], k['prime_genre_diversity']),
        ('G4', 'Average idle per cell (min)', '≤', targets['G4'], k['avg_idle_min']),
        ('G5', 'Prime-time occupancy', '≥', targets['G5'], k['prime_occupancy']),
        ('G6', 'Deviation from Model 2 quota (shows)', '=', 0, k['quota_deviation']),
    ]
    rep = pd.DataFrame(rows, columns=['goal', 'measure', 'sense', 'target', 'achieved'])
    rep['penalised_deviation'] = rep['goal'].map(dev)
    if solver_dev is not None:
        rep['solver_deviation'] = rep['goal'].map(solver_dev)
    rep['weight'] = rep['goal'].map(weights)
    rep['weighted'] = rep['weight'] * rep['penalised_deviation']
    rep['met'] = rep['penalised_deviation'] <= 1e-6
    return rep


def fmt_goal_value(goal, v):
    if goal == 'G1':
        return rupees(v)
    if goal in ('G2', 'G5'):
        return f'{v:.1%}'
    if goal == 'G4':
        return f'{v:.1f}'
    return f'{v:.0f}'


__all__ = ['solve_knapsack', 'greedy_knapsack', 'binding_table', 'film_quotas', 'genre_quotas', 'transport_costs',
           'solve_transportation', 'build_assignment_core', 'chosen_cells', 'solve_assignment', 'goal_targets',
           'solve_goal_program', 'goal_report', 'fmt_goal_value', 'quota_counts']
