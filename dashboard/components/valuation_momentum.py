"""
dashboard/components/valuation_momentum.py — Module 4: Valuation & Momentum

Public API:
    render(row, ticker) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st


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

        with val_col:
            st.subheader("Valuation")
            if pd.isna(ev_ebitda) and pd.isna(pe_ratio):
                st.warning("Valuation data not available for this ticker.")
            else:
                vc1, vc2, vc3 = st.columns(3)
                with vc1:
                    st.metric("EV / EBITDA",
                              f"{ev_ebitda:.1f}x" if pd.notna(ev_ebitda) else "N/A",
                              help=None if pd.notna(ev_ebitda) else
                              "EV/EBITDA is undefined when EBITDA is negative or missing in Compustat (oibdpy). Common for high-growth or recently public companies.")
                with vc2:
                    st.metric("P / E",
                              f"{pe_ratio:.1f}x" if pd.notna(pe_ratio) else "N/A",
                              help=None if pd.notna(pe_ratio) else
                              "P/E is undefined when net income is negative or missing. Excluded to avoid misleading negative-earnings multiples.")
                with vc3:
                    st.metric("Value Percentile",
                              f"{value_pct:.1f}th" if pd.notna(value_pct) else "N/A",
                              help="Higher = cheaper vs. peers (inverted multiple rank)." if pd.notna(value_pct) else
                              "Percentile rank requires at least one valid multiple (EV/EBITDA or P/E).")

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
                    rev_label = "Yes (caution)" if reversal_flag == 1 else "No"
                    st.metric("Reversal Flag", rev_label,
                              help="1 if prior-month return is in bottom decile.")
                if pd.notna(mom_pct):
                    st.metric("Momentum Percentile", f"{mom_pct:.1f}th")
