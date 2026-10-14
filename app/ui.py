"""Shared page components: the model-card template, solver panel, run status and formatting."""
import os
import tempfile
from collections import Counter

import pulp
import streamlit as st

import engine as E

from app import state

STATUS_ICON = {'ok': '✅', 'failed': '❌', 'stale': '⚠️', 'not run': '▫️'}


def header(title, question=None, caption=None):
    st.title(title)
    if question:
        st.markdown(f'**Question.** {question}')
    if caption:
        st.caption(caption)


def need_data():
    # Stop the page with a clear message if the dataset is not usable.
    ds = state.dataset()
    if ds['clean'] is None:
        st.error('The current dataset cannot be used: ' + '; '.join(ds['problems']))
        st.page_link('views/data.py', label='Go to the Data page to load a valid file', icon='📂')
        st.stop()
    problems = E.validate_config(state.cfg())
    if problems:
        st.error('The scenario settings are not valid: ' + '; '.join(problems))
        st.stop()
    return ds


def model_size(prob):
    kinds = Counter(v.cat for v in prob.variables())
    fam = Counter(name.split('_')[0] for name in prob.constraints)
    return {'variables': len(prob.variables()), 'binary/integer': kinds.get(pulp.LpInteger, 0),
            'continuous': kinds.get(pulp.LpContinuous, 0), 'constraints': len(prob.constraints),
            'constraint families': ', '.join(f'{k} ×{v}' for k, v in sorted(fam.items()))}


def lp_text(prob):
    # The exact model handed to the solver, in LP file format.
    fd, path = tempfile.mkstemp(suffix='.lp')
    os.close(fd)
    try:
        prob.writeLP(path)
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    finally:
        os.remove(path)


def solver_panel(prob, status, seconds, objective=None, objective_label='objective', key='lp'):
    size = model_size(prob)
    cols = st.columns(5)
    cols[0].metric('Solver status', status)
    cols[1].metric(objective_label, objective if objective is not None else '—')
    cols[2].metric('Variables', f"{size['variables']}", help=f"binary/integer {size['binary/integer']}, continuous {size['continuous']}")
    cols[3].metric('Constraints', f"{size['constraints']}")
    cols[4].metric('Solve time', f'{seconds:.2f} s')
    with st.expander('The exact model sent to the CBC solver (LP file)'):
        st.caption('Constraint families: ' + size['constraint families'])
        text = lp_text(prob)
        st.download_button('Download .lp file', text, file_name=f'{prob.name}.lp', mime='text/plain', key=f'dl_{key}')
        st.code(text[:6000] + ('\n… (truncated; download for the full model)' if len(text) > 6000 else ''), language=None)


def run_banner(stage):
    # Show whether the stored result for `stage` matches the current inputs. Returns (record, fresh).
    rec, fresh = state.latest(stage)
    if rec is None:
        st.info('Not solved yet for this scenario. Use the solve button.')
    elif not fresh:
        st.warning(f"The inputs changed since this result was computed (at {rec['when']}). The numbers below are **stale**; solve again.")
    elif not state.stage_ok(rec['result'], stage):
        st.error(f"This scenario could not be solved: {rec['result'].status}.")
    return rec, fresh


def solve_button(stage, label):
    upstream = ', '.join(state.STAGE_LABELS[s].split(' · ')[0] for s in state.STAGES[:state.STAGES.index(stage)])
    help_ = f'Solves {upstream} first, because this model uses their outputs.' if upstream else None
    if st.button(label, type='primary', key=f'solve_{stage}', help=help_):
        with st.spinner('Solving…'):
            state.run(stage)
        st.rerun()


def formulation(md, expanded=False):
    with st.expander('Formulation', expanded=expanded):
        st.markdown(md)


def handoff(text, page=None, label=None):
    st.markdown('---')
    st.markdown(f'**Hand-off →** {text}')
    if page:
        st.page_link(page, label=label or 'Next model', icon='➡️')


def chain_status_sidebar():
    st.sidebar.markdown('**Chain status**')
    for s in state.STAGES:
        stt = state.stage_status(s)
        st.sidebar.markdown(f'{STATUS_ICON[stt]} {state.STAGE_LABELS[s]} — *{stt}*')


def kpi_row(items):
    cols = st.columns(len(items))
    for col, (label, value, *help_) in zip(cols, items):
        col.metric(label, value, help=help_[0] if help_ else None)


def pct(x, d=1):
    return f'{x:.{d}%}'
