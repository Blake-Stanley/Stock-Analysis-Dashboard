# AI-Powered Equity Research Dashboard

**FIN 372T / 397 — UT Austin, Spring 2026, Group 9**
Demo: April 21, 2026 | Final writeup: April 27, 2026

---

## What It Does

User enters a U.S. equity ticker and gets a full quant signal dashboard, earnings call sentiment trends, and a Claude-generated bull/bear synthesis — all from pre-computed data so there are no live API calls to WRDS at runtime.

---

## Team

| Member | Responsibility |
|--------|---------------|
| Blake Stanley | Data engineering & quant signals (WRDS, Compustat, CRSP, signal calculators, composite scoring) |
| Will Pechersky | AI layer, sentiment pipeline, Streamlit dashboard |

---

## Stack

- **Python** — data pipeline and dashboard
- **WRDS** (Compustat + CRSP) — fundamental and market data
- **Claude API** (`claude-sonnet-4-6`) — bull/bear synthesis
- **SEC EDGAR** — earnings call transcript source
- **Streamlit** — dashboard UI

---

## Project Structure

```
Stock-Analysis-Dashboard/
├── README.md
├── CLAUDE.md                       # AI context and project decisions
├── todo.md                         # Task tracking
├── requirements.txt
├── .gitignore                      # data/* excluded (files too large for git)
├── pechersky_setup_todo.txt        # Will's environment setup instructions
├── Background/
│   ├── pitch_deck.pdf
│   └── pitch_instructor_feedback.txt
├── data/                           # pre-computed, gitignored
│   ├── compustat_with_permno.parquet
│   ├── crsp_m.dta
│   ├── ff5_plus_mom.dta
│   └── quant_metrics.parquet       # master output — 33,675 rows, 49 cols
├── signals/                        # Quant signal calculators (Phase 1 — complete)
│   ├── fscore.py
│   ├── gross_profitability.py
│   ├── accruals.py
│   ├── valuation.py
│   ├── momentum.py
│   └── composite.py
├── sentiment/                      # Transcript fetching + scoring (Phase 2 — Will)
├── ai/                             # Claude API synthesis (Phase 3 — Will)
└── dashboard/                      # Streamlit app (Phase 4 — in progress)
    └── app.py
```

---

## Quant Signals

| Signal | Module | Key Output |
|--------|--------|-----------|
| Piotroski F-Score | `signals/fscore.py` | Score 0–9 + 9 binary components |
| Gross Profitability | `signals/gross_profitability.py` | GP/Assets ratio + universe & sector percentile |
| Earnings Quality | `signals/accruals.py` | Accruals ratio + CFO vs. net income |
| Valuation | `signals/valuation.py` | EV/EBITDA, P/E + value percentile |
| Momentum | `signals/momentum.py` | 12-1M return + reversal flag |
| **Composite** | `signals/composite.py` | Equal-weighted avg of 5 signal percentiles (0–100) |

All signals are pre-computed and stored in `data/quant_metrics.parquet` (33,675 rows, 49 columns). The composite score requires at least 3 of 5 signals to be present for a ticker.

---

## Setup

```bash
# Clone and enter the repo
git clone <repo-url>
cd Stock-Analysis-Dashboard

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

**Data files** are not tracked in git (too large). Obtain from Blake:
- `data/compustat_with_permno.parquet`
- `data/crsp_m.dta`
- `data/ff5_plus_mom.dta`
- `data/quant_metrics.parquet` ← pre-built; no need to regenerate unless signals change

**API key** — set your Anthropic key before running the dashboard:
```bash
export ANTHROPIC_API_KEY=sk-...   # macOS/Linux
set ANTHROPIC_API_KEY=sk-...      # Windows
```

---

## Running the Dashboard

```bash
streamlit run dashboard/app.py
```

Open the URL Streamlit prints (default: `http://localhost:8501`), enter a ticker in the sidebar, and click **Run analysis**.

---

## Regenerating Quant Metrics

Only needed if signal logic changes. Requires WRDS data files in `data/`.

```bash
python signals/composite.py
```

---

## Data Notes

- **Stale data by design.** Quant metrics are pre-computed from a static WRDS pull; the dashboard does not make live WRDS queries at runtime. This limitation is acknowledged in the writeup.
- **Transcript source:** SEC EDGAR 8-K filings only. No fallback scraper — tickers without a clean EDGAR transcript show "not available" in the dashboard.

---

## Current Status (April 15, 2026)

| Phase | Owner | Status |
|-------|-------|--------|
| Phase 1 — Data & quant signals | Blake | Complete |
| Phase 2 — Earnings call sentiment | Will | Not started |
| Phase 3 — Claude AI synthesis | Will | Not started |
| Phase 4 — Streamlit dashboard | Both | In progress (Modules 1–4 built) |
| Phase 5 — Validation & polish | Both | Not started |
| Phase 6 — Final writeup | Both | Not started |
