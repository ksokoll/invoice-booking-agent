# ADR-004: Verification as Pure Python Functions

Status: Accepted
Date: 2026-04-04
Deciders: Kevin Sokoll

## Context

Every action the agent takes (book invoice, request approval,
consult Procurement) needs to be verified against business rules
before execution. There are two places this verification could
live: as part of the LLM's reasoning (instructed via the system
prompt), or as deterministic Python code in the Coordinator.

Empirical observation from the early rounds: the LLM produces
correct verification reasoning most of the time but not always.
It makes equality-edge-case mistakes (200.00 EUR vs 200.00 EUR
limit), occasionally forgets to check budget after consulting
Procurement, and cannot be relied on for safety-critical checks where
a single wrong answer results in an incorrect booking.

The question: where does verification belong, and how is its
integrity guaranteed?

## Decision

All verification rules live in `verification/rules.py` as pure
Python functions with no I/O, no logging, no LLM calls, and no
imports from `services/`, `pipeline.py`, or any bounded context
other than `core/`. Each function takes the relevant state as
arguments and returns either `None` (rule passed) or a
`VerificationFailure` instance (rule violated). The Coordinator
calls these functions before and after every tool execution.

## Rationale

- Direct application of `best_practises.md` Rule #8: "Verification
  belongs in pure Python, not in the LLM. Any check whose correct
  answer depends on a deterministic comparison against state is a
  Python check, not an LLM judgement."
- Pure functions are testable in isolation. Each rule has a unit
  test that does not require any LLM mock.
- The architecture fitness function in
  `tests/architecture/test_verification_rules_are_pure.py`
  enforces the purity constraint by inspecting imports (see
  ADR-007).
- Empirical evidence from Round 5.5: across 350 test runs with
  gpt-4o-mini, the LLM made 27 verification reasoning errors at
  exact-equality boundaries. The deterministic Python checks
  caught all 27 before any incorrect booking. Zero false
  positives.

## Alternatives Considered

The alternative was to instruct the LLM to perform verification
reasoning in its chain-of-thought before each tool call. This
works most of the time but fails reproducibly at boundary
conditions where mathematical equality matters. gpt-4o-mini
specifically struggles with cases like "is 100.00 EUR greater
than 100.00 EUR?". Pure Python evaluates this in microseconds and
is correct every time, every time, every time. Rejected because
correctness at boundaries is the whole point of verification.

## Consequences

Positive:
- Zero false positives across 350 production-style runs
- Each verification rule is independently testable with a one-line
  test
- The "skeptical execution" property of the architecture is
  enforceable, not aspirational

Negative:
- Adding a new verification rule requires touching three files:
  the rule function in `verification/rules.py`, the call site in
  `pipeline.py`, and the status mapping in `pipeline.py`'s
  `_STATUS_MAP`. This three-file coupling is a known smell and a
  future refactor candidate.
- Verification logic is in code, not in a configurable rule
  engine. Changing a threshold requires a code change and a
  redeploy.

Neutral:
- The `VerificationFailure` dataclass becomes the contract between
  rules and the Coordinator's failure routing logic (see ADR-006)
