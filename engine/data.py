"""Loading, schema checking and cleaning of the TMDB movie dataset."""
import ast
import io

import numpy as np
import pandas as pd

# Columns the models actually use. Other TMDB columns are kept if present but are not required.
REQUIRED_COLUMNS = ['title', 'genres', 'release_date', 'runtime', 'popularity', 'vote_count', 'vote_average',
                    'status', 'original_language']
JSON_COLUMNS = ['genres', 'keywords', 'production_companies', 'spoken_languages']


def read_dataset(src):
    # src: a path, raw bytes (e.g. an uploaded file) or a file-like object.
    if isinstance(src, (bytes, bytearray)):
        return pd.read_csv(io.BytesIO(src))
    return pd.read_csv(src)


def _parse_json_list(value):
    # TMDB stores lists as JSON-like strings: "[{'id': 28, 'name': 'Action'}, ...]".
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []
    return parsed if isinstance(parsed, list) else []


def check_schema(raw):
    # Problems that prevent the pipeline from running; [] means the file is usable.
    problems = [f'missing column: {c}' for c in REQUIRED_COLUMNS if c not in raw.columns]
    if problems:
        return problems
    sample = raw['genres'].dropna().head(20).map(_parse_json_list)
    if len(sample) and not any(len(x) and isinstance(x[0], dict) and 'name' in x[0] for x in sample):
        problems.append("column 'genres' is not in TMDB format (a list of {'id', 'name'} entries)")
    for col in ['runtime', 'popularity', 'vote_count', 'vote_average']:
        if not pd.api.types.is_numeric_dtype(raw[col]):
            problems.append(f'column {col} must be numeric')
    return problems


def load_and_clean(cfg, raw=None):
    # Cleaning steps in order; returns the clean films and a table of rows remaining after each step.
    df = read_dataset(cfg['data_path']) if raw is None else raw.copy()
    steps = [('Initial rows', len(df))]
    for col in JSON_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(_parse_json_list)
    if 'budget' in df.columns:
        df['budget_missing_flag'] = df['budget'] == 0
    if 'revenue' in df.columns:
        df['revenue_missing_flag'] = df['revenue'] == 0

    df = df[df['status'] == 'Released']
    steps.append(("status == 'Released'", len(df)))
    df = df[df['vote_count'] >= cfg['min_vote_count']]
    steps.append((f"vote_count ≥ {cfg['min_vote_count']}", len(df)))
    df = df[df['runtime'].notnull() & (df['runtime'] > 0)]
    steps.append(('valid runtime', len(df)))
    df = df.assign(release_date=pd.to_datetime(df['release_date'], errors='coerce'))
    df = df[df['release_date'].notnull()].copy()
    steps.append(('valid release_date', len(df)))

    df['popularity_log'] = np.log1p(df['popularity'])
    lo, hi = df['popularity_log'].min(), df['popularity_log'].max()
    df['popularity_norm'] = (df['popularity_log'] - lo) / (hi - lo) if hi > lo else 0.0
    df['genre_list'] = df['genres'].apply(lambda items: [g['name'] for g in items if isinstance(g, dict) and 'name' in g])
    df['primary_genre'] = df['genre_list'].apply(lambda gl: gl[0] if gl else 'Unknown')
    return df.reset_index(drop=True), pd.DataFrame(steps, columns=['Step', 'Rows remaining'])
