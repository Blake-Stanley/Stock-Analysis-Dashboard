"""
dashboard/pages/fscore_detail.py — Full F-Score Financial Detail

Opened from the main dashboard via "Open Full Report ↗" button.
Reads ?ticker= from the URL query params.

URL: /fscore_detail?ticker=AAPL
"""

import pandas as pd
import streamlit as st

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
# F-Score component metadata (duplicated here so this page is self-contained)
# ---------------------------------------------------------------------------

FSCORE_META: dict[str, dict] = {
    "F1": {
        "label": "Positive ROA",
        "group": "Profitability",
        "description": "Return on Assets > 0. Confirms the firm generates positive accounting profits on its asset base.",
        "formula": "Net Income ÷ Total Assets",
        "pass_rule": "ROA > 0",
        "metric_cols": ["roa"],
        "metric_labels": ["ROA"],
        "benchmark": 0.0,
    },
    "F2": {
        "label": "Positive Cash Flow from Operations",
        "group": "Profitability",
        "description": "Operating cash flow is positive — the firm generates real cash earnings, not just accounting income.",
        "formula": "CFO ÷ Total Assets (pass if > 0)",
        "pass_rule": "CFO / Assets > 0",
        "metric_cols": ["cfo_assets"],
        "metric_labels": ["CFO / Assets"],
        "benchmark": 0.0,
    },
    "F3": {
        "label": "Increasing ROA",
        "group": "Profitability",
        "description": "ROA improved year-over-year. Indicates the firm's operational profitability is on an upward trend.",
        "formula": "ROA(t) > ROA(t−1)",
        "pass_rule": "Current ROA > prior-year ROA",
        "metric_cols": ["roa"],
        "metric_labels": ["ROA (current period)"],
        "benchmark": None,
    },
    "F4": {
        "label": "Accruals: Cash Earnings > Accounting Earnings",
        "group": "Profitability",
        "description": "Cash-based earnings exceed accrual-based earnings. Low accruals signal higher earnings quality and lower manipulation risk.",
        "formula": "CFO / Assets > Net Income / Assets",
        "pass_rule": "CFO/Assets > ROA",
        "metric_cols": ["cfo_assets", "roa"],
        "metric_labels": ["CFO / Assets", "ROA (NI / Assets)"],
        "benchmark": None,
    },
    "F5": {
        "label": "Decreasing Leverage",
        "group": "Leverage / Liquidity",
        "description": "Long-term debt ratio fell year-over-year, reducing financial risk and improving solvency margin.",
        "formula": "LT Debt / Assets(t) < LT Debt / Assets(t−1)",
        "pass_rule": "Leverage fell vs. prior year",
        "metric_cols": ["leverage"],
        "metric_labels": ["LT Debt / Assets"],
        "benchmark": None,
    },
    "F6": {
        "label": "Increasing Current Ratio",
        "group": "Leverage / Liquidity",
        "description": "Short-term liquidity improved year-over-year. The firm has a stronger ability to cover near-term obligations.",
        "formula": "Current Assets / Current Liabilities",
        "pass_rule": "Current ratio rose vs. prior year",
        "metric_cols": ["current_ratio"],
        "metric_labels": ["Current Ratio"],
        "benchmark": 1.0,
    },
    "F7": {
        "label": "No New Equity Issued",
        "group": "Leverage / Liquidity",
        "description": "Shares outstanding did not increase. Avoids EPS dilution that would harm existing shareholders.",
        "formula": "Shares(t) ≤ Shares(t−1)",
        "pass_rule": "Share count did not rise",
        "metric_cols": [],
        "metric_labels": [],
        "benchmark": None,
    },
    "F8": {
        "label": "Improving Gross Margin",
        "group": "Operating Efficiency",
        "description": "Gross margin expanded year-over-year, signaling pricing power or improved cost control.",
        "formula": "(Revenue − COGS) ÷ Revenue",
        "pass_rule": "Gross margin(t) > prior year",
        "metric_cols": ["gross_margin"],
        "metric_labels": ["Gross Margin"],
        "benchmark": None,
    },
    "F9": {
        "label": "Improving Asset Turnover",
        "group": "Operating Efficiency",
        "description": "Asset turnover increased year-over-year — more revenue generated per dollar of assets deployed.",
        "formula": "Revenue ÷ Total Assets",
        "pass_rule": "Asset turnover(t) > prior year",
        "metric_cols": ["asset_turnover"],
        "metric_labels": ["Asset Turnover"],
        "benchmark": None,
    },
}

GROUPS = ["Profitability", "Leverage / Liquidity", "Operating Efficiency"]

QUANT_PATH = "data/quant_metrics.parquet"

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading quant metrics…")
def load_quant() -> pd.DataFrame:
    return pd.read_parquet(QUANT_PATH, engine="fastparquet")


def get_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    mask = df["tic"].str.upper() == ticker.upper()
    return df[mask].iloc[0] if mask.any() else None


# ---------------------------------------------------------------------------
# Ticker resolution — URL param takes priority, then session state
# ---------------------------------------------------------------------------

params = st.query_params
ticker = params.get("ticker", st.session_state.get("fscore_detail_ticker", "")).upper().strip()

if not ticker:
    st.warning("No ticker specified. Use `?ticker=AAPL` in the URL or open this page from the main dashboard.")
    st.stop()

quant_df = load_quant()
row = get_row(quant_df, ticker)

if row is None:
    st.error(f"Ticker **{ticker}** not found in the quant metrics dataset.")
    st.stop()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

company = row.get("conm", ticker)
fscore = row.get("fscore")
fscore_pct = row.get("fscore_pct")
fyearq = row.get("fyearq")

st.title(f"Piotroski F-Score — {company} ({ticker})")
if fyearq:
    st.caption(f"Fiscal year: **{int(fyearq)}** · Data source: Compustat via WRDS (pre-computed)")

st.markdown("---")

# Summary bar
s1, s2, s3, s4 = st.columns(4)
with s1:
    st.metric("F-Score", f"{int(fscore)} / 9" if pd.notna(fscore) else "N/A",
              help="Sum of 9 binary signals (0 = worst, 9 = best fundamentals).")
with s2:
    st.metric("Percentile Rank", f"{fscore_pct:.1f}th" if pd.notna(fscore_pct) else "N/A",
              help="Rank vs. all tickers in the Compustat universe.")
with s3:
    passed_count = sum(1 for fk in FSCORE_META if row.get(fk) == 1)
    failed_count = sum(1 for fk in FSCORE_META if row.get(fk) == 0)
    st.metric("Components Passed", f"{passed_count} / 9")
with s4:
    sector = row.get("sector", "N/A")
    st.metric("Sector", sector if pd.notna(sector) else "N/A")

st.markdown("---")

# ---------------------------------------------------------------------------
# Score gauge — horizontal bar
# ---------------------------------------------------------------------------

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

all_ratio_cols = ["roa", "cfo_assets", "leverage", "current_ratio",
                  "gross_margin", "asset_turnover"]
all_ratio_labels = ["ROA", "CFO / Assets", "LT Debt / Assets",
                    "Current Ratio", "Gross Margin", "Asset Turnover"]

for group in GROUPS:
    group_components = {fk: m for fk, m in FSCORE_META.items() if m["group"] == group}
    st.subheader(group)

    for fk, meta in group_components.items():
        passed = row.get(fk)
        icon = "✅" if passed == 1 else "❌" if passed == 0 else "—"
        verdict = "PASS" if passed == 1 else "FAIL" if passed == 0 else "N/A"

        with st.expander(f"{icon} **{fk}** — {meta['label']}  ·  {verdict}", expanded=True):
            left, right = st.columns([3, 2])

            with left:
                st.markdown(f"**Description:** {meta['description']}")
                st.markdown(f"**Formula:** `{meta['formula']}`")
                st.markdown(f"**Pass condition:** {meta['pass_rule']}")

                if meta["metric_cols"]:
                    st.markdown("**Current-period values:**")
                    mcols = st.columns(len(meta["metric_cols"]))
                    for i, (col_name, label) in enumerate(
                        zip(meta["metric_cols"], meta["metric_labels"])
                    ):
                        val = row.get(col_name)
                        with mcols[i]:
                            if pd.notna(val):
                                st.metric(label, f"{val:.4f}")
                            else:
                                st.metric(label, "N/A")

            with right:
                if meta["metric_cols"]:
                    chart_vals: dict[str, float] = {}
                    benchmark = meta.get("benchmark")

                    for col_name, label in zip(meta["metric_cols"], meta["metric_labels"]):
                        val = row.get(col_name)
                        if pd.notna(val):
                            chart_vals[label] = float(val)

                    if chart_vals:
                        if benchmark is not None:
                            chart_vals["Benchmark"] = benchmark

                        chart_df = pd.DataFrame(
                            {"Metric": list(chart_vals.keys()),
                             "Value": list(chart_vals.values())}
                        )
                        st.bar_chart(chart_df.set_index("Metric"), height=220)

    st.markdown("---")

# ---------------------------------------------------------------------------
# All ratios summary table
# ---------------------------------------------------------------------------

st.subheader("All Underlying Ratios — Summary Table")

ratio_rows = []
for col, label in zip(all_ratio_cols, all_ratio_labels):
    val = row.get(col)
    ratio_rows.append({"Metric": label, "Column": col,
                        "Value": f"{val:.4f}" if pd.notna(val) else "N/A"})

ratio_df = pd.DataFrame(ratio_rows)
st.dataframe(ratio_df, use_container_width=True, hide_index=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

if st.button("← Back to Dashboard"):
    st.switch_page("app.py")
