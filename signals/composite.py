"""
Composite quant score builder.

Joins all 5 signal modules, direction-corrects each to a 0–100 percentile
where higher always means "better", then takes the equal-weighted average
as the composite score.

Signal directions after correction (all: higher = better):
  1. F-Score       fscore_pct          percentile rank of raw F-Score (0–9)
  2. Gross Profit  gp_pct_universe     direct from gross_profitability.py
  3. Earn. Quality accruals_quality_pct = 100 - accruals_pct  (inverted)
  4. Valuation     value_pct           = mean(100-ev_ebitda_pct, 100-pe_pct)
                                         (cheaper = better; uses whichever
                                          multiples are available)
  5. Momentum      mom_pct             direct from momentum.py

Composite score = equal-weighted mean across available signals per ticker.
Tickers missing a signal are still scored over the remaining signals and a
"signals_used" column records how many contributed.

Exports: data/quant_metrics.parquet — one row per ticker, latest period.

Usage:
    python signals/composite.py          # builds and exports quant_metrics.parquet
    from signals.composite import build_composite
    metrics = build_composite()
"""

import pandas as pd
import numpy as np

from signals.fscore import compute_fscore
from signals.gross_profitability import compute_gross_profitability
from signals.accruals import compute_accruals
from signals.valuation import compute_valuation
from signals.momentum import compute_momentum

OUTPUT_PATH = "data/quant_metrics.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rank_pct(series: pd.Series) -> pd.Series:
    """Percentile rank (0–100), NaN-safe."""
    return series.rank(pct=True, na_option="keep") * 100


def _load_fscore() -> pd.DataFrame:
    df = compute_fscore(latest_only=True)
    df["fscore_pct"] = _rank_pct(df["fscore"])
    keep = ["permno", "tic", "conm", "gvkey", "sich", "fyearq",
            "fscore", "fscore_pct",
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
            "roa", "cfo_assets", "leverage", "current_ratio",
            "gross_margin", "asset_turnover"]
    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    return df[keep].dropna(subset=["permno"])


def _load_gp() -> pd.DataFrame:
    df = compute_gross_profitability(latest_only=True)
    keep = ["permno", "gp_ratio", "gp_pct_universe", "gp_pct_sector", "sector"]
    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    return df[keep].dropna(subset=["permno"])


def _load_accruals() -> pd.DataFrame:
    df = compute_accruals(latest_only=True)
    # Invert: lower accruals = higher quality score
    df["accruals_quality_pct"] = 100 - df["accruals_pct"]
    keep = ["permno", "net_income", "cfo", "total_assets",
            "accruals_ratio", "accruals_pct", "accruals_quality_pct",
            "high_accruals"]
    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    return df[keep].dropna(subset=["permno"])


def _load_valuation() -> pd.DataFrame:
    df = compute_valuation()
    # Invert: cheaper = better value score
    df["ev_ebitda_value_pct"] = 100 - df["ev_ebitda_pct"]
    df["pe_value_pct"] = 100 - df["pe_pct"]
    # Average whichever multiples are available
    df["value_pct"] = df[["ev_ebitda_value_pct", "pe_value_pct"]].mean(axis=1, skipna=True)
    # Set NaN if both multiples are unavailable
    both_null = df["ev_ebitda_pct"].isna() & df["pe_pct"].isna()
    df.loc[both_null, "value_pct"] = np.nan
    keep = ["permno", "market_cap", "enterprise_value", "ebitda",
            "ev_ebitda", "pe_ratio", "ev_ebitda_pct", "pe_pct", "value_pct"]
    df["permno"] = pd.to_numeric(df["permno"], errors="coerce")
    return df[keep].dropna(subset=["permno"])


def _load_momentum() -> pd.DataFrame:
    df = compute_momentum(latest_only=True)
    df = df.rename(columns={"PERMNO": "permno"})
    keep = ["permno", "mom_12_1", "ret_1m", "reversal_flag", "mom_pct"]
    return df[keep].dropna(subset=["permno"])


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_composite() -> pd.DataFrame:
    """
    Build the master quant metrics table.

    Returns
    -------
    pd.DataFrame
        One row per ticker (latest available period). Columns:
          Identity:    permno, tic, conm, gvkey, sich, sector, fyearq
          F-Score:     fscore (0–9), F1–F9, fscore_pct, + underlying ratios
          GP:          gp_ratio, gp_pct_universe, gp_pct_sector
          Accruals:    accruals_ratio, accruals_quality_pct, high_accruals
          Valuation:   ev_ebitda, pe_ratio, value_pct, market_cap
          Momentum:    mom_12_1, ret_1m, reversal_flag, mom_pct
          Composite:   composite_score (0–100, equal-weighted avg of 5 signals)
                       signals_used    (how many of the 5 contributed)
    """
    print("Loading F-Score...")
    fs = _load_fscore()
    print("Loading Gross Profitability...")
    gp = _load_gp()
    print("Loading Accruals...")
    ac = _load_accruals()
    print("Loading Valuation...")
    va = _load_valuation()
    print("Loading Momentum...")
    mo = _load_momentum()

    # Join on permno — start with F-Score as spine (broadest coverage)
    df = fs.copy()
    df["permno"] = df["permno"].astype(int)

    for other, label in [(gp, "GP"), (ac, "Accruals"), (va, "Valuation"), (mo, "Momentum")]:
        other = other.copy()
        other["permno"] = other["permno"].astype(int)
        df = df.merge(other, on="permno", how="outer")
        print(f"  After joining {label}: {len(df):,} rows")

    # Fill identity columns from whichever side provided them
    for col in ["tic", "conm", "gvkey"]:
        if f"{col}_x" in df.columns:
            df[col] = df[f"{col}_x"].combine_first(df.get(f"{col}_y"))
            df = df.drop(columns=[c for c in df.columns if c in (f"{col}_x", f"{col}_y")])

    # --- Composite score ---
    signal_cols = ["fscore_pct", "gp_pct_universe", "accruals_quality_pct",
                   "value_pct", "mom_pct"]
    df["composite_score"] = df[signal_cols].mean(axis=1, skipna=True)
    df["signals_used"] = df[signal_cols].notna().sum(axis=1)
    # Require at least 3 of 5 signals to assign a composite score
    df.loc[df["signals_used"] < 3, "composite_score"] = np.nan

    # Overall percentile rank of composite (useful for dashboard)
    df["composite_pct"] = _rank_pct(df["composite_score"])

    print(f"\nFinal universe: {df['permno'].nunique():,} tickers")
    print(f"Composite scored (3+ signals): {df['composite_score'].notna().sum():,}")
    print(f"\nComposite score distribution:\n{df['composite_score'].describe()}")

    return df.reset_index(drop=True)


def export_metrics(path: str = OUTPUT_PATH) -> pd.DataFrame:
    """Build composite and write to parquet. Returns the DataFrame."""
    df = build_composite()
    # Normalize Arrow-backed string dtypes → plain object so fastparquet can write them
    for col in df.select_dtypes(include="string").columns:
        df[col] = df[col].astype(object)
    df.to_parquet(path, engine="fastparquet", index=False)
    print(f"\nExported -> {path}  ({len(df):,} rows, {len(df.columns)} cols)")
    return df


if __name__ == "__main__":
    export_metrics()
