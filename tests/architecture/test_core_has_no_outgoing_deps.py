"""Fitness Function: core/ is the Shared Kernel and must not depend
on any other layer.

Verifies the architectural rule that the Shared Kernel
(`app.core.*`) imports only from itself and from the Python
standard library. Any import from `app.services`, `app.intake`,
`app.verification`, `app.approval`, `app.booking`,
`app.harness`, `app.prompts`, or `app.pipeline` is a layering
violation that this test catches.
"""

from __future__ import annotations

from tests.architecture._import_inspector import all_app_imports

_FORBIDDEN_PREFIXES_FOR_CORE: frozenset[str] = frozenset(
    {
        "app.services",
        "app.intake",
        "app.verification",
        "app.approval",
        "app.booking",
        "app.harness",
        "app.prompts",
        "app.pipeline",
    }
)


def test_core_layer_has_no_outgoing_dependencies() -> None:
    """core/ may not import from any other app layer."""
    violations: list[str] = []

    for record in all_app_imports():
        if not record.source_module.startswith("app.core"):
            continue
        if record.imported_module is None:
            continue

        for forbidden in _FORBIDDEN_PREFIXES_FOR_CORE:
            if record.imported_module.startswith(forbidden):
                violations.append(
                    f"{record.source_module}:{record.line_number} "
                    f"imports from {record.imported_module} "
                    f"(forbidden: core/ may not depend on {forbidden})"
                )
                break

    assert not violations, "Layering violation: core/ has outgoing dependencies.\n" + "\n".join(
        violations
    )
