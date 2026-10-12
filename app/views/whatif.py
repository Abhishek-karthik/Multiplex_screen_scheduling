from copy import deepcopy

import pandas as pd
import streamlit as st

import engine as E
from app import charts, state, ui

ss = st.session_state
cfg = state.cfg()
ui.header('What-if: choose your own films',
          question='Is a manager\'s own film choice better or worse than Model 1\'s? The same Models 2–4 schedule your films, '
                   'so the only difference is the licensing decision.')
ds = ui.need_data()
b = state.base()
films = b['films']
cand = films[films['fits']]

rec, fresh = state.latest('m1')
default = (rec['result'].licensed if rec is not None and fresh and state.stage_ok(rec['result'], 'm1')
           else cand.sort_values('effective_demand', ascending=False).index[:cfg['n_min']].tolist())
picks = st.multiselect('Films to license (only films that fit a 180-minute slot are listed)', cand.index.tolist(),
                       default=[i for i in default if i in cand.index], format_func=lambda i: films.at[i, 'title'])
fee = films.loc[picks, 'fee'].sum()
c1, c2, c3 = st.columns(3)
c1.metric('Licensing spend', E.rupees(fee), delta=f"{E.rupees(cfg['budget'] - fee)} left" if fee <= cfg['budget'] else 'over budget',
          delta_color='normal' if fee <= cfg['budget'] else 'inverse')
c2.metric('Films', f'{len(picks)}', help=f"Variety policy: {cfg['n_min']}–{cfg['n_max']} films")
c3.metric('Content', ', '.join(x for x, col in [('action-like', 'is_action'), ('family', 'is_family')] if films.loc[picks, col].any()) or 'none')
if fee > cfg['budget']:
    st.warning('This choice is over the licensing budget: Model 1 could not choose it. It is still scheduled, for comparison.')
if not cfg['n_min'] <= len(picks) <= cfg['n_max']:
    st.warning(f"This choice breaks the variety policy ({cfg['n_min']}–{cfg['n_max']} films).")

if st.button('Run Models 2–4 on my films and compare', type='primary', disabled=not picks):
    with st.spinner('Solving both chains…'):
        c = deepcopy(cfg)
        mine = E.run_chain(ds['clean'], c, licensed=picks)
        model = E.run_chain(ds['clean'], c)
    ss.whatif = {'key': state.scenario_hash(), 'picks': list(picks), 'mine': mine, 'model': model}

w = ss.whatif
if w is None:
    st.stop()
if w['key'] != state.scenario_hash() or w['picks'] != list(picks):
    st.warning('The scenario or the film choice changed since this comparison was computed; run it again.')
mine, model = w['mine'], w['model']
if not mine.ok or not model.ok:
    st.error(f'Could not solve: your films → {mine.status}; Model 1 films → {model.status}')
    st.stop()


def row(r, name):
    k = r.k_m4
    return {'plan': name, 'films': len(r.licensed), 'licensing spend': r.films.loc[r.licensed, 'fee'].sum(),
            'within budget': r.films.loc[r.licensed, 'fee'].sum() <= r.cfg['budget'],
            'R* (Model 3)': r.R_star, 'final revenue (Model 4)': k['revenue'], 'avg occupancy': k['avg_occupancy'],
            'prime-time occupancy': k['prime_occupancy'], 'genres': k['genres_covered'], 'turned away': k['spill'],
            'weekly gross / licensing': k['weekly_gross_to_fee'], 'all constraints pass': r.all_valid}


comp = pd.DataFrame([row(model, 'Model 1 films'), row(mine, 'Your films')]).set_index('plan')
st.dataframe(comp.style.format({'licensing spend': '₹{:,.0f}', 'R* (Model 3)': '₹{:,.0f}', 'final revenue (Model 4)': '₹{:,.0f}',
                                'avg occupancy': '{:.1%}', 'prime-time occupancy': '{:.1%}', 'turned away': '{:,.0f}',
                                'weekly gross / licensing': '{:.2f}'}))
gap = mine.k_m4['revenue'] - model.k_m4['revenue']
over = mine.films.loc[mine.licensed, 'fee'].sum() > cfg['budget']
breaks = not cfg['n_min'] <= len(mine.licensed) <= cfg['n_max']
note = (' Note that your choice breaks ' + ' and '.join(x for x, f in [('the budget', over), ('the variety policy', breaks)] if f)
        + ', so the comparison is not like for like.') if over or breaks else ''
st.markdown(f"Your films earn **{E.rupees(abs(gap))} per day {'more' if gap > 0 else 'less'}** than Model 1's choice in the final "
            f"schedule.{note}")
c1, c2 = st.columns(2)
with c1:
    st.markdown('**Model 1 films**')
    st.dataframe(charts.grid_styler(model.sched_m4, model.cfg))
with c2:
    st.markdown('**Your films**')
    st.dataframe(charts.grid_styler(mine.sched_m4, mine.cfg))
