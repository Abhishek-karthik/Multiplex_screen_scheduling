from itertools import combinations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as E
from app import charts, state, ui

ss = st.session_state
cfg = state.cfg()
ui.header('Model 4 · Multi-objective reconciliation (weighted goal programming, MILP)',
          question='Which schedule best balances revenue with occupancy, prime-time variety, idle time and the Model 2 '
                   'capacity plan, and how much revenue does that balance cost?')
ds = ui.need_data()
ui.formulation(E.formulations.M4)

# ---------------------------------------------------------------- weights: AHP or manual
st.subheader('Goal weights')
mode = st.segmented_control('Set the weights by', ['AHP', 'Manual'], key=state.bind('w_wmode', ss.weights_mode)) or 'AHP'
ss.weights_mode = mode
G = E.GOALS
if mode == 'AHP':
    st.markdown(E.formulations.AHP)
    base = E.judgments_to_matrix(G, ss.ahp_judgments)
    opts = E.SAATY_SCALE

    def snap(v):
        return min(opts, key=lambda o: abs(np.log(o) - np.log(v)))

    st.caption('For each pair, how much more important is one goal than the other? (Saaty 1–9 scale)')
    judg = []
    cols = st.columns(3)
    for k, (a, b) in enumerate(combinations(G, 2)):
        lab = lambda v, a=a, b=b: 'equal' if v == 1 else (f'{a} {v:g}× more' if v > 1 else f'{b} {1 / v:g}× more')
        v = cols[k % 3].select_slider(f'{a} {E.GOAL_LABELS[a]}  vs  {b} {E.GOAL_LABELS[b]}', options=opts, format_func=lab,
                                      key=state.bind(f'w_ahp_{a}_{b}', snap(float(base.at[a, b]))))
        judg.append([a, b, v])
    res = E.ahp_weights(E.judgments_to_matrix(G, judg))
    c1, c2 = st.columns([3, 2])
    with c1:
        st.dataframe(pd.DataFrame({'goal': G, 'meaning': [E.GOAL_LABELS[g] for g in G],
                                   'AHP weight': [res['weights'][g] for g in G]}).round(3), hide_index=True)
    with c2:
        st.metric('Consistency ratio CR', f"{res['CR']:.3f}", help=f"λ_max = {res['lambda_max']:.3f}, CI = {res['CI']:.4f}, RI(6) = {res['RI']}")
        if res['consistent']:
            st.success('Consistent (CR < 0.10): these weights are used.')
            ss.ahp_judgments = judg
            cfg['gp_weights'] = {g: float(w) for g, w in res['weights'].items()}
        else:
            st.error('Inconsistent judgments (CR ≥ 0.10): revise them. The last consistent weights stay in use.')
    with st.expander('Pairwise comparison matrix'):
        st.dataframe(res['matrix'].round(3))
else:
    cols = st.columns(6)
    raw = {g: cols[k].slider(f'{g} {E.GOAL_LABELS[g]}', 0.0, 1.0, step=0.01, key=state.bind(f'w_wman_{g}', round(cfg['gp_weights'][g], 2)))
           for k, g in enumerate(G)}
    tot = sum(raw.values())
    if tot > 0:
        cfg['gp_weights'] = {g: v / tot for g, v in raw.items()}
        st.caption('Normalised weights: ' + ', '.join(f'{g} {w:.3f}' for g, w in cfg['gp_weights'].items()))
    else:
        st.error('At least one weight must be positive.')

with st.expander('Target rule (each target one step better than Model 3)'):
    c1, c2, c3, c4 = st.columns(4)
    cfg['gp_occ_step'] = c1.number_input('G2 occupancy step', 0.0, 0.3, step=0.01, key=state.bind('w_occstep', float(cfg['gp_occ_step'])))
    cfg['gp_prime_step'] = c2.number_input('G5 prime-time step', 0.0, 0.3, step=0.01, key=state.bind('w_primestep', float(cfg['gp_prime_step'])))
    cfg['gp_idle_step'] = c3.number_input('G4 idle step (min)', 0.0, 30.0, step=1.0, key=state.bind('w_idlestep', float(cfg['gp_idle_step'])))
    cfg['gp_div_step'] = c4.number_input('G3 variety step (genres)', 0, 3, step=1, key=state.bind('w_divstep', int(cfg['gp_div_step'])))

ui.solve_button('m4', 'Solve Model 4')
rec, fresh = ui.run_banner('m4')
if rec is None or not state.stage_ok(rec['result'], 'm4'):
    st.stop()
r = rec['result']
m4, rc, F = r.m4, r.cfg, r.films
s3, s4 = r.sched_m3, r.sched_m4
R_gp = r.k_m4['revenue']
pob = (r.R_star - R_gp) / r.R_star

st.subheader('Solution')
ui.solver_panel(m4['prob'], m4['status'], m4['solve_s'], f"{m4['weighted_deviation']:.4f}", 'weighted deviation', key='m4')
rep4 = E.goal_report(s4, F, r.targets, r.weights, r.quota, rc, m4['solver_dev'])
rep3 = E.goal_report(s3, F, r.targets, r.weights, r.quota, rc)
ui.kpi_row([('Final revenue', E.rupees(R_gp)), ('Revenue optimum R*', E.rupees(r.R_star)),
            ('Price of balance', f'{pob:.2%}', '(R* − R_GP) / R*: the share of revenue given up to meet the other goals.'),
            ('Goals met', f"{int(rep4['met'].sum())} of 6")])
if not np.allclose(rep4['penalised_deviation'], rep4['solver_deviation'], atol=1e-5):
    st.error('Solver deviations do not match the schedule!')
table = pd.DataFrame({
    'goal': rep4['goal'], 'measure': rep4['measure'], 'sense': rep4['sense'],
    'target': [E.fmt_goal_value(g, v) for g, v in zip(rep4['goal'], rep4['target'])],
    'Model 3 achieved': [E.fmt_goal_value(g, v) for g, v in zip(rep3['goal'], rep3['achieved'])],
    'Model 4 achieved': [E.fmt_goal_value(g, v) for g, v in zip(rep4['goal'], rep4['achieved'])],
    'deviation (M4)': rep4['penalised_deviation'].round(4), 'weight': rep4['weight'].round(3),
    'met': rep4['met'].map({True: '✔', False: '✘'})})
st.dataframe(table, hide_index=True)
st.caption('Every deviation is recomputed from the schedule and checked against the solver\'s deviation variables.')
st.plotly_chart(charts.goal_chart(rep3, rep4, 'Deviation from each target: Model 3 schedule vs Model 4 schedule'))

key = ['screen', 'slot']
diff = s3[key + ['title', 'revenue']].merge(s4[key + ['title', 'revenue']], on=key, how='outer', suffixes=(' (M3)', ' (M4)'))
diff = diff[diff['title (M3)'].fillna('—') != diff['title (M4)'].fillna('—')].copy()
diff['screen'] = diff['screen'].map(lambda s: E.screen_names(rc)[s])
diff['slot'] = diff['slot'].map(lambda j: rc['slot_labels'][j])
diff['Δ revenue'] = diff['revenue (M4)'].fillna(0) - diff['revenue (M3)'].fillna(0)
st.markdown(f'**{len(diff)} of {len(rc["capacities"]) * len(rc["slot_labels"])} cells changed** from the revenue-only schedule:')
st.dataframe(diff.round(0), hide_index=True)
st.markdown('**Final timetable (colour = genre)**')
st.dataframe(charts.grid_styler(s4, rc))
st.plotly_chart(charts.gantt(s4, rc, 'Model 4 (FINAL): daily Gantt chart'))

k3, k4 = r.k_m3, r.k_m4
st.markdown(f'''**Reading the result.** For **{pob:.2%} of revenue** ({E.rupees(r.R_star - R_gp)}/day) the balanced schedule
moves prime-time variety from {k3['prime_genre_diversity']} to {k4['prime_genre_diversity']} genres, idle time from {k3['avg_idle_min']:.1f} to
{k4['avg_idle_min']:.1f} min per cell and the deviation from the capacity plan from {k3['quota_deviation']:.0f} to {k4['quota_deviation']:.0f}
shows, while average occupancy moves {k3['avg_occupancy']:.1%} → {k4['avg_occupancy']:.1%}. These are trade-offs, priced. The weighted
deviation is Model 4's own objective, so Model 4 always scores lowest on it by construction; the evidence is the per-goal change.''')

# ---------------------------------------------------------------- trade-off curve
st.subheader('Trade-off curve (revenue weight)')
st.caption('Re-solves Model 4 for revenue weights 0.1 … 0.9 (other weights keep their proportions) with the same films, quota and targets.')
tkey = (rec['keys']['m4'], 'tradeoff')
if st.button('Compute trade-off curve'):
    others = {g: w for g, w in r.weights.items() if g != 'G1'}
    rows, bar = [], st.progress(0.0)
    grid = np.round(np.arange(0.1, 0.91, 0.1), 2)
    for k, w1 in enumerate(grid):
        w = {'G1': w1, **{g: (1 - w1) * v / sum(others.values()) for g, v in others.items()}}
        res_ = E.solve_goal_program(F, r.licensed, r.dem, r.prefs, r.quota, r.targets, w, rc)
        if res_['status'] == 'Optimal':
            kk = E.kpis(res_['schedule'], F, rc, r.licensed, r.quota)
            rows.append({'w_revenue': w1, 'revenue': kk['revenue'], 'price_of_balance': 1 - kk['revenue'] / r.R_star,
                         'quota_deviation': kk['quota_deviation'], 'prime_genres': kk['prime_genre_diversity'],
                         'avg_occupancy': kk['avg_occupancy'], 'avg_idle_min': kk['avg_idle_min']})
        bar.progress((k + 1) / len(grid))
    ss.sweeps[tkey] = pd.DataFrame(rows)
if tkey in ss.sweeps:
    t = ss.sweeps[tkey]
    fig = go.Figure(go.Scatter(x=t['quota_deviation'], y=t['price_of_balance'] * 100, mode='lines+markers+text',
                               text=[f'w₁={w:g}' for w in t['w_revenue']], textposition='top right'))
    fig.update_layout(title='Revenue given up vs deviation from the capacity plan', xaxis_title='quota deviation (shows)',
                      yaxis_title='price of balance (% of R*)', height=380, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig)
    st.dataframe(t.round(4), hide_index=True)

ui.handoff('the final schedule and goal report → **Compare & validate** (against the baselines) and **Final plan & export**.',
           'views/compare.py', 'Compare & validate')
