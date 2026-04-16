"""
sentiment/fetch_transcripts.py

Fetch earnings call transcripts from SEC EDGAR 8-K filings.

Strategy:
  1. Resolve ticker → CIK using EDGAR company_tickers.json (cached in memory)
  2. Pull filing history from data.sec.gov/submissions/CIK{cik}.json
  3. Walk recent 8-K filings; filter candidates by item number (7.01, 8.01, 9.01)
     or exhibit filename containing "transcript"
  4. For each candidate, fetch the filing index to find all exhibits
  5. Download the exhibit most likely to be the transcript (99.1, 99.2, or the
     primary doc) and extract the call section
  6. Return last N quarters as list of dicts; empty list if nothing found

No fallback scraper — if EDGAR has no clean transcript, callers receive [].

EDGAR rate-limit: 10 req/s is the documented limit; we sleep 0.12 s between
document downloads to stay comfortably within it.
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": "StockAnalysisDashboard will.pechersky@utexas.edu",
    "Accept-Encoding": "gzip, deflate",
}

EDGAR_DATA = "https://data.sec.gov"
EDGAR_WWW = "https://www.sec.gov"

# Keyword signals that a filing contains an earnings call transcript
_TRANSCRIPT_KEYWORDS = frozenset([
    "transcript", "earnings call", "conference call", "earnings conference",
])
# Item numbers that typically carry transcript exhibits
_TRANSCRIPT_ITEMS = frozenset(["7.01", "8.01", "9.01"])

# Minimum characters for a filing to be plausible transcript content
_MIN_TRANSCRIPT_LEN = 2_000

# ---------------------------------------------------------------------------
# Module-level CIK cache (populated once per process)
# ---------------------------------------------------------------------------
_ticker_to_cik: Optional[dict[str, str]] = None


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

def _load_ticker_map() -> dict[str, str]:
    """Download and cache the EDGAR ticker→CIK mapping (runs once)."""
    global _ticker_to_cik
    if _ticker_to_cik is None:
        resp = requests.get(
            f"{EDGAR_WWW}/files/company_tickers.json",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _ticker_to_cik = {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in data.values()
        }
    return _ticker_to_cik


def get_cik(ticker: str) -> Optional[str]:
    """Return zero-padded 10-digit CIK for *ticker*, or None if not in EDGAR."""
    return _load_ticker_map().get(ticker.upper())


# ---------------------------------------------------------------------------
# Filing discovery
# ---------------------------------------------------------------------------

def _get_submissions(cik: str) -> list[dict]:
    """
    Return recent 8-K filing records for *cik* from the EDGAR submissions API.
    Each record: {accession_raw, accession_fmt, date, primary_doc, items}
    """
    url = f"{EDGAR_DATA}/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])
    items_list = recent.get("items", [])

    records = []
    for i, form in enumerate(forms):
        if form in ("8-K", "8-K/A"):
            acc_fmt = accessions[i]          # e.g. "0001234567-24-000001"
            acc_raw = acc_fmt.replace("-", "")  # e.g. "0001234567240000001" (18 chars, no dashes)
            records.append({
                "accession_raw": acc_raw,
                "accession_fmt": acc_fmt,
                "date": dates[i],
                "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
                "items": items_list[i] if i < len(items_list) else "",
            })
    return records


def _is_transcript_candidate(record: dict) -> bool:
    """Heuristic: does this 8-K record likely contain an earnings call transcript?"""
    items = record.get("items", "") or ""
    primary_doc = (record.get("primary_doc", "") or "").lower()

    # Item number match
    for item in _TRANSCRIPT_ITEMS:
        if item in items:
            return True

    # Filename match
    if any(kw in primary_doc for kw in ["transcript", "earnings"]):
        return True

    return False


# ---------------------------------------------------------------------------
# Filing index and exhibit resolution
# ---------------------------------------------------------------------------

def _get_filing_index(cik: str, accession_raw: str) -> list[dict]:
    """
    Fetch the filing index JSON and return all documents.
    Each doc dict has keys: name, type, description, url.
    """
    cik_int = int(cik)
    url = (
        f"{EDGAR_WWW}/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik_int}"
        f"&type=8-K&dateb=&owner=include&count=10"
    )
    # Use the direct index JSON endpoint instead
    index_url = (
        f"{EDGAR_WWW}/Archives/edgar/data/{cik_int}"
        f"/{accession_raw}/{accession_raw}-index.json"
    )
    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    docs = []
    for item in data.get("directory", {}).get("item", []):
        name = item.get("name", "")
        docs.append({
            "name": name,
            "type": item.get("type", ""),
            "description": item.get("description", ""),
            "url": (
                f"{EDGAR_WWW}/Archives/edgar/data/{cik_int}"
                f"/{accession_raw}/{name}"
            ),
        })
    return docs


def _pick_best_exhibit(docs: list[dict], primary_doc: str) -> Optional[str]:
    """
    From the filing document list, return the URL most likely to contain the
    earnings call transcript text.

    Priority:
      1. Any document whose name/description contains "transcript"
      2. ex99-1, ex99.1, exhibit99 style files (most common transcript exhibit)
      3. The primary document itself
    """
    # Normalise
    lower_docs = [(d, d["name"].lower(), d["description"].lower()) for d in docs]

    # Priority 1 — explicit transcript label
    for d, name, desc in lower_docs:
        if "transcript" in name or "transcript" in desc:
            return d["url"]

    # Priority 2 — exhibit 99.x (common for Reg FD disclosures)
    for d, name, _ in lower_docs:
        if re.search(r"ex[\-_]?99", name) or re.search(r"exhibit[\-_]?99", name):
            if name.endswith((".htm", ".html", ".txt")):
                return d["url"]

    # Priority 3 — primary document
    primary_lower = primary_doc.lower()
    for d, name, _ in lower_docs:
        if name == primary_lower:
            return d["url"]

    # Fallback: first HTM/TXT in the list
    for d, name, _ in lower_docs:
        if name.endswith((".htm", ".html", ".txt")):
            return d["url"]

    return None


# ---------------------------------------------------------------------------
# Text extraction and cleaning
# ---------------------------------------------------------------------------

def _fetch_text(url: str) -> Optional[str]:
    """Download *url* and return plain text (HTML is stripped). None on error."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
    except Exception:
        return None

    content_type = resp.headers.get("content-type", "")
    raw = resp.content

    if "html" in content_type or url.lower().endswith((".htm", ".html")):
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    else:
        text = raw.decode("utf-8", errors="replace")

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_transcript_section(text: str) -> Optional[str]:
    """
    Extract the earnings call portion from an 8-K filing body.

    Tries to find the start of the call (Operator greeting, Safe Harbor intro,
    or an explicit transcript header) and the end (closing remarks).
    Falls back to the full text if no clear boundary is found.
    """
    if not text:
        return None

    # --- Find the start ---
    start_patterns = [
        # Operator opening line
        r"(?im)^(?:operator|moderator)\s*[:\-]\s*(?:good\s+(?:morning|afternoon|evening)|ladies and gentlemen|welcome|thank you)",
        # Explicit transcript header
        r"(?i)earnings\s+(?:call\s+)?transcript",
        r"(?i)q[1-4]\s+\d{4}\s+(?:earnings|results)\s+(?:call|conference)",
        # Date + call format seen in many 8-Ks
        r"(?i)(?:first|second|third|fourth)\s+quarter\s+\d{4}\s+(?:earnings|results)",
    ]

    start_idx = 0
    for pattern in start_patterns:
        m = re.search(pattern, text)
        if m:
            # Back up a little to capture any heading on the preceding line
            start_idx = max(0, m.start() - 100)
            break

    text = text[start_idx:]

    # --- Strip trailing exhibit separators / legal boilerplate ---
    end_patterns = [
        r"(?i)(?:this|that)\s+(?:concludes|ends)\s+(?:today'?s?|the)\s+(?:conference|call|presentation|webcast)",
        r"(?i)thank\s+you\s+for\s+(?:participating|joining|attending|your\s+participation)",
        r"(?im)^[-_=]{20,}\s*$",   # visual divider often after transcript
    ]
    end_idx = len(text)
    for pattern in end_patterns:
        m = re.search(pattern, text)
        if m:
            candidate = m.end() + 300  # keep a small tail
            end_idx = min(end_idx, candidate)
            break

    extracted = text[:end_idx].strip()

    # Must contain at least some call-like signals to be useful
    has_signals = any(kw in extracted.lower() for kw in [
        "operator", "analyst", "question", "revenue", "earnings",
        "quarter", "guidance", "margin",
    ])
    return extracted if (has_signals and len(extracted) >= _MIN_TRANSCRIPT_LEN) else None


def _strip_safe_harbor(text: str) -> str:
    """Remove common Safe Harbor boilerplate paragraphs at the start."""
    # Many transcripts open with a Safe Harbor / forward-looking statement block
    pattern = (
        r"(?i)(?:SAFE\s+HARBOR|FORWARD[- ]LOOKING\s+STATEMENT)"
        r".{0,2000}?"
        r"(?=\n\n|\Z)"
    )
    return re.sub(pattern, "", text, count=1, flags=re.DOTALL).strip()


def _infer_quarter_label(date_str: str) -> str:
    """'2024-11-01' → 'Q4 2024' (calendar quarter of the filing date)."""
    try:
        year, month, _ = date_str.split("-")
        q = (int(month) - 1) // 3 + 1
        return f"Q{q} {year}"
    except Exception:
        return date_str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_earnings_transcripts(
    ticker: str,
    n_quarters: int = 6,
    *,
    max_filings_to_scan: int = 30,
) -> list[dict]:
    """
    Fetch the last *n_quarters* earnings call transcripts for *ticker* from
    SEC EDGAR 8-K filings.

    Parameters
    ----------
    ticker : str
        US equity ticker (case-insensitive).
    n_quarters : int
        Maximum number of quarterly transcripts to return (most recent first).
    max_filings_to_scan : int
        How many 8-K filings to inspect before giving up (avoids long loops for
        companies that file many non-earnings 8-Ks).

    Returns
    -------
    list[dict]
        Each element has keys:
          ticker, date (YYYY-MM-DD), quarter_label, transcript_text, url, accession
        Returns [] if EDGAR has no usable transcript.
    """
    ticker = ticker.upper()

    cik = get_cik(ticker)
    if cik is None:
        return []

    try:
        all_8ks = _get_submissions(cik)
    except Exception:
        return []

    results: list[dict] = []
    scanned = 0

    for record in all_8ks:
        if len(results) >= n_quarters or scanned >= max_filings_to_scan:
            break

        if not _is_transcript_candidate(record):
            continue

        scanned += 1

        # Get filing index to find the right exhibit
        time.sleep(0.12)
        docs = _get_filing_index(cik, record["accession_raw"])

        exhibit_url = _pick_best_exhibit(docs, record["primary_doc"])
        if exhibit_url is None:
            # Fall back to constructing the primary doc URL directly
            cik_int = int(cik)
            exhibit_url = (
                f"{EDGAR_WWW}/Archives/edgar/data/{cik_int}"
                f"/{record['accession_raw']}/{record['primary_doc']}"
            )

        time.sleep(0.12)
        raw_text = _fetch_text(exhibit_url)
        if not raw_text:
            continue

        transcript_text = _extract_transcript_section(raw_text)
        if transcript_text is None:
            continue

        transcript_text = _strip_safe_harbor(transcript_text)

        results.append({
            "ticker": ticker,
            "date": record["date"],
            "quarter_label": _infer_quarter_label(record["date"]),
            "transcript_text": transcript_text,
            "url": exhibit_url,
            "accession": record["accession_fmt"],
        })

    return results


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly: python -m sentiment.fetch_transcripts)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    test_tickers = sys.argv[1:] or ["AAPL", "MSFT", "NVDA", "JPM", "TSLA"]
    print(f"Testing fetch_earnings_transcripts on: {test_tickers}\n")

    for ticker in test_tickers:
        print(f"--- {ticker} ---")
        transcripts = fetch_earnings_transcripts(ticker, n_quarters=2)
        if not transcripts:
            print("  [not available]\n")
        else:
            for t in transcripts:
                word_count = len(t["transcript_text"].split())
                print(f"  {t['quarter_label']}  |  {t['date']}  |  {word_count:,} words")
                print(f"  URL: {t['url']}")
            print()
