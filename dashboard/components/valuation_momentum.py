"""
dashboard/components/valuation_momentum.py — Module 4: Valuation & Momentum

Public API:
    render(row, ticker) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st


def _ev_ebitda_help(row: pd.Series) -> str | None:
    ebitda = row.get("ebitda")
    market_cap = row.get("market_cap")
    if pd.isna(market_cap):
        return "N/A: market cap not available in Compustat for this ticker, so EV cannot be computed."
    if pd.isna(ebitda):
        return "N/A: EBITDA (Compustat oibdpy) not reported for this ticker."
    if ebitda <= 0:
        return f"N/A: EBITDA is negative (${ebitda:,.1f}M), so the ratio is undefined and excluded to avoid a misleading negative multiple."
    return None


def _pe_help(row: pd.Series) -> str | None:
    net_income = row.get("net_income")
    market_cap = row.get("market_cap")
    if pd.isna(market_cap):
        return "N/A: market cap not available in Compustat for this ticker."
    if pd.isna(net_income):
        return "N/A: net income not reported for this ticker."
    if net_income <= 0:
        return f"N/A: net income is negative (${net_income:,.1f}M), so the P/E ratio is undefined and excluded to avoid misleading negative-earnings multiples."
    return None


def render(row: pd.Series, ticker: str) -> None:
    with st.expander("Module 4 — Valuation & Momentum", expanded=True):
        ev_ebitda = row.get("ev_ebitda")
        pe_ratio = row.get("pe_ratio")
        value_pct = row.get("value_pct")
        mom_12_1 = row.get("mom_12_1")
        ret_1m = row.get("ret_1m")
        reversal_flag = row.get("reversal_flag")
        mom_pct = row.get("mom_pct")

        val_col, mom_col = st.columns(2)

        fyearq = row.get("fyearq")
        val_vintage = f"FY {int(fyearq)} Q4" if pd.notna(fyearq) else "Dec 2024"

        with val_col:
            st.subheader("Valuation")
            if pd.isna(ev_ebitda) and pd.isna(pe_ratio):
                st.warning("Valuation data not available for this ticker.")
            else:
                vc1, vc2, vc3 = st.columns(3)
                with vc1:
                    st.metric("EV / EBITDA",
                              f"{ev_ebitda:.1f}x" if pd.notna(ev_ebitda) else "N/A",
                              help=_ev_ebitda_help(row) if pd.isna(ev_ebitda) else None)
                with vc2:
                    st.metric("P / E",
                              f"{pe_ratio:.1f}x" if pd.notna(pe_ratio) else "N/A",
                              help=_pe_help(row) if pd.isna(pe_ratio) else None)
                with vc3:
                    st.metric("Value Percentile",
                              f"{value_pct:.1f}th" if pd.notna(value_pct) else "N/A",
                              help="Higher = cheaper vs. peers (inverted multiple rank)." if pd.notna(value_pct) else
                              "Percentile rank requires at least one valid multiple (EV/EBITDA or P/E).")
            st.caption(f"Compustat fundamentals · {val_vintage}")

        with mom_col:
            st.subheader("Momentum")
            if pd.isna(mom_12_1):
                st.warning("Momentum data not available for this ticker.")
            else:
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    st.metric("12-1M Momentum",
                              f"{mom_12_1*100:.1f}%",
                              help="Cumulative return t−12 to t−2.")
                with mc2:
                    st.metric("Prior Month Return",
                              f"{ret_1m*100:.1f}%" if pd.notna(ret_1m) else "N/A",
                              help=None if pd.notna(ret_1m) else
                              "Prior-month return missing from CRSP for this ticker.")
                with mc3:
                    if pd.isna(reversal_flag):
                        rev_label = "N/A"
                    elif reversal_flag == 1:
                        rev_label = "Yes (caution)"
                    else:
                        rev_label = "No"
                    st.metric("Reversal Flag", rev_label,
                              help="1 if prior-month return is in bottom decile.")
                if pd.notna(mom_pct):
                    st.metric("Momentum Percentile", f"{mom_pct:.1f}th")
            st.caption("CRSP monthly returns · through Dec 2024")
