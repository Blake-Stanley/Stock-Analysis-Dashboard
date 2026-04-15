"""
dashboard/app.py — AI-Powered Equity Research Dashboard

Single-page Streamlit app.  User enters a ticker in the sidebar, hits Run,
and sees six analysis panels populated from pre-computed data + live AI calls.

Panels
------
1. Piotroski F-Score        (quant_metrics.parquet)
2. Gross Profitability      (quant_metrics.parquet)
3. Earnings Quality         (quant_metrics.parquet)
4. Valuation & Momentum     (quant_metrics.parquet)
5. Earnings Call Sentiment  (sentiment_scores.parquet — Will)
6. AI Synthesis             (Claude API call — Will)

Run
---
    streamlit run dashboard/app.py
"""

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Equity Research Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Data loading (cached so it only hits disk once per session)
# ---------------------------------------------------------------------------

QUANT_PATH = "data/quant_metrics.parquet"
SENTIMENT_PATH = "data/sentiment_scores.parquet"


@st.cache_data(show_spinner="Loading quant metrics…")
def load_quant() -> pd.DataFrame:
    return pd.read_parquet(QUANT_PATH, engine="fastparquet")


@st.cache_data(show_spinner="Loading sentiment scores…")
def load_sentiment() -> pd.DataFrame | None:
    try:
        return pd.read_parquet(SENTIMENT_PATH, engine="fastparquet")
    except FileNotFoundError:
        return None


def get_ticker_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    """Return the single row for *ticker* (case-insensitive), or None."""
    mask = df["tic"].str.upper() == ticker.upper()
    if mask.any():
        return df[mask].iloc[0]
    return None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Equity Research")
    st.markdown("---")
    ticker_input = st.text_input(
        "Ticker symbol",
        placeholder="e.g. AAPL",
        max_chars=10,
    ).strip().upper()
    run_button = st.button("Run analysis", type="primary", use_container_width=True)
    st.markdown("---")
    st.caption(
        "Data is pre-computed from WRDS (Compustat + CRSP). "
        "Quant signals reflect the most recent available fiscal quarter. "
        "Sentiment and AI synthesis require Phase 2/3 modules."
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("AI-Powered Equity Research")

if not run_button or not ticker_input:
    st.info("Enter a ticker in the sidebar and click **Run analysis** to begin.")
    st.stop()

# Load data
quant_df = load_quant()
row = get_ticker_row(quant_df, ticker_input)

if row is None:
    st.error(f"Ticker **{ticker_input}** not found in the quant metrics file. "
             "Check the symbol and try again.")
    st.stop()

company_name = row.get("conm", ticker_input)
st.header(f"{company_name} ({ticker_input})")

# Composite score summary bar
col_score, col_signals, col_sector = st.columns(3)
composite = row.get("composite_score")
composite_pct = row.get("composite_pct")
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
# Module 1 — Piotroski F-Score
# ---------------------------------------------------------------------------

with st.expander("Module 1 — Piotroski F-Score", expanded=True):
    fscore = row.get("fscore")
    fscore_pct = row.get("fscore_pct")

    if pd.isna(fscore):
        st.warning("F-Score data not available for this ticker.")
    else:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("F-Score", f"{int(fscore)} / 9",
                      help="0 = weakest fundamentals, 9 = strongest.")
            if pd.notna(fscore_pct):
                st.metric("Percentile Rank", f"{fscore_pct:.1f}th")

        with c2:
            # Component pass/fail table
            components = {
                "F1 — Positive ROA":              row.get("F1"),
                "F2 — Positive CFO":              row.get("F2"),
                "F3 — Increasing ROA":            row.get("F3"),
                "F4 — Accruals < 0 (CFO > NI)":  row.get("F4"),
                "F5 — Decreasing Leverage":       row.get("F5"),
                "F6 — Increasing Current Ratio":  row.get("F6"),
                "F7 — No New Shares Issued":      row.get("F7"),
                "F8 — Improving Gross Margin":    row.get("F8"),
                "F9 — Improving Asset Turnover":  row.get("F9"),
            }
            comp_df = pd.DataFrame(
                {"Component": components.keys(),
                 "Pass": ["✅" if v == 1 else "❌" if v == 0 else "—"
                          for v in components.values()]}
            )
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Module 2 — Gross Profitability
# ---------------------------------------------------------------------------

with st.expander("Module 2 — Gross Profitability", expanded=True):
    gp_ratio = row.get("gp_ratio")
    gp_univ = row.get("gp_pct_universe")
    gp_sect = row.get("gp_pct_sector")

    if pd.isna(gp_ratio):
        st.warning("Gross profitability data not available for this ticker.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("GP / Assets (Novy-Marx)", f"{gp_ratio:.3f}",
                      help="(Revenue − COGS) / Total Assets")
        with c2:
            st.metric("Universe Percentile",
                      f"{gp_univ:.1f}th" if pd.notna(gp_univ) else "N/A",
                      help="Rank vs. all tickers in universe.")
        with c3:
            st.metric("Sector Percentile",
                      f"{gp_sect:.1f}th" if pd.notna(gp_sect) else "N/A",
                      help="Rank vs. tickers in same sector.")

# ---------------------------------------------------------------------------
# Module 3 — Earnings Quality (Accruals)
# ---------------------------------------------------------------------------

with st.expander("Module 3 — Earnings Quality", expanded=True):
    accruals_ratio = row.get("accruals_ratio")
    aq_pct = row.get("accruals_quality_pct")
    high_acc = row.get("high_accruals")
    net_income = row.get("net_income")
    cfo = row.get("cfo")

    if pd.isna(accruals_ratio):
        st.warning("Accruals data not available for this ticker.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Accruals Ratio", f"{accruals_ratio:.4f}",
                      help="(Net Income − CFO) / Total Assets. Lower is better.")
        with c2:
            st.metric("Earnings Quality Percentile",
                      f"{aq_pct:.1f}th" if pd.notna(aq_pct) else "N/A",
                      help="Inverted accruals rank — higher = cleaner earnings.")
        with c3:
            flag_label = "High (caution)" if high_acc == 1 else "Normal"
            st.metric("Accruals Flag", flag_label)

        # CFO vs Net Income bar chart
        if pd.notna(net_income) and pd.notna(cfo):
            cf_df = pd.DataFrame({
                "Metric": ["Net Income", "Operating Cash Flow"],
                "Value ($M)": [net_income / 1e6, cfo / 1e6],
            })
            st.bar_chart(cf_df.set_index("Metric"))

# ---------------------------------------------------------------------------
# Module 4 — Valuation & Momentum
# ---------------------------------------------------------------------------

with st.expander("Module 4 — Valuation & Momentum", expanded=True):
    ev_ebitda = row.get("ev_ebitda")
    pe_ratio = row.get("pe_ratio")
    value_pct = row.get("value_pct")
    mom_12_1 = row.get("mom_12_1")
    ret_1m = row.get("ret_1m")
    reversal_flag = row.get("reversal_flag")
    mom_pct = row.get("mom_pct")

    val_col, mom_col = st.columns(2)

    with val_col:
        st.subheader("Valuation")
        if pd.isna(ev_ebitda) and pd.isna(pe_ratio):
            st.warning("Valuation data not available for this ticker.")
        else:
            vc1, vc2, vc3 = st.columns(3)
            with vc1:
                st.metric("EV / EBITDA",
                          f"{ev_ebitda:.1f}x" if pd.notna(ev_ebitda) else "N/A")
            with vc2:
                st.metric("P / E",
                          f"{pe_ratio:.1f}x" if pd.notna(pe_ratio) else "N/A")
            with vc3:
                st.metric("Value Percentile",
                          f"{value_pct:.1f}th" if pd.notna(value_pct) else "N/A",
                          help="Higher = cheaper vs. peers (inverted multiple rank).")

    with mom_col:
        st.subheader("Momentum")
        if pd.isna(mom_12_1):
            st.warning("Momentum data not available for this ticker.")
        else:
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.metric("12-1M Momentum",
                          f"{mom_12_1*100:.1f}%",
                          help="Cumulative return t−12 to t−2.")
            with mc2:
                st.metric("Prior Month Return",
                          f"{ret_1m*100:.1f}%" if pd.notna(ret_1m) else "N/A")
            with mc3:
                rev_label = "Yes (caution)" if reversal_flag == 1 else "No"
                st.metric("Reversal Flag", rev_label,
                          help="1 if prior-month return is in bottom decile.")
            if pd.notna(mom_pct):
                st.metric("Momentum Percentile", f"{mom_pct:.1f}th")

# ---------------------------------------------------------------------------
# Module 5 — Earnings Call Sentiment (Will — Phase 2)
# ---------------------------------------------------------------------------

with st.expander("Module 5 — Earnings Call Sentiment", expanded=True):
    sent_df = load_sentiment()

    if sent_df is None:
        st.info("Sentiment data not yet available (Phase 2 — Will). "
                "Expected file: `data/sentiment_scores.parquet`.")
    else:
        mask = sent_df["tic"].str.upper() == ticker_input
        ticker_sent = sent_df[mask]
        if ticker_sent.empty:
            st.warning(f"No sentiment data found for **{ticker_input}**.")
        else:
            # Will: replace this placeholder with real charts/metrics
            st.dataframe(ticker_sent, use_container_width=True)

# ---------------------------------------------------------------------------
# Module 6 — AI Synthesis (Will — Phase 3)
# ---------------------------------------------------------------------------

with st.expander("Module 6 — AI Synthesis", expanded=True):
    st.info("AI synthesis not yet available (Phase 3 — Will). "
            "Expected: `ai/synthesize.py` → bull case, bear case, key risks, "
            "divergence flag.")

    # Will: replace this block with something like:
    #
    #   with st.spinner("Generating AI synthesis…"):
    #       from ai.synthesize import synthesize
    #       result = synthesize(row, ticker_sent)
    #   st.subheader("Bull Case")
    #   st.write(result["bull"])
    #   st.subheader("Bear Case")
    #   st.write(result["bear"])
    #   st.subheader("Key Risks")
    #   for risk in result["risks"]:
    #       st.markdown(f"- {risk}")
    #   if result.get("divergence_flag"):
    #       st.warning("Divergence detected: quant signals and sentiment disagree.")
