# SDLC 3.1 qualification results

This directory retains only schema-validated, sanitized qualification
summaries for release 3.1.0. It does not claim that any host result exists.

Create deterministic results with synthetic project and home roots. A
`check-install` result reports only checks performed while inspecting that
cell. Mode-inapplicable and suite-level cases remain `not-executed`; they
cannot be promoted to passes without separate, verifiable suite evidence.
Produce live results from locally reviewed blind-evaluator verdicts with
`scripts/qualify.py sanitize-live`. Raw prompts, responses, logs, project
content, paths, user or machine identifiers, model identifiers, timestamps,
and secrets remain under ignored `qualification/raw/` and are deleted after
review.

Review every summary and manifest hash diff before release. Every profile
requires a project-copy live baseline, and at least one additional live result
must use a manifest-supported link cell. The release gate checks completeness
and normalized verdicts; it does not replace human review of behavior quality.
