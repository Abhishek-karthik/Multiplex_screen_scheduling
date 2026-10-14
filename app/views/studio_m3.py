import pandas as pd
import streamlit as st

import engine as E
from app import charts, state, ui

cfg = state.cfg()
ui.header('Model 3 · Film–screen–slot assignment (binary ILP)',
          question='Which licensed film should play on which screen, in which slot, to maximise ticket revenue?')
ds = ui.need_data()
ui.formulation(E.formulations.M3)

st.subheader('Controls')
c1, c2, c3 = st.columns(3)
cfg['k_max'] = c1.slider('C4 · max showings per film per day', 1, 6, key=state.bind('w_kmax', int(cfg['k_max'])))
if st.session_state.get('w_mmin', 0) > len(cfg['capacities']):          # the theatre shrank in the sidebar
    st.session_state['w_mmin'] = len(cfg['capacities'])
cfg['m_min'] = c2.slider('C6 · min operating screens per slot', 1, len(cfg['capacities']),
                         key=state.bind('w_mmin', min(int(cfg['m_min']), len(cfg['capacities']))))
cfg['use_c7'] = c3.toggle('C7 · each screen shows its Model 2 preferred genre', key=state.bind('w_c7', bool(cfg['use_c7'])))
st.caption('C1 one film per cell · C2 no simulcast · C3 runtime + cleanup fits · C5 every licensed film is shown are always on.')

ui.solve_button('m3', 'Solve Model 3')
rec, fresh = ui.run_banner('m3')
if rec is None or not state.stage_ok(rec['result'], 'm3'):
    st.stop()
r = rec['result']
m3, rc, F, sched = r.m3, r.cfg, r.films, r.sched_m3

st.subheader('Solution')
ui.solver_panel(m3['prob'], m3['status'], m3['solve_s'], E.rupees(r.R_star), 'R* (₹ per day)', key='m3')
k = r.k_m3
ui.kpi_row([('Shows', f"{k['shows']} of {len(rc['capacities']) * len(rc['slot_labels'])}"), ('Seats sold', f"{k['seats_sold']:,.0f}"),
            ('Average occupancy', ui.pct(k['avg_occupancy'])), ('Prime-time occupancy', ui.pct(k['prime_occupancy'])),
            ('People turned away', f"{k['spill']:,.0f}")])
st.markdown('**Timetable (colour = genre)**')
st.dataframe(charts.grid_styler(sched, rc))
st.plotly_chart(charts.gantt(sched, rc, 'Model 3 (revenue-only optimum): daily Gantt chart (hover a show for its numbers)'))

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(charts.heatmap(E.schedule_grid(sched, rc, 'occupancy').astype(float) * 100, 'Occupancy by screen and slot (%)',
                                   fmt='.0f', colorscale='YlGnBu', zmin=0, zmax=100))
with c2:
    st.plotly_chart(charts.heatmap(E.schedule_grid(sched, rc, 'revenue').astype(float) / 1000, 'Revenue by screen and slot (₹ thousand)',
                                   fmt='.1f', colorscale='Blues'))

st.subheader('Insights')
t1, t2, t3 = st.tabs(['Constraint activity', 'Hard-constraint validation', 'Clock timetable'])
with t1:
    shows = sched['film'].value_counts().reindex(r.licensed, fill_value=0)
    st.dataframe(pd.DataFrame({'title': F.loc[r.licensed, 'title'], 'shows': shows.values,
                               f"C4 (≤ {rc['k_max']}) binding": shows.values == rc['k_max'], 'C5 (≥ 1) binding': shows.values == 1}), hide_index=True)
    per_slot = sched.groupby('time', sort=False).size()
    st.markdown(f"Screens operating per slot: {per_slot.to_dict()} (C6 requires ≥ {rc['m_min']}). A dark cell appears only when no licensed "
                'film can add revenue there without breaking another rule.')
with t2:
    v = E.validate_schedule(sched, F, rc, r.licensed, r.prefs, 'M3')
    st.dataframe(v, hide_index=True)
    if (v['result'] != 'FAIL').all():
        st.success('All hard constraints pass.')
    else:
        st.error('A hard constraint fails!')
with t3:
    st.dataframe(sched[['screen', 'capacity', 'time', 'start', 'title', 'genre', 'runtime', 'end_with_cleanup', 'demand', 'attendance',
                        'occupancy', 'revenue', 'spill', 'idle_min']].round({'demand': 0, 'attendance': 0, 'occupancy': 2, 'revenue': 0, 'spill': 0}),
                 hide_index=True)

ui.handoff(f"R* = {E.rupees(r.R_star)} becomes **Model 4**'s revenue target (G1); Model 3's occupancy, variety and idle time set the "
           'other targets one step higher, so the goals genuinely conflict.', 'views/studio_m4.py', 'Model 4 · Goal programming')
