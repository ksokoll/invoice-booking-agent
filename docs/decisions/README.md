# Architecture Decision Records

This directory contains the Architecture Decision Records (ADRs)
for the invoice booking agent. ADRs document significant
architectural choices, the context that demanded them, the
alternatives considered, and the consequences accepted.

The format follows a standardized template with sections for
Context, Decision, Rationale, Alternatives Considered, and
Consequences. Each ADR has a status (Accepted, Deprecated, or
Superseded), a date, and a list of deciders.

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-constraint-hierarchy.md) | Constraint Hierarchy as a Design Principle | Accepted |
| [ADR-002](ADR-002-bounded-contexts-workflow-phases.md) | Bounded Contexts Along Workflow Phases | Accepted |
| [ADR-003](ADR-003-protocol-based-llm-client.md) | Protocol-Based LLM Client for Provider Independence | Accepted |
| [ADR-004](ADR-004-verification-as-pure-functions.md) | Verification as Pure Python Functions | Accepted |
| [ADR-005](ADR-005-recipient-removal-from-approval-schema.md) | Recipient Removal from the Approval Tool Schema | Accepted |
| [ADR-006](ADR-006-hard-consultable-failure-routing.md) | Hard / Consultable Failure Routing | Accepted |
| [ADR-007](ADR-007-architecture-fitness-functions.md) | Architecture Fitness Functions as Executable Tests | Accepted |
| [ADR-008](ADR-008-categories-and-variants.md) | Categories and Variants in the Test Harness | Accepted |
| [ADR-009](ADR-009-switch-to-gpt-4o-mini.md) | Switch from gpt-4o to gpt-4o-mini | Accepted |
| [ADR-010](ADR-010-versioned-prompt-library.md) | Versioned Prompt Library as Python Module | Accepted |
| [ADR-011](ADR-011-observability-architecture-characteristic.md) | Observability as an Architecture Characteristic | Accepted |
| [ADR-012](ADR-012-decorator-based-span-instrumentation.md) | Decorator-Based Span Instrumentation | Accepted |
| [ADR-013](ADR-013-cross-cutting-concerns-in-core.md) | Cross-Cutting Concerns in core/ | Superseded (by ADR-014) |
| [ADR-014](ADR-014-permissiongate-relocation.md) | PermissionGate Relocation to services/ | Accepted |

## Reading order

For a first-time reader unfamiliar with the project:

1. Start with ADR-002 (Bounded Contexts) for the high-level
   structure
2. Read ADR-001 (Constraint Hierarchy) for the most important
   design principle
3. Read ADR-005 (Recipient Removal) for the concrete bug story
   that produced ADR-001
4. Read the others in any order

## ADR Format

Every ADR uses the same structure:

- Status, Date, Deciders header
- Context: the situation that demanded a decision
- Decision: what was chosen
- Rationale: why this was chosen, with references to applicable
  style guide rules
- Alternatives Considered: prose or trade-off table
- Consequences: positive, negative, and neutral effects

## Docstring Practice in This Project

The code follows Google-style docstrings, but applies a stricter
rule than the style guide requires: a function earns a full
Args/Returns/Raises block when its behaviour goes beyond what the
name and type annotations already communicate. Typical triggers
are non-trivial business rules, heuristics with magic constants,
ambiguous return types (for example a union where the variant
depends on state), and non-obvious fallback behaviour. Functions
whose name and signature fully describe the contract keep their
single-line docstrings. This note exists so future contributors
recognise the pattern as intentional rather than as drift from
the style guide.
