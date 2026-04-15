# AI-Powered Equity Research Agent — Claude Context

## Meta: Keeping This File Current

Update this file at the end of every working session or whenever a meaningful milestone is reached:
- Mark completed phases/tasks and add the date completed
- Update "Current State" to reflect what's actually built and working
- Add any new decisions made (data sources, methodology choices, architecture)
- Note any blockers, open questions, or deviations from the original plan
- If the file grows stale, regenerate it from the current repo state

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
- **Composite score:** Equal-weighted average of per-signal percentile ranks → one composite score (0–100). Dashboard also shows each individual factor's percentile rank so viewers can see the contribution breakdown. Weighting rationale documented in code docstring.
- **Transcript source:** SEC EDGAR 8-K parsing only. No fallback scraper. Tickers without a clean EDGAR transcript surface "not available" gracefully in the dashboard.

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
└── dashboard/                  # Will — Streamlit app
    └── __init__.py
```

---

## Current State — April 15, 2026

**Phase 1 complete. All quant signals built and exported.**

### What exists and works
- All 5 quant signal calculators in `signals/` — fully tested
- `signals/composite.py` — joins all signals, computes composite, exports master parquet
- `data/quant_metrics.parquet` — 33,675 rows, 49 columns; ready for dashboard consumption
- `.venv/` — virtual environment with all dependencies installed
- `pechersky_setup_todo.txt` — Will's setup guide (venv, data files, API key)

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
- EDGAR transcript fetcher + sentiment scoring (Phase 2 — Will)
- Claude API synthesis (Phase 3 — Will)
- Streamlit dashboard (Phase 4 — Will)

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
