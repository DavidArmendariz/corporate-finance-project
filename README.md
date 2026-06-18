# VPN del Proyecto — explorador interactivo

Interactive Streamlit app for exploring the Net Present Value (VPN) of a project
modeled in `Taller_final.xlsx`. Move the decision-variable sliders and watch the
VPN, the opportunity-cost hurdle, the cash-flow stream, and a live sensitivity
tornado update in real time.

## What it does

- Recomputes VPN, WACC, and free cash flow from a parametrized model on every change.
- Flags whether the project clears its opportunity-cost hurdle.
- Provides preset scenarios in the sidebar:
  - **Base** — the base case read from the workbook.
  - **Óptimo** — levers that maximize VPN within reasonable bounds.
  - **Opp. uniforme** — uniform effort across levers to just clear the hurdle.
  - **Opp. mínimo** — minimal total effort to clear the hurdle.
- Charts the free cash flow (nominal and discounted) per year and a sensitivity tornado.

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI: sliders, presets, metrics, charts. |
| `model.py` | Parametrized financial model loaded from `Taller_final.xlsx`. |
| `opportunity.py` | Opportunity-cost hurdle and effort-allocation scenarios. |
| `optimize.py` | VPN optimization within reasonable lever bounds. |
| `sensitivity.py` | Sensitivity (tornado) computations. |
| `Taller_final.xlsx` | Source workbook with fixed parameters and the base case. |

## Requirements

- Python 3.13
- Dependencies: `streamlit`, `pandas`, `openpyxl`, `scipy`, `altair`

## Run locally

With [uv](https://docs.astral.sh/uv/):

```bash
uv run streamlit run app.py
```

Or with pip:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app reads `Taller_final.xlsx` from the project root, so run it from there.

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (include `Taller_final.xlsx`).
2. In [share.streamlit.io](https://share.streamlit.io), create an app pointing at
   the repo with `app.py` as the entry point and Python 3.13.
3. Streamlit Cloud installs dependencies from `requirements.txt`.
