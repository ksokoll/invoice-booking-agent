# ADR-010: Versioned Prompt Library as Python Module

Status: Accepted
Date: 2026-04-08
Deciders: Kevin Sokoll

## Context

By Round 6.0 the system prompt lived in
`prompts/system_prompt.md` as raw markdown loaded at runtime by
a `load_system_prompt()` function. This worked, but it lost
information that is essential for production prompt management:
which version of the prompt is in use, when it was last changed,
which models it has been validated against, and what its purpose
is.

Kevin's other DDD project (`customer-support-ai-ddd-refactor`)
uses a typed `PromptTemplate` dataclass for exactly this reason.
The two demo projects should share the same prompt management
pattern so that a reviewer sees consistent vocabulary across
both.

The question: should the invoice agent adopt the same pattern,
or keep the simpler markdown approach?

## Decision

Replace `prompts/system_prompt.md` with a `PromptTemplate`
dataclass instance defined in `prompts/templates.py`. The
`PromptTemplate` is a frozen dataclass with fields `name`,
`version`, `last_modified`, `tested_models`, `description`, and
`prompt`. The system prompt content lives in the `prompt` field
as a triple-quoted Python string. The Coordinator imports
`SYSTEM_PROMPT` from `app.prompts` and uses
`SYSTEM_PROMPT.prompt` as the system prompt text.

## Rationale

- Prompts are content with operational metadata, not just
  content. A `PromptTemplate` captures both in one place, and the
  metadata lives next to the content (no sidecar JSON to keep in
  sync).
- Consistency with the customer-support project: same pattern,
  same field names, same usage. A reviewer comparing both repos
  sees the same prompt management approach in two different
  domains.
- The `version` field signals when prompts have been changed in a
  way that affects model behavior, separate from cosmetic edits.
- The `tested_models` field warns future maintainers which models
  the prompt has been validated against. Editing the prompt and
  not updating this field is a visible red flag in code review.
- All metadata lives next to the content. There is no separate
  `system_prompt.meta.json` to keep in sync.

## Alternatives Considered

Two alternatives were considered:

1. Keep the markdown file and add a sidecar JSON file with
   metadata (`system_prompt.meta.json`). This doubles the
   files-per-prompt and creates sync risk: the content and the
   metadata can drift out of alignment. Rejected because a single
   file is strictly simpler.
2. Use a templating library like Jinja2 to enable variable
   interpolation in the prompt. This would be useful if the
   prompt had runtime-substituted variables, but the invoice
   agent currently has zero template variables. Rejected because
   it is over-engineering for a project that does not need
   templating.

The dataclass approach is the smallest possible solution that
captures all required information without adding a dependency.

## Consequences

Positive:
- Every prompt change is also a version bump, by convention
- The `tested_models` field documents which models the prompt has
  been validated against
- Adding a second prompt (e.g. for a new use case) means adding a
  second `PromptTemplate` instance, with the same metadata
  structure

Negative:
- Editing the prompt now means editing a Python file with a
  triple-quoted string, which is slightly less ergonomic than
  editing a plain markdown file
- Non-Python collaborators cannot edit prompts without
  understanding Python syntax (the triple quotes, the trailing
  comma)

Neutral:
- The prompt content is byte-identical to what was in the markdown
  file. No content changes accompanied this refactor.
