"""
dashboard/components/fscore.py — Module 1: Piotroski F-Score

Public API:
    render(row, ticker) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st

from dashboard.data_loader import (
    FSCORE_HIST_CFG,
    build_fscore_chart,
    fmt_fscore_delta,
    fmt_fscore_val,
    get_fscore_yoy_pair,
    load_ticker_history,
)

# ---------------------------------------------------------------------------
# Component metadata
# ---------------------------------------------------------------------------

FSCORE_META: dict[str, dict] = {
    "F1": {
        "label": "Positive ROA",
        "group": "Profitability",
        "description": "Return on Assets > 0. Confirms the firm generates positive accounting profits on its asset base.",
        "formula": "TTM Net Income ÷ Total Assets",
        "pass_rule": "ROA > 0",
    },
    "F2": {
        "label": "Positive Cash Flow from Operations",
        "group": "Profitability",
        "description": "Operating cash flow is positive — the firm generates real cash earnings, not just accounting income.",
        "formula": "TTM CFO ÷ Total Assets",
        "pass_rule": "CFO / Assets > 0",
    },
    "F3": {
        "label": "Increasing ROA",
        "group": "Profitability",
        "description": "ROA improved year-over-year. Indicates the firm's operational profitability is on an upward trend.",
        "formula": "ROA(TTM, now) > ROA(TTM, 1yr ago)",
        "pass_rule": "Current TTM ROA > prior-year TTM ROA",
    },
    "F4": {
        "label": "Accruals: Cash Earnings > Accounting Earnings",
        "group": "Profitability",
        "description": "Cash-based earnings exceed accrual-based earnings. Low accruals signal higher earnings quality and lower manipulation risk.",
        "formula": "TTM CFO / Assets > TTM NI / Assets",
        "pass_rule": "CFO/Assets (TTM) > ROA (TTM)",
    },
    "F5": {
        "label": "Decreasing Leverage",
        "group": "Leverage / Liquidity",
        "description": "Long-term debt ratio fell year-over-year, reducing financial risk and improving solvency margin.",
        "formula": "LT Debt / Assets (current) < LT Debt / Assets (prior year)",
        "pass_rule": "Leverage fell vs. prior year",
    },
    "F6": {
        "label": "Increasing Current Ratio",
        "group": "Leverage / Liquidity",
        "description": "Short-term liquidity improved year-over-year. The firm has a stronger ability to cover near-term obligations.",
        "formula": "Current Assets / Current Liabilities",
        "pass_rule": "Current ratio rose vs. prior year",
    },
    "F7": {
        "label": "No New Equity Issued",
        "group": "Leverage / Liquidity",
        "description": "Shares outstanding did not increase. Avoids EPS dilution that would harm existing shareholders.",
        "formula": "Shares Outstanding (current) ≤ Shares Outstanding (prior year)",
        "pass_rule": "Share count did not rise",
    },
    "F8": {
        "label": "Improving Gross Margin",
        "group": "Operating Efficiency",
        "description": "Gross margin expanded year-over-year, signaling pricing power or improved cost control.",
        "formula": "(TTM Revenue − TTM COGS) ÷ TTM Revenue",
        "pass_rule": "TTM gross margin > prior-year TTM gross margin",
    },
    "F9": {
        "label": "Improving Asset Turnover",
        "group": "Operating Efficiency",
        "description": "Asset turnover increased year-over-year — more revenue generated per dollar of assets deployed.",
        "formula": "TTM Revenue ÷ Total Assets",
        "pass_rule": "TTM asset turnover > prior-year TTM asset turnover",
    },
}

# ---------------------------------------------------------------------------
# YoY comparison helper
# ---------------------------------------------------------------------------

def _render_yoy(component: str, curr: pd.Series, prev: pd.Series | None) -> None:
    """Show current TTM vs. same quarter one year ago using st.metric with delta."""
    cfg = FSCORE_HIST_CFG[component]
    col_names: list[str] = cfg["cols"] if "cols" in cfg else [cfg["col"]]
    col_labels: list[str] = cfg["labels"] if "labels" in cfg else [cfg["label"]]

    curr_lbl = f"Q{int(curr['fqtr'])} {int(curr['fyearq'])}"
    prev_lbl = f"Q{int(prev['fqtr'])} {int(prev['fyearq'])}" if prev is not None else "Prior Year"

    metric_cols = st.columns(len(col_names) * 2)

    for i, (cn, cl) in enumerate(zip(col_names, col_labels)):
        cv = curr.get(cn)
        cv = float(cv) if cv is not None and pd.notna(cv) else None
        pv = prev.get(cn) if prev is not None else None
        pv = float(pv) if pv is not None and pd.notna(pv) else None

        delta_str = fmt_fscore_delta(cn, cv - pv) if cv is not None and pv is not None else None

        with metric_cols[i * 2]:
            st.metric(
                f"{cl} ({curr_lbl})",
                fmt_fscore_val(cn, cv) if cv is not None else "N/A",
                delta=delta_str,
            )
        with metric_cols[i * 2 + 1]:
            st.metric(
                f"{cl} ({prev_lbl})",
                fmt_fscore_val(cn, pv) if pv is not None else "N/A",
            )

# ---------------------------------------------------------------------------
# Component detail dialog
# ---------------------------------------------------------------------------

@st.dialog("F-Score Component Detail", width="large")
def _component_dialog(component: str, ticker_row: pd.Series, ticker: str) -> None:
    meta = FSCORE_META[component]
    cfg = FSCORE_HIST_CFG[component]
    passed = ticker_row.get(component)

    if passed == 1:
        st.success(f"**PASS** — {component}: {meta['label']}")
    elif passed == 0:
        st.error(f"**FAIL** — {component}: {meta['label']}")
    else:
        st.warning(f"**N/A** — {component}: {meta['label']}")

    desc_col, formula_col = st.columns([3, 2])
    with desc_col:
        st.caption(meta["description"])
    with formula_col:
        st.code(meta["formula"], language=None)
        st.caption(f"Pass if: {meta['pass_rule']}")

    st.divider()

    with st.spinner("Loading history…"):
        hist = load_ticker_history(ticker)

    if hist is not None and not hist.empty:
        curr, prev = get_fscore_yoy_pair(hist)

        st.markdown("**TTM — Year-over-Year**")
        _render_yoy(component, curr, prev)

        st.divider()

        chart_df = build_fscore_chart(component, hist)
        main_label = cfg.get("labels", [cfg.get("label")])[0]
        st.markdown(f"**{main_label} — Quarterly ({len(hist)} periods, TTM)**")

        if chart_df is not None and not chart_df.empty:
            st.line_chart(chart_df, height=260)
        else:
            st.info("Insufficient data for chart.")
    else:
        st.info("Historical data not available for this ticker.")

    st.divider()

    btn_close, btn_full = st.columns(2)
    with btn_close:
        if st.button("Close", use_container_width=True):
            st.session_state.pop("_fscore_open", None)
            st.rerun()
    with btn_full:
        st.markdown(
            f'<a href="/fscore_detail?ticker={ticker}" target="_blank">'
            f'<button style="width:100%;padding:0.45rem 0.6rem;background:#FF4B4B;'
            f'color:white;border:none;border-radius:0.3rem;cursor:pointer;'
            f'font-size:0.875rem;font-weight:600;">Open Full Report ↗</button>'
            f'</a>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render(row: pd.Series, ticker: str) -> None:
    with st.expander("Module 1 — Piotroski F-Score", expanded=True):
        fscore = row.get("fscore")
        fscore_pct = row.get("fscore_pct")

        if pd.isna(fscore):
            st.warning("F-Score data not available for this ticker.")
        else:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.metric("F-Score", f"{int(fscore)} / 9",
                          help="0 = weakest fundamentals, 9 = strongest.")
                if pd.notna(fscore_pct):
                    st.metric("Percentile Rank", f"{fscore_pct:.1f}th")

            with c2:
                hdr = st.columns([0.5, 4, 1])
                hdr[0].markdown("**Pass**")
                hdr[1].markdown("**Component**")
                hdr[2].markdown("**Detail**")
                st.divider()

                for fk, meta in FSCORE_META.items():
                    val = row.get(fk)
                    icon = "✅" if val == 1 else "❌" if val == 0 else "—"
                    r = st.columns([0.5, 4, 1])
                    r[0].markdown(icon)
                    r[1].markdown(f"**{fk}** — {meta['label']}")
                    if r[2].button("Detail", key=f"_fscore_btn_{fk}", use_container_width=True):
                        st.session_state["_fscore_open"] = fk
                        st.rerun()

        if st.session_state.get("_fscore_open"):
            _component_dialog(st.session_state["_fscore_open"], row, ticker)
