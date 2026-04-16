# AI-Powered Equity Research Agent — Project TODO

> **Today:** April 15 (end of Week 2). Demo due April 21. Final writeup due April 27.
> **Stack:** Python · WRDS (Compustat, CRSP) · Claude API · SEC EDGAR · Streamlit

---

## Phase 0 — Decisions to Make First (blocking everything else) ✅ April 15, 2026

- [x] **Decide: live data vs. pre-computed.** ✅ **Pre-computed / cached.** Blake will pull and load the data files manually; dashboard reads from parquet at runtime — no live WRDS queries. Data will be stale; this limitation will be acknowledged in the writeup.
- [x] **Decide: composite score methodology.** ✅ **Equal-weighted average percentile rank across all quant signals.** Dashboard also displays each individual factor's percentile rank so viewers can see the contribution breakdown.
- [x] **Decide: transcript source.** ✅ **SEC EDGAR 8-K only.** No fallback scraper — if a ticker's transcript isn't available via EDGAR, show "not available" gracefully.

---

## Phase 1 — Data & Metrics Engine (Blake) — *was due April 11*

- [x] **Set up project structure.** ✅ April 15, 2026. Created `signals/`, `sentiment/`, `dashboard/`, `ai/` with `__init__.py`; added `requirements.txt`. Data already loaded by Blake: `compustat_with_permno.parquet`, `crsp_m.dta`, `ff5_plus_mom.dta`.
- [x] **Pull Compustat fundamentals from WRDS.** ✅ April 15, 2026. Loaded as `data/compustat_with_permno.parquet` (654 cols, 1.7M rows; PERMNO already joined).
- [x] **Pull CRSP market data from WRDS.** ✅ April 15, 2026. Loaded as `data/crsp_m.dta`. Factor data in `data/ff5_plus_mom.dta`.
- [x] **Implement Piotroski F-Score calculator** (`signals/fscore.py`). ✅ April 15, 2026. All 9 binary components implemented; outputs component breakdown + total score (0–9) + underlying ratios per ticker. Verified on 30k tickers; AAPL=6 spot-check passes.
- [x] **Implement gross profitability signal** (`signals/gross_profitability.py`). ✅ April 15, 2026. Novy-Marx GP = (Revenue − COGS) / Assets; outputs universe + sector percentile ranks. 27k tickers scored.
- [x] **Implement earnings quality / accruals ratio** (`signals/accruals.py`). ✅ April 15, 2026. Accruals = (NI − CFO) / Assets; outputs ratio, percentile rank, high-accruals flag. 28k tickers scored.
- [x] **Implement valuation multiples** (`signals/valuation.py`). ✅ April 15, 2026. EV/EBITDA and P/E with percentile ranks. EV = mkvaltq + dlttq + dlcq − cheq. 15k tickers scored (limited by mkvaltq availability).
- [x] **Implement 12-1 month momentum** (`signals/momentum.py`). ✅ April 15, 2026. Cumulative return t-12 to t-2 from CRSP; reversal flag for bottom-decile prior-month return; outputs mom_pct rank.
- [x] **Compute percentile ranks.** ✅ April 15, 2026. Handled within each signal module + composite.py. GP has universe + sector ranks; all others have universe rank.
- [x] **Build composite quant score.** ✅ April 15, 2026. `signals/composite.py`. Equal-weighted mean of 5 direction-corrected percentile ranks; requires 3+ signals; individual factor pcts all present. 23k tickers scored.
- [x] **Export a single master metrics file.** ✅ April 15, 2026. `data/quant_metrics.parquet` — 33,675 rows, 49 cols. Composite score distribution mean=47.5, well-centered.

---

## Phase 2 — Earnings Call Sentiment Pipeline (Will)

- [x] **Build EDGAR transcript fetcher** (`sentiment/fetch_transcripts.py`). ✅ April 16, 2026. Resolves ticker→CIK via EDGAR company_tickers.json, walks 8-K filings, picks transcript exhibit (priority: filename contains "transcript" > ex99.x > primary doc), extracts call section, strips Safe Harbor boilerplate. Returns [] if no usable transcript found. Smoke-test: `python -m sentiment.fetch_transcripts AAPL MSFT NVDA`.
- [x] **Parse and clean transcripts.** ✅ April 16, 2026. `sentiment/parse_transcripts.py` — splits prepared remarks vs Q&A, parses into speaker turns, classifies each turn as executive/analyst/operator, strips operator logistics lines. Returns ParsedTranscript with management_text and analyst_text ready for scoring.
- [x] **Score tone, hedging, and forward-looking confidence per transcript** (`sentiment/score.py`). ✅ April 16, 2026. VADER compound for tone [-1,1]; Loughran-McDonald uncertainty word list for hedging [0,1]; forward-looking sentence ratio penalised by hedging for confidence [0,1]. `score_transcript(parsed)` → TranscriptScores; `score_transcript_list(transcripts)` → DataFrame.
- [x] **Build QoQ trend tracker.** ✅ April 16, 2026. `sentiment/trend.py` — `compute_qoq()` adds tone_qoq/hedging_qoq/confidence_qoq deltas + trend labels (improving/declining/stable) per ticker. `build_ticker_sentiment(ticker)` runs the full pipeline for one ticker.
- [x] **Export sentiment results.** ✅ April 16, 2026. `export_sentiment_scores(tickers, path)` batch-processes tickers and writes `data/sentiment_scores.parquet`. `load_ticker_sentiment(ticker)` is the dashboard fast path — reads cache, falls back to live fetch if missing.

---

## Phase 3 — Claude AI Synthesis Layer (Will)

- [ ] **Design the synthesis prompt.** Input: formatted quant signals + percentile ranks + sentiment scores + QoQ trend. Output: bull case (2–3 sentences), bear case (2–3 sentences), key risks (bullet list), divergence flag (quant vs. sentiment). Write the prompt as a template in `ai/prompt_template.py`.
- [ ] **Implement Claude API call** (`ai/synthesize.py`). Use `claude-sonnet-4-6`. Pass quant + sentiment context in a structured user message. Parse and return the structured output (bull, bear, risks, divergence flag).
- [ ] **Add prompt caching** for repeated ticker lookups (pass `cache_control` on the system prompt block to avoid re-billing the large context on repeat queries).
- [ ] **Test synthesis on 3–5 diverse tickers** (large-cap, small-cap, a stock with known quant/sentiment divergence). Evaluate output quality and adjust prompt.

---

## Phase 4 — Streamlit Dashboard (Both)

- [x] **Scaffold the Streamlit app** (`dashboard/app.py`). Single-page layout with sidebar ticker input and run button. ✅ April 15, 2026
- [x] **Module 1 — Piotroski F-Score panel.** Gauge or bar showing total score (0–9) + table of all 9 component pass/fail. ✅ April 15, 2026
- [x] **Module 2 — Gross Profitability panel.** Current value + percentile rank vs. sector (bar or gauge). ✅ April 15, 2026
- [x] **Module 3 — Earnings Quality panel.** Accruals ratio + cash flow vs. net income comparison chart. ✅ April 15, 2026
- [x] **Module 4 — Valuation & Momentum panel.** EV/EBITDA, P/E, 12-1M momentum, reversal flag. ✅ April 15, 2026
- [ ] **Module 5 — Sentiment & Textual Analysis panel.** QoQ trend line chart (tone, hedging, confidence over last 4–6 quarters).
- [ ] **Module 6 — AI Synthesis panel.** Display bull case, bear case, key risks, and divergence flag from Claude output. Show a spinner while the API call is in flight.
- [ ] **Wire up all modules end-to-end.** Ticker input → load from parquet → compute/fetch → display all 6 panels.
- [ ] **Handle missing data gracefully.** If transcript data or a signal is unavailable for a ticker, show a clear "not available" message rather than crashing.

---

## Phase 5 — Validation & Polish (Both)

- [ ] **Test on tickers across cap ranges.** At minimum: 1 mega-cap (e.g. AAPL), 1 mid-cap, 1 small-cap. Confirm outputs are coherent.
- [ ] **Test a known divergence case.** Find a ticker where quant signals are strong but recent management tone is cautious (or vice versa) and verify Claude flags it correctly.
- [ ] **Refine Claude prompts** based on output quality from validation testing.
- [ ] **Fix any data or display issues** surfaced during testing.
- [ ] **Add signal selection rationale** (per instructor feedback). Either a brief explainer section in the dashboard sidebar or a comment block in the code documenting why each signal was chosen.
- [ ] **Finalize live demo script.** Pick 2–3 demo tickers, pre-cache their data so the demo runs fast. Practice the walkthrough.
- [ ] **Finalize presentation slides** before April 21 demo.

---

## Phase 6 — Final Writeup (Both) — *due April 27*

- [ ] **Write final report.** Sections: motivation, signal selection rationale (address instructor feedback), data sources, methodology (composite score formula, sentiment scoring approach), results/demo outputs, limitations (stale data, EDGAR transcript gaps), future work.
- [ ] **Incorporate any feedback** received after the April 21 demo.
- [ ] **Submit final writeup** by April 27.
