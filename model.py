"""Parametrized model of "VPN del Proyecto" from Taller_final.xlsx.

This is a pure-Python reimplementation of the cash-flow chain behind
`Estado de resultados!C66`, exposing the decision variables the user wants to
optimize as `Levers`. All other inputs are read once from the workbook as
`FixedParams` so the model stays in sync with the spreadsheet.

The model reproduces Excel's cached VPN exactly (see `validate()` at the bottom).

Non-obvious behavior replicated deliberately: `%D` (porcentaje de deuda) affects
VPN through TWO channels:
  - the WACC discount rate, and
  - `Impuestos por pagar` (row 36 = row 28), which is computed on EBT
    (= EBIT - Gastos financieros). Gastos financieros come from the Bancos
    debt schedule sized by `%D`, so debt flows into the FCL via KTNO.
NOPAT itself uses the *unlevered* operative tax (row 49). The model keeps this
mix of levered/unlevered tax exactly as the sheet does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import openpyxl

WORKBOOK_PATH = "Taller_final.xlsx"
N_YEARS = 10  # Año 1 .. Año 10 (columns D..M in the sheet)


@dataclass
class FixedParams:
    """Inputs to VPN held constant during optimization (read from the workbook)."""

    inflation: list[float]          # ES!D4:M4, per year (Año 1..10)
    tax: float                      # Datos!C17 (== ES D5:M5 == WACC!B6)
    precio_base: float              # ES!D8 (hardcoded =6500000)
    g_real_mp: float                # Datos!C23, real growth of raw-material cost
    nomina_oper_base: float         # Nómina!H3 (grows by inflation)
    nomina_admin_base: float        # Nómina!H4 (grows by inflation)
    pct_mantenimiento: float        # Datos!C21 (of revenue)
    pct_gastos_op_var: float        # Datos!C26 (of revenue)
    pct_comisiones: float           # Datos!C27 (of revenue)
    depre_annual: float             # constant per year (Depreciaciones!B7)
    amort_annual: float             # constant per year (Amortización!B4)
    capex_total_mm: float           # Datos!C10 (millones de COP)
    pct_overhaul: float             # Datos!C24 (year-5 renovation, of initial capex)
    # Salvage (Año 11) constants
    pct_venta_activos: float        # ES!P37
    pct_desmantelamiento: float     # ES!P38
    tax_ganancia_ocasional: float   # ES!P39
    # WACC building blocks
    rf: float                       # WACC!B1
    market_return: float            # WACC!B2
    beta_l: float                   # WACC!B4
    de_sector: float                # WACC!B5 (D/E of the sector)
    bono_yankee: float              # WACC!B11
    tes_cop: float                  # WACC!B13
    # Bancos (cost of debt)
    dtf: float                      # Bancos!B4
    spread: float                   # Bancos!B5

    @property
    def capex_total(self) -> float:
        return self.capex_total_mm * 1_000_000

    @property
    def kd(self) -> float:
        """Bancos!B10 — effective annual cost of debt. Independent of %D."""
        tasa_ta = self.dtf + self.spread          # B6
        trim_ant = tasa_ta / 4                     # B7
        trim_venc = trim_ant / (1 - trim_ant)      # B8
        nominal_anual = trim_venc * 4              # B9
        return (1 + nominal_anual / 4) ** 4 - 1    # B10

    @property
    def salvage(self) -> float:
        """ES!P48 — Año-11 cash flow from asset disposal. Independent of levers."""
        valor_venta = self.capex_total * self.pct_venta_activos          # P41
        ppe_neta_10 = self.capex_total - N_YEARS * self.depre_annual     # M42
        utilidad = valor_venta - ppe_neta_10                             # P43
        impuesto = max(0.0, utilidad * self.tax_ganancia_ocasional)      # P44
        flujo_venta = valor_venta - impuesto                            # P46
        desmantelamiento = self.capex_total_mm * self.pct_desmantelamiento * 1_000_000  # P47
        return flujo_venta - desmantelamiento                           # P48


@dataclass
class Levers:
    """The decision variables to be optimized."""

    pct_e: float                    # Datos!C34, porcentaje de equity
    pct_d: float                    # Datos!C35, porcentaje de deuda
    costo_mp_base: float            # ES!D9, raw-material cost per ton, Año 1
    cxc_dias: float                 # Datos!C28
    cxp_dias: float                 # Datos!C29
    g_real_precio: float            # Datos!C31, real annual price growth
    cantidades: list[float] = field(default_factory=list)  # ES!D10:M10 (10 values)


def load_fixed_params(path: str = WORKBOOK_PATH) -> tuple[FixedParams, Levers]:
    """Read constants (FixedParams) and the base-case lever values from the workbook."""
    wb = openpyxl.load_workbook(path, data_only=True)
    es, d, w, b, nom = (
        wb["Estado de resultados"],
        wb["Datos"],
        wb["WACC"],
        wb["Bancos"],
        wb["Nómina"],
    )

    inflation = [es.cell(row=4, column=col).value for col in range(4, 4 + N_YEARS)]  # D4:M4
    depre_annual = sum(
        d.cell(row=r, column=3).value * 1_000_000 / d.cell(row=r, column=5).value
        for r in range(5, 10)  # Datos C5:C9 / E5:E9
    )
    amort_annual = 1_000_000 * d["C10"].value * d["C25"].value / 5

    fixed = FixedParams(
        inflation=inflation,
        tax=d["C17"].value,
        precio_base=es["D8"].value,
        g_real_mp=d["C23"].value,
        nomina_oper_base=nom["H3"].value,
        nomina_admin_base=nom["H4"].value,
        pct_mantenimiento=d["C21"].value,
        pct_gastos_op_var=d["C26"].value,
        pct_comisiones=d["C27"].value,
        depre_annual=depre_annual,
        amort_annual=amort_annual,
        capex_total_mm=d["C10"].value,
        pct_overhaul=d["C24"].value,
        pct_venta_activos=es["P37"].value,
        pct_desmantelamiento=es["P38"].value,
        tax_ganancia_ocasional=es["P39"].value,
        rf=w["B1"].value,
        market_return=w["B2"].value,
        beta_l=w["B4"].value,
        de_sector=w["B5"].value,
        bono_yankee=w["B11"].value,
        tes_cop=w["B13"].value,
        dtf=b["B4"].value,
        spread=b["B5"].value,
    )

    base_levers = Levers(
        pct_e=d["C34"].value,
        pct_d=d["C35"].value,
        costo_mp_base=es["D9"].value,
        cxc_dias=d["C28"].value,
        cxp_dias=d["C29"].value,
        g_real_precio=d["C31"].value,
        cantidades=[es.cell(row=10, column=col).value for col in range(4, 4 + N_YEARS)],
    )
    return fixed, base_levers


def debt_schedule_interest(pct_d: float, fixed: FixedParams) -> list[float]:
    """Reproduce Bancos rows 20-59 and return the 10 annual interest figures (J20:J29).

    Loan = Datos!C10 * %D (in millones). Quarterly vencido rate from Bancos!B8.
    Amortization: Año 1 = grace (0); Años 2-9 = 10%/yr (2.5%/quarter);
    Año 10 = 20%/yr (5%/quarter).
    """
    loan = fixed.capex_total_mm * pct_d  # Bancos!B12, in millones
    tasa_ta = fixed.dtf + fixed.spread
    trim_venc = (tasa_ta / 4) / (1 - tasa_ta / 4)  # B8

    annual_interest = [0.0] * N_YEARS
    saldo = loan
    for q in range(1, 41):  # 40 quarters (rows 20..59)
        year = (q - 1) // 4 + 1  # Bancos column B (1..10)
        interes = saldo * trim_venc
        if year == 1:
            amort = 0.0
        elif year < 10:
            amort = loan * 0.1 / 4
        else:
            amort = loan * 0.2 / 4
        saldo -= amort
        annual_interest[year - 1] += interes
    return annual_interest


def wacc(pct_e: float, pct_d: float, fixed: FixedParams) -> float:
    """Reproduce WACC!B18 = Ke_COP*%E + %D*(1-tax)*Kd."""
    tax = fixed.tax
    erp = fixed.market_return - fixed.rf                          # B3
    beta_u = fixed.beta_l / (1 + (1 - tax) * fixed.de_sector)     # B7
    de_ratio = pct_d / pct_e                                      # B9
    beta_proyecto = beta_u * (1 + (1 - tax) * de_ratio)          # B10
    rp = fixed.bono_yankee - fixed.rf                            # B12
    deval = fixed.tes_cop - fixed.bono_yankee                    # B14
    ke_usd = fixed.rf + beta_proyecto * erp + rp                 # B15
    ke_cop = (1 + ke_usd) * (1 + deval) - 1                      # B16
    return ke_cop * pct_e + pct_d * (1 - tax) * fixed.kd          # B18


@dataclass
class ModelResult:
    vpn: float
    wacc: float
    fcl_unlevered: list[float]  # C63 .. N63 (years 0..11), 12 values
    salvage: float


def compute_model(levers: Levers, fixed: FixedParams) -> ModelResult:
    """Build the full 10-year P&L + cash-flow chain and return VPN and key intermediates."""
    n = N_YEARS
    infl = fixed.inflation
    tax = fixed.tax
    cant = levers.cantidades
    assert len(cant) == n, f"cantidades must have {n} values"

    # --- Precio (row 8) and Costo (row 9): grow by inflation_of_previous_year * (1+real) ---
    precio = [0.0] * n
    costo = [0.0] * n
    precio[0] = fixed.precio_base
    costo[0] = levers.costo_mp_base
    for j in range(1, n):
        precio[j] = precio[j - 1] * (1 + infl[j - 1]) * (1 + levers.g_real_precio)
        costo[j] = costo[j - 1] * (1 + infl[j - 1]) * (1 + fixed.g_real_mp)

    ingresos = [precio[j] * cant[j] for j in range(n)]        # row 15
    costo_ventas = [costo[j] * cant[j] for j in range(n)]     # row 16

    # Nómina (rows 17, 20) grow by inflation of previous year
    nom_oper = [0.0] * n
    nom_admin = [0.0] * n
    nom_oper[0] = fixed.nomina_oper_base
    nom_admin[0] = fixed.nomina_admin_base
    for j in range(1, n):
        nom_oper[j] = nom_oper[j - 1] * (1 + infl[j - 1])
        nom_admin[j] = nom_admin[j - 1] * (1 + infl[j - 1])

    mantenimiento = [ing * fixed.pct_mantenimiento for ing in ingresos]   # row 18
    utilidad_bruta = [
        ingresos[j] - costo_ventas[j] - nom_oper[j] - mantenimiento[j] for j in range(n)
    ]  # row 19
    gastos_op_var = [ing * fixed.pct_gastos_op_var for ing in ingresos]   # row 21
    comisiones = [ing * fixed.pct_comisiones for ing in ingresos]         # row 24
    depre = fixed.depre_annual
    amort = fixed.amort_annual

    ebit = [
        utilidad_bruta[j] - nom_admin[j] - gastos_op_var[j] - depre - amort - comisiones[j]
        for j in range(n)
    ]  # row 25
    impuestos_op = [max(0.0, ebit[j] * tax) for j in range(n)]            # row 49 (unlevered)
    nopat = [ebit[j] - impuestos_op[j] for j in range(n)]                 # row 50
    flujo_caja_bruto = [nopat[j] + depre + amort for j in range(n)]       # rows 53/59

    # --- Levered branch feeding KTNO via Impuestos por pagar ---
    interest_mm = debt_schedule_interest(levers.pct_d, fixed)
    gastos_fin = [interest_mm[j] * 1_000_000 for j in range(n)]           # row 26 (millones -> COP)
    ebt = [ebit[j] - gastos_fin[j] for j in range(n)]                    # row 27
    impuestos_por_pagar = [max(0.0, ebt[j] * tax) for j in range(n)]     # rows 28/36

    cxc = [(levers.cxc_dias / 360) * ingresos[j] for j in range(n)]      # row 33 (= KTO row 34)
    cxp = [(levers.cxp_dias / 360) * costo_ventas[j] for j in range(n)]  # row 35
    ktno = [cxc[j] - cxp[j] - impuestos_por_pagar[j] for j in range(n)]  # row 37

    d_ktno = [0.0] * n  # row 38
    d_ktno[0] = ktno[0]
    for j in range(1, n):
        d_ktno[j] = ktno[j] - ktno[j - 1]

    fcl = [flujo_caja_bruto[j] - d_ktno[j] for j in range(n)]            # row 61

    # CAPEX (row 62): year0 = -total; year5 (Año 5 = index 4) = overhaul; else 0
    capex = [0.0] * n
    capex[4] = -fixed.capex_total * fixed.pct_overhaul
    capex0 = -fixed.capex_total

    # FCL unlevered (row 63): years 0..10 then salvage as year 11
    fcl_unlevered = [capex0] + [fcl[j] + capex[j] for j in range(n)] + [fixed.salvage]

    # VPN (C66): NPV of years 1..11 at WACC, plus undiscounted year 0
    w = wacc(levers.pct_e, levers.pct_d, fixed)
    npv = sum(fcl_unlevered[k] / (1 + w) ** k for k in range(1, len(fcl_unlevered)))
    vpn = npv + fcl_unlevered[0]

    return ModelResult(vpn=vpn, wacc=w, fcl_unlevered=fcl_unlevered, salvage=fixed.salvage)


def compute_vpn(levers: Levers, fixed: FixedParams) -> float:
    """Convenience wrapper: return only the VPN (objective for the solver)."""
    return compute_model(levers, fixed).vpn


# --- Cached Excel values used to validate the reimplementation ---
EXCEL_VPN = -12_640_745_057.294985
EXCEL_WACC = 0.20737679910341045
EXCEL_FCL63 = [
    -14_000_000_000,
    -1_571_666_666.6666667,
    -7_503_113.333333731,
    95_032_008.81467843,
    607_199_130.7679977,
    -7_961_454_941.71465,
    2_086_157_052.961433,
    3_687_098_554.302073,
    5_560_396_345.043389,
    6_214_143_201.963727,
    6_949_544_636.733009,
    2_730_000_000,
]
EXCEL_SALVAGE = 2_730_000_000.0


def validate() -> None:
    fixed, base = load_fixed_params()
    res = compute_model(base, fixed)

    print("=== Validation against Excel cached values ===")
    print(f"WACC     model={res.wacc:.15f}  excel={EXCEL_WACC:.15f}")
    print(f"Salvage  model={res.salvage:,.2f}  excel={EXCEL_SALVAGE:,.2f}")
    print(f"VPN      model={res.vpn:,.4f}")
    print(f"VPN      excel={EXCEL_VPN:,.4f}")
    print(f"VPN diff       {res.vpn - EXCEL_VPN:,.6f}")

    print("\nFCL unlevered (row 63), model vs excel:")
    for k, (m, e) in enumerate(zip(res.fcl_unlevered, EXCEL_FCL63)):
        flag = "OK" if abs(m - e) < 1.0 else "MISMATCH"
        print(f"  year {k:>2}: model={m:>22,.2f}  excel={e:>22,.2f}  [{flag}]")

    assert abs(res.wacc - EXCEL_WACC) < 1e-12, "WACC mismatch"
    assert abs(res.salvage - EXCEL_SALVAGE) < 1.0, "Salvage mismatch"
    for m, e in zip(res.fcl_unlevered, EXCEL_FCL63):
        assert abs(m - e) < 1.0, "FCL stream mismatch"
    assert abs(res.vpn - EXCEL_VPN) < 1.0, "VPN mismatch"
    print("\nAll checks passed: model reproduces Excel's VPN.")


def sensitivity_check() -> None:
    """Print VPN deltas when each lever moves in its value-improving direction."""
    from dataclasses import replace

    fixed, base = load_fixed_params()
    base_vpn = compute_vpn(base, fixed)
    print("\n=== Sensitivity (each lever nudged toward higher VPN) ===")
    print(f"base VPN = {base_vpn:,.2f}")

    nudges = {
        "costo_mp_base -10%": replace(base, costo_mp_base=base.costo_mp_base * 0.9),
        "cxc_dias -10 days": replace(base, cxc_dias=base.cxc_dias - 10),
        "cxp_dias +10 days": replace(base, cxp_dias=base.cxp_dias + 10),
        "g_real_precio +1pp": replace(base, g_real_precio=base.g_real_precio + 0.01),
        "cantidades +10%": replace(base, cantidades=[q * 1.1 for q in base.cantidades]),
        "pct_d -> 0.2 (pct_e 0.8)": replace(base, pct_d=0.2, pct_e=0.8),
    }
    for name, lev in nudges.items():
        v = compute_vpn(lev, fixed)
        print(f"  {name:<28} VPN = {v:>22,.2f}   Δ = {v - base_vpn:>20,.2f}")


if __name__ == "__main__":
    validate()
    sensitivity_check()
