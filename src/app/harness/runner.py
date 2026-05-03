"""Parallel execution engine for the test harness."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.harness.config import MAX_PARALLEL_SCENARIOS, ROUND_COOLDOWN_SECONDS
from app.harness.wiring import build_coordinator_for_variant

if TYPE_CHECKING:
    from app.core.statuses import AgentStatus
    from app.harness.logging_capture import ThreadIsolatedBufferHandler
    from app.harness.scenarios import Category, Variant


@dataclass(frozen=True)
class RunResult:
    """The result of running one (category, variant) once."""

    category: Category
    variant: Variant
    round_number: int
    status: AgentStatus
    message: str
    duration_seconds: float
    trace: tuple[str, ...]


def run_one(
    category: Category,
    variant: Variant,
    round_number: int,
    handler: ThreadIsolatedBufferHandler,
) -> RunResult:
    """Execute one variant once and return a result record."""
    thread_id = handler.start_capture()
    coordinator = build_coordinator_for_variant(category, variant)
    task = category.task_template.format(invoice_id=variant.invoice_id)
    started = time.monotonic()
    result = coordinator.run(variant.invoice_id, task)
    elapsed = time.monotonic() - started
    trace_lines = handler.pop_capture(thread_id)
    return RunResult(
        category=category,
        variant=variant,
        round_number=round_number,
        status=result.status,
        message=result.message,
        duration_seconds=elapsed,
        trace=tuple(trace_lines),
    )


def run_round(
    round_number: int,
    handler: ThreadIsolatedBufferHandler,
) -> list[RunResult]:
    """Run all variants of all categories in parallel for one round."""
    from app.harness.scenarios import CATEGORIES

    pairs = [(category, variant) for category in CATEGORIES for variant in category.variants]
    max_workers = min(MAX_PARALLEL_SCENARIOS, len(pairs))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_one, category, variant, round_number, handler)
            for category, variant in pairs
        ]
        return [future.result() for future in as_completed(futures)]


def run_all_rounds(
    handler: ThreadIsolatedBufferHandler,
    num_rounds: int = 5,
) -> list[RunResult]:
    """Run all variants for all rounds.

    Rounds are sequential; variants within a round are parallel,
    capped at MAX_PARALLEL_SCENARIOS to stay within API rate limits.
    """
    all_results: list[RunResult] = []
    for round_number in range(1, num_rounds + 1):
        round_results = run_round(round_number, handler)
        all_results.extend(round_results)
        if round_number < num_rounds:
            time.sleep(ROUND_COOLDOWN_SECONDS)
    return all_results
