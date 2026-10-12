import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as E
from app import state, ui

cfg = state.cfg()
ui.header('Model 1 · Film selection (0/1 knapsack, binary ILP)',
          question='With a limited weekly licensing budget, which films should the multiplex license this week?')
ds = ui.need_data()
ui.formulation(E.formulations.M1)

# ---------------------------------------------------------------- controls
st.subheader('Controls')
c1, c2, c3 = st.columns(3)
cfg['budget'] = c1.number_input('Weekly licensing budget (₹)', 100_000, 20_000_000, step=50_000,
                                key=state.bind('w_budget', int(cfg['budget'])))
nmin, nmax = c2.slider('Variety policy: films to license (min, max)', 1, 20, key=state.bind('w_nrange', (cfg['n_min'], cfg['n_max'])))
cfg['n_min'], cfg['n_max'] = int(nmin), int(nmax)
with c3.expander('Licensing fee formula'):
    cfg['fee_floor'] = st.number_input('Fee floor (₹)', 0, 5_000_000, step=10_000, key=state.bind('w_feefloor', int(cfg['fee_floor'])))
    cfg['fee_premium'] = st.number_input('Fee premium per unit of effective demand (₹)', 0, 50_000_000, step=50_000,
                                         key=state.bind('w_feeprem', int(cfg['fee_premium'])))
    cfg['c_ref'] = st.number_input('Reference screen size for the film value (seats)', 20, 600, step=10,
                                   key=state.bind('w_cref', int(cfg['c_ref'])))

# ---------------------------------------------------------------- instance
b = state.base()
films = b['films']
with st.expander('Instance: the candidate films and their parameters', expanded=False):
    inst = films[['title', 'primary_genre', 'runtime', 'fits', 'effective_demand', 'value', 'fee', 'is_action', 'is_family', 'is_regional']].copy()
    inst['value / fee'] = inst['value'] / inst['fee']
    st.dataframe(inst.round({'effective_demand': 3, 'value / fee': 3}), hide_index=True,
                 column_config={'value': st.column_config.NumberColumn('value v_i (₹/day)', format='%.0f'),
                                'fee': st.column_config.NumberColumn('fee f_i (₹/week)', format='%.0f')})
    st.caption(f"{int(films['fits'].sum())} of {len(films)} films fit a slot. All schedulable films together cost "
               f"{E.rupees(films.loc[films['fits'], 'fee'].sum())} against a budget of {E.rupees(cfg['budget'])}.")

ui.solve_button('m1', 'Solve Model 1')
rec, fresh = ui.run_banner('m1')
if rec is None or not state.stage_ok(rec['result'], 'm1'):
    st.stop()
r = rec['result']
m1, F, rc = r.m1, r.films, r.cfg

# ---------------------------------------------------------------- solution
st.subheader('Solution')
ui.solver_panel(m1['prob'], m1['status'], m1['solve_s'], E.rupees(m1['objective']), 'value score', key='m1')
ui.kpi_row([('Films licensed', f"{len(r.licensed)}"), ('Licensing spend', E.rupees(m1['fee_used'])),
            ('Budget used', f"{m1['fee_used'] / rc['budget']:.1%}"), ('Weekly fee range', f"{E.rupees(F['fee'].min())}–{E.rupees(F['fee'].max())}")])
plot = F.assign(status=np.where(F.index.isin(r.licensed), 'licensed', np.where(F['fits'], 'not licensed', 'cannot fit a slot')))
fig = go.Figure()
for status, colour in [('licensed', 'seagreen'), ('not licensed', 'lightgrey'), ('cannot fit a slot', 'firebrick')]:
    d = plot[plot['status'] == status]
    fig.add_trace(go.Scatter(x=d['fee'], y=d['value'], mode='markers+text', name=status, text=d['title'].str[:18],
                             textposition='top center', marker=dict(size=12, color=colour), textfont=dict(size=9)))
fig.update_layout(title='Each film: weekly fee vs daily value (the knapsack trades value against budget)', height=420,
                  xaxis_title='licensing fee (₹ per week)', yaxis_title='value score (₹ per day)', margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(fig)
st.dataframe(F.loc[r.licensed, ['title', 'primary_genre', 'runtime', 'weeks_out', 'effective_demand', 'fee', 'value']].round(3), hide_index=True)

# ---------------------------------------------------------------- insights
st.subheader('Insights')
t1, t2, t3, t4 = st.tabs(['Binding constraints', 'Why an ILP? (greedy, LP relaxation)', 'Sensitivity report', 'Budget sweep'])
with t1:
    bt = E.binding_table(m1)
    st.dataframe(bt, hide_index=True)
    slack = bt.set_index('constraint').at['K1 budget', 'slack']
    left = F.drop(index=r.licensed).query('fits')['fee']
    st.markdown(f"Budget slack is {E.rupees(slack)}. "
                + (f"The cheapest film not licensed costs {E.rupees(left.min())}, so the budget is **effectively binding**." if len(left) and slack < left.min()
                   else 'The budget is not binding.')
                + (' The film-count minimum binds too: this is the **variety policy**, and the Sensitivity lab (S6) prices it.'
                   if bt.set_index('constraint').at['K2 min films', 'binding'] else ''))
with t2:
    g = E.greedy_knapsack(F, rc)
    lp = E.solve_knapsack(F, rc, relax=True)
    comp = pd.DataFrame([
        {'method': 'Greedy (value per rupee)', 'films': len(g['selected']), 'fee used': g['fee_used'], 'value score': g['value'], 'feasible': 'yes' if g['feasible'] else 'NO'},
        {'method': 'ILP (Model 1)', 'films': len(r.licensed), 'fee used': m1['fee_used'], 'value score': m1['objective'], 'feasible': 'yes'},
        {'method': 'LP relaxation (bound)', 'films': round(lp['n_selected'], 2), 'fee used': lp['fee_used'], 'value score': lp['objective'], 'feasible': 'fractional films'},
    ])
    st.dataframe(comp.round(2), hide_index=True)
    broken = [k for k, v in g['checks'].items() if not v]
    st.markdown(f"Greedy picks {', '.join(F.loc[g['selected'], 'title'])}. "
                + (f"It **breaks** {', '.join(broken)}: side constraints are why an exact ILP is needed." if broken else 'It happens to be feasible here.')
                + f" The LP relaxation is {(lp['objective'] - m1['objective']) / lp['objective']:.1%} above the ILP (the integrality gap), "
                "because it may license fractions of films.")
with t3:
    rep = E.lp_sensitivity_report(lp['prob'], lp['var_labels'], lp['con_labels'])
    st.caption('Read from the LP relaxation (an ILP has no shadow prices). Same format as a spreadsheet Solver report; '
               'ranges are exact (computed from the LP optimality conditions).')
    st.markdown('**Constraints**')
    st.dataframe(rep['constraints'].round(4), hide_index=True)
    st.markdown('**Variables (films)**')
    st.dataframe(rep['variables'].round(3), hide_index=True)
    con = rep['constraints'].set_index('constraint')
    k1, k2 = con.loc['K1 budget'], con.loc['K2 min films']
    st.markdown(f"* **Budget:** each extra rupee adds {k1['shadow price']:.3f} value units, valid for budgets between "
                f"{E.rupees(rc['budget'] - k1['allowable decrease'])} and {E.rupees(rc['budget'] + k1['allowable increase'])}.\n"
                f"* **Variety policy:** shadow price {k2['shadow price']:,.0f}, so each extra film the rule requires costs about "
                f"{E.rupees(abs(k2['shadow price']))} of daily value (local LP estimate).")
with t4:
    lo, hi = max(100_000, int(rc['budget'] * 0.5)), int(rc['budget'] * 1.5)
    budgets = np.linspace(lo, hi, 9).round(-4)
    rows = []
    for bud in budgets:
        res = E.solve_knapsack(F, E.cfg_with({'budget': bud}, base=rc))
        rows.append({'budget': bud, 'status': res['status'], 'films': len(res.get('selected', [])), 'value score': res.get('objective', np.nan)})
    sw = pd.DataFrame(rows)
    sw['marginal value'] = sw['value score'].diff()
    fig = go.Figure(go.Scatter(x=sw['budget'], y=sw['value score'], mode='lines+markers+text', text=sw['films'].astype(str) + ' films',
                               textposition='top center'))
    fig.add_vline(x=rc['budget'], line_dash='dash', line_color='red')
    fig.update_layout(title='Model 1 value score vs budget (Model 1 only; the end-to-end sweep is in the Sensitivity lab)',
                      xaxis_title='budget (₹/week)', yaxis_title='value score (₹/day)', height=380, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig)
    st.dataframe(sw, hide_index=True)

ui.handoff(f"{len(r.licensed)} licensed films → **Model 2** (genre quotas per screen) and the decision variables of Models 3 and 4.",
           'views/studio_m2.py', 'Model 2 · Transportation')
