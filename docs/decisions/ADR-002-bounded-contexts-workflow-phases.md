# ADR-002: Bounded Contexts Along Workflow Phases

Status: Accepted
Date: 2026-04-08
Deciders: Kevin Sokoll

## Context

After Round 6.0 the codebase had a clean Layered Architecture
consisting of `domain/`, `application/`, and `infrastructure/`
packages. It worked correctly and the layering rules were
respected. The problem was stylistic: this layout diverged from
Kevin's other DDD project (`customer-support-ai-ddd-refactor`),
which uses Bounded Contexts along business capabilities
(classification, retrieval, generation, quality_assurance).

Two demo projects with different architectural vocabularies is a
defendability risk in the upcoming paiqo interview. A reviewer
comparing both repos will reasonably ask why the same team picked
different architectures for similar problems, and the answer
should be visible in the code rather than improvised on the spot.

The question: which bounded context decomposition fits the
invoice agent's domain best, and why does it differ from the
customer-support decomposition?

## Decision

Restructure the codebase into four Bounded Contexts named after
the phases of an AP clerk workflow:

- `intake/` (review the invoice)
- `verification/` (check business constraints)
- `approval/` (obtain authorization)
- `booking/` (record the result)

Each context owns its tools and any domain logic specific to that
phase. Cross-context types live in `core/` as a Shared Kernel.
The Coordinator lives at top-level `pipeline.py` outside any
context, because it orchestrates across all contexts.

## Rationale

- Invoice booking has natural sequence boundaries, not natural
  capability boundaries. A real AP clerk performs four
  recognizable steps in order. The architecture mirrors this.
- The phase names match the language an AP domain expert would
  use, so the code structure is self-documenting for any reviewer
  with a finance background.
- Aligns with `architecture.md` Rule #6 (separate bounded contexts
  for components with different lifecycle and scaling
  requirements). intake and booking change for different reasons
  and at different rates.
- Consistency with the customer-support project: same DDD
  vocabulary, different decomposition axis, same shared kernel
  pattern. The axis differs because the domains differ: customer
  support has parallel capabilities, invoice booking has a
  sequential pipeline.

## Alternatives Considered

| Dimension | Layered (Round 6) | Workflow phases | Capability split |
|---|---|---|---|
| Maps to domain language | No | Yes (AP clerk steps) | No (technical) |
| Cohesion of related code | Medium | High | Medium |
| Symmetry of context sizes | High | Medium (verification is largest) | High |
| Consistency with customer-support repo | No | Yes | Yes |
| Easy to explain to a domain expert | No | Yes | No |

The workflow phase decomposition wins on every dimension that
matters for the demo: domain language, cohesion, and consistency
with the other repo. The asymmetric size is acceptable because
verification owns both the rules and the tools that feed them,
which is the correct home for both.

## Consequences

Positive:
- A reviewer with AP background can navigate the codebase without
  explanation
- Adding a new phase (e.g. archiving) means creating a new context,
  not modifying existing ones
- Test scenarios can be grouped by which context they exercise

Negative:
- `verification/` is larger than the other three contexts
- `pipeline.py` is the only module allowed to import from multiple
  contexts, which concentrates orchestration knowledge in one file
- Migration from Round 6 layered structure required updating every
  import statement in `main.py` and `tests/`

Neutral:
- Cross-context imports are forbidden by convention and enforced
  by the architecture fitness function in
  `tests/architecture/test_no_cross_context_imports.py` (see
  ADR-007)
