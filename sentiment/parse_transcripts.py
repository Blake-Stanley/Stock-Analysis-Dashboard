"""
sentiment/parse_transcripts.py

Parse and clean raw earnings call transcript text produced by fetch_transcripts.

Given the `transcript_text` string from fetch_earnings_transcripts(), this module:
  1. Splits the text into a prepared-remarks section and a Q&A section
  2. Parses each section into speaker turns {speaker, affiliation, text}
  3. Classifies each speaker as executive | analyst | operator
  4. Strips operator logistics lines (hold music cues, dial-in instructions)
  5. Exposes clean combined text for management remarks and analyst questions

Public API
----------
    parsed = parse_transcript(transcript_text)
    parsed.prepared_remarks_text   # clean str — management prepared remarks
    parsed.qa_text                 # clean str — full Q&A section
    parsed.management_text         # management turns from BOTH sections combined
    parsed.analyst_text            # analyst question turns
    parsed.turns                   # list[Turn] — every speaker turn in order
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    speaker: str          # raw name as it appears in the transcript
    affiliation: str      # company / bank extracted from header, or ""
    role: str             # "executive" | "analyst" | "operator" | "unknown"
    section: str          # "prepared" | "qa"
    text: str             # cleaned body text of this turn


@dataclass
class ParsedTranscript:
    prepared_remarks_text: str        # clean text — prepared remarks section
    qa_text: str                      # clean text — Q&A section
    management_text: str              # all executive turns concatenated
    analyst_text: str                 # all analyst turns concatenated
    turns: list[Turn] = field(default_factory=list)

    @property
    def has_qa(self) -> bool:
        return bool(self.qa_text.strip())

    @property
    def has_prepared(self) -> bool:
        return bool(self.prepared_remarks_text.strip())


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Markers that signal the start of the Q&A section
# Inline flags stripped — re.IGNORECASE | re.MULTILINE passed to compile instead
_QA_START_PATTERNS = [
    r"^.*\bquestion[- ]and[- ]answer\b.*session.*$",
    r"^.*\bq\s*&\s*a\b.*session.*$",
    r"^(?:operator|moderator)\s*[:\-]\s*.*\bquestions?\b.*",
    r"we\s+will\s+now\s+(?:begin|open|take)\s+(?:the\s+)?(?:question|q&a|q\s+and\s+a)",
    r"(?:open(?:ing)?|begin(?:ning)?)\s+(?:the\s+)?(?:floor|lines?)\s+(?:to|for)\s+questions?",
    r"now\s+(?:open|begin)\s+(?:up\s+)?(?:for\s+)?(?:the\s+)?(?:question|q&a)",
]
_QA_START_RE = re.compile("|".join(_QA_START_PATTERNS), re.IGNORECASE | re.MULTILINE)

# Speaker header formats:
#
#  EDGAR (header-per-line):
#   "John Smith — Chief Financial Officer:"   (colon at end of line)
#   "JOHN SMITH, Goldman Sachs:"
#   "John Smith (CFO):"
#
#  Motley Fool (inline):
#   "John Smith: text continues on same line..."
#   "Operator: [Operator Instructions] ..."
#
# The regex captures both by making end-of-line optional — the name+colon
# may be followed by either end-of-line (EDGAR) or a space + body text (Fool).
_SPEAKER_RE = re.compile(
    r"^"
    r"(?P<name>[A-Z][A-Za-z\.\-']+(?:\s+[A-Z][A-Za-z\.\-']+){0,4})"   # Name (1-5 title-cased words)
    r"(?:"
        r"\s*[—–\-]\s*(?P<affil1>[^:\n]{1,60})"   # — Affiliation
        r"|"
        r",\s*(?P<affil2>[^:\n]{1,60})"            # , Affiliation
        r"|"
        r"\s*\((?P<affil3>[^)\n]{1,60})\)"         # (Affiliation)
    r")?"
    r"\s*:[ \t]*(?=$|\s)",                         # colon then end-of-line OR whitespace
    re.MULTILINE,
)

# Bracketed speaker format: [Operator], [John Smith]
_BRACKET_SPEAKER_RE = re.compile(
    r"^\[(?P<name>[A-Za-z][^\]\n]{1,60})\]\s*:?[ \t]*$",
    re.MULTILINE,
)

# Operator logistics lines — content-free, safe to drop entirely
# Inline flags stripped — re.IGNORECASE passed to compile instead
_OPERATOR_NOISE_PATTERNS = [
    r"please\s+(?:press|dial|hold|stand\s+by|remain\s+on\s+the\s+line)",
    r"(?:your|the)\s+line\s+is\s+(?:open|muted|now\s+open)",
    r"please\s+go\s+ahead",
    r"one\s+moment\s+(?:please|while\s+we)",
    r"(?:ladies\s+and\s+)?gentlemen,?\s+(?:please|thank\s+you\s+for\s+(?:your\s+)?patience)",
    r"this\s+call\s+(?:is\s+being\s+)?recorded",
    r"(?:press|dial)\s+(?:star|pound|\*|#)\s*(?:one|1|two|2)",
    r"to\s+ask\s+a\s+question.*?(?:press|dial)",
    r"our\s+next\s+(?:question|caller)\s+comes?\s+from",
    r"the\s+next\s+question\s+(?:is\s+)?from",
    r"we\s+have\s+no\s+further\s+questions",
    r"(?:that\s+)?(?:concludes|ends)\s+(?:today'?s?|our|the)\s+(?:question|q&a|conference|call)",
]
_OPERATOR_NOISE_RE = re.compile("|".join(_OPERATOR_NOISE_PATTERNS), re.IGNORECASE)

# Role classification keywords
_EXECUTIVE_TITLES = frozenset([
    "ceo", "cfo", "coo", "cto", "cpo", "president", "chairman", "chair",
    "chief", "executive", "officer", "director", "founder", "vice president",
    "vp", "head of", "treasurer", "controller", "secretary",
    "investor relations", "ir ",
])
_ANALYST_FIRMS = frozenset([
    "goldman", "morgan", "jp morgan", "jpmorgan", "barclays", "citi", "citigroup",
    "ubs", "credit suisse", "deutsche", "wells fargo", "bank of america", "bofa",
    "raymond james", "piper", "stifel", "jefferies", "cowen", "baird",
    "needham", "berenberg", "mizuho", "truist", "oppenheimer", "canaccord",
    "research", "securities", "capital", "partners", "advisors", "asset management",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_role(speaker: str, affiliation: str) -> str:
    """Classify a speaker turn as executive | analyst | operator | unknown."""
    s = speaker.lower()
    a = affiliation.lower()

    if s in ("operator", "moderator", "conference operator"):
        return "operator"

    combined = s + " " + a
    if any(kw in combined for kw in _EXECUTIVE_TITLES):
        return "executive"
    if any(kw in combined for kw in _ANALYST_FIRMS):
        return "analyst"

    # Analysts are often identified only by firm in the affiliation field
    if a and not any(kw in a for kw in _EXECUTIVE_TITLES):
        # Anything that looks like a bank/research firm → analyst
        if re.search(r"(?i)\b(?:llc|llp|inc|corp|co\.|group|fund)\b", a):
            return "analyst"

    return "unknown"


def _clean_body(text: str) -> str:
    """Normalise whitespace and remove residual HTML artifacts."""
    # Remove HTML entities that BeautifulSoup may have missed
    text = re.sub(r"&(?:nbsp|amp|lt|gt|quot|apos);", " ", text)
    # Collapse runs of spaces/tabs
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Normalise line endings
    text = re.sub(r"\r\n?", "\n", text)
    # Drop lines that are purely dashes/underscores/equals (visual dividers)
    text = re.sub(r"(?m)^[-_=*]{3,}\s*$", "", text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_operator_noise(line: str) -> bool:
    return bool(_OPERATOR_NOISE_RE.search(line))


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> tuple[str, str]:
    """
    Split transcript into (prepared_remarks, qa_section).
    Returns (full_text, "") if no Q&A boundary is found.
    """
    m = _QA_START_RE.search(text)
    if m:
        return text[: m.start()].strip(), text[m.start() :].strip()
    return text.strip(), ""


# ---------------------------------------------------------------------------
# Speaker-turn parsing
# ---------------------------------------------------------------------------

def _find_speaker_spans(text: str) -> list[tuple[int, int, str, str]]:
    """
    Return a list of (start, end, name, affiliation) tuples for all speaker
    headers found in *text*.  end = index of the first char of the body.
    """
    spans: list[tuple[int, int, str, str]] = []

    for m in _SPEAKER_RE.finditer(text):
        name = m.group("name").strip()
        affil = (
            m.group("affil1") or m.group("affil2") or m.group("affil3") or ""
        ).strip()
        spans.append((m.start(), m.end(), name, affil))

    for m in _BRACKET_SPEAKER_RE.finditer(text):
        name = m.group("name").strip()
        spans.append((m.start(), m.end(), name, ""))

    # Sort by position
    spans.sort(key=lambda x: x[0])
    return spans


def _parse_turns(text: str, section: str) -> list[Turn]:
    """Parse a section of transcript text into a list of Turn objects."""
    if not text.strip():
        return []

    spans = _find_speaker_spans(text)

    if not spans:
        # No speaker headers found — return the whole block as one unknown turn
        cleaned = _clean_body(text)
        if cleaned:
            return [Turn("", "", "unknown", section, cleaned)]
        return []

    turns: list[Turn] = []

    # Text before the first speaker header (often a section title — discard if short)
    preamble = text[: spans[0][0]].strip()
    if preamble and len(preamble) > 80:
        turns.append(Turn("", "", "unknown", section, _clean_body(preamble)))

    for i, (start, end, name, affil) in enumerate(spans):
        body_start = end
        body_end = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        raw_body = text[body_start:body_end]

        # Filter operator noise lines but keep substantive operator content
        role = _classify_role(name, affil)
        if role == "operator":
            lines = raw_body.splitlines()
            raw_body = "\n".join(
                ln for ln in lines if not _is_operator_noise(ln)
            )

        body = _clean_body(raw_body)
        if not body:
            continue

        turns.append(Turn(name, affil, role, section, body))

    return turns


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_transcript(transcript_text: str) -> ParsedTranscript:
    """
    Parse raw transcript text into a structured ParsedTranscript.

    Parameters
    ----------
    transcript_text : str
        Raw text from fetch_transcripts.fetch_earnings_transcripts()
        (after _extract_transcript_section and _strip_safe_harbor).

    Returns
    -------
    ParsedTranscript
        Structured object with clean text fields and a list of speaker turns.
    """
    text = _clean_body(transcript_text)

    prepared_raw, qa_raw = _split_sections(text)

    prepared_turns = _parse_turns(prepared_raw, "prepared")
    qa_turns = _parse_turns(qa_raw, "qa")
    all_turns = prepared_turns + qa_turns

    management_text = "\n\n".join(
        t.text for t in all_turns if t.role == "executive"
    )
    analyst_text = "\n\n".join(
        t.text for t in all_turns if t.role == "analyst"
    )

    return ParsedTranscript(
        prepared_remarks_text=prepared_raw,
        qa_text=qa_raw,
        management_text=management_text,
        analyst_text=analyst_text,
        turns=all_turns,
    )


# ---------------------------------------------------------------------------
# Quick smoke-test (python -m sentiment.parse_transcripts)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from sentiment.fetch_transcripts import fetch_earnings_transcripts

    test_tickers = sys.argv[1:] or ["AAPL", "MSFT"]
    print(f"Fetching + parsing transcripts for: {test_tickers}\n")

    for ticker in test_tickers:
        print(f"=== {ticker} ===")
        transcripts = fetch_earnings_transcripts(ticker, n_quarters=1)
        if not transcripts:
            print("  [not available]\n")
            continue

        t = transcripts[0]
        parsed = parse_transcript(t["transcript_text"])

        role_counts: dict[str, int] = {}
        for turn in parsed.turns:
            role_counts[turn.role] = role_counts.get(turn.role, 0) + 1

        print(f"  Quarter : {t['quarter_label']}")
        print(f"  Turns   : {len(parsed.turns)}  {role_counts}")
        print(f"  Prepared: {len(parsed.prepared_remarks_text):,} chars")
        print(f"  Q&A     : {len(parsed.qa_text):,} chars")
        print(f"  Mgmt    : {len(parsed.management_text):,} chars")
        print(f"  Analyst : {len(parsed.analyst_text):,} chars")
        print()
