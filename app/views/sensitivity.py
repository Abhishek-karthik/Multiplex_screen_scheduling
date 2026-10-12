from copy import deepcopy

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as E
from app import charts, state, ui

ss = st.session_state
cfg = state.cfg()
ui.header('Sensitivity lab',
          question='Do the conclusions survive when the assumptions change? Every point re-solves the whole chain '
                   '(market → demand → Models 1–4 → baselines → validation).')
ds = ui.need_data()

EXPERIMENTS = {
    'S1 · Demand decay λ': ('lam', [0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85], 'How fast does demand fade? Changes which films are worth licensing.'),
    'S2 · Licensing budget': ('budget', [round(cfg['budget'] * m, -4) for m in (0.625, 0.75, 0.875, 1.0, 1.125, 1.25, 1.375)],
                              'Where does extra budget stop paying off?'),
    'S3 · Demand scale': ('demand_scale', [round(cfg['demand_scale'] * m) for m in (0.7, 0.85, 1.0, 1.15, 1.3)],
                          'Does the result survive the biggest synthetic assumption?'),
    'S5 · Schedule weeks': ('schedule_week_start', None, 'Is the main week a lucky pick? Weeks are chosen by a fixed rule, not by hand.'),
    'S6 · Variety policy (minimum films)': ('n_min', [4, 5, 6, 7, 8, 9, 10], 'What does the "license at least 8 films" policy cost?'),
}
exp = st.selectbox('Experiment', list(EXPERIMENTS))
param, defaults, why = EXPERIMENTS[exp]
st.caption(why + ' (The Model 4 revenue-weight trade-off curve, S4, is on the Model 4 page.)')

if param == 'schedule_week_start':
    n_weeks = st.slider('Number of weeks', 4, 12, 10)
    grid = pd.date_range('2010-01-06', '2016-06-29', freq='4W-WED')
    sizes = E.pool_size_by_week(ds['clean'], cfg, grid)
    eligible = sizes.loc[sizes['pool'] >= 15, 'week'].tolist()
    values = [str(eligible[k].date()) for k in np.linspace(0, len(eligible) - 1, n_weeks).round().astype(int)]
    st.caption(f'Rule: every 4th Wednesday from Jan 2010 to Jun 2016 with ≥ 15 candidate films ({len(eligible)} weeks); '
               f'{n_weeks} evenly spaced: ' + ', '.join(values))
else:
    shown = ', '.join(f'{v:g}' if param == 'lam' else f'{v:.0f}' for v in defaults)
    txt = st.text_input('Values to test (comma-separated)', shown, key=f'w_sens_{param}')
    try:
        values = [int(float(v)) if param in ('n_min', 'budget', 'demand_scale') else float(v) for v in txt.split(',') if v.strip()]
    except ValueError:
        st.error('Could not read the values.')
        st.stop()

skey = (state.scenario_hash(), param, tuple(values))
if st.button(f'Run {len(values)} end-to-end solves', type='primary'):
    bar = st.progress(0.0, text='Solving…')
    rows = []
    base = deepcopy(cfg)
    for k, v in enumerate(values):
        row = E.run_pipeline({param: v}, clean=ds['clean'], base=base)
        row[param] = v
        rows.append(row)
        bar.progress((k + 1) / len(values), text=f'{k + 1} of {len(values)} solved')
    ss.sweeps[skey] = pd.DataFrame(rows)
if skey not in ss.sweeps:
    st.stop()

df = ss.sweeps[skey]
ok = df[df['status'] == 'ok'].copy()
failed = df[df['status'] != 'ok']
if len(failed):
    st.warning(f'{len(failed)} setting(s) could not be solved: ' + '; '.join(f'{v} → {s}' for v, s in zip(failed[param], failed['status'])))
if ok.empty:
    st.stop()

fig = go.Figure()
for col, name, colour in [('R_B1', 'B1 naive', 'grey'), ('R_B2', 'B2 greedy', 'tan'), ('R_M3', 'M3 revenue optimum', 'steelblue'),
                          ('R_M4', 'M4 final', 'seagreen')]:
    fig.add_trace(go.Scatter(x=ok[param].astype(str) if param == 'schedule_week_start' else ok[param], y=ok[col], mode='lines+markers',
                             name=name, line=dict(color=colour)))
if param != 'schedule_week_start' and cfg[param] in list(ok[param]):
    fig.add_vline(x=cfg[param], line_dash='dash', line_color='red')
fig.update_layout(title=f'{exp}: daily revenue of each method', xaxis_title=param, yaxis_title='₹ per day', height=400,
                  margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(fig)

cols = [param, 'status', 'films_licensed', 'fee_used', 'R_B1', 'B1_within_budget', 'R_B2', 'R_M3', 'R_M4', 'lift_M4_vs_B1',
        'lift_M3_vs_B2', 'price_of_balance', 'avg_occ_M4', 'weekly_gross_to_fee', 'all_valid', 'licensed_titles', 'seconds']
st.dataframe(df[[c for c in cols if c in df.columns]].style.format(
    {'fee_used': '₹{:,.0f}', 'R_B1': '₹{:,.0f}', 'R_B2': '₹{:,.0f}', 'R_M3': '₹{:,.0f}', 'R_M4': '₹{:,.0f}', 'lift_M4_vs_B1': '{:+.1%}',
     'lift_M3_vs_B2': '{:+.2%}', 'price_of_balance': '{:.2%}', 'avg_occ_M4': '{:.1%}', 'weekly_gross_to_fee': '{:.2f}', 'seconds': '{:.2f}'},
    na_rep='—'), hide_index=True)
st.download_button('Download results (CSV)', df.to_csv(index=False).encode(), f'sensitivity_{param}.csv', 'text/csv')

fair = ok[ok['B1_within_budget'].astype(bool)]
lines = [f"**{len(ok)} of {len(df)}** settings solve end to end; every schedule passes validation: **{bool(ok['all_valid'].all())}**.",
         f"The final plan beats the naive schedule in **{int((ok['lift_M4_vs_B1'] > 0).sum())} of {len(ok)}** settings "
         f"({int((fair['lift_M4_vs_B1'] > 0).sum())} of {len(fair)} where the naive plan is affordable).",
         f"The assignment ILP beats the greedy manager on revenue by at most {ok['lift_M3_vs_B2'].max():.2%}; "
         f"the price of balance ranges {ok['price_of_balance'].min():.2%} … {ok['price_of_balance'].max():.2%}."]
if param == 'n_min':
    best = ok['R_M3'].max()
    free = int(ok.loc[ok['R_M3'] >= best - 1e-6, 'n_min'].max())
    cur = ok.loc[ok['n_min'] == cfg['n_min'], 'R_M3']
    if len(cur):
        lines.append(f"**Price of the variety policy:** up to {free} films the rule is free; at least {cfg['n_min']} films costs "
                     f"**{E.rupees(best - cur.iloc[0])} per day** ({(best - cur.iloc[0]) / best:.1%} of the revenue available without it).")
if param == 'budget':
    ok = ok.sort_values('budget')
    jump = ok['R_M4'].diff()
    if jump.notna().any():
        lines.append(f"The largest gain from extra budget is {E.rupees(jump.max())}/day, at {E.rupees(ok.loc[jump.idxmax(), 'budget'])}; "
                     'after that, returns diminish (films are indivisible, and extra films compete for the same show-slots).')
st.markdown('\n'.join(f'* {l}' for l in lines))
