---
name: sdlc-accessibility-browser
description: "Use when a change creates or modifies rendered web or mobile UI, user interaction behavior, responsive layout, navigation or focus behavior, accessibility semantics, or browser-only runtime behavior."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "accessibility-browser"
---

# Accessibility and browser module

## Bounded responsibility

Use this module to assure that changed rendered web or mobile behavior works
through its actual browser or app runtime, remains operable with relevant
assistive input, and has deliberate responsive, focus, semantic, and
interaction states. It owns specialist accessibility and runtime-flow
evidence, not general visual design or all end-to-end testing.

## Positive trigger

Load this module when a change creates or modifies rendered web or mobile UI,
user interaction behavior, responsive layout, navigation or focus behavior,
accessibility semantics, or browser-only runtime behavior.

Evaluate the accepted scope and changed surfaces. The mere existence of a
frontend does not trigger this module.

## Non-trigger counterexamples

- A backend-only response optimization leaves rendered behavior unchanged.
- A database migration has no user interface change.
- A README screenshot or prose-only change does not alter a shipped interface.
- A server-rendered email changes without a web, mobile, or browser flow.
- A UI is only an unchanged consumer of a compatible internal service change.

## Evidence contract

1. Map changed acceptance criteria to affected pages, screens, interaction
   states, viewport classes, and relevant input modes.
2. Exercise applicable loading, empty, error, disabled, validation, and
   success states through the real rendered interface.
3. Provide current automated accessibility results and manual evidence for
   applicable keyboard or switch navigation, focus order and restoration,
   accessible names, announcements, zoom or reflow, and reduced motion.
4. Name tested viewport classes and record overflow, clipping, target size,
   orientation, and content-reflow outcomes.
5. Record each finding's severity, affected flow, reproduction, and
   disposition. Carry accepted limitations into final risk and handoff
   evidence.

Evidence must be inspectable, scope-aligned, and current for the contract and
implementation revision. Reuse qualifying evidence regardless of producer.

## Overlap rules

- Change contract and PRD own users, promises, and acceptance criteria. This
  module identifies specialist criteria; it does not invent requirements.
- Planning owns overall sequencing. This module supplies the affected-flow
  and accessibility matrix.
- TDD owns red-before-green order. A browser or accessibility assertion may
  provide TDD evidence, but this module does not certify implementation order.
- Implementation owns UI code and verified slices.
- Testing owns final acceptance coverage. It references rather than repeats
  current browser, assistive-input, and responsive evidence from this module.
- Security-auth owns threats such as XSS, authorization, and sensitive
  display. This module owns perceivability and operability.
- Operational readiness owns rollout and production signals. This module owns
  pre-release runtime-flow qualification.
- Review selects the accessibility and UX perspective and triages findings;
  it does not rerun current evidence without a freshness reason.

## Right-sizing

- For one local semantic or focus change, test the affected flow, relevant
  state, input mode, and viewport rather than auditing the whole product.
- For a multi-screen or navigation change, expand the matrix to every changed
  journey and shared component state.
- Use repository accessibility standards and existing browser or mobile test
  infrastructure. Do not add a second framework solely for this module.

## Steps

1. Identify changed journeys, rendered surfaces, and runtime boundaries.
2. Derive a proportional matrix for viewport, input, focus/navigation, state,
   and reduced motion where relevant.
3. Follow established component semantics before adding a new pattern.
4. Implement only the semantic, name, relationship, focus, announcement,
   contrast, reflow, target-size, and motion changes required by the contract.
5. Exercise the real rendered flow with existing infrastructure.
6. Run targeted automated checks, then perform manual checks automation cannot
   establish.
7. Record evidence by acceptance criterion. Mark it stale after relevant UI,
   CSS, routing, content, or component changes.

## Exit

This module is satisfied when every affected flow has current browser or
app-runtime evidence at relevant viewport and input modes, applicable
accessibility checks pass, and unresolved usability or accessibility
limitations are explicit.

## Common shortcuts to reject

- A component unit test or screenshot is treated as complete runtime evidence.
- One happy-path desktop run substitutes for keyboard, focus, state, and
  responsive checks.
- Unrelated existing pages are audited because the repository has a frontend.
- All accessibility work is deferred without recording missing evidence.

## Behavioral cases

| Case ID | Type | Observable expectation |
|---|---|---|
| `a11y-browser-dialog-flow-positive` | positive | A new modal flow triggers semantics, focus, close and restoration, error announcement, and narrow-viewport evidence. |
| `a11y-browser-backend-only-negative` | negative | A compatible backend-only refactor does not load this module merely because a web client exists. |
| `a11y-browser-email-counterexample` | counterexample | A prose-only transactional email change remains outside this module unless it changes a web or mobile flow. |
| `a11y-browser-release-pressure` | pressure | A desktop-only success under release pressure does not satisfy the module without proportional keyboard, focus, state, automated, and responsive evidence. |
