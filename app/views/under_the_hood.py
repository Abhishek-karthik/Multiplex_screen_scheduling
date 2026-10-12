import inspect
import platform

import numpy as np
import pandas as pd
import plotly
import pulp
import scipy
import streamlit as st

import engine as E
from app import state, ui

ui.header('Under the hood', caption='The real models behind every page: their size, the exact files sent to the solver, and the code.')
ds = ui.need_data()

st.subheader('Models solved in this session')
rows, probs = [], {}
for stage in state.STAGES:
    rec, fresh = state.latest(stage)
    if rec is None or not state.stage_ok(rec['result'], stage):
        continue
    r = rec['result']
    m = {'m1': r.m1, 'm2': r.m2, 'm3': r.m3, 'm4': r.m4}[stage]
    if m is None:
        continue
    size = ui.model_size(m['prob'])
    probs[state.STAGE_LABELS[stage]] = m['prob']
    rows.append({'model': state.STAGE_LABELS[stage], 'status': m['status'], 'current': 'yes' if fresh else 'stale',
                 'solve time (s)': round(m['solve_s'], 3), **size})
if rows:
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    pick = st.selectbox('Show the LP file of', list(probs))
    text = ui.lp_text(probs[pick])
    st.download_button('Download this .lp file', text, f'{probs[pick].name}.lp', 'text/plain')
    st.code(text[:20000] + ('\n…' if len(text) > 20000 else ''), language=None)
else:
    st.info('No model solved yet: use **Run full chain** in the sidebar.')

st.subheader('Source code')
modules = {'models (M1–M4)': E.models, 'pipeline (chain, sweeps)': E.pipeline, 'demand model': E.demand, 'weekly market': E.market,
           'metrics and validator': E.metrics, 'baselines': E.baselines, 'sensitivity report': E.analysis, 'AHP': E.ahp,
           'data cleaning': E.data, 'configuration': E.config}
c1, c2 = st.columns(2)
mod_name = c1.selectbox('Module', list(modules))
mod = modules[mod_name]
funcs = [n for n, f in inspect.getmembers(mod, inspect.isfunction) if f.__module__ == mod.__name__]
fn = c2.selectbox('Function', funcs, index=0)
st.caption(f'`{mod.__name__}` · {inspect.getsourcefile(mod).split("Multiplex_screen_scheduling")[-1]}')
st.code(inspect.getsource(getattr(mod, fn)), language='python')

st.subheader('Chain verification (live)')
rec, fresh = state.latest('m4')
if rec is not None and fresh and state.stage_ok(rec['result'], 'm4'):
    r = rec['result']
    v = r.validation
    chain = pd.DataFrame([
        ('Demand model → M1, M2, M3/M4', bool(np.isclose(r.sched_m3['revenue'].sum(), r.R_star))),
        ('M1 licensed films → M2 quotas and M3/M4 variables', bool(r.m2['quotas']['films'].sum() == len(r.licensed)
                                                              and r.m3['n_vars'] == len(r.licensed) * len(r.cfg['capacities']) * len(r.cfg['slot_labels']))),
        ('M2 preferred genres → M3/M4 constraint C7', bool(r.prefs is None or (v.loc[v['schedule'].isin(['M3', 'M4']) & v['check'].str.startswith('8'), 'result'] == 'PASS').all())),
        ('M2 quota x[s,g] → M4 goal G6', bool(r.k_m4['quota_deviation'] <= r.k_m3['quota_deviation'])),
        ('M3 R* → M4 target G1', bool(np.isclose(r.targets['G1'], r.R_star))),
        ('Weights → M4 objective', bool(all(np.isclose(r.weights[g], r.cfg['gp_weights'][g]) for g in E.GOALS))),
        ('M4 final schedule passes every hard constraint', bool((v.loc[v['schedule'] == 'M4', 'result'] != 'FAIL').all())),
    ], columns=['hand-off', 'verified'])
    st.dataframe(chain, hide_index=True)
else:
    st.info('Solve the full chain to verify the hand-offs.')

st.subheader('Environment and reproducibility')
st.dataframe(pd.DataFrame({'package': ['engine', 'python', 'pulp', 'CBC solver', 'scipy (HiGHS)', 'pandas', 'numpy', 'streamlit', 'plotly'],
                           'version': [E.__version__, platform.python_version(), pulp.__version__,
                                       'available' if pulp.PULP_CBC_CMD().available() else 'NOT available', scipy.__version__,
                                       pd.__version__, np.__version__, st.__version__, plotly.__version__]}), hide_index=True)
st.markdown('''The app and the notebook import the same `engine/` package. With the default scenario, the app reproduces the
notebook's numbers exactly; `tests/test_engine.py` checks this and also verifies the sensitivity ranges by brute force:''')
st.code('python -m pytest -q', language='bash')
