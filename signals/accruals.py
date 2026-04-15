"""
Earnings Quality / Accruals signal.

Formula: Accruals Ratio = (Net Income - CFO) / Total Assets

A high positive accruals ratio means earnings are running well ahead of cash
flow — a red flag for earnings quality. Sloan (1996) showed that high-accrual
firms systematically underperform.

Rationale: Low accruals (earnings backed by cash) predict positive future
returns; high accruals predict negative future returns. Complements the
Piotroski F-Score's F4 component with a standalone continuous signal.

Data: Compustat quarterly file (compustat_with_permno.parquet), filtered to
fiscal-year-end quarters (fqtr == 4).

Usage:
    from signals.accruals import compute_accruals
    ac = compute_accruals()
    ac = compute_accruals(ticker="AAPL")
"""

import pandas as pd
import numpy as np

PARQUET_PATH = "data/compustat_with_permno.parquet"

COLS_NEEDED = [
    "gvkey", "tic", "conm", "datadate", "fyearq", "fqtr",
    "iby",      # net income (annual)
    "oancfy",   # cash from operations (annual)
    "atq",      # total assets
    "sich",
    "permno",
]


def _load_annual(path: str = PARQUET_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path, engine="fastparquet", columns=COLS_NEEDED)
    df = df[df["fqtr"] == 4].copy()
    df = df.dropna(subset=["iby", "oancfy", "atq"])
    df = df[df["atq"] > 0]
    return df


def compute_accruals(
    path: str = PARQUET_PATH,
    ticker: str | None = None,
    latest_only: bool = True,
) -> pd.DataFrame:
    """
    Compute accruals ratio for all tickers (or one ticker).

    Parameters
    ----------
    path : str
        Path to compustat_with_permno.parquet.
    ticker : str, optional
        Filter to a single ticker.
    latest_only : bool
        If True (default), return only the most recent fiscal year per ticker.

    Returns
    -------
    pd.DataFrame
        Columns:
          gvkey, tic, conm, datadate, fyearq, sich, permno,
          net_income       — annual net income (iby)
          cfo              — annual cash from operations (oancfy)
          total_assets     — total assets (atq)
          accruals_ratio   — (NI - CFO) / Assets  (lower = better quality)
          high_accruals    — 1 if accruals_ratio > 75th percentile (warning flag)
          accruals_pct     — percentile rank within universe (0=best, 100=worst)
                             Note: lower accruals rank = higher earnings quality,
                             so invert when building composite score.
    """
    df = _load_annual(path)

    if ticker is not None:
        df = df[df["tic"].str.upper() == ticker.upper()]
        if df.empty:
            raise ValueError(f"Ticker '{ticker}' not found in Compustat data.")

    if latest_only:
        df = df.sort_values("fyearq").groupby("gvkey").tail(1).copy()

    df["net_income"] = df["iby"]
    df["cfo"] = df["oancfy"]
    df["total_assets"] = df["atq"]
    df["accruals_ratio"] = (df["iby"] - df["oancfy"]) / df["atq"]

    # Percentile rank: high rank = high accruals = low quality
    df["accruals_pct"] = (
        df["accruals_ratio"].rank(pct=True, na_option="keep") * 100
    )

    p75 = df["accruals_ratio"].quantile(0.75)
    df["high_accruals"] = (df["accruals_ratio"] > p75).astype(int)

    out_cols = [
        "gvkey", "tic", "conm", "datadate", "fyearq", "sich", "permno",
        "net_income", "cfo", "total_assets",
        "accruals_ratio", "accruals_pct", "high_accruals",
    ]
    return df[out_cols].reset_index(drop=True)


if __name__ == "__main__":
    ac = compute_accruals()
    print(f"Tickers scored: {ac['tic'].nunique()}")
    print(f"\nAccruals ratio stats:\n{ac['accruals_ratio'].describe()}")
    print(f"\nHigh accruals flags: {ac['high_accruals'].sum()} / {len(ac)}")
    print(f"\nSample:\n{ac[['tic', 'fyearq', 'accruals_ratio', 'accruals_pct', 'high_accruals']].head(10).to_string()}")
