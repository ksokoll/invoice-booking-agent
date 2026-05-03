# ADR-001: Constraint Hierarchy as a Design Principle

Status: Accepted
Date: 2026-04-04
Deciders: Kevin Sokoll

## Context

Across four consecutive patch rounds (4.0 through 5.1) the project
tried to fix a single recurring LLM hallucination via prompt
engineering. The specific bug: the `request_approval` tool's
`recipient` parameter was repeatedly filled with invented names
(John Doe, Jane Smith, the literal string "Responsible Person
Name"), even after the system prompt was rewritten multiple times
to forbid exactly those values.

Each round added a new prompt rule to fix the previous failure
mode, and each round introduced a new failure mode that the rule
did not cover. By Round 5.1 the pattern was unmistakable: five
scenarios were broken in five different ways, each a downstream
consequence of a different prompt rule fighting a different
variant of the same hallucination.

The question the project needed to answer: when is prompt
engineering the wrong tool, and what is the alternative?

## Decision

Adopt a four-level Constraint Hierarchy for enforcing rules in
LLM-driven systems, and always pick the weakest level that should
work in theory before escalating to a stronger one:

1. Soft constraint: a rule in the system prompt
2. Moderate constraint: a verification check after the fact
3. Hard constraint: removing the tool from the available set
4. Hardest constraint: removing the parameter from the tool schema

Escalate to the next level only when measurements show the current
level is empirically insufficient. After two prompt-level
iterations on the same bug, escalate immediately instead of trying
a third prompt rule.

## Rationale

- Each level has a different cost and a different guarantee. Level
  1 is cheap to add and easy for the LLM to ignore. Level 4 is
  structurally enforced and cannot be ignored at all.
- The hierarchy makes the cost/guarantee trade-off explicit. A
  reviewer can read the code and identify at which level any rule
  is enforced.
- Empirical observation from rounds 4-5: prompt rules that work
  for one test case often break another, because LLM behavior is
  correlated across cases in non-obvious ways. Stronger
  constraints isolate cases from each other.
- Documented as Rules #1-3 in `best_practises.md` (the agent
  architecture style guide), produced as a direct lesson from this
  project.

## Alternatives Considered

The two alternatives to introducing a hierarchy were:

1. Keep iterating on prompt rules indefinitely. This is what the
   project tried for four rounds. It produced cascading failure
   modes where each fix introduced a new bug. Rejected because
   the evidence showed this path does not converge.
2. Jump straight to hardest-level enforcement for every rule.
   This would over-engineer simple constraints, obscure which
   rules are actually difficult for the LLM, and remove useful
   flexibility from cases where the LLM handles the decision
   correctly. Rejected because most rules do belong at level 1
   or level 2.

The hierarchy is the middle path: start cheap, escalate only when
empirically needed.

## Consequences

Positive:
- Bug stories from this project are reproducibly traceable to
  specific hierarchy levels
- The next time a similar hallucination appears, the team has a
  protocol: try level 1 once, level 2 once, then go structural
- The hierarchy is reusable across other LLM-driven projects

Negative:
- Requires discipline to escalate quickly. The temptation to try
  one more prompt rule is strong because prompt edits are cheap.
- Level 4 (parameter removal) reduces what the LLM can decide,
  which means less flexibility for legitimate edge cases

Neutral:
- All four levels are visible at distinct code locations in the
  codebase: prompt rules in `prompts/templates.py`, verification
  in `verification/rules.py`, tool removal in
  `harness/scenarios.py` (Category 10 `minimal_tools` flag),
  parameter removal in `approval/approval_tool.py` schema
