import numpy as np
import pandas as pd
import pulp
import streamlit as st

import engine as E
from app import charts, state, ui

cfg = state.cfg()
ui.header('Model 2 · Screen–genre capacity planning (transportation LP)',
          question='How should the daily show capacity of the screens be split across genres, so that big screens carry high-demand genres?')
ds = ui.need_data()
ui.formulation(E.formulations.M2)

st.subheader('Controls')
c1, c2 = st.columns(2)
cfg['empty_seat_cost'] = c1.number_input('Cost of one empty seat in one show, h (₹)', 0, 500, step=5,
                                         key=state.bind('w_h', int(cfg['empty_seat_cost'])))
rule = c2.radio('Quota rule', ['film', 'genre'], horizontal=True, key=state.bind('w_quota_rule', cfg['quota_rule']),
                format_func=lambda v: {'film': 'per film, summed per genre (post-review)', 'genre': 'per genre (first version)'}[v])
cfg['quota_rule'] = rule

ui.solve_button('m2', 'Solve Model 2')
rec, fresh = ui.run_banner('m2')
if rec is None or not state.stage_ok(rec['result'], 'm2'):
    st.stop()
r = rec['result']
m2, rc, F = r.m2, r.cfg, r.films
names = E.screen_names(rc)

st.subheader('Solution')
ui.solver_panel(m2['prob'], m2['status'], m2['solve_s'], E.rupees(m2['total_cost']), 'mismatch cost / day', key='m2')
ui.kpi_row([('Integral without integer constraints', 'yes' if m2['integral'] else 'no', 'Total unimodularity: every vertex of a transportation polytope with integer supplies/demands is integral.'),
            ('Supply = demand', f"{int(m2['b'].sum())} = {len(names) * len(rc['slot_labels'])} shows"),
            ('Degenerate costs (no spill anywhere)', 'yes' if m2['degenerate'] else 'no')])

c1, c2 = st.columns(2)
with c1:
    st.markdown('**Genre quotas b_g (shows per day)**')
    st.dataframe(m2['quotas'].round({'share': 3, 'raw_quota': 2}))
with c2:
    if 'film_quota' in m2:
        st.markdown('**Film quotas (summed per genre)**')
        fq = m2['film_quota']
        st.dataframe(pd.DataFrame({'title': F.loc[fq.index, 'title'], 'genre': F.loc[fq.index, 'primary_genre'],
                                   'daily demand': [round(r.dem['D'][i].sum()) for i in fq.index], 'quota': fq.values}), hide_index=True)

st.plotly_chart(charts.sankey(m2['x'], rc, 'Optimal flow: show-slots from screens to genres (width = shows per day)'))
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(charts.heatmap(m2['cost'].set_axis(names) / 1000, 'Mismatch cost c[s,g] (₹ thousand per show)', fmt='.1f', colorscale='Reds'))
with c2:
    st.plotly_chart(charts.heatmap(m2['x'].set_axis(names), 'Optimal allocation x[s,g] (shows per day)', fmt='.0f', colorscale='Greens'))

uniform = pd.DataFrame([[len(rc['slot_labels']) * m2['b'][g] / (len(names) * len(rc['slot_labels'])) for g in m2['x'].columns]
                        for _ in names], columns=m2['x'].columns)
uniform_cost = float((m2['cost'] * uniform).sum().sum())
st.markdown(f"**Benchmark:** giving every screen the same genre mix would cost {E.rupees(uniform_cost)} per day; the optimal plan "
            f"saves **{E.rupees(uniform_cost - m2['total_cost'])} ({(uniform_cost - m2['total_cost']) / uniform_cost:.1%})** of mismatch.")

st.subheader('Duals and sensitivity')
t1, t2 = st.tabs(['MODI potentials', 'Sensitivity report'])
with t1:
    shift = m2['u'][0]
    u_n, v_n = m2['u'] - shift, m2['v'] + shift
    c1, c2 = st.columns(2)
    c1.dataframe(pd.DataFrame({'u_s (screen potential)': u_n.values}, index=names).round(1))
    c2.dataframe(pd.DataFrame({'v_g (genre potential)': v_n.round(1)}))
    rcost = m2['reduced_cost']
    st.markdown(f"MODI optimality check: the smallest reduced cost c − u − v is **{round(rcost.values.min(), 3) + 0.0:.3f}** (≥ 0 ⇒ optimal); "
                f"on used cells it is {np.abs(rcost.values[m2['x'].values > 1e-6]).max():.4f} (≈ 0). Potentials are normalised so u(Screen 0) = 0; "
                'only their differences carry meaning, because one constraint of a balanced problem is redundant.')
with t2:
    rep = E.lp_sensitivity_report(m2['prob'], m2['var_labels'], m2['con_labels'])
    vs = rep['variables']
    show_all = st.toggle('Show unused cells too', value=False)
    st.dataframe((vs if show_all else vs[vs['final value'] > 1e-9]).round(1), hide_index=True)
    st.dataframe(rep['constraints'].round(1), hide_index=True)
    ties = vs[(vs['final value'] <= 1e-9) & (vs['reduced cost'].abs() <= 1e-3)]
    fragile = vs[(vs['final value'] > 1e-9) & (vs['allowable increase'] <= 1e-6)]
    robust = vs[(vs['final value'] > 1e-9) & (vs['allowable increase'] > 1e-6)].sort_values('allowable increase', ascending=False)
    st.markdown(
        f"* **Robust assignments:** {', '.join(f'{x} (+{E.rupees(v)} per show)' for x, v in zip(robust['variable'].head(3), robust['allowable increase'].head(3))) or 'none'}: "
        'their cost can rise that much before the plan changes.\n'
        f"* **Alternative optima:** {len(ties)} unused cell(s) have zero reduced cost and {len(fragile)} used cell(s) have no room to get dearer, "
        f"so {'other plans with exactly the same cost exist' if len(ties) or len(fragile) else 'the plan is unique'}.\n"
        '* **Right-hand-side ranges are 0** because the problem is balanced: one supply or demand cannot change on its own. '
        'Read shadow prices in pairs: one more show of genre g on screen s costs about u_s + v_g.')
    if not np.isclose(rep['objective'], pulp.value(m2['prob'].objective)):
        st.error('The sensitivity report does not match the solved model.')

ui.handoff('the preferred genre of each screen → **Model 3** hard constraint C7: '
           + ', '.join(f"{names[s]} → {g}" for s, g in m2['prefs'].items())
           + '; the full quota x[s,g] → **Model 4** goal G6.', 'views/studio_m3.py', 'Model 3 · Assignment')
