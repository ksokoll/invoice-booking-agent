# ADR-007: Architecture Fitness Functions as Executable Tests

Status: Accepted
Date: 2026-04-08
Deciders: Kevin Sokoll

## Context

By Round 7.0 the codebase had a clean Bounded Context structure
(see ADR-002) with strict layering rules:

- `core/` has no outgoing dependencies
- `services/` depends only on `core/`
- Bounded contexts depend only on `core/` and `services/`
- Contexts do not import from each other
- `verification/rules.py` is pure (no I/O, no logging, no LLM)

These rules existed only as prose in the CLAUDE.md files and as
discipline in the author's head. There was no automated
enforcement. A future change could violate any rule and nothing
would catch it until a reviewer happened to notice.

The question: how to make architectural constraints survive
future changes, including changes made by people who did not
write the rules?

## Decision

Add three architecture tests under `tests/architecture/`, each
verifying one structural property by parsing Python imports with
the standard library `ast` module:

1. `test_core_has_no_outgoing_deps.py`: `core/` may not import
   from any other layer
2. `test_no_cross_context_imports.py`: bounded contexts may not
   import from each other
3. `test_verification_rules_are_pure.py`: `verification/rules.py`
   may not import I/O modules or other layers

A shared helper `_import_inspector.py` parses every module under
`src/app/` and extracts import records via `ast`. Each test
asserts a specific constraint over those records.

## Rationale

- Direct application of `architecture.md` Rule #4: "Treat Fitness
  Functions as first-class architecture artifacts. Any automated
  check that verifies an architectural characteristic is a
  Fitness Function."
- The tests run as part of the normal test suite. There is no
  separate "architecture lint" step to remember to run.
- Standard library `ast` parsing has zero third-party
  dependencies. The tests cannot break because of an upstream
  library version bump.
- Failure messages are precise. Each violation lists the source
  file, line number, target module, and the rule that was
  violated. A new contributor sees exactly what needs to change.

## Alternatives Considered

Two alternatives were considered:

1. Use a third-party tool like `import-linter` or `pydeps`. Both
   would work, but they add a dependency for roughly 50 lines of
   testing infrastructure. Rejected because the standard library
   `ast` module is sufficient and the self-contained approach has
   fewer moving parts.
2. Rely on code review to catch violations. This works until it
   doesn't, and the failure is invisible at the moment of
   breakage. Rejected because automated enforcement is strictly
   better than discipline for anything a machine can check.

## Consequences

Positive:
- Architectural rules are enforced automatically in CI
- A failed architecture test points to the exact line that
  violates the rule
- The tests are themselves documentation of the architectural
  constraints, in executable form

Negative:
- New architectural rules require new tests. The tests are not
  generic; each one is specific to one constraint.
- Tests inspect imports at the source-file level. Runtime dynamic
  imports (e.g. `importlib.import_module(...)`) are not caught.
  The codebase has none of these, but the blind spot exists.

Neutral:
- The `_import_inspector.py` helper is private to the architecture
  test package and is not used by any other tests
- Adding a fourth fitness function in the future requires creating
  one new file, not modifying any existing test
