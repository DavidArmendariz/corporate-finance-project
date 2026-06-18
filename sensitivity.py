"""Sensitivity analysis for "VPN del Proyecto".

Computes how much VPN changes per one-unit change in each decision variable,
measured at the base case via central finite differences (local slope ∂VPN/∂x).

Run:  uv run python sensitivity.py
"""

from __future__ import annotations

from dataclasses import replace

from model import FixedParams, Levers, compute_vpn, load_fixed_params


def _slope(make_levers, x: float, h: float, fixed: FixedParams) -> float:
    """Central finite difference d(VPN)/dx at x with step h."""
    up = compute_vpn(make_levers(x + h), fixed)
    dn = compute_vpn(make_levers(x - h), fixed)
    return (up - dn) / (2 * h)


def scalar_sensitivities(base: Levers, fixed: FixedParams):
    """Per-unit slopes for the scalar levers. Returns list of dicts.

    `unit_scale` converts the raw derivative (per 1.0 of the variable) into the
    reported per-unit figure: 0.01 for fractions (per 1pp), 1.0 otherwise.
    `step` is a tangible move used for cross-lever comparison in the tornado.
    """
    specs = [
        # name, unit label, setter, current value, h, unit_scale, practical step (in reported units)
        ("%D", "per +1pp",
         lambda v: replace(base, pct_d=v, pct_e=1 - v), base.pct_d, 1e-4, 0.01, 1.0),
        ("Costo MP base", "per +1 COP/ton",
         lambda v: replace(base, costo_mp_base=v), base.costo_mp_base, 1.0, 1.0, 100_000.0),
        ("CXC días", "per +1 day",
         lambda v: replace(base, cxc_dias=v), base.cxc_dias, 1e-3, 1.0, 1.0),
        ("CXP días", "per +1 day",
         lambda v: replace(base, cxp_dias=v), base.cxp_dias, 1e-3, 1.0, 1.0),
        ("Crec. real precio", "per +1pp",
         lambda v: replace(base, g_real_precio=v), base.g_real_precio, 1e-5, 0.01, 1.0),
    ]
    rows = []
    for name, unit, setter, x, h, scale, step in specs:
        d_per_unit = _slope(setter, x, h, fixed) * scale
        step_label = {0.01: "+1pp"}.get(scale)
        if step_label is None:
            step_label = f"+{step:,.0f}"
        rows.append({
            "name": name,
            "unit": unit,
            "per_unit": d_per_unit,
            "step_label": step_label,
            "step_impact": d_per_unit * (step if scale == 1.0 else 1.0),
        })
    return rows


def cantidades_sensitivities(base: Levers, fixed: FixedParams):
    """Per-year ∂VPN per +1 ton for each Año 1..10."""
    rows = []
    h = 1e-3
    for j in range(len(base.cantidades)):
        def setter(v, j=j):
            new = list(base.cantidades)
            new[j] = v
            return replace(base, cantidades=new)

        d = _slope(setter, base.cantidades[j], h, fixed)
        rows.append({
            "name": f"Cantidades Año {j + 1}",
            "unit": "per +1 ton",
            "per_unit": d,
            "step_label": "+100 tons",
            "step_impact": d * 100,
        })
    return rows


def report(base: Levers, fixed: FixedParams) -> None:
    base_vpn = compute_vpn(base, fixed)
    scalars = scalar_sensitivities(base, fixed)
    cantidades = cantidades_sensitivities(base, fixed)

    print(f"Base-case VPN = {base_vpn:,.2f}\n")

    print("=== Per-unit VPN sensitivity (scalar levers) ===")
    print(f"{'Variable':<20}{'unit':<16}{'ΔVPN / unit':>22}{'ΔVPN (practical step)':>28}")
    for r in scalars:
        step = f"{r['step_label']}: {r['step_impact']:>+,.0f}"
        print(f"{r['name']:<20}{r['unit']:<16}{r['per_unit']:>22,.2f}{step:>28}")

    print("\n=== Cantidades, per year (ΔVPN per +1 ton) ===")
    print(f"{'Variable':<20}{'unit':<16}{'ΔVPN / unit':>22}{'ΔVPN (+100 tons)':>28}")
    for r in cantidades:
        step = f"{r['step_impact']:>+,.0f}"
        print(f"{r['name']:<20}{r['unit']:<16}{r['per_unit']:>22,.2f}{step:>28}")

    print("\n=== Tornado: levers ranked by |impact| of a practical step ===")
    ranked = sorted(scalars + cantidades, key=lambda r: abs(r["step_impact"]), reverse=True)
    for r in ranked:
        print(f"  {r['name']:<22}{r['step_label']:<12}ΔVPN = {r['step_impact']:>+,.0f}")


if __name__ == "__main__":
    fixed, base = load_fixed_params()
    report(base, fixed)
