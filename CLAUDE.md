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

**Stack:** Python · WRDS (Compustat + CRSP) · Claude API (`claude-sonnet-4-6`) · SEC EDGAR · Streamlit

---

## Key Decisions Made

- **Data approach:** Pre-computed / cached. Blake pulls and loads the data files manually; dashboard reads from parquet at runtime — no live WRDS queries. Data is intentionally stale; limitation is acknowledged in the writeup.
- **Data vintage:** All data (Compustat + CRSP) runs through **December 31, 2024**. The dashboard presents signals as-of that date; no data exists beyond it. This is the single consistent cutoff across all signals — quant_metrics.parquet reflects this vintage. Dashboard should surface this date so viewers know the analysis is not real-time.
- **Composite score:** Equal-weighted average of per-signal percentile ranks → one composite score (0–100). Dashboard also shows each individual factor's percentile rank so viewers can see the contribution breakdown. Weighting rationale documented in code docstring.
- **Transcript source:** SEC EDGAR 8-K parsing only. No fallback scraper. Tickers without a clean EDGAR transcript surface "not available" gracefully in the dashboard.
- **Dashboard architecture:** Modular component files — `app.py` is a thin orchestrator; each panel lives in `dashboard/components/<module>.py` and exposes a single `render(row, ticker, ...)` function. New panels = new file, no touching `app.py` logic. Data loading lives in `dashboard/data_loader.py`. Full-screen detail pages live in `dashboard/pages/`.

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
│   ├── compustat_with_permno.parquet   # Compustat fundamentals + PERMNO joined
│   ├── crsp_m.dta                      # CRSP monthly returns/price/shares
│   ├── ff5_plus_mom.dta                # Fama-French 5 factors + momentum
│   └── quant_metrics.parquet           # MASTER OUTPUT — 33,675 rows, 49 cols
├── signals/                    # Blake — quant signal calculators (complete)
│   ├── __init__.py
│   ├── fscore.py
│   ├── gross_profitability.py
│   ├── accruals.py
│   ├── valuation.py
│   ├── momentum.py
│   └── composite.py            # joins all signals + exports quant_metrics.parquet
├── sentiment/                  # Will — EDGAR transcript fetching + scoring
│   └── __init__.py
├── ai/                         # Will — Claude API synthesis layer
│   └── __init__.py
└── dashboard/                  # Streamlit app — modular component architecture
    ├── app.py                  # THIN ORCHESTRATOR — page config, sidebar, calls render()
    ├── data_loader.py          # load_quant(), load_sentiment(), get_ticker_row()
    ├── components/             # One file per dashboard panel
    │   ├── __init__.py
    │   ├── fscore.py           # Module 1 — F-Score + clickable detail dialog
    │   ├── gross_profitability.py  # Module 2
    │   ├── earnings_quality.py     # Module 3
    │   ├── valuation_momentum.py   # Module 4
    │   ├── sentiment.py        # Module 5 — Will (Phase 2)
    │   └── ai_synthesis.py     # Module 6 — Will (Phase 3)
    └── pages/                  # Full-screen detail pages (Streamlit multipage)
        └── fscore_detail.py    # Full F-Score financial breakdown (/fscore_detail?ticker=X)
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

---

## Current State — April 16, 2026

**Phase 1 complete. Dashboard scaffold (Modules 1–4) built and working.**

### What exists and works
- All 5 quant signal calculators in `signals/` — fully tested
- `signals/composite.py` — joins all signals, computes composite, exports master parquet
- `data/quant_metrics.parquet` — 33,675 rows, 49 columns; ready for dashboard consumption
- `.venv/` — virtual environment with all dependencies installed
- `pechersky_setup_todo.txt` — Will's setup guide (venv, data files, API key)
- `dashboard/app.py` — thin orchestrator; Enter-key submit, composite summary bar, six `render()` calls
- `dashboard/data_loader.py` — cached parquet loaders shared across app and detail pages
- `dashboard/components/fscore.py` — Module 1 with clickable per-component detail dialogs + full-report link
- `dashboard/components/gross_profitability.py` — Module 2
- `dashboard/components/earnings_quality.py` — Module 3
- `dashboard/components/valuation_momentum.py` — Module 4
- `dashboard/components/sentiment.py` — Module 5 stub (Will fills in Phase 2)
- `dashboard/components/ai_synthesis.py` — Module 6 stub (Will fills in Phase 3)
- `dashboard/pages/fscore_detail.py` — full F-Score drill-down page (`/fscore_detail?ticker=X`)

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
```

### What's not started
- EDGAR transcript fetcher + sentiment scoring (Phase 2 — Will) → `sentiment/`
- Claude API synthesis (Phase 3 — Will) → `ai/`
- Will implements `components/sentiment.py` and `components/ai_synthesis.py`

---

## Dashboard Modules (spec)

| # | Module | Key Outputs |
|---|--------|-------------|
| 1 | Piotroski F-Score | Score 0–9 + all 9 component pass/fail |
| 2 | Gross Profitability | Novy-Marx signal + sector percentile rank |
| 3 | Earnings Quality | Accruals ratio + CFO vs. net income chart |
| 4 | Valuation & Momentum | EV/EBITDA, P/E, 12-1M momentum, reversal flag |
| 5 | Earnings Call Sentiment | Tone / hedging / confidence scores, QoQ trend chart |
| 6 | AI Synthesis | Claude bull case, bear case, key risks, divergence flag |

---

## Instructor Feedback to Address

- [ ] Define and document signal selection rationale (why these 5 signals)
- [x] Define composite score formula explicitly — equal-weighted average percentile rank; individual factor ranks also displayed ✅ April 15, 2026
- [ ] Confirm EDGAR transcript parsing works; if a ticker has no EDGAR transcript, dashboard shows "not available" (no fallback scraper)
- [x] Acknowledge stale-data limitation in the writeup — pre-computed cache approach confirmed; stale-data note will be in writeup ✅ April 15, 2026
