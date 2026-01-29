import os
import json
import time
from pathlib import Path
from google import genai

# Create a Gemini client, passing in the API key from environment variables
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def get_python_files(repo_path: str) -> list[str]:
    """Return a list of Python files in the repo, excluding common ignored folders."""
    python_files: list[str] = []

    for path in Path(repo_path).rglob("*.py"):
        # Skip virtual environments and common directories to ignore
        if any(part in path.parts for part in ["venv", ".venv", "node_modules", "__pycache__", ".git"]):
            continue
        python_files.append(str(path))

    return python_files


def read_file_content(file_path: str) -> str:
    """Read and return the content of a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


def analyze_code_with_gemini(code_content: str, file_path: str) -> dict:
    """Send code to Gemini for dead code analysis."""
    prompt = f"""Analyze the following Python code and identify any dead code.

Look for:
1. Unused functions (defined but never called within this file)
2. Dead imports (imported but never used)
3. Unreachable code (code after return statements, etc.)

For each finding, estimate the cleanup time based on:
- Simple fixes (removing an import, deleting a small function): ~2-5 minutes
- Medium fixes (removing a function with dependencies to check): ~10-15 minutes
- Complex fixes (removing code that might have external callers): ~30+ minutes

File: {file_path}

Code:

{code_content}


Respond in JSON format with this structure:
{{
  "findings": [
    {{
      "type": "unused_function" | "dead_import" | "unreachable_code",
      "name": "name of the function/import/code",
      "line": line_number,
      "description": "brief description of why this is dead code",
      "estimated_minutes": number,
      "reasoning": "short explanation of estimate"
    }}
  ]
}}

If no dead code is found, return: {{"findings": []}}
Only return the JSON, no additional text."""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        response_text = response.text.strip()

        # Handle ```json fenced blocks if Gemini returns them
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            response_text = response_text.rsplit("```", 1)[0].strip()

        return json.loads(response_text)
    except Exception as e:
        return {"error": str(e), "findings": []}


def format_findings_as_markdown(all_findings: list[dict]) -> str:
    """Format all findings as markdown with time estimates."""
    if not all_findings:
        return "No dead code detected in this scan."

    total_minutes = sum(int(f.get("estimated_minutes") or 0) for f in all_findings)

    markdown = "## Stale Code Report\n\n"
    markdown += f"**{len(all_findings)}** issues found ~**{total_minutes} minutes** total cleanup\n\n"

    for f in all_findings:
        name = f.get("name", "unknown")
        mins = f.get("estimated_minutes", "?")
        desc = f.get("description", "")
        file_path = f.get("file", "")
        line = f.get("line", "?")
        reasoning = f.get("reasoning", "")

        markdown += f"- **{name}** (~{mins} min) - {desc}\n"
        markdown += f"  - `{file_path}:{line}`\n"
        if reasoning:
            markdown += f"  - Estimate reasoning: {reasoning}\n"

    return markdown


def main() -> list[dict]:
    """Main function to scan repository and report findings."""
    repo_path = os.environ.get("GITHUB_WORKSPACE", ".")

    print(f"Scanning repository: {repo_path}")

    python_files = get_python_files(repo_path)
    print(f"Found {len(python_files)} Python files")

    all_findings: list[dict] = []

    for file_path in python_files:
        print(f"Analyzing: {file_path}")
        content = read_file_content(file_path)

        if content.startswith("Error reading file:"):
            print("  Skipping due to read error")
            continue

        result = analyze_code_with_gemini(content, file_path)

        if "error" in result:
            print(f"  Analysis error: {result['error']}")
            continue

        for finding in result.get("findings", []):
            finding["file"] = file_path
            all_findings.append(finding)

        # Optional: light rate limit to reduce 429s
        time.sleep(0.2)

    markdown_report = format_findings_as_markdown(all_findings)

    print("\n" + "=" * 50)
    print(markdown_report)

    with open("stale_code_report.md", "w", encoding="utf-8") as f:
        f.write(markdown_report)

    print("\nReport saved to stale_code_report.md")
    return all_findings


if __name__ == "__main__":
    findings = main()
    raise SystemExit(1 if findings else 0)
