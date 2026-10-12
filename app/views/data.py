import hashlib

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import engine as E
from app import charts, state, ui

ss = st.session_state
cfg = state.cfg()
ui.header('Data & statistics', caption='Load the dataset, see how it is cleaned, and generate statistics on demand.')

# ---------------------------------------------------------------- 1. load
st.subheader('1 · Load the data')
c1, c2 = st.columns([1, 2])
with c1:
    source = st.radio('Source', ['Bundled TMDB 5000 (Kaggle)', 'Upload a CSV in TMDB format'],
                      index=1 if ss.use_upload else 0)
with c2:
    if source.startswith('Upload'):
        f = st.file_uploader('TMDB-format CSV (same columns as tmdb_5000_movies.csv)', type=['csv'])
        if f is not None:
            data = f.getvalue()
            sha = hashlib.sha1(data).hexdigest()
            if not ss.upload or ss.upload[2] != sha:
                ss.upload = (f.name, data, sha)
                ss.runs, ss.sweeps, ss.whatif = {}, {}, None
        if ss.upload:
            ss.use_upload = True
            st.caption(f'Using upload: **{ss.upload[0]}** ({len(ss.upload[1]) / 1e6:.1f} MB)')
        else:
            ss.use_upload = False
            st.caption('No file uploaded yet, so the bundled dataset is used.')
    else:
        if ss.use_upload:
            ss.use_upload = False
            ss.runs, ss.sweeps, ss.whatif = {}, {}, None
        st.caption('TMDB 5000 Movie Dataset: budget, revenue, popularity, ratings, release date, runtime, genres and '
                   'languages of 4,803 films ([Kaggle](https://www.kaggle.com/datasets/tmdb/tmdb-movie-metadata)).')
    st.caption('Required columns: ' + ', '.join(f'`{c}`' for c in E.REQUIRED_COLUMNS))

cfg['min_vote_count'] = st.number_input('Minimum vote count (removes low-information records)', 0, 5000, step=50,
                                        key=state.bind('w_minvote', int(cfg['min_vote_count'])))
ds = state.dataset()
if ds['problems']:
    st.error('This file cannot be used: ' + '; '.join(ds['problems']))
    st.stop()
raw, clean, steps = ds['raw'], ds['clean'], ds['steps']
ui.kpi_row([('Rows (raw)', f'{len(raw):,}'), ('Columns', f'{raw.shape[1]}'), ('Clean films', f'{len(clean):,}'),
            ('Release dates', f"{clean['release_date'].min().year}–{clean['release_date'].max().year}")])
with st.expander('Preview the raw file'):
    st.dataframe(raw.head(50), hide_index=True)

# ---------------------------------------------------------------- 2. cleaning
st.subheader('2 · Cleaning')
c1, c2 = st.columns([3, 2])
with c1:
    st.plotly_chart(charts.funnel(steps, 'Rows remaining after each cleaning step'))
with c2:
    st.markdown('''Steps, in order: parse the JSON-like list columns → keep `status == Released` → keep films with enough
    votes → keep a valid runtime → keep a valid release date → normalise popularity with log(1 + x) then min–max
    scaling (raw popularity is heavily skewed). Zero budget/revenue values mean "not reported"; they are flagged and
    not used by the models.''')
    st.dataframe(steps, hide_index=True)

# ---------------------------------------------------------------- 3. statistics on demand
st.subheader('3 · Statistics on demand')
b = state.base()
scopes = {'Clean dataset': clean, 'Raw dataset': raw}
if b is not None:
    scopes['Candidate pool (this week)'] = b['films']
rec, fresh = state.latest('m1')
if rec is not None and fresh and state.stage_ok(rec['result'], 'm1'):
    r = rec['result']
    scopes['Licensed films (Model 1)'] = r.films.loc[r.licensed]

c1, c2 = st.columns(2)
scope = c1.selectbox('Data scope', list(scopes), key=state.bind('w_scope', 'Clean dataset'))
df = scopes[scope].copy()
ANALYSES = ['Summary statistics', 'Missing values', 'Distribution of a column', 'Category counts', 'Relationship (scatter)',
            'Trend by release year', 'Correlation matrix', 'Top-N films', 'Group-by aggregate']
analysis = c2.selectbox('Analysis', ANALYSES, key=state.bind('w_analysis', 'Summary statistics'))

# filters
if 'release_date' in df.columns:
    years = pd.to_datetime(df['release_date'], errors='coerce').dt.year
    df = df.assign(release_year=years)
num_cols = [c for c in df.select_dtypes('number').columns if c not in ('id',)]
cat_cols = [c for c in ['primary_genre', 'original_language', 'status', 'market_status', 'all listed genres'] if c in df.columns or
            (c == 'all listed genres' and 'genre_list' in df.columns)]
with st.expander('Filters', expanded=False):
    if 'release_year' in df.columns and df['release_year'].notna().any():
        y0, y1 = int(df['release_year'].min()), int(df['release_year'].max())
        if y0 < y1:
            yr = st.slider('Release years', y0, y1, (y0, y1))
            df = df[df['release_year'].between(*yr)]
    if 'primary_genre' in df.columns:
        gsel = st.multiselect('Primary genres (empty = all)', sorted(df['primary_genre'].dropna().unique()))
        if gsel:
            df = df[df['primary_genre'].isin(gsel)]
st.caption(f'{len(df):,} rows after filters.')

spec = {'analysis': analysis}
c1, c2, c3 = st.columns(3)
if analysis == 'Distribution of a column':
    spec['col'] = c1.selectbox('Numeric column', num_cols, index=num_cols.index('runtime') if 'runtime' in num_cols else 0)
    spec['log'] = c2.checkbox('Log scale (x)', value=False)
elif analysis == 'Category counts':
    spec['col'] = c1.selectbox('Category', cat_cols)
    spec['top'] = c2.slider('Show top', 5, 40, 15)
elif analysis == 'Relationship (scatter)':
    spec['x'] = c1.selectbox('x', num_cols, index=num_cols.index('popularity') if 'popularity' in num_cols else 0)
    spec['y'] = c2.selectbox('y', num_cols, index=num_cols.index('vote_average') if 'vote_average' in num_cols else 0)
    spec['logx'] = c3.checkbox('Log x', value='popularity' in num_cols)
elif analysis == 'Trend by release year':
    spec['metric'] = c1.selectbox('Metric', ['number of films'] + [f'mean {c}' for c in num_cols])
elif analysis == 'Top-N films':
    spec['col'] = c1.selectbox('Rank by', num_cols, index=num_cols.index('popularity') if 'popularity' in num_cols else 0)
    spec['n'] = c2.slider('N', 5, 50, 15)
    spec['asc'] = c3.checkbox('Lowest first', value=False)
elif analysis == 'Group-by aggregate':
    spec['by'] = c1.selectbox('Group by', [c for c in cat_cols if c != 'all listed genres'])
    spec['col'] = c2.selectbox('Value', num_cols, index=num_cols.index('popularity') if 'popularity' in num_cols else 0)
    spec['agg'] = c3.selectbox('Aggregate', ['mean', 'median', 'sum', 'count', 'min', 'max'])

if st.button('Generate', type='primary'):
    ss.stats_spec = {**spec, 'scope': scope, 'n_rows': len(df)}
    ss.stats_df = df

res_spec = ss.get('stats_spec')
if res_spec and res_spec.get('scope') == scope and res_spec.get('analysis') == analysis:
    d = ss.stats_df
    a = res_spec['analysis']
    table, fig, summary = None, None, ''
    if a == 'Summary statistics':
        table = d[num_cols].describe().T.round(3)
        summary = f'{len(num_cols)} numeric columns over {len(d):,} rows.'
    elif a == 'Missing values':
        miss = d.isnull().sum()
        table = pd.DataFrame({'missing': miss, '% of rows': (100 * miss / max(len(d), 1)).round(1)}).sort_values('missing', ascending=False)
        if 'budget' in d.columns:
            table.loc['budget == 0 (not reported)'] = [int((d['budget'] == 0).sum()), round(100 * (d['budget'] == 0).mean(), 1)]
        if 'revenue' in d.columns:
            table.loc['revenue == 0 (not reported)'] = [int((d['revenue'] == 0).sum()), round(100 * (d['revenue'] == 0).mean(), 1)]
        fig = px.bar(table[table['missing'] > 0].reset_index(), x='index', y='missing', title='Missing values by column')
        summary = f"{int((miss > 0).sum())} columns have missing values."
    elif a == 'Distribution of a column':
        col = res_spec['col']
        fig = px.histogram(d, x=col, nbins=40, marginal='box', log_x=res_spec['log'], title=f'Distribution of {col}')
        table = d[col].describe().to_frame().T.round(3)
        s = d[col].dropna()
        summary = f'{col}: mean {s.mean():,.2f}, median {s.median():,.2f}, skewness {s.skew():.2f}.'
    elif a == 'Category counts':
        col = res_spec['col']
        counts = (pd.Series([g for gl in d['genre_list'] for g in gl]) if col == 'all listed genres' else d[col]).value_counts()
        table = counts.head(res_spec['top']).rename('films').to_frame()
        fig = px.bar(table.reset_index(), x='index' if 'index' in table.reset_index().columns else table.index.name or col,
                     y='films', title=f'Films by {col}')
        summary = f'Most common: {counts.index[0]} ({counts.iloc[0]:,} films, {counts.iloc[0] / counts.sum():.0%}).' if len(counts) else ''
    elif a == 'Relationship (scatter)':
        x, y = res_spec['x'], res_spec['y']
        fig = px.scatter(d, x=x, y=y, color='primary_genre' if 'primary_genre' in d.columns else None,
                         hover_name='title' if 'title' in d.columns else None, log_x=res_spec['logx'], title=f'{y} vs {x}')
        corr = d[[x, y]].corr().iloc[0, 1]
        table = pd.DataFrame({'pearson correlation': [round(corr, 3)], 'rows': [len(d)]})
        summary = f'Correlation between {x} and {y}: {corr:.2f}.'
    elif a == 'Trend by release year':
        m = res_spec['metric']
        g = d.groupby('release_year')
        series = g.size() if m == 'number of films' else g[m.replace('mean ', '')].mean()
        table = series.rename(m).to_frame()
        fig = px.line(table.reset_index(), x='release_year', y=m, markers=True, title=f'{m} by release year')
        summary = f'Peak: {series.idxmax():.0f} ({series.max():,.2f}).' if len(series) else ''
    elif a == 'Correlation matrix':
        corr = d[num_cols].corr().round(2)
        fig = charts.heatmap(corr, 'Correlation matrix (Pearson)', fmt='.2f', colorscale='RdBu', zmin=-1, zmax=1)
        table = corr
        pairs = corr.where(~np.eye(len(corr), dtype=bool)).stack()
        if len(pairs):
            top = pairs.abs().idxmax()
            summary = f'Strongest pair: {top[0]} – {top[1]} ({corr.loc[top]:.2f}).'
    elif a == 'Top-N films':
        col = res_spec['col']
        show = [c for c in ['title', 'release_date', 'primary_genre', col, 'popularity', 'vote_average', 'runtime'] if c in d.columns]
        table = d.sort_values(col, ascending=res_spec['asc'])[list(dict.fromkeys(show))].head(res_spec['n'])
        summary = f"{'Lowest' if res_spec['asc'] else 'Top'} {res_spec['n']} by {col}."
    elif a == 'Group-by aggregate':
        by, col, agg = res_spec['by'], res_spec['col'], res_spec['agg']
        table = d.groupby(by)[col].agg(agg).sort_values(ascending=False).rename(f'{agg} {col}').to_frame()
        fig = px.bar(table.reset_index().head(30), x=by, y=f'{agg} {col}', title=f'{agg} of {col} by {by}')
        summary = f'Highest: {table.index[0]} ({table.iloc[0, 0]:,.2f}).' if len(table) else ''
    st.success(f"**{a}** · {res_spec['scope']} · {res_spec['n_rows']:,} rows. {summary}")
    if fig is not None:
        st.plotly_chart(fig)
    if table is not None:
        st.dataframe(table)
        st.download_button('Download this table (CSV)', table.to_csv().encode(), file_name='statistics.csv', mime='text/csv')
else:
    st.caption('Choose a scope and an analysis, then press **Generate**.')
