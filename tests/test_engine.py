"""Engine tests: reproducibility, post-review corrections, AHP, sensitivity reports, validator and robustness.

Run from the project root:  python -m pytest -q
"""
import numpy as np
import pandas as pd
import pulp
import pytest

import engine as E


@pytest.fixture(scope='module')
def clean():
    return E.load_and_clean(E.default_config())[0]


@pytest.fixture(scope='module')
def main(clean):
    return E.run_chain(clean, E.default_config())


# ---------------------------------------------------------------- reproducibility

def test_cleaning_funnel(clean):
    assert len(clean) == 2571


def test_first_version_numbers_are_reproduced(clean):
    # The engine run with the first (pre-review) configuration must give exactly the first notebook's results.
    r = E.run_chain(clean, E.cfg_with(E.PRE_REVIEW_OVERRIDES))
    assert r.ok
    assert np.isclose(r.R_star, 419_710.81, atol=1)
    assert np.isclose(r.k_m4['revenue'], 413_524.35, atol=1)
    assert np.isclose(r.kb1['revenue'], 257_293.65, atol=1)
    assert round(r.m1['objective']) == 405_270
    assert round(r.m2['total_cost']) == 129_780


def test_main_scenario(main):
    r = main
    assert r.ok and r.all_valid
    assert r.films.loc[r.licensed, 'title'].tolist() == [
        'Lucy', 'Dawn of the Planet of the Apes', 'Deliver Us from Evil', 'How to Train Your Dragon 2',
        'Earth to Echo', 'Maleficent', 'Jersey Boys', 'Edge of Tomorrow']
    assert np.isclose(r.R_star, 419_710.81, atol=1)
    assert np.isclose(r.k_m4['revenue'], 416_229.57, atol=1)
    assert r.k_m4['quota_deviation'] == 0
    assert r.films.loc[r.licensed, 'fee'].sum() <= r.cfg['budget']
    assert 1.4 < r.k_m4['weekly_gross_to_fee'] < 1.5
    # the solver's goal deviations equal the ones recomputed from the schedule
    rep = E.goal_report(r.sched_m4, r.films, r.targets, r.weights, r.quota, r.cfg, r.m4['solver_dev'])
    assert np.allclose(rep['penalised_deviation'], rep['solver_deviation'], atol=1e-5)


def test_run_pipeline_matches_run_chain(clean, main):
    s = E.run_pipeline(clean=clean)
    assert s['status'] == 'ok'
    assert np.isclose(s['R_M4'], main.k_m4['revenue'])


# ---------------------------------------------------------------- post-review corrections

def test_fee_halving_changes_no_decision(clean):
    pre = E.PRE_REVIEW_OVERRIDES
    half = {'fee_floor': 100_000, 'fee_premium': 1_250_000, 'fee_round': 500}
    for ov in [{'lam': 0.35}, {'lam': 0.75}, {'schedule_week_start': '2012-10-10'}]:
        a = E.run_pipeline({**pre, **ov}, clean=clean)
        b = E.run_pipeline({**pre, **half, 'budget': 2_000_000, **ov}, clean=clean)
        assert a['licensed_titles'] == b['licensed_titles']
        assert np.isclose(a['R_M4'], b['R_M4'])


def test_film_level_quota_respects_film_caps(main):
    fq = main.m2['film_quota']
    assert fq.sum() == 30 and fq.min() >= 1 and fq.max() <= main.cfg['k_max']
    genre_of = main.films.loc[fq.index, 'primary_genre']
    assert fq.groupby(genre_of).sum().to_dict() == main.m2['quotas']['quota_b'].to_dict()


# ---------------------------------------------------------------- AHP

def test_ahp_recovers_weights_of_a_consistent_matrix():
    w = np.array([0.5, 0.3, 0.2])
    res = E.ahp_weights(pd.DataFrame(w[:, None] / w[None, :], index=list('abc'), columns=list('abc')))
    assert np.allclose(list(res['weights'].values()), w)
    assert abs(res['CR']) < 1e-9 and res['consistent']


def test_project_ahp_judgments_are_consistent():
    weights, res = E.ahp_goal_weights()
    assert res['CR'] < 0.10
    assert np.isclose(sum(weights.values()), 1.0)
    assert max(weights, key=weights.get) == 'G1'
    assert E.default_config()['gp_weights'] == weights


# ---------------------------------------------------------------- sensitivity reports (C2)

def _brute_force_cost_ranges(prob, report, labels, maximize):
    variables = prob.variables()
    x_star = {v.name: v.value() for v in variables}
    c0 = {v.name: 0.0 for v in variables}
    c0.update({v.name: c for v, c in prob.objective.items()})
    by_label = {lab: name for name, lab in labels.items()}
    bad = 0
    for _, row in report['variables'].iterrows():
        name = by_label[row['variable']]
        for delta, should_stay in [(row['allowable increase'] * 0.98, True), (row['allowable increase'] * 1.02 + 1, False),
                                   (-row['allowable decrease'] * 0.98, True), (-row['allowable decrease'] * 1.02 - 1, False)]:
            if not np.isfinite(delta) or abs(delta) > 1e7 or (should_stay and delta == 0):
                continue
            q = prob.deepcopy()
            q.setObjective(pulp.lpSum((c0[v.name] + (delta if v.name == name else 0)) * v for v in variables))
            q.solve(pulp.PULP_CBC_CMD(msg=False))
            opt = pulp.value(q.objective)
            val = sum((c0[n] + (delta if n == name else 0)) * x_star[n] for n in c0)
            tol = 1e-6 * max(1, abs(opt))
            stays = val >= opt - tol if maximize else val <= opt + tol
            bad += stays != should_stay
    return bad


def test_transportation_report_ranges_are_exact(main):
    m2 = main.m2
    rep = E.lp_sensitivity_report(m2['prob'], m2['var_labels'], m2['con_labels'])
    assert np.isclose(rep['objective'], pulp.value(m2['prob'].objective))
    assert _brute_force_cost_ranges(m2['prob'], rep, m2['var_labels'], maximize=False) == 0
    # shadow prices are the solver's own duals (the MODI potentials)
    assert np.allclose(rep['constraints']['shadow price'].iloc[:5].values, m2['u'].values, atol=1e-6)


def test_knapsack_lp_report_budget_shadow_price(main):
    lp = E.solve_knapsack(main.films, main.cfg, relax=True)
    rep = E.lp_sensitivity_report(lp['prob'], lp['var_labels'], lp['con_labels'])
    assert _brute_force_cost_ranges(lp['prob'], rep, lp['var_labels'], maximize=True) == 0
    k1 = rep['constraints'].set_index('constraint').loc['K1 budget']
    for frac in (0.5, -0.5):
        db = frac * (k1['allowable increase'] if frac > 0 else k1['allowable decrease'])
        z = E.solve_knapsack(main.films, E.cfg_with({'budget': main.cfg['budget'] + db}), relax=True)['objective']
        assert np.isclose(z - lp['objective'], k1['shadow price'] * db, rtol=1e-6)


def test_report_rejects_integer_models(main):
    with pytest.raises(ValueError):
        E.lp_sensitivity_report(main.m3['prob'])


# ---------------------------------------------------------------- validator and robustness

def test_validator_detects_violations(main):
    bad = pd.concat([main.sched_m4, main.sched_m4.iloc[[0]]])          # the same film twice in one cell
    v = E.validate_schedule(bad, main.films, main.cfg, main.licensed, main.prefs)
    assert (v.set_index('check').loc['1 At most one film per screen-slot', 'result']) == 'FAIL'


def test_infeasible_budget_fails_gracefully(clean):
    r = E.run_chain(clean, E.cfg_with({'budget': 300_000}))
    assert not r.ok and r.failed_stage == 'Model 1'
    assert E.run_pipeline({'budget': 300_000}, clean=clean)['status'].startswith('Model 1')


def test_manual_licensing_what_if(clean, main):
    pick = main.films.index[main.films['fits']][:6].tolist()
    r = E.run_chain(clean, E.default_config(), licensed=pick)
    assert r.ok and r.manual_licensing and set(r.licensed) == set(pick)


@pytest.mark.parametrize('caps', [[250, 180, 120, 120], [300, 250, 180, 180, 120, 120]])
def test_other_theatre_sizes(clean, caps):
    cfg = E.cfg_with({'capacities': caps, 'm_min': len(caps) - 1})
    r = E.run_chain(clean, cfg)
    assert r.ok and r.all_valid
    assert len(r.sched_m4) <= len(caps) * 6


def test_explain_cell_matches_demand_tensor(main):
    e = E.explain_cell(main.films, main.dem, main.cfg, 0, 4, 0)
    assert np.isclose(e['demand'], e['demand_scale'] * e['effective_demand'] * e['slot_factor'] * e['affinity'])
    assert np.isclose(e['attendance'], min(e['demand'], e['capacity']))
    assert np.isclose(e['revenue'], e['price'] * e['attendance'])


def test_schema_check():
    good = pd.read_csv(E.DATA_PATH, nrows=20)
    assert E.check_schema(good) == []
    assert any('missing column' in p for p in E.check_schema(good.drop(columns=['runtime'])))
