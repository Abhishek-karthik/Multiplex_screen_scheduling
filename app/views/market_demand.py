import pandas as pd
import plotly.express as px
import streamlit as st

import engine as E
from app import charts, state, ui

cfg = state.cfg()
ui.header('Market & demand', caption='How static TMDB metadata becomes a weekly market and audience demand per show.')
ds = ui.need_data()

b = state.base()
films, dem, market = b['films'], b['dem'], b['market']


@st.cache_data(show_spinner='Counting candidate films per week…')
def _pool_sizes(key, _clean, window, cleanup, slot_length):
    weeks = pd.date_range('2005-01-05', '2016-08-17', freq='2W-WED')
    return E.pool_size_by_week(_clean, {'window_weeks': window, 'cleanup': cleanup, 'slot_length': slot_length}, weeks)


# ---------------------------------------------------------------- the week
st.subheader('1 · The weekly market')
counts = market['market_status'].value_counts()
ui.kpi_row([('Schedule week', cfg['schedule_week_start']), ('Candidate films', f'{len(films)}'),
            ('Schedulable (≤ 160 min)', f"{int(films['fits'].sum())}"),
            ('New this week', f"{counts.get('New this week', 0)}"), ('Decay λ', f"{cfg['lam']:g}")])
if films['fits'].sum() < 10:
    st.warning('This week has fewer than 10 schedulable films; Model 1 may not reach its film minimum. The chart below shows richer weeks.')
ps = _pool_sizes(ds['key'], ds['clean'], cfg['window_weeks'], cfg['cleanup'], cfg['slot_length'])
fig = px.line(ps, x='week', y=['pool', 'schedulable'], title=f"Candidate films per week ({cfg['window_weeks']}-week window)")
fig.add_vline(x=cfg['schedule_week_start'], line_dash='dash', line_color='red')
fig.update_layout(height=300, margin=dict(l=10, r=10, t=50, b=10))
st.plotly_chart(fig)

st.markdown(f'''For the week starting **{cfg['schedule_week_start']}**, every clean film gets `weeks_out` (weeks since release),
`weekly_decay = exp(−λ·weeks_out)` and `effective_demand = popularity_norm × weekly_decay`. The **candidate pool** is every film released
in the previous {cfg['window_weeks']} weeks: new releases *and* still-running films, as a real multiplex would consider.''')
show = ['title', 'release_date', 'market_status', 'weeks_out', 'popularity_norm', 'weekly_decay', 'effective_demand', 'runtime', 'fits',
        'primary_genre', 'genre_list', 'original_language']
st.dataframe(films[show].round({'weeks_out': 2, 'popularity_norm': 3, 'weekly_decay': 3, 'effective_demand': 3}), hide_index=True,
             column_config={'fits': st.column_config.CheckboxColumn('fits a slot'),
                            'release_date': st.column_config.DateColumn('release date')})

st.subheader('2 · Demand decays as a film ages')
st.plotly_chart(charts.decay_curve(films, cfg['lam'], f"Share of popularity left after each week (λ = {cfg['lam']:g}; change it in the sidebar)"))

# ---------------------------------------------------------------- demand model
st.subheader('3 · Demand per show, capped by screen size')
st.markdown(E.formulations.DEMAND)
labels = cfg['slot_labels']
D_df = pd.DataFrame(dem['D'], index=films['title'], columns=labels)
c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(charts.heatmap(D_df, 'Demand D[i, j] (persons who want to watch)', fmt='.0f', label='persons'))
with c2:
    s = st.selectbox('Occupancy on screen', range(len(cfg['capacities'])), format_func=lambda k: E.screen_names(cfg)[k])
    occ = pd.DataFrame(dem['occ'][:, :, s], index=films['title'], columns=labels)
    st.plotly_chart(charts.heatmap(occ * 100, f"Occupancy on a {cfg['capacities'][s]}-seat screen (%)", fmt='.0f',
                                   colorscale='YlGnBu', zmin=0, zmax=100, label='%'))

c1, c2 = st.columns([1, 2])
pick = c1.selectbox('Film', films.index, format_func=lambda i: films.at[i, 'title'])
with c2:
    st.plotly_chart(charts.capacity_bars(films.at[pick, 'title'], dem['D'][pick], cfg['capacities'], labels,
                                         f"{films.at[pick, 'title']}: demand by slot vs screen sizes (bars above a line = people turned away)"))

st.subheader('4 · Calculate one show, step by step')
c1, c2, c3 = st.columns(3)
i = c1.selectbox('Film ', films.index, format_func=lambda k: films.at[k, 'title'], key='ex_film')
j = c2.selectbox('Slot', range(len(labels)), index=cfg['prime_slots'][-1], format_func=lambda k: labels[k], key='ex_slot')
s2 = c3.selectbox('Screen', range(len(cfg['capacities'])), format_func=lambda k: E.screen_names(cfg)[k], key='ex_screen')
e = E.explain_cell(films, dem, cfg, i, j, s2)
st.markdown(f'''
| Step | Calculation | Value |
|---|---|---|
| Effective demand $e_i$ | popularity {e['popularity_norm']:.3f} × decay e^(−{cfg['lam']:g}·{e['weeks_out']:.2f}) = {e['popularity_norm']:.3f} × {e['weekly_decay']:.3f} | **{e['effective_demand']:.3f}** |
| Demand $D_{{ij}}$ (persons) | {e['demand_scale']} × {e['effective_demand']:.3f} × slot factor {e['slot_factor']} × {e['genre']} affinity at {e['slot']} {e['affinity']} | **{e['demand']:.1f}** |
| Seats sold | min(demand {e['demand']:.1f}, capacity {e['capacity']:.0f}) | **{e['attendance']:.1f}** |
| Occupancy | {e['attendance']:.1f} / {e['capacity']:.0f} | **{e['occupancy']:.1%}** |
| Revenue | price ₹{e['price']:.0f} × {e['attendance']:.1f} seats | **{E.rupees(e['revenue'])}** |
| Turned away (spill) | max(demand − capacity, 0) | **{e['spill']:.1f}** |
''')
st.caption('These are the numbers the optimisation models use: `rev[i, j, s]` is the revenue coefficient of Models 3 and 4, '
           'and the demand values drive Model 1\'s film value and Model 2\'s mismatch cost.')
