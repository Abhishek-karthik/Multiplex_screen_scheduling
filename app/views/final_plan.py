import json

import pandas as pd
import streamlit as st

import engine as E
from app import charts, state, ui

cfg = state.cfg()
ui.header('Final plan & export', caption='The operating plan for the multiplex manager: Model 4\'s balanced schedule.')
ds = ui.need_data()
ui.solve_button('m4', 'Solve the full chain')
rec, fresh = ui.run_banner('m4')
if rec is None or not state.stage_ok(rec['result'], 'm4'):
    st.stop()
r = rec['result']
rc, F, s4, k = r.cfg, r.films, r.sched_m4, r.k_m4
names = E.screen_names(rc)
week = pd.Timestamp(rc['schedule_week_start'])
st.subheader(f"Week of {week.strftime('%d %b %Y')}")

ui.kpi_row([('Daily ticket revenue', E.rupees(k['revenue'])), ('Seats sold', f"{k['seats_sold']:,.0f}"),
            ('Average / prime occupancy', f"{k['avg_occupancy']:.1%} / {k['prime_occupancy']:.1%}"),
            ('Licensing spend', f"{E.rupees(k['licensing_cost'])} of {E.rupees(rc['budget'])}"),
            ('Price of balance', f"{(r.R_star - k['revenue']) / r.R_star:.2%}")])

st.markdown('**1 · Films to license**')
lic = F.loc[r.licensed, ['title', 'primary_genre', 'runtime', 'market_status', 'weeks_out', 'fee']].copy()
lic['shows per day'] = s4['film'].value_counts().reindex(r.licensed, fill_value=0).values
lic['daily revenue'] = s4.groupby('film')['revenue'].sum().reindex(r.licensed, fill_value=0).values
st.dataframe(lic.round({'weeks_out': 1, 'daily revenue': 0}), hide_index=True)

st.markdown('**2 · Screen × slot plan**')
st.dataframe(charts.grid_styler(s4, rc))
st.plotly_chart(charts.gantt(s4, rc, 'Daily Gantt chart'))

st.markdown('**3 · Clock timetable**')
tt = s4.assign(screen=s4['screen'].map(lambda s: names[s]))[['screen', 'start', 'title', 'genre', 'runtime', 'end_with_cleanup',
                                                             'price', 'attendance', 'occupancy', 'revenue']]
st.dataframe(tt.round({'attendance': 0, 'occupancy': 2, 'revenue': 0}), hide_index=True)

c1, c2 = st.columns(2)
with c1:
    st.markdown('**4 · Idle minutes per screen**')
    idle = s4.groupby('screen').apply(lambda d: len(rc['slot_labels']) * rc['slot_length'] - (d['runtime'] + rc['cleanup']).sum())
    st.dataframe(idle.rename('idle minutes per day').set_axis([names[s] for s in idle.index]).to_frame())
with c2:
    st.markdown('**5 · Goal attainment**')
    rep = E.goal_report(s4, F, r.targets, r.weights, r.quota, rc)
    st.dataframe(pd.DataFrame({'goal': rep['goal'], 'measure': rep['measure'],
                               'target': [E.fmt_goal_value(g, v) for g, v in zip(rep['goal'], rep['target'])],
                               'achieved': [E.fmt_goal_value(g, v) for g, v in zip(rep['goal'], rep['achieved'])],
                               'met': rep['met'].map({True: '✔', False: '✘'})}), hide_index=True)

st.subheader('Export')
c1, c2, c3, c4 = st.columns(4)
c1.download_button('Timetable (CSV)', tt.to_csv(index=False).encode(), 'final_schedule.csv', 'text/csv')
c2.download_button('Screen × slot grid (CSV)', E.schedule_grid(s4, rc).to_csv().encode(), 'final_grid.csv', 'text/csv')
c3.download_button('Licensed films (CSV)', lic.to_csv(index=False).encode(), 'licensed_films.csv', 'text/csv')
c4.download_button('Scenario settings (JSON)', json.dumps(rc, indent=2, default=str).encode(), 'scenario.json', 'application/json',
                   help='Every assumption behind this plan, so it can be reproduced in the notebook with run_chain(clean, cfg).')
