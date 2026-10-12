"""Multiplex scheduling — OR decision-support app.   Run from the project root:  streamlit run app/streamlit_app.py"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import engine as E  # noqa: E402

from app import state, ui  # noqa: E402

st.set_page_config(page_title='Multiplex Scheduling · OR', page_icon='🎬', layout='wide')
state.init()
cfg = state.cfg()
ss = st.session_state


def _sync_tables():
    # Base tables for the theatre editors (rebuilt only on start-up and reset, so edits are kept).
    if 'screens_base' not in ss:
        ss.screens_base = pd.DataFrame({'seats': cfg['capacities']})          # row k = Screen k
        ss.slots_base = pd.DataFrame({'price (₹)': cfg['prices'], 'demand factor': cfg['slot_factor']}, index=cfg['slot_labels'])


def _reset():
    state.reset_scenario()
    for k in ['screens_base', 'slots_base']:
        ss.pop(k, None)


_sync_tables()

# ---------------------------------------------------------------- sidebar: the scenario
with st.sidebar:
    st.markdown('### 🎬 Scenario')
    ds = state.dataset()
    st.caption(f"Data: {ds['name']}" + (f" · {len(ds['clean']):,} clean films" if ds['clean'] is not None else ' · **not usable**'))

    week = st.date_input('Schedule week starts', key=state.bind('w_week', pd.Timestamp(cfg['schedule_week_start']).date()),
                         min_value=date(1990, 1, 1), max_value=date(2016, 12, 31),
                         help='Films released in the window before this date are the candidates (the dataset ends in Aug 2016).')
    cfg['schedule_week_start'] = str(week)
    cfg['window_weeks'] = st.slider('Candidate window (weeks)', 2, 16, key=state.bind('w_window', cfg['window_weeks']))
    cfg['lam'] = st.slider('Demand decay λ (per week)', 0.05, 1.50, step=0.05, key=state.bind('w_lam', float(cfg['lam'])),
                           help='weekly_decay = exp(−λ · weeks since release). 0.55 ≈ 42% drop per week.')
    cfg['demand_scale'] = st.number_input('Demand scale (persons per unit of effective demand)', 100, 3000, step=50,
                                          key=state.bind('w_scale', int(cfg['demand_scale'])),
                                          help='Calibrated to 650 (average occupancy 35–45%); see the notebook, Section 8.2.')

    with st.expander('Theatre: screens and slots'):
        screens = st.data_editor(ss.screens_base, num_rows='dynamic', key='w_screens',
                                 column_config={'seats': st.column_config.NumberColumn('seats', min_value=20, max_value=600, step=10)})
        caps = [int(v) for v in screens['seats'].dropna().tolist()]
        if caps:
            cfg['capacities'] = caps
        slots = st.data_editor(ss.slots_base, key='w_slots', num_rows='fixed',
                               column_config={'price (₹)': st.column_config.NumberColumn(min_value=0, max_value=2000, step=10),
                                              'demand factor': st.column_config.NumberColumn(min_value=0.0, max_value=2.0, step=0.05)})
        cfg['prices'] = [float(v) for v in slots['price (₹)'].tolist()]
        cfg['slot_factor'] = [float(v) for v in slots['demand factor'].tolist()]
        st.caption('Six fixed 180-minute slots (the genre-slot affinity table is defined for these six). Prime time: 6 pm and 9 pm.')

    problems = E.validate_config(cfg)
    for p in problems:
        st.error(p)

    c1, c2 = st.columns(2)
    if c1.button('▶ Run full chain', type='primary', disabled=bool(problems) or ds['clean'] is None,
                 help='Solves Models 1 → 4, the baselines and the validator for this scenario.'):
        with st.spinner('Solving Models 1–4…'):
            state.run('m4')
    c2.button('↺ Reset', on_click=_reset, help='Back to the main scenario of the report.')
    st.divider()
    ui.chain_status_sidebar()

# ---------------------------------------------------------------- pages
pages = {
    'Project': [st.Page('views/overview.py', title='Overview', icon='🏠', default=True)],
    'Data': [st.Page('views/data.py', title='Data & statistics', icon='📂'),
             st.Page('views/market_demand.py', title='Market & demand', icon='📈')],
    'Optimisation studio': [st.Page('views/studio_m1.py', title='Model 1 · Knapsack', icon='1️⃣'),
                            st.Page('views/studio_m2.py', title='Model 2 · Transportation', icon='2️⃣'),
                            st.Page('views/studio_m3.py', title='Model 3 · Assignment', icon='3️⃣'),
                            st.Page('views/studio_m4.py', title='Model 4 · Goal programming', icon='4️⃣'),
                            st.Page('views/whatif.py', title='What-if: choose your films', icon='🧪')],
    'Results': [st.Page('views/compare.py', title='Compare & validate', icon='⚖️'),
                st.Page('views/sensitivity.py', title='Sensitivity lab', icon='🎛️'),
                st.Page('views/final_plan.py', title='Final plan & export', icon='📋')],
    'Code': [st.Page('views/under_the_hood.py', title='Under the hood', icon='🔧')],
}
st.navigation(pages).run()
