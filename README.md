# Invoice Booking Agent: LLM-Driven AP Automation

A production-grade autonomous agent that books supplier invoices into SAP, built
around a deterministic Coordinator that orchestrates an LLM through a constrained
tool API. The system demonstrates how to keep agentic systems safe, observable, and
testable in environments where LLM mistakes have financial consequences.

## Motivation

The idea predates this implementation by several years. As a P2P accountant
turned automation architect, I started experimenting with LLM-driven invoice
booking when GPT-3 was released in 2023. The first attempt was a Power Automate
prototype with mock databases. It failed. Subsequent iterations on Crew-AI got
closer but never crossed the line where I would trust the system in a real
accounting context.

This project is the version that finally clears that bar, on artificial business
cases close to production scenarios I have seen in practice.

---

## Business Context

In a typical Accounts Payable department, clerks process invoices through a fixed
sequence of checks: validate the invoice against its purchase order, verify supplier
status, route for approval if the amount exceeds limits, post to SAP. Most of this
work is rule-driven and repetitive, but enough edge cases exist that pure RPA
solutions cannot handle the long tail.

This system uses an LLM to drive the workflow autonomously. The LLM decides which
tools to call in which order. A deterministic Coordinator wraps the LLM, enforces
business rules through pure-Python verification, and routes failures by category.

| Metric | Result |
|---|---|
| Successful auto-booking rate | 78% across 14 scenario categories |
| Hard failures correctly blocked | 100% of limit, supplier, and contradiction cases |
| Human escalations correctly routed | 100% of designated edge cases |
| LLM contradictions caught by verification | 27/27 in Round 5.5 (zero leaked) |
| End-to-end run latency | ~3-5 seconds with gpt-4o-mini |

---

## Architecture

The system is structured around four bounded contexts aligned with the AP workflow.
Each context owns its tools and its tests. No context imports from another context
directly. All cross-context coordination flows through `pipeline.py`.

```
LLM
  │
  ▼
pipeline.py (Coordinator)
  ├── intake/         get_invoice_data, get_supplier_rules
  ├── verification/   get_po_limit, get_budget, pure rule functions
  ├── approval/       request_approval, consult_procurement
  └── booking/        book_invoice, escalate_to_human
```

```
src/app/
  core/                   Domain entities, statuses, results, failures
  services/               Cross-cutting: LLM clients, observability, permission gate
  intake/                 Bounded context: invoice and supplier intake
  verification/           Bounded context: PO and budget checks, pure rules
  approval/               Bounded context: approval workflow
  booking/                Bounded context: SAP booking and escalation
  prompts/                Versioned prompt library
  harness/                Test harness with 14 categories x 5 variants x 5 rounds
  pipeline.py             Coordinator orchestration
  main.py                 Entry point
```

### Constraint Hierarchy

The central design principle. Rules in LLM-driven systems are enforced at four
levels of strength, weakest first, escalated only on empirical failure:

1. **Prompt rule** "you must call X before Y"
2. **Verification check** pure-Python validation after each tool call
3. **Tool removal** the tool does not exist in the LLM's schema
4. **Parameter removal** the parameter does not exist in the tool's schema

The canonical level-4 example is the `request_approval` tool. The recipient field is
absent from the LLM-visible schema. The Coordinator injects it from authoritative
state, so the LLM cannot hallucinate or override the approver.

### Protocol-based LLM Client

The Coordinator imports only the `LLMClient` Protocol. Concrete providers
(`AnthropicClient`, `OpenAIClient`) implement it without inheritance. Provider
switching is one line in the wiring code. Tests run with a dummy client and no API
keys.

```python
class LLMClient(Protocol):
    def start(self, system_prompt: str, task: str, tool_schemas: list[dict]) -> LLMResponse: ...
    def continue_with_results(self, results: list[ToolResult]) -> LLMResponse: ...
```

### Verification as Pure Functions

Every business rule is a pure Python function in `verification/rules.py`. No I/O, no
LLM, no logging. An architecture fitness function enforces purity by AST inspection
on every CI run. The Coordinator calls these rules after each tool execution and
routes failures based on classification.

### Hard vs. Consultable Failure Routing

Failures fall into two categories, distinguished by data, not by control flow:

- **Hard failures** terminate the run immediately. Examples: limit exceeded,
  supplier inactive, cost center not allowed.
- **Consultable failures** return to the LLM as a tool result, allowing it to call
  `consult_procurement` and retry. Limited to two rule names and capped at three
  consultations per invoice.

The classification lives as a `frozenset` in `core/failures.py`, separate from
enforcement logic.

### Three-Pillar Observability

Logs via `structlog`, traces via OpenTelemetry, metrics via `prometheus_client`,
linked by a correlation ID per run held in a `ContextVar`. Structural spans are
declared via a `@traced` decorator; iteration-level and dynamic spans remain manual.
The Coordinator owns all observability calls so business logic stays clean.

---

## Key Decisions

Fourteen Architecture Decision Records document the major choices. Selected
highlights:

**ADR-001: Constraint Hierarchy.** Distilled from four prompt-engineering rounds
that failed to prevent recipient hallucination. The hierarchy formalizes when to
escalate from soft prompts to hard schema removal.

**ADR-004: Verification as Pure Python Functions.** Round 5.5 of the test harness
caught 27 LLM reasoning errors at equality boundaries. All 27 were blocked by
deterministic rule functions, zero leaked into bookings.

**ADR-007: Architecture Fitness Functions.** Three AST-based tests enforce layering
rules: `core/` has no outgoing dependencies, bounded contexts do not import from
each other, `verification/rules.py` stays pure. Run on every CI invocation.

**ADR-014: PermissionGate Relocation.** Moved from `core/` to `services/` after
recognizing that permission checks are cross-cutting infrastructure, not domain
concepts. Supersedes ADR-013, which had documented the pragmatic placement. Kept in
the index as Superseded to preserve the decision history.

Full ADRs in `docs/decisions/`.

---

## Quickstart

```bash
# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Add your ANTHROPIC_API_KEY or OPENAI_API_KEY

# Run the harness
make run
# Reports written to runs/
```

The harness executes 14 scenario categories, each with 5 variants, across 5 rounds
(350 runs total). Each scenario asserts an expected `AgentStatus`. The pass rate
across rounds is the system's quality metric.

### Example Scenario

A normal invoice within all limits should book cleanly:

```python
Scenario(
    invoice_id="17",
    expected_status=AgentStatus.BOOKED,
    description="Standard supplier invoice within PO limit and approval threshold.",
)
```

A contradiction should be caught and escalated:

```python
Scenario(
    invoice_id="42",
    expected_status=AgentStatus.BLOCKED_CONTRADICTION,
    description="Approver refuses citing limit exceeded, but amount is within their limit.",
)
```

---

## Development

```bash
make test-unit          # Unit tests, no API calls
make test-architecture  # Fitness functions for layering rules
make lint               # ruff + mypy strict mode
make run                # Full harness, requires API key
```

### Test Strategy

```
Unit tests           Per-context logic, dummy LLM clients, no I/O
Architecture tests   AST-based layering and purity rules
Harness              End-to-end runs against real LLM providers, the integration test for stochastic agent behavior
```

The harness is the truth. Unit tests catch regressions, architecture tests catch
structural drift, but only the harness measures whether the system actually books
the right invoices.

---

## Project Layout

```
src/app/
  core/
    entities.py             Invoice, SupplierRule, PORecord, BudgetRecord
    failures.py             VerificationFailure, CONSULTABLE_RULES
    results.py              ToolCall, ToolResult, CoordinatorResult
    statuses.py             AgentStatus enum (16 terminal states)
  services/
    llm/                    LLMClient Protocol, Anthropic + OpenAI implementations
    observability/          structlog, OpenTelemetry, prometheus, @traced decorator
    permission_gate.py      Cross-cutting permission check
    sap_data.py             Mock SAP data for the harness
    tool_base.py            Tool Protocol
  intake/                   invoice_tool, supplier_rules_tool
  verification/             po_tool, budget_tool, rules.py (pure functions)
  approval/                 approval_tool, consult_procurement_tool
  booking/                  booking_tool, escalate_to_human_tool
  prompts/
    templates.py            Versioned prompt library
  harness/
    scenarios.py            14 categories x 5 variants
    runner.py, report.py    Harness execution and reporting
  pipeline.py               Coordinator orchestration
  main.py                   Entry point

docs/
  decisions/                14 ADRs documenting architectural choices

tests/
  unit/                     Coordinator and observability unit tests
  architecture/             Fitness functions enforcing layering
```

---

## Status

Built between March and April 2026 across 14 iterative refactor rounds. The 
implementation was developed in close collaboration with Claude Code: code 
generation and routine refactoring were AI-assisted, while architecture 
decisions, ADRs, and the review-driven refactor strategy are mine. A final
ownership walkthrough was the validation step.

This is a portfolio project. It runs against mock SAP data, not a live ERP. 
Not actively accepting contributions.

## License

MIT. See `LICENSE` for details.