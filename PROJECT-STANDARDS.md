# Project standards

## Stack and conventions

- Keep the distributable skill bundle portable and use Python's standard
  library for runtime helpers.
- Keep optional host integrations isolated in their existing packages and use
  their host APIs and built-in dependencies.
- Preserve strict, versioned JSON contracts and explicit manager authority.
- Keep public prose independently understandable and avoid em dashes.

## Verification

- Python behavior: run focused `python -m unittest` selectors, then
  `python -m unittest` for broad changes.
- Dashboard behavior: run `npm --prefix packages/sdlc-dashboard test` and
  `npm --prefix packages/sdlc-dashboard run check`.
- Repository: run `python scripts/validate.py` and the relevant artifact,
  manifest, or qualification validators.
- Do not claim tests or live-host capabilities that were not directly run.

## Safety and compatibility

- Preserve default-disabled behavior and prior versioned records.
- Keep the execution manager as the sole writer and independent acceptance
  authority; never treat worker output as approval.
- Do not retain prompts, transcripts, secrets, or raw command output in
  execution records.
- Do not add a runtime dependency without a separately reviewed decision.
- Use a focused branch and normal pull request workflow; do not merge or
  release without explicit authorization.

## Rollout and review

- Keep new orchestration behavior opt-in and fail closed on stale bindings,
  invalid records, unsupported host capabilities, or ownership conflicts.
- Review contracts, failure handling, accessibility, compatibility, and
  rollback proportionate to the changed surfaces.
