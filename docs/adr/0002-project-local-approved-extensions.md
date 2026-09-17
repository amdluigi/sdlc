---
status: accepted
---

# Learn through project-local approved extensions

Recurring process gaps become project-owned extension candidates rather than
mutations to the globally installed skill. Explicit approval, validation, and
project configuration are required before activation, preserving repository
trust boundaries and keeping core updates replaceable.

## Considered Options

- Modify the global installed skill automatically.
- Maintain a private fork for every learned behavior.
- Store reviewable overlays with the project.

## Consequences

Learning is scoped to the repository where it occurred. Promotion to a global
catalog only makes an extension available, and every project must opt in
separately. Upstream contribution remains an explicit sanitized workflow.
