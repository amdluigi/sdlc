---
name: sdlc-change-contract
description: 'Use when always when enabled to establish the change contract.'
license: MIT
metadata:
  category: requirements
  version: "1.0.0"
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "change-contract"
---

# Change contract module

Goal: make sure you're solving the right problem before writing code, without
turning every request into an interrogation.

## 1. Restate the goal

In one or two sentences, state what you understood the user wants, including
the implicit "definition of done" (what changes, what must keep working).

## 2. Present a discovery brief for Significant changes

Before asking the first clarifying question for a Significant change in an
existing repository, inspect enough current evidence to present a concise
discovery brief:

- **Evidence inspected**: key files and documents, with what each established.
- **Existing decisions and patterns**: architecture, conventions, and similar
  behavior the change should preserve.
- **Integration points**: contracts, consumers, data flows, and operational
  surfaces likely to be affected.
- **Constraints and relevant debt**: only evidenced limitations that can
  shape the solution.
- **Facts, assumptions, and unknowns**: separate repository evidence from
  provisional interpretation.

Keep the brief proportional and visible to the developer. Do not turn it into
a repository tour or delay one genuinely blocking question to perform
unbounded research. Greenfield work replaces repository findings with known
constraints and explicit assumptions.

**Hard gate:** do not ask the first clarification question until the discovery
brief is visible. If the target repository or required evidence is
unavailable, say what could not be inspected and treat it as an unknown
instead of fabricating findings.

## 3. Define the change contract

Before coding, make these points explicit:

- **Outcome**: one observable improvement this change will deliver.
- **Acceptance criteria**: concrete behaviors or checks that prove the
  outcome.
- **Non-goals**: plausible adjacent work this change will not include.
- **PR boundary**: the product area, contract, or behavior included.
- **Minimum complete change**: the implementation, tests, docs, migrations,
  configuration, error handling, and compatibility work required to deliver
  that outcome safely.

For a user-facing or product-facing change, also identify:

- **Target user and benefit**: who receives the outcome and why it matters.
- **User stories or scenarios**: include them only when they clarify distinct
  behavior or permissions.
- **Success metrics**: include product or operational measures only when they
  define success or constrain the design. Acceptance tests remain mandatory.
- **Open decisions**: list unresolved choices separately. Resolve costly
  ambiguity before planning; low-cost assumptions must be explicit.

Do not convert ownership, sharing, authorization, retention, limits, billing,
or public-contract choices into "reasonable defaults" when they affect the
data model, security boundary, user experience, or compatibility. Keep them
as open decisions and ask one focused question at a time.

A focused change can cross API, UI, database, and documentation layers when
they are all required for the same outcome. Do not split by file count or
technical layer alone. Split when parts have independent value, different
acceptance criteria, or can be reviewed and delivered separately.

Example: adding account export may require API, UI, authorization, and tests
in one coherent change. A CSV dependency upgrade and unrelated log cleanup
are separate outcomes unless the export cannot be delivered safely without
them.

## 4. Classify the change

- **Trivial**: typo, formatting, rename, obvious one-line bugfix, no behavior
  ambiguity. Skip to implementation.
- **Standard**: new function/endpoint/component, bugfix with a non-obvious
  root cause, refactor touching a few files. Do a short analysis (below) and
  a short plan.
- **Significant**: new feature area, schema/API/auth changes, cross-cutting
  refactor, anything touching money, PII, permissions, or irreversible data
  operations. Do a full analysis, a written plan, and confirm risky
  assumptions with the user before implementing.

## 5. Impact analysis (Standard/Significant)

- Which files/modules/services are affected? Use search tools to find all
  call sites, not just the obvious one.
- What existing tests, contracts, or consumers (internal or external) could
  break?
- Are there data migrations, backward compatibility, or versioning concerns?
- Does this interact with authentication, authorization, or user-visible
  permissions?
- Are there performance, concurrency, or scaling implications?

## 6. When to ask vs. assume

Ask the user (one focused question at a time) only when:
- The ambiguity changes the shape of the solution (e.g., "should this be a
  hard limit or a soft warning?").
- The wrong assumption is expensive to undo (breaking change, data loss,
  security posture, spend).
- Multiple reasonable interpretations exist and the codebase/PROJECT-STANDARDS
  gives no signal.
- The request bundles independent outcomes and it is unclear which one has
  priority.

Otherwise, state the assumption explicitly in your response ("Assuming X
because Y") and proceed - don't block progress on low-stakes ambiguity.

Do not let urgency replace acceptance criteria. If "make a sensible
implementation" could produce materially different user-visible, data, auth,
or compatibility behavior, clarify before coding.

## 7. Check prior context

When selected, the project-memory module runs before this one. In that case,
check `.sdlc/memory/decisions-log.md` and
`.sdlc/memory/do-and-dont.md` for anything relevant before proposing a new
approach. Do not re-litigate settled decisions or repeat a rejected approach
without new evidence.

## Ready to plan

Proceed only when the outcome, acceptance criteria, non-goals, PR boundary,
and costly open decisions are clear enough that another engineer could tell
whether a proposed file or behavior belongs in the change.

If the PRD module trigger applies, hand this contract to that module. The
change contract alone does not authorize planning or implementation for a new
project or feature that requires a PRD.

Every applicable acceptance criterion from the change contract must map to a
numbered PRD `AC-*` item. A criterion can disappear only when the PRD records
it as deliberately superseded and the developer explicitly approves that
change. Do not create a second unconnected acceptance model.
