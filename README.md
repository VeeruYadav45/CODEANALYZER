# Code Complexity Analyzer

A CLI tool that uses a **local Ollama LLM** to analyze any piece of code and report:

- ⏱ **Time Complexity** (Big O notation)
- 💾 **Space Complexity** (Big O notation)
- 📖 **Plain-English Explanation** of why the code has those complexities
- 💡 **Actionable Improvement Suggestions** with example code

---

## Prerequisites

1. **Python 3.10+**
2. **[Ollama](https://ollama.com)** installed and running locally
3. The `qwen2.5-coder:3b` model pulled

---

## Installation

### 1. Install Python dependencies

```bash
pip install openai
```

### 2. Install & start Ollama

```bash
# Install from https://ollama.com, then:
ollama serve              # start the Ollama server
ollama pull qwen2.5-coder:3b   # pull the model (one-time)
```

---

## Usage

### Analyze a file

```bash
python main.py --file path/to/your_code.py
```

### Analyze a raw code snippet

```bash
python main.py --code "for i in range(n):
    for j in range(n):
        print(i, j)"
```

### Short flags

```bash
python main.py -f my_script.py
python main.py -c "def foo(n): return [i for i in range(n)]"
```

---

## Example Output

```
════════════════════════════════════════════════════════════
  🔍  CODE COMPLEXITY ANALYSIS
════════════════════════════════════════════════════════════

────────────────────────────────────────────────────────────
  ⏱  TIME COMPLEXITY
────────────────────────────────────────────────────────────
  O(n²)

────────────────────────────────────────────────────────────
  💾  SPACE COMPLEXITY
────────────────────────────────────────────────────────────
  O(1)

────────────────────────────────────────────────────────────
  📖  EXPLANATION
────────────────────────────────────────────────────────────
  The nested for-loops each iterate n times, resulting in n×n
  total operations → O(n²). No extra data structures are
  allocated beyond the loop variables → O(1) space.

────────────────────────────────────────────────────────────
  💡  SUGGESTED IMPROVEMENTS
────────────────────────────────────────────────────────────
  1. If you only need pairs, consider using itertools.product
     which is still O(n²) but expresses intent more clearly:

     import itertools
     for i, j in itertools.product(range(n), repeat=2):
         print(i, j)

  2. If the goal is matrix operations, use NumPy vectorized
     operations to avoid Python-level loops entirely.
```

---

## Project Structure

```
my_agent_project/
├── main.py        # CLI entry point (--file / --code flags)
├── analyzer.py    # Core analysis engine (importable independently)
├── prompts.py     # System prompt + user prompt template
└── README.md      # This file
```

## Extensibility

`analyzer.py` is intentionally decoupled from the CLI.
You can import and call it directly from any other context:

```python
from analyzer import analyze_code

result = analyze_code("for i in range(n): pass")
print(result.time_complexity)   # "O(n)"
print(result.to_dict())         # full dict for JSON/API use
```

This makes it easy to plug into:
- A **browser extension** (via a local HTTP wrapper)
- An **agent loop** (as a tool function)
- A **web API** (FastAPI/Flask route)
- A **VS Code extension**

---

## Error Handling

| Situation | Message shown |
|-----------|--------------|
| File not found | `❌ Error: File not found: 'path'` |
| Ollama not running | `❌ Could not connect to Ollama` + instructions |
| Empty code input | `❌ Error: No code provided` |
