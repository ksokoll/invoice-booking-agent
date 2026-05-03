# ADR-006: Hard / Consultable Failure Routing

Status: Accepted
Date: 2026-04-04
Deciders: Kevin Sokoll

## Context

Verification failures are not all the same. Some are terminal:
the invoice does not exist, the supplier is inactive, the
booking is a duplicate. There is no recovery path. Other
failures might be resolvable: the PO limit might be raisable by
Procurement, the budget might be reallocatable across cost centers.

A real AP clerk handles these two classes differently.
Hard failures get escalated to a human immediately. Soft
failures get a quick consultation with Procurement first, and only
if that does not resolve the problem does the case escalate.

The question: how to encode this routing distinction in the
codebase without hardcoding it at multiple call sites?

## Decision

Maintain a single `frozenset` constant in `core/failures.py`
named `CONSULTABLE_RULES` containing the rule names that may be
recovered through consultation. The Coordinator's
`_route_failure` method consults this set: if the failure rule
is in `CONSULTABLE_RULES`, the failure is returned to the LLM as
a tool result with `verification_failed=true`, allowing the LLM
to choose between consulting Procurement or escalating. If the rule
is not in the set, the failure terminates the run immediately
with the appropriate `BLOCKED_*` status.

## Rationale

- The classification (which failures are consultable) is business
  knowledge from the AP domain, not a technical property.
  Modeling it as data (a frozenset) instead of as code branches
  makes it easy to inspect and change.
- The `frozenset` is a single source of truth. There is no
  duplicated routing logic anywhere else in the system.
- The decision to consult or escalate is left to the LLM, not
  hardcoded. This is correct because it depends on context (how
  many consultations have already happened, what the Procurement team
  said, what the human escalation queue looks like). The LLM has
  the context; the routing constant determines only whether the
  option is available.
- Models real AP clerk cognition: humans know which
  problems are worth a phone call to procurement and which ones
  need to go straight to a manager.

## Alternatives Considered

Two alternatives were considered:

1. Hardcode the routing in the Coordinator with an `if-elif`
   chain on rule names. This would scatter the classification
   across the code, and every new rule would require editing the
   chain in addition to adding the rule function. Rejected
   because the data table is strictly better separation.
2. Make each verification function declare its own consultability
   via a field on `VerificationFailure`. This would couple the
   rule implementation to its routing semantics, meaning the same
   rule could not be reused with different routing in a future
   context. Rejected because rule semantics and routing semantics
   have different lifecycles.

The frozenset is the cleanest separation: rules don't know about
routing, the Coordinator doesn't know about rule semantics, the
routing table is one line of data.

## Consequences

Positive:
- Adding a new consultable failure type means adding one string
  to the frozenset
- The routing logic is testable in isolation
- The business semantics (which failures procurement can help
  with) are visible at a single location for any reviewer with
  domain knowledge

Negative:
- The string-based key creates a small risk of typos. A misspelled
  rule name in the frozenset would silently fail to route
  correctly. Mitigated by using rule names that match the
  function names in `verification/rules.py`.
- LLMs occasionally try to consult Procurement for hard failures out
  of optimism. The tool description for `consult_procurement` has
  explicit guards against this.

Neutral:
- The maximum consultation budget per invoice (currently 3) is
  enforced separately by the Coordinator, not by the routing
  constant. The two concerns are intentionally kept separate.
