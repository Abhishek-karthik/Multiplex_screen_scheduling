"""Demand model (persons, capped by screen capacity) and the licensing terms used by Model 1."""
import numpy as np


def build_demand(films, cfg):
    # Demand / attendance / occupancy / revenue / spill tensors for every candidate film.
    cap = np.array(cfg['capacities'], dtype=float)
    price = np.array(cfg['prices'], dtype=float)
    sf = np.array(cfg['slot_factor'], dtype=float)
    aff_table = cfg['genre_affinity']
    aff = np.array([aff_table.get(g, aff_table['Default']) for g in films['primary_genre']], dtype=float).reshape(len(films), -1)
    D = cfg['demand_scale'] * films['effective_demand'].to_numpy()[:, None] * sf[None, :] * aff     # (n, T)
    att = np.minimum(D[:, :, None], cap[None, None, :])                                           # (n, T, S)
    return {
        'D': D, 'att': att, 'occ': att / cap[None, None, :], 'rev': price[None, :, None] * att,
        'spill': np.maximum(D[:, :, None] - cap[None, None, :], 0.0), 'cap': cap, 'price': price,
    }


def add_licensing_terms(films, dem, cfg):
    # value v_i = sum_j P_j * min(D_ij, C_ref): daily revenue potential of one show per slot on an average screen.
    # fee f_i = FEE_FLOOR + FEE_PREMIUM * e_i: weekly minimum guarantee, rounded to cfg['fee_round'] rupees.
    f = films.copy()
    f['value'] = (dem['price'][None, :] * np.minimum(dem['D'], cfg['c_ref'])).sum(axis=1).round(0)
    r = cfg.get('fee_round', 1000)
    f['fee'] = ((cfg['fee_floor'] + cfg['fee_premium'] * f['effective_demand']) / r).round() * r
    return f


def explain_cell(films, dem, cfg, i, j, s):
    # Every factor of the demand calculation for one film i, slot j and screen s (for the UI explainer).
    g = films.at[i, 'primary_genre']
    aff_table = cfg['genre_affinity']
    aff = aff_table.get(g, aff_table['Default'])[j]
    return {
        'title': films.at[i, 'title'], 'genre': g, 'slot': cfg['slot_labels'][j], 'screen': s,
        'popularity_norm': float(films.at[i, 'popularity_norm']),
        'weeks_out': float(films.at[i, 'weeks_out']),
        'weekly_decay': float(films.at[i, 'weekly_decay']),
        'effective_demand': float(films.at[i, 'effective_demand']),
        'demand_scale': cfg['demand_scale'],
        'slot_factor': cfg['slot_factor'][j],
        'affinity': aff,
        'demand': float(dem['D'][i, j]),
        'capacity': float(dem['cap'][s]),
        'attendance': float(dem['att'][i, j, s]),
        'occupancy': float(dem['occ'][i, j, s]),
        'price': float(dem['price'][j]),
        'revenue': float(dem['rev'][i, j, s]),
        'spill': float(dem['spill'][i, j, s]),
    }
