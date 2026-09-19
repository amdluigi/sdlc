---
name: sdlc-debugging
description: "Use when a bug or unexplained failure is in scope."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "debugging"
---

# Debugging module

Use this module for non-trivial bug fixes. Do not treat the user's suggested
patch or the first plausible explanation as the root cause.

1. Reproduce the failure with the smallest deterministic case available. If
   it is intermittent, gather logs, traces, state, or timing evidence instead
   of guessing.
2. Localize where actual behavior first diverges from expected behavior, then
   trace backward to the originating condition.
3. State one falsifiable root-cause hypothesis and run the smallest test that
   can disprove it. Change one variable at a time.
4. Establish a failing regression test or deterministic reproduction before
   implementing the fix when technically feasible.
5. Apply the smallest fix at the root cause, not a collection of defensive
   changes around the symptom.
6. Verify the original failure, surrounding behavior, and realistic failure
   paths.

When active harm requires immediate containment, keep containment reversible
and label it as mitigation, not proof of root cause. Continue diagnosis
before presenting the permanent fix as complete.

Load specialist debugging guidance when the failure is nondeterministic,
distributed, concurrency-related, environment-specific, performance-related,
or persists after two disproven hypotheses.
