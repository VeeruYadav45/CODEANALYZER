# ─────────────────────────────────────────────────────────────────────────────
# main.py
# CLI entry point for the Code Complexity Analyzer.
# Usage:
#   python main.py --file path/to/code.py
#   python main.py --code "for i in range(n): print(i)"
#   python main.py --dir  path/to/folder/
#
# Caching: results are stored in .complexity_cache.json inside the scanned
# directory.  Files are re-analyzed only when their content changes.
# ─────────────────────────────────────────────────────────────────────────────

import argparse
import sys
import datetime
from pathlib import Path

from openai import APIConnectionError

from analyzer import analyze_code, AnalysisResult
from cache import load_cache, save_cache, get_file_hash, get_cached_result, store_result

# ── ANSI colour helpers (degrade gracefully on terminals without colour) ───────
BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
RESET = "\033[0m"
DIM   = "\033[2m"


def _header(title: str) -> str:
    """Format a section header for terminal output."""
    bar = "─" * 60
    return f"\n{BOLD}{CYAN}{bar}\n  {title}\n{bar}{RESET}"


def _print_result(result: AnalysisResult) -> None:
    """Pretty-print the analysis result to stdout."""
    print()
    print(f"{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  🔍  CODE COMPLEXITY ANALYSIS{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")

    print(_header("⏱  TIME COMPLEXITY"))
    print(f"  {GREEN}{result.time_complexity}{RESET}")

    print(_header("💾  SPACE COMPLEXITY"))
    print(f"  {GREEN}{result.space_complexity}{RESET}")

    print(_header("📖  EXPLANATION"))
    # Word-wrap the explanation to 70 chars for readability
    for line in result.explanation.splitlines():
        print(f"  {line}")

    print(_header("💡  SUGGESTED IMPROVEMENTS"))
    for line in result.suggestions.splitlines():
        print(f"  {line}")

    print(f"\n{DIM}{'─'*60}{RESET}\n")


def _read_code_from_file(file_path: str) -> str:
    """
    Read source code from a file.
    Exits with a clear error message if the file doesn't exist.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"\n❌  Error: File not found: '{file_path}'", file=sys.stderr)
        print("    Please check the path and try again.", file=sys.stderr)
        sys.exit(1)
    if not path.is_file():
        print(f"\n❌  Error: '{file_path}' is not a file.", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


# File extensions considered as source code when scanning a directory
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".r",
}


def _build_markdown_report(
    dir_path: str,
    results: list[tuple[str, AnalysisResult | None]],
) -> str:
    """
    Build a full Markdown report string from the list of (filename, result) tuples.
    result is None if the file was skipped or errored.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    # ── Title ─────────────────────────────────────────────────────────────────
    lines.append(f"# 🔍 Code Complexity Report")
    lines.append(f"`{dir_path}`  ·  Generated {now}  ·  {len(results)} file(s) scanned")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Summary table ─────────────────────────────────────────────────────────
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| # | File | Time Complexity | Space Complexity |")
    lines.append("|---|------|----------------|-----------------|")
    for idx, (fname, result) in enumerate(results, 1):
        if result:
            tc = result.time_complexity or "—"
            sc = result.space_complexity or "—"
        else:
            tc = sc = "*(skipped)*"
        lines.append(f"| {idx} | `{fname}` | `{tc}` | `{sc}` |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Per-file detail ───────────────────────────────────────────────────────
    lines.append("## 📁 File-by-File Analysis")
    lines.append("")
    for idx, (fname, result) in enumerate(results, 1):
        lines.append(f"### [{idx}] `{fname}`")
        lines.append("")
        if result is None:
            lines.append("_Skipped (empty file or analysis error)._")
            lines.append("")
            continue

        lines.append(f"**⏱ Time Complexity:** `{result.time_complexity}`  ")
        lines.append(f"**💾 Space Complexity:** `{result.space_complexity}`")
        lines.append("")
        lines.append("**📖 Explanation:**")
        lines.append("")
        lines.append(result.explanation)
        lines.append("")
        lines.append("**💡 Suggested Improvements:**")
        lines.append("")
        lines.append(result.suggestions)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _analyze_directory(dir_path: str) -> None:
    """
    Walk a directory, find all code files, analyze each one,
    print results to terminal, and save a Markdown report.
    """
    root = Path(dir_path)
    if not root.exists():
        print(f"\n\u274c  Error: Directory not found: '{dir_path}'", file=sys.stderr)
        sys.exit(1)
    if not root.is_dir():
        print(f"\n\u274c  '{dir_path}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Collect all matching files (skip venv / node_modules / hidden dirs)
    skip_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git"}
    code_files = [
        p for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.suffix in CODE_EXTENSIONS
        and not any(part in skip_dirs for part in p.parts)
    ]

    if not code_files:
        print(f"\n\u26a0\ufe0f  No code files found in '{dir_path}'.")
        print(f"    Supported extensions: {', '.join(sorted(CODE_EXTENSIONS))}")
        return

    print(f"\n\U0001f4c2  Found {len(code_files)} code file(s) in '{dir_path}'")
    print(f"    Results will be saved to: report.md\n")

    # ── Load cache for this directory ────────────────────────────────────────
    cache = load_cache(root)
    cache_hits = 0

    # Collect results for the report
    collected: list[tuple[str, AnalysisResult | None]] = []

    for idx, file_path in enumerate(code_files, 1):
        rel   = file_path.relative_to(root)
        fname = str(rel)
        print(f"{BOLD}{'═'*60}{RESET}")
        print(f"{BOLD}  [{idx}/{len(code_files)}]  {rel}{RESET}")
        print(f"{BOLD}{'═'*60}{RESET}")

        code = file_path.read_text(encoding="utf-8", errors="replace")
        if not code.strip():
            print(f"  {DIM}(skipped — file is empty){RESET}\n")
            collected.append((fname, None))
            continue

        # ── Cache lookup ──────────────────────────────────────────────────────
        file_hash      = get_file_hash(file_path)
        cached_result  = get_cached_result(cache, file_hash)

        if cached_result:
            print(f"  {DIM}⚡ Loaded from cache (file unchanged){RESET}\n")
            _print_result(cached_result)
            collected.append((fname, cached_result))
            cache_hits += 1
            continue

        # ── Call the model ────────────────────────────────────────────────────
        print(f"  🤖 Analyzing...\n")
        try:
            result = analyze_code(code)
            _print_result(result)
            store_result(cache, file_hash, result)   # save to in-memory cache
            save_cache(root, cache)                  # persist to disk immediately
            collected.append((fname, result))
        except APIConnectionError:
            print("\n❌  Ollama is not running. Start it with: ollama serve", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"  ⚠️  Could not analyze {rel}: {e}\n")
            collected.append((fname, None))

    # ── Cache summary ─────────────────────────────────────────────────────────
    if cache_hits:
        print(f"  {DIM}💾  {cache_hits}/{len(code_files)} file(s) served from cache{RESET}")

    # ── Save report ───────────────────────────────────────────────────────────
    report_path = root / "report.md"
    report_md   = _build_markdown_report(dir_path, collected)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\n{'\u2550'*60}")
    print(f"  \u2705  Report saved to: {report_path}")
    print(f"{'\u2550'*60}\n")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="complexity-analyzer",
        description=(
            "Code Complexity Analyzer — powered by a local Ollama model.\n"
            "Analyzes source code for Big O time/space complexity and suggests improvements."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --file my_script.py\n"
            "  python main.py --dir  path/to/my_ds_folder/\n"
            '  python main.py --code "for i in range(n):\\n  for j in range(n):\\n    print(i,j)"\n'
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file", "-f",
        metavar="PATH",
        help="Path to a single source code file to analyze.",
    )
    source.add_argument(
        "--code", "-c",
        metavar="CODE",
        help="Raw code string to analyze (quote the whole thing).",
    )
    source.add_argument(
        "--dir", "-d",
        metavar="DIR",
        help="Path to a folder — analyzes every code file inside it.",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args   = parser.parse_args()

    # ── Directory mode ────────────────────────────────────────────────────────
    if args.dir:
        _analyze_directory(args.dir)
        return

    # ── Load code ─────────────────────────────────────────────────────────────
    if args.file:
        print(f"\n📂  Reading: {args.file}")
        code = _read_code_from_file(args.file)
    else:
        code = args.code

    # ── Empty-input guard ─────────────────────────────────────────────────────
    if not code or not code.strip():
        print("\n❌  Error: No code provided (input is empty or whitespace only).",
              file=sys.stderr)
        sys.exit(1)

    # ── Run analysis ──────────────────────────────────────────────────────────
    print("🤖  Analyzing with local Ollama model… (this may take a few seconds)\n")

    try:
        result = analyze_code(code)
        _print_result(result)

    except ValueError as e:
        # Empty/invalid input — shouldn't reach here given the check above,
        # but kept for safety when analyze_code() is called programmatically.
        print(f"\n❌  Input error: {e}", file=sys.stderr)
        sys.exit(1)

    except APIConnectionError:
        print("\n❌  Could not connect to Ollama.", file=sys.stderr)
        print("    Make sure Ollama is running:", file=sys.stderr)
        print("      ollama serve", file=sys.stderr)
        print("    And that the model is pulled:", file=sys.stderr)
        print("      ollama pull qwen2.5-coder:3b", file=sys.stderr)
        sys.exit(1)

    except RuntimeError as e:
        print(f"\n❌  Analysis failed: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"\n❌  Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
