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

- **Data approach:** Pre-computed / cached. Pull Compustat + CRSP for a fixed universe (S&P 500 or Russell 1000) and store as parquet. The dashboard reads from cache — no live WRDS queries at runtime. This sidesteps Compustat's 2FA/lag issues flagged by the instructor.
- **Composite score:** Equal-weighted average percentile rank across all quant signals (to be documented in code).
- **Transcript source:** Try SEC EDGAR 8-K parsing first; fall back to Motley Fool or Seeking Alpha if transcripts are not clean.

---

## Project Structure

```
Stock-Analysis-Dashboard/
├── CLAUDE.md
├── todo.md
├── Background/
│   ├── pitch_deck.pdf
│   └── pitch_instructor_feedback.txt
```

*(Update this tree as files are added.)*

---

## Current State — April 15, 2026

**Nothing has been implemented yet.** The repo contains only background materials (pitch deck, instructor feedback) and planning documents (todo.md, CLAUDE.md).

### What exists
- `Background/pitch_deck.pdf` — original project pitch (dashboard modules, execution plan, division of labor)
- `Background/pitch_instructor_feedback.txt` — instructor feedback (score 4.5/5); key flags: Compustat 2FA, EDGAR transcript quality, composite score methodology, signal rationale
- `todo.md` — full ordered task list across 6 phases

### What's not started
- Data pipeline (WRDS / Compustat / CRSP pull)
- Any signal calculators (F-Score, gross profitability, accruals, momentum, valuation)
- Percentile ranking engine
- Composite score
- Transcript fetching and sentiment scoring
- Claude API integration
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
- [ ] Define composite score formula explicitly (not just "we average them")
- [ ] Confirm EDGAR transcript parsing works; document fallback source if not
- [ ] Acknowledge stale-data limitation in the writeup
