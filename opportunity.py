"""Gentlest plan to beat the opportunity cost.

The `Costo de oportunidad` sheet values the alternative to the project (renting the
bodega), with present value `Costo de oportunidad!B16`. The project is only worth
doing if its VPN clears that hurdle.

This finds reasonable decision-variable values — staying within the agreed bounds
(`optimize.build_bounds`) and avoiding extreme corners — that bring VPN up to the
hurdle. Two plans are produced:

  1. Uniform-effort  : push every lever the SAME fraction λ toward its reasonable
                       limit (minimal λ s.t. VPN >= hurdle). "Reasonable for all."
  2. Minimal-effort  : minimize Σ progress² s.t. VPN >= hurdle (smallest balanced
                       changes; lets high-leverage levers carry more).

Run:  uv run python opportunity.py
"""

from __future__ import annotations

import openpyxl

from model import N_YEARS, WORKBOOK_PATH, compute_vpn, load_fixed_params
from optimize import build_bounds, vector_to_levers

LEVER_NAMES = ["%D", "Costo MP", "CXC días", "CXP días", "Crec. real"] + [
    f"Cant Año {j + 1}" for j in range(N_YEARS)
]


def read_hurdle(path: str = WORKBOOK_PATH) -> float:
    wb = openpyxl.load_workbook(path, data_only=True)
    return wb["Costo de oportunidad"]["B16"].value


def base_vector(base) -> list[float]:
    return [
        base.pct_d,
        base.costo_mp_base,
        base.cxc_dias,
        base.cxp_dias,
        base.g_real_precio,
        *base.cantidades,
    ]


def improving_targets(base_vec, bounds, fixed) -> list[float]:
    """For each dim, the bound endpoint that raises VPN (others held at base)."""
    targets = []
    for i, (lo, hi) in enumerate(bounds):
        v_lo = list(base_vec); v_lo[i] = lo
        v_hi = list(base_vec); v_hi[i] = hi
        vpn_lo = compute_vpn(vector_to_levers(v_lo), fixed)
        vpn_hi = compute_vpn(vector_to_levers(v_hi), fixed)
        targets.append(hi if vpn_hi >= vpn_lo else lo)
    return targets


def value_vector(progress, base_vec, target_vec) -> list[float]:
    """progress is a scalar λ or a per-dim list; interpolate base -> target."""
    if isinstance(progress, (int, float)):
        progress = [progress] * len(base_vec)
    return [b + p * (t - b) for b, t, p in zip(base_vec, target_vec, progress)]


def vpn_at(progress, base_vec, target_vec, fixed) -> float:
    return compute_vpn(vector_to_levers(value_vector(progress, base_vec, target_vec)), fixed)


def uniform_effort(base_vec, target_vec, fixed, hurdle, tol=1e-6) -> float:
    """Smallest shared λ in [0,1] with VPN(λ) >= hurdle (bisection; VPN monotonic in λ)."""
    lo, hi = 0.0, 1.0
    if vpn_at(hi, base_vec, target_vec, fixed) < hurdle:
        return 1.0  # infeasible even at full reasonable push
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if vpn_at(mid, base_vec, target_vec, fixed) >= hurdle:
            hi = mid
        else:
            lo = mid
    return hi


def minimal_effort(base_vec, target_vec, fixed, hurdle, seed_lambda):
    """Minimize Σ p_i^2 s.t. VPN >= hurdle, p_i in [0,1]."""
    from scipy.optimize import minimize

    n = len(base_vec)
    res = minimize(
        lambda p: float(sum(pi * pi for pi in p)),
        x0=[seed_lambda] * n,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=[{
            "type": "ineq",
            "fun": lambda p: vpn_at(list(p), base_vec, target_vec, fixed) - hurdle,
        }],
        options={"maxiter": 500, "ftol": 1e-9},
    )
    return res.x


def _fmt(i: int, v: float) -> str:
    """Format a lever value: fractions as %, money/quantities with commas, days with 1 decimal."""
    if i in (0, 4):          # %D, Crec. real -> percentage
        return f"{v:.2%}"
    if i in (1,) or i >= 5:  # Costo MP, Cantidades -> integer with commas
        return f"{v:,.0f}"
    return f"{v:,.1f}"        # CXC / CXP days


def print_plan(title, progress, base_vec, target_vec, fixed, hurdle) -> None:
    if isinstance(progress, (int, float)):
        progress = [progress] * len(base_vec)
    vals = value_vector(progress, base_vec, target_vec)
    lev = vector_to_levers(vals)
    vpn = compute_vpn(lev, fixed)
    print(f"\n=== {title} ===")
    print(f"  VPN = {vpn:,.0f}   (hurdle {hurdle:,.0f}, slack {vpn - hurdle:+,.0f})")
    print(f"  {'lever':<14}{'base':>14}{'value':>16}{'progress':>11}")
    for i, (name, b, v, p) in enumerate(zip(LEVER_NAMES, base_vec, vals, progress)):
        print(f"  {name:<14}{_fmt(i, b):>14}{_fmt(i, v):>16}{p:>10.1%}")
    print(f"  pct_e = {lev.pct_e:.2%}")


def solo_diagnostic(base_vec, target_vec, fixed, hurdle) -> None:
    """Can a single lever, alone at its reasonable limit, clear the hurdle?"""
    print("\n=== Single-lever check (only that lever at its reasonable limit) ===")
    groups = {name: [i] for i, name in enumerate(LEVER_NAMES[:5])}
    groups["Cantidades (all yrs)"] = list(range(5, 5 + N_YEARS))
    for name, idxs in groups.items():
        v = list(base_vec)
        for i in idxs:
            v[i] = target_vec[i]
        vpn = compute_vpn(vector_to_levers(v), fixed)
        mark = "clears" if vpn >= hurdle else "no"
        print(f"  {name:<22} VPN = {vpn:>18,.0f}   [{mark}]")


def main() -> None:
    fixed, base = load_fixed_params()
    hurdle = read_hurdle()
    bounds = build_bounds()
    base_vec = base_vector(base)
    target_vec = improving_targets(base_vec, bounds, fixed)

    base_vpn = compute_vpn(base, fixed)
    full_vpn = vpn_at(1.0, base_vec, target_vec, fixed)
    print(f"Opportunity cost (hurdle) = {hurdle:,.0f}")
    print(f"Base-case VPN             = {base_vpn:,.0f}   [{'clears' if base_vpn >= hurdle else 'fails'}]")
    print(f"Full reasonable push VPN  = {full_vpn:,.0f}   [{'clears' if full_vpn >= hurdle else 'fails'}]")

    if full_vpn < hurdle:
        print("\nHurdle is NOT reachable within the reasonable bounds.")
        return

    solo_diagnostic(base_vec, target_vec, fixed, hurdle)

    lam = uniform_effort(base_vec, target_vec, fixed, hurdle)
    print_plan(f"Uniform-effort plan (λ = {lam:.1%} of each lever's reasonable range)",
               lam, base_vec, target_vec, fixed, hurdle)

    p = minimal_effort(base_vec, target_vec, fixed, hurdle, seed_lambda=lam)
    print_plan("Minimal-effort plan (smallest balanced changes)",
               list(p), base_vec, target_vec, fixed, hurdle)


if __name__ == "__main__":
    main()
