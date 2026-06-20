"""Solver scaffold for maximizing "VPN del Proyecto".

SCAFFOLD ONLY — this is not executed yet. It documents the decision vector,
the objective, and the constraints so the optimization step can be run later.

Decision vector (17 dims):
    [pct_d, costo_mp_base, cxc_dias, cxp_dias, g_real_precio,
     pct_comisiones, pct_seguro, q1..q10]

Note pct_e is NOT a free variable: the constraint %E + %D == 1 is enforced by
construction (pct_e = 1 - pct_d), which removes the equality constraint entirely.

Constraints the user has stated so far:
    - %E + %D == 1, with 0 < %D < 1                     (handled by pct_e = 1 - pct_d)
    - cantidades[0] (Año 1)      <= 1500
    - cantidades[1..9] (Año 2+)  <= 5000
    - all cantidades >= 0

TODO (user to refine — "restrictions we solve last"):
    - sensible day ranges for CXC / CXP
    - floor on costo_mp_base
    - cap/floor on g_real_precio
    - any monotonicity or ramp constraints on cantidades

To run this you must add `scipy` to the project deps:
    uv add scipy
"""

from __future__ import annotations

from model import Levers, compute_vpn, load_fixed_params, N_YEARS

# Indices into the decision vector
I_PCT_D = 0
I_COSTO_MP = 1
I_CXC = 2
I_CXP = 3
I_G_PRECIO = 4
I_COMIS = 5
I_SEGURO = 6
I_CANT0 = 7  # cantidades start here; 10 values follow


def vector_to_levers(x) -> Levers:
    pct_d = x[I_PCT_D]
    return Levers(
        pct_e=1.0 - pct_d,
        pct_d=pct_d,
        costo_mp_base=x[I_COSTO_MP],
        cxc_dias=x[I_CXC],
        cxp_dias=x[I_CXP],
        g_real_precio=x[I_G_PRECIO],
        pct_comisiones=x[I_COMIS],
        pct_seguro=x[I_SEGURO],
        cantidades=list(x[I_CANT0 : I_CANT0 + N_YEARS]),
    )


def make_objective(fixed):
    # Minimize the negative VPN == maximize VPN.
    def neg_vpn(x):
        return -compute_vpn(vector_to_levers(x), fixed)

    return neg_vpn


def build_bounds():
    """Bounds matching the user's stated business constraints."""
    bounds = [
        (0.001, 0.80),          # pct_d  (up to the chosen 80% debt structure)
        (1_600_000, 2_000_000), # costo_mp_base: floor -20%, cannot exceed base
        (30.0, 95.0),           # cxc_dias: min 30 days, cannot exceed base 95
        (20.0, 90.0),           # cxp_dias: from base 20 up to max 90
        (0.035, 0.06),          # g_real_precio: from base 3.5% up to 6%
        (0.01, 0.03),           # pct_comisiones: base 2%, range 1%–3%
        (0.05, 0.15),           # pct_seguro: base 10%, range 5%–15%
    ]
    # Cantidades: Año 1 <= 1500; Año 2..10 <= 5000; all >= 0
    bounds.append((0.0, 1500.0))
    bounds.extend([(0.0, 5000.0)] * (N_YEARS - 1))
    return bounds


def _print_levers(best: Levers, fixed) -> None:
    from model import compute_model

    res = compute_model(best, fixed)
    print(f"  VPN           = {res.vpn:,.2f}")
    print(f"  WACC          = {res.wacc:.4%}")
    print(f"  pct_e         = {best.pct_e:.4f}")
    print(f"  pct_d         = {best.pct_d:.4f}")
    print(f"  costo_mp_base = {best.costo_mp_base:,.2f}")
    print(f"  cxc_dias      = {best.cxc_dias:.2f}")
    print(f"  cxp_dias      = {best.cxp_dias:.2f}")
    print(f"  g_real_precio = {best.g_real_precio:.4%}")
    print(f"  pct_comisiones= {best.pct_comisiones:.4%}")
    print(f"  pct_seguro    = {best.pct_seguro:.4%}")
    print(f"  cantidades    = {[round(float(q), 1) for q in best.cantidades]}")


def optimal_levers(fixed) -> Levers:
    """Maximize VPN within build_bounds() and return the optimal Levers.

    differential_evolution is gradient-free and scale-robust, so it handles the very
    different lever magnitudes (1e6 vs 1e1 vs 1e-2 vs 1e3) that defeat SLSQP. We then
    polish the global result with a local gradient method.
    """
    from scipy.optimize import differential_evolution, minimize

    bounds = build_bounds()
    objective = make_objective(fixed)

    de = differential_evolution(
        objective, bounds=bounds, seed=42, tol=1e-10, maxiter=2000, polish=True,
    )
    # Extra local polish from the DE optimum (L-BFGS-B respects bounds well here).
    local = minimize(objective, x0=de.x, method="L-BFGS-B", bounds=bounds,
                     options={"maxiter": 5000, "ftol": 1e-12})
    best_x = local.x if -local.fun > -de.fun else de.x
    return vector_to_levers(best_x)


def solve():
    fixed, base = load_fixed_params()
    base_vpn = compute_vpn(base, fixed)
    best = optimal_levers(fixed)

    print(f"=== Base case ===\n  VPN = {base_vpn:,.2f}\n")
    print("=== Optimized ===")
    _print_levers(best, fixed)
    print(f"\n  VPN improvement = {compute_vpn(best, fixed) - base_vpn:,.2f}")

    sweep_pct_d(best, fixed)
    return best


def sweep_pct_d(best: Levers, fixed) -> None:
    """Show the %D tradeoff (WACC vs the KTNO tax effect) at the optimal other levers."""
    from dataclasses import replace

    from model import compute_model

    print("\n=== %D sweep (other levers held at optimum) ===")
    print("  pct_d    WACC        VPN")
    for pct_d in [0.001, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]:
        lev = replace(best, pct_d=pct_d, pct_e=1 - pct_d)
        r = compute_model(lev, fixed)
        print(f"  {pct_d:<6.3f}  {r.wacc:7.4%}   {r.vpn:>18,.2f}")


if __name__ == "__main__":
    solve()
