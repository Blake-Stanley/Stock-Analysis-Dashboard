"""
dashboard/components/fscore.py — Module 1: Piotroski F-Score

Public API:
    render(row, ticker) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Component metadata
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
    },
    "F2": {
        "label": "Positive Cash Flow from Operations",
        "group": "Profitability",
        "description": "Operating cash flow is positive — the firm generates real cash earnings, not just accounting income.",
        "formula": "CFO ÷ Total Assets (pass if > 0)",
        "pass_rule": "CFO / Assets > 0",
        "metric_cols": ["cfo_assets"],
        "metric_labels": ["CFO / Assets"],
    },
    "F3": {
        "label": "Increasing ROA",
        "group": "Profitability",
        "description": "ROA improved year-over-year. Indicates the firm's operational profitability is on an upward trend.",
        "formula": "ROA(t) > ROA(t−1)",
        "pass_rule": "Current ROA > prior-year ROA",
        "metric_cols": ["roa"],
        "metric_labels": ["ROA (current period)"],
    },
    "F4": {
        "label": "Accruals: Cash Earnings > Accounting Earnings",
        "group": "Profitability",
        "description": "Cash-based earnings exceed accrual-based earnings. Low accruals signal higher earnings quality and lower manipulation risk.",
        "formula": "CFO / Assets > Net Income / Assets",
        "pass_rule": "CFO/Assets > ROA",
        "metric_cols": ["cfo_assets", "roa"],
        "metric_labels": ["CFO / Assets", "ROA (NI / Assets)"],
    },
    "F5": {
        "label": "Decreasing Leverage",
        "group": "Leverage / Liquidity",
        "description": "Long-term debt ratio fell year-over-year, reducing financial risk and improving solvency margin.",
        "formula": "LT Debt / Assets(t) < LT Debt / Assets(t−1)",
        "pass_rule": "Leverage fell vs. prior year",
        "metric_cols": ["leverage"],
        "metric_labels": ["LT Debt / Assets"],
    },
    "F6": {
        "label": "Increasing Current Ratio",
        "group": "Leverage / Liquidity",
        "description": "Short-term liquidity improved year-over-year. The firm has a stronger ability to cover near-term obligations.",
        "formula": "Current Assets / Current Liabilities",
        "pass_rule": "Current ratio rose vs. prior year",
        "metric_cols": ["current_ratio"],
        "metric_labels": ["Current Ratio"],
    },
    "F7": {
        "label": "No New Equity Issued",
        "group": "Leverage / Liquidity",
        "description": "Shares outstanding did not increase. Avoids EPS dilution that would harm existing shareholders.",
        "formula": "Shares(t) ≤ Shares(t−1)",
        "pass_rule": "Share count did not rise",
        "metric_cols": [],
        "metric_labels": [],
    },
    "F8": {
        "label": "Improving Gross Margin",
        "group": "Operating Efficiency",
        "description": "Gross margin expanded year-over-year, signaling pricing power or improved cost control.",
        "formula": "(Revenue − COGS) ÷ Revenue",
        "pass_rule": "Gross margin(t) > prior year",
        "metric_cols": ["gross_margin"],
        "metric_labels": ["Gross Margin"],
    },
    "F9": {
        "label": "Improving Asset Turnover",
        "group": "Operating Efficiency",
        "description": "Asset turnover increased year-over-year — more revenue generated per dollar of assets deployed.",
        "formula": "Revenue ÷ Total Assets",
        "pass_rule": "Asset turnover(t) > prior year",
        "metric_cols": ["asset_turnover"],
        "metric_labels": ["Asset Turnover"],
    },
}

_DELTA_SIGNALS = {"F3", "F5", "F6", "F7", "F8", "F9"}

# ---------------------------------------------------------------------------
# Component detail dialog
# ---------------------------------------------------------------------------

@st.dialog("F-Score Component Detail", width="large")
def _component_dialog(component: str, ticker_row: pd.Series, ticker: str) -> None:
    meta = FSCORE_META[component]
    passed = ticker_row.get(component)
    icon = "✅" if passed == 1 else "❌" if passed == 0 else "—"

    st.subheader(f"{icon} {component}: {meta['label']}")
    st.caption(f"Group: **{meta['group']}**")
    st.divider()

    desc_col, rule_col = st.columns(2)
    with desc_col:
        st.markdown("**What it measures**")
        st.write(meta["description"])
    with rule_col:
        st.markdown("**Formula**")
        st.code(meta["formula"], language=None)
        st.markdown(f"**Pass condition:** {meta['pass_rule']}")

    st.divider()

    if meta["metric_cols"]:
        st.markdown("**Current-period metric(s)**")
        mcols = st.columns(len(meta["metric_cols"]))
        chart_vals: dict[str, float] = {}
        for i, (col_name, label) in enumerate(zip(meta["metric_cols"], meta["metric_labels"])):
            val = ticker_row.get(col_name)
            with mcols[i]:
                st.metric(label, f"{val:.4f}" if pd.notna(val) else "N/A")
            if pd.notna(val):
                chart_vals[label] = float(val)

        if chart_vals:
            chart_df = pd.DataFrame(
                {"Metric": list(chart_vals.keys()), "Value": list(chart_vals.values())}
            )
            st.bar_chart(chart_df.set_index("Metric"), height=220)

        if component in _DELTA_SIGNALS:
            st.caption(
                "Pass/fail is based on year-over-year change. "
                "Only the current-period value is stored in the pre-computed dataset."
            )
    else:
        st.info(
            "This signal (share issuance) is a binary year-over-year "
            "comparison of share counts — no scalar ratio is stored."
        )

    st.divider()

    if passed == 1:
        st.success(f"**PASS** — {meta['label']}")
    elif passed == 0:
        st.error(f"**FAIL** — {meta['label']}")
    else:
        st.warning("Result unavailable (insufficient historical data).")

    st.divider()

    btn_close, btn_full = st.columns(2)
    with btn_close:
        if st.button("Close", use_container_width=True):
            st.session_state.pop("_fscore_open", None)
            st.rerun()
    with btn_full:
        st.markdown(
            f'<a href="/fscore_detail?ticker={ticker}" target="_blank">'
            f'<button style="width:100%;padding:0.45rem 0.6rem;background:#FF4B4B;'
            f'color:white;border:none;border-radius:0.3rem;cursor:pointer;'
            f'font-size:0.875rem;font-weight:600;">Open Full Report ↗</button>'
            f'</a>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render(row: pd.Series, ticker: str) -> None:
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
                hdr = st.columns([0.5, 4, 1])
                hdr[0].markdown("**Pass**")
                hdr[1].markdown("**Component**")
                hdr[2].markdown("**Detail**")
                st.divider()

                for fk, meta in FSCORE_META.items():
                    val = row.get(fk)
                    icon = "✅" if val == 1 else "❌" if val == 0 else "—"
                    r = st.columns([0.5, 4, 1])
                    r[0].markdown(icon)
                    r[1].markdown(f"**{fk}** — {meta['label']}")
                    if r[2].button("Detail", key=f"_fscore_btn_{fk}", use_container_width=True):
                        st.session_state["_fscore_open"] = fk
                        st.rerun()

        if st.session_state.get("_fscore_open"):
            _component_dialog(st.session_state["_fscore_open"], row, ticker)
