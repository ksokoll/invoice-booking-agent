# ADR-005: Recipient Removal from the Approval Tool Schema

Status: Accepted
Date: 2026-04-04
Deciders: Kevin Sokoll

## Context

The `request_approval` tool needs three pieces of information to
execute: the invoice ID, the amount, and the recipient (the
person authorized to approve invoices for that PO). The recipient
is deterministic: for any given PO, exactly one person has
authority, and the information is returned by the earlier
`get_po_limit` tool call as its `responsible_person` field.

Across patch rounds 4.0 through 5.1, the LLM hallucinated the
recipient value in 8 of 14 test scenarios, copying it from
unrelated fields (the invoice's `contact_person`, the supplier
name, the PO number itself) or inventing it outright (John Doe,
"Responsible Person Name"). Four rounds of prompt engineering
each fixed one variant of the bug while introducing a new one.

The question: when prompt engineering provably cannot fix a
parameter hallucination, what is the structural alternative?

## Decision

Remove the `recipient` parameter from the `request_approval`
tool's LLM-visible schema entirely. The `input_schema` only
contains `invoice_id` and `amount_eur`. The Coordinator's
`_pre_execute_verify` method injects the recipient into the tool
call params from `state["po_responsible_person"]` immediately
before the tool executes. The LLM never sees the recipient field,
never decides what its value should be, and cannot hallucinate it.

## Rationale

- This is the canonical example of Constraint Hierarchy level 4
  (parameter removal) from ADR-001. The level was reached after
  empirically proving that levels 1, 2, and 3 were insufficient.
- The decision separates two concerns: WHEN approval is needed (an
  LLM judgment based on amount and threshold) and TO WHOM it goes
  (a deterministic lookup from prior state). The LLM is good at
  the first; it is unreliable at the second.
- Tool schemas are intentionally not 1:1 with full tool signatures.
  They are contracts about what decisions the LLM is allowed to
  make. Hiding a parameter is a statement about its decisional
  ownership.
- Aligns with `best_practises.md` Rule #9: "Coordinator-managed
  parameters are the strongest version of state-as-truth."

## Alternatives Considered

Four alternatives were attempted in order, following the
Constraint Hierarchy discipline from ADR-001:

1. Soft prompt rule "always pass responsible_person as recipient".
   Failed in 4 of 14 scenarios. The LLM would read the rule and
   still substitute a different field.
2. Worked example in the tool description showing the exact
   mapping from `get_po_limit.responsible_person` to the
   `recipient` parameter. Failed in 3 of 14 scenarios. The LLM
   copied the example value literally instead of the current
   value.
3. Verification check after the fact that blocks booking if the
   LLM-supplied recipient does not match `po_responsible_person`.
   Caught the bug but produced a confusing error, and did not
   prevent the LLM from trying again in the next iteration of the
   same run.
4. Parameter removal (the chosen solution). Eliminated the bug
   class entirely.

Each weaker alternative was tried first because of the hierarchy
discipline. The documentation of these failures is what produced
the Constraint Hierarchy itself.

## Consequences

Positive:
- The recipient hallucination class of bugs is structurally
  impossible after Round 5.2
- The pattern (Coordinator-managed parameter injection)
  generalizes to any future parameter that is deterministic from
  state
- The injection logic in `pipeline.py` is small (around 10 lines)
  and visible at one location

Negative:
- The Coordinator now has knowledge of which tool parameters it
  must inject. This is a small but real form of coupling between
  the orchestrator and the tools.
- A reviewer reading `approval_tool.py` in isolation sees a schema
  with only two fields and might wonder where the recipient comes
  from. The answer is in the Coordinator, one file away.

Neutral:
- The tool's `execute()` method still accepts a `recipient`
  parameter (because the Coordinator injects it). The asymmetry
  between the schema and the execute signature is intentional.
