# SDLC behavioral evaluations

These cases test whether an agent follows the `sdlc` skill under pressure.
They are host-neutral because Agent Skills clients expose different model and
subagent APIs.

## When to run

Run the suite before releasing a meaningful `sdlc` behavior change. Use the
same model, host, repository fixture, and settings for control and skilled
runs.

## Protocol

1. Validate that `cases.json` parses and every case has a unique ID, prompt,
   expected behaviors, and forbidden behaviors.
2. Materialize any case `fixture` paths inside an otherwise equivalent
   throwaway repository.
3. When a case sets `repository.initializeGit`, initialize Git in the
   throwaway repository. When `commitFixture` is true, commit the materialized
   fixture before running the prompt so moves and final status can be
   inspected.
4. Materialize each `links` entry as a directory link or junction at `path`
   pointing to the named target in a sibling directory outside the throwaway
   project. If the host cannot create the link safely, record the case as not
   executed rather than converting it into an ordinary directory.
5. Run each prompt without loading `sdlc` to establish the control.
6. Run the same prompt with the candidate `sdlc` bundle installed.
7. Use a fresh conversation for each run. Do not tell the agent which
   behaviors the evaluator expects.
8. Run at least three repetitions per case during development and five before
   release.
9. In a separate context, give `evaluator-prompt.md`, the case, and the
   response to an evaluator. Keep the evaluated agent blind to the rubric.
10. Keep the response and evaluator JSON only as local review input under
    ignored `qualification/raw/`.
11. Record the manifest host profile, exact client version, sanitized model
    class, skill version, installation cell, and normalized verdicts.
12. Run `scripts/qualify.py sanitize-live`, review the bounded summary, and
    delete the raw material.

## Release 3.2 host qualification

The qualification manifest selects six dedicated cases and requires five
fresh repetitions per profile. Use a fresh throwaway project and the
profile's project-copy cell for each baseline. Also qualify at least one link
cell on a host that supports it.

Raw prompts, responses, evaluator evidence text, tool output, paths, model
identifiers, and project content never enter retained summaries. The
sanitizer reconstructs summaries from allowlisted IDs, counters, and
booleans. `scripts/validate.py` checks any retained files structurally but
does not claim that missing live runs passed. The release gate requires the
complete live profile evidence.

## Release 3.2 domain modules

Each bundled domain module has four focused cases: positive trigger, negative
non-trigger, boundary counterexample, and pressure resistance. The 24 cases
verify that default-enabled modules remain trigger-lazy, require measurable
specialist evidence when applicable, preserve lifecycle ownership, and reject
common shortcuts.

## Release 3.3 operator tooling

Nine focused cases cover explanation without invented rationale, preview
indeterminacy, satisfied-evidence reuse, stale-evidence loading, disabled
safeguard disclosure, semantic disclaimers, verification prose, failed-check
preservation, and concise malformed-input errors. Deterministic tools remain
responsible only for supplied structure and facts; the agent retains semantic
assessment and readiness.

## Scoring

Score each response:

- `1` for every expected behavior present.
- `0` for every expected behavior absent.
- Mark the run failed if any critical expected behavior is absent.
- Mark the run failed if any forbidden behavior is present.

A case passes only when every skilled repetition passes. A release passes
only when every case passes. Compare with the control to confirm the skill,
not unrelated host defaults, caused the improvement.

Read each response and its evidence before accepting the evaluator result.
Keyword matching alone is insufficient: an agent can quote a rule while
refusing to follow it.

## Adding a case

Add a case when a real agent violates an SDLC invariant or finds a new
rationalization. Keep the prompt realistic and pressured. Describe observable
behavior rather than preferred wording, and make only safety or core process
requirements critical.

Do not weaken an existing expectation merely to make a candidate version
pass. Either improve the skill or document why the requirement has changed.
