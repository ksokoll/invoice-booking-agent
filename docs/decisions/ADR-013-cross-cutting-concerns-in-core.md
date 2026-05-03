# ADR-013: Cross-Cutting Concerns in core/

> **Status:** Superseded by ADR-014 (Round 14).

Status: Superseded
Date: 2026-04-24
Deciders: Kevin Sokoll

## Context

ADR-002 organises the agent into bounded contexts aligned with
workflow phases (intake, verification, approval, booking) and a
`core/` layer that acts as the Shared Kernel in the strict DDD
sense. The Shared Kernel is meant to hold domain objects that
every bounded context needs to reference, with no outgoing
dependencies. The architecture fitness function
`test_core_has_no_outgoing_deps` enforces the "no outgoing
dependencies" half of the contract.

In practice, `core/` in this project carries two distinct kinds
of modules:

- Shared Kernel in the strict sense: domain objects such as
  `Invoice`, `SupplierRule`, `CoordinatorResult`, `ToolCall`,
  `ToolResult`, `VerificationFailure`, `AgentStatus`.
- Cross-cutting infrastructure: `PermissionGate`, which is not a
  domain object but an authorisation policy that every bounded
  context must route through.

The Round 13 walkthrough flagged this as a category-C smell and
asked whether `PermissionGate` should move to `services/` where
most other cross-cutting code lives. The move is theoretically
cleaner but not cost-neutral (imports in multiple files, updates
to the fitness functions, test rewiring), and the benefit is
purely structural.

## Decision

Keep cross-cutting infrastructure that every bounded context
depends on inside `core/`. Specifically, `PermissionGate`
remains in `core/permission_gate.py`. We document the decision
rather than migrate the code.

The implicit rule becomes: `core/` holds both the strict DDD
Shared Kernel and cross-cutting infrastructure that must not
depend on any bounded context. A module belongs in `core/` if
and only if (a) every bounded context is allowed to import it
and (b) it has no outgoing dependencies on any bounded context
or service.

## Rationale

- The "no outgoing dependencies" rule that the fitness function
  enforces is the load-bearing guarantee. Both kinds of modules
  in `core/` satisfy it.
- Moving `PermissionGate` to `services/` would expose it to code
  that has outgoing dependencies on bounded contexts. The
  integrity of the Shared Kernel would hold, but the new module
  in `services/` would be at risk of gaining dependencies on
  bounded contexts, which is the opposite of what a cross-cutting
  policy wants.
- The term "Shared Kernel" in the strict DDD sense is narrower
  than how `core/` is used here. We choose to extend the meaning
  of `core/` rather than invent a third top-level directory.
- Refactor cost (imports, fitness functions, tests) outweighs the
  structural benefit. The money saved can be spent on work with
  higher leverage.

## Alternatives Considered

- **Move `PermissionGate` to `services/permission_gate.py`.** The
  theoretically purer choice. Not taken because of the refactor
  cost and because the new location would weaken the invariant
  that the gate has no outgoing dependencies.
- **Invent a new top-level directory (for example `shared/`) for
  cross-cutting code.** Would require reorganising the fitness
  functions and documenting a third kind of module. Not taken
  because the benefit does not justify the additional vocabulary
  in a single-service codebase.
- **Leave the smell uncommented.** Not taken because a future
  reader applying strict DDD would wonder why `PermissionGate`
  sits next to `Invoice`. The decision is worth documenting even
  when the code does not move.

## Consequences

Positive:
- Status quo is stabilised. No migration, no fitness-function
  changes, no test rewiring.
- Future readers have a clear answer when they ask "why is this
  in `core/`?". The answer is "`core/` covers both Shared Kernel
  and cross-cutting infrastructure in this project".

Negative:
- Theoretical purists may note that `core/` is no longer a
  strict DDD Shared Kernel. The deviation is documented and
  intentional.

Neutral:
- The fitness function `test_core_has_no_outgoing_deps` is
  unchanged and works for both interpretations: every
  `core/` module continues to have zero outgoing dependencies
  on bounded contexts or services, regardless of whether it is
  a domain object or a cross-cutting policy.
