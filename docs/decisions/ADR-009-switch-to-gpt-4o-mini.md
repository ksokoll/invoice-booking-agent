# ADR-009: Switch from gpt-4o to gpt-4o-mini

Status: Accepted
Date: 2026-04-07
Deciders: Kevin Sokoll

## Context

Round 5.5 introduced the Categories and Variants harness with
350 runs per invocation (see ADR-008). The first attempt at
running this with `gpt-4o` on a Tier 1 OpenAI account hit the
800K tokens-per-minute rate limit immediately.

Reducing parallelism from 70 to 20, then to 8, with a 30-second
cooldown between rounds, still exceeded the limit because the
sustained rate across multiple rounds accumulated within the
rolling window. The cost projection at `gpt-4o` pricing for the
full harness was also significant for a portfolio project.

The question: accept the cost and rate limit, or change models?

## Decision

Switch the OpenAI client default model from `gpt-4o` to
`gpt-4o-mini`. Keep all other code unchanged. Re-run the full
harness and measure the new pass rate.

## Rationale

- `gpt-4o-mini` has a roughly 30x lower cost per token and a
  roughly 2.5x higher rate limit on the same tier. Both
  constraints (cost and rate limit) are resolved simultaneously
  by a single change.
- The Protocol-based LLM client design (see ADR-003) makes the
  switch a one-line change in
  `services/llm/openai_client.py`. No other code is touched.
- The empirical pass rate after switching dropped from
  approximately 100% to 92% (323 of 350). The 27 failures
  concentrated on exact-equality edge cases (amount equals PO
  limit, amount equals remaining budget). Critically, all 27
  failures were caught by the deterministic Python verification
  (see ADR-004), and zero incorrect bookings occurred. The
  architecture absorbed the model downgrade.
- The 92% pass rate with documented failure analysis is a
  stronger interview story than 100% with no failures. It
  empirically demonstrates the value of the skeptical execution
  architecture: even when the LLM gets the reasoning wrong, the
  verification layer catches it every time.

## Alternatives Considered

Three alternatives were considered:

1. Upgrade the OpenAI account to a higher tier to remove the
   rate limit. This costs money and does not address the
   per-token cost. Rejected because a portfolio project should
   not require a paid account upgrade to demo.
2. Implement exponential backoff with retries via `tenacity`.
   This would let aggressive parallelism work within the rate
   limit, but does not reduce cost and adds a dependency plus
   retry logic complexity. Rejected because cost was the larger
   concern.
3. Switch to Anthropic's `claude-haiku`. This would also work
   and has comparable cost, but it introduces a different model
   family mid-project and would require re-running comparison
   benchmarks. Rejected because `gpt-4o-mini` is the
   lowest-friction option: same family, same tool-call format,
   same tokenizer.

## Consequences

Positive:
- Full harness runs in 9 to 10 minutes wall clock without rate
  limit errors
- Cost per harness run dropped by approximately 30x
- The failure analysis from `gpt-4o-mini` becomes a concrete
  empirical demonstration of the deterministic verification
  layer's value

Negative:
- Pass rate fell from approximately 100% to 92.3%
- The 27 failures cluster in exact-equality categories (Cat 4
  "Exact limit" and Cat 14 "Budget exactly sufficient"), making
  those two categories noticeably weaker than the others
- The interview demo must explain the failure pattern, which
  requires more nuance than "everything works"

Neutral:
- The switch validates the Protocol-based design from ADR-003: a
  model change is a one-line edit
- The 27 failures are all of the form `blocked_approval_missing`,
  the same blocking status that the safety net is designed to
  produce when the LLM tries to skip a required step
