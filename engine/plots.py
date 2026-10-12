"""Matplotlib figures used by the notebook (the app draws the same views with Plotly)."""
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from .metrics import minutes_to_clock, n_screens

GENRE_COLOURS = {}


def genre_colour(g):
    if g not in GENRE_COLOURS:
        GENRE_COLOURS[g] = plt.cm.tab20(len(GENRE_COLOURS) % 20)
    return GENRE_COLOURS[g]


def plot_gantt(sched, cfg, title, ax=None, save=None):
    # One bar per show (runtime) plus a hatched cleanup block; colour = genre.
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(14, 4.2))
    for _, r in sched.iterrows():
        ax.barh(r['screen'], r['runtime'], left=r['start_min'], color=genre_colour(r['genre']), edgecolor='white', height=0.62)
        ax.barh(r['screen'], cfg['cleanup'], left=r['start_min'] + r['runtime'], color='lightgrey', hatch='///', edgecolor='white', height=0.62)
        label = r['title'] if len(r['title']) <= 22 else r['title'][:21] + '…'
        ax.text(r['start_min'] + r['runtime'] / 2, r['screen'], label, ha='center', va='center', fontsize=6.3, color='black')
    ax.set_yticks(range(n_screens(cfg)))
    ax.set_yticklabels([f'Screen {s} ({c})' for s, c in enumerate(cfg['capacities'])])
    ax.invert_yaxis()
    ticks = list(cfg['slot_start_min']) + [cfg['slot_start_min'][-1] + cfg['slot_length']]
    ax.set_xticks(ticks)
    ax.set_xticklabels([minutes_to_clock(t) for t in ticks])
    ax.set_xlim(ticks[0] - 10, ticks[-1] + 10)
    for t in ticks:
        ax.axvline(t, color='grey', lw=0.6, ls=':')
    handles = [mpatches.Patch(color=genre_colour(g), label=g) for g in sorted(sched['genre'].unique())]
    handles.append(mpatches.Patch(facecolor='lightgrey', hatch='///', label=f"cleanup ({cfg['cleanup']} min)"))
    ax.legend(handles=handles, bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=8)
    ax.set_title(title, fontweight='bold')
    if own:
        plt.tight_layout()
        if save:
            plt.savefig(save, dpi=150, bbox_inches='tight')
        plt.show()
