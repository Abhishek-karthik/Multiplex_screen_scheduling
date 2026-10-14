"""Analytic Hierarchy Process (AHP): priority weights from pairwise comparisons, with a consistency check."""
import numpy as np
import pandas as pd

# Saaty's random consistency index RI(n)
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
SAATY_SCALE = [1 / 9, 1 / 8, 1 / 7, 1 / 6, 1 / 5, 1 / 4, 1 / 3, 1 / 2, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def judgments_to_matrix(items, judgments):
    # judgments: iterable of (a, b, v) meaning "a is v times as important as b" (Saaty 1-9).
    # Missing pairs default to 1 (equal importance); the matrix is reciprocal by construction.
    n = len(items)
    pos = {g: k for k, g in enumerate(items)}
    A = np.ones((n, n))
    for a, b, v in judgments:
        i, j = pos[a], pos[b]
        A[i, j], A[j, i] = float(v), 1.0 / float(v)
    return pd.DataFrame(A, index=items, columns=items)


def ahp_weights(matrix):
    # Principal-eigenvector priorities, lambda_max, CI = (lambda_max - n)/(n - 1), CR = CI / RI(n).
    A = matrix.to_numpy(dtype=float) if isinstance(matrix, pd.DataFrame) else np.asarray(matrix, dtype=float)
    items = list(matrix.index) if isinstance(matrix, pd.DataFrame) else list(range(len(A)))
    n = len(A)
    vals, vecs = np.linalg.eig(A)
    k = int(np.argmax(vals.real))
    w = np.abs(vecs[:, k].real)
    w = w / w.sum()
    lam = float(vals[k].real)
    ci = (lam - n) / (n - 1) if n > 2 else 0.0
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = ci / ri if ri > 0 else 0.0
    return {
        'weights': dict(zip(items, w)),
        'lambda_max': lam,
        'CI': ci,
        'RI': ri,
        'CR': cr,
        'consistent': cr < 0.10,
        'matrix': pd.DataFrame(A, index=items, columns=items),
    }
