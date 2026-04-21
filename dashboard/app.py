"""
dashboard/app.py — AI-Powered Equity Research Dashboard

Thin orchestrator: page config, sidebar, data loading, and module calls.
All panel rendering lives in dashboard/components/<module>.py.

Panels
------
1. Piotroski F-Score        → components/fscore.py
2. Gross Profitability      → components/gross_profitability.py
3. Earnings Quality         → components/earnings_quality.py
4. Valuation & Momentum     → components/valuation_momentum.py
5. Earnings Call Sentiment  → components/sentiment.py          (Will — Phase 2)
6. AI Synthesis             → components/ai_synthesis.py       (Will — Phase 3)

Run
---
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that sentiment/, ai/, etc. are importable
# regardless of which directory Streamlit is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from data_loader import get_ticker_row, load_quant, load_sentiment
from components import ai_synthesis, earnings_quality, fscore, gross_profitability, sentiment, valuation_momentum

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Equity Research Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

# Hide Streamlit's automatic multipage sidebar nav
st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] {
        display: none;
    }

    [data-testid="stSidebar"] [data-testid="InputInstructions"] {
        display: none;
    }

    [data-testid="stSidebar"] [data-testid="stTextInput"] {
        margin-bottom: 0.65rem;
    }

    [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
        margin-top: 0.15rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Equity Research")
    st.markdown("---")
    with st.form("ticker_form"):
        ticker_input = st.text_input(
            "Ticker symbol",
            placeholder="e.g. AAPL",
            max_chars=10,
        ).strip().upper()
        run_button = st.form_submit_button("Run analysis", type="primary", use_container_width=True)
    st.markdown("---")
    st.caption(
        "Data is pre-computed from WRDS (Compustat + CRSP). "
        "Quant signals reflect the most recent available fiscal quarter. "
        "Sentiment and AI synthesis require Phase 2/3 modules."
    )

# Persist the active ticker across reruns (e.g. when a Detail button triggers st.rerun())
if run_button and ticker_input:
    st.session_state["_active_ticker"] = ticker_input

active_ticker: str = st.session_state.get("_active_ticker", "")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("AI-Powered Equity Research")

if not active_ticker:
    st.info("Enter a ticker in the sidebar and click **Run analysis** to begin.")
    st.stop()

quant_df = load_quant()
row = get_ticker_row(quant_df, active_ticker)

if row is None:
    st.error(f"Ticker **{active_ticker}** not found in the quant metrics file. "
             "Check the symbol and try again.")
    st.stop()

company_name = row.get("conm", active_ticker)
st.header(f"{company_name} ({active_ticker})")

# Composite score summary bar
col_score, col_signals, col_sector = st.columns(3)
composite = row.get("composite_score")
signals_used = int(row.get("signals_used", 0)) if pd.notna(row.get("signals_used")) else 0

with col_score:
    if pd.notna(composite):
        st.metric("Composite Score", f"{composite:.1f} / 100",
                  help="Equal-weighted average of up to 5 signal percentile ranks.")
    else:
        st.metric("Composite Score", "N/A")

with col_signals:
    st.metric("Signals Used", f"{signals_used} / 5",
              help="Number of the 5 quant signals available for this ticker.")

with col_sector:
    sector = row.get("sector", "N/A")
    st.metric("Sector", sector if pd.notna(sector) else "N/A")

st.markdown("---")

# ---------------------------------------------------------------------------
# Module panels
# ---------------------------------------------------------------------------

sent_df = load_sentiment()

fscore.render(row, active_ticker)
gross_profitability.render(row, active_ticker)
earnings_quality.render(row, active_ticker)
valuation_momentum.render(row, active_ticker)
sentiment.render(active_ticker, sent_df)
ai_synthesis.render(row, active_ticker, sent_df)
