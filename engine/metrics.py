"""One schedule table, one KPI definition and one hard-constraint validator for every schedule."""
import numpy as np
import pandas as pd


def n_screens(cfg):
    return len(cfg['capacities'])


def n_slots(cfg):
    return len(cfg['slot_labels'])


def minutes_to_clock(m):
    return f'{int(m // 60) % 24:02d}:{int(m % 60):02d}'


def rupees(x):
    return f'₹{x:,.0f}'


def signed_pct(x, digits=1):
    # '+12.3%' style, without printing '-0.0%' for tiny negative rounding noise
    return f'{round(x, digits + 2) + 0.0:+.{digits}%}'


def screen_names(cfg):
    return [f'Screen {s} ({c})' for s, c in enumerate(cfg['capacities'])]


SCHEDULE_COLUMNS = ['screen', 'capacity', 'slot', 'time', 'film', 'title', 'genre', 'runtime', 'price', 'demand',
                    'attendance', 'occupancy', 'revenue', 'spill', 'start_min', 'end_min', 'start',
                    'end_with_cleanup', 'idle_min']


def make_schedule(cells, films, dem, cfg):
    # cells: iterable of (film i, slot j, screen s) -> one row per show, sorted by screen and slot.
    rows = []
    for i, j, s in cells:
        start = cfg['slot_start_min'][j]
        runtime = float(films.at[i, 'runtime'])
        rows.append({
            'screen': s, 'capacity': cfg['capacities'][s], 'slot': j, 'time': cfg['slot_labels'][j],
            'film': i, 'title': films.at[i, 'title'], 'genre': films.at[i, 'primary_genre'],
            'runtime': runtime, 'price': cfg['prices'][j],
            'demand': dem['D'][i, j], 'attendance': dem['att'][i, j, s], 'occupancy': dem['occ'][i, j, s],
            'revenue': dem['rev'][i, j, s], 'spill': dem['spill'][i, j, s],
            'start_min': start, 'end_min': start + runtime + cfg['cleanup'],
            'start': minutes_to_clock(start), 'end_with_cleanup': minutes_to_clock(start + runtime + cfg['cleanup']),
            'idle_min': cfg['slot_length'] - runtime - cfg['cleanup'],
        })
    return pd.DataFrame(rows, columns=SCHEDULE_COLUMNS).sort_values(['screen', 'slot']).reset_index(drop=True)


def schedule_grid(sched, cfg, value='title'):
    # screens-by-slots table of titles (or any other column).
    grid = sched.pivot(index='screen', columns='slot', values=value).reindex(
        index=range(n_screens(cfg)), columns=range(n_slots(cfg)))
    grid.index = screen_names(cfg)
    grid.columns = cfg['slot_labels']
    return grid.fillna('—') if value == 'title' else grid


def quota_counts(sched, genres, cfg):
    # Shows of each genre on each screen (compare with Model 2's x[s,g]).
    counts = pd.crosstab(sched['screen'], sched['genre']).reindex(index=range(n_screens(cfg)), columns=genres, fill_value=0)
    return counts.fillna(0)


def kpis(sched, films, cfg, licensed=None, quota=None):
    # One KPI definition for every schedule.
    S, T = n_screens(cfg), n_slots(cfg)
    n_cells = S * T
    prime = sched[sched['slot'].isin(cfg['prime_slots'])]
    shown = sorted(sched['film'].unique())
    lic = shown if licensed is None else list(licensed)
    fee_col = 'fee' if 'fee' in films.columns else None
    k = {
        'revenue': sched['revenue'].sum(),
        'seats_sold': sched['attendance'].sum(),
        'shows': len(sched),
        'empty_cells': n_cells - len(sched),
        'avg_occupancy': sched['occupancy'].mean() if len(sched) else 0.0,
        'seat_weighted_occupancy': sched['attendance'].sum() / sched['capacity'].sum() if len(sched) else 0.0,
        'prime_occupancy': prime['occupancy'].mean() if len(prime) else 0.0,
        'spill': sched['spill'].sum(),
        'films_shown': len(shown),
        'genres_covered': sched['genre'].nunique(),
        'prime_genre_diversity': prime['genre'].nunique(),
        'avg_idle_min': (n_cells * cfg['slot_length'] - (sched['runtime'] + cfg['cleanup']).sum()) / n_cells,
        'utilisation': sched['runtime'].sum() / (n_cells * cfg['slot_length']),
        'licensing_cost': films.loc[lic, fee_col].sum() if fee_col else np.nan,
    }
    k['weekly_gross_to_fee'] = 7 * k['revenue'] / k['licensing_cost'] if fee_col and k['licensing_cost'] else np.nan
    if quota is not None:
        counts = quota_counts(sched, list(quota.columns), cfg)
        k['quota_deviation'] = float(np.abs(counts.values - quota.values).sum())
    return k


def validate_schedule(sched, films, cfg, licensed=None, prefs=None, name='schedule'):
    # Hard-constraint check. 'physical' checks must hold for ANY schedule;
    # 'plan' checks test consistency with the Model 1 / Model 2 plan (n/a when no plan is given).
    T = n_slots(cfg)
    res = []

    def add(check, scope, ok, detail=''):
        res.append({'schedule': name, 'check': check, 'scope': scope,
                    'result': 'n/a' if ok is None else ('PASS' if ok else 'FAIL'), 'detail': detail})

    dup_cell = sched.duplicated(['slot', 'screen']).sum()
    add('1 At most one film per screen-slot', 'physical', dup_cell == 0, f'{dup_cell} clashes')
    too_long = (sched['runtime'] + cfg['cleanup'] > cfg['slot_length']).sum()
    add('2 Runtime + cleanup ≤ slot length', 'physical', too_long == 0,
        f"longest show {sched['runtime'].max():.0f}+{cfg['cleanup']} min vs {cfg['slot_length']} min")
    simul = sched.duplicated(['film', 'slot']).sum()
    add('3 No simultaneous duplicate (simulcast)', 'physical', simul == 0, f'{simul} simulcasts')
    max_show = sched['film'].value_counts().max() if len(sched) else 0
    add('4 Showings per film ≤ K_MAX', 'physical', max_show <= cfg['k_max'], f"max {max_show} vs {cfg['k_max']}")
    per_slot = sched.groupby('slot').size().reindex(range(T), fill_value=0)
    add('5 Operating screens per slot ≥ M_MIN', 'physical', per_slot.min() >= cfg['m_min'],
        f"min {per_slot.min()} vs {cfg['m_min']}")
    if licensed is None:
        add('6 Only licensed films shown', 'plan', None)
        add('7 Every licensed film shown', 'plan', None)
    else:
        lic = set(licensed)
        extra = set(sched['film']) - lic
        missing = lic - set(sched['film'])
        add('6 Only licensed films shown', 'plan', not extra, f'{len(extra)} unlicensed')
        add('7 Every licensed film shown', 'plan', not missing, f'{len(missing)} licensed but unused')
    if prefs is None:
        add('8 Preferred genre on each screen (Model 2)', 'plan', None)
    else:
        bad = [s for s, g in prefs.items() if not ((sched['screen'] == s) & (sched['genre'] == g)).any()]
        add('8 Preferred genre on each screen (Model 2)', 'plan', not bad, f'screens missing it: {bad}' if bad else 'all screens')
    if licensed is None or 'fee' not in films.columns:
        add('9 Licensing cost ≤ budget', 'plan', None)
    else:
        cost = films.loc[list(licensed), 'fee'].sum()
        add('9 Licensing cost ≤ budget', 'plan', cost <= cfg['budget'], f"{rupees(cost)} vs {rupees(cfg['budget'])}")
    return pd.DataFrame(res)
