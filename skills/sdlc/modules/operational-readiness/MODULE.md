# Operational readiness module

Use this module when a change affects migrations, stored data, application
runtime or deployment configuration, infrastructure, public contracts,
feature flags, background processing, deployment sequencing, or other
production behavior. SDLC's own `.sdlc/config.json` does not trigger this
module.

- **Reversibility**: explain how code, configuration, schema, and data return
  to a safe state. If data cannot be reversed, define a tested mitigation
  rather than calling the change rollback-safe.
- **Compatibility sequence**: identify which old and new versions coexist
  during rollout and whether expand-and-contract or dual-read/write behavior
  is required.
- **Rollout**: choose an appropriate feature flag, canary, tenant cohort, or
  staged deployment when a full rollout would create unnecessary risk.
- **Operational signals**: define measurable success, failure, and rollback
  signals, where they are observed, and who or what acts on them.
- **Post-change validation**: list the checks that confirm production state,
  data integrity, and user-visible behavior after rollout.

A rollback paragraph is a plan, not evidence. Significant irreversible work
needs a dry run, restore test, rehearsal, or equivalent proof proportionate
to the risk.
