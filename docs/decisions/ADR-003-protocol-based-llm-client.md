# ADR-003: Protocol-Based LLM Client for Provider Independence

Status: Accepted
Date: 2026-04-03
Deciders: Kevin Sokoll

## Context

The invoice agent must work with both OpenAI and Anthropic APIs.
The two providers have different message formats, different tool
schemas, different streaming semantics, and different conventions
for signaling the end of a conversation. A naive approach would
hardcode one provider into the Coordinator and add the second
later as a fork.

The question: how to model the LLM dependency so that swapping
providers is a single import change, not a codebase-wide refactor?

## Decision

Define an `LLMClient` Protocol in
`services/llm/client_protocol.py` that captures only what the
Coordinator needs:

- `start(system_prompt, task, tool_schemas)` returns an
  `LLMResponse`
- `continue_with_results(tool_results)` returns the next
  `LLMResponse`

Each concrete provider implements the protocol in its own file
(`anthropic_client.py`, `openai_client.py`). The Coordinator
imports only the Protocol, never any concrete provider. Provider
selection happens via the `PROVIDER` environment variable in
`harness/wiring.py::build_llm_client()`.

## Rationale

- Direct application of `architecture.md` Rule #2: "Guide
  technology choices, don't specify them. Say 'use a
  Protocol-based client interface' not 'use OpenAI'."
- A Protocol-based interface means the Coordinator can be tested
  without any real LLM calls. A mock client implementing the
  Protocol substitutes for real providers in unit tests, which is
  how all 50 unit tests avoid needing API keys.
- Adding a third provider (e.g. Google Gemini) requires creating
  one new file in `services/llm/` and updating one branch in
  `wiring.py`. No other code changes.
- Aligns with the Open-Closed Principle: the system is open for
  extension (new providers) and closed for modification (no
  existing code needs to change).

## Alternatives Considered

Two alternatives were considered:

1. Inherit from an abstract base class instead of using a
   Protocol. This is more verbose, creates an unnecessary
   inheritance hierarchy, and does not interoperate as cleanly
   with duck-typed test doubles. Rejected because Protocol gives
   the same guarantees with less code.
2. Use a unified abstraction layer like LangChain that wraps
   multiple providers behind a single import. This adds a heavy
   third-party dependency, obscures the actual provider behavior
   behind a generic interface, and couples the project to the
   abstraction author's design choices. Rejected because the
   Protocol approach achieves provider independence with zero
   third-party dependencies and around ten lines of interface
   code.

## Consequences

Positive:
- Two providers (OpenAI, Anthropic) work with the same Coordinator
  code today
- The mid-project switch from gpt-4o to gpt-4o-mini (see ADR-009)
  required changing one default parameter, no architecture changes
- Unit tests use a mock LLMClient and run without API keys

Negative:
- The Protocol must be kept narrow. Adding methods that only one
  provider supports creates pressure to widen it, which would
  erode provider independence.
- Provider-specific features (like Anthropic's prompt caching) have
  to be modeled inside the concrete client, not exposed via the
  Protocol

Neutral:
- The `LLMResponse` dataclass becomes the lingua franca between
  Coordinator and providers. Its shape is the real contract; the
  Protocol just names the methods.
