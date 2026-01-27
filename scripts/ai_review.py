from google import genai
import sys

client = genai.Client()

def review_code(diff_text):
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

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

def parse_severity(review_text):
    """Extract severity level from the review output."""
    for line in review_text.strip().split("\n"):
        if line.strip().startswith("SEVERITY_SUMMARY:"):
            level = line.split(":", 1)[1].strip().upper()
            if level in ("CRITICAL", "WARNING", "GOOD"):
                return level
    return "WARNING"  # Default to WARNING if parsing fails



if __name__ == "__main__":
    if len(sys.argv) > 1:
        diff_file = sys.argv[1]
        with open(diff_file, "r", encoding="utf-8") as f:
            diff_content = f.read()
    else:
        diff_content = sys.stdin.read()

    review = review_code(diff_content)
    severity = parse_severity(review)
    print(review)

    with open("severity.txt", "w") as f:
        f.write(severity)
