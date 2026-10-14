import pandas as pd
import streamlit as st

import engine as E
from app import charts, state, ui

cfg = state.cfg()
ui.header('Compare & validate',
          question='Are the schedules feasible, and is the optimised plan better than a naive or a greedy manager?')
ds = ui.need_data()
st.markdown('''Four schedules, measured with **the same demand model, the same KPIs and the same hard-constraint validator**:

| Schedule | Definition |
|---|---|
| **B1 Naive popularity** | the most popular films by raw TMDB popularity (ignores decay, budget and variety), rotated round-robin |
| **B2 Greedy manager** | Model 1's films; fill cells in revenue order while respecting the rules, then repair them |
| **M3 Revenue optimum** | Model 3 (assignment ILP) |
| **M4 Goal programming** | Model 4: the final, balanced plan |''')
ui.solve_button('m4', 'Run the full chain and baselines')
rec, fresh = ui.run_banner('m4')
if rec is None or not state.stage_ok(rec['result'], 'm4'):
    st.stop()
r = rec['result']
rc, F = r.cfg, r.films
schedules = {'B1 Naive popularity': (r.sched_b1, r.b1_films, None, r.kb1), 'B2 Greedy manager': (r.sched_b2, r.licensed, None, r.kb2),
             'M3 Revenue optimum': (r.sched_m3, r.licensed, r.prefs, r.k_m3), 'M4 Goal programming': (r.sched_m4, r.licensed, r.prefs, r.k_m4)}

st.subheader('Hard-constraint validation')
val = r.validation.replace({'B1': 'B1 Naive popularity', 'B2': 'B2 Greedy manager', 'M3': 'M3 Revenue optimum', 'M4': 'M4 Goal programming'})
mat = val.pivot(index='check', columns='schedule', values='result')[list(schedules)]
st.dataframe(mat.style.map(lambda v: {'PASS': 'background-color:#d3f9d8', 'FAIL': 'background-color:#ffc9c9'}.get(v, 'color:#868e96')))
st.caption('Checks 1–5 are physical rules every schedule must obey. Checks 6–9 compare a schedule with the plan (licensed films, '
           'Model 2 preferred genres, budget); they are n/a where a baseline does not use that part of the plan.')
if r.all_valid:
    st.success('Every physical rule holds for all four schedules, and every plan rule holds for Models 3 and 4.')

st.subheader('KPIs')
fmt = {'revenue': E.rupees, 'seats_sold': '{:,.0f}'.format, 'avg_occupancy': '{:.1%}'.format, 'seat_weighted_occupancy': '{:.1%}'.format,
       'prime_occupancy': '{:.1%}'.format, 'spill': '{:,.0f}'.format, 'avg_idle_min': '{:.1f}'.format, 'utilisation': '{:.1%}'.format,
       'licensing_cost': E.rupees, 'weekly_gross_to_fee': '{:.2f}'.format, 'quota_deviation': '{:.0f}'.format}
kp = pd.DataFrame({n: k for n, (_, _, _, k) in schedules.items()})
shown = kp.copy().astype(object)
for idx in shown.index:
    shown.loc[idx] = [fmt.get(idx, '{:.0f}'.format)(v) if pd.notnull(v) else 'n/a' for v in kp.loc[idx]]
st.dataframe(shown)
rev = kp.loc['revenue']
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(charts.bars(rev, 'Daily revenue', '₹ per day', colours=['grey', 'tan', 'steelblue', 'seagreen'], fmt='₹{:,.0f}'))
with c2:
    st.plotly_chart(charts.bars(kp.loc['prime_occupancy'] * 100, 'Prime-time occupancy', '%', colours=['grey', 'tan', 'steelblue', 'seagreen'], fmt='{:.1f}%'))

st.subheader('Where does the improvement come from?')
bridge = E.revenue_bridge(r)
st.plotly_chart(charts.waterfall(bridge, 'Revenue bridge from the naive baseline to the final schedule'))
lift_b1 = rev['M4 Goal programming'] / rev['B1 Naive popularity'] - 1
gap_b2 = rev['M3 Revenue optimum'] / rev['B2 Greedy manager'] - 1
pob = 1 - rev['M4 Goal programming'] / rev['M3 Revenue optimum']
b1_fee = F.loc[r.b1_films, 'fee'].sum()
st.markdown(f'''* The final plan earns **{E.signed_pct(lift_b1)}** against the naive schedule: {E.rupees(bridge['change'].iloc[2])} from *which films*
  are licensed (Model 1) and {E.rupees(bridge['change'].iloc[1])} from *where they are placed*.
  {'The naive plan would also be within the budget.' if b1_fee <= rc['budget'] else f'Note: the naive plan would cost {E.rupees(b1_fee)}, over the budget.'}
* **Honest benchmark:** a greedy manager with Model 1's films gets within **{gap_b2:.2%}** of the revenue optimum. Pure revenue is easy to
  approach heuristically; the exact models matter for the rules (budget, variety policy, preferred genres) and for pricing the balance.
* **Price of balance:** Model 4 gives up **{pob:.2%}** of R\\* for the goals in the goal report.''')

st.subheader('Side by side')
c1, c2 = st.columns(2)
a = c1.selectbox('Left', list(schedules), index=1)
bsel = c2.selectbox('Right', list(schedules), index=3)
c1.dataframe(charts.grid_styler(schedules[a][0], rc))
c2.dataframe(charts.grid_styler(schedules[bsel][0], rc))
