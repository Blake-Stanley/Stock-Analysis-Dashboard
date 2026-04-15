"""
Gross Profitability signal (Novy-Marx 2013).

Formula: GP = (Revenue - COGS) / Total Assets

Reference: Novy-Marx (2013), "The Other Side of Value: The Gross Profitability
Premium." Journal of Financial Economics.

Rationale: Gross profit scaled by assets captures productive efficiency before
SG&A and other discretionary costs, and is a robust predictor of cross-sectional
returns with a return premium distinct from the value factor.

Data: Compustat quarterly file (compustat_with_permno.parquet), filtered to
fiscal-year-end quarters (fqtr == 4) for full-year revenue and COGS.

Usage:
    from signals.gross_profitability import compute_gross_profitability
    gp = compute_gross_profitability()
    gp = compute_gross_profitability(ticker="AAPL")
"""

import pandas as pd
import numpy as np

PARQUET_PATH = "data/compustat_with_permno.parquet"

COLS_NEEDED = [
    "gvkey", "tic", "conm", "datadate", "fyearq", "fqtr",
    "saley",   # net sales (annual)
    "cogsy",   # cost of goods sold (annual)
    "atq",     # total assets
    "sich",    # SIC code (for sector percentile)
    "permno",
]


def _load_annual(path: str = PARQUET_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path, engine="fastparquet", columns=COLS_NEEDED)
    df = df[df["fqtr"] == 4].copy()
    df = df.dropna(subset=["saley", "cogsy", "atq"])
    df = df[df["atq"] > 0]
    df = df[df["saley"] > 0]
    return df


def _sic_to_sector(sic: pd.Series) -> pd.Series:
    """Map 4-digit SIC to broad sector buckets for peer ranking."""
    s = pd.to_numeric(sic, errors="coerce").fillna(-1).astype(int)
    bins = [
        (100,  999,  "Agriculture"),
        (1000, 1499, "Mining"),
        (1500, 1799, "Construction"),
        (2000, 3999, "Manufacturing"),
        (4000, 4999, "Transportation"),
        (5000, 5199, "Wholesale"),
        (5200, 5999, "Retail"),
        (6000, 6799, "Finance"),
        (7000, 8999, "Services"),
        (9000, 9999, "Public"),
    ]
    result = pd.Series("Other", index=sic.index)
    for lo, hi, label in bins:
        result[(s >= lo) & (s <= hi)] = label
    return result


def compute_gross_profitability(
    path: str = PARQUET_PATH,
    ticker: str | None = None,
    latest_only: bool = True,
) -> pd.DataFrame:
    """
    Compute Novy-Marx gross profitability for all tickers (or one ticker).

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
          gp_ratio         — (Revenue - COGS) / Total Assets
          gp_pct_universe  — percentile rank within full universe (0–100)
          gp_pct_sector    — percentile rank within SIC sector (0–100)
          sector           — broad sector label used for peer ranking
    """
    df = _load_annual(path)

    if ticker is not None:
        df = df[df["tic"].str.upper() == ticker.upper()]
        if df.empty:
            raise ValueError(f"Ticker '{ticker}' not found in Compustat data.")

    if latest_only:
        df = df.sort_values("fyearq").groupby("gvkey").tail(1).copy()

    df["gp_ratio"] = (df["saley"] - df["cogsy"]) / df["atq"]
    df["sector"] = _sic_to_sector(df["sich"])

    # Percentile ranks (0–100, higher = better)
    df["gp_pct_universe"] = (
        df["gp_ratio"].rank(pct=True, na_option="keep") * 100
    )
    df["gp_pct_sector"] = (
        df.groupby("sector")["gp_ratio"]
        .rank(pct=True, na_option="keep") * 100
    )

    out_cols = [
        "gvkey", "tic", "conm", "datadate", "fyearq", "sich", "permno",
        "gp_ratio", "gp_pct_universe", "gp_pct_sector", "sector",
    ]
    return df[out_cols].reset_index(drop=True)


if __name__ == "__main__":
    gp = compute_gross_profitability()
    print(f"Tickers scored: {gp['tic'].nunique()}")
    print(f"\nGP ratio stats:\n{gp['gp_ratio'].describe()}")
    print(f"\nSample:\n{gp[['tic', 'fyearq', 'gp_ratio', 'gp_pct_universe', 'gp_pct_sector', 'sector']].head(10).to_string()}")
