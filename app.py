"""Interactive explorer for VPN del Proyecto.

Move the decision-variable sliders and watch VPN, the opportunity-cost hurdle,
the cash-flow stream, and a live sensitivity tornado update.

Run:  uv run streamlit run app.py
"""

from __future__ import annotations

from dataclasses import replace

import altair as alt
import pandas as pd
import streamlit as st

from model import (
    METRIC_SPECS,
    N_YEARS,
    Levers,
    NominaRole,
    compute_model,
    compute_vpn,
    load_fixed_params,
    load_nomina_roster,
    nomina_bases,
)
from opportunity import read_hurdle
from optimize import optimal_levers
from sensitivity import cantidades_sensitivities, scalar_sensitivities

st.set_page_config(page_title="VPN del Proyecto", layout="wide")

# Slider keys for the 10 yearly quantities
Q_KEYS = [f"q{j}" for j in range(N_YEARS)]


# State-key helpers for the nómina roster (one set per role)
def nom_keys(i: int) -> tuple[str, str, str]:
    return f"nom_count_{i}", f"nom_sal_{i}", f"nom_prod_{i}"


def roster_to_state(roster: list[NominaRole]) -> dict:
    s = {}
    for i, r in enumerate(roster):
        kc, ks, kp = nom_keys(i)
        s[kc] = int(r.count)
        s[ks] = float(r.salario_mes)
        s[kp] = "SI" if r.es_produccion else "NO"
    return s


def state_to_roster(roster: list[NominaRole]) -> list[NominaRole]:
    """Rebuild the roster from session state, keeping each role's cargo label."""
    out = []
    for i, r in enumerate(roster):
        kc, ks, kp = nom_keys(i)
        out.append(
            NominaRole(
                cargo=r.cargo,
                count=int(st.session_state[kc]),
                salario_mes=float(st.session_state[ks]),
                es_produccion=st.session_state[kp] == "SI",
            )
        )
    return out


# ---------------------------------------------------------------- cached loaders
@st.cache_data
def get_fixed_and_base():
    return load_fixed_params()


@st.cache_data
def get_hurdle():
    return read_hurdle()


@st.cache_data
def get_roster():
    return load_nomina_roster()


@st.cache_data
def get_optimum_levers():
    fixed, _ = get_fixed_and_base()
    return optimal_levers(fixed)


# ---------------------------------------------------------------- state helpers
def levers_to_state(lev: Levers) -> dict:
    s = {
        "pct_d": float(lev.pct_d),
        "costo": int(round(lev.costo_mp_base)),
        "cxc": float(lev.cxc_dias),
        "cxp": float(lev.cxp_dias),
        "g": float(lev.g_real_precio),
        "comis": float(lev.pct_comisiones),
        "seg": float(lev.pct_seguro),
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
        pct_comisiones=st.session_state["comis"],
        pct_seguro=st.session_state["seg"],
        cantidades=[float(st.session_state[k]) for k in Q_KEYS],
    )


def apply_preset(lev: Levers) -> None:
    for k, v in levers_to_state(lev).items():
        st.session_state[k] = v
    st.rerun()


def metric_chart(spec: dict, values: list[float]) -> alt.Chart:
    """Build a small per-year (Año 1..10) chart for one financial indicator."""
    kind = spec["kind"]
    scaled = [v / 1e6 if kind == "millones" else v for v in values]
    df = pd.DataFrame({"Año": list(range(1, len(scaled) + 1)), "Valor": scaled})

    if kind == "pct":
        y = alt.Y("Valor:Q", title="", axis=alt.Axis(format=".0%"))
        tip = alt.Tooltip("Valor:Q", format=".2%")
    elif kind == "millones":
        y = alt.Y("Valor:Q", title="millones COP")
        tip = alt.Tooltip("Valor:Q", format=",.0f")
    else:  # "x" — ratio
        y = alt.Y("Valor:Q", title="veces")
        tip = alt.Tooltip("Valor:Q", format=".2f")

    base_chart = alt.Chart(df)
    mark = base_chart.mark_line(point=True) if spec["chart"] == "line" else base_chart.mark_bar()
    return (
        mark.encode(x=alt.X("Año:O", title=""), y=y, tooltip=["Año", tip])
        .properties(height=200, title=spec["title"])
    )


# ---------------------------------------------------------------- setup
fixed, base = get_fixed_and_base()
hurdle = get_hurdle()
base_roster = get_roster()
base_vpn = compute_vpn(base, fixed)

# initialize widget state from the base case once
for k, v in levers_to_state(base).items():
    st.session_state.setdefault(k, v)
for k, v in roster_to_state(base_roster).items():
    st.session_state.setdefault(k, v)
st.session_state.setdefault("multa", float(fixed.multa_base))

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Escenarios")
c1, c2 = st.sidebar.columns(2)
if c1.button("Base", use_container_width=True):
    apply_preset(base)
if c2.button("Óptimo", use_container_width=True):
    apply_preset(get_optimum_levers())

st.sidebar.header("Variables de decisión")
st.sidebar.slider("%D (deuda)", 0.0, 1.0, step=0.01, key="pct_d",
                  help="Razonable: 0.1–60%")
st.sidebar.caption(f"%E (equity) = {1 - st.session_state['pct_d']:.0%}  ·  razonable %D: 0.1–60%")
st.sidebar.slider("Costo materia prima (COP/ton)", 1_000_000, 3_000_000, step=10_000, key="costo")
st.sidebar.caption("razonable: 1,600,000–2,000,000")
st.sidebar.slider("CXC (días)", 0.0, 180.0, step=1.0, key="cxc")
st.sidebar.caption("razonable: 30–95")
st.sidebar.slider("CXP (días)", 0.0, 180.0, step=1.0, key="cxp")
st.sidebar.caption("razonable: 20–90")
st.sidebar.slider("Crecimiento real precio", 0.0, 0.15, step=0.005, key="g",
                  format="%.3f")
st.sidebar.caption("razonable: 3.5%–6%")
st.sidebar.slider("Comisiones", 0.01, 0.03, step=0.001, key="comis", format="%.3f")
st.sidebar.caption("base 2%  ·  razonable: 1%–3%")
st.sidebar.slider("Porcentaje de seguro", 0.05, 0.15, step=0.005, key="seg", format="%.3f")
st.sidebar.caption("base 10%  ·  razonable: 5%–15%  ·  solo afecta el EBIT del Año 1")
st.sidebar.markdown("**Cantidades (ton/año)**")
for j in range(N_YEARS):
    cap = "≤1500" if j == 0 else "≤5000"
    st.sidebar.slider(f"Año {j + 1}  ·  razonable {cap}", 0, 6000, step=50, key=Q_KEYS[j])

st.sidebar.header("Multa")
st.sidebar.slider(
    "Multa por quitar arrendadores (COP)",
    0.0,
    float(fixed.multa_base) * 2,
    step=1e8,
    key="multa",
    format="%.0f",
)
st.sidebar.caption(f"base {fixed.multa_base / 1e6:,.0f}M (Datos!C19)  ·  resta del VPN")

# ---------------------------------------------------------------- nómina detalle
with st.sidebar.expander("Nómina (detalle)"):
    if st.button("Restablecer nómina", use_container_width=True):
        for k, v in roster_to_state(base_roster).items():
            st.session_state[k] = v
        st.rerun()
    for i, r in enumerate(base_roster):
        kc, ks, kp = nom_keys(i)
        st.markdown(f"**{r.cargo}**")
        c1, c2, c3 = st.columns(3)
        c1.number_input("No", min_value=0, step=1, key=kc)
        c2.number_input("Sal/mes (M)", min_value=0.0, step=0.5, key=ks, format="%.1f")
        c3.selectbox("Producción", ["SI", "NO"], key=kp)
    oper_preview, admin_preview = nomina_bases(state_to_roster(base_roster))
    st.caption(
        f"operativa = {oper_preview / 1e6:,.0f}M  ·  administrativa = {admin_preview / 1e6:,.0f}M"
    )

# ---------------------------------------------------------------- compute
lev = state_to_levers()
nom_oper, nom_admin = nomina_bases(state_to_roster(base_roster))
fixed = replace(fixed, nomina_oper_base=nom_oper, nomina_admin_base=nom_admin)
multa = st.session_state["multa"]
res = compute_model(lev, fixed)
vpn = res.vpn

# ---------------------------------------------------------------- header metrics
st.title("VPN del Proyecto — explorador interactivo")
m0, m1, m2, m3, m4, m5 = st.columns(6)
m0.metric("Costo de oportunidad", f"{hurdle / 1e9:,.2f} B")
m1.metric("WACC", f"{res.wacc:.2%}")
m2.metric("VPN", f"{vpn / 1e9:,.2f} B", f"{(vpn - base_vpn) / 1e9:,.2f} B vs base")
m3.metric("VPN − multa", f"{(vpn - multa) / 1e9:,.2f} B", f"−{multa / 1e9:,.2f} B multa")
m4.metric("VPN − costo de oportunidad", f"{(vpn - hurdle) / 1e9:,.2f} B")
m5.metric("VPN − costo de oportunidad − multa", f"{(vpn - hurdle - multa) / 1e9:,.2f} B")

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
st.subheader("Sensibilidad dados los valores actuales")
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

# ---------------------------------------------------------------- financial indicators
st.subheader("Indicadores financieros")
N_COLS = 4
for row_start in range(0, len(METRIC_SPECS), N_COLS):
    cols = st.columns(N_COLS)
    for col, spec in zip(cols, METRIC_SPECS[row_start:row_start + N_COLS]):
        col.altair_chart(metric_chart(spec, res.metrics[spec["key"]]), use_container_width=True)

