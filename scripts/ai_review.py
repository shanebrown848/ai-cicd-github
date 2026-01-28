import os
import sys
import time
from google import genai

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "4"))
RETRY_SLEEP_SECONDS = int(os.environ.get("GEMINI_RETRY_SLEEP", "25"))


def _is_rate_limit_error(err: Exception) -> bool:
    msg = str(err)
    return ("429" in msg) or ("RESOURCE_EXHAUSTED" in msg) or ("rate limit" in msg.lower())


def review_code(client: genai.Client, diff_text: str) -> str:
    prompt = f"""You are an expert code reviewer. Review the following code diff and provide feedback.

Focus on:
1. Security vulnerabilities
2. Bug risks
3. Performance issues
4. Best practice violations

For each issue found, provide:
- Severity: HIGH / MEDIUM / LOW
- Description of the issue
- Suggested fix

If the code looks good, say so.

IMPORTANT: At the very end of your review, add a severity summary line in exactly this format:
SEVERITY_SUMMARY: <level>
Where <level> is one of: CRITICAL, WARNING, GOOD

Use CRITICAL if any HIGH severity issues exist.
Use WARNING if only MEDIUM or LOW severity issues exist.
Use GOOD if no issues found.

Code diff to review:

{diff_text}

Provide your review in a clear, structured format, ending with the SEVERITY_SUMMARY line.
"""

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as e:
            last_err = e
            if _is_rate_limit_error(e):
                time.sleep(RETRY_SLEEP_SECONDS)
                continue
            raise

    # Graceful fallback instead of crashing the workflow
    return (
        "AI review skipped due to Gemini quota/rate limit.\n\n"
        "SEVERITY_SUMMARY: WARNING"
    )


def parse_severity(review_text: str) -> str:
    for line in review_text.strip().split("\n"):
        if line.strip().startswith("SEVERITY_SUMMARY:"):
            level = line.split(":", 1)[1].strip().upper()
            if level in ("CRITICAL", "WARNING", "GOOD"):
                return level
    return "WARNING"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        diff_file = sys.argv[1]
        with open(diff_file, "r", encoding="utf-8") as f:
            diff_content = f.read()
    else:
        diff_content = sys.stdin.read()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Don’t hard-fail CI if secret isn't present (fork PRs, etc.)
        review = "AI review skipped (missing GEMINI_API_KEY).\n\nSEVERITY_SUMMARY: WARNING"
        print(review)
        with open("severity.txt", "w", encoding="utf-8") as f:
            f.write("WARNING")
        raise SystemExit(0)

    client = genai.Client(api_key=api_key)

    review = review_code(client, diff_content)
    severity = parse_severity(review)

    print(review)

    with open("severity.txt", "w", encoding="utf-8") as f:
        f.write(severity)
