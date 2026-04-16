"""
Valuation multiples: EV/EBITDA and P/E ratio.

Formulas:
  EV        = Market Cap + Long-Term Debt + Current Portion of LT Debt - Cash
            = mkvaltq + dlttq + dlcq - cheq
  EBITDA    = Operating Income Before D&A (annual)  [oibdpy]
  EV/EBITDA = EV / EBITDA

  P/E       = Market Cap / Net Income  (mkvaltq / iby)
            (uses market cap / earnings rather than per-share to avoid
             share count mismatches)

Rationale: EV/EBITDA is capital-structure-neutral and less susceptible to
accounting distortions than P/E. Both are among the most commonly used
relative value signals in quant equity research.

Data: Compustat quarterly file (compustat_with_permno.parquet), filtered to
most recent quarter per ticker (not fqtr==4 only, so market cap is current).

Usage:
    from signals.valuation import compute_valuation
    val = compute_valuation()
    val = compute_valuation(ticker="AAPL")
"""

import pandas as pd
import numpy as np

PARQUET_PATH = "data/compustat_with_permno.parquet"

COLS_NEEDED = [
    "gvkey", "tic", "conm", "datadate", "fyearq", "fqtr",
    "mkvaltq",  # market value of equity (quarter end)
    "dlttq",    # long-term debt total
    "dlcq",     # current portion of long-term debt
    "cheq",     # cash and short-term investments
    "oibdpy",   # operating income before D&A (annual)
    "iby",      # net income (annual)
    "sich",
    "permno",
]


def _load_latest(path: str = PARQUET_PATH) -> pd.DataFrame:
    """
    Load Compustat. Balance sheet / market cap from the most recent quarter;
    annual income statement items (oibdpy, iby) from the most recent fiscal
    year-end row (fqtr==4) — those fields are YTD in Compustat quarterly files,
    so only the Q4 row contains the full-year figure.
    """
    df = pd.read_parquet(path, engine="fastparquet", columns=COLS_NEEDED)
    df = df.sort_values("datadate")

    # Balance sheet + market cap: most recent quarter with valid mkvaltq
    bs = (
        df.dropna(subset=["mkvaltq"])
        .query("mkvaltq > 0")
        .groupby("gvkey")
        .tail(1)
        [["gvkey", "tic", "conm", "datadate", "fyearq", "sich", "permno",
          "mkvaltq", "dlttq", "dlcq", "cheq"]]
    )

    # Annual income items: most recent fiscal year-end quarter (fqtr==4)
    ann = (
        df[df["fqtr"] == 4]
        .dropna(subset=["oibdpy"])
        .groupby("gvkey")
        .tail(1)
        [["gvkey", "oibdpy", "iby"]]
    )

    merged = bs.merge(ann, on="gvkey", how="left")
    return merged


def compute_valuation(
    path: str = PARQUET_PATH,
    ticker: str | None = None,
) -> pd.DataFrame:
    """
    Compute EV/EBITDA and P/E for all tickers (or one ticker).

    Uses the most recent available quarter's balance sheet for debt/cash/mktcap
    and the most recent annual EBITDA and net income (_y suffix).

    Parameters
    ----------
    path : str
        Path to compustat_with_permno.parquet.
    ticker : str, optional
        Filter to a single ticker.

    Returns
    -------
    pd.DataFrame
        Columns:
          gvkey, tic, conm, datadate, fyearq, sich, permno,
          market_cap         — mkvaltq ($ millions, Compustat units)
          enterprise_value   — EV = mktcap + debt - cash
          ebitda             — annual operating income before D&A
          ev_ebitda          — EV / EBITDA  (NaN if EBITDA <= 0)
          net_income         — annual net income
          pe_ratio           — market_cap / net_income  (NaN if NI <= 0)
          ev_ebitda_pct      — percentile rank, universe (0=cheapest, 100=most expensive)
          pe_pct             — percentile rank, universe (0=cheapest, 100=most expensive)
    """
    df = _load_latest(path)

    if ticker is not None:
        df = df[df["tic"].str.upper() == ticker.upper()]
        if df.empty:
            raise ValueError(f"Ticker '{ticker}' not found in Compustat data.")

    df["market_cap"] = df["mkvaltq"]

    total_debt = df["dlttq"].fillna(0) + df["dlcq"].fillna(0)
    cash = df["cheq"].fillna(0)
    df["enterprise_value"] = df["market_cap"] + total_debt - cash

    df["ebitda"] = df["oibdpy"]
    df["net_income"] = df["iby"]

    # EV/EBITDA: undefined / misleading for negative EBITDA
    df["ev_ebitda"] = np.where(
        df["ebitda"] > 0,
        df["enterprise_value"] / df["ebitda"],
        np.nan,
    )

    # P/E: undefined for negative earnings
    df["pe_ratio"] = np.where(
        df["net_income"] > 0,
        df["market_cap"] / df["net_income"],
        np.nan,
    )

    # Percentile ranks: higher rank = more expensive (worse value)
    df["ev_ebitda_pct"] = (
        df["ev_ebitda"].rank(pct=True, na_option="keep") * 100
    )
    df["pe_pct"] = (
        df["pe_ratio"].rank(pct=True, na_option="keep") * 100
    )

    out_cols = [
        "gvkey", "tic", "conm", "datadate", "fyearq", "sich", "permno",
        "market_cap", "enterprise_value", "ebitda", "ev_ebitda",
        "net_income", "pe_ratio", "ev_ebitda_pct", "pe_pct",
    ]
    return df[out_cols].reset_index(drop=True)


if __name__ == "__main__":
    val = compute_valuation()
    print(f"Tickers scored: {val['tic'].nunique()}")
    print(f"\nEV/EBITDA stats:\n{val['ev_ebitda'].describe()}")
    print(f"\nP/E stats:\n{val['pe_ratio'].describe()}")
    print(f"\nSample:\n{val[['tic', 'fyearq', 'ev_ebitda', 'pe_ratio', 'ev_ebitda_pct', 'pe_pct']].head(10).to_string()}")
