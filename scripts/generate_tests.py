import ast
import os
import re
import sys
import time
from pathlib import Path
from google import genai

# ---- Tuning knobs (safe defaults for free tier) ----
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Free tier often behaves like ~5 requests/minute -> keep under that.
REQUEST_SLEEP_SECONDS = int(os.environ.get("GEMINI_REQUEST_SLEEP", "15"))

# Retry behavior for 429s / transient issues
MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "6"))
RETRY_SLEEP_SECONDS = int(os.environ.get("GEMINI_RETRY_SLEEP", "25"))

# Skip risky stuff (adjust as needed)
SKIP_FILES = {"dangerous.py"}
SKIP_FUNCTION_NAMES = {"run_command"}  # add more if needed


def extract_functions(file_path: str):
    """Parse a Python file and extract function definitions."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_name = node.name
            args = [arg.arg for arg in node.args.args]
            docstring = ast.get_docstring(node) or ""
            func_source = ast.get_source_segment(source, node) or ""

            functions.append(
                {
                    "name": func_name,
                    "args": args,
                    "docstring": docstring,
                    "source": func_source,
                }
            )

    return functions


def _is_rate_limit_error(err: Exception) -> bool:
    msg = str(err)
    return ("429" in msg) or ("RESOURCE_EXHAUSTED" in msg) or ("rate limit" in msg.lower())


def generate_tests_for_function(client: genai.Client, func_info: dict) -> str:
    """Use Gemini to generate pytest tests for a function, with retry + pacing."""
    prompt = f"""Generate pytest tests for this Python function.

Function name: {func_info['name']}
Arguments: {', '.join(func_info['args'])}
Docstring: {func_info['docstring']}

Source code:

{func_info['source']}

Requirements:
1. Generate 3-5 meaningful test cases
2. Include edge cases (empty inputs, None values, etc.)
3. Use descriptive test function names
4. Include assertions that actually test behavior
5. Do NOT generate placeholder tests like assert True
6. Keep tests deterministic (no time/network randomness)

Return ONLY the Python test code, no explanations.
"""

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )

            # Pacing to avoid hitting free-tier RPM
            time.sleep(REQUEST_SLEEP_SECONDS)

            text = (response.text or "").strip()
            return text

        except Exception as e:
            last_err = e
            if _is_rate_limit_error(e):
                print(
                    f"  Rate limit hit (attempt {attempt}/{MAX_RETRIES}). "
                    f"Sleeping {RETRY_SLEEP_SECONDS}s then retrying..."
                )
                time.sleep(RETRY_SLEEP_SECONDS)
                continue

            # Non-rate-limit error -> bubble up
            raise

    raise RuntimeError(f"Gemini error: retries exhausted. Last error: {last_err}")


def _safe_test_filename(src_path: str) -> str:
    """
    Convert 'foo/bar.py' -> 'tests/test_bar_generated.py'
    Keeps test files small and prevents clobbering one giant file.
    """
    base = Path(src_path).name.replace(".py", "")
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", base)
    return f"tests/test_{base}_generated.py"


def main():
    """Main function to generate tests for changed files."""
    changed_files = sys.argv[1:] if len(sys.argv) > 1 else []

    if not changed_files:
        print("No Python files provided for test generation")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)

    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue
        if file_path.startswith("tests/"):
            continue

        if Path(file_path).name in SKIP_FILES:
            print(f"Skipping file (in SKIP_FILES): {file_path}")
            continue

        print(f"Analyzing: {file_path}")
        functions = extract_functions(file_path)

        # Filter functions
        functions = [
            f for f in functions
            if not f["name"].startswith("_")
            and f["name"] not in SKIP_FUNCTION_NAMES
        ]

        if not functions:
            print("  No eligible functions found")
            continue

        all_tests = []
        for func in functions:
            print(f"  Generating tests for: {func['name']}")
            tests = generate_tests_for_function(client, func)
            all_tests.append(f"# Tests for {func['name']} from {file_path}\n{tests}")

        if all_tests:
            os.makedirs("tests", exist_ok=True)
            test_file = _safe_test_filename(file_path)

            with open(test_file, "w", encoding="utf-8") as f:
                f.write("import pytest\n\n")
                f.write("\n\n".join(all_tests))
                f.write("\n")

            print(f"Generated tests written to: {test_file}")


if __name__ == "__main__":
    main()
