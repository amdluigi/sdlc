---
name: sdlc-project-standards
description: 'Use when always when enabled.'
license: MIT
metadata:
  category: context
  version: "1.0.0"
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "project-standards"
---

# Project standards module

Before planning or implementation, look for `PROJECT-STANDARDS.md` at the
project root, `.agents/PROJECT-STANDARDS.md`, or
`docs/PROJECT-STANDARDS.md`.

- If it exists, read it and treat it as the source of truth for stack,
  conventions, test commands, security/compliance, review, and rollout
  policy. Other modules fill only its gaps.
- If it does not exist, propose creating one from
  [assets/PROJECT-STANDARDS.template.md](assets/PROJECT-STANDARDS.template.md).
  Infer what is safe from manifests, CI, linters, tests, and existing code,
  then ask the user to confirm unknown project policy once.
- For trivial low-risk work, infer applicable conventions and defer creating
  the standards file so setup does not expand the change.
- Skip the proposal only for work explicitly framed as scratch or throwaway.

Project standards customize selected modules but do not control module
activation. `.sdlc/config.json` is the only activation source.
