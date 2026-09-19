# Project memory module

Project decisions and constraints must survive across conversations, models,
and tools. Apply this module whenever the orchestrator selects it.

## Canonical location

Committed project memory lives at `.sdlc/memory/`.

Before reading or writing memory, inspect both the canonical
`.sdlc/memory/` path and the legacy root `project-memory/` path:

| Canonical | Legacy | Action |
|-----------|--------|--------|
| absent | absent | Bootstrap `.sdlc/memory/` for a non-trivial task; defer for trivial work |
| present | absent | Use `.sdlc/memory/` |
| absent | present | For non-trivial work, move the complete directory to `.sdlc/memory/`, verify it, report the migration, then read it; for trivial work, read legacy memory and defer the move |
| present | present | Stop before planning and ask the developer to reconcile the conflict |

Never merge, overwrite, or delete two memory stores automatically. If either
location is a symbolic link, junction, or reparse point, stop and report it
instead of following it.

For a legacy-only non-trivial project, preserve every file and source-control
history. Prefer a source-control-aware move when the files are tracked. Verify
that the canonical store contains the complete original contents and the
legacy path is absent before continuing.

## Bootstrap

- If neither location exists and the task is non-trivial, create
  `.sdlc/memory/` from
  [assets/project-memory-templates/](assets/project-memory-templates/), then
  fill `project-brief.md` and `architecture.md` from observable repository
  evidence. Mark genuinely unknown details clearly and tell the user what was
  created.
- If neither location exists and the task is trivial, defer scaffolding until the
  first non-trivial task.

Never store secrets, credentials, tokens, raw sensitive data, or customer PII
in project memory.

## Read before work

- Always skim `.sdlc/memory/active-context.md` and
  `.sdlc/memory/do-and-dont.md` before non-trivial work.
- Read `.sdlc/memory/decisions-log.md` and
  `.sdlc/memory/architecture.md` before design or architecture decisions and
  when the current system is unclear.
- Read `.sdlc/memory/glossary.md` when domain terminology is unfamiliar.
- Treat active decisions and concrete do/don't rules as binding context. Flag
  conflicts before contradicting them.

See [REFERENCE.md](REFERENCE.md) for the file schema.

## Write when knowledge changes

- Record non-obvious decisions, rationale, and rejected alternatives in
  `.sdlc/memory/decisions-log.md`.
- Record discovered constraints, gotchas, and user corrections as concrete
  rules in `.sdlc/memory/do-and-dont.md`.
- Update `.sdlc/memory/architecture.md` when components, dependencies, data flow, or
  established patterns change.
- Replace stale task focus in `.sdlc/memory/active-context.md` when work
  completes or the focus shifts.
- Add new domain terms to `.sdlc/memory/glossary.md`.

Keep entries short, dated where relevant, and high-signal. Do not turn memory
into a changelog of routine mechanical edits.

## Maintain and delegate

Consolidate stale or duplicate entries when files become difficult to scan.
Mark reversed decisions as superseded with a reason instead of deleting their
history.

When delegating, pass the project-memory path and require the delegate to read
the relevant files. The orchestrator remains responsible for reconciling and
recording returned decisions.
