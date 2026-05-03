"""Entrypoint for the invoice booking agent test harness.

Runs 14 behavioural categories with 5 variants each across
multiple rounds. Writes a structured Markdown report to runs/.

Usage:
    PROVIDER=openai OPENAI_API_KEY=sk-... python src/app/main.py
"""

from __future__ import annotations

from dotenv import load_dotenv

from app.harness.config import DEFAULT_NUM_ROUNDS
from app.harness.logging_capture import configure_capture_logging
from app.harness.report import write_report
from app.harness.runner import run_all_rounds
from app.harness.scenarios import CATEGORIES
from app.services.observability import configure_observability


def main() -> None:
    """Run the harness and write a report."""
    load_dotenv()
    configure_observability()
    handler = configure_capture_logging()
    num_rounds = DEFAULT_NUM_ROUNDS

    total_variants = sum(len(c.variants) for c in CATEGORIES)
    print(
        f"Running {len(CATEGORIES)} categories "
        f"({total_variants} variants per round) "
        f"across {num_rounds} rounds..."
    )

    results = run_all_rounds(handler, num_rounds=num_rounds)
    report_path = write_report(results, num_rounds=num_rounds)

    total_pass = sum(1 for r in results if r.status == r.category.expected_status)
    print(f"Report written to: {report_path}")
    print(f"Pass: {total_pass} / {len(results)}")


if __name__ == "__main__":
    main()
