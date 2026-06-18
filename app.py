"""Interactive explorer for VPN del Proyecto.

Move the decision-variable sliders and watch VPN, the opportunity-cost hurdle,
the cash-flow stream, and a live sensitivity tornado update.

Run:  uv run streamlit run app.py
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from model import N_YEARS, Levers, compute_model, compute_vpn, load_fixed_params
from opportunity import (
    base_vector,
    improving_targets,
    minimal_effort,
    read_hurdle,
    uniform_effort,
    value_vector,
    vector_to_levers,
)
from optimize import build_bounds, optimal_levers
from sensitivity import cantidades_sensitivities, scalar_sensitivities

st.set_page_config(page_title="VPN del Proyecto", layout="wide")

# Slider keys for the 10 yearly quantities
Q_KEYS = [f"q{j}" for j in range(N_YEARS)]


# ---------------------------------------------------------------- cached loaders
@st.cache_data
def get_fixed_and_base():
    return load_fixed_params()


@st.cache_data
def get_hurdle():
    return read_hurdle()


@st.cache_data
def get_optimum_levers():
    fixed, _ = get_fixed_and_base()
    return optimal_levers(fixed)


@st.cache_data
def get_opportunity_levers():
    """Return (uniform_plan_levers, minimal_plan_levers) or (None, None) if infeasible."""
    fixed, base = get_fixed_and_base()
    hurdle = get_hurdle()
    bv = base_vector(base)
    tv = improving_targets(bv, build_bounds(), fixed)
    if compute_vpn(vector_to_levers(value_vector(1.0, bv, tv)), fixed) < hurdle:
        return None, None
    lam = uniform_effort(bv, tv, fixed, hurdle)
    uni = vector_to_levers(value_vector(lam, bv, tv))
    p = minimal_effort(bv, tv, fixed, hurdle, seed_lambda=lam)
    mini = vector_to_levers(value_vector(list(p), bv, tv))
    return uni, mini


# ---------------------------------------------------------------- state helpers
def levers_to_state(lev: Levers) -> dict:
    s = {
        "pct_d": float(lev.pct_d),
        "costo": int(round(lev.costo_mp_base)),
        "cxc": float(lev.cxc_dias),
        "cxp": float(lev.cxp_dias),
        "g": float(lev.g_real_precio),
    }
    for j, q in enumerate(lev.cantidades):
        s[Q_KEYS[j]] = int(round(q))
    return s


def state_to_levers() -> Levers:
    pct_d = st.session_state["pct_d"]
    return Levers(
        pct_e=1.0 - pct_d,
        pct_d=pct_d,
        costo_mp_base=float(st.session_state["costo"]),
        cxc_dias=st.session_state["cxc"],
        cxp_dias=st.session_state["cxp"],
        g_real_precio=st.session_state["g"],
        cantidades=[float(st.session_state[k]) for k in Q_KEYS],
    )


def apply_preset(lev: Levers) -> None:
    for k, v in levers_to_state(lev).items():
        st.session_state[k] = v
    st.rerun()


# ---------------------------------------------------------------- setup
fixed, base = get_fixed_and_base()
hurdle = get_hurdle()
base_vpn = compute_vpn(base, fixed)

# initialize widget state from the base case once
for k, v in levers_to_state(base).items():
    st.session_state.setdefault(k, v)

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Escenarios")
c1, c2 = st.sidebar.columns(2)
if c1.button("Base", use_container_width=True):
    apply_preset(base)
if c2.button("Óptimo", use_container_width=True):
    apply_preset(get_optimum_levers())
uni, mini = get_opportunity_levers()
if c1.button("Opp. uniforme", use_container_width=True, disabled=uni is None):
    apply_preset(uni)
if c2.button("Opp. mínimo", use_container_width=True, disabled=mini is None):
    apply_preset(mini)

st.sidebar.header("Variables de decisión")
st.sidebar.slider("%D (deuda)", 0.0, 1.0, step=0.01, key="pct_d",
                  help="Reasonable: 0.1–60%")
st.sidebar.caption(f"%E (equity) = {1 - st.session_state['pct_d']:.0%}  ·  reasonable %D: 0.1–60%")
st.sidebar.slider("Costo materia prima (COP/ton)", 1_000_000, 3_000_000, step=10_000, key="costo")
st.sidebar.caption("reasonable: 1,600,000–2,000,000")
st.sidebar.slider("CXC (días)", 0.0, 180.0, step=1.0, key="cxc")
st.sidebar.caption("reasonable: 30–95")
st.sidebar.slider("CXP (días)", 0.0, 180.0, step=1.0, key="cxp")
st.sidebar.caption("reasonable: 20–90")
st.sidebar.slider("Crecimiento real precio", 0.0, 0.15, step=0.005, key="g",
                  format="%.3f")
st.sidebar.caption("reasonable: 3.5%–6%")
st.sidebar.markdown("**Cantidades (ton/año)**")
for j in range(N_YEARS):
    cap = "≤1500" if j == 0 else "≤5000"
    st.sidebar.slider(f"Año {j + 1}  ·  reasonable {cap}", 0, 6000, step=50, key=Q_KEYS[j])

# ---------------------------------------------------------------- compute
lev = state_to_levers()
res = compute_model(lev, fixed)
vpn = res.vpn

# ---------------------------------------------------------------- header metrics
st.title("VPN del Proyecto — explorador interactivo")
m1, m2, m3 = st.columns(3)
m1.metric("VPN", f"{vpn / 1e9:,.2f} B", f"{(vpn - base_vpn) / 1e9:,.2f} B vs base")
m2.metric("WACC", f"{res.wacc:.2%}")
m3.metric("VPN − costo de oportunidad", f"{(vpn - hurdle) / 1e9:,.2f} B")

if vpn >= hurdle:
    st.success(f"Supera el costo de oportunidad ({hurdle:,.0f} COP) por {vpn - hurdle:,.0f}.")
else:
    st.error(f"No supera el costo de oportunidad ({hurdle:,.0f} COP). Faltan {hurdle - vpn:,.0f}.")

# ---------------------------------------------------------------- cash-flow chart
st.subheader("Flujo de caja libre por año")
fcl = res.fcl_unlevered
discounted = [f / (1 + res.wacc) ** k for k, f in enumerate(fcl)]
cf = pd.DataFrame({
    "Año": list(range(len(fcl))) * 2,
    "Serie": ["FCL"] * len(fcl) + ["FCL descontado"] * len(fcl),
    "Valor": fcl + discounted,
})
chart = (
    alt.Chart(cf)
    .mark_bar()
    .encode(
        x=alt.X("Año:O"),
        xOffset="Serie:N",
        y=alt.Y("Valor:Q", title="COP"),
        color=alt.Color("Serie:N", legend=alt.Legend(orient="top")),
        tooltip=["Año", "Serie", alt.Tooltip("Valor:Q", format=",.0f")],
    )
    .properties(height=320)
)
st.altair_chart(chart, use_container_width=True)

# ---------------------------------------------------------------- sensitivity tornado
st.subheader("Sensibilidad (ΔVPN por un paso práctico, en los valores actuales)")
rows = scalar_sensitivities(lev, fixed) + cantidades_sensitivities(lev, fixed)
tor = pd.DataFrame({
    "Variable": [f"{r['name']} ({r['step_label']})" for r in rows],
    "Impacto": [r["step_impact"] for r in rows],
})
tor["abs"] = tor["Impacto"].abs()
tornado = (
    alt.Chart(tor)
    .mark_bar()
    .encode(
        x=alt.X("Impacto:Q", title="ΔVPN (COP)"),
        y=alt.Y("Variable:N", sort=alt.SortField("abs", order="descending")),
        color=alt.condition(alt.datum.Impacto >= 0, alt.value("#2ca02c"), alt.value("#d62728")),
        tooltip=["Variable", alt.Tooltip("Impacto:Q", format=",.0f")],
    )
    .properties(height=420)
)
st.altair_chart(tornado, use_container_width=True)

st.caption(
    "Base VPN = {:,.0f}  ·  costo de oportunidad = {:,.0f}".format(base_vpn, hurdle)
)
