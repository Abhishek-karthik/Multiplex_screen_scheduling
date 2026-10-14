import pandas as pd
import streamlit as st

import engine as E
from app import state, ui

cfg = state.cfg()
ui.header('Multiplex screen scheduling — an OR decision-support tool',
          caption='Operations Research · Group 14 · TMDB 5000 movie data + a declared synthetic theatre')

st.markdown('''
A multiplex has a few screens, six fixed show times a day, a weekly licensing budget, and audience demand that changes
by film, by time of day and by how many weeks a film has been running. Every week the manager must decide **which films
to license**, **how much screen capacity each genre gets**, **which film plays where and when**, and **how to balance
revenue against occupancy, prime-time variety and the capacity plan**. These decisions are connected, so the tool solves
them as a **chain of four OR models**, each feeding the next.

> **Project question:** *can a chain of OR models produce a feasible one-day schedule that is better than a simple
> popularity-based schedule, and what does each trade-off cost?*
''')

dot = '''digraph G {
  rankdir=LR; node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fillcolor="#eef2ff", color="#4c6ef5"];
  data [label="TMDB data\\n+ weekly market\\n+ demand model", fillcolor="#f1f3f5", color="#868e96"];
  m1 [label="Model 1\\n0/1 Knapsack (ILP)\\nwhich films to license?"];
  m2 [label="Model 2\\nTransportation (LP)\\nwhich screens for which genre?"];
  m3 [label="Model 3\\nAssignment (binary ILP)\\nrevenue-optimal timetable"];
  ahp [label="AHP\\npairwise judgments\\n→ goal weights", fillcolor="#fff4e6", color="#f08c00"];
  m4 [label="Model 4\\nGoal programming (MILP)\\nbalanced final schedule"];
  ev [label="Validation · baselines\\nsensitivity · robustness", fillcolor="#ebfbee", color="#2f9e44"];
  data -> m1 [label="demand, fees"]; m1 -> m2 [label="licensed films"]; m2 -> m3 [label="preferred genre / screen"];
  m2 -> m4 [label="quota x[s,g]"]; m3 -> m4 [label="R*, targets"]; ahp -> m4 [label="weights"]; m4 -> ev [label="final plan"];
}'''
st.graphviz_chart(dot)

st.subheader('The four decisions')
st.dataframe(pd.DataFrame([
    ('1', 'Which films to license this week?', '0/1 knapsack (binary ILP)', 'budget, 8–12 films, content mix, runtime fit', 'licensed films'),
    ('2', 'How many shows of each genre on each screen?', 'Transportation LP (+ duals, sensitivity report)', 'supply = 6 shows per screen, demand = genre quotas', 'quota x[s,g], preferred genre per screen'),
    ('3', 'Which film plays on which screen and slot?', 'Assignment-type binary ILP', 'one film per cell, runtime + cleanup, no simulcast, ≤ 5 shows, ≥ 4 screens, preferred genre', 'revenue-optimal schedule, R*'),
    ('4', 'How to balance revenue with the other goals?', 'Weighted goal programming (MILP) with AHP weights', 'same hard rules + 6 goals', 'final schedule, goal report, price of balance'),
], columns=['#', 'Decision', 'OR technique', 'Main constraints', 'Output']), hide_index=True)

st.subheader('The theatre at a glance')
c1, c2 = st.columns([2, 3])
with c1:
    st.dataframe(pd.DataFrame({'screen': E.screen_names(cfg), 'seats': cfg['capacities']}), hide_index=True)
with c2:
    st.dataframe(pd.DataFrame({'slot': cfg['slot_labels'],
                               'starts': [E.minutes_to_clock(m) for m in cfg['slot_start_min']],
                               'ticket price (₹)': cfg['prices'], 'demand factor': cfg['slot_factor'],
                               'prime time': ['yes' if j in cfg['prime_slots'] else '' for j in range(len(cfg['slot_labels']))]}),
                 hide_index=True)
st.caption(f"Each slot is {cfg['slot_length']} minutes with a {cfg['cleanup']}-minute cleanup, so a film must be ≤ "
           f"{cfg['slot_length'] - cfg['cleanup']} minutes. Change screens, prices and demand in the sidebar.")

st.subheader('How to use this app')
st.markdown('''
1. **Data & statistics:** load the bundled TMDB file or upload your own, see the cleaning steps, and generate statistics on demand.
2. **Market & demand:** pick a week and see how popularity and film age become audience demand.
3. **Optimisation studio:** solve any of the four models (each page shows the formulation, the input data, the exact
   model sent to the solver, the solution and its sensitivity information). Or try **What-if** with your own film choice.
4. **Results:** compare against the baselines with a hard-constraint check, run sensitivity experiments, and export the final plan.
5. **Under the hood:** the model files, solver statistics and the source code of every model.
''')
st.info('Every number in this app is computed live by the same `engine/` package that the report notebook uses; '
        '`tests/test_engine.py` checks that both give identical results. Revenue and occupancy are model estimates built on '
        'declared assumptions (TMDB has no ticket sales), not observed data.')
