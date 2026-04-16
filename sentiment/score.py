"""
sentiment/score.py

Score earnings call transcripts on three dimensions:

  tone_score      [-1.0, +1.0]  — VADER compound sentiment on management text.
                                  Positive = optimistic/bullish language.

  hedging_score   [0.0,  1.0]   — Fraction of management words that appear in
                                  the Loughran-McDonald (2011) uncertainty word
                                  list. Higher = more hedging / equivocal language.

  confidence_score [0.0, 1.0]   — Forward-looking sentence ratio, penalised by
                                  hedging. Captures "are executives making concrete
                                  predictions, or are they hedging everything?"

Usage
-----
    from sentiment.parse_transcripts import parse_transcript
    from sentiment.score import score_transcript, score_transcript_list

    parsed = parse_transcript(raw_text)
    scores = score_transcript(parsed)          # → TranscriptScores

    # For a full ticker run (returns DataFrame):
    df = score_transcript_list(transcripts)   # list of fetch_transcripts dicts
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from sentiment.parse_transcripts import ParsedTranscript, parse_transcript


# ---------------------------------------------------------------------------
# Loughran-McDonald (2011) Uncertainty / Hedging Word List
# Source: "When Is a Liability Not a Liability?" J. Finance 2011, Table A1
# This is the uncertainty category (297 words); we embed the full list here
# so there is no runtime HTTP call.
# ---------------------------------------------------------------------------

_LM_UNCERTAINTY_WORDS: frozenset[str] = frozenset("""
abnormalities abrupt absence acceptable accuracy adequate adequately
adjust adjustable adjusting adjustment adjustments ambiguity ambiguous
anomalies anomalous anomaly apparent apparently appear appeared appears
approximate approximately approximating approximation approximations
approximations assume assumed assumes assuming assumption assumptions
atypical background believe believe believed believes believing
cautious cautiously cautiously cautionary chances challenging changed
changes changing circumstance circumstances comparable compared
comparisons complexity complication complications consider considerable
considerably considering consistent constraints contingencies contingency
contingent controversy controversial could curbed cyclical
debate debatable debating decline declining deferred depend depending
dependent differs difficult difficulties difficulty diminishing doubt
doubted doubtful doubts downturn downturns drops dynamic dynamics
emphasis estimate estimated estimates estimating estimation evaluating
evaluation evaluations exception exceptional exceptions expect expectation
expectations expected expecting experience experienced experiencing
exposure fail failed failing failure failures fair fairly favor
feel felt fluctuate fluctuated fluctuates fluctuating fluctuation
fluctuations forecasted fully generally gradual gradually guess
harder hardship headwind headwinds higher historically hope hoped
hoping hypothesis hypothetical if impact impacts imprecise inadequate
indirect indirectly indeterminate indeterminate influence influenced
involves involving irregularities irregularity issues know known
largely likely limit limited limiting limitations limits lower magnitude
manageable may maybe meaningful merits might moderate moderately
mostly nearly needs negative perhaps plausible possible possibly
potential potentially predict predicted predicting prediction predictions
preliminary probably problem problems projected projection projections
reasonable reasonably refine reflect reflected reflecting reflects
relatively remain remaining remains require requirement requirements
risk risks risky seemingly sensitive sensitivity should shortfall
shortfalls significant significantly sometime sometimes speculate
speculative subjective subsequent subsequently suggest suggested
suggesting suggestion suggestions suitable susceptible tentative
though typically uncertain uncertainties uncertainty undetermined
unexpected unfavorable unknown unlikely unpredictable unpredictably
unusual usually variable variables various vary varying versus
volatility vulnerable whenever whether yet
""".split())

# Forward-looking keywords — sentences containing these are forward-looking
_FORWARD_LOOKING_WORDS: frozenset[str] = frozenset([
    "expect", "expects", "expected", "expecting",
    "anticipate", "anticipates", "anticipated", "anticipating",
    "forecast", "forecasts", "forecasted", "forecasting",
    "guidance", "outlook", "target", "targets",
    "project", "projects", "projected", "projecting",
    "plan", "plans", "planned", "planning",
    "intend", "intends", "intended", "intending",
    "will", "would", "should", "going forward",
    "next quarter", "next year", "full year", "fiscal year",
    "remainder of", "second half", "first half",
])


# ---------------------------------------------------------------------------
# Dataclass for scores
# ---------------------------------------------------------------------------

@dataclass
class TranscriptScores:
    # Primary scores (these go into sentiment_scores.parquet)
    tone_score: float            # VADER compound [-1, 1]
    hedging_score: float         # L-M uncertainty word fraction [0, 1]
    confidence_score: float      # forward-looking ratio, hedging-penalised [0, 1]

    # Diagnostics (useful for debugging / dashboard tooltips)
    vader_positive: float
    vader_negative: float
    vader_neutral: float
    hedging_word_count: int
    total_word_count: int
    forward_looking_sentences: int
    total_sentences: int
    n_executive_turns: int
    n_analyst_turns: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Scorer internals
# ---------------------------------------------------------------------------

_analyzer = SentimentIntensityAnalyzer()


def _vader_scores(text: str) -> dict[str, float]:
    """
    Score text by averaging sentence-level VADER compound scores.

    Running VADER on a full transcript (~9k words) causes the compound score
    to saturate at ±1 because valence accumulates across hundreds of sentences.
    Sentence-level averaging keeps the score in a meaningful range.
    """
    if not text.strip():
        return {"compound": 0.0, "pos": 0.0, "neg": 0.0, "neu": 1.0}

    sentences = _split_sentences(text)
    if not sentences:
        return {"compound": 0.0, "pos": 0.0, "neg": 0.0, "neu": 1.0}

    totals = {"compound": 0.0, "pos": 0.0, "neg": 0.0, "neu": 0.0}
    for sent in sentences:
        s = _analyzer.polarity_scores(sent)
        for k in totals:
            totals[k] += s[k]

    n = len(sentences)
    return {k: round(v / n, 4) for k, v in totals.items()}


def _tokenize_words(text: str) -> list[str]:
    """Lowercase alpha tokens only (matches L-M word list format)."""
    return re.findall(r"[a-z]+", text.lower())


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter — adequate for transcript prose."""
    # Split on . ! ? followed by whitespace or end-of-string
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _hedging_score(words: list[str]) -> tuple[float, int]:
    """Return (fraction of hedging words, raw count)."""
    if not words:
        return 0.0, 0
    count = sum(1 for w in words if w in _LM_UNCERTAINTY_WORDS)
    return count / len(words), count


def _forward_looking_ratio(sentences: list[str]) -> tuple[float, int]:
    """
    Return (forward-looking sentence fraction, count).
    A sentence is forward-looking if it contains at least one FL keyword.
    """
    if not sentences:
        return 0.0, 0
    fl_count = 0
    for sent in sentences:
        sent_lower = sent.lower()
        if any(kw in sent_lower for kw in _FORWARD_LOOKING_WORDS):
            fl_count += 1
    return fl_count / len(sentences), fl_count


def _confidence_score(fl_ratio: float, hedging: float) -> float:
    """
    Combine forward-looking ratio and hedging into a single confidence score.

    High FL + low hedging  → high confidence (executives making concrete claims)
    High FL + high hedging → moderate (lots of predictions but all qualified)
    Low FL + any hedging   → low confidence (not saying much about the future)

    Formula: fl_ratio * (1 - 0.5 * hedging)
    The 0.5 weight keeps hedging from zeroing out legitimate FL content.
    Clipped to [0, 1].
    """
    raw = fl_ratio * (1.0 - 0.5 * hedging)
    return min(max(raw, 0.0), 1.0)


# ---------------------------------------------------------------------------
# Public scoring functions
# ---------------------------------------------------------------------------

def score_transcript(parsed: ParsedTranscript) -> TranscriptScores:
    """
    Compute tone, hedging, and confidence scores for a parsed transcript.

    Scoring is done on management_text (all executive turns from both prepared
    remarks and Q&A).  If the parser found no speaker turns (common with
    non-standard EDGAR transcript formats), falls back to scoring the full
    prepared-remarks section, then the full transcript text.
    Analyst text is never scored — it would dilute the signal.

    Parameters
    ----------
    parsed : ParsedTranscript
        Output of sentiment.parse_transcripts.parse_transcript().

    Returns
    -------
    TranscriptScores
    """
    mgmt_text = parsed.management_text

    # Fallback: speaker-turn parser found nothing (non-standard EDGAR format).
    # Use prepared remarks (predominantly management content); if that's also
    # empty, combine both sections so we score something meaningful.
    if not mgmt_text.strip():
        mgmt_text = (parsed.prepared_remarks_text.strip()
                     or (parsed.prepared_remarks_text + "\n" + parsed.qa_text).strip())

    # --- Tone (VADER) ---
    vader = _vader_scores(mgmt_text)

    # --- Hedging (L-M uncertainty) ---
    words = _tokenize_words(mgmt_text)
    h_score, h_count = _hedging_score(words)

    # --- Forward-looking confidence ---
    sentences = _split_sentences(mgmt_text)
    fl_ratio, fl_count = _forward_looking_ratio(sentences)
    conf_score = _confidence_score(fl_ratio, h_score)

    # --- Turn counts ---
    n_exec = sum(1 for t in parsed.turns if t.role == "executive")
    n_analyst = sum(1 for t in parsed.turns if t.role == "analyst")

    return TranscriptScores(
        tone_score=round(vader["compound"], 4),
        hedging_score=round(h_score, 4),
        confidence_score=round(conf_score, 4),
        vader_positive=round(vader["pos"], 4),
        vader_negative=round(vader["neg"], 4),
        vader_neutral=round(vader["neu"], 4),
        hedging_word_count=h_count,
        total_word_count=len(words),
        forward_looking_sentences=fl_count,
        total_sentences=len(sentences),
        n_executive_turns=n_exec,
        n_analyst_turns=n_analyst,
    )


def score_transcript_list(
    transcripts: list[dict],
    *,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Score a list of transcript dicts (as returned by fetch_earnings_transcripts).

    Parameters
    ----------
    transcripts : list[dict]
        Each dict must have keys: ticker, date, quarter_label, transcript_text.
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    pd.DataFrame
        One row per transcript, columns: ticker, date, quarter_label,
        tone_score, hedging_score, confidence_score,
        + all diagnostic columns from TranscriptScores.
    """
    rows = []
    for t in transcripts:
        if verbose:
            print(f"  Scoring {t['ticker']} {t['quarter_label']} ...")
        try:
            parsed = parse_transcript(t["transcript_text"])
            scores = score_transcript(parsed)
            row = {
                "ticker": t["ticker"],
                "date": t["date"],
                "quarter_label": t["quarter_label"],
                **scores.to_dict(),
            }
        except Exception as exc:
            if verbose:
                print(f"    ERROR: {exc}")
            row = {
                "ticker": t["ticker"],
                "date": t["date"],
                "quarter_label": t["quarter_label"],
                "tone_score": None,
                "hedging_score": None,
                "confidence_score": None,
            }
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Score interpretation helpers (used by dashboard tooltips and AI prompt)
# ---------------------------------------------------------------------------

def interpret_tone(score: float) -> str:
    if score >= 0.35:
        return "strongly positive"
    if score >= 0.10:
        return "mildly positive"
    if score >= -0.10:
        return "neutral"
    if score >= -0.35:
        return "mildly negative"
    return "strongly negative"


def interpret_hedging(score: float) -> str:
    if score >= 0.08:
        return "high hedging"
    if score >= 0.04:
        return "moderate hedging"
    return "low hedging"


def interpret_confidence(score: float) -> str:
    if score >= 0.35:
        return "high confidence"
    if score >= 0.15:
        return "moderate confidence"
    return "low confidence"


# ---------------------------------------------------------------------------
# Quick smoke-test (python -m sentiment.score)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from sentiment.fetch_transcripts import fetch_earnings_transcripts

    test_tickers = sys.argv[1:] or ["AAPL", "MSFT"]
    print(f"Fetching + scoring transcripts for: {test_tickers}\n")

    for ticker in test_tickers:
        print(f"=== {ticker} ===")
        transcripts = fetch_earnings_transcripts(ticker, n_quarters=2)
        if not transcripts:
            print("  [not available]\n")
            continue

        df = score_transcript_list(transcripts, verbose=True)
        for _, row in df.iterrows():
            tone_i = interpret_tone(row["tone_score"])
            hedge_i = interpret_hedging(row["hedging_score"])
            conf_i = interpret_confidence(row["confidence_score"])
            print(
                f"  {row['quarter_label']}  "
                f"tone={row['tone_score']:+.3f} ({tone_i})  "
                f"hedging={row['hedging_score']:.3f} ({hedge_i})  "
                f"confidence={row['confidence_score']:.3f} ({conf_i})"
            )
        print()
