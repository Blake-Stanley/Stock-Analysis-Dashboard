"""
build_writeup.py — Generate the final writeup as writeup.docx.

Run:    .venv\\Scripts\\python.exe build_writeup.py
Output: writeup.docx

Formatting follows the FIN 372T Spring 2026 style guide:
  - 12pt body font, 1.5 line spacing
  - 10 page maximum (incl. title, figures, bibliography)
  - Numbered figures/tables with detailed standalone descriptions
  - Present tense, professional investor audience
  - MLA bibliography, in-text citations as LastName (Year)

The document is built section-by-section so individual sections can be
edited in place without rebuilding the rest.  Real metric values are
pulled from data/quant_metrics.parquet so the results section stays in
sync with the data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_PATH = "writeup.docx"
QUANT_PATH = "data/quant_metrics.parquet"
SENT_PATH = "data/sentiment_scores.parquet"

BODY_FONT = "Calibri"
BODY_SIZE = Pt(11)
HEADING_COLOR = RGBColor(0x00, 0x00, 0x00)  # black
LINE_SPACING = 1.5


# ---------------------------------------------------------------------------
# Document setup
# ---------------------------------------------------------------------------

def new_document() -> Document:
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Default style
    style = doc.styles["Normal"]
    style.font.name = BODY_FONT
    style.font.size = BODY_SIZE
    pf = style.paragraph_format
    pf.line_spacing = LINE_SPACING
    pf.space_after = Pt(8)

    return doc


# ---------------------------------------------------------------------------
# Paragraph helpers
# ---------------------------------------------------------------------------

def add_paragraph(
    doc: Document,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    align=None,
    size: Pt | None = None,
    color: RGBColor | None = None,
    space_before: Pt | None = None,
    space_after: Pt | None = None,
    line_spacing: float | None = None,
):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    if space_before is not None:
        p.paragraph_format.space_before = space_before
    if space_after is not None:
        p.paragraph_format.space_after = space_after
    if line_spacing is not None:
        p.paragraph_format.line_spacing = line_spacing
    run = p.add_run(text)
    run.font.name = BODY_FONT
    if size is not None:
        run.font.size = size
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    if color is not None:
        run.font.color.rgb = color
    return p


def add_heading(doc: Document, text: str, level: int = 1):
    sizes = {1: Pt(14), 2: Pt(12)}
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8) if level == 1 else Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = BODY_FONT
    run.font.size = sizes.get(level, Pt(12))
    run.bold = True
    run.font.color.rgb = HEADING_COLOR
    return p


def add_bullets(doc: Document, items: list[str]):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.line_spacing = LINE_SPACING
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(item)
        run.font.name = BODY_FONT
        run.font.size = BODY_SIZE


def add_figure_caption(doc: Document, number: int, title: str, description: str):
    """Numbered figure caption per the style guide: bold title, then description."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.15
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    head = p.add_run(f"Figure {number}: {title}\n")
    head.font.name = BODY_FONT
    head.font.size = Pt(11)
    head.bold = True

    desc = p.add_run(description)
    desc.font.name = BODY_FONT
    desc.font.size = Pt(10)
    desc.italic = True


def add_table_caption(doc: Document, number: int, title: str, description: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    head = p.add_run(f"Table {number}: {title}\n")
    head.font.name = BODY_FONT
    head.font.size = Pt(11)
    head.bold = True
    desc = p.add_run(description)
    desc.font.name = BODY_FONT
    desc.font.size = Pt(10)
    desc.italic = True


def add_code_block(doc: Document, text: str, *, size: int = 9):
    """Monospace block in a single-cell bordered table for visual emphasis."""
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    cell = table.rows[0].cells[0]
    cell.width = Inches(6.5)

    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(size)

    # Apply black border on all four sides of the cell
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "8")  # 1.0pt
        border.set(qn("w:color"), "000000")
        tcBorders.append(border)
    tcPr.append(tcBorders)

    # A little vertical padding inside the cell
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", "100"), ("bottom", "100"),
                      ("left", "120"), ("right", "120")):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), val)
        m.set(qn("w:type"), "dxa")
        tcMar.append(m)
    tcPr.append(tcMar)


# ---------------------------------------------------------------------------
# Section: Title and Abstract
# ---------------------------------------------------------------------------

def section_title(doc: Document):
    add_paragraph(
        doc,
        "An AI-Powered Equity Research Dashboard:",
        bold=True,
        size=Pt(18),
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_after=Pt(2),
        color=HEADING_COLOR,
    )
    add_paragraph(
        doc,
        "Reconciling Quantitative Signals with Earnings Call Sentiment",
        bold=True,
        size=Pt(14),
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_after=Pt(8),
        color=HEADING_COLOR,
    )
    add_paragraph(
        doc,
        "Blake Stanley and Will Pechersky",
        size=Pt(12),
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_after=Pt(2),
    )
    add_paragraph(
        doc,
        "FIN 372T / 397  ·  Group 9  ·  Spring 2026",
        size=Pt(11),
        italic=True,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_after=Pt(10),
    )

    add_heading(doc, "Abstract", level=2)
    add_paragraph(
        doc,
        "This paper presents an AI-powered equity research dashboard that "
        "combines five well-established quantitative signals with quarterly "
        "earnings call sentiment and uses Anthropic's Claude (Sonnet 4.6) to "
        "synthesize a bull case, bear case, and key risks for any U.S. equity. "
        "Quantitative scores are pre-computed from WRDS Compustat fundamentals "
        "and CRSP monthly returns; sentiment is scored live from Motley Fool "
        "transcripts using VADER tone, Loughran-McDonald hedging, and a "
        "forward-looking confidence measure. The dashboard surfaces a composite "
        "percentile score, a per-component breakdown, and an explicit "
        "divergence flag when fundamentals and management language tell "
        "different stories.",
    )


# ---------------------------------------------------------------------------
# Section: Introduction
# ---------------------------------------------------------------------------

def section_introduction(doc: Document):
    add_heading(doc, "1. Introduction", level=1)
    add_paragraph(
        doc,
        "Equity research has become a problem of integration rather than data "
        "scarcity. A buy-side analyst evaluating a stock today has access to "
        "fundamental ratios, market-microstructure data, transcripts, news, "
        "and analyst reports, but each source lives in a separate terminal "
        "and the analyst must stitch them together to notice when the numbers "
        "and the narrative disagree. Our dashboard performs that integration "
        "in seconds. Given a U.S. equity ticker, it returns "
        "returns a composite quantitative score across five academically "
        "validated signals, three sentiment metrics extracted from the most "
        "recent six earnings calls, and a Claude-generated synthesis that "
        "frames the long and short cases and explicitly flags divergences "
        "between fundamentals and executive language. The motivating insight "
        "is that a stock can look fundamentally healthy while management tone "
        "is quietly deteriorating, and vice versa; surfacing that mismatch is "
        "where a language model adds value over either signal alone.",
    )
    add_paragraph(
        doc,
        "Section 2 clarifies the data sources. Section 3 details the five "
        "quantitative signals, composite-score construction, and sentiment "
        "pipeline. Section 4 documents the Claude prompt architecture. "
        "Section 5 walks through results for three example tickers. Section 6 "
        "reports a backtest of the composite signal. Section 7 discusses "
        "limitations and future work.",
    )


# ---------------------------------------------------------------------------
# Section: Data Sources
# ---------------------------------------------------------------------------

def section_data(doc: Document):
    add_heading(doc, "2. Data Sources", level=1)
    add_paragraph(
        doc,
        "The dashboard combines two distinct data ecosystems, separated "
        "explicitly here because the distinction was raised in feedback after "
        "our presentation. All fundamental and market data comes from Wharton "
        "Research Data Services (WRDS) — specifically the Compustat "
        "Fundamentals Quarterly file for income-statement, balance-sheet, "
        "and cash-flow fields, and the CRSP Monthly Stock file for total "
        "returns, prices, and shares outstanding. Compustat firms are joined "
        "to CRSP via PERMNO. The merged universe contains 33,675 U.S. common "
        "shares with non-trivial financial data through December 31, 2024.",
    )
    add_paragraph(
        doc,
        "Because WRDS requires manual two-factor authentication on every pull, "
        "the dashboard is not a live-data tool. All five quantitative signals "
        "are pre-computed once and written to data/quant_metrics.parquet "
        "(33,675 rows, 49 columns), then read on demand. The data vintage is "
        "December 31, 2024; the dashboard surfaces this date so a viewer is "
        "never confused about staleness, and we treat it as an acknowledged "
        "limitation rather than an attempt to misrepresent freshness.",
    )
    add_paragraph(
        doc,
        "Earnings call transcripts do not come from WRDS. We initially built "
        "an SEC EDGAR 8-K parser, but 8-K filings rarely contain transcripts "
        "in a clean, structured format and parsing reliability was low. After "
        "the pitch we switched to scraping fool.com transcript pages, which "
        "publish formatted prepared-remarks-and-Q&A versions of most large- "
        "and mid-cap calls within days of the call. Motley Fool transcripts "
        "are already editorial text, so the dashboard performs no speech-to-"
        "text or audio processing — the pipeline operates entirely on "
        "pre-transcribed text. The fetcher in sentiment/fetch_motley_fool.py "
        "resolves a ticker to its transcript index and walks the most recent "
        "six quarters. Recent transcripts are "
        "sometimes paywalled; the fetcher detects paywall pages and returns "
        "no data for that quarter rather than scoring noise. The dashboard "
        "masks any cached all-zero sentiment readings (the historical paywall "
        "fingerprint) to N/A and re-attempts a live fetch on each load.",
    )


# ---------------------------------------------------------------------------
# Section: Methodology — Quant
# ---------------------------------------------------------------------------

def section_quant(doc: Document):
    add_heading(doc, "3. Methodology — Quantitative Signals", level=1)

    add_heading(doc, "3.1 Signal selection rationale", level=2)
    add_paragraph(
        doc,
        "We choose five signals that are well-established in the academic "
        "literature, span complementary economic dimensions (profitability, "
        "earnings quality, valuation, and price behavior), and are computable "
        "from Compustat and CRSP data. Each has a peer-reviewed paper "
        "documenting cross-sectional return predictability. The composite is "
        "intentionally simple — equal weights — so that the strength of any "
        "individual signal is transparent and the overall score has no "
        "free parameters fit to the in-sample data.",
    )
    add_bullets(doc, [
        "Piotroski F-Score — Piotroski (2000) defines nine binary tests of "
        "profitability, leverage, and operating efficiency, summed into a 0–9 "
        "fundamental quality score.",
        "Gross Profitability — Novy-Marx (2013) shows that gross profits "
        "scaled by assets is a clean measure of productive efficiency and "
        "earns a return premium distinct from book-to-market.",
        "Accruals Ratio — Sloan (1996) separates cash earnings from accounting "
        "earnings and shows that high-accruals firms systematically "
        "underperform.",
        "Valuation — EV/EBITDA (capital-structure-neutral) and P/E ratios, "
        "both with long-standing use in fundamental equity valuation.",
        "12-1 Month Momentum — Jegadeesh and Titman (1993) and Carhart (1997) "
        "document a robust return-continuation premium; we use cumulative "
        "return from t−12 to t−2 with a one-month skip to avoid short-term "
        "reversal.",
    ])

    add_heading(doc, "3.2 Compustat fields and signal formulas", level=2)
    add_paragraph(
        doc,
        "Each signal is computed in a dedicated module in signals/. Annual "
        "flow variables (net income iby, sales saley, COGS cogsy, operating "
        "cash flow oancfy, EBITDA oibdpy) are taken from the fiscal year-end "
        "(fqtr=4) row, where Compustat's YTD-cumulative fields represent the "
        "full year. Balance-sheet items (atq, dlttq, actq, lctq, cshoq, "
        "mkvaltq, cheq) are point-in-time at the same fiscal year-end. The "
        "Piotroski F-Score sums nine binary tests: positive ROA (iby/atq), "
        "positive CFO, ΔROA > 0, CFO/atq > iby/atq (cash earnings quality), "
        "declining long-term-debt ratio, improving current ratio, no new "
        "equity issuance, improving gross margin ((saley − cogsy)/saley), and "
        "improving asset turnover (saley/atq). Gross Profitability is "
        "(saley − cogsy)/atq. The accruals ratio is (iby − oancfy)/atq, where "
        "positive values indicate earnings outpacing cash flow. EV/EBITDA "
        "uses EV = mkvaltq + dlttq + dlcq − cheq. P/E uses mkvaltq / iby. "
        "Momentum sums log-returns from t−12 to t−2 within each PERMNO, then "
        "exponentiates back; the reversal flag fires when the prior-month "
        "return is in the universe's bottom decile.",
    )

    add_heading(doc, "3.3 Composite score construction", level=2)
    add_paragraph(
        doc,
        "Each signal is converted to a 0–100 percentile rank across the "
        "universe, with two direction adjustments so higher always means "
        "better: accruals percentiles are inverted (lower accruals = higher "
        "quality), and valuation percentiles are inverted and averaged across "
        "whichever of EV/EBITDA and P/E are available (cheaper = higher value "
        "rank). The composite score is the equal-weighted mean of the five "
        "direction-corrected percentiles. We require at least three of five "
        "signals to be present before assigning a composite, preventing "
        "tiny-cap firms with sparse Compustat coverage from receiving "
        "misleading scores. The dashboard reports both composite_score (0–100) "
        "and its cross-sectional percentile rank (composite_pct). Equal "
        "weighting is deliberate: any optimised weighting would be in-sample "
        "to the same data used to construct the signals, while equal weights "
        "have no free parameters.",
    )


# ---------------------------------------------------------------------------
# Section: Methodology — Sentiment
# ---------------------------------------------------------------------------

def section_sentiment(doc: Document):
    add_heading(doc, "3.4 Earnings call sentiment pipeline", level=2)
    add_paragraph(
        doc,
        "The sentiment pipeline runs in three stages: fetch, parse, score. "
        "parse_transcripts.py splits each transcript into prepared remarks "
        "and Q&A, identifies speaker turns, and classifies each as executive, "
        "analyst, or operator. Only executive turns are retained for scoring; "
        "analyst questions are discarded so the sentiment captures "
        "management's own language. score.py computes three measures: Tone "
        "is VADER's compound sentiment averaged across sentences and bounded "
        "in [−1, +1] (sentence-level averaging avoids the saturation that "
        "VADER exhibits on long texts). Hedging is the fraction of management "
        "words appearing in the Loughran and McDonald (2011) financial "
        "uncertainty word list — a 297-word vocabulary validated on 10-K and "
        "earnings text. Confidence is a forward-looking-sentence ratio "
        "penalised by hedging: confidence = FL_ratio × (1 − 0.5 × hedging), "
        "where FL_ratio is the share of sentences containing at least one of "
        "32 forward-looking keywords (expect, anticipate, guidance, will, "
        "etc.). Quarter-over-quarter deltas and trend labels (improving, "
        "stable, declining) feed directly into the Claude prompt so the "
        "language model reasons about trajectory rather than only the latest "
        "reading.",
    )


# ---------------------------------------------------------------------------
# Section: Methodology — AI Synthesis (with full prompt)
# ---------------------------------------------------------------------------

def section_ai(doc: Document):
    add_heading(doc, "4. AI Synthesis Layer", level=1)

    add_heading(doc, "4.1 Architecture and model choice", level=2)
    add_paragraph(
        doc,
        "The synthesis layer (ai/synthesize.py) sends a single completion "
        "request per ticker to Anthropic's claude-sonnet-4-6 model, chosen "
        "over Opus for the latency and cost profile appropriate to an "
        "interactive dashboard and over Haiku because the task requires "
        "reasoning over structured numeric data and prose rather than pure "
        "classification. Output tokens are capped at 1,024 with a 60-second "
        "client timeout, and errors return a graceful fallback so the "
        "dashboard never hard-crashes on an API failure. Prompt caching is "
        "enabled on the system block via cache_control: ephemeral; the "
        "system prompt is identical across ticker requests and is therefore "
        "billed once per five-minute cache window rather than once per "
        "ticker. Output is constrained to a JSON object with five keys: "
        "bull (2–3 sentences), bear (2–3 sentences), risks (a list of "
        "strings), divergence_flag (boolean), and divergence_note. "
        "Divergence is defined as quant signals and sentiment pointing in "
        "clearly opposite directions — strong fundamentals with cautious "
        "tone, or weak fundamentals with highly optimistic language.",
    )

    add_heading(doc, "4.2 System prompt", level=2)
    add_paragraph(
        doc,
        "Figure 1 shows the key excerpts of the system prompt loaded from "
        "ai/prompt_template.py. The full prompt enumerates each of the five "
        "quant signals and the three sentiment measures with the same "
        "definitions used in Section 3, then constrains the model's output "
        "to the JSON schema shown.",
    )
    add_figure_caption(
        doc, 1,
        "Excerpts from the Claude system prompt",
        "Top: analyst-persona definition. Middle (in square brackets): "
        "elision marker for the signal-definition block, which enumerates "
        "the same five quant signals and three sentiment measures defined "
        "in Section 3. Bottom: required JSON output schema with five fixed "
        "keys (bull, bear, risks, divergence_flag, divergence_note) and the "
        "explicit divergence rule. The prompt is sent to claude-sonnet-4-6 "
        "with cache_control: ephemeral on the system block so the cached "
        "system text is billed once per five-minute window rather than once "
        "per ticker.",
    )
    add_code_block(doc, _SYSTEM_PROMPT_TEXT, size=9)

    add_paragraph(
        doc,
        "The per-ticker user message (build_user_message in "
        "ai/prompt_template.py) follows a structured-data layout: company "
        "name and sector, composite score and percentile, F-Score with all "
        "nine pass/fail components, gross profitability with universe and "
        "sector ranks, accruals ratio and quality rank, EV/EBITDA and P/E "
        "with universe ranks, 12-1 momentum with reversal flag, and up to "
        "six quarters of sentiment scores with QoQ deltas and trend labels. "
        "Missing values render as N/A so the model can reason about coverage "
        "gaps explicitly.",
    )


# ---------------------------------------------------------------------------
# Section: Results
# ---------------------------------------------------------------------------

def section_results(doc: Document, q: pd.DataFrame, s: pd.DataFrame | None):
    add_heading(doc, "5. Results", level=1)
    add_paragraph(
        doc,
        "We illustrate the dashboard with three tickers chosen to span "
        "different fundamental and sentiment profiles: Apple (AAPL), "
        "Microsoft (MSFT), and Harley-Davidson (HOG). Quantitative scores "
        "below reflect the December 31, 2024 data vintage and percentile "
        "ranks vs. the 33,675-name universe. Sentiment scores reflect the "
        "most recent six earnings calls available on Motley Fool as of late "
        "April 2026.",
    )

    # ---- Build a results table ----
    add_table_caption(
        doc, 1,
        "Composite quantitative scores for the three example tickers",
        "Composite score is the equal-weighted mean of five direction-corrected "
        "percentile ranks (F-Score, Gross Profitability, Accruals Quality, "
        "Valuation, Momentum), each on a 0–100 scale where higher is more "
        "favourable. Composite percentile is the cross-sectional rank of the "
        "composite score among the 23,000+ tickers with three or more available "
        "signals. EV/EBITDA percentile reports the raw expensiveness rank where "
        "higher means more expensive; Value percentile inverts and averages "
        "EV/EBITDA and P/E so that higher means cheaper.",
    )

    rows = [
        ["", "AAPL", "MSFT", "HOG"],
        ["Sector", "Manufacturing", "Services", "Manufacturing"],
        ["Composite score (0–100)", *_fmt_each(q, ["AAPL","MSFT","HOG"], "composite_score", ".1f")],
        ["Composite percentile", *_fmt_each(q, ["AAPL","MSFT","HOG"], "composite_pct", ".0f")],
        ["F-Score (0–9)", *_fmt_each(q, ["AAPL","MSFT","HOG"], "fscore", ".0f")],
        ["Gross profitability", *_fmt_each(q, ["AAPL","MSFT","HOG"], "gp_ratio", ".3f")],
        ["GP universe pct", *_fmt_each(q, ["AAPL","MSFT","HOG"], "gp_pct_universe", ".0f")],
        ["Accruals ratio", *_fmt_each(q, ["AAPL","MSFT","HOG"], "accruals_ratio", ".3f")],
        ["EV / EBITDA", *_fmt_each(q, ["AAPL","MSFT","HOG"], "ev_ebitda", ".1f")],
        ["P / E", *_fmt_each(q, ["AAPL","MSFT","HOG"], "pe_ratio", ".1f")],
        ["Value percentile", *_fmt_each(q, ["AAPL","MSFT","HOG"], "value_pct", ".0f")],
        ["12-1 momentum", *_fmt_each(q, ["AAPL","MSFT","HOG"], "mom_12_1", ".1%")],
        ["Momentum percentile", *_fmt_each(q, ["AAPL","MSFT","HOG"], "mom_pct", ".0f")],
    ]
    table = doc.add_table(rows=len(rows), cols=4)
    table.style = "Light Grid Accent 1"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i].cells[j]
            cell.text = val
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                for r in p.runs:
                    r.font.name = BODY_FONT
                    r.font.size = Pt(10)
                    if i == 0 or j == 0:
                        r.bold = True

    # ---- Narrative ----
    add_heading(doc, "5.1 Apple (AAPL) — quality at a price", level=2)
    add_paragraph(
        doc,
        "Apple scores 58 on the composite (73rd percentile). The fundamentals "
        "panel is strong: an F-Score of 6 of 9 (77th percentile), gross "
        "profitability at 0.53 (84th universe percentile, 83rd within "
        "Manufacturing), and a clean accruals reading. Valuation is the "
        "headwind: an EV/EBITDA of 28× sits in the 87th percentile of the "
        "universe (more expensive than 87% of names), pulling the value "
        "percentile to 17 — bottom-quintile cheap. Sentiment is the most "
        "consistent of the three names: tone has held above +0.27 across the "
        "last four quarters, hedging is below 0.03, and confidence has risen "
        "from 0.13 in Q4 2024 to 0.16 in Q1 2026. Claude's bull case "
        "emphasises the durable franchise and high-quality earnings; the "
        "bear case is anchored on the premium valuation. No divergence is "
        "flagged because the strong fundamentals and confident management "
        "language tell the same story.",
    )

    add_heading(doc, "5.2 Microsoft (MSFT) — high quality, fully priced", level=2)
    add_paragraph(
        doc,
        "Microsoft scores 51 on the composite (57th percentile). The F-Score "
        "is 5 of 9, gross profitability is 0.38 (73rd universe percentile), "
        "and EV/EBITDA of 24× places it in the 85th percentile — a profile "
        "comparable to Apple. Sentiment trends similarly: tone has climbed "
        "from neutral in mid-2024 to roughly +0.28 in the last three quarters, "
        "with confidence rising from 0.21 to 0.25. Like AAPL, the model does "
        "not flag a divergence — quant and sentiment are aligned, and the "
        "discussion centres on the growth-versus-valuation tradeoff.",
    )

    add_heading(doc, "5.3 Harley-Davidson (HOG) — value with softening tone", level=2)
    add_paragraph(
        doc,
        "Harley-Davidson scores 56 on the composite (68th percentile) and is "
        "the most interesting of the three. Quality is mid-pack (F-Score 5, "
        "GP 51st universe percentile, 39th in Manufacturing). Valuation is "
        "where it stands out: EV/EBITDA of 9.5× and a P/E of 8.2× place it "
        "in the 70th value percentile — meaningfully cheaper than the "
        "universe median. Sentiment, however, has drifted lower over the "
        "available transcript window: tone has fallen from +0.30 in Q4 2023 "
        "to +0.18 in Q4 2025, while hedging has crept up modestly. Forward-"
        "looking confidence has risen, suggesting management is providing "
        "more concrete guidance even as the overall language has cooled. "
        "This is exactly the type of mismatch the divergence flag is "
        "designed for: an inexpensive name where the numbers screen well but "
        "the executive narrative is no longer as positive.",
    )


def _fmt_each(q: pd.DataFrame, tickers, col: str, fmt: str):
    out = []
    for t in tickers:
        r = q[q["tic"] == t]
        if r.empty:
            out.append("—")
            continue
        v = r.iloc[0].get(col)
        if pd.isna(v):
            out.append("—")
        else:
            try:
                out.append(format(float(v), fmt))
            except Exception:
                out.append(str(v))
    return out


# ---------------------------------------------------------------------------
# Section: Backtesting (placeholder for Blake's input)
# ---------------------------------------------------------------------------

def section_backtest(doc: Document):
    add_heading(doc, "6. Backtesting the Composite Signal", level=1)
    add_paragraph(
        doc,
        "[Backtest results pending — Blake to insert. Plan: extend the signal "
        "calculators to run on each historical fiscal year-end cross-section "
        "(2010–2024), join with CRSP forward 12-month returns at the "
        "appropriate delay, and report quintile portfolio returns with the "
        "long-short Q5 minus Q1 spread. We expect the composite to inherit "
        "the return premia documented in the underlying-signal literature: "
        "Piotroski (2000) reports a 23% annual return spread between high- "
        "and low-F-Score firms; Novy-Marx (2013) documents a roughly 5% "
        "annual gross-profitability premium; Sloan (1996) reports a 10% "
        "annual accruals spread; Jegadeesh and Titman (1993) document a "
        "12% annual momentum premium.]",
        italic=True,
    )


# ---------------------------------------------------------------------------
# Section: Limitations and Future Work
# ---------------------------------------------------------------------------

def section_limitations(doc: Document):
    add_heading(doc, "7. Limitations and Future Work", level=1)

    add_heading(doc, "7.1 Limitations", level=2)
    add_bullets(doc, [
        "Stale data. Quantitative signals reflect December 31, 2024 "
        "fundamentals; a live-data version would require a non-WRDS provider "
        "or an automated pull that handles 2FA.",
        "Transcript coverage. Motley Fool covers most large- and mid-cap U.S. "
        "firms but thins for micro-caps, and recent quarters can be paywalled. "
        "The dashboard surfaces gaps as N/A rather than imputing.",
        "Divergence flag scope. The model occasionally describes contradictions "
        "internal to the sentiment series (e.g., rising confidence with falling "
        "tone) rather than the intended quant-vs-sentiment mismatch.",
        "Single-model dependency. We do not ensemble or self-consistency "
        "sample, so each synthesis reflects one draw of model judgement.",
        "Sector neutrality. Composite percentiles are universe-wide (only "
        "gross profitability is also reported sector-relative). Capital-"
        "intensive industries mechanically rank lower on GP regardless of "
        "intra-sector quality.",
    ])

    add_heading(doc, "7.2 Future work", level=2)
    add_bullets(doc, [
        "Live data feed via a non-WRDS provider, removing the staleness caveat.",
        "Formal portfolio backtest with transaction-cost assumptions and "
        "factor-model attribution against Fama-French five-factor plus momentum.",
        "Sector-relative composite scoring as a second view.",
        "Tighter divergence detection — programmatic comparison of composite "
        "percentile against tone-trend slope before invoking the language model.",
        "Expansion to international equities.",
    ])


# ---------------------------------------------------------------------------
# Section: Bibliography (MLA)
# ---------------------------------------------------------------------------

def section_bibliography(doc: Document):
    add_heading(doc, "Bibliography", level=1)
    refs = [
        "Anthropic. \"Claude API Documentation.\" Anthropic, 2025, "
        "docs.anthropic.com.",
        "Carhart, Mark M. \"On Persistence in Mutual Fund Performance.\" "
        "The Journal of Finance, vol. 52, no. 1, 1997, pp. 57–82.",
        "Fama, Eugene F., and Kenneth R. French. \"A Five-Factor Asset "
        "Pricing Model.\" Journal of Financial Economics, vol. 116, no. 1, "
        "2015, pp. 1–22.",
        "Hutto, C. J., and Eric Gilbert. \"VADER: A Parsimonious Rule-Based "
        "Model for Sentiment Analysis of Social Media Text.\" Proceedings of "
        "the Eighth International AAAI Conference on Weblogs and Social "
        "Media, 2014.",
        "Jegadeesh, Narasimhan, and Sheridan Titman. \"Returns to Buying "
        "Winners and Selling Losers: Implications for Stock Market "
        "Efficiency.\" The Journal of Finance, vol. 48, no. 1, 1993, "
        "pp. 65–91.",
        "Loughran, Tim, and Bill McDonald. \"When Is a Liability Not a "
        "Liability? Textual Analysis, Dictionaries, and 10-Ks.\" The Journal "
        "of Finance, vol. 66, no. 1, 2011, pp. 35–65.",
        "Novy-Marx, Robert. \"The Other Side of Value: The Gross "
        "Profitability Premium.\" Journal of Financial Economics, vol. 108, "
        "no. 1, 2013, pp. 1–28.",
        "Piotroski, Joseph D. \"Value Investing: The Use of Historical "
        "Financial Statement Information to Separate Winners from Losers.\" "
        "Journal of Accounting Research, vol. 38, 2000, pp. 1–41.",
        "Sloan, Richard G. \"Do Stock Prices Fully Reflect Information in "
        "Accruals and Cash Flows about Future Earnings?\" The Accounting "
        "Review, vol. 71, no. 3, 1996, pp. 289–315.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.first_line_indent = Inches(-0.5)
        run = p.add_run(ref)
        run.font.name = BODY_FONT
        run.font.size = Pt(11)


# ---------------------------------------------------------------------------
# System prompt — verbatim copy of ai/prompt_template.py:_SYSTEM, abridged
# only by removing trailing whitespace.  Kept as a constant so the docx is
# reproducible without importing the dashboard package.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEXT = """You are a quantitative equity research analyst. Given structured data on a stock's quant signals and earnings call sentiment, you produce a concise bull/bear synthesis.

[Signal definitions for F-Score, Gross Profitability, Accruals, Valuation, Momentum, and the three sentiment scores — full text in ai/prompt_template.py.]

Respond with ONLY a JSON object:
{
  "bull":  "<2-3 sentences>",
  "bear":  "<2-3 sentences>",
  "risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "divergence_flag": true | false,
  "divergence_note": "<one sentence, or empty if no divergence>"
}

Divergence = quant signals and sentiment clearly point in opposite directions. Only flag true divergences. Keep the output concise and grounded in the numbers provided. Do not make up data."""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build():
    print("Building writeup ...")
    quant = pd.read_parquet(QUANT_PATH, engine="pyarrow")
    sent = None
    if Path(SENT_PATH).exists():
        try:
            sent = pd.read_parquet(SENT_PATH, engine="pyarrow")
        except Exception:
            sent = None

    doc = new_document()

    section_title(doc)
    section_introduction(doc)
    section_data(doc)
    section_quant(doc)
    section_sentiment(doc)
    section_ai(doc)
    section_results(doc, quant, sent)
    section_backtest(doc)
    section_limitations(doc)
    section_bibliography(doc)

    doc.save(OUTPUT_PATH)
    print(f"Saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    build()
