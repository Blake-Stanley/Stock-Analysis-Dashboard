"""
dashboard/components/gross_profitability.py — Module 2: Gross Profitability

Public API:
    render(row, ticker) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st


def render(row: pd.Series, ticker: str) -> None:
    with st.expander("Module 2 — Gross Profitability", expanded=True):
        gp_ratio = row.get("gp_ratio")
        gp_univ = row.get("gp_pct_universe")
        gp_sect = row.get("gp_pct_sector")

        if pd.isna(gp_ratio):
            st.warning("Gross profitability data not available for this ticker.")
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("GP / Assets (Novy-Marx)", f"{gp_ratio:.3f}",
                      help="(Revenue − COGS) / Total Assets")
        with c2:
            st.metric("Universe Percentile",
                      f"{gp_univ:.1f}th" if pd.notna(gp_univ) else "N/A",
                      help="Rank vs. all tickers in universe.")
        with c3:
            st.metric("Sector Percentile",
                      f"{gp_sect:.1f}th" if pd.notna(gp_sect) else "N/A",
                      help="Rank vs. tickers in same sector.")

        fyearq = row.get("fyearq")
        vintage = f"FY {int(fyearq)} Q4" if pd.notna(fyearq) else "Dec 2024"
        st.caption(f"Compustat fundamentals · {vintage}")
