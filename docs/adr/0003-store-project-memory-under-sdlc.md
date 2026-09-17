---
status: accepted
---

# Store project memory under the SDLC metadata directory

Committed project memory lives at `.sdlc/memory/` instead of a root
`project-memory/` directory. Keeping configuration, learning state,
extensions, contributions, and memory under one `.sdlc/` namespace makes
ownership clear and avoids mixing agent delivery metadata with application
source directories.

## Considered Options

- Keep `project-memory/` at the project root.
- Store memory under `.sdlc/project-memory/`.
- Store memory under `.sdlc/memory/`.
- Store memory under `docs/`.

## Consequences

Legacy-only projects migrate their directory intact on the first non-trivial
task. Projects containing both legacy and canonical stores stop for manual
reconciliation. The six-file memory schema remains unchanged.
