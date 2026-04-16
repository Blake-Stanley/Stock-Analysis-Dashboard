"""
dashboard/components/sentiment.py — Module 5: Earnings Call Sentiment (Will — Phase 2)

Public API:
    render(ticker, sent_df) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st


def render(ticker: str, sent_df: pd.DataFrame | None) -> None:
    with st.expander("Module 5 — Earnings Call Sentiment", expanded=True):
        if sent_df is None:
            st.info("Sentiment data not yet available (Phase 2 — Will). "
                    "Expected file: `data/sentiment_scores.parquet`.")
            return

        mask = sent_df["tic"].str.upper() == ticker.upper()
        ticker_sent = sent_df[mask]
        if ticker_sent.empty:
            st.warning(f"No sentiment data found for **{ticker}**.")
            return

        # Will: replace this placeholder with real charts/metrics
        st.dataframe(ticker_sent, use_container_width=True)
