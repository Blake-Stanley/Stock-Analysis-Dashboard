"""
ai/prompt_template.py

Formats quant signal data and sentiment scores into a structured prompt for
the Claude synthesis call.

Public API
----------
    system_prompt() -> str          # cached system block (methodology context)
    build_user_message(row, sent_df, ticker) -> str   # ticker-specific context
"""

from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# System prompt — cached (passed with cache_control in synthesize.py)
# ---------------------------------------------------------------------------

_SYSTEM = """You are a quantitative equity research analyst. Given structured data on \
a stock's fundamental quality signals and earnings call sentiment, you produce a concise \
bull/bear synthesis for an academic research dashboard.

## Signal definitions

**Piotroski F-Score (0–9)**
Nine binary tests across three pillars: profitability (F1–F3), leverage/liquidity (F4–F6), \
and operating efficiency (F7–F9). Score ≥7 = strong, ≤3 = weak. Percentile rank is vs. \
the full universe in the pre-computed dataset.

**Gross Profitability (Novy-Marx)**
(Revenue − COGS) / Total Assets. Higher = more efficient economic moat. Both a \
universe and a sector percentile rank are provided.

**Earnings Quality / Accruals**
Accruals ratio = (Net Income − CFO) / Assets. Lower (more negative) is better — \
means earnings are backed by cash flow. High accruals flag means top-decile accruals \
(earnings quality concern).

**Valuation**
EV/EBITDA and P/E ratios with universe percentile ranks. Lower percentile = cheaper.

**Momentum (12-1M)**
12-month return excluding the most recent month. Reversal flag = prior-month return \
was in the bottom decile (short-term reversal risk). Higher momentum percentile = \
stronger price trend.

**Sentiment Scores (from earnings call transcripts)**
- Tone: VADER compound sentiment on management speech [-1, +1]. Higher = more optimistic.
- Hedging: Loughran-McDonald uncertainty word fraction [0, 1]. Higher = more equivocal.
- Confidence: Forward-looking sentence ratio penalised by hedging [0, 1]. Higher = \
  more concrete guidance.
- QoQ trends: improving / stable / declining.

## Output format

Respond with ONLY a JSON object — no prose outside the JSON:
{
  "bull": "<2–3 sentences highlighting the strongest signals and why they are bullish>",
  "bear": "<2–3 sentences highlighting the weakest signals and key risks>",
  "risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "divergence_flag": true | false,
  "divergence_note": "<one sentence explaining the divergence, or empty string if none>"
}

Divergence = quant signals and sentiment clearly point in opposite directions \
(e.g. strong fundamentals but cautious/declining management tone, or weak quant \
but highly optimistic management language). Only flag true divergences.

Keep the output concise and grounded in the numbers provided. Do not make up data.
"""


def system_prompt() -> str:
    return _SYSTEM


# ---------------------------------------------------------------------------
# User message builder
# ---------------------------------------------------------------------------

def _fmt(val, fmt: str = ".2f", na: str = "N/A") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return na
    try:
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return str(val)


def _pct(val, na: str = "N/A") -> str:
    """Format a 0-100 percentile rank."""
    return _fmt(val, ".1f", na)


def build_user_message(
    row: pd.Series,
    ticker: str,
    sent_df: pd.DataFrame | None,
) -> str:
    """
    Format all available signals for *ticker* into a structured text block
    for the Claude user message.

    Parameters
    ----------
    row : pd.Series
        Row from quant_metrics.parquet for this ticker.
    ticker : str
        Ticker symbol.
    sent_df : pd.DataFrame | None
        Pre-filtered sentiment rows for this ticker (already sorted oldest→newest),
        or None if unavailable.
    """
    company = row.get("conm", ticker)
    sector = row.get("sector", "N/A")
    if pd.isna(sector):
        sector = "N/A"

    lines: list[str] = [
        f"## {ticker} — {company}",
        f"Sector: {sector}",
        "",
        "### Composite Quant Score",
        f"  Composite score: {_pct(row.get('composite_score'))} / 100  "
        f"(signals used: {int(row.get('signals_used', 0)) if pd.notna(row.get('signals_used')) else 'N/A'})",
        f"  Composite percentile rank: {_pct(row.get('composite_pct'))}th",
        "",
        "### Piotroski F-Score",
        f"  Total: {_fmt(row.get('fscore'), '.0f')} / 9  "
        f"(universe pct: {_pct(row.get('fscore_pct'))}th)",
    ]

    # F-Score components
    f_labels = {
        "F1": "ROA positive",
        "F2": "Operating CF positive",
        "F3": "ROA improving",
        "F4": "Leverage decreasing",
        "F5": "Current ratio improving",
        "F6": "No share dilution",
        "F7": "Gross margin improving",
        "F8": "Asset turnover improving",
        "F9": "Accruals (CF > NI)",
    }
    component_parts = []
    for f, label in f_labels.items():
        v = row.get(f)
        if pd.notna(v):
            component_parts.append(f"{f}({label})={'PASS' if int(v) else 'FAIL'}")
    if component_parts:
        lines.append("  Components: " + ", ".join(component_parts))

    lines += [
        "",
        "### Gross Profitability (Novy-Marx)",
        f"  GP ratio: {_fmt(row.get('gp_ratio'))}",
        f"  Universe pct: {_pct(row.get('gp_pct_universe'))}th  |  "
        f"Sector pct: {_pct(row.get('gp_pct_sector'))}th",
        "",
        "### Earnings Quality / Accruals",
        f"  Accruals ratio: {_fmt(row.get('accruals_ratio'), '.4f')}",
        f"  Quality pct (lower accruals = better): {_pct(row.get('accruals_quality_pct'))}th",
        f"  High accruals flag: {bool(row.get('high_accruals', False))}",
        "",
        "### Valuation",
        f"  EV/EBITDA: {_fmt(row.get('ev_ebitda'))}  (universe pct: {_pct(row.get('ev_ebitda_pct'))}th)",
        f"  P/E ratio: {_fmt(row.get('pe_ratio'))}  (value pct: {_pct(row.get('value_pct'))}th)",
        "",
        "### Momentum (12-1M)",
        f"  12-1M return: {_fmt(row.get('mom_12_1'), '.2%')}",
        f"  Momentum pct: {_pct(row.get('mom_pct'))}th",
        f"  Prior-month return: {_fmt(row.get('ret_1m'), '.2%')}",
        f"  Reversal flag (bottom-decile prior month): {bool(row.get('reversal_flag', False))}",
    ]

    # Sentiment section
    lines += ["", "### Earnings Call Sentiment"]

    if sent_df is not None and not sent_df.empty:
        # sent_df is already filtered to this ticker and sorted oldest→newest
        latest = sent_df.iloc[-1]
        n_quarters = len(sent_df)

        lines += [
            f"  Latest quarter: {latest.get('quarter_label', 'N/A')}  "
            f"({n_quarters} quarter(s) available)",
            f"  Tone: {_fmt(latest.get('tone_score'), '+.3f')}  "
            f"(trend: {latest.get('tone_trend', 'n/a')})",
            f"  Hedging: {_fmt(latest.get('hedging_score'), '.3f')}  "
            f"(trend: {latest.get('hedging_trend', 'n/a')})",
            f"  Confidence: {_fmt(latest.get('confidence_score'), '.3f')}  "
            f"(trend: {latest.get('confidence_trend', 'n/a')})",
        ]

        if n_quarters > 1:
            lines.append("  Recent QoQ changes:")
            for _, r in sent_df.tail(3).iterrows():
                tone_qoq = r.get("tone_qoq")
                tone_qoq_str = f"{float(tone_qoq):+.3f}" if pd.notna(tone_qoq) else "—"
                lines.append(
                    f"    {r.get('quarter_label', '?')}: "
                    f"tone={_fmt(r.get('tone_score'), '+.3f')} (Δ{tone_qoq_str}), "
                    f"hedging={_fmt(r.get('hedging_score'), '.3f')}, "
                    f"confidence={_fmt(r.get('confidence_score'), '.3f')}"
                )
    else:
        lines.append("  No earnings call transcript data available for this ticker.")

    lines += ["", "---", "Provide your JSON synthesis now."]
    return "\n".join(lines)
