"""
dashboard/components/sentiment.py — Module 5: Earnings Call Sentiment

Renders tone, hedging, and confidence scores for the last 4–6 quarters,
with a QoQ trend line chart and latest-quarter metric cards.

Public API:
    render(ticker, sent_df) — renders the expander panel in app.py

Data source: data/sentiment_scores.parquet (pre-computed) or live fetch fallback.
Columns expected: ticker, date, quarter_label, tone_score, hedging_score,
                  confidence_score, tone_trend, hedging_trend, confidence_trend.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from sentiment.trend import load_ticker_sentiment  # uses Motley Fool fetcher internally
from sentiment.score import interpret_tone, interpret_hedging, interpret_confidence


def _trend_arrow(trend: str) -> str:
    return {"improving": "↑", "declining": "↓", "stable": "→", "n/a": "—"}.get(trend, "—")


def _trend_color(trend: str, higher_is_better: bool = True) -> str:
    if trend == "improving":
        return "normal" if higher_is_better else "inverse"
    if trend == "declining":
        return "inverse" if higher_is_better else "normal"
    return "off"


def _build_trend_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart with all three scores over the available quarters."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["quarter_label"], y=df["tone_score"],
        mode="lines+markers", name="Tone",
        line=dict(color="#2196F3", width=2),
        marker=dict(size=7),
        hovertemplate="<b>Tone</b>: %{y:.3f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["quarter_label"], y=df["confidence_score"],
        mode="lines+markers", name="Confidence",
        line=dict(color="#4CAF50", width=2),
        marker=dict(size=7),
        hovertemplate="<b>Confidence</b>: %{y:.3f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["quarter_label"], y=df["hedging_score"],
        mode="lines+markers", name="Hedging",
        line=dict(color="#FF9800", width=2, dash="dot"),
        marker=dict(size=7),
        hovertemplate="<b>Hedging</b>: %{y:.3f}<extra></extra>",
    ))

    # Reference line at 0 for tone
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1, opacity=0.5)

    fig.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title=None,
        yaxis_title="Score",
        yaxis=dict(range=[-1.05, 1.05]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render(ticker: str, sent_df: pd.DataFrame | None) -> None:
    with st.expander("Module 5 — Earnings Call Sentiment", expanded=True):

        # --- Resolve data ---
        ticker_sent: pd.DataFrame = pd.DataFrame()

        if sent_df is not None:
            # Fast path: pre-computed parquet (column is "ticker", not "tic")
            mask = sent_df["ticker"].str.upper() == ticker.upper()
            ticker_sent = sent_df[mask].copy()

        if ticker_sent.empty:
            # Fallback: live fetch from EDGAR (slower — shows spinner)
            with st.spinner("Fetching earnings call transcripts from Motley Fool…"):
                ticker_sent = load_ticker_sentiment(ticker)

        if ticker_sent.empty:
            st.warning(
                f"No earnings call transcript found for **{ticker}** on SEC EDGAR. "
                "This ticker may not file earnings transcripts as 8-K exhibits."
            )
            return

        # Ensure sorted oldest → newest for chart
        ticker_sent = ticker_sent.sort_values("date").reset_index(drop=True)
        latest = ticker_sent.iloc[-1]

        # --- Latest quarter metric cards ---
        st.caption(f"Latest quarter: **{latest['quarter_label']}**")

        c1, c2, c3 = st.columns(3)

        tone = latest["tone_score"]
        hedging = latest["hedging_score"]
        confidence = latest["confidence_score"]
        tone_trend = latest.get("tone_trend", "n/a")
        hedging_trend = latest.get("hedging_trend", "n/a")
        conf_trend = latest.get("confidence_trend", "n/a")

        with c1:
            st.metric(
                label=f"Tone  {_trend_arrow(tone_trend)}",
                value=f"{tone:+.3f}",
                delta=interpret_tone(tone),
                delta_color=_trend_color(tone_trend, higher_is_better=True),
                help="VADER compound sentiment on management text. "
                     "Range −1 (very negative) to +1 (very positive).",
            )

        with c2:
            st.metric(
                label=f"Hedging  {_trend_arrow(hedging_trend)}",
                value=f"{hedging:.3f}",
                delta=interpret_hedging(hedging),
                delta_color=_trend_color(hedging_trend, higher_is_better=False),
                help="Fraction of management words matching the Loughran-McDonald "
                     "uncertainty word list. Higher = more equivocal language.",
            )

        with c3:
            st.metric(
                label=f"Confidence  {_trend_arrow(conf_trend)}",
                value=f"{confidence:.3f}",
                delta=interpret_confidence(confidence),
                delta_color=_trend_color(conf_trend, higher_is_better=True),
                help="Forward-looking sentence ratio, penalised by hedging. "
                     "Higher = more concrete guidance with less qualification.",
            )

        # --- QoQ trend chart ---
        if len(ticker_sent) > 1:
            st.plotly_chart(
                _build_trend_chart(ticker_sent),
                use_container_width=True,
            )
        else:
            st.caption("Only one quarter available — trend chart requires 2+ quarters.")

        # --- QoQ delta table ---
        if len(ticker_sent) > 1:
            qoq_cols = [
                "quarter_label", "tone_score", "tone_qoq", "tone_trend",
                "hedging_score", "hedging_qoq",
                "confidence_score", "confidence_qoq", "confidence_trend",
            ]
            display_cols = [c for c in qoq_cols if c in ticker_sent.columns]
            st.dataframe(
                ticker_sent[display_cols].rename(columns={
                    "quarter_label": "Quarter",
                    "tone_score": "Tone", "tone_qoq": "Tone QoQ", "tone_trend": "Trend",
                    "hedging_score": "Hedging", "hedging_qoq": "Hedging QoQ",
                    "confidence_score": "Confidence", "confidence_qoq": "Conf. QoQ",
                    "confidence_trend": "Conf. Trend",
                }).round(4),
                use_container_width=True,
                hide_index=True,
            )
