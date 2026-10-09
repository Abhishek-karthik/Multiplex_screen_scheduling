# Multiplex Screen Scheduling – Operations Research Project

A four-model OR pipeline for multiplex screen scheduling and revenue management, built on the TMDB 5000 Movie Dataset with a transparent synthetic theatre configuration.

## Models
1. **Knapsack (0/1 ILP)** – select films to license within a budget
2. **Transportation problem** – allocate screen seat capacity to genres
3. **Assignment problem (ILP)** – place films into the 5 screens x 6 timeslots grid
4. **Goal programming (MILP)** – reconcile revenue, occupancy, genre diversity, idle time and prime-time targets

Followed by a baseline comparison and sensitivity analysis (decay rate and licensing budget).

## Files
- `multiplex_screen_scheduling.ipynb` – main notebook
- `tmdb_5000_movies.csv` – dataset
- `weekly_candidate_pool.csv` – candidate films for the selected week
- `gantt_chart.png` – schedule Gantt chart
- `ppt_or.pptx` – presentation

## Dataset
TMDB 5000 Movie Dataset (Kaggle): https://www.kaggle.com/datasets/tmdb/tmdb-movie-metadata

## How to run
```bash
pip install pandas numpy matplotlib seaborn pulp scipy
jupyter notebook multiplex_screen_scheduling.ipynb
```
Then run all cells. `weekly_market_synthesized.csv` is regenerated automatically.
