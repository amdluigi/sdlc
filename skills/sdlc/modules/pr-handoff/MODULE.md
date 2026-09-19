# Final diff and PR handoff

Goal: make the completed change easy for a human reviewer to understand
without reconstructing its purpose from code.

## 1. Inspect the final repository state

Before calling a change PR-ready:

- Check repository status, including untracked files.
- Inspect the complete diff against the intended base, plus any staged or
  unstaged changes not represented there.
- Confirm every changed file is necessary for the coherent outcome.
- Confirm no required implementation, test, documentation, migration,
  configuration, generated file, or lockfile change is missing.
- Remove accidental formatting, debug output, temporary files, secrets, and
  unrelated cleanup.
- Re-check the diff after resolving review findings.

If unrelated pre-existing changes share the worktree, distinguish them
explicitly. Do not revert work you do not own, and do not represent it as part
of the proposed PR.

## 2. Prepare the handoff

Use `contracts/handoff.schema.json` as the forge-neutral source model when a
machine-checkable packet is needed. Validate it locally before presenting the
human-readable handoff:

```text
python PATH_TO_SDLC/scripts/validate_artifacts.py validate-handoff HANDOFF.json --project-root PROJECT_ROOT
```

The command checks supplied fields and can cross-check an explicitly
referenced local PRD. It does not inspect git, run tests, load modules, infer
risk, render forge text, write output files, or make the readiness decision.
Its `semanticApproval: not-assessed` result is structural evidence only.

After validation succeeds, render the same normalized packet locally:

```text
python PATH_TO_SDLC/scripts/validate_artifacts.py render-handoff HANDOFF.json --forge github
```

Select `github`, `gitlab`, or `azure-devops`. Output is Markdown on stdout
unless an explicit local `--output` path is supplied. Use `--template` only
for a template chosen explicitly by the user or repository workflow. The
renderer copies template text literally and never discovers templates,
remotes, credentials, or forge configuration.

Rendering is not publication. Any later action to authenticate, push,
publish, open, update, approve, or merge a request must be a separate,
explicit user action outside this deterministic helper.

Use the repository's PR template when one exists. Otherwise provide this
compact structure:

```markdown
## Outcome
[One observable improvement delivered by this PR.]

## Product requirements
- PRD: [authoritative artifact, reconciliation report when used, stable ID,
  and approved version, or "Not applicable"]
- Requirements delivered: [FR and AC identifiers]

## Scope
- [Minimum complete implementation.]

## Non-goals and deferred work
- [Related work intentionally excluded or proposed separately.]

## Acceptance evidence
| Criterion | Evidence |
|-----------|----------|
| [Expected behavior] | [Test or verification command and result] |

## Review
- Perspectives: [correctness, tests, security, compatibility, etc.]
- Findings resolved: [summary]
- Independent review unavailable: [state only when applicable]

## Compatibility, rollout and rollback
- [Compatibility constraints, rollout plan, rollback or mitigation, and
  post-change validation. Write "Not applicable" with a reason when none
  applies.]

## Risks and limitations
- [Unresolved risk, accepted limitation, or "None known."]
```

The PR title should describe the single outcome in imperative language. Keep
the handoff concise, but never omit failed checks, unavailable review,
irreversible effects, or known risk.

## 3. Readiness decision

State `PR-ready` only when the complete SDLC gate passes. Otherwise state
`blocked`, name the missing evidence or decision, and do not use
success-shaped language.
