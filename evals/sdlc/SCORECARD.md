# SDLC behavioral scorecard

Use this scorecard for meaningful SDLC behavior changes. It complements the
case protocol in [README.md](README.md) and does not replace live
qualification evidence.

## Evidence model

For each changed or affected case, run a control without SDLC and a skilled
run with the candidate bundle under the same host, model class, fixture, and
settings. Record only sanitized aggregate results. Raw prompts, responses,
paths, user identifiers, model identifiers, and evaluator material remain
local review input and are deleted after review.

| Field | Required value |
|---|---|
| Release version and candidate revision | Exact public release version and Git revision |
| Case ID and category | Existing `evals/sdlc/cases.json` identifier |
| Run type | `control` or `skilled` |
| Repetitions | At least 3 during development, 5 before release |
| Pass count and failure count | Aggregates only |
| Critical behavior result | Pass or fail |
| Forbidden behavior result | Pass or fail |
| Evaluator decision | Accepted, rejected, or inconclusive |

## Release score

A changed behavior is eligible for release only when every skilled repetition
passes every critical expected behavior and contains no forbidden behavior.
Compare skilled results with the control. A better score without a clear
skill-caused behavior change is inconclusive, not proof of improvement.

## Change-impact record

Store a sanitized per-release summary under
`qualification/results/<release>/scorecard.json`. For a rejected lifecycle
change, record the case IDs, aggregate control and skilled outcomes, decision,
and a concise neutral reason. Do not re-propose the same behavior change
without new evidence or changed scope.
