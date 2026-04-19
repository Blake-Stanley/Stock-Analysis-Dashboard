"""
dashboard/data_loader.py — Cached data accessors shared across the dashboard.
"""

import numpy as np
import pandas as pd
import streamlit as st

QUANT_PATH = "data/quant_metrics.parquet"
SENTIMENT_PATH = "data/sentiment_scores.parquet"
COMPUSTAT_PATH = "data/compustat_with_permno.parquet"

_HIST_COLS = [
    "tic", "datadate", "fyearq", "fqtr",
    "ibq", "oancfy", "atq", "dlttq", "actq", "lctq",
    "cshoq", "saleq", "cogsq",
]

# Per-component chart config: col(s), display label(s), reference line.
# All flow metrics are TTM; balance sheet items are point-in-time.
FSCORE_HIST_CFG: dict[str, dict] = {
    "F1": {"col": "roa_ttm",            "label": "ROA (TTM)",               "ref": 0.0},
    "F2": {"col": "cfo_assets_ttm",     "label": "CFO / Assets (TTM)",      "ref": 0.0},
    "F3": {"col": "roa_ttm",            "label": "ROA (TTM)",               "ref": None},
    "F4": {"cols": ["roa_ttm", "cfo_assets_ttm"],
           "labels": ["ROA (TTM)", "CFO / Assets (TTM)"],                   "ref": None},
    "F5": {"col": "leverage_q",         "label": "LT Debt / Assets",        "ref": None},
    "F6": {"col": "current_ratio_q",    "label": "Current Ratio",           "ref": 1.0},
    "F7": {"col": "shares_m",           "label": "Shares Out. (M)",         "ref": None},
    "F8": {"col": "gross_margin_ttm",   "label": "Gross Margin (TTM)",      "ref": None},
    "F9": {"col": "asset_turnover_ttm", "label": "Asset Turnover (TTM)",    "ref": None},
}


@st.cache_data(show_spinner="Loading quant metrics…")
def load_quant() -> pd.DataFrame:
    return pd.read_parquet(QUANT_PATH, engine="fastparquet")


@st.cache_data(show_spinner="Loading sentiment scores…")
def load_sentiment() -> pd.DataFrame | None:
    try:
        return pd.read_parquet(SENTIMENT_PATH, engine="fastparquet")
    except FileNotFoundError:
        return None


@st.cache_data(show_spinner="Loading financial history…")
def _load_compustat_raw() -> pd.DataFrame:
    return pd.read_parquet(COMPUSTAT_PATH, engine="fastparquet", columns=_HIST_COLS)


@st.cache_data(show_spinner=False)
def load_ticker_history(ticker: str, n_quarters: int = 16) -> pd.DataFrame | None:
    """
    Return the last n_quarters of quarterly data for ticker with TTM metrics.

    Flow variables (NI, CFO, sales, COGS) are summed over the trailing four
    quarters so every row represents a rolling twelve-month view.  Balance
    sheet items (assets, debt, current ratio, shares) are point-in-time.

    We load n_quarters + 4 raw rows so the first returned row already has a
    complete four-quarter window.
    """
    df = _load_compustat_raw()
    df = df[df["tic"].str.upper() == ticker.upper()].copy()
    if df.empty:
        return None

    df["datadate"] = pd.to_datetime(df["datadate"])
    df = df.sort_values("datadate").tail(n_quarters + 4).reset_index(drop=True)

    # Incremental quarterly CFO: oancfy is fiscal-YTD cumulative and resets at Q1
    df["cfo_q"] = df["oancfy"].diff()
    df.loc[df["fqtr"] == 1, "cfo_q"] = df.loc[df["fqtr"] == 1, "oancfy"]

    # TTM aggregates — rolling 4-quarter sum of flow variables
    df["ni_ttm"]    = df["ibq"].rolling(4, min_periods=4).sum()
    df["cfo_ttm"]   = df["cfo_q"].rolling(4, min_periods=4).sum()
    df["sales_ttm"] = df["saleq"].rolling(4, min_periods=4).sum()
    df["cogs_ttm"]  = df["cogsq"].rolling(4, min_periods=4).sum()

    # TTM ratios (flow numerator, current-quarter balance sheet denominator)
    df["roa_ttm"]            = df["ni_ttm"]    / df["atq"]
    df["cfo_assets_ttm"]     = df["cfo_ttm"]   / df["atq"]
    df["gross_margin_ttm"]   = (df["sales_ttm"] - df["cogs_ttm"]) / df["sales_ttm"]
    df["asset_turnover_ttm"] = df["sales_ttm"] / df["atq"]

    # Balance sheet point-in-time
    df["leverage_q"]      = df["dlttq"] / df["atq"]
    df["current_ratio_q"] = df["actq"]  / df["lctq"]
    df["shares_m"]        = df["cshoq"]   # Compustat cshoq is already in millions

    df["period"] = df["fyearq"].astype(str) + " Q" + df["fqtr"].astype(str)

    # Drop the warm-up rows; every remaining row has a full TTM window
    return df.tail(n_quarters).reset_index(drop=True)


def get_fscore_yoy_pair(hist: pd.DataFrame) -> tuple[pd.Series | None, pd.Series | None]:
    """
    Return (most_recent_row, four_quarters_prior_row) for YoY TTM comparisons.
    Four quarters back gives the same calendar quarter one year ago.
    """
    if hist is None or hist.empty:
        return None, None
    curr = hist.iloc[-1]
    prev = hist.iloc[-5] if len(hist) >= 5 else None
    return curr, prev


def build_fscore_chart(component: str, hist: pd.DataFrame) -> pd.DataFrame | None:
    """Build a chart-ready DataFrame (period index, metric columns) for an F-Score component."""
    if hist is None or hist.empty:
        return None
    cfg = FSCORE_HIST_CFG.get(component)
    if cfg is None:
        return None

    data = hist.set_index("period")

    if "cols" in cfg:
        chart = data[cfg["cols"]].rename(columns=dict(zip(cfg["cols"], cfg["labels"])))
    else:
        chart = data[[cfg["col"]]].rename(columns={cfg["col"]: cfg["label"]})

    ref = cfg.get("ref")
    if ref is not None:
        chart["Reference"] = ref

    return chart.dropna(how="all")


def fmt_fscore_val(col: str, val: float) -> str:
    """Format a ratio value for display based on its column type."""
    if "gross_margin" in col:
        return f"{val:.1%}"
    if col == "shares_m":
        return f"{val:,.0f} M"
    if "current_ratio" in col or "asset_turnover" in col:
        return f"{val:.2f}"
    return f"{val:.4f}"


def fmt_fscore_delta(col: str, delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    if "gross_margin" in col:
        return f"{sign}{delta:.1%}"
    if col == "shares_m":
        return f"{sign}{delta:,.0f} M"
    if "current_ratio" in col or "asset_turnover" in col:
        return f"{sign}{delta:.2f}"
    return f"{sign}{delta:.4f}"


def get_ticker_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    """Return the single row for *ticker* (case-insensitive), or None."""
    mask = df["tic"].str.upper() == ticker.upper()
    return df[mask].iloc[0] if mask.any() else None
