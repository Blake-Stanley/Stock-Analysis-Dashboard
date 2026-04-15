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
├── Background/
│   ├── pitch_deck.pdf
│   └── pitch_instructor_feedback.txt
├── data/                       # pre-computed, gitignored
│   ├── compustat_with_permno.parquet
│   ├── crsp_m.dta
│   └── ff5_plus_mom.dta
├── signals/                    # Blake — quant signal calculators
│   └── __init__.py
├── sentiment/                  # Will — EDGAR transcript fetching + scoring
│   └── __init__.py
├── ai/                         # Will — Claude API synthesis layer
│   └── __init__.py
└── dashboard/                  # Will — Streamlit app
    └── __init__.py
```

---

## Current State — April 15, 2026

**Phase 0 complete. Project structure scaffolded. Data loaded.**

### What exists
- `Background/pitch_deck.pdf` — original project pitch
- `Background/pitch_instructor_feedback.txt` — instructor feedback (score 4.5/5)
- `todo.md` — full ordered task list across 6 phases
- `requirements.txt` — pinned dependencies
- `data/compustat_with_permno.parquet` — Compustat fundamentals with PERMNO
- `data/crsp_m.dta` — CRSP monthly returns/price/shares
- `data/ff5_plus_mom.dta` — Fama-French 5 factors + momentum
- `signals/`, `sentiment/`, `ai/`, `dashboard/` — scaffolded, empty

### What's not started
- Signal calculators (F-Score, gross profitability, accruals, momentum, valuation)
- Percentile ranking engine + composite score
- EDGAR transcript fetcher + sentiment scoring
- Claude API synthesis
- Streamlit dashboard

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
