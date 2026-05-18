"""Fitness Function: core/verification_rules.py contains pure functions only.

Verifies that the verification-rules module has no I/O dependencies.
The Constraint Hierarchy lesson from best_practises.md (Rule #8)
states that verification belongs in pure Python, not in the LLM
and not in modules that touch external state.

A "pure" module here means: no logging, no print, no file I/O,
no LLM client imports, no HTTP, no database access.
"""

from __future__ import annotations

from pathlib import Path

from tests.architecture._import_inspector import parse_imports

_FORBIDDEN_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "logging",
        "sys",
        "os",
        "pathlib",
        "json",
        "pickle",
        "csv",
        "http",
        "urllib",
        "requests",
        "httpx",
        "sqlite3",
        "sqlalchemy",
        "openai",
        "anthropic",
    }
)

_FORBIDDEN_APP_PREFIXES: frozenset[str] = frozenset(
    {
        "app.services",
        "app.pipeline",
        "app.harness",
        "app.prompts",
        "app.intake",
        "app.approval",
        "app.booking",
    }
)


def test_verification_rules_module_is_pure() -> None:
    """core/verification_rules.py imports nothing that implies I/O or coupling."""
    project_root = Path(__file__).resolve().parents[2]
    rules_path = project_root / "src" / "app" / "core" / "verification_rules.py"

    assert rules_path.exists(), (
        f"core/verification_rules.py not found at {rules_path}. Did the file move?"
    )

    records = parse_imports(rules_path)
    violations: list[str] = []

    for record in records:
        target = record.imported_module
        if target is None:
            for name in record.imported_names:
                top_level = name.split(".")[0]
                if top_level in _FORBIDDEN_TOP_LEVEL:
                    violations.append(
                        f"line {record.line_number}: "
                        f"import {name} is forbidden in core/verification_rules.py"
                    )
            continue

        top_level = target.split(".")[0]
        if top_level in _FORBIDDEN_TOP_LEVEL:
            violations.append(
                f"line {record.line_number}: "
                f"from {target} import ... is forbidden "
                f"({top_level} implies I/O or external state)"
            )
            continue

        for forbidden_prefix in _FORBIDDEN_APP_PREFIXES:
            if target.startswith(forbidden_prefix):
                violations.append(
                    f"line {record.line_number}: "
                    f"from {target} import ... is forbidden "
                    f"(core/verification_rules.py must not depend on {forbidden_prefix})"
                )
                break

    assert not violations, (
        "core/verification_rules.py is not pure. Forbidden imports detected:\n" + "\n".join(violations)
    )
