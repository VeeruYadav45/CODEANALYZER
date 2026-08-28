# ─────────────────────────────────────────────────────────────────────────────
# cache.py
# File-level result cache for the Code Complexity Analyzer.
# Results are keyed by the MD5 hash of each file's content, so a file is only
# re-analyzed when its source code actually changes.
#
# Cache is stored as a hidden JSON file (.complexity_cache.json) inside the
# scanned directory, so each project keeps its own cache.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from analyzer import AnalysisResult

CACHE_FILENAME = ".complexity_cache.json"


# ── Hashing ───────────────────────────────────────────────────────────────────

def get_file_hash(path: Path) -> str:
    """Return the MD5 hex-digest of a file's byte content."""
    return hashlib.md5(path.read_bytes()).hexdigest()


# ── Persistence ───────────────────────────────────────────────────────────────

def load_cache(dir_path: Path) -> dict:
    """
    Load the cache dict from <dir_path>/.complexity_cache.json.
    Returns an empty dict if the file doesn't exist or is corrupt.
    """
    cache_file = dir_path / CACHE_FILENAME
    if not cache_file.exists():
        return {}
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(dir_path: Path, cache: dict) -> None:
    """
    Persist the cache dict to <dir_path>/.complexity_cache.json.
    Silently ignores write errors (cache is best-effort).
    """
    cache_file = dir_path / CACHE_FILENAME
    try:
        cache_file.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


# ── Lookup / Store ────────────────────────────────────────────────────────────

def get_cached_result(cache: dict, file_hash: str) -> "AnalysisResult | None":
    """
    Return a reconstructed AnalysisResult from the cache if available,
    or None if this hash has never been analyzed before.
    """
    entry = cache.get(file_hash)
    if not entry:
        return None

    # Import here to avoid circular imports at module level
    from analyzer import AnalysisResult
    return AnalysisResult(
        time_complexity  = entry.get("time_complexity",  ""),
        space_complexity = entry.get("space_complexity", ""),
        explanation      = entry.get("explanation",      ""),
        suggestions      = entry.get("suggestions",      ""),
        raw_response     = entry.get("raw_response",     ""),
    )


def store_result(cache: dict, file_hash: str, result: "AnalysisResult") -> None:
    """
    Save an AnalysisResult into the in-memory cache dict under the given hash.
    Call save_cache() afterwards to persist to disk.
    """
    cache[file_hash] = {
        "time_complexity":  result.time_complexity,
        "space_complexity": result.space_complexity,
        "explanation":      result.explanation,
        "suggestions":      result.suggestions,
        "raw_response":     result.raw_response,
    }
