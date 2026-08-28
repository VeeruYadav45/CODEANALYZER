# ─────────────────────────────────────────────────────────────────────────────
# analyzer.py
# Core analysis engine.  Intentionally decoupled from the CLI so it can be
# imported and called directly by a browser extension, agent loop, web API, etc.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import httpx
from openai import OpenAI, APIConnectionError

from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

# ── Ollama connection ─────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY  = "ollama"          # Ollama ignores this but openai SDK requires it
OLLAMA_MODEL    = "qwen2.5-coder:3b"

# ── Section headers the model is instructed to emit ───────────────────────────
SECTIONS = [
    "TIME COMPLEXITY",
    "SPACE COMPLEXITY",
    "EXPLANATION",
    "SUGGESTED IMPROVEMENTS",
]


# ── Public data structure returned to callers ─────────────────────────────────
class AnalysisResult:
    """
    Structured result from analyze_code().
    All fields are plain strings so they're easy to render in any context
    (CLI, JSON API, HTML, etc.).
    """
    def __init__(
        self,
        time_complexity: str,
        space_complexity: str,
        explanation: str,
        suggestions: str,
        raw_response: str,
    ) -> None:
        self.time_complexity  = time_complexity
        self.space_complexity = space_complexity
        self.explanation      = explanation
        self.suggestions      = suggestions
        self.raw_response     = raw_response   # useful for debugging / logging

    def to_dict(self) -> dict:
        """Serialise to a plain dict — handy for JSON APIs or agent tool responses."""
        return {
            "time_complexity":  self.time_complexity,
            "space_complexity": self.space_complexity,
            "explanation":      self.explanation,
            "suggestions":      self.suggestions,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_client() -> OpenAI:
    """Create an OpenAI client pointed at the local Ollama server."""
    return OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
    )


def _call_model(client: OpenAI, code: str) -> str:
    """
    Send the code to the model and return the raw text response.
    Raises APIConnectionError if Ollama is not reachable.
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(code=code)
    response = client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,   # low temperature → more deterministic/consistent output
    )
    return response.choices[0].message.content.strip()


def _parse_response(raw: str) -> dict[str, str]:
    """
    Parse the model's structured text response into a dict keyed by section name.
    Robust to minor formatting variations (extra whitespace, lowercase headers, etc.).
    """
    parsed: dict[str, str] = {s: "" for s in SECTIONS}

    # Build a map of "SECTION NAME" → where it starts in the raw text
    positions: list[tuple[int, str]] = []
    raw_upper = raw.upper()
    for section in SECTIONS:
        idx = raw_upper.find(section + ":")
        if idx != -1:
            positions.append((idx, section))

    # Sort by position so we can slice out each section's content
    positions.sort(key=lambda x: x[0])

    for i, (start_idx, section) in enumerate(positions):
        # Content starts after "SECTION NAME:\n"
        content_start = start_idx + len(section) + 1  # +1 for ":"
        # Content ends where the next section begins (or at end of string)
        if i + 1 < len(positions):
            content_end = positions[i + 1][0]
        else:
            content_end = len(raw)
        parsed[section] = raw[content_start:content_end].strip()

    return parsed


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_code(code: str) -> AnalysisResult:
    """
    Analyze the given source code for time/space complexity.

    Args:
        code: Source code string to analyze.

    Returns:
        AnalysisResult with structured fields.

    Raises:
        ValueError:          If code is empty or whitespace-only.
        APIConnectionError:  If Ollama is not running.
        RuntimeError:        If the model returns a malformed response.
    """
    # ── Validate input ────────────────────────────────────────────────────────
    if not code or not code.strip():
        raise ValueError("Code input is empty or contains only whitespace.")

    # ── Call the model ────────────────────────────────────────────────────────
    client  = _build_client()
    raw     = _call_model(client, code)

    # ── Parse sections ────────────────────────────────────────────────────────
    sections = _parse_response(raw)

    # Warn (but don't crash) if any expected section is missing
    missing = [s for s in SECTIONS if not sections.get(s)]
    if missing:
        # Fall back to showing the raw response in the missing field(s)
        for s in missing:
            sections[s] = "(Model did not provide this section — see raw output)"

    return AnalysisResult(
        time_complexity  = sections["TIME COMPLEXITY"],
        space_complexity = sections["SPACE COMPLEXITY"],
        explanation      = sections["EXPLANATION"],
        suggestions      = sections["SUGGESTED IMPROVEMENTS"],
        raw_response     = raw,
    )
