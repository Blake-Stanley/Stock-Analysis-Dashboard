"""
dashboard/components/ai_synthesis.py — Module 6: AI Synthesis (Will — Phase 3)

Public API:
    render(row, ticker, sent_df) — renders the expander panel in app.py
"""

import pandas as pd
import streamlit as st


def render(row: pd.Series, ticker: str, sent_df: pd.DataFrame | None) -> None:
    with st.expander("Module 6 — AI Synthesis", expanded=True):
        st.info("AI synthesis not yet available (Phase 3 — Will). "
                "Expected: `ai/synthesize.py` → bull case, bear case, key risks, "
                "divergence flag.")

        # Will: replace this block with something like:
        #
        #   with st.spinner("Generating AI synthesis…"):
        #       from ai.synthesize import synthesize
        #       result = synthesize(row, sent_df)
        #   st.subheader("Bull Case")
        #   st.write(result["bull"])
        #   st.subheader("Bear Case")
        #   st.write(result["bear"])
        #   st.subheader("Key Risks")
        #   for risk in result["risks"]:
        #       st.markdown(f"- {risk}")
        #   if result.get("divergence_flag"):
        #       st.warning("Divergence detected: quant signals and sentiment disagree.")
