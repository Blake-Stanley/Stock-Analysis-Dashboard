"""
sentiment/trend.py

Quarter-over-quarter sentiment trend tracker and parquet exporter.

Ties together the full sentiment pipeline:
  fetch_transcripts → score_transcript_list → QoQ deltas → parquet

Public API
----------
    # Single ticker (used by dashboard at runtime)
    df = build_ticker_sentiment("AAPL", n_quarters=6)

    # Batch export (run once to pre-populate data/sentiment_scores.parquet)
    export_sentiment_scores(["AAPL", "MSFT", "NVDA", ...], "data/sentiment_scores.parquet")

    # Load cached scores for a ticker (dashboard fast path)
    df = load_ticker_sentiment("AAPL", "data/sentiment_scores.parquet")

Output DataFrame schema (one row per ticker-quarter)
-----------------------------------------------------
    ticker          str
    date            str  (YYYY-MM-DD, the 8-K filing date)
    quarter_label   str  (e.g. "Q3 2024")
    tone_score      float  [-1, 1]
    hedging_score   float  [0, 1]
    confidence_score float [0, 1]
    tone_qoq        float  delta vs prior quarter (NaN for oldest)
    hedging_qoq     float
    confidence_qoq  float
    tone_trend      str    "improving" | "declining" | "stable" | "n/a"
    hedging_trend   str
    confidence_trend str
    -- plus all diagnostic columns from TranscriptScores --
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd

from sentiment.fetch_motley_fool import fetch_earnings_transcripts
from sentiment.score import score_transcript_list


# ---------------------------------------------------------------------------
# QoQ delta computation
# ---------------------------------------------------------------------------

# How large a delta must be to count as "improving" or "declining"
_TONE_THRESHOLD = 0.05
_HEDGING_THRESHOLD = 0.005
_CONFIDENCE_THRESHOLD = 0.03


def _trend_label(delta: float, threshold: float, higher_is_better: bool) -> str:
    """Convert a QoQ delta into a human-readable trend label."""
    if pd.isna(delta):
        return "n/a"
    if abs(delta) < threshold:
        return "stable"
    improving = delta > 0 if higher_is_better else delta < 0
    return "improving" if improving else "declining"


def compute_qoq(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add quarter-over-quarter delta and trend columns to a scores DataFrame.

    Expects columns: ticker, date, tone_score, hedging_score, confidence_score.
    Rows within each ticker are sorted oldest→newest before differencing.

    Returns a new DataFrame with additional columns:
      tone_qoq, hedging_qoq, confidence_qoq,
      tone_trend, hedging_trend, confidence_trend
    """
    if df.empty:
        for col in [
            "tone_qoq", "hedging_qoq", "confidence_qoq",
            "tone_trend", "hedging_trend", "confidence_trend",
        ]:
            df[col] = pd.NA
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    for score_col in ["tone_score", "hedging_score", "confidence_score"]:
        qoq_col = score_col.replace("_score", "_qoq")
        df[qoq_col] = df.groupby("ticker")[score_col].diff()

    # Trend labels
    df["tone_trend"] = df["tone_qoq"].apply(
        lambda d: _trend_label(d, _TONE_THRESHOLD, higher_is_better=True)
    )
    df["hedging_trend"] = df["hedging_qoq"].apply(
        lambda d: _trend_label(d, _HEDGING_THRESHOLD, higher_is_better=False)
    )
    df["confidence_trend"] = df["confidence_qoq"].apply(
        lambda d: _trend_label(d, _CONFIDENCE_THRESHOLD, higher_is_better=True)
    )

    # Restore date as string for parquet compatibility
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    return df


# ---------------------------------------------------------------------------
# Single-ticker pipeline
# ---------------------------------------------------------------------------

def build_ticker_sentiment(
    ticker: str,
    n_quarters: int = 6,
    *,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Full pipeline for one ticker: fetch → score → QoQ deltas.

    Parameters
    ----------
    ticker : str
        US equity ticker.
    n_quarters : int
        How many quarters to fetch (most recent first).
    verbose : bool
        Print progress.

    Returns
    -------
    pd.DataFrame
        Scored rows with QoQ columns, sorted oldest→newest.
        Empty DataFrame if no EDGAR transcripts found.
    """
    ticker = ticker.upper()

    if verbose:
        print(f"[{ticker}] Fetching transcripts ...")
    transcripts = fetch_earnings_transcripts(ticker, n_quarters=n_quarters)

    if not transcripts:
        if verbose:
            print(f"[{ticker}] No transcripts found on EDGAR.")
        return pd.DataFrame()

    if verbose:
        print(f"[{ticker}] Scoring {len(transcripts)} quarter(s) ...")
    scores_df = score_transcript_list(transcripts, verbose=verbose)

    df = compute_qoq(scores_df)
    return df


# ---------------------------------------------------------------------------
# Batch export
# ---------------------------------------------------------------------------

def export_sentiment_scores(
    tickers: list[str],
    output_path: str = "data/sentiment_scores.parquet",
    n_quarters: int = 6,
    *,
    verbose: bool = True,
    skip_existing: bool = False,
) -> pd.DataFrame:
    """
    Run the full pipeline for each ticker and write results to parquet.

    Parameters
    ----------
    tickers : list[str]
        List of US equity tickers to process.
    output_path : str
        Destination parquet path (created or overwritten).
    n_quarters : int
        Quarters to fetch per ticker.
    verbose : bool
        Print progress.
    skip_existing : bool
        If True and output_path already exists, skip tickers already present
        in the file (useful for incremental updates).

    Returns
    -------
    pd.DataFrame
        The full combined DataFrame written to disk.
    """
    existing: Optional[pd.DataFrame] = None
    existing_tickers: set[str] = set()

    if skip_existing and Path(output_path).exists():
        try:
            existing = pd.read_parquet(output_path, engine="fastparquet")
            existing_tickers = set(existing["ticker"].unique())
            if verbose:
                print(f"Loaded existing file with {len(existing_tickers)} tickers.")
        except Exception as e:
            if verbose:
                print(f"Could not load existing file: {e}")

    frames: list[pd.DataFrame] = [existing] if existing is not None else []

    for ticker in tickers:
        if skip_existing and ticker.upper() in existing_tickers:
            if verbose:
                print(f"[{ticker}] Skipping (already in parquet).")
            continue

        df = build_ticker_sentiment(ticker, n_quarters=n_quarters, verbose=verbose)
        if not df.empty:
            frames.append(df)
            if verbose:
                print(f"[{ticker}] {len(df)} row(s) added.")
        else:
            if verbose:
                print(f"[{ticker}] No data.")

    if not frames:
        if verbose:
            print("No data collected — parquet not written.")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
    os.makedirs(Path(output_path).parent, exist_ok=True)
    combined.to_parquet(output_path, engine="pyarrow", index=False)

    if verbose:
        print(f"\nWrote {len(combined)} rows -> {output_path}")

    return combined


# ---------------------------------------------------------------------------
# Dashboard fast path — load cached scores for one ticker
# ---------------------------------------------------------------------------

def load_ticker_sentiment(
    ticker: str,
    parquet_path: str = "data/sentiment_scores.parquet",
) -> pd.DataFrame:
    """
    Load pre-computed sentiment scores for *ticker* from the parquet cache.

    Returns empty DataFrame if the file doesn't exist or the ticker is absent.
    Falls back to live fetch if cache is missing (so dashboard never crashes).
    """
    ticker = ticker.upper()

    if Path(parquet_path).exists():
        try:
            df = pd.read_parquet(parquet_path, engine="pyarrow")
            result = df[df["ticker"] == ticker].copy()
            if not result.empty:
                return result.sort_values("date").reset_index(drop=True)
        except Exception:
            pass

    # Cache miss — fetch live (slower but dashboard stays functional)
    return build_ticker_sentiment(ticker, n_quarters=6)


# ---------------------------------------------------------------------------
# Smoke-test (python -m sentiment.trend)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    test_tickers = sys.argv[1:] or ["AAPL", "MSFT"]
    print(f"Running sentiment pipeline for: {test_tickers}\n")

    all_frames = []
    for ticker in test_tickers:
        df = build_ticker_sentiment(ticker, n_quarters=4, verbose=True)
        if df.empty:
            print(f"  [{ticker}] not available\n")
            continue
        all_frames.append(df)
        print(f"\n  [{ticker}] results:")
        cols = ["quarter_label", "tone_score", "hedging_score",
                "confidence_score", "tone_qoq", "tone_trend"]
        print(df[cols].to_string(index=False))
        print()

    if all_frames:
        out = "data/sentiment_scores_test.parquet"
        combined = pd.concat(all_frames, ignore_index=True)
        combined.to_parquet(out, engine="fastparquet", index=False)
        print(f"Test parquet written → {out}  ({len(combined)} rows)")
