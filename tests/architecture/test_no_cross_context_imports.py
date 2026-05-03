"""Fitness Function: bounded contexts must not import from each other.

Verifies the architectural rule that the four bounded contexts
(intake, verification, approval, booking) are independent. The
only allowed shared dependencies are core/ and services/.

Cross-context imports would couple the workflow phases and
defeat the purpose of bounded context modeling. The pipeline.py
top-level orchestrator is the only module allowed to import
from multiple bounded contexts.
"""

from __future__ import annotations

from tests.architecture._import_inspector import all_app_imports

_BOUNDED_CONTEXTS: frozenset[str] = frozenset(
    {
        "app.intake",
        "app.verification",
        "app.approval",
        "app.booking",
    }
)


def _which_context(module: str) -> str | None:
    """Return the bounded context a module belongs to, or None."""
    for context in _BOUNDED_CONTEXTS:
        if module == context or module.startswith(context + "."):
            return context
    return None


def test_bounded_contexts_do_not_import_from_each_other() -> None:
    """Each bounded context is independent of every other."""
    violations: list[str] = []

    for record in all_app_imports():
        source_context = _which_context(record.source_module)
        if source_context is None:
            continue
        if record.imported_module is None:
            continue

        target_context = _which_context(record.imported_module)
        if target_context is None:
            continue
        if target_context == source_context:
            continue

        violations.append(
            f"{record.source_module}:{record.line_number} "
            f"imports from {record.imported_module} "
            f"(forbidden: {source_context} may not depend on {target_context})"
        )

    assert not violations, "Layering violation: cross-context imports detected.\n" + "\n".join(
        violations
    )
