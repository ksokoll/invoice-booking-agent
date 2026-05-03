# ADR-008: Categories and Variants in the Test Harness

Status: Accepted
Date: 2026-04-07
Deciders: Kevin Sokoll

## Context

By Round 5.4 the test harness ran 14 hardcoded scenarios, each
exercising one specific behavior with one specific data point.
A scenario passed or failed against one fixed input. This made
it impossible to tell whether the agent had learned the general
pattern or had memorized the specific input.

If invoice ID "2" with amount 20 EUR worked, did invoice ID
"15" with amount 80 EUR also work against a different PO with
a different responsible person? The 14 scenarios could not say.
Each one tested a single data point, and the fixed inputs
happened to concentrate on a narrow slice of the input space
(one main PO, three cost centers, one active supplier).

The question: how to test pattern learning instead of input
memorization, without adopting a heavy property-based testing
library?

## Decision

Restructure the harness into 14 behavioral Categories, each
containing 5 concrete Variants. A Category defines the expected
behavior (e.g. "Amount within limit, must book") and the
expected status. A Variant is one concrete data point that
should produce that status. Each Variant runs in isolation with
its own state.

Variant "a" of every Category preserves the exact data from
Round 5.4 to guarantee continuity with prior results. Variants
"b" through "e" introduce new data that exercises the same
behavior. Total runs per harness invocation: 14 categories x
5 variants x 5 rounds = 350 runs.

## Rationale

- This is property-based testing applied by hand. Instead of
  asserting "invoice 2 with 20 EUR is bookable", the harness
  asserts "any invoice within its PO limit is bookable" and
  exercises that property with five different concrete invoices.
- Catches over-fitting. If an LLM only handles the specific
  values it has seen in training-like patterns and fails on
  novel values, the variants surface this immediately.
- Catches sample bias in the mock data. The original scenarios
  used a narrow range of POs and cost centers. The new variants
  use four new POs, seven new cost centers, and fifty new
  invoices, exposing the agent to broader input variation.
- Better interview narrative: "I test 14 categories with 5
  concrete variants per category, 5 rounds per harness
  invocation, 350 runs total" is a stronger story than "I test
  14 hardcoded cases".

## Alternatives Considered

Two alternatives were considered:

1. Increase the number of rounds from 5 to 50 with the same 14
   scenarios. This catches sampling noise across multiple LLM
   invocations, but it does not catch over-fitting. The same 14
   inputs still only probe 14 points in the input space.
   Rejected because the goal was pattern learning, not sampling
   noise.
2. Use a real property-based testing library like Hypothesis
   with generators for each category. This is overkill for
   fixed behavioral categories with hand-curated test data, and
   it would obscure the `expected_status` declaration per
   category. Rejected because the Categories/Variants design
   captures most of the property-based testing benefit without
   the library dependency.

## Consequences

Positive:
- 25 runs per category per harness invocation catch over-fitting
  reproducibly
- The first variant of every category preserves backward
  compatibility with Round 5.4 results
- Categories serve as documentation: a reader can see all 14
  behaviors of the agent in one file (`harness/scenarios.py`)

Negative:
- The harness file grew from around 14 scenarios to 14 categories
  with 70 variants. Mock data also grew significantly (fifty new
  invoices, four new POs, seven new cost centers).
- Running all 350 scenarios takes 9 to 10 minutes wall clock
  with rate-limit-safe parallelism (8 parallel, 30 second cooldown
  between rounds)

Neutral:
- The `expected_status` is declared at the Category level, not
  per Variant. All variants of a category share the same
  expectation, which is exactly what makes them variants of the
  same behavior.
