"""
sentiment/fetch_motley_fool.py

Fetch earnings call transcripts from The Motley Fool.

Strategy (fast path):
  1. Resolve ticker → EDGAR company name → URL slug
  2. Fetch fool.com/quote/{exchange}/{slug}/{ticker}/ (the per-stock quote page)
     which lists ~8 recent transcript links directly — no pagination needed.
  3. Try "nasdaq" then "nyse" exchange prefix; fall back to listing pagination
     if neither quote page returns transcript links.

Fallback (slow path):
  Paginate through fool.com/earnings-call-transcripts/page/{n}/ and filter
  URLs containing "-{ticker.lower()}-". Used only when the quote page fails.

Motley Fool transcript URL pattern:
  /earnings/call-transcripts/YYYY/MM/DD/{company}-{ticker}-q{N}-{year}-earnings[-call]-transcript/

Speaker format in extracted text (after HTML→text):
  "Name: text on the same line"   ← inline format, not header-per-line
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE = "https://www.fool.com"
EDGAR_WWW = "https://www.sec.gov"

_LISTING_PAGE1 = BASE + "/earnings-call-transcripts/"
_LISTING_PAGEN = BASE + "/earnings-call-transcripts/page/{page}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Intentionally omit Accept-Encoding: br — requests cannot decompress Brotli
    # without the optional brotli package; omitting lets the server serve gzip or
    # plain text, which requests handles natively.
    "Connection": "keep-alive",
}

_MIN_TRANSCRIPT_LEN = 1_500   # chars — discard pages that are mostly boilerplate
_MAX_PAGES = 40               # fallback pagination limit

# Module-level cache for EDGAR ticker → company name
_edgar_names: Optional[dict[str, str]] = None

_TRANSCRIPT_URL_RE = re.compile(
    r'/earnings/call-transcripts/\d{4}/\d{2}/\d{2}/[^\"\s<>\\]+'
)


# ---------------------------------------------------------------------------
# EDGAR company name lookup (used to build the Motley Fool quote page URL)
# ---------------------------------------------------------------------------

def _load_edgar_names() -> dict[str, str]:
    global _edgar_names
    if _edgar_names is None:
        resp = requests.get(
            f"{EDGAR_WWW}/files/company_tickers.json",
            headers={"User-Agent": "StockAnalysisDashboard pecherskyw@gmail.com"},
            timeout=15,
        )
        resp.raise_for_status()
        _edgar_names = {
            v["ticker"].upper(): v["title"]
            for v in resp.json().values()
        }
    return _edgar_names


def _company_slug(ticker: str) -> Optional[str]:
    """
    Convert EDGAR company name to a Motley Fool URL slug.
    e.g. "Apple Inc." -> "apple", "MICROSOFT CORP" -> "microsoft"
    """
    names = _load_edgar_names()
    name = names.get(ticker.upper())
    if not name:
        return None
    name = name.lower()
    name = re.sub(r"\b(inc\.?|corp\.?|ltd\.?|llc\.?|plc\.?|co\.?)\b", "", name)
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return name


# ---------------------------------------------------------------------------
# Fast path: per-stock quote page
# ---------------------------------------------------------------------------

def _quote_page_urls(ticker: str, n: int) -> list[str]:
    """
    Fetch the Motley Fool quote page for *ticker* and return up to *n*
    transcript URLs. Tries "nasdaq" then "nyse" exchange prefixes.
    Returns [] if neither works.
    """
    slug = _company_slug(ticker)
    if not slug:
        return []

    t = ticker.lower()
    for exchange in ("nasdaq", "nyse", "nysemkt", "nysearca"):
        url = f"{BASE}/quote/{exchange}/{slug}/{t}/"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
        except Exception:
            continue

        links = list(dict.fromkeys(
            BASE + s.rstrip("/") + "/"
            for s in _TRANSCRIPT_URL_RE.findall(resp.text)
        ))
        if links:
            return links[:n]

    return []


# ---------------------------------------------------------------------------
# Slow fallback: paginate the shared listing
# ---------------------------------------------------------------------------

def _get_listing_links(page: int) -> list[str]:
    """Return all transcript URLs on one listing page (regex over raw HTML)."""
    url = _LISTING_PAGE1 if page == 1 else _LISTING_PAGEN.format(page=page)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except Exception:
        return []

    slugs = _TRANSCRIPT_URL_RE.findall(resp.text)
    links = [BASE + s.rstrip("/") + "/" for s in slugs]
    return list(dict.fromkeys(links))


def _listing_urls(ticker: str, n: int, max_pages: int = _MAX_PAGES) -> list[str]:
    """Fallback: scan listing pages for up to *n* URLs matching *ticker*."""
    slug_fragment = f"-{ticker.lower()}-"
    found: list[str] = []
    for page in range(1, max_pages + 1):
        links = _get_listing_links(page)
        if not links:
            break
        for url in links:
            if slug_fragment in url and url not in found:
                found.append(url)
                if len(found) >= n:
                    return found
        time.sleep(0.5)
    return found


def _find_transcript_urls(ticker: str, n: int) -> list[str]:
    """
    Return up to *n* Motley Fool transcript URLs for *ticker*.
    Tries the quote page first (fast); falls back to listing pagination.
    """
    urls = _quote_page_urls(ticker, n)
    if urls:
        return urls
    return _listing_urls(ticker, n)


# ---------------------------------------------------------------------------
# Transcript page downloader + text extractor
# ---------------------------------------------------------------------------

def _fetch_transcript_text(url: str) -> Optional[str]:
    """
    Download a Motley Fool transcript page and return the article body as
    plain text, preserving speaker-turn line structure.
    Returns None on error or if the page looks like a paywall / empty result.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.content, "html.parser")

    # Remove nav, header, footer, sidebar, ads
    for tag in soup(["nav", "header", "footer", "aside", "script", "style",
                     "noscript", "iframe", "button", "form"]):
        tag.decompose()

    # Try known content containers (Motley Fool uses several over time)
    article_body = None
    for selector in [
        {"class_": "article-body"},
        {"class_": "tailwind-article-body"},
        {"itemprop": "articleBody"},
        {"class_": "content"},
        "article",
    ]:
        if isinstance(selector, dict):
            article_body = soup.find("div", **selector) or soup.find("section", **selector)
        else:
            article_body = soup.find(selector)
        if article_body:
            break

    # Fallback: use the largest <div> block by text length
    if article_body is None:
        divs = soup.find_all("div")
        if divs:
            article_body = max(divs, key=lambda d: len(d.get_text()))

    if article_body is None:
        return None

    # Extract text paragraph by paragraph so speaker turns land on their own lines
    lines: list[str] = []
    for elem in article_body.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
        text = elem.get_text(" ", strip=True)
        if text:
            lines.append(text)

    full_text = "\n".join(lines)

    # Normalise whitespace
    full_text = re.sub(r"[ \t]{2,}", " ", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    return full_text.strip() if len(full_text) >= _MIN_TRANSCRIPT_LEN else None


# ---------------------------------------------------------------------------
# Metadata extraction from URL
# ---------------------------------------------------------------------------

def _parse_url_metadata(url: str) -> dict[str, str]:
    """
    Extract date and quarter label from a Motley Fool transcript URL.
    e.g. /2026/04/16/apple-aapl-q1-2026-earnings-call-transcript/
    → date="2026-04-16", quarter_label="Q1 2026"
    """
    date_m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    date = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}" if date_m else ""

    quarter_m = re.search(r"-(q[1-4])-?(\d{4})-", url, re.IGNORECASE)
    if quarter_m:
        quarter_label = f"{quarter_m.group(1).upper()} {quarter_m.group(2)}"
    elif date_m:
        year = date_m.group(1)
        month = int(date_m.group(2))
        q = (month - 1) // 3 + 1
        quarter_label = f"Q{q} {year}"
    else:
        quarter_label = ""

    return {"date": date, "quarter_label": quarter_label}


# ---------------------------------------------------------------------------
# Public API (mirrors fetch_transcripts.fetch_earnings_transcripts)
# ---------------------------------------------------------------------------

def fetch_earnings_transcripts(
    ticker: str,
    n_quarters: int = 6,
) -> list[dict]:
    """
    Fetch the last *n_quarters* earnings call transcripts for *ticker* from
    The Motley Fool.

    Parameters
    ----------
    ticker : str
        US equity ticker (case-insensitive).
    n_quarters : int
        Maximum number of quarterly transcripts to return (most recent first).

    Returns
    -------
    list[dict]
        Each element: ticker, date, quarter_label, transcript_text, url, accession.
        Returns [] if no transcripts found.
    """
    ticker = ticker.upper()
    urls = _find_transcript_urls(ticker, n=n_quarters)

    results: list[dict] = []
    for url in urls:
        time.sleep(0.6)
        text = _fetch_transcript_text(url)
        if not text:
            continue

        meta = _parse_url_metadata(url)
        results.append({
            "ticker": ticker,
            "date": meta["date"],
            "quarter_label": meta["quarter_label"],
            "transcript_text": text,
            "url": url,
            "accession": "",   # N/A for Motley Fool (no SEC accession number)
        })

    return results


# ---------------------------------------------------------------------------
# Smoke-test (python -m sentiment.fetch_motley_fool)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    test_tickers = sys.argv[1:] or ["AAPL", "MSFT", "NVDA"]
    print(f"Testing Motley Fool fetcher on: {test_tickers}\n")

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
