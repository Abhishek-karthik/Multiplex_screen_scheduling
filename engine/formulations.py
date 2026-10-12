"""Mathematical formulations of the four models (Markdown + LaTeX), shown on the app's model pages."""

DEMAND = r"""
$$D_{ij} = \text{DEMAND\_SCALE}\cdot e_i \cdot \sigma_j \cdot \alpha_{g(i),j}, \qquad e_i = \text{popularity\_norm}_i \cdot e^{-\lambda\,\text{weeks\_out}_i}$$

| Quantity | Formula | Meaning |
|---|---|---|
| attendance | $att_{ijs} = \min(D_{ij}, C_s)$ | seats sold if film $i$ plays slot $j$ on screen $s$ |
| occupancy | $occ_{ijs} = att_{ijs} / C_s$ | depends on the screen size |
| revenue | $rev_{ijs} = P_j \cdot att_{ijs}$ | ticket revenue of that show |
| spill | $spill_{ijs} = \max(D_{ij} - C_s, 0)$ | people turned away |
"""

M1 = r"""
**Decision:** $y_i \in \{0,1\}$ — license film $i$ this week.

$$\max \sum_i v_i\, y_i, \qquad v_i = \sum_j P_j \min(D_{ij}, C_{ref})\ \ \text{(daily revenue potential)}$$

| # | Constraint | Meaning |
|---|---|---|
| K1 | $\sum_i f_i\, y_i \le \text{BUDGET}$ | weekly licensing budget |
| K2 | $N_{min} \le \sum_i y_i \le N_{max}$ | variety policy: number of films |
| K3 | $\sum_{i \in \text{Action-like}} y_i \ge 1$ | content coverage |
| K4 | $\sum_{i \in \text{Family}} y_i \ge 1$ | content coverage |
| K5 | $\sum_{i \in \text{Regional}} y_i \ge 1$ | only if such a film exists |
| K6 | $y_i = 0$ if $L_i + B > \Lambda$ | a film that cannot fit any slot is never licensed |

Fee (weekly minimum guarantee): $f_i = \text{FEE\_FLOOR} + \text{FEE\_PREMIUM}\cdot e_i$.
"""

M2 = r"""
**Unit of flow:** one show-slot. Each screen supplies $|T| = 6$ show-slots; each licensed genre demands a quota $b_g$.

$$\min \sum_s\sum_g c_{sg}\,x_{sg} \quad \text{s.t.} \quad \sum_g x_{sg} = 6\ \ \forall s, \qquad \sum_s x_{sg} = b_g\ \ \forall g, \qquad x_{sg}\ge 0$$

$$c_{sg} = \underset{i\in g,\ j}{\text{mean}}\Big[P_j \max(D_{ij}-C_s,0) + h\,\max(C_s-D_{ij},0)\Big]$$

The first term is lost tickets (spill), the second is empty seats ($h$ = cost of one empty seat in one show).
Quota $b_g$: each licensed film gets shows in proportion to its demand, clipped to $[1, K_{max}]$; $b_g$ sums its films.
The constraint matrix is **totally unimodular**, so the LP optimum is integral without integer constraints.
"""

M3 = r"""
**Decision:** $a_{ijs} \in \{0,1\}$ — licensed film $i$ plays slot $j$ on screen $s$.

$$\max\; R = \sum_{i\in F_L}\sum_j\sum_s rev_{ijs}\; a_{ijs}$$

| # | Constraint | Meaning |
|---|---|---|
| C1 | $\sum_i a_{ijs} \le 1 \quad \forall j,s$ | at most one film per screen-slot |
| C2 | $\sum_s a_{ijs} \le 1 \quad \forall i,j$ | no simultaneous duplicate shows |
| C3 | $a_{ijs} = 0$ if $L_i + B > \Lambda$ | runtime + cleanup must fit the slot |
| C4 | $\sum_{j,s} a_{ijs} \le K_{max} \quad \forall i$ | maximum showings per film |
| C5 | $\sum_{j,s} a_{ijs} \ge 1 \quad \forall i \in F_L$ | every licensed film is shown |
| C6 | $\sum_{i,s} a_{ijs} \ge M_{min} \quad \forall j$ | minimum operating screens per slot |
| C7 | $\sum_{i:\,g(i)=g^*(s)}\sum_j a_{ijs} \ge 1 \quad \forall s$ | each screen shows its Model 2 preferred genre |
"""

M4 = r"""
**Hard constraints:** C1–C7 of Model 3. **Variables:** $a_{ijs}$, $z_g \in\{0,1\}$ (genre $g$ in prime time), deviations $d_k^-, d_k^+ \ge 0$.

| Goal | Goal constraint (normalised) | Penalise |
|---|---|---|
| G1 Revenue | $\sum rev\cdot a\,/\,R^* + d_1^- - d_1^+ = 1$ | $d_1^-$ |
| G2 Average occupancy | $\sum (occ-\tau_{occ})\,a\,/\,30 + d_2^- - d_2^+ = 0$ | $d_2^-$ |
| G3 Prime-time variety | $\sum_g z_g/\tau_{div} + d_3^- - d_3^+ = 1$ | $d_3^-$ |
| G4 Idle time | $(30\Lambda - \sum (L_i+B)\,a)/(30\,\tau_{idle}) + d_4^- - d_4^+ = 1$ | $d_4^+$ |
| G5 Prime-time occupancy | $\sum_{j\in prime}(occ-\tau_{prime})\,a\,/\,10 + d_5^- - d_5^+ = 0$ | $d_5^-$ |
| G6 Capacity plan | $\sum_{i\in g}\sum_j a_{ijs} - x_{sg} = e^+_{sg} - e^-_{sg}$, $dev_6 = \sum(e^++e^-)/30$ | $dev_6$ |

$$\min\; w_1 d_1^- + w_2 d_2^- + w_3 d_3^- + w_4 d_4^+ + w_5 d_5^- + w_6\, dev_6$$

Targets: G1 $= R^*$ (Model 3); G2–G5 one declared step better than Model 3; G6 = follow Model 2's $x_{sg}$ exactly.
Weights: from AHP pairwise comparisons (consistency ratio < 0.10), or set manually.
"""

AHP = r"""
For $n$ goals, the manager fills a reciprocal matrix $A$ with $a_{kl}$ = how many times goal $k$ is more important than goal $l$
(Saaty 1–9 scale, $a_{lk} = 1/a_{kl}$). Weights = principal eigenvector of $A$ (normalised);
$CI = (\lambda_{max} - n)/(n-1)$, $CR = CI / RI(n)$ with $RI(6) = 1.24$. The judgments are acceptable if $CR < 0.10$.
"""
