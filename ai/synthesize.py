"""
ai/synthesize.py

Claude AI synthesis for a single ticker — bull case, bear case, key risks,
and a quant-vs-sentiment divergence flag.

Uses claude-sonnet-4-6 with prompt caching on the system block so repeated
calls within the same session don't re-bill the large methodology context.

Public API
----------
    result = synthesize(row, ticker, sent_df)
    # result keys: bull, bear, risks, divergence_flag, divergence_note

Environment
-----------
    ANTHROPIC_API_KEY must be set in the environment or in
    .streamlit/secrets.toml.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

import anthropic
import pandas as pd

from ai.prompt_template import build_user_message, system_prompt

_MODEL = "claude-sonnet-4-6"
_API_TIMEOUT_SECONDS = 60.0

_client: anthropic.Anthropic | None = None


def _get_api_key() -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()

    secrets_path = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return None

    try:
        import tomllib

        raw = secrets_path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        secrets = tomllib.loads(raw.decode("utf-8"))
    except Exception:
        return None

    secret = secrets.get("ANTHROPIC_API_KEY")
    return secret.strip() if isinstance(secret, str) and secret.strip() else None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = _get_api_key()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set in the environment or .streamlit/secrets.toml"
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _parse_json(text: str) -> dict:
    """Extract and parse the JSON object from Claude's response."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))
    return json.loads(text)


_FALLBACK: dict = {
    "bull": "Unable to generate synthesis — API error.",
    "bear": "Unable to generate synthesis — API error.",
    "risks": ["Check ANTHROPIC_API_KEY and retry."],
    "divergence_flag": False,
    "divergence_note": "",
}


def synthesize(
    row: pd.Series,
    ticker: str,
    sent_df: pd.DataFrame | None,
) -> dict:
    """
    Generate a bull/bear synthesis for *ticker* using Claude.

    Parameters
    ----------
    row : pd.Series
        Row from quant_metrics.parquet for this ticker.
    ticker : str
        Ticker symbol.
    sent_df : pd.DataFrame | None
        Sentiment rows for this ticker (filtered, sorted oldest→newest),
        or None if unavailable.

    Returns
    -------
    dict with keys: bull, bear, risks (list[str]), divergence_flag (bool),
    divergence_note (str).
    """
    try:
        client = _get_client()

        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": build_user_message(row, ticker, sent_df)},
            ],
            timeout=_API_TIMEOUT_SECONDS,
        )

        raw = "".join(
            block.text for block in response.content if getattr(block, "text", None)
        )
        if not raw.strip():
            raise ValueError("Claude returned no text content.")
        result = _parse_json(raw)

        return {
            "bull": str(result.get("bull", "")),
            "bear": str(result.get("bear", "")),
            "risks": [str(r) for r in result.get("risks", [])],
            "divergence_flag": bool(result.get("divergence_flag", False)),
            "divergence_note": str(result.get("divergence_note", "")),
        }

    except Exception as exc:
        return {**_FALLBACK, "bear": f"Error: {exc}"}


# ---------------------------------------------------------------------------
# Smoke-test (python -m ai.synthesize AAPL)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    ticker = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    print(f"Running AI synthesis for {ticker} ...\n")

    quant_df = pd.read_parquet("data/quant_metrics.parquet", engine="fastparquet")
    matches = quant_df[quant_df["tic"] == ticker]
    if matches.empty:
        print(f"Ticker {ticker} not found in quant_metrics.parquet")
        sys.exit(1)

    row = matches.iloc[0]

    from sentiment.trend import load_ticker_sentiment
    sent_df = load_ticker_sentiment(ticker)
    if sent_df.empty:
        sent_df = None
        print("No sentiment data — synthesising quant-only.\n")
    else:
        print(f"Sentiment: {len(sent_df)} quarters loaded.\n")

    result = synthesize(row, ticker, sent_df)

    print("=== BULL CASE ===")
    print(result["bull"])
    print("\n=== BEAR CASE ===")
    print(result["bear"])
    print("\n=== KEY RISKS ===")
    for r in result["risks"]:
        print(f"  - {r}")
    if result["divergence_flag"]:
        print(f"\n[DIVERGENCE] {result['divergence_note']}")
