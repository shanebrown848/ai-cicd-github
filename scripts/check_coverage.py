import json
import subprocess
import sys
from pathlib import Path

COVERAGE_FILE = Path("coverage.json")


def get_coverage_percentage() -> float:
    """Run pytest with coverage and return total percent covered."""
    # Force the json file name so we know exactly what to read
    # Use --cov=. to cover all Python files in the repo root (flat layout)
    # Exclude tests/ and scripts/ directories from coverage
    cmd = [
        "pytest",
        "--cov=.",
        "--cov-report=json:coverage.json",
        "--ignore=tests",
        "--ignore=scripts",
        "-q"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # If pytest failed, show why and treat as 0 coverage (forces generation)
    if result.returncode != 0:
        print("Pytest failed while measuring coverage.")
        if result.stdout:
            print("pytest stdout:\n" + result.stdout)
        if result.stderr:
            print("pytest stderr:\n" + result.stderr)
        return 0.0

    if not COVERAGE_FILE.exists():
        print("Coverage file was not created:", str(COVERAGE_FILE))
        if result.stdout:
            print("pytest stdout:\n" + result.stdout)
        if result.stderr:
            print("pytest stderr:\n" + result.stderr)
        return 0.0

    try:
        data = json.loads(COVERAGE_FILE.read_text(encoding="utf-8"))
        return float(data["totals"]["percent_covered"])
    except Exception as e:
        print("Failed to parse coverage JSON:", e)
        if result.stdout:
            print("pytest stdout:\n" + result.stdout)
        if result.stderr:
            print("pytest stderr:\n" + result.stderr)
        return 0.0


def main() -> None:
    """Check coverage and exit with appropriate code."""
    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 80.0

    coverage = get_coverage_percentage()
    print(f"Current coverage: {coverage:.1f}%")
    print(f"Threshold: {threshold:.1f}%")

    if coverage >= threshold:
        print(f"Coverage is sufficient ({coverage:.1f}% >= {threshold:.1f}%)")
        print("Skipping test generation.")
        raise SystemExit(0)

    print(f"Coverage below threshold ({coverage:.1f}% < {threshold:.1f}%)")
    print("Test generation needed.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
