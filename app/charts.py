"""Plotly figures for the app (the notebook draws the same views with matplotlib)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import engine as E

_PALETTE = px.colors.qualitative.Plotly + px.colors.qualitative.D3 + px.colors.qualitative.Set2
_GENRES = sorted(E.DEFAULT_CONFIG['genre_affinity']) + ['Unknown']
GENRE_COLOURS = {g: _PALETTE[k % len(_PALETTE)] for k, g in enumerate(_GENRES)}


def genre_colour(g):
    return GENRE_COLOURS.get(g, '#999999')


def _layout(fig, title=None, height=None):
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=50 if title else 20, b=10), height=height,
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0))
    return fig


def gantt(sched, cfg, title):
    # One bar per show (runtime) plus a grey cleanup block; colour = genre; hover = demand, attendance, revenue.
    names = E.screen_names(cfg)
    fig = go.Figure()
    for g in sorted(sched['genre'].unique()):
        d = sched[sched['genre'] == g]
        fig.add_trace(go.Bar(
            y=[names[s] for s in d['screen']], x=d['runtime'], base=d['start_min'], orientation='h', name=g,
            marker_color=genre_colour(g), text=d['title'], textposition='inside', insidetextanchor='middle',
            customdata=np.stack([d['title'], d['start'], d['end_with_cleanup'], d['demand'].round(0), d['attendance'].round(0),
                                 d['occupancy'] * 100, d['revenue'].round(0), d['spill'].round(0)], axis=-1),
            hovertemplate='<b>%{customdata[0]}</b><br>%{customdata[1]} → %{customdata[2]} (incl. cleanup)<br>'
                          'demand %{customdata[3]} · sold %{customdata[4]} · occupancy %{customdata[5]:.0f}%<br>'
                          'revenue ₹%{customdata[6]:,.0f} · turned away %{customdata[7]}<extra>%{y}</extra>'))
    fig.add_trace(go.Bar(y=[names[s] for s in sched['screen']], x=[cfg['cleanup']] * len(sched),
                         base=sched['start_min'] + sched['runtime'], orientation='h', name=f"cleanup ({cfg['cleanup']} min)",
                         marker_color='lightgrey', marker_pattern_shape='/', hoverinfo='skip'))
    ticks = list(cfg['slot_start_min']) + [cfg['slot_start_min'][-1] + cfg['slot_length']]
    fig.update_layout(barmode='overlay', bargap=0.3)
    fig.update_xaxes(tickvals=ticks, ticktext=[E.minutes_to_clock(t) for t in ticks], range=[ticks[0] - 10, ticks[-1] + 10],
                     showgrid=True, gridcolor='rgba(128,128,128,0.25)')
    fig.update_yaxes(categoryorder='array', categoryarray=names[::-1])
    return _layout(fig, title, height=120 + 55 * len(names))


def _text_colour(css):
    # black text on light backgrounds, white on dark ones (relative luminance of an '#rrggbb' or 'rgb(r,g,b)' colour)
    if css.startswith('#'):
        r, g, b = (int(css[k:k + 2], 16) for k in (1, 3, 5))
    else:
        r, g, b = (int(v) for v in css[css.index('(') + 1:css.index(')')].split(',')[:3])
    return 'black' if 0.299 * r + 0.587 * g + 0.114 * b > 150 else 'white'


def grid_styler(sched, cfg):
    # screens x slots grid of titles, each cell coloured by genre (pandas Styler for st.dataframe).
    titles = E.schedule_grid(sched, cfg, 'title')
    genres = E.schedule_grid(sched, cfg, 'genre')

    def colour(_):
        return genres.apply(lambda col: [f'background-color: {genre_colour(g)}; color: {_text_colour(genre_colour(g))}'
                                         if isinstance(g, str) else '' for g in col])
    return titles.style.apply(colour, axis=None)


def heatmap(df, title, fmt='.0f', colorscale='YlOrRd', zmin=None, zmax=None, height=None, label=''):
    fig = px.imshow(df.astype(float), text_auto=fmt, aspect='auto', color_continuous_scale=colorscale, zmin=zmin, zmax=zmax,
                    labels=dict(color=label))
    return _layout(fig, title, height=height or 120 + 32 * len(df))


def sankey(x, cfg, title):
    # Transportation flows: screens (sources) -> genres (destinations), width = shows per day.
    names = E.screen_names(cfg)
    genres = list(x.columns)
    labels = names + genres
    src, dst, val, col = [], [], [], []
    for s in range(len(names)):
        for k, g in enumerate(genres):
            v = float(x.iloc[s, k])
            if v > 1e-9:
                src.append(s); dst.append(len(names) + k); val.append(v)
                col.append(genre_colour(g).replace('rgb', 'rgba').replace(')', ',0.45)') if genre_colour(g).startswith('rgb') else genre_colour(g) + '80')
    fig = go.Figure(go.Sankey(
        node=dict(label=labels, pad=18, thickness=16, color=['#4c6ef5'] * len(names) + [genre_colour(g) for g in genres]),
        link=dict(source=src, target=dst, value=val, color=col,
                  hovertemplate='%{source.label} → %{target.label}: %{value:.0f} shows<extra></extra>')))
    return _layout(fig, title, height=380)


def waterfall(bridge, title):
    steps = bridge.copy()
    measure = ['absolute'] + ['relative'] * (len(steps) - 1) + ['total']
    x = ['B1 naive', 'scheduling effect', 'selection effect (M1)', 'cost of balance (M4)', 'M4 final']
    y = [steps['daily revenue'].iloc[0]] + steps['change'].iloc[1:].tolist() + [0]
    signed = lambda v: f"{'+' if v >= 0 else '−'}₹{abs(v):,.0f}"
    fig = go.Figure(go.Waterfall(x=x, y=y, measure=measure, text=[signed(v) if k else f'₹{v:,.0f}' for k, v in enumerate(y[:-1])] +
                                 [f"₹{steps['daily revenue'].iloc[-1]:,.0f}"], textposition='outside',
                                 connector=dict(line=dict(color='grey'))))
    fig.update_yaxes(title='₹ per day')
    return _layout(fig, title, height=380)


def funnel(steps, title):
    fig = go.Figure(go.Funnel(y=steps['Step'], x=steps['Rows remaining'], textinfo='value+percent initial'))
    return _layout(fig, title, height=320)


def decay_curve(films, lam, title):
    t = np.linspace(0, max(10, float(films['weeks_out'].max()) + 1), 200)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t, y=np.exp(-lam * t), name=f'weekly decay e^(−{lam:g}·weeks)', line=dict(color='grey')))
    fig.add_trace(go.Scatter(x=films['weeks_out'], y=films['weekly_decay'], mode='markers+text', name='candidate films',
                             text=films['title'].str[:16], textposition='top center', textfont=dict(size=9),
                             marker=dict(size=9, color=[genre_colour(g) for g in films['primary_genre']]),
                             customdata=np.stack([films['title'], films['popularity_norm'], films['effective_demand']], axis=-1),
                             hovertemplate='<b>%{customdata[0]}</b><br>%{x:.1f} weeks out · decay %{y:.3f}<br>'
                                           'popularity %{customdata[1]:.3f} → effective demand %{customdata[2]:.3f}<extra></extra>'))
    fig.update_xaxes(title='weeks since release')
    fig.update_yaxes(title='share of demand left', range=[0, 1.05])
    return _layout(fig, title, height=380)


def capacity_bars(film_title, demand_row, capacities, slot_labels, title):
    # Demand of one film in each slot against the three screen sizes: the part above a line is spill.
    fig = go.Figure(go.Bar(x=slot_labels, y=demand_row, name='demand (persons)', marker_color='#4c6ef5',
                           text=[f'{v:.0f}' for v in demand_row], textposition='outside'))
    for c in sorted(set(capacities), reverse=True):
        fig.add_hline(y=c, line_dash='dash', line_color='firebrick', annotation_text=f'{c}-seat screen',
                      annotation_position='top left')
    fig.update_yaxes(title='persons', range=[0, max(max(demand_row), max(capacities)) * 1.18])
    return _layout(fig, title or f'Demand for {film_title} by slot vs screen capacity', height=360)


def goal_chart(rep_m3, rep_m4, title):
    lab = rep_m4['goal'] + ' ' + rep_m4['measure'].str[:28]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=lab, x=rep_m3['penalised_deviation'], orientation='h', name='Model 3 schedule', marker_color='lightgrey'))
    fig.add_trace(go.Bar(y=lab, x=rep_m4['penalised_deviation'], orientation='h', name='Model 4 schedule', marker_color='seagreen'))
    fig.update_layout(barmode='group')
    fig.update_xaxes(title='penalised deviation from target (0 = goal met)')
    fig.update_yaxes(autorange='reversed')
    return _layout(fig, title, height=360)


def bars(series, title, ytitle, colours=None, fmt='{:,.0f}'):
    fig = go.Figure(go.Bar(x=list(series.index), y=series.values, marker_color=colours,
                           text=[fmt.format(v) for v in series.values], textposition='outside'))
    fig.update_yaxes(title=ytitle)
    return _layout(fig, title, height=330)


def lines(df, x, ys, title, ytitle, names=None, base_x=None):
    fig = go.Figure()
    for k, y in enumerate(ys):
        fig.add_trace(go.Scatter(x=df[x], y=df[y], mode='lines+markers', name=(names or ys)[k]))
    if base_x is not None:
        fig.add_vline(x=base_x, line_dash='dash', line_color='red', annotation_text='current')
    fig.update_xaxes(title=x)
    fig.update_yaxes(title=ytitle)
    return _layout(fig, title, height=360)
