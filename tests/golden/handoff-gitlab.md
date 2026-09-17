# Add filtered search export

## Outcome
Users can export the active filtered result set.

## Product requirements
- PRD: `docs/prds/search-export.md` (`search-export`, declared version 2, status `approved`)
- Delivered functional requirements: `FR-1`, `FR-2`
- Delivered acceptance criteria: `AC-1`, `AC-2`

## Scope
- Export the active filtered result set.

## Non-goals and deferred work
- Scheduled exports remain out of scope.

## Acceptance evidence
| Criterion | Kind | Command | Result | Revision | Summary |
|---|---|---|---|---|---|
| `AC-1` | test | `python -m unittest tests.test_export` | `passed` | `abc123` | Filtered rows matched the export. |
| `AC-2` | test | `python -m unittest tests.test_export_errors` | `passed` | `abc123` | Failures returned actionable errors. |

## Review
- Perspectives: correctness, tests
- Findings resolved: Handled empty result sets.
- Unavailable perspectives: None.

## Compatibility
Not applicable: No public or persisted contract changed.

## Rollout
- Deploy with the ordinary application release.

## Rollback
- Revert the change and redeploy.

## Risks and limitations
- Risks: None known.
- Limitations: None known.

## Blockers
- None.

## Configured-disabled modules
- None.
