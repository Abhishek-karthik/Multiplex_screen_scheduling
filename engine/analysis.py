"""LP sensitivity report in the format of a spreadsheet Solver report (shadow prices, reduced costs, ranging).

The ranges are computed exactly from the LP optimality conditions, not by trial re-solves:

* Objective-coefficient range of variable k: the interval of c_k for which the CURRENT solution x* stays optimal.
  x* is optimal iff some dual solution satisfies complementary slackness with it, so the range end-points are
  max / min of t over (duals, t) with c_k replaced by c_k + t.
* Right-hand-side range of constraint r: the interval of b_r for which the CURRENT shadow prices stay valid,
  i.e. some primal solution satisfies complementary slackness with the current duals: max / min of δ over (x, δ).

Each range is therefore two small LPs, solved with HiGHS through scipy.
"""
import numpy as np
import pandas as pd
import pulp
from scipy.optimize import linprog

_TOL = 1e-7


def _lp_matrices(prob):
    variables = prob.variables()
    pos = {v.name: k for k, v in enumerate(variables)}
    n = len(variables)
    sense = 1 if prob.sense == pulp.LpMinimize else -1
    c = np.zeros(n)
    for v, coef in prob.objective.items():
        c[pos[v.name]] = coef
    rows = []
    for name, con in prob.constraints.items():
        a = np.zeros(n)
        for v, coef in con.items():
            a[pos[v.name]] = coef
        rows.append((name, a, -con.constant, con.sense))
    bounds = [(-np.inf if v.lowBound is None else v.lowBound, np.inf if v.upBound is None else v.upBound) for v in variables]
    return variables, sense, c, rows, bounds


def _t_range(nv, A_ub, b_ub, A_eq, b_eq, bounds):
    # (max t, min t) where t is the LAST of nv variables, subject to the given linear system.
    kw = dict(A_ub=np.array(A_ub) if A_ub else None, b_ub=np.array(b_ub) if b_ub else None,
              A_eq=np.array(A_eq) if A_eq else None, b_eq=np.array(b_eq) if b_eq else None, bounds=bounds, method='highs')
    obj = np.zeros(nv)
    obj[-1] = -1.0
    hi = linprog(obj, **kw)                                  # min -t  -> max t
    obj[-1] = 1.0
    lo = linprog(obj, **kw)                                  # min t
    t_max = np.inf if hi.status == 3 else (-hi.fun if hi.status == 0 else np.nan)
    t_min = -np.inf if lo.status == 3 else (lo.fun if lo.status == 0 else np.nan)
    return t_max, t_min


def lp_sensitivity_report(prob, var_labels=None, con_labels=None):
    # prob: a PuLP LP (continuous variables only). Returns the two report tables and the objective.
    if any(v.cat != pulp.LpContinuous for v in prob.variables()):
        raise ValueError('sensitivity reports are defined for LPs; solve the LP relaxation instead')
    variables, sense, c, rows, bounds = _lp_matrices(prob)
    n = len(variables)
    ct = sense * c                                            # everything below works on: min ct·x
    ub_rows = [(k, r) for k, r in enumerate(rows) if r[3] != pulp.LpConstraintEQ]
    eq_rows = [(k, r) for k, r in enumerate(rows) if r[3] == pulp.LpConstraintEQ]
    sgn_ub = np.array([1.0 if r[3] == pulp.LpConstraintLE else -1.0 for _, r in ub_rows])   # store ≥ rows as -a·x ≤ -b
    G = np.array([s * r[1] for s, (_, r) in zip(sgn_ub, ub_rows)]).reshape(-1, n)
    h = np.array([s * r[2] for s, (_, r) in zip(sgn_ub, ub_rows)])
    E = np.array([r[1] for _, r in eq_rows]).reshape(-1, n)
    e = np.array([r[2] for _, r in eq_rows])
    m_ub, m_eq = len(h), len(e)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    scale = max(1.0, float(np.abs(ct).max(initial=1.0)))

    # The report must describe THE solution the model uses: LPs often have several optimal solutions, so take the
    # solver's values from the PuLP problem when it has been solved, and re-solve only if it has not.
    x = np.array([v.varValue if v.varValue is not None else np.nan for v in variables], dtype=float)
    if np.isnan(x).any():
        lp = linprog(ct, A_ub=G if m_ub else None, b_ub=h if m_ub else None, A_eq=E if m_eq else None,
                     b_eq=e if m_eq else None, bounds=bounds, method='highs')
        if lp.status != 0:
            raise ValueError(f'LP not solved to optimality: {lp.message}')
        x = lp.x

    at_lo = np.isfinite(lo) & (np.abs(x - np.where(np.isfinite(lo), lo, 0)) <= 1e-7 * np.maximum(1, np.abs(np.nan_to_num(lo))))
    at_hi = np.isfinite(hi) & (np.abs(x - np.where(np.isfinite(hi), hi, 0)) <= 1e-7 * np.maximum(1, np.abs(np.nan_to_num(hi, posinf=0))))
    fixed = at_lo & at_hi
    tight = np.abs(h - G @ x) <= 1e-7 * np.maximum(1.0, np.abs(h)) if m_ub else np.zeros(0, dtype=bool)

    def dual_system(k=None):
        # Optimality conditions of x* as a linear system in (lam, mu, t), with t added to ct_k (t unused if k is None):
        # d_j(t) = ct_j + t*[j=k] - G_j·lam - E_j·mu  must be ≥ 0 at a lower bound, ≤ 0 at an upper bound, = 0 between.
        A_ub_r, b_ub_r, A_eq_r, b_eq_r = [], [], [], []
        for j in range(n):
            if fixed[j]:
                continue
            row = np.concatenate([-G[:, j], -E[:, j], [1.0 if j == k else 0.0]])
            if at_lo[j]:
                A_ub_r.append(-row); b_ub_r.append(ct[j])
            elif at_hi[j]:
                A_ub_r.append(row); b_ub_r.append(-ct[j])
            else:
                A_eq_r.append(row); b_eq_r.append(-ct[j])
        bnds = [(-np.inf, 0.0) if tight[i] else (0.0, 0.0) for i in range(m_ub)] + [(None, None)] * m_eq
        bnds.append((None, None) if k is not None else (0.0, 0.0))
        return A_ub_r, b_ub_r, A_eq_r, b_eq_r, bnds

    def kkt_ok(lam_c, mu_c):
        if m_ub and (lam_c > 1e-7 * scale).any():
            return False
        if m_ub and (np.abs(lam_c[~tight]) > 1e-7 * scale).any():
            return False
        d_c = ct - G.T @ lam_c - E.T @ mu_c
        tol = 1e-6 * scale
        free = ~at_lo & ~at_hi
        return bool((d_c[at_lo & ~at_hi] >= -tol).all() and (d_c[at_hi & ~at_lo] <= tol).all() and (np.abs(d_c[free]) <= tol).all())

    # Shadow prices: the solver's own duals if they are optimal for x* (they match the notebook's MODI potentials);
    # otherwise any dual solution that satisfies the optimality conditions of x*.
    lam = mu = None
    pis = [prob.constraints[name].pi for name, *_ in rows]
    if all(p is not None for p in pis):
        pis = np.array(pis, dtype=float)
        for flip in (1.0, -1.0):
            lam_c = np.array([flip * sense * pis[k] * s for s, (k, _) in zip(sgn_ub, ub_rows)])
            mu_c = np.array([flip * sense * pis[k] for k, _ in eq_rows])
            if kkt_ok(lam_c, mu_c):
                lam, mu = lam_c, mu_c
                break
    if lam is None:
        A_ub_r, b_ub_r, A_eq_r, b_eq_r, bnds = dual_system()
        res = linprog(np.zeros(m_ub + m_eq + 1), A_ub=np.array(A_ub_r) if A_ub_r else None, b_ub=np.array(b_ub_r) if b_ub_r else None,
                      A_eq=np.array(A_eq_r) if A_eq_r else None, b_eq=np.array(b_eq_r) if b_eq_r else None, bounds=bnds, method='highs')
        if res.status != 0:
            raise ValueError('the given solution is not optimal for this LP')
        lam, mu = res.x[:m_ub], res.x[m_ub:m_ub + m_eq]
    d = ct - G.T @ lam - E.T @ mu                             # reduced costs (min form)

    def cost_range(k):
        return _t_range(m_ub + m_eq + 1, *dual_system(k))

    def rhs_range(k_row):
        # variables (x, delta): the original row k_row becomes a·x (sense) b + delta
        A_ub_r, b_ub_r, A_eq_r, b_eq_r = [], [], [], []
        for idx, (k, _) in enumerate(ub_rows):
            row = np.concatenate([G[idx], [-sgn_ub[idx] if k == k_row else 0.0]])
            if abs(lam[idx]) > _TOL * scale:                      # nonzero shadow price -> the row must stay tight
                A_eq_r.append(row); b_eq_r.append(h[idx])
            else:
                A_ub_r.append(row); b_ub_r.append(h[idx])
        for idx, (k, _) in enumerate(eq_rows):
            A_eq_r.append(np.concatenate([E[idx], [-1.0 if k == k_row else 0.0]])); b_eq_r.append(e[idx])
        bnds = []
        for j in range(n):
            if d[j] > _TOL * scale and np.isfinite(lo[j]):
                bnds.append((lo[j], lo[j]))                       # positive reduced cost -> stays at lower bound
            elif d[j] < -_TOL * scale and np.isfinite(hi[j]):
                bnds.append((hi[j], hi[j]))                       # negative reduced cost -> stays at upper bound
            else:
                bnds.append(bounds[j])
        bnds.append((None, None))
        return _t_range(n + 1, A_ub_r, b_ub_r, A_eq_r, b_eq_r, bnds)

    var_labels, con_labels = var_labels or {}, con_labels or {}
    tidy = lambda v: 0.0 if abs(v) < 1e-9 else float(v)
    tidy_cost = lambda v: 0.0 if abs(v) < 1e-7 * scale else float(v)   # cost-unit columns: solver noise -> exact zero
    vrows = []
    for k, v in enumerate(variables):
        t_max, t_min = cost_range(k)
        # min form: ct_k may move in [ct_k + t_min, ct_k + t_max]; for a maximisation c = -ct
        inc, dec = (t_max, -t_min) if sense == 1 else (-t_min, t_max)
        vrows.append({'variable': var_labels.get(v.name, v.name), 'final value': tidy(x[k]),
                      'reduced cost': tidy_cost(sense * d[k]), 'objective coefficient': float(c[k]),
                      'allowable increase': tidy_cost(inc), 'allowable decrease': tidy_cost(dec)})
    lam_of = {k: lam[idx] * sgn_ub[idx] for idx, (k, _) in enumerate(ub_rows)}   # ∂(min obj)/∂b in original row form
    mu_of = {k: mu[idx] for idx, (k, _) in enumerate(eq_rows)}
    crows = []
    for k, (name, a, b, sns) in enumerate(rows):
        dual_min_form = lam_of[k] if k in lam_of else mu_of[k]
        d_max, d_min = rhs_range(k)
        crows.append({'constraint': con_labels.get(name, name), 'final value': tidy(a @ x),
                      'sense': {pulp.LpConstraintLE: '≤', pulp.LpConstraintGE: '≥', pulp.LpConstraintEQ: '='}[sns],
                      'shadow price': tidy(sense * dual_min_form), 'right-hand side': float(b),
                      'allowable increase': tidy(d_max), 'allowable decrease': tidy(-d_min)})
    return {
        'objective': float(c @ x) + float(prob.objective.constant or 0.0),
        'variables': pd.DataFrame(vrows),
        'constraints': pd.DataFrame(crows),
        'x': dict(zip([v.name for v in variables], x)),
    }
