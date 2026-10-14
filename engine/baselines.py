"""Benchmark schedules: B1 naive popularity (first-review baseline) and B2 greedy manager."""
import math

from .metrics import make_schedule, n_screens, n_slots


def baseline_naive(films, dem, cfg):
    # B1: top films by raw popularity among schedulable candidates, round-robin.
    S, T = n_screens(cfg), n_slots(cfg)
    n_b = math.ceil(S * T / cfg['k_max'])                       # 6 films are needed to fill 30 cells with ≤ 5 shows each
    top = films[films['fits']].sort_values('popularity', ascending=False).index[:n_b].tolist()
    cells = [(top[(s + j) % len(top)], j, s) for j in range(T) for s in range(S)]
    seen, kept = {}, []
    for i, j, s in cells:                                        # safety: never exceed K_MAX (relevant only for tiny pools)
        if seen.get(i, 0) < cfg['k_max']:
            kept.append((i, j, s))
            seen[i] = seen.get(i, 0) + 1
    return top, make_schedule(kept, films, dem, cfg)


def baseline_greedy(films, lic, dem, cfg):
    # B2: greedy by cell revenue over the Model 1 licensed set, respecting C1-C6, then repair C5.
    S, T = n_screens(cfg), n_slots(cfg)
    options = sorted(((dem['rev'][i, j, s], i, j, s) for i in lic for j in range(T) for s in range(S)
                      if films.at[i, 'runtime'] + cfg['cleanup'] <= cfg['slot_length']), reverse=True)
    cell_film, shows, in_slot = {}, {i: 0 for i in lic}, set()
    for r, i, j, s in options:
        if (j, s) not in cell_film and (i, j) not in in_slot and shows[i] < cfg['k_max']:
            cell_film[(j, s)] = i
            in_slot.add((i, j))
            shows[i] += 1
    for i in [i for i in lic if shows[i] == 0]:                  # repair C5: give every licensed film one show
        swaps = sorted(((dem['rev'][f, j, s] - dem['rev'][i, j, s], j, s) for (j, s), f in cell_film.items()
                        if shows[f] > 1 and (i, j) not in in_slot))
        if swaps:
            _, j, s = swaps[0]
            f = cell_film[(j, s)]
            shows[f] -= 1
            in_slot.discard((f, j))
            cell_film[(j, s)] = i
            shows[i] += 1
            in_slot.add((i, j))

    def n_in(j):
        return sum(1 for (jj, _) in cell_film if jj == j)

    for j in range(T):                                            # repair C6: open screens in under-staffed slots
        while n_in(j) < cfg['m_min']:
            best = None
            for s in [s for s in range(S) if (j, s) not in cell_film]:
                for i in [i for i in lic if (i, j) not in in_slot]:
                    if shows[i] < cfg['k_max']:
                        cand = (dem['rev'][i, j, s], i, s, None)
                    else:                                         # film at K_MAX: move its weakest show from a slot with spare screens
                        moves = [(dem['rev'][i, j2, s2], j2, s2) for (j2, s2), f in cell_film.items()
                                 if f == i and n_in(j2) > cfg['m_min']]
                        if not moves:
                            continue
                        loss, j2, s2 = min(moves)
                        cand = (dem['rev'][i, j, s] - loss, i, s, (j2, s2))
                    if best is None or cand[0] > best[0]:
                        best = cand
            if best is None:
                break
            _, i, s, moved = best
            if moved:
                del cell_film[moved]
                in_slot.discard((i, moved[0]))
                shows[i] -= 1
            cell_film[(j, s)] = i
            in_slot.add((i, j))
            shows[i] += 1
    return make_schedule([(i, j, s) for (j, s), i in cell_film.items()], films, dem, cfg)
