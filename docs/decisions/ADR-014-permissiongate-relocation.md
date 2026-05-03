# ADR-014: PermissionGate Relocation to services/

Status: Accepted
Date: 2026-04-24
Deciders: Kevin Sokoll

Supersedes: ADR-013

## Context

ADR-013 accepted the pragmatic placement of `PermissionGate` inside
`core/` on the grounds that a migration to `services/` was not
cost-neutral and that the "no outgoing dependencies" invariant held
for both domain objects and cross-cutting infrastructure. The
decision was explicitly flagged as a compromise between DDD purity
and refactor cost.

Reviewing the compromise after Round 13, the refactor cost turned
out to be small (eleven import statements plus the file move), and
the confusion cost of the mixed `core/` role was higher than
initially assumed. `core/` now holds two conceptually different
kinds of modules side by side: strict Shared-Kernel domain objects
(`Invoice`, `SupplierRule`, `CoordinatorResult`, `ToolCall`,
`ToolResult`, `VerificationFailure`, `AgentStatus`) and a
cross-cutting authorisation policy (`PermissionGate`). A reader
applying strict DDD has to re-learn the deviation every time.

## Decision

Move `PermissionGate`, `PermissionLevel`, and `PermissionDeniedError`
from `src/app/core/permission_gate.py` to
`src/app/services/permission_gate.py`. The file contents are
unchanged; only the module path moves. `core/` returns to holding
strict Shared-Kernel domain objects only.

## Rationale

- `PermissionGate` is a cross-cutting policy, not a domain object.
  The conceptual home for cross-cutting infrastructure in this
  project is `services/`, which already hosts `observability/`,
  `llm/`, `sap_data.py`, and `tool_base.py`.
- `core/` in its strict sense now matches the architectural diagram
  and the fitness-function label `test_core_has_no_outgoing_deps`
  without additional context. A single rule covers every module in
  `core/`: it is a domain object, it has no outgoing dependencies,
  and every bounded context may import it.
- The refactor cost turned out to be small. Eleven files change an
  import line; the fitness functions are path-based and need no
  change.
- The "the `services/` module might acquire outgoing dependencies"
  concern raised in ADR-013 is mitigated by the observation that
  `permission_gate.py` has no imports other than `enum` from the
  standard library. A future change that adds such a dependency
  would be visible at review time and could be rejected on its own
  merits.

## Alternatives Considered

- **Keep the ADR-013 status quo.** Rejected. The original
  reluctance was refactor cost, which turns out to be small. The
  confusion cost of the mixed `core/` role is the larger number.
- **Introduce a third top-level directory such as `shared/` or
  `infrastructure/`.** Rejected. Adds vocabulary without a
  proportional benefit in a single-service codebase. `services/`
  already carries cross-cutting code and is the natural home.
- **Leave the file in `core/` but rename it to signal its status.**
  Rejected. A rename would have the same cost as the move without
  the conceptual benefit of the directory change.

## Consequences

Positive:
- `core/` returns to a clean DDD Shared-Kernel role. A single
  sentence describes what belongs there.
- `services/` gains a uniform character: everything under it is
  cross-cutting infrastructure.
- The architecture is easier to explain in interviews and design
  reviews. The diagram matches the code.

Negative:
- Git history for `permission_gate.py` splits across two paths.
  A reader who greps `core/` for the old location will need to
  follow `git log --follow` or read ADR-013 plus ADR-014.

Neutral:
- The architecture fitness functions are unchanged.
  `test_core_has_no_outgoing_deps` continues to enforce that
  `core/` has no outgoing dependencies. `test_no_cross_context_imports`
  continues to allow bounded contexts to import from `services/`,
  which now legitimately includes `permission_gate`.
- Runtime behaviour is unchanged. No test expectations shift, no
  harness status distribution changes.
