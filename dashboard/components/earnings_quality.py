"""
dashboard/components/earnings_quality.py — Module 3: Earnings Quality (Accruals)

Public API:
    render(row, ticker) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st


def render(row: pd.Series, ticker: str) -> None:
    with st.expander("Module 3 — Earnings Quality", expanded=True):
        accruals_ratio = row.get("accruals_ratio")
        aq_pct = row.get("accruals_quality_pct")
        high_acc = row.get("high_accruals")
        net_income = row.get("net_income")
        cfo = row.get("cfo")

        if pd.isna(accruals_ratio):
            st.warning("Accruals data not available for this ticker.")
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Accruals Ratio", f"{accruals_ratio:.4f}",
                      help="(Net Income − CFO) / Total Assets. Lower is better.")
        with c2:
            st.metric("Earnings Quality Percentile",
                      f"{aq_pct:.1f}th" if pd.notna(aq_pct) else "N/A",
                      help="Inverted accruals rank — higher = cleaner earnings.")
        with c3:
            flag_label = "High (caution)" if high_acc == 1 else "Normal"
            st.metric("Accruals Flag", flag_label)

        if pd.notna(net_income) and pd.notna(cfo):
            cf_df = pd.DataFrame({
                "Metric": ["Net Income", "Operating Cash Flow"],
                "Value ($M)": [net_income / 1e6, cfo / 1e6],
            })
            st.bar_chart(cf_df.set_index("Metric"))
