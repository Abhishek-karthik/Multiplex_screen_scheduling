# ── VALIDATION HARNESS ─────────────────────────────────────────────────────
import builtins
def display(x):
    try:
        if hasattr(x, 'to_string'):
            print(x.to_string())
        elif hasattr(x, '__str__'):
            print(str(x))
        else:
            print(repr(x))
    except Exception as e:
        print(f'[display error: {e}]')
builtins.display = display

# Force test week
import pandas as _pd
_FORCED_WEEK = _pd.Timestamp('2014-07-16')
print(f"[HARNESS] Test week forced to: {_FORCED_WEEK.date()}")
print("="*60)
# ── CELL 00 ─────────────────────────────────────────
# Phase 0 — Environment Setup
# Run this cell first on a fresh kernel before running any other cell.
import subprocess, sys

packages = ['pandas', 'numpy', 'matplotlib', 'seaborn', 'pulp', 'scipy']
for pkg in packages:
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', pkg, '-q'],
        capture_output=True, text=True
    )
print('All packages installed:', packages)
print('Python:', sys.version.split()[0])


# ── CELL 04 ─────────────────────────────────────────
import ast
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pulp

warnings.filterwarnings('ignore')
sns.set_theme(style='whitegrid', palette='muted')

DATA_PATH = Path('tmdb_5000_movies.csv')
df = pd.read_csv(DATA_PATH)

print('Rows, columns:', df.shape)
print('\nColumn info:')
df.info()
print('\nMissing values:')
print(df.isnull().sum())
print('\nRows with budget == 0:', int((df['budget'] == 0).sum()))
print('Rows with revenue == 0:', int((df['revenue'] == 0).sum()))

# ── CELL 08 ─────────────────────────────────────────

# User/theatre-owner input
SCHEDULE_WEEK_START = _FORCED_WEEK  # forced by harness
WINDOW_WEEKS = 8
WEEKLY_DECAY_RATE = 0.55

print('Selected schedule week:', SCHEDULE_WEEK_START.date())
print('Candidate window:', WINDOW_WEEKS, 'weeks before selected week')
print('Decay rate lambda:', WEEKLY_DECAY_RATE)


# ── CELL 11 ─────────────────────────────────────────
clean_df = pd.read_csv(DATA_PATH)
row_counts = [('Initial rows', len(clean_df))]

for col in ['genres', 'keywords', 'production_companies', 'spoken_languages']:
    clean_df[col] = clean_df[col].apply(ast.literal_eval)

clean_df['budget_missing_flag'] = clean_df['budget'] == 0
clean_df['revenue_missing_flag'] = clean_df['revenue'] == 0
budget_zero_count = int(clean_df['budget_missing_flag'].sum())
revenue_zero_count = int(clean_df['revenue_missing_flag'].sum())

clean_df = clean_df[clean_df['status'] == 'Released'].copy()
row_counts.append(("After status == 'Released'", len(clean_df)))

clean_df = clean_df[clean_df['vote_count'] >= 200].copy()
row_counts.append(('After vote_count >= 200', len(clean_df)))

runtime_null_before = int(clean_df['runtime'].isnull().sum())
runtime_zero_before = int((clean_df['runtime'] == 0).sum())
clean_df = clean_df[clean_df['runtime'].notnull() & (clean_df['runtime'] > 0)].copy()
row_counts.append(('After runtime filter', len(clean_df)))

release_null_before = int(clean_df['release_date'].isnull().sum())
clean_df = clean_df[clean_df['release_date'].notnull()].copy()
clean_df['release_date'] = pd.to_datetime(clean_df['release_date'], errors='coerce')
release_nat_after = int(clean_df['release_date'].isnull().sum())
clean_df = clean_df[clean_df['release_date'].notnull()].copy()
row_counts.append(('After release_date filter', len(clean_df)))

clean_df['popularity_log'] = np.log1p(clean_df['popularity'])
clean_df['popularity_norm'] = (
    (clean_df['popularity_log'] - clean_df['popularity_log'].min()) /
    (clean_df['popularity_log'].max() - clean_df['popularity_log'].min())
)
clean_df['primary_genre'] = clean_df['genres'].apply(
    lambda items: items[0]['name'] if isinstance(items, list) and len(items) else 'Unknown'
)
clean_df['language_name'] = clean_df['spoken_languages'].apply(
    lambda items: items[0]['name'] if isinstance(items, list) and len(items) else 'Unknown'
)

def build_weekly_market(source_df, schedule_week_start, window_weeks=8, decay_rate=0.55):
    weekly = source_df.copy()
    weekly['schedule_week_start'] = pd.Timestamp(schedule_week_start)
    weekly['weeks_out'] = (weekly['schedule_week_start'] - weekly['release_date']).dt.days / 7
    weekly['is_released_by_week'] = weekly['weeks_out'] >= 0
    weekly['is_new_this_week'] = weekly['weeks_out'].between(0, 1, inclusive='both')
    weekly['is_current_window'] = weekly['weeks_out'].between(0, window_weeks, inclusive='both')
    weekly['weekly_decay'] = np.where(
        weekly['is_released_by_week'],
        np.exp(-decay_rate * weekly['weeks_out'].clip(lower=0)),
        0.0
    )
    weekly['effective_demand'] = weekly['popularity_norm'] * weekly['weekly_decay']
    weekly['market_status'] = np.select(
        [
            ~weekly['is_released_by_week'],
            weekly['is_new_this_week'],
            weekly['is_current_window'],
        ],
        [
            'Future release',
            'New this week',
            'Currently running',
        ],
        default='Older catalogue'
    )
    return weekly


weekly_market_df = build_weekly_market(
    clean_df,
    schedule_week_start=SCHEDULE_WEEK_START,
    window_weeks=WINDOW_WEEKS,
    decay_rate=WEEKLY_DECAY_RATE,
)

candidate_df = (
    weekly_market_df[weekly_market_df['is_current_window']]
    .sort_values(['release_date', 'effective_demand'], ascending=[False, False])
    .reset_index(drop=True)
)

weekly_market_df.to_csv('weekly_market_synthesized.csv', index=False)
candidate_df.to_csv('weekly_candidate_pool.csv', index=False)

cleaning_summary = pd.DataFrame(row_counts, columns=['Step', 'Rows'])
market_status_counts = weekly_market_df['market_status'].value_counts()

print(cleaning_summary.to_string(index=False))
print('\nBudget == 0 flagged:', budget_zero_count)
print('Revenue == 0 flagged:', revenue_zero_count)
print('Runtime null before drop:', runtime_null_before)
print('Runtime zero before drop:', runtime_zero_before)
print('Release_date null before drop:', release_null_before)
print('Invalid release dates after parsing:', release_nat_after)
print('Schedule week start:', SCHEDULE_WEEK_START.date())
print('Current-running window:', WINDOW_WEEKS, 'weeks')
print('Weekly decay rate:', WEEKLY_DECAY_RATE)
print('\nWeekly market status counts:')
print(market_status_counts.to_string())
print('\nCandidate pool rows:', len(candidate_df))
print('\nSaved synthesized files:')
print('- weekly_market_synthesized.csv')
print('- weekly_candidate_pool.csv')

candidate_df[[
    'title', 'release_date', 'market_status', 'weeks_out', 'popularity_norm',
    'weekly_decay', 'effective_demand', 'runtime', 'vote_count',
    'primary_genre', 'original_language'
]].round({'weeks_out': 2, 'popularity_norm': 4, 'weekly_decay': 4, 'effective_demand': 4})

# ── CELL 16 ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
genre_counts = candidate_df['primary_genre'].value_counts()
sns.barplot(x=genre_counts.index, y=genre_counts.values, ax=ax)
ax.set_title('Genre Distribution - Candidate Films')
ax.set_xlabel('Primary genre')
ax.set_ylabel('Number of films')
ax.tick_params(axis='x', rotation=35)
plt.tight_layout()
plt.show()
print(genre_counts)

# ── CELL 18 ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 4))
sns.histplot(candidate_df['runtime'], bins=8, kde=False, ax=ax)
ax.axvline(candidate_df['runtime'].mean(), color='red', linestyle='--', label=f"Mean = {candidate_df['runtime'].mean():.1f} min")
ax.set_title('Runtime Histogram - Candidate Films')
ax.set_xlabel('Runtime in minutes')
ax.legend()
plt.tight_layout()
plt.show()
print(candidate_df['runtime'].describe())

# ── CELL 20 ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))
sns.scatterplot(data=candidate_df, x='popularity', y='vote_average', hue='primary_genre', s=90, ax=ax)
for _, row in candidate_df.iterrows():
    ax.annotate(row['title'][:16], (row['popularity'], row['vote_average']), fontsize=7, xytext=(4, 3), textcoords='offset points')
ax.set_title('Popularity vs Vote Average')
plt.tight_layout()
plt.show()

# ── CELL 22 ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
sns.histplot(candidate_df['popularity'], bins=8, ax=axes[0], color='tomato')
axes[0].set_title('Raw popularity')
sns.histplot(candidate_df['popularity_norm'], bins=8, ax=axes[1], color='seagreen')
axes[1].set_title('Log + min-max normalized popularity')
plt.tight_layout()
plt.show()
print('Raw popularity range:', round(candidate_df['popularity'].min(), 2), 'to', round(candidate_df['popularity'].max(), 2))
print('Normalized range:', round(candidate_df['popularity_norm'].min(), 4), 'to', round(candidate_df['popularity_norm'].max(), 4))

# ── CELL 26 ─────────────────────────────────────────
SCREENS = list(range(5))
CAPACITIES = {0: 250, 1: 180, 2: 180, 3: 120, 4: 120}
SLOTS = list(range(6))
SLOT_LABELS = ['9am', '12pm', '3pm', '6pm', '9pm', '11pm']
SLOT_START_MIN = {0: 9*60, 1: 12*60, 2: 15*60, 3: 18*60, 4: 21*60, 5: 23*60}
SLOT_LENGTHS = {0: 180, 1: 180, 2: 180, 3: 180, 4: 180, 5: 180}
PRICES = {0: 120, 1: 150, 2: 180, 3: 250, 4: 280, 5: 200}
SLOT_FACTOR = {0: 0.55, 1: 0.70, 2: 0.75, 3: 0.95, 4: 1.00, 5: 0.80}
LAMBDA = WEEKLY_DECAY_RATE
DEMAND_SCALE = 15.0
LICENSING_BUDGET = 4_000_000
CLEANUP_BUFFER = 20

GENRE_AFFINITY = {
    'Action': {0:0.55, 1:0.70, 2:0.80, 3:1.00, 4:1.00, 5:0.75},
    'Adventure': {0:0.60, 1:0.85, 2:0.95, 3:1.00, 4:0.90, 5:0.65},
    'Comedy': {0:0.65, 1:0.90, 2:0.90, 3:0.85, 4:0.75, 5:0.55},
    'Drama': {0:0.60, 1:0.75, 2:0.85, 3:0.85, 4:0.75, 5:0.55},
    'Horror': {0:0.35, 1:0.45, 2:0.55, 3:0.75, 4:0.95, 5:1.00},
    'Mystery': {0:0.45, 1:0.60, 2:0.70, 3:0.85, 4:1.00, 5:0.85},
    'Crime': {0:0.45, 1:0.60, 2:0.70, 3:0.90, 4:1.00, 5:0.85},
    'Default': {0:0.50, 1:0.65, 2:0.75, 3:0.85, 4:0.85, 5:0.65},
}
FAMILY_GENRES = {'Adventure', 'Comedy', 'Animation', 'Family'}
REGIONAL_LANGUAGES = {'hi', 'ta', 'te', 'ml', 'kn', 'ko', 'ja', 'zh'}
print('Synthetic constants loaded.')
print('Schedule week start:', SCHEDULE_WEEK_START.date())
print('Candidate window:', WINDOW_WEEKS, 'weeks')
print('Decay rate lambda:', LAMBDA)

# ── CELL 30 ─────────────────────────────────────────
films = candidate_df.copy().reset_index(drop=True)
films['decay'] = films['weekly_decay']
films['demand'] = films['effective_demand']

occ = np.zeros((len(films), len(SLOTS)))
rev = np.zeros((len(films), len(SLOTS), len(SCREENS)))
for i, row in films.iterrows():
    affinity = GENRE_AFFINITY.get(row['primary_genre'], GENRE_AFFINITY['Default'])
    for j in SLOTS:
        occ[i, j] = min(row['demand'] * DEMAND_SCALE * SLOT_FACTOR[j] * affinity[j], 1.0)
        for s in SCREENS:
            rev[i, j, s] = PRICES[j] * CAPACITIES[s] * occ[i, j]

occ_df = pd.DataFrame(occ, index=films['title'], columns=SLOT_LABELS)
rev_avg_df = pd.DataFrame(rev.mean(axis=2), index=films['title'], columns=SLOT_LABELS)
print(films[[
    'title', 'market_status', 'weeks_out', 'popularity_norm',
    'decay', 'demand', 'primary_genre'
]].round(4).to_string(index=False))
print('\nOccupancy matrix shape:', occ.shape)
print('Revenue matrix shape:', rev.shape)

# ── CELL 31 ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(occ_df, cmap='YlOrRd', annot=True, fmt='.2f', ax=ax, cbar_kws={'label': 'Occupancy'})
ax.set_title('Expected Occupancy Matrix')
plt.tight_layout()
plt.show()

fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(rev_avg_df / 1000, cmap='Blues', annot=True, fmt='.1f', ax=ax, cbar_kws={'label': 'Revenue, Rs. thousands'})
ax.set_title('Expected Revenue Matrix, Average Screen')
plt.tight_layout()
plt.show()

# ── CELL 34 ─────────────────────────────────────────
BASE_FEE = 300_000
films['licensing_fee'] = (
    BASE_FEE * (0.50 + 0.50 * films['popularity_norm']) * (1.00 + 0.30 * films['decay'])
).round(0)
films['revenue_potential_score'] = rev.sum(axis=(1, 2)).round(0)

n = len(films)
prob1 = pulp.LpProblem('Model_1_Knapsack', pulp.LpMaximize)
y = pulp.LpVariable.dicts('license', range(n), cat='Binary')
prob1 += pulp.lpSum(films.loc[i, 'revenue_potential_score'] * y[i] for i in range(n))
prob1 += pulp.lpSum(films.loc[i, 'licensing_fee'] * y[i] for i in range(n)) <= LICENSING_BUDGET
prob1 += pulp.lpSum(y[i] for i in range(n)) >= 8
prob1 += pulp.lpSum(y[i] for i in range(n)) <= 12

action_idx = [i for i in range(n) if films.loc[i, 'primary_genre'] in {'Action', 'Crime', 'Mystery', 'Horror', 'Thriller'}]
family_idx = [i for i in range(n) if films.loc[i, 'primary_genre'] in FAMILY_GENRES]
regional_idx = [i for i in range(n) if films.loc[i, 'original_language'] in REGIONAL_LANGUAGES]
if action_idx:
    prob1 += pulp.lpSum(y[i] for i in action_idx) >= 1
if family_idx:
    prob1 += pulp.lpSum(y[i] for i in family_idx) >= 1
if regional_idx:
    prob1 += pulp.lpSum(y[i] for i in regional_idx) >= 1

prob1.solve(pulp.PULP_CBC_CMD(msg=False))
selected_idx = [i for i in range(n) if pulp.value(y[i]) > 0.5]
licensed_films = films.loc[selected_idx].copy().reset_index(drop=True)

print('Solver status:', pulp.LpStatus[prob1.status])
print('Selected films:', len(licensed_films))
print('Total licensing fee: Rs.{:,.0f}'.format(licensed_films['licensing_fee'].sum()))
print('Revenue potential score: Rs.{:,.0f}'.format(licensed_films['revenue_potential_score'].sum()))
print('Regional category available in pool:', bool(regional_idx))
licensed_films[['title', 'primary_genre', 'original_language', 'licensing_fee', 'revenue_potential_score']].sort_values('revenue_potential_score', ascending=False)

# ── CELL 36 ─────────────────────────────────────────
greedy = films.copy()
greedy['value_density'] = greedy['revenue_potential_score'] / greedy['licensing_fee']
greedy = greedy.sort_values('value_density', ascending=False)
greedy_rows = []
greedy_cost = 0
for _, row in greedy.iterrows():
    if len(greedy_rows) >= 12:
        break
    if greedy_cost + row['licensing_fee'] <= LICENSING_BUDGET:
        greedy_rows.append(row)
        greedy_cost += row['licensing_fee']
greedy_selected = pd.DataFrame(greedy_rows)
print('Greedy selected films:', len(greedy_selected))
print('Greedy cost: Rs.{:,.0f}'.format(greedy_selected['licensing_fee'].sum()))
print('Greedy score: Rs.{:,.0f}'.format(greedy_selected['revenue_potential_score'].sum()))
print('ILP score improvement over greedy: Rs.{:,.0f}'.format(licensed_films['revenue_potential_score'].sum() - greedy_selected['revenue_potential_score'].sum()))

# ── CELL 39 ─────────────────────────────────────────
genre_demand = licensed_films.groupby('primary_genre')['demand'].sum().sort_values(ascending=False)
total_capacity = sum(CAPACITIES.values())
genre_seat_need = (genre_demand / genre_demand.sum() * total_capacity).round(0).astype(int)
diff = total_capacity - genre_seat_need.sum()
if diff != 0:
    genre_seat_need.iloc[0] += diff

genres_t = genre_seat_need.index.tolist()
prob2 = pulp.LpProblem('Model_2_Transportation', pulp.LpMinimize)
x = pulp.LpVariable.dicts('seat_flow', [(s, g) for s in SCREENS for g in genres_t], lowBound=0)
for s in SCREENS:
    prob2 += pulp.lpSum(x[(s, g)] for g in genres_t) == CAPACITIES[s]
for g in genres_t:
    prob2 += pulp.lpSum(x[(s, g)] for s in SCREENS) == int(genre_seat_need[g])
genre_rank = {g: r for r, g in enumerate(genres_t)}
capacity_rank = {s: r for r, s in enumerate(sorted(SCREENS, key=lambda s: CAPACITIES[s], reverse=True))}
prob2 += pulp.lpSum(abs(capacity_rank[s] - genre_rank[g]) * x[(s, g)] for s in SCREENS for g in genres_t)
prob2.solve(pulp.PULP_CBC_CMD(msg=False))

transport = pd.DataFrame(index=[f'Screen {s}' for s in SCREENS], columns=genres_t)
for s in SCREENS:
    for g in genres_t:
        transport.loc[f'Screen {s}', g] = round(pulp.value(x[(s, g)]), 1)

screen_preferred_genre = {}
for s in SCREENS:
    screen_row = transport.loc[f'Screen {s}'].astype(float)
    screen_preferred_genre[s] = screen_row.idxmax()

print('Solver status:', pulp.LpStatus[prob2.status])
print('Screen preferred genres from transportation quotas:')
print(screen_preferred_genre)
transport

# ── CELL 42 ─────────────────────────────────────────
films_l = licensed_films.copy().reset_index(drop=True)
n_l = len(films_l)
occ_l = np.zeros((n_l, len(SLOTS)))
rev_l = np.zeros((n_l, len(SLOTS), len(SCREENS)))
for i, row in films_l.iterrows():
    affinity = GENRE_AFFINITY.get(row['primary_genre'], GENRE_AFFINITY['Default'])
    for j in SLOTS:
        occ_l[i, j] = min(row['demand'] * DEMAND_SCALE * SLOT_FACTOR[j] * affinity[j], 1.0)
        for s in SCREENS:
            rev_l[i, j, s] = PRICES[j] * CAPACITIES[s] * occ_l[i, j]

slot_fit_length = {
    j: (SLOT_START_MIN[j + 1] - SLOT_START_MIN[j]) if j < max(SLOTS) else SLOT_LENGTHS[j]
    for j in SLOTS
}

prob3 = pulp.LpProblem('Model_3_Assignment', pulp.LpMaximize)
a = pulp.LpVariable.dicts('assign', [(i, j, s) for i in range(n_l) for j in SLOTS for s in SCREENS], cat='Binary')
prob3 += pulp.lpSum(rev_l[i, j, s] * a[(i, j, s)] for i in range(n_l) for j in SLOTS for s in SCREENS)

is_feasible = {}
for i in range(n_l):
    for j in SLOTS:
        can_fit = films_l.loc[i, 'runtime'] + CLEANUP_BUFFER <= slot_fit_length[j]
        for s in SCREENS:
            is_feasible[(i, j, s)] = can_fit

for j in SLOTS:
    for s in SCREENS:
        prob3 += pulp.lpSum(a[(i, j, s)] for i in range(n_l)) == 1

for i in range(n_l):
    for j in SLOTS:
        prob3 += pulp.lpSum(a[(i, j, s)] for s in SCREENS) <= 1
        for s in SCREENS:
            if not is_feasible[(i, j, s)]:
                prob3 += a[(i, j, s)] == 0
    prob3 += pulp.lpSum(a[(i, j, s)] for j in SLOTS for s in SCREENS) <= 5

skipped_genre_constraints = []
for genre in sorted(films_l['primary_genre'].unique()):
    genre_films = [i for i in range(n_l) if films_l.loc[i, 'primary_genre'] == genre]
    feasible_terms = [
        a[(i, j, s)]
        for i in genre_films
        for j in SLOTS
        for s in SCREENS
        if is_feasible[(i, j, s)]
    ]
    if feasible_terms:
        prob3 += pulp.lpSum(feasible_terms) >= 1
    else:
        skipped_genre_constraints.append(genre)

skipped_screen_quota_constraints = []
for s, preferred_genre in screen_preferred_genre.items():
    preferred_films = [i for i in range(n_l) if films_l.loc[i, 'primary_genre'] == preferred_genre]
    feasible_terms = [
        a[(i, j, s)]
        for i in preferred_films
        for j in SLOTS
        if is_feasible[(i, j, s)]
    ]
    if feasible_terms:
        prob3 += pulp.lpSum(feasible_terms) >= 1
    else:
        skipped_screen_quota_constraints.append((s, preferred_genre))


# M2→M3 wiring: screen genre quotas as soft preference
# screen_preferred_genre from Model 2 is used here to add a revenue bonus
# of 5% when a film's genre matches the screen's transportation quota.
# This is a soft preference (bonus in objective), not a hard constraint,
# so the solver can override it if revenue strongly favours another film.
GENRE_BONUS = 0.05  # 5% revenue bonus for matching screen quota
for i in range(n_l):
    film_genre = films_l.loc[i, 'primary_genre']
    for s in SCREENS:
        preferred = screen_preferred_genre.get(s, None)
        if preferred and film_genre == preferred:
            for j in SLOTS:
                if is_feasible[(i, j, s)]:
                    # Re-add a small bonus to objective for matching quota
                    prob3.objective += GENRE_BONUS * rev_l[i, j, s] * a[(i, j, s)]

prob3.solve(pulp.PULP_CBC_CMD(msg=False))
status3 = pulp.LpStatus[prob3.status]
print('Solver status:', status3)
if skipped_genre_constraints:
    print('Skipped impossible genre constraints:', skipped_genre_constraints)
if skipped_screen_quota_constraints:
    print('Skipped impossible screen quota constraints:', skipped_screen_quota_constraints)
if status3 != 'Optimal':
    raise ValueError(f'Model 3 assignment is {status3}. Choose a week with more feasible films or relax constraints.')

schedule_records = []
for s in SCREENS:
    for j in SLOTS:
        for i in range(n_l):
            val = pulp.value(a[(i, j, s)])
            if val is not None and val > 0.5:
                schedule_records.append({
                    'screen': s,
                    'capacity': CAPACITIES[s],
                    'slot': j,
                    'time': SLOT_LABELS[j],
                    'film_index': i,
                    'title': films_l.loc[i, 'title'],
                    'genre': films_l.loc[i, 'primary_genre'],
                    'runtime': films_l.loc[i, 'runtime'],
                    'occupancy': occ_l[i, j],
                    'revenue': rev_l[i, j, s],
                })
assignment_df = pd.DataFrame(schedule_records)
schedule_grid = assignment_df.pivot(index='screen', columns='time', values='title').reindex(index=SCREENS, columns=SLOT_LABELS)
print('Assigned cells:', len(assignment_df))
print('Model 3 revenue: Rs.{:,.0f}'.format(assignment_df['revenue'].sum()))
schedule_grid

# ── CELL 44 ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))
sns.heatmap(
    assignment_df.pivot(index='screen', columns='time', values='occupancy').reindex(index=SCREENS, columns=SLOT_LABELS),
    annot=True, fmt='.2f', cmap='YlGnBu', ax=ax, cbar_kws={'label': 'Occupancy'}
)
ax.set_title('Model 3 Schedule Occupancy Heatmap')
plt.tight_layout()
plt.show()

# ── CELL 47 ─────────────────────────────────────────
def minutes_to_clock(minutes):
    hours = int(minutes // 60) % 24
    mins = int(minutes % 60)
    return f'{hours:02d}:{mins:02d}'

seq_df = assignment_df.copy()
seq_df['start_min'] = seq_df['slot'].map(SLOT_START_MIN)
seq_df['end_min'] = seq_df['start_min'] + seq_df['runtime'] + CLEANUP_BUFFER
seq_df['start_time'] = seq_df['start_min'].apply(minutes_to_clock)
seq_df['end_with_cleanup'] = seq_df['end_min'].apply(minutes_to_clock)

idle_records = []
for s in SCREENS:
    s_df = seq_df[seq_df['screen'] == s].sort_values('start_min')
    previous_end = None
    for _, row in s_df.iterrows():
        idle = 0 if previous_end is None else max(row['start_min'] - previous_end, 0)
        idle_records.append({'screen': s, 'time': row['time'], 'title': row['title'], 'idle_before_min': idle})
        previous_end = row['end_min']
idle_df = pd.DataFrame(idle_records)
avg_idle = idle_df['idle_before_min'].mean()
max_idle = idle_df['idle_before_min'].max()
print('Average idle before shows:', round(avg_idle, 1), 'minutes')
print('Maximum idle before shows:', round(max_idle, 1), 'minutes')
seq_df.sort_values(['screen', 'slot'])[['screen', 'time', 'start_time', 'title', 'runtime', 'end_with_cleanup']]

# ── CELL 49 ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))
for _, row in seq_df.iterrows():
    ax.barh(row['screen'], row['runtime'], left=row['start_min'], color='steelblue', alpha=0.75)
    ax.text(row['start_min'] + 4, row['screen'], row['title'][:18], va='center', fontsize=7, color='white')
ax.set_yticks(SCREENS)
ax.set_yticklabels([f'Screen {s}' for s in SCREENS])
xticks = [9*60, 12*60, 15*60, 18*60, 21*60, 23*60, 26*60]
ax.set_xticks(xticks)
ax.set_xticklabels([minutes_to_clock(x) for x in xticks])
ax.set_title('Model 4 Gantt Chart')
plt.tight_layout()
plt.show()

# ── CELL 52 ─────────────────────────────────────────
prob5 = pulp.LpProblem('Model_5_Set_Covering', pulp.LpMinimize)
z = pulp.LpVariable.dicts('cover', list(assignment_df.index), cat='Binary')
prob5 += pulp.lpSum(z[idx] for idx in assignment_df.index)

for genre in sorted(assignment_df['genre'].unique()):
    idxs = assignment_df.index[assignment_df['genre'] == genre].tolist()
    prob5 += pulp.lpSum(z[idx] for idx in idxs) >= 1

top5_titles = licensed_films.sort_values('revenue_potential_score', ascending=False).head(5)['title'].tolist()
for title in top5_titles:
    idxs = assignment_df.index[assignment_df['title'] == title].tolist()
    if idxs:
        prob5 += pulp.lpSum(z[idx] for idx in idxs) >= min(2, len(idxs))

for slot in SLOTS:
    idxs = assignment_df.index[(assignment_df['slot'] == slot) & (assignment_df['genre'].isin(FAMILY_GENRES))].tolist()
    if idxs:
        prob5 += pulp.lpSum(z[idx] for idx in idxs) >= 1

prob5.solve(pulp.PULP_CBC_CMD(msg=False))
assignment_df['protected_core'] = [int(pulp.value(z[idx]) > 0.5) for idx in assignment_df.index]
core_df = assignment_df[assignment_df['protected_core'] == 1].copy()
print('Solver status:', pulp.LpStatus[prob5.status])
print('Protected obligation cells:', len(core_df))
print('Genres covered:', sorted(core_df['genre'].unique()))
print('Top 5 titles:', top5_titles)
core_df.sort_values(['slot', 'screen'])[['screen', 'time', 'title', 'genre', 'revenue']]

# ── CELL 54 ─────────────────────────────────────────
coverage_matrix = assignment_df.pivot(index='screen', columns='time', values='protected_core').reindex(index=SCREENS, columns=SLOT_LABELS)
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
sns.heatmap(coverage_matrix, annot=True, fmt='d', cmap='Greens', cbar=False, ax=axes[0])
axes[0].set_title('Protected Obligation Core')
comparison = pd.Series({'Revenue-max schedule': assignment_df['revenue'].sum(), 'Protected core only': core_df['revenue'].sum()}) / 1000
comparison.plot(kind='bar', ax=axes[1], color=['tomato', 'steelblue'])
axes[1].set_title('Revenue Comparison')
axes[1].set_ylabel('Rs. thousands')
axes[1].tick_params(axis='x', rotation=20)
plt.tight_layout()
plt.show()

# ── CELL 57 ─────────────────────────────────────────
films_gp = films_l.copy().reset_index(drop=True)
n_gp = len(films_gp)
prime_slots = [3, 4]
gap_slots = [j for j in SLOTS if j < max(SLOTS)]

prob6 = pulp.LpProblem('Model_6_Goal_Programming', pulp.LpMinimize)
gp = pulp.LpVariable.dicts('gp_assign', [(i, j, s) for i in range(n_gp) for j in SLOTS for s in SCREENS], cat='Binary')
genre_cover = pulp.LpVariable.dicts('genre_cover', sorted(films_gp['primary_genre'].unique()), cat='Binary')
d_minus = pulp.LpVariable.dicts('d_minus', range(1, 6), lowBound=0)
d_plus = pulp.LpVariable.dicts('d_plus', range(1, 6), lowBound=0)

is_feasible_gp = {}
for i in range(n_gp):
    for j in SLOTS:
        can_fit = films_gp.loc[i, 'runtime'] + CLEANUP_BUFFER <= slot_fit_length[j]
        for s in SCREENS:
            is_feasible_gp[(i, j, s)] = can_fit

for j in SLOTS:
    for s in SCREENS:
        prob6 += pulp.lpSum(gp[(i, j, s)] for i in range(n_gp)) == 1

for i in range(n_gp):
    for j in SLOTS:
        prob6 += pulp.lpSum(gp[(i, j, s)] for s in SCREENS) <= 1
        for s in SCREENS:
            if not is_feasible_gp[(i, j, s)]:
                prob6 += gp[(i, j, s)] == 0
    prob6 += pulp.lpSum(gp[(i, j, s)] for j in SLOTS for s in SCREENS) <= 5

for s, preferred_genre in screen_preferred_genre.items():
    preferred_films = [i for i in range(n_gp) if films_gp.loc[i, 'primary_genre'] == preferred_genre]
    feasible_terms = [gp[(i, j, s)] for i in preferred_films for j in SLOTS if is_feasible_gp[(i, j, s)]]
    if feasible_terms:
        prob6 += pulp.lpSum(feasible_terms) >= 1

# Protect the obligation core from Model 5 where possible.
for _, row in core_df.iterrows():
    i = int(row['film_index'])
    j = int(row['slot'])
    s = int(row['screen'])
    if i < n_gp and is_feasible_gp[(i, j, s)]:
        prob6 += gp[(i, j, s)] == 1

genres_gp = sorted(films_gp['primary_genre'].unique())
for genre in genres_gp:
    genre_films = [i for i in range(n_gp) if films_gp.loc[i, 'primary_genre'] == genre]
    assign_sum = pulp.lpSum(gp[(i, j, s)] for i in genre_films for j in SLOTS for s in SCREENS)
    prob6 += assign_sum >= genre_cover[genre]
    prob6 += assign_sum <= len(SLOTS) * len(SCREENS) * genre_cover[genre]

revenue_expr = pulp.lpSum(rev_l[i, j, s] * gp[(i, j, s)] for i in range(n_gp) for j in SLOTS for s in SCREENS)
occ_expr = pulp.lpSum(occ_l[i, j] * gp[(i, j, s)] for i in range(n_gp) for j in SLOTS for s in SCREENS) / (len(SLOTS) * len(SCREENS))
genre_expr = pulp.lpSum(genre_cover[g] for g in genres_gp)
prime_occ_expr = pulp.lpSum(occ_l[i, j] * gp[(i, j, s)] for i in range(n_gp) for j in prime_slots for s in SCREENS) / (len(prime_slots) * len(SCREENS))
avg_idle_expr = pulp.lpSum(
    (SLOT_START_MIN[j + 1] - SLOT_START_MIN[j] - CLEANUP_BUFFER) -
    pulp.lpSum(films_gp.loc[i, 'runtime'] * gp[(i, j, s)] for i in range(n_gp))
    for s in SCREENS
    for j in gap_slots
) / (len(SCREENS) * len(gap_slots))

G_REVENUE_TARGET = 850_000
G_OCC_TARGET = 0.65
G_GENRE_TARGET = 6
G_IDLE_TARGET = 45
G_PRIME_OCC_TARGET = 0.80

prob6 += revenue_expr / G_REVENUE_TARGET + d_minus[1] - d_plus[1] == 1
prob6 += occ_expr + d_minus[2] - d_plus[2] == G_OCC_TARGET
prob6 += genre_expr / G_GENRE_TARGET + d_minus[3] - d_plus[3] == 1
prob6 += avg_idle_expr / G_IDLE_TARGET + d_minus[4] - d_plus[4] == 1
prob6 += prime_occ_expr + d_minus[5] - d_plus[5] == G_PRIME_OCC_TARGET

W = {1: 0.50, 2: 0.20, 3: 0.15, 4: 0.10, 5: 0.05}
prob6 += (
    W[1] * d_minus[1] +
    W[2] * d_minus[2] +
    W[3] * d_minus[3] +
    W[4] * d_plus[4] +
    W[5] * d_minus[5] -
    1e-9 * revenue_expr
)

prob6.solve(pulp.PULP_CBC_CMD(msg=False))
status6 = pulp.LpStatus[prob6.status]
print('Solver status:', status6)
if status6 != 'Optimal':
    raise ValueError(f'Model 6 goal programming is {status6}.')

final_records = []
for s in SCREENS:
    for j in SLOTS:
        for i in range(n_gp):
            val = pulp.value(gp[(i, j, s)])
            if val is not None and val > 0.5:
                final_records.append({
                    'screen': s,
                    'capacity': CAPACITIES[s],
                    'slot': j,
                    'time': SLOT_LABELS[j],
                    'film_index': i,
                    'title': films_gp.loc[i, 'title'],
                    'genre': films_gp.loc[i, 'primary_genre'],
                    'runtime': films_gp.loc[i, 'runtime'],
                    'occupancy': occ_l[i, j],
                    'revenue': rev_l[i, j, s],
                })

final_schedule_df = pd.DataFrame(final_records)
final_grid = final_schedule_df.pivot(index='screen', columns='time', values='title').reindex(index=SCREENS, columns=SLOT_LABELS)

def minutes_to_clock(minutes):
    hours = int(minutes // 60) % 24
    mins = int(minutes % 60)
    return f'{hours:02d}:{mins:02d}'

seq_df = final_schedule_df.copy()
seq_df['start_min'] = seq_df['slot'].map(SLOT_START_MIN)
seq_df['end_min'] = seq_df['start_min'] + seq_df['runtime'] + CLEANUP_BUFFER
seq_df['start_time'] = seq_df['start_min'].apply(minutes_to_clock)
seq_df['end_with_cleanup'] = seq_df['end_min'].apply(minutes_to_clock)

idle_records = []
for s in SCREENS:
    s_df = seq_df[seq_df['screen'] == s].sort_values('start_min')
    previous_end = None
    for _, row in s_df.iterrows():
        idle = 0 if previous_end is None else max(row['start_min'] - previous_end, 0)
        idle_records.append({'screen': s, 'time': row['time'], 'title': row['title'], 'idle_before_min': idle})
        previous_end = row['end_min']
idle_df = pd.DataFrame(idle_records)
avg_idle = idle_df['idle_before_min'].mean()
max_idle = idle_df['idle_before_min'].max()

final_revenue = final_schedule_df['revenue'].sum()
final_avg_occ = final_schedule_df['occupancy'].mean()
final_genres = final_schedule_df['genre'].nunique()
final_prime_occ = final_schedule_df[final_schedule_df['slot'].isin(prime_slots)]['occupancy'].mean()

GOALS = pd.DataFrame([
    {'goal': 'Revenue', 'target': G_REVENUE_TARGET, 'achieved': final_revenue, 'met': final_revenue >= G_REVENUE_TARGET, 'weight': W[1], 'd_minus': pulp.value(d_minus[1]), 'd_plus': pulp.value(d_plus[1])},
    {'goal': 'Average occupancy', 'target': G_OCC_TARGET, 'achieved': final_avg_occ, 'met': final_avg_occ >= G_OCC_TARGET, 'weight': W[2], 'd_minus': pulp.value(d_minus[2]), 'd_plus': pulp.value(d_plus[2])},
    {'goal': 'Genres covered', 'target': G_GENRE_TARGET, 'achieved': final_genres, 'met': final_genres >= G_GENRE_TARGET, 'weight': W[3], 'd_minus': pulp.value(d_minus[3]), 'd_plus': pulp.value(d_plus[3])},
    {'goal': 'Average idle minutes', 'target': G_IDLE_TARGET, 'achieved': avg_idle, 'met': avg_idle <= G_IDLE_TARGET, 'weight': W[4], 'd_minus': pulp.value(d_minus[4]), 'd_plus': pulp.value(d_plus[4])},
    {'goal': 'Prime occupancy', 'target': G_PRIME_OCC_TARGET, 'achieved': final_prime_occ, 'met': final_prime_occ >= G_PRIME_OCC_TARGET, 'weight': W[5], 'd_minus': pulp.value(d_minus[5]), 'd_plus': pulp.value(d_plus[5])},
])
GOALS['weighted_deviation'] = GOALS.apply(
    lambda row: row['weight'] * (row['d_plus'] if row['goal'] == 'Average idle minutes' else row['d_minus']),
    axis=1
)

print('Final revenue: Rs.{:,.0f}'.format(final_revenue))
print('Average occupancy: {:.1%}'.format(final_avg_occ))
print('Genres covered:', final_genres)
print('Average idle:', round(avg_idle, 1), 'minutes')
print('Max idle:', round(max_idle, 1), 'minutes')
print('Prime-time occupancy: {:.1%}'.format(final_prime_occ))
display(GOALS)
final_grid

# ── CELL 59 ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
schedule_occ = final_schedule_df.pivot(index='screen', columns='time', values='occupancy').reindex(index=SCREENS, columns=SLOT_LABELS)
sns.heatmap(schedule_occ, annot=True, fmt='.2f', cmap='YlGnBu', ax=axes[0])
axes[0].set_title('Final Schedule Occupancy')

plot_goals = GOALS.copy()
plot_goals['display_achieved'] = plot_goals.apply(lambda r: r['achieved'] * 100 if 'occupancy' in r['goal'].lower() else r['achieved'], axis=1)
plot_goals['display_target'] = plot_goals.apply(lambda r: r['target'] * 100 if 'occupancy' in r['goal'].lower() else r['target'], axis=1)
colors = ['seagreen' if met else 'tomato' for met in plot_goals['met']]
axes[1].barh(plot_goals['goal'], plot_goals['display_achieved'], color=colors)
for target in plot_goals['display_target']:
    axes[1].axvline(target, color='black', linestyle='--', alpha=0.20)
axes[1].set_title('Goal Attainment')
plt.tight_layout()
plt.show()

final_grid = final_schedule_df.pivot(index='screen', columns='time', values='title').reindex(index=SCREENS, columns=SLOT_LABELS)
final_grid

# ── CELL 62 ─────────────────────────────────────────
top5_baseline = films.sort_values('popularity_norm', ascending=False).head(5).reset_index(drop=True)
baseline_records = []
for s in SCREENS:
    for j in SLOTS:
        film_row = top5_baseline.iloc[(s + j) % len(top5_baseline)]
        affinity = GENRE_AFFINITY.get(film_row['primary_genre'], GENRE_AFFINITY['Default'])
        occ_val = min(film_row['demand'] * DEMAND_SCALE * SLOT_FACTOR[j] * affinity[j], 1.0)
        baseline_records.append({
            'screen': s,
            'slot': j,
            'time': SLOT_LABELS[j],
            'title': film_row['title'],
            'genre': film_row['primary_genre'],
            'occupancy': occ_val,
            'revenue': PRICES[j] * CAPACITIES[s] * occ_val,
        })
baseline_df = pd.DataFrame(baseline_records)
baseline_revenue = baseline_df['revenue'].sum()
baseline_genres = baseline_df['genre'].nunique()
revenue_lift = final_revenue - baseline_revenue
improvement_pct = revenue_lift / baseline_revenue * 100 if baseline_revenue else 0
genre_lift = final_genres - baseline_genres

comparison_df = pd.DataFrame({
    'Metric': ['Daily revenue', 'Average occupancy', 'Genres covered'],
    'Naive baseline': [baseline_revenue, baseline_df['occupancy'].mean(), baseline_genres],
    'Optimized schedule': [final_revenue, final_avg_occ, final_genres],
})
print('Headline: Optimized schedule produces Rs.{:,.0f} more per day, a {:.1f}% improvement, while covering {} more genres.'.format(revenue_lift, improvement_pct, genre_lift))
comparison_df

# ── CELL 64 ─────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
pd.Series({'Naive baseline': baseline_revenue/1000, 'Optimized': final_revenue/1000}).plot(kind='bar', ax=axes[0], color=['gray', 'seagreen'])
axes[0].set_title('Revenue Comparison')
axes[0].set_ylabel('Rs. thousands')
axes[0].tick_params(axis='x', rotation=15)
pd.Series({'Naive baseline': baseline_genres, 'Optimized': final_genres}).plot(kind='bar', ax=axes[1], color=['gray', 'steelblue'])
axes[1].set_title('Genre Coverage Comparison')
axes[1].set_ylabel('Number of genres')
axes[1].tick_params(axis='x', rotation=15)
plt.tight_layout()
plt.show()

# ── CELL 67 ─────────────────────────────────────────
print('Final 5 x 6 schedule grid:')
display(final_grid)
print('\nClock timing table:')
display(seq_df.sort_values(['screen', 'slot'])[['screen', 'time', 'start_time', 'title', 'runtime', 'end_with_cleanup']])
print('\nCoverage report:')
coverage_report = pd.DataFrame({
    'Item': ['Genres covered', 'Unique films scheduled', 'Languages covered', 'Protected core cells'],
    'Value': [final_genres, final_schedule_df['title'].nunique(), final_schedule_df['genre'].nunique(), len(core_df)]
})
display(coverage_report)
print('\nGoal report:')
display(GOALS)
print('\nP&L comparison:')
display(comparison_df)

# ── CELL 70 ─────────────────────────────────────────
def revenue_for_lambda(lambda_value):
    temp = films.copy()
    temp['decay_temp'] = np.exp(-lambda_value * temp['weeks_out'])
    temp['demand_temp'] = temp['popularity_norm'] * temp['decay_temp']
    total = 0
    for _, row in temp.iterrows():
        affinity = GENRE_AFFINITY.get(row['primary_genre'], GENRE_AFFINITY['Default'])
        for j in SLOTS:
            occ_val = min(row['demand_temp'] * DEMAND_SCALE * SLOT_FACTOR[j] * affinity[j], 1.0)
            for s in SCREENS:
                total += PRICES[j] * CAPACITIES[s] * occ_val
    return total

lambda_values = np.arange(0.25, 0.86, 0.10)
lambda_results = pd.DataFrame({'lambda': lambda_values, 'estimated_total_pool_revenue': [revenue_for_lambda(x) for x in lambda_values]})

budget_values = [2_500_000, 3_000_000, 3_500_000, 4_000_000, 4_500_000]
budget_results = []
for budget in budget_values:
    p = pulp.LpProblem('budget_sensitivity', pulp.LpMaximize)
    yy = pulp.LpVariable.dicts('b', range(n), cat='Binary')
    p += pulp.lpSum(films.loc[i, 'revenue_potential_score'] * yy[i] for i in range(n))
    p += pulp.lpSum(films.loc[i, 'licensing_fee'] * yy[i] for i in range(n)) <= budget
    p += pulp.lpSum(yy[i] for i in range(n)) >= 5
    p += pulp.lpSum(yy[i] for i in range(n)) <= 12
    p.solve(pulp.PULP_CBC_CMD(msg=False))
    chosen = [i for i in range(n) if pulp.value(yy[i]) > 0.5]
    budget_results.append({'budget': budget, 'selected_films': len(chosen), 'expected_revenue': sum(films.loc[i, 'revenue_potential_score'] for i in chosen)})
budget_results = pd.DataFrame(budget_results)

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
sns.lineplot(data=lambda_results, x='lambda', y='estimated_total_pool_revenue', marker='o', ax=axes[0])
axes[0].set_title('Sensitivity to Decay Rate')
axes[0].set_ylabel('Estimated revenue')
sns.lineplot(data=budget_results, x='budget', y='expected_revenue', marker='o', ax=axes[1])
axes[1].set_title('Sensitivity to Licensing Budget')
axes[1].set_ylabel('Expected selected revenue')
plt.tight_layout()
plt.show()

display(lambda_results)
display(budget_results)