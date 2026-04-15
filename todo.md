# AI-Powered Equity Research Agent — Project TODO

> **Today:** April 15 (end of Week 2). Demo due April 21. Final writeup due April 27.
> **Stack:** Python · WRDS (Compustat, CRSP) · Claude API · SEC EDGAR · Streamlit

---

## Phase 0 — Decisions to Make First (blocking everything else)

- [ ] **Decide: live data vs. pre-computed.** Compustat via WRDS has login/2FA friction and lagged data. Recommended: pre-pull fundamentals for a fixed universe (e.g. S&P 500 or Russell 1000) and cache to CSV/parquet. Demo runs off cached data; user inputs a ticker and gets instant results. Document this limitation clearly.
- [ ] **Decide: composite score methodology.** Define how the 5 quant signals combine into one overall rank (e.g. equal-weighted average percentile). This needs to be written down before coding the scoring engine.
- [ ] **Decide: transcript source.** Test EDGAR 8-K parsing first. If transcripts are not clean/complete, fall back to Motley Fool or Seeking Alpha scraping (as instructor suggested).

---

## Phase 1 — Data & Metrics Engine (Blake) — *was due April 11*

- [ ] **Set up project structure.** Create `data/`, `signals/`, `sentiment/`, `dashboard/`, `ai/` directories; add `requirements.txt` and `.gitignore`.
- [ ] **Pull Compustat fundamentals from WRDS.** Income statement, balance sheet, and cash flow statement for target universe (suggest S&P 500). Save to `data/compustat_fundamentals.parquet`.
- [ ] **Pull CRSP market data from WRDS.** Monthly returns, shares outstanding, and price for momentum and valuation multiples. Save to `data/crsp_market.parquet`.
- [ ] **Implement Piotroski F-Score calculator** (`signals/fscore.py`). All 9 binary components: profitability (ROA, CFO, ΔROA, accruals), leverage/liquidity (ΔLeverage, ΔCurrent ratio, no new equity), efficiency (ΔGross margin, ΔAsset turnover). Output component breakdown + total score (0–9) per ticker.
- [ ] **Implement gross profitability signal** (`signals/gross_profitability.py`). Novy-Marx (2013): (Revenue − COGS) / Total Assets.
- [ ] **Implement earnings quality / accruals ratio** (`signals/accruals.py`). Operating accruals = (Net Income − CFO) / Total Assets. Flag large positive accruals as low quality.
- [ ] **Implement valuation multiples** (`signals/valuation.py`). EV/EBITDA and P/E ratio per ticker per period.
- [ ] **Implement 12-1 month momentum** (`signals/momentum.py`). Cumulative return months t-12 to t-2; add reversal flag for past-month return.
- [ ] **Compute percentile ranks.** For each signal, rank ticker within (a) its GICS sector and (b) full universe. Output a `ranks_df` with one row per ticker: signal values + percentile ranks.
- [ ] **Build composite quant score.** Average the percentile ranks across all signals into one overall quant score (0–100). Document the weighting rationale in a docstring.
- [ ] **Export a single master metrics file.** `data/quant_metrics.parquet` with all signals, ranks, and composite score. One row per ticker, latest available period.

---

## Phase 2 — Earnings Call Sentiment Pipeline (Will)

- [ ] **Build EDGAR transcript fetcher** (`sentiment/fetch_transcripts.py`). Query SEC EDGAR full-text search for 8-K filings; extract the earnings call transcript section. Test on 5–10 tickers before scaling.
- [ ] **Implement fallback transcript scraper** if EDGAR parsing is unreliable. Consider Motley Fool earnings transcript pages or Seeking Alpha (per instructor feedback).
- [ ] **Parse and clean transcripts.** Separate management prepared remarks from Q&A section. Strip boilerplate (Safe Harbor language, operator lines).
- [ ] **Score tone, hedging, and forward-looking confidence per transcript** (`sentiment/score.py`). Options: VADER/FinBERT for tone; hedging word list (EPFR or Loughran-McDonald); forward-looking sentence ratio. Produce a numeric score for each dimension per quarter.
- [ ] **Build QoQ trend tracker.** Store scores for the last 4–6 quarters per ticker; compute quarter-over-quarter delta. Output a small DataFrame used by the AI synthesis and dashboard chart.
- [ ] **Export sentiment results.** `data/sentiment_scores.parquet` with ticker, quarter, tone score, hedging score, confidence score, and QoQ deltas.

---

## Phase 3 — Claude AI Synthesis Layer (Will)

- [ ] **Design the synthesis prompt.** Input: formatted quant signals + percentile ranks + sentiment scores + QoQ trend. Output: bull case (2–3 sentences), bear case (2–3 sentences), key risks (bullet list), divergence flag (quant vs. sentiment). Write the prompt as a template in `ai/prompt_template.py`.
- [ ] **Implement Claude API call** (`ai/synthesize.py`). Use `claude-sonnet-4-6`. Pass quant + sentiment context in a structured user message. Parse and return the structured output (bull, bear, risks, divergence flag).
- [ ] **Add prompt caching** for repeated ticker lookups (pass `cache_control` on the system prompt block to avoid re-billing the large context on repeat queries).
- [ ] **Test synthesis on 3–5 diverse tickers** (large-cap, small-cap, a stock with known quant/sentiment divergence). Evaluate output quality and adjust prompt.

---

## Phase 4 — Streamlit Dashboard (Will)

- [ ] **Scaffold the Streamlit app** (`dashboard/app.py`). Single-page layout with sidebar ticker input and run button.
- [ ] **Module 1 — Piotroski F-Score panel.** Gauge or bar showing total score (0–9) + table of all 9 component pass/fail.
- [ ] **Module 2 — Gross Profitability panel.** Current value + percentile rank vs. sector (bar or gauge).
- [ ] **Module 3 — Earnings Quality panel.** Accruals ratio + cash flow vs. net income comparison chart.
- [ ] **Module 4 — Valuation & Momentum panel.** EV/EBITDA, P/E, 12-1M momentum, reversal flag.
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
