# SDLC development flow

These diagrams explain the development process managed by the SDLC skill.
They separate the lifecycle, evidence gate, and risk scaling so each image
answers one question.

## 1. What is the overall development process?

![Five steps: understand, plan, build, verify, and handoff. Verification can return the process to understanding when evidence changes.](./images/sdlc-development-flow/01-development-lifecycle.svg)

The SDLC skill guides one coherent change through five understandable phases.
It can return to an earlier phase when scope, implementation, or evidence
changes.

## 2. Why does the skill sometimes run different checks?

![For each module, the skill checks whether it applies, whether it is enabled, and whether current evidence exists. It fills only evidence gaps and finishes when all applicable gates pass.](./images/sdlc-development-flow/02-evidence-gate.svg)

The skill evaluates modules lazily. It skips modules that do not apply,
discloses modules disabled by project configuration, reuses current evidence,
and performs only unresolved work.

## 3. How much process does a change receive?

![Trivial changes receive a small contract, focused check, review, and handoff. Standard and significant changes add progressively stronger planning, tests, risk checks, and review.](./images/sdlc-development-flow/03-risk-scaling.svg)

The process is proportional to risk. A typo does not receive the same ceremony
as an authentication or data migration change, but both must provide enough
evidence for the risks they introduce.

## Source and maintenance

The module order, triggers, and evidence contracts are defined by
[`skills/sdlc/modules/registry.json`](../skills/sdlc/modules/registry.json).
These diagrams are explanatory views, not an authoritative replacement for
that registry.

Keep each diagram:

- focused on one question;
- readable without zoom at typical documentation width;
- understandable without relying on color alone;
- accessible through an SVG title, description, and descriptive Markdown alt
  text;
- aligned with the current module registry.
