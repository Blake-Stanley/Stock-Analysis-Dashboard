"""
dashboard/pages/fscore_detail.py — Full F-Score Financial Detail

Opened from the main dashboard via "Open Full Report ↗" button.
URL: /fscore_detail?ticker=AAPL
"""

import pandas as pd
import streamlit as st

from dashboard.data_loader import (
    FSCORE_HIST_CFG,
    build_fscore_chart,
    fmt_fscore_delta,
    fmt_fscore_val,
    get_fscore_yoy_pair,
    get_ticker_row,
    load_quant,
    load_ticker_history,
)

st.set_page_config(
    page_title="F-Score Detail",
    page_icon=":bar_chart:",
    layout="wide",
)

st.markdown(
    '<style>[data-testid="stSidebarNav"]{display:none}</style>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Component metadata (self-contained so this page has no component dep)
# ---------------------------------------------------------------------------

FSCORE_META: dict[str, dict] = {
    "F1": {
        "label": "Positive ROA",
        "group": "Profitability",
        "description": "Return on Assets > 0. Confirms the firm generates positive accounting profits on its asset base.",
        "formula": "TTM Net Income ÷ Total Assets",
        "pass_rule": "ROA (TTM) > 0",
    },
    "F2": {
        "label": "Positive Cash Flow from Operations",
        "group": "Profitability",
        "description": "Operating cash flow is positive — the firm generates real cash earnings, not just accounting income.",
        "formula": "TTM CFO ÷ Total Assets",
        "pass_rule": "CFO / Assets (TTM) > 0",
    },
    "F3": {
        "label": "Increasing ROA",
        "group": "Profitability",
        "description": "ROA improved year-over-year. Indicates the firm's operational profitability is on an upward trend.",
        "formula": "ROA(TTM, now) > ROA(TTM, 1yr ago)",
        "pass_rule": "Current TTM ROA > prior-year TTM ROA",
    },
    "F4": {
        "label": "Accruals: Cash Earnings > Accounting Earnings",
        "group": "Profitability",
        "description": "Cash-based earnings exceed accrual-based earnings. Low accruals signal higher earnings quality and lower manipulation risk.",
        "formula": "TTM CFO / Assets > TTM NI / Assets",
        "pass_rule": "CFO/Assets (TTM) > ROA (TTM)",
    },
    "F5": {
        "label": "Decreasing Leverage",
        "group": "Leverage / Liquidity",
        "description": "Long-term debt ratio fell year-over-year, reducing financial risk and improving solvency margin.",
        "formula": "LT Debt / Assets (current) < LT Debt / Assets (prior year)",
        "pass_rule": "Leverage fell vs. prior year",
    },
    "F6": {
        "label": "Increasing Current Ratio",
        "group": "Leverage / Liquidity",
        "description": "Short-term liquidity improved year-over-year. The firm has a stronger ability to cover near-term obligations.",
        "formula": "Current Assets / Current Liabilities",
        "pass_rule": "Current ratio rose vs. prior year",
    },
    "F7": {
        "label": "No New Equity Issued",
        "group": "Leverage / Liquidity",
        "description": "Shares outstanding did not increase. Avoids EPS dilution that would harm existing shareholders.",
        "formula": "Shares Outstanding (current) ≤ Shares Outstanding (prior year)",
        "pass_rule": "Share count did not rise",
    },
    "F8": {
        "label": "Improving Gross Margin",
        "group": "Operating Efficiency",
        "description": "Gross margin expanded year-over-year, signaling pricing power or improved cost control.",
        "formula": "(TTM Revenue − TTM COGS) ÷ TTM Revenue",
        "pass_rule": "TTM gross margin > prior-year TTM gross margin",
    },
    "F9": {
        "label": "Improving Asset Turnover",
        "group": "Operating Efficiency",
        "description": "Asset turnover increased year-over-year — more revenue generated per dollar of assets deployed.",
        "formula": "TTM Revenue ÷ Total Assets",
        "pass_rule": "TTM asset turnover > prior-year TTM asset turnover",
    },
}

GROUPS = ["Profitability", "Leverage / Liquidity", "Operating Efficiency"]

# ---------------------------------------------------------------------------
# Ticker resolution
# ---------------------------------------------------------------------------

params = st.query_params
ticker = params.get("ticker", st.session_state.get("fscore_detail_ticker", "")).upper().strip()

if not ticker:
    st.warning("No ticker specified. Use `?ticker=AAPL` in the URL or open this page from the main dashboard.")
    st.stop()

quant_df = load_quant()
row = get_ticker_row(quant_df, ticker)

if row is None:
    st.error(f"Ticker **{ticker}** not found in the quant metrics dataset.")
    st.stop()

with st.spinner("Loading financial history…"):
    hist = load_ticker_history(ticker, n_quarters=16)

curr_ann, prev_ann = get_fscore_yoy_pair(hist) if hist is not None else (None, None)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

company = row.get("conm", ticker)
fscore = row.get("fscore")
fscore_pct = row.get("fscore_pct")
fyearq = row.get("fyearq")

st.title(f"Piotroski F-Score — {company} ({ticker})")

if curr_ann is not None:
    most_recent = f"Q{int(curr_ann['fqtr'])} {int(curr_ann['fyearq'])}"
    st.caption(
        f"Most recent data: **{most_recent}** · "
        f"F-Score signals computed at fiscal year-end · "
        f"Charts show TTM metrics through most recent available quarter"
    )

st.markdown("---")

s1, s2, s3, s4 = st.columns(4)
with s1:
    st.metric("F-Score", f"{int(fscore)} / 9" if pd.notna(fscore) else "N/A",
              help="Sum of 9 binary signals (0 = worst, 9 = best fundamentals).")
with s2:
    st.metric("Percentile Rank", f"{fscore_pct:.1f}th" if pd.notna(fscore_pct) else "N/A",
              help="Rank vs. all tickers in the Compustat universe.")
with s3:
    passed_count = sum(1 for fk in FSCORE_META if row.get(fk) == 1)
    st.metric("Components Passed", f"{passed_count} / 9")
with s4:
    sector = row.get("sector", "N/A")
    st.metric("Sector", sector if pd.notna(sector) else "N/A")

st.markdown("---")

if pd.notna(fscore):
    score = int(fscore)
    filled = "🟩" * score
    empty = "⬜" * (9 - score)
    label = "Strong" if score >= 7 else "Neutral" if score >= 4 else "Weak"
    st.markdown(f"### Score: {score}/9 — {label}")
    st.markdown(f"{filled}{empty}")
    st.markdown("---")

# ---------------------------------------------------------------------------
# Component detail — grouped
# ---------------------------------------------------------------------------

for group in GROUPS:
    group_components = {fk: m for fk, m in FSCORE_META.items() if m["group"] == group}
    st.subheader(group)

    for fk, meta in group_components.items():
        passed = row.get(fk)
        icon = "✅" if passed == 1 else "❌" if passed == 0 else "—"
        verdict = "PASS" if passed == 1 else "FAIL" if passed == 0 else "N/A"
        cfg = FSCORE_HIST_CFG[fk]

        col_names: list[str] = cfg["cols"] if "cols" in cfg else [cfg["col"]]
        col_labels: list[str] = cfg["labels"] if "labels" in cfg else [cfg["label"]]

        with st.expander(f"{icon} **{fk}** — {meta['label']}  ·  {verdict}", expanded=True):
            left, right = st.columns([2, 3])

            with left:
                st.markdown(f"**{meta['description']}**")
                st.code(meta["formula"], language=None)
                st.caption(f"Pass condition: {meta['pass_rule']}")

                st.markdown("**TTM — Year-over-Year**")
                if curr_ann is not None:
                    curr_lbl = f"Q{int(curr_ann['fqtr'])} {int(curr_ann['fyearq'])}"
                    prev_lbl = f"Q{int(prev_ann['fqtr'])} {int(prev_ann['fyearq'])}" if prev_ann is not None else "Prior Year"
                    yoy_cols = st.columns(2)
                    for cn, cl in zip(col_names, col_labels):
                        cv = curr_ann.get(cn)
                        cv = float(cv) if cv is not None and pd.notna(cv) else None
                        pv = prev_ann.get(cn) if prev_ann is not None else None
                        pv = float(pv) if pv is not None and pd.notna(pv) else None
                        delta_str = fmt_fscore_delta(cn, cv - pv) if cv is not None and pv is not None else None
                        with yoy_cols[0]:
                            st.metric(
                                f"{cl} ({curr_lbl})",
                                fmt_fscore_val(cn, cv) if cv is not None else "N/A",
                                delta=delta_str,
                            )
                        with yoy_cols[1]:
                            st.metric(
                                f"{cl} ({prev_lbl})",
                                fmt_fscore_val(cn, pv) if pv is not None else "N/A",
                            )
                else:
                    st.caption("Historical data not available.")

            with right:
                chart_df = build_fscore_chart(fk, hist)
                n_periods = len(hist) if hist is not None else 0
                st.markdown(f"**{col_labels[0]} — Quarterly ({n_periods} periods, TTM)**")
                if chart_df is not None and not chart_df.empty:
                    st.line_chart(chart_df, height=240)
                else:
                    st.info("Insufficient history for chart.")

    st.markdown("---")

# ---------------------------------------------------------------------------
# Summary ratios table — TTM where applicable
# ---------------------------------------------------------------------------

st.subheader("Underlying Ratios — Most Recent TTM")

if curr_ann is not None:
    curr_lbl = f"Q{int(curr_ann['fqtr'])} {int(curr_ann['fyearq'])} (TTM)"
    ratio_rows = [
        {"Metric": "ROA",               "Column": "roa_ttm",            "Value": fmt_fscore_val("roa_ttm",            curr_ann.get("roa_ttm"))            if pd.notna(curr_ann.get("roa_ttm"))            else "N/A"},
        {"Metric": "CFO / Assets",      "Column": "cfo_assets_ttm",     "Value": fmt_fscore_val("cfo_assets_ttm",     curr_ann.get("cfo_assets_ttm"))     if pd.notna(curr_ann.get("cfo_assets_ttm"))     else "N/A"},
        {"Metric": "LT Debt / Assets",  "Column": "leverage_q",         "Value": fmt_fscore_val("leverage_q",         curr_ann.get("leverage_q"))         if pd.notna(curr_ann.get("leverage_q"))         else "N/A"},
        {"Metric": "Current Ratio",     "Column": "current_ratio_q",    "Value": fmt_fscore_val("current_ratio_q",    curr_ann.get("current_ratio_q"))    if pd.notna(curr_ann.get("current_ratio_q"))    else "N/A"},
        {"Metric": "Gross Margin",      "Column": "gross_margin_ttm",   "Value": fmt_fscore_val("gross_margin_ttm",   curr_ann.get("gross_margin_ttm"))   if pd.notna(curr_ann.get("gross_margin_ttm"))   else "N/A"},
        {"Metric": "Asset Turnover",    "Column": "asset_turnover_ttm", "Value": fmt_fscore_val("asset_turnover_ttm", curr_ann.get("asset_turnover_ttm")) if pd.notna(curr_ann.get("asset_turnover_ttm")) else "N/A"},
        {"Metric": "Shares Out. (M)",   "Column": "shares_m",           "Value": fmt_fscore_val("shares_m",           curr_ann.get("shares_m"))           if pd.notna(curr_ann.get("shares_m"))           else "N/A"},
    ]
    st.caption(f"As of {curr_lbl}. Balance sheet items are point-in-time; flow metrics are trailing twelve months.")
    st.dataframe(pd.DataFrame(ratio_rows).drop(columns="Column"), use_container_width=True, hide_index=True)
else:
    st.info("Historical data not available for ratio table.")

st.markdown("---")

if st.button("← Back to Dashboard"):
    st.switch_page("app.py")
