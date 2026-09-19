# Project memory store file schema

`.sdlc/memory/` contains these files. Keep each one focused - this is what
makes progressive reading cheap.

## `project-brief.md`

The stable "what and why" of the project: purpose, target users, core
scope, explicit non-goals, high-level success criteria. Changes rarely -
update only when the project's actual purpose/scope shifts.

## `architecture.md`

Current architecture: major components/modules, how they interact, key
technology choices and why, data flow for the most important paths. This is
a living description of "how the system currently works", not a history -
prefer editing in place over appending indefinitely.

## `decisions-log.md`

Append-only log of non-obvious decisions. One entry per decision:

```
## <date> - <short title>
Decision: <what was decided>
Why: <rationale>
Alternatives considered: <what else was considered and why it lost>
Status: active | superseded by <link/date>
```

## `do-and-dont.md`

Concrete, imperative rules distilled from experience on this project.
Grouped by area if it grows long (e.g. `## API`, `## Database`, `## Testing`).

```
- DO <specific instruction> - <why, one line>
- DON'T <specific instruction> - <why, one line>
```

These should be specific enough to act on directly ("Don't use `Date.now()`
for IDs, use the `uuid` lib - collisions observed under load") rather than
vague ("be careful with dates").

## `active-context.md`

The current working focus: what's being worked on right now, what changed
recently, what's next, and any open questions blocking progress. This file
reflects *now*, not history - overwrite stale sections instead of letting
them accumulate.

## `glossary.md`

Domain-specific terms, acronyms, and internal names used in this project
that wouldn't be obvious to someone (or an AI) new to it. One line each.

## General rules

- Every entry should be attributable and dated where relevant (decisions,
  active context) so staleness is visible.
- Prefer a few precise, high-signal entries over exhaustively logging
  everything - the goal is that future reads are fast, not complete.
- No secrets, credentials, customer PII, or anything that shouldn't be
  committed to version control.
