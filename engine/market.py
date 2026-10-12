"""Weekly market synthesis: turns the static dataset into the films 'in cinemas' for a chosen week."""
import numpy as np
import pandas as pd


def build_weekly_market(clean, week_start, window_weeks, lam):
    w = clean.copy()
    w['schedule_week_start'] = pd.Timestamp(week_start)
    w['weeks_out'] = (w['schedule_week_start'] - w['release_date']).dt.days / 7
    released = w['weeks_out'] >= 0
    w['weekly_decay'] = np.where(released, np.exp(-lam * w['weeks_out'].clip(lower=0)), 0.0)
    w['effective_demand'] = w['popularity_norm'] * w['weekly_decay']
    w['is_current_window'] = w['weeks_out'].between(0, window_weeks, inclusive='both')
    w['market_status'] = np.select(
        [~released, w['weeks_out'] <= 1, w['is_current_window']],
        ['Future release', 'New this week', 'Currently running'],
        default='Older catalogue')
    return w


def build_candidate_pool(market, cfg):
    pool = (market[market['is_current_window']]
            .sort_values('effective_demand', ascending=False)
            .reset_index(drop=True))
    action, family = set(cfg['action_like']), set(cfg['family_friendly'])
    pool['fits'] = pool['runtime'] + cfg['cleanup'] <= cfg['slot_length']
    pool['is_action'] = pool['genre_list'].apply(lambda gl: bool(action & set(gl)))
    pool['is_family'] = pool['genre_list'].apply(lambda gl: bool(family & set(gl)))
    pool['is_regional'] = pool['original_language'].isin(cfg['regional_languages'])
    return pool


def pool_size_by_week(clean, cfg, weeks):
    # Candidate-pool size (and schedulable count) for each week: helps pick a week with enough films.
    rows = []
    for w in weeks:
        wo = (pd.Timestamp(w) - clean['release_date']).dt.days / 7
        in_window = wo.between(0, cfg['window_weeks'], inclusive='both')
        fits = clean['runtime'] + cfg['cleanup'] <= cfg['slot_length']
        rows.append({'week': pd.Timestamp(w), 'pool': int(in_window.sum()), 'schedulable': int((in_window & fits).sum())})
    return pd.DataFrame(rows)
