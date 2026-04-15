"""
Piotroski F-Score calculator.

Reference: Piotroski (2000), "Value Investing: The Use of Historical Financial
Statement Information to Separate Winners from Losers."

Nine binary signals (1 = pass, 0 = fail) across three groups:

  Profitability
    F1  ROA > 0
    F2  CFO > 0
    F3  ΔROA > 0  (ROA improved year-over-year)
    F4  Accruals: CFO/Assets > NI/Assets  (cash earnings quality)

  Leverage / Liquidity
    F5  ΔLeverage < 0  (long-term debt ratio decreased)
    F6  ΔCurrent Ratio > 0  (liquidity improved)
    F7  No new equity issued  (shares outstanding did not increase)

  Operating Efficiency
    F8  ΔGross Margin > 0  (gross margin improved)
    F9  ΔAsset Turnover > 0  (asset turnover improved)

Total F-Score = F1 + … + F9  (0–9)

Data: Compustat quarterly file (compustat_with_permno.parquet).
      Filtered to fiscal-year-end quarters (fqtr == 4) so all flow
      variables (_y suffix) represent a full fiscal year.

Usage:
    from signals.fscore import compute_fscore
    scores = compute_fscore()          # returns latest score per ticker
    scores = compute_fscore(ticker="AAPL")
"""

import pandas as pd
import numpy as np

PARQUET_PATH = "data/compustat_with_permno.parquet"

# Compustat column mapping
# _y = annual/YTD cumulative (valid at fqtr==4)
# _q = balance-sheet (point-in-time)
COLS_NEEDED = [
    "gvkey", "tic", "conm", "datadate", "fyearq", "fqtr",
    "iby",      # net income (annual)
    "oancfy",   # cash from operations (annual)
    "atq",      # total assets
    "dlttq",    # long-term debt total
    "actq",     # current assets
    "lctq",     # current liabilities
    "cshoq",    # common shares outstanding
    "saley",    # net sales (annual)
    "cogsy",    # cost of goods sold (annual)
    "sich",     # historical SIC code (for sector)
    "permno",
]


def _load_annual(path: str = PARQUET_PATH) -> pd.DataFrame:
    """Load Compustat, keep only fiscal-year-end rows with the needed columns."""
    df = pd.read_parquet(path, engine="fastparquet", columns=COLS_NEEDED)

    # Keep only Q4 (fiscal year end) — flow variables (_y) are full-year here
    df = df[df["fqtr"] == 4].copy()

    # Drop rows missing the core balance-sheet anchor
    df = df.dropna(subset=["atq", "iby"])
    df = df[df["atq"] > 0]

    # Sort for lag calculations
    df = df.sort_values(["gvkey", "fyearq"]).reset_index(drop=True)

    return df


def _add_lags(df: pd.DataFrame) -> pd.DataFrame:
    """Add one-year-lagged versions of key variables within each firm."""
    lag_cols = ["iby", "oancfy", "atq", "dlttq", "actq", "lctq", "cshoq",
                "saley", "cogsy"]
    grp = df.groupby("gvkey")
    for col in lag_cols:
        df[f"{col}_lag"] = grp[col].shift(1)
    return df


def _compute_components(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all 9 binary F-Score components and underlying ratios."""
    d = df.copy()

    # --- Profitability ---

    # ROA = Net Income / Total Assets
    d["roa"] = d["iby"] / d["atq"]
    d["roa_lag"] = d["iby_lag"] / d["atq_lag"]

    # CFO/Assets
    d["cfo_assets"] = d["oancfy"] / d["atq"]

    # F1: ROA > 0
    d["F1"] = (d["roa"] > 0).astype(int)

    # F2: CFO > 0
    d["F2"] = (d["oancfy"] > 0).astype(int)

    # F3: ΔROA > 0
    d["F3"] = (d["roa"] > d["roa_lag"]).astype(int)

    # F4: Accruals — CFO/Assets > NI/Assets (higher cash quality)
    d["F4"] = (d["cfo_assets"] > d["roa"]).astype(int)

    # --- Leverage / Liquidity ---

    # Leverage = LT Debt / Total Assets
    d["leverage"] = d["dlttq"] / d["atq"]
    d["leverage_lag"] = d["dlttq_lag"] / d["atq_lag"]

    # Current Ratio = Current Assets / Current Liabilities
    d["current_ratio"] = d["actq"] / d["lctq"]
    d["current_ratio_lag"] = d["actq_lag"] / d["lctq_lag"]

    # F5: ΔLeverage < 0 (leverage fell)
    d["F5"] = (d["leverage"] < d["leverage_lag"]).astype(int)

    # F6: ΔCurrent Ratio > 0 (liquidity improved)
    d["F6"] = (d["current_ratio"] > d["current_ratio_lag"]).astype(int)

    # F7: No new equity issued (shares did not increase)
    d["F7"] = (d["cshoq"] <= d["cshoq_lag"]).astype(int)

    # --- Operating Efficiency ---

    # Gross Margin = (Sales - COGS) / Sales
    d["gross_margin"] = (d["saley"] - d["cogsy"]) / d["saley"]
    d["gross_margin_lag"] = (d["saley_lag"] - d["cogsy_lag"]) / d["saley_lag"]

    # Asset Turnover = Sales / Total Assets
    d["asset_turnover"] = d["saley"] / d["atq"]
    d["asset_turnover_lag"] = d["saley_lag"] / d["atq_lag"]

    # F8: ΔGross Margin > 0
    d["F8"] = (d["gross_margin"] > d["gross_margin_lag"]).astype(int)

    # F9: ΔAsset Turnover > 0
    d["F9"] = (d["asset_turnover"] > d["asset_turnover_lag"]).astype(int)

    # --- Total Score ---
    f_cols = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]
    # Only score rows where all 9 components are non-null (need lag year)
    d["fscore"] = d[f_cols].sum(axis=1)
    # Null out rows where any component relied on a missing lag
    has_lags = d[["roa_lag", "leverage_lag", "current_ratio_lag",
                   "cshoq_lag", "gross_margin_lag", "asset_turnover_lag"]].notna().all(axis=1)
    d.loc[~has_lags, f_cols + ["fscore"]] = np.nan

    return d


# Columns surfaced to callers
COMPONENT_COLS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "fscore"]
RATIO_COLS = ["roa", "cfo_assets", "leverage", "current_ratio",
              "gross_margin", "asset_turnover"]
META_COLS = ["gvkey", "tic", "conm", "datadate", "fyearq", "sich", "permno"]


def compute_fscore(
    path: str = PARQUET_PATH,
    ticker: str | None = None,
    latest_only: bool = True,
) -> pd.DataFrame:
    """
    Compute Piotroski F-Score for all tickers (or one ticker).

    Parameters
    ----------
    path : str
        Path to compustat_with_permno.parquet.
    ticker : str, optional
        If provided, filter to a single ticker (e.g. "AAPL").
    latest_only : bool
        If True (default), return only the most recent fiscal year per ticker.
        If False, return the full time series.

    Returns
    -------
    pd.DataFrame
        Columns: META_COLS + COMPONENT_COLS + RATIO_COLS
        F1–F9 are binary (1/0); fscore is the sum (0–9).
        NaN where insufficient history exists to compute delta signals.
    """
    df = _load_annual(path)

    if ticker is not None:
        df = df[df["tic"].str.upper() == ticker.upper()]
        if df.empty:
            raise ValueError(f"Ticker '{ticker}' not found in Compustat data.")

    df = _add_lags(df)
    df = _compute_components(df)

    if latest_only:
        df = df.sort_values("fyearq").groupby("gvkey").tail(1)

    out_cols = META_COLS + COMPONENT_COLS + RATIO_COLS
    return df[out_cols].reset_index(drop=True)


if __name__ == "__main__":
    scores = compute_fscore()
    print(f"Tickers scored: {scores['tic'].nunique()}")
    print(f"Score distribution:\n{scores['fscore'].value_counts().sort_index()}")
    print(scores[["tic", "fyearq", "fscore"] + COMPONENT_COLS].head(10).to_string())
