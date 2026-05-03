"""Markdown report generation for the test harness."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.harness.scenarios import CATEGORIES

if TYPE_CHECKING:
    from app.harness.runner import RunResult


def write_report(
    results: list[RunResult],
    num_rounds: int,
) -> Path:
    """Write a structured Markdown report and return the path."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    path = runs_dir / f"scenario_run_{timestamp}.md"

    by_category: dict[str, list[RunResult]] = {}
    for r in results:
        by_category.setdefault(r.category.category_id, []).append(r)
    sorted_category_ids = sorted(by_category.keys(), key=int)

    lines: list[str] = []

    # Header
    total_runs = len(results)
    total_pass = sum(1 for r in results if r.status == r.category.expected_status)
    total_fail = total_runs - total_pass
    num_categories = len(CATEGORIES)
    num_variants_per_round = sum(len(c.variants) for c in CATEGORIES)

    lines.append(f"# Scenario Run {timestamp}")
    lines.append("")
    lines.append(f"Categories: {num_categories}")
    lines.append(f"Variants per round: {num_variants_per_round}")
    lines.append(f"Rounds: {num_rounds}")
    lines.append(f"Total runs: {total_runs}")
    lines.append("")
    lines.append(f"Pass: {total_pass} / {total_runs}")
    lines.append(f"Fail: {total_fail} / {total_runs}")
    lines.append("")

    # Summary table: one row per category, aggregate pass rate
    lines.append("## Pass rate per category")
    lines.append("")
    lines.append("| Category | Description | Expected | Variants | Runs | Pass rate |")
    lines.append("|---|---|---|---|---|---|")
    for cat_id in sorted_category_ids:
        cat_results = by_category[cat_id]
        category = cat_results[0].category
        variants_count = len(category.variants)
        runs_per_category = variants_count * num_rounds
        passes = sum(1 for r in cat_results if r.status == category.expected_status)
        lines.append(
            f"| Cat {cat_id} | {category.name} | "
            f"`{category.expected_status.value}` | "
            f"{variants_count} | {runs_per_category} | "
            f"{passes}/{runs_per_category} |"
        )
    lines.append("")

    # Failures section
    failures = [r for r in results if r.status != r.category.expected_status]
    if failures:
        lines.append("## Failures (unexpected status)")
        lines.append("")
        lines.append("| Category | Variant | Round | Expected | Actual |")
        lines.append("|---|---|---|---|---|")
        for r in failures:
            lines.append(
                f"| Cat {r.category.category_id} ({r.category.name}) | "
                f"{r.variant.variant_id} ({r.variant.description}) | "
                f"R{r.round_number} | "
                f"`{r.category.expected_status.value}` | "
                f"`{r.status.value}` |"
            )
        lines.append("")
    else:
        lines.append("## Failures")
        lines.append("")
        lines.append(
            "No failures across any round. All variants of all "
            "categories produced their expected status."
        )
        lines.append("")

    # Detailed traces: nested Category > Variant > Round
    lines.append("## Detailed traces")
    lines.append("")
    lines.append(
        "Full Coordinator iteration log for each run, grouped by "
        "category, then variant, then round."
    )
    lines.append("")
    for cat_id in sorted_category_ids:
        cat_results = by_category[cat_id]
        category = cat_results[0].category
        lines.append(f"### Category {cat_id}: {category.name}")
        lines.append("")
        lines.append(f"Expected status: `{category.expected_status.value}`")
        lines.append("")

        by_variant: dict[str, list[RunResult]] = {}
        for r in cat_results:
            by_variant.setdefault(r.variant.variant_id, []).append(r)
        sorted_variant_ids = sorted(by_variant.keys())

        for var_id in sorted_variant_ids:
            var_results = by_variant[var_id]
            var_results.sort(key=lambda r: r.round_number)
            variant = var_results[0].variant
            lines.append(f"#### Variant {var_id}: {variant.description}")
            lines.append("")
            lines.append(f"Invoice ID: `{variant.invoice_id}`")
            lines.append("")
            for r in var_results:
                mark = "OK" if r.status == category.expected_status else "FAIL"
                lines.append(f"##### Round {r.round_number} [{mark}, {r.duration_seconds:.2f}s]")
                lines.append("")
                lines.append(f"Status: `{r.status.value}`")
                lines.append("")
                lines.append("```")
                if r.trace:
                    lines.extend(r.trace)
                else:
                    lines.append("(no trace captured)")
                lines.append(f"Status : {r.status.value}")
                lines.append(f"Message: {r.message}")
                lines.append("```")
                lines.append("")

    # Timing per category
    lines.append("## Timing per category")
    lines.append("")
    lines.append("| Category | Mean (s) | Min | Max |")
    lines.append("|---|---|---|---|")
    for cat_id in sorted_category_ids:
        cat_results = by_category[cat_id]
        durations = [r.duration_seconds for r in cat_results]
        mean_d = sum(durations) / len(durations)
        lines.append(
            f"| Cat {cat_id} | {mean_d:.2f} | {min(durations):.2f} | {max(durations):.2f} |"
        )
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
