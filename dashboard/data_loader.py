"""
dashboard/data_loader.py — Cached data accessors shared across the dashboard.
"""

import pandas as pd
import streamlit as st

QUANT_PATH = "data/quant_metrics.parquet"
SENTIMENT_PATH = "data/sentiment_scores.parquet"


@st.cache_data(show_spinner="Loading quant metrics…")
def load_quant() -> pd.DataFrame:
    return pd.read_parquet(QUANT_PATH, engine="fastparquet")


@st.cache_data(show_spinner="Loading sentiment scores…")
def load_sentiment() -> pd.DataFrame | None:
    try:
        return pd.read_parquet(SENTIMENT_PATH, engine="fastparquet")
    except FileNotFoundError:
        return None


def get_ticker_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    """Return the single row for *ticker* (case-insensitive), or None."""
    mask = df["tic"].str.upper() == ticker.upper()
    return df[mask].iloc[0] if mask.any() else None
