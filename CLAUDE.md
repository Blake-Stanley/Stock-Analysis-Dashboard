# AI-Powered Equity Research Agent — Claude Context

## Meta: Keeping This File Current

Update this file at the end of every working session or whenever a meaningful milestone is reached:
- Mark completed phases/tasks and add the date completed
- Update "Current State" to reflect what's actually built and working
- Add any new decisions made (data sources, methodology choices, architecture)
- Note any blockers, open questions, or deviations from the original plan
- If the file grows stale, regenerate it from the current repo state

**Whenever a task in `todo.md` is completed, immediately mark it `[x]` and append the completion date.**

**Whenever something significant changes in the project (phase completed, new module built, key decision made, new data file added), update `README.md` to reflect the current state — especially the Status table and Project Structure.**

---

## Project Overview

**Course:** FIN 372T / 397 — UT Austin, Spring 2026, Group 9
**Goal:** AI-powered equity research dashboard. User inputs a U.S. equity ticker and gets a quant signal dashboard, earnings call sentiment trends, and a Claude-generated bull/bear synthesis.
**Demo:** April 21, 2026
**Final writeup:** April 27, 2026

**Team:**
- **Blake Stanley** — data engineering & quant signals (WRDS, Compustat, CRSP, signal calculators, composite scoring)
- **Will Pechersky** — AI layer, sentiment pipeline, Streamlit dashboard

**Stack:** Python · WRDS (Compustat + CRSP) · Claude API (`claude-sonnet-4-6`) · Motley Fool (transcripts) · Streamlit

---

## Key Decisions Made

- **Data approach:** Pre-computed / cached. Blake pulls and loads the data files manually; dashboard reads from parquet at runtime — no live WRDS queries. Data is intentionally stale; limitation is acknowledged in the writeup.
- **Data vintage:** All data (Compustat + CRSP) runs through **December 31, 2024**. The dashboard presents signals as-of that date; no data exists beyond it. This is the single consistent cutoff across all signals — quant_metrics.parquet reflects this vintage. Dashboard should surface this date so viewers know the analysis is not real-time.
- **Composite score:** Equal-weighted average of per-signal percentile ranks → one composite score (0–100). Dashboard also shows each individual factor's percentile rank so viewers can see the contribution breakdown. Weighting rationale documented in code docstring.
- **Transcript source:** ~~SEC EDGAR 8-K~~ → **Motley Fool** (`sentiment/fetch_motley_fool.py`). Changed after EDGAR parsing proved unreliable. `sentiment/fetch_transcripts.py` (EDGAR fetcher) still exists but is no longer the primary path. `sentiment/trend.py:load_ticker_sentiment()` uses the Motley Fool fetcher internally.
- **Dashboard architecture:** Modular component files — `app.py` is a thin orchestrator; each panel lives in `dashboard/components/<module>.py` and exposes a single `render(row, ticker, ...)` function. New panels = new file, no touching `app.py` logic. Data loading lives in `dashboard/data_loader.py`. Full-screen detail pages live in `dashboard/pages/`.
- **F-Score display metrics:** All flow-based ratios in the F-Score detail dialog and detail page use **TTM (trailing twelve months)** calculated from rolling 4-quarter sums of quarterly Compustat data (`ibq`, `saleq`, `cogsq`, incremental `oancfy`). Balance sheet items (`atq`, `dlttq`, `actq`, `lctq`, `cshoq`) remain point-in-time. The underlying F-Score pass/fail signals in `quant_metrics.parquet` are still computed annually (fiscal year-end) as Piotroski (2000) specifies.

---

## Project Structure

```
Stock-Analysis-Dashboard/
├── CLAUDE.md
├── todo.md
├── requirements.txt
├── .gitignore                  # data/* excluded (files too large for git)
├── pechersky_setup_todo.txt    # Will's environment setup instructions
├── Background/
│   ├── pitch_deck.pdf
│   └── pitch_instructor_feedback.txt
├── data/                       # pre-computed, gitignored
│   ├── compustat_with_permno.parquet   # Compustat fundamentals + PERMNO joined (1.7M rows, 654 cols)
│   ├── crsp_m.dta                      # CRSP monthly returns/price/shares
│   ├── ff5_plus_mom.dta                # Fama-French 5 factors + momentum
│   ├── quant_metrics.parquet           # MASTER OUTPUT — 33,675 rows, 49 cols
│   └── sentiment_scores.parquet        # Pre-computed sentiment scores (if exported)
├── signals/                    # Blake — quant signal calculators (complete)
│   ├── __init__.py
│   ├── fscore.py               # Piotroski F-Score (annual Q4 data, iby/atq)
│   ├── gross_profitability.py
│   ├── accruals.py
│   ├── valuation.py
│   ├── momentum.py
│   └── composite.py            # joins all signals + exports quant_metrics.parquet
├── sentiment/                  # Will — transcript fetching + scoring (complete)
│   ├── __init__.py
│   ├── fetch_motley_fool.py    # PRIMARY fetcher — scrapes fool.com transcript pages
│   ├── fetch_transcripts.py    # Legacy EDGAR 8-K fetcher (kept, not primary)
│   ├── parse_transcripts.py    # Splits remarks/Q&A, classifies speaker turns
│   ├── score.py                # VADER tone, LM hedging, forward-looking confidence
│   └── trend.py                # QoQ deltas; load_ticker_sentiment() = dashboard fast path
├── ai/                         # Will — Claude API synthesis layer (in progress)
│   ├── __init__.py
│   └── prompt_template.py      # system_prompt() + build_user_message() — prompt formatting
└── dashboard/                  # Streamlit app — modular component architecture
    ├── app.py                  # THIN ORCHESTRATOR — page config, sidebar, calls render()
    ├── data_loader.py          # Parquet loaders + TTM history infrastructure (see below)
    ├── components/             # One file per dashboard panel
    │   ├── __init__.py
    │   ├── fscore.py           # Module 1 — F-Score + TTM detail dialog + full-report link
    │   ├── gross_profitability.py  # Module 2
    │   ├── earnings_quality.py     # Module 3
    │   ├── valuation_momentum.py   # Module 4
    │   ├── sentiment.py        # Module 5 — Motley Fool sentiment, QoQ trend chart (built)
    │   └── ai_synthesis.py     # Module 6 — stub (Will, Phase 3)
    └── pages/                  # Full-screen detail pages (Streamlit multipage)
        └── fscore_detail.py    # Full F-Score drill-down with TTM charts (/fscore_detail?ticker=X)
```

### Dashboard coding pattern

**Rule: `app.py` stays thin.** It owns page config, sidebar, data loading, and the six `render()` calls. Nothing else.

**Adding a new panel:** create `dashboard/components/<name>.py`, define `render(row, ticker, ...)`, add one line to `app.py`.

**Adding a detail/drill-down page:** create `dashboard/pages/<name>.py`. Read `st.query_params["ticker"]` for context. Link to it with `?ticker=X` in an HTML anchor with `target="_blank"` for new-tab behavior.

**Component file template:**
```python
# dashboard/components/my_module.py
import pandas as pd
import streamlit as st

def render(row: pd.Series, ticker: str) -> None:
    with st.expander("Module N — Title", expanded=True):
        ...
```

### data_loader.py public API

| Function / Constant | Purpose |
|---|---|
| `load_quant()` | Cached loader for `quant_metrics.parquet` |
| `load_sentiment()` | Cached loader for `sentiment_scores.parquet` (returns None if missing) |
| `load_ticker_history(ticker, n_quarters=16)` | Last N quarters from Compustat with TTM ratios pre-computed |
| `get_fscore_yoy_pair(hist)` | Returns `(most_recent_row, 4_quarters_prior_row)` for YoY display |
| `build_fscore_chart(component, hist)` | Chart-ready DataFrame (period index) for a given F1–F9 component |
| `fmt_fscore_val(col, val)` | Component-aware value formatter (%, 2dp, 4dp, comma shares) |
| `fmt_fscore_delta(col, delta)` | Same with +/- sign for st.metric delta |
| `FSCORE_HIST_CFG` | Per-component chart config: metric col(s), labels, reference line |
| `get_ticker_row(df, ticker)` | Returns single row from quant_metrics for a ticker |

**TTM computation in `load_ticker_history`:** loads `n + 4` raw rows so every returned row has a complete 4-quarter rolling window. Incremental quarterly CFO is derived from `oancfy` (which is fiscal-YTD cumulative and resets at Q1). Flow metrics rolled: `ni_ttm`, `cfo_ttm`, `sales_ttm`, `cogs_ttm`. Balance sheet items are point-in-time.

---

## Current State — April 19, 2026

**Phases 1–2 complete. Phase 3 (AI synthesis) in progress. Demo April 21.**

### What exists and works
- All 5 quant signal calculators in `signals/` — fully tested
- `signals/composite.py` — joins all signals, computes composite, exports master parquet
- `data/quant_metrics.parquet` — 33,675 rows, 49 columns; ready for dashboard consumption
- `.venv/` — virtual environment with all dependencies installed
- `pechersky_setup_todo.txt` — Will's setup guide (venv, data files, API key)
- `dashboard/app.py` — thin orchestrator; Enter-key submit, composite summary bar, six `render()` calls
- `dashboard/data_loader.py` — parquet loaders + full TTM history infrastructure for F-Score detail views
- `dashboard/components/fscore.py` — Module 1: F-Score panel with per-component detail dialog showing TTM line charts (16 quarters), YoY metric comparison, and link to full report
- `dashboard/components/gross_profitability.py` — Module 2
- `dashboard/components/earnings_quality.py` — Module 3
- `dashboard/components/valuation_momentum.py` — Module 4
- `dashboard/components/sentiment.py` — Module 5: Motley Fool sentiment, QoQ trend line chart (tone/hedging/confidence), latest-quarter metric cards
- `dashboard/components/ai_synthesis.py` — Module 6: stub only
- `dashboard/pages/fscore_detail.py` — full F-Score drill-down: all 9 components with TTM line charts + YoY deltas, summary ratio table
- `sentiment/fetch_motley_fool.py` — primary transcript fetcher (Motley Fool)
- `sentiment/fetch_transcripts.py` — legacy EDGAR fetcher (kept, not primary)
- `sentiment/parse_transcripts.py`, `score.py`, `trend.py` — full sentiment pipeline
- `ai/prompt_template.py` — prompt formatter (`system_prompt()` + `build_user_message()`)

### What's not done
- `ai/synthesize.py` — Claude API call + response parsing (Phase 3 — Will)
- `dashboard/components/ai_synthesis.py` — needs `synthesize.py` to exist first
- End-to-end wire-up of AI synthesis into the dashboard
- Validation testing across cap ranges (Phase 5)
- Final writeup (Phase 6, due April 27)

### quant_metrics.parquet contents (key columns for dashboard)
| Signal | Key columns | Note |
|--------|-------------|------|
| F-Score | `fscore` (0–9), `F1`–`F9`, `fscore_pct`, + 6 ratios | 30k tickers |
| Gross Profitability | `gp_ratio`, `gp_pct_universe`, `gp_pct_sector` | 27k tickers |
| Accruals / Earnings Quality | `accruals_ratio`, `accruals_quality_pct`, `high_accruals` | 28k tickers |
| Valuation | `ev_ebitda`, `pe_ratio`, `ev_ebitda_pct`, `value_pct` | 15k tickers (mkvaltq limited) |
| Momentum | `mom_12_1`, `ret_1m`, `reversal_flag`, `mom_pct` | 24k tickers |
| **Composite** | `composite_score` (0–100), `composite_pct`, `signals_used` | 23k tickers (3+ signals) |

### How Will loads data for a ticker
```python
import pandas as pd
df = pd.read_parquet("data/quant_metrics.parquet", engine="fastparquet")
row = df[df["tic"] == "AAPL"].iloc[0]

# For TTM history (F-Score detail, etc.):
from dashboard.data_loader import load_ticker_history
hist = load_ticker_history("AAPL", n_quarters=16)  # returns DataFrame with roa_ttm, etc.
```

---

## Dashboard Modules (spec)

| # | Module | Key Outputs | Status |
|---|--------|-------------|--------|
| 1 | Piotroski F-Score | Score 0–9 + all 9 component pass/fail + TTM detail dialog | ✅ Complete |
| 2 | Gross Profitability | Novy-Marx signal + sector percentile rank | ✅ Complete |
| 3 | Earnings Quality | Accruals ratio + CFO vs. net income chart | ✅ Complete |
| 4 | Valuation & Momentum | EV/EBITDA, P/E, 12-1M momentum, reversal flag | ✅ Complete |
| 5 | Earnings Call Sentiment | Tone / hedging / confidence scores, QoQ trend chart | ✅ Complete |
| 6 | AI Synthesis | Claude bull case, bear case, key risks, divergence flag | ⏳ Stub only |

---

## Instructor Feedback to Address

- [ ] Define and document signal selection rationale (why these 5 signals)
- [x] Define composite score formula explicitly — equal-weighted average percentile rank; individual factor ranks also displayed ✅ April 15, 2026
- [x] Transcript source confirmed working — switched to Motley Fool after EDGAR proved unreliable ✅ April 16, 2026
- [x] Acknowledge stale-data limitation in the writeup — pre-computed cache approach confirmed; stale-data note will be in writeup ✅ April 15, 2026
