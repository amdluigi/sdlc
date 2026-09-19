<!--
Copy this file to the project root as PROJECT-STANDARDS.md and fill it in
once per project. When enabled, the project-standards module reads it before
other selected modules and defers to what this file specifies.
-->

# Project standards

## Stack

- Language(s)/runtime(s):
- Framework(s):
- Package manager:
- Key libraries to prefer (and any to avoid):

## Conventions

- Formatting/linting tool(s) and command(s):
- Naming conventions:
- Folder/module structure notes:
- Error handling conventions:

## Testing

- Test framework(s):
- Command(s) to run unit / integration / e2e tests:
- Minimum coverage expectations (if any):
- What must always have a test (e.g. all public endpoints, all bug fixes):

## Product requirements

- PRD location convention (default: `docs/prds/FEATURE_ID.md`):
- Additional changes that require a PRD:
- Product roles authorized to approve a PRD:
- Required product, compliance, or operational success measures:

## Security & compliance

- Auth mechanism (e.g. OAuth/OIDC, session cookies, API keys):
- Authorization model (roles, ACLs, multi-tenancy rules):
- Data sensitivity/compliance requirements (PII, GDPR, HIPAA, PCI, etc.):
- Secrets management approach:
- Anything explicitly out of scope for the AI to touch (infra, prod data,
  billing, etc.):

## Review & delivery

- PR/commit message conventions:
- PR template path (if any):
- Expected PR scope (one coherent outcome, maximum size, required split
  points):
- Required reviewer perspectives by risk or change type:
- Findings that block PR readiness:
- CI checks that must pass before merge:
- Required local verification before opening a PR:
- Anything else every change must satisfy:

## Rollout & operations

- Changes that require a feature flag, canary, or staged rollout:
- Backward/forward compatibility requirements:
- Rollback and restore-test expectations:
- Required dashboards, alerts, logs, or post-deployment checks:
- Owner or escalation path for failed rollout:
