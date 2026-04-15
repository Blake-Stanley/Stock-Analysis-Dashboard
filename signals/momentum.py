"""
12-1 Month Price Momentum signal.

Formula: MOM = Cumulative return from month t-12 to month t-2
         (skip the most recent month to avoid short-term reversal contamination)

Reversal flag: past-month return (t-1) in the bottom decile of the universe.

Reference: Jegadeesh & Titman (1993), Carhart (1997).

Rationale: The 12-1 month momentum factor is one of the most robust cross-
sectional return predictors. Skipping the last month avoids the well-documented
1-month reversal effect. Combined with value/quality signals it provides a
return-continuation dimension largely orthogonal to fundamentals.

Data: CRSP monthly file (crsp_m.dta). PERMNO links to Compustat via
      compustat_with_permno.parquet.

Usage:
    from signals.momentum import compute_momentum
    mom = compute_momentum()
    mom = compute_momentum(permno=14593)   # AAPL
"""

import pandas as pd
import numpy as np

CRSP_PATH = "data/crsp_m.dta"
COMPUSTAT_PATH = "data/compustat_with_permno.parquet"

MIN_OBS = 10  # minimum valid observations in the 11-month window


def _load_crsp(path: str = CRSP_PATH) -> pd.DataFrame:
    """Load CRSP monthly, keep ordinary common shares (SHRCD 10/11)."""
    df = pd.read_stata(path, convert_categoricals=False)
    df = df[df["SHRCD"].isin([10, 11])].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["RET"] = pd.to_numeric(df["RET"], errors="coerce")
    df["PRC"] = df["PRC"].abs()
    df = df.sort_values(["PERMNO", "date"]).reset_index(drop=True)
    return df


def _compute_momentum_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute 12-1 month momentum and 1-month reversal using vectorized
    grouped rolling operations.

    At each month t for each PERMNO:
      mom_12_1 = cumulative return from t-12 to t-2  (11-month window, shifted 2)
      ret_1m   = return at t-1                        (1-month lag)

    Uses log returns for the rolling sum, then exponentiates back.
    """
    df = df.copy()
    df["log_ret"] = np.log1p(df["RET"])

    grp = df.groupby("PERMNO")["log_ret"]

    # shift(2) moves the window so index t sums t-2, t-3, ..., t-12 (11 obs)
    # min_periods=MIN_OBS ensures we don't score on thin history
    df["mom_12_1"] = np.expm1(
        grp.transform(lambda s: s.shift(2).rolling(11, min_periods=MIN_OBS).sum())
    )

    # Reversal: prior month return
    df["ret_1m"] = grp.transform(lambda s: s.shift(1)).pipe(np.expm1)

    return df


def _load_permno_ticker_map(path: str = COMPUSTAT_PATH) -> pd.DataFrame:
    """Pull PERMNO → ticker mapping from Compustat (most recent row per PERMNO)."""
    cols = ["permno", "tic", "conm", "gvkey", "sich"]
    df = pd.read_parquet(path, engine="fastparquet", columns=cols)
    df = df.dropna(subset=["permno"])
    df["permno"] = df["permno"].astype(int)
    return df.groupby("permno").last().reset_index()


def compute_momentum(
    crsp_path: str = CRSP_PATH,
    compustat_path: str = COMPUSTAT_PATH,
    permno: int | None = None,
    latest_only: bool = True,
) -> pd.DataFrame:
    """
    Compute 12-1 month momentum and 1-month reversal for all PERMNOs.

    Parameters
    ----------
    crsp_path : str
        Path to crsp_m.dta.
    compustat_path : str
        Path to compustat_with_permno.parquet (for ticker labels).
    permno : int, optional
        Filter to a single PERMNO.
    latest_only : bool
        If True (default), return only the most recent month per PERMNO.

    Returns
    -------
    pd.DataFrame
        Columns:
          PERMNO, date, tic, conm, gvkey, sich,
          mom_12_1       — 12-1 month cumulative return (decimal)
          ret_1m         — prior month return (reversal signal)
          reversal_flag  — 1 if ret_1m is in the bottom decile of the universe
          mom_pct        — percentile rank of mom_12_1, 0–100 (higher = stronger)
    """
    df = _load_crsp(crsp_path)

    if permno is not None:
        df = df[df["PERMNO"] == permno]
        if df.empty:
            raise ValueError(f"PERMNO {permno} not found in CRSP data.")

    df = _compute_momentum_vectorized(df)

    if latest_only:
        df = df.sort_values("date").groupby("PERMNO").tail(1).copy()

    df = df.dropna(subset=["mom_12_1"])

    # Cross-sectional percentile ranks
    df["mom_pct"] = df["mom_12_1"].rank(pct=True, na_option="keep") * 100

    p10 = df["ret_1m"].quantile(0.10)
    df["reversal_flag"] = (df["ret_1m"] <= p10).astype(int)

    # Merge ticker labels
    ticker_map = _load_permno_ticker_map(compustat_path)
    df["PERMNO"] = df["PERMNO"].astype(int)
    df = df.merge(ticker_map, left_on="PERMNO", right_on="permno", how="left")

    out_cols = [
        "PERMNO", "date", "tic", "conm", "gvkey", "sich",
        "mom_12_1", "ret_1m", "reversal_flag", "mom_pct",
    ]
    return df[out_cols].reset_index(drop=True)


if __name__ == "__main__":
    mom = compute_momentum()
    print(f"PERMNOs scored: {mom['PERMNO'].nunique()}")
    print(f"\nMomentum stats:\n{mom['mom_12_1'].describe()}")
    print(f"\nReversal flags: {mom['reversal_flag'].sum()} / {len(mom)}")
    print(f"\nSample:\n{mom[['tic', 'date', 'mom_12_1', 'ret_1m', 'reversal_flag', 'mom_pct']].head(10).to_string()}")
