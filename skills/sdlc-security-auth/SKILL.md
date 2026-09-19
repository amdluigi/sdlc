---
name: sdlc-security-auth
description: 'Use when external input, stored or sensitive data, network access, identity, permissions, secrets, dependencies, or user-visible output are affected.'
license: MIT
metadata:
  category: risk
  version: "1.0.0"
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "security-auth"
---

# Security, authentication & authorization checklist

Run the items relevant to what the change actually touches - not every item
applies to every task, but check whether each *category* applies before
skipping it.

## Input handling & injection

- Are all external inputs (user input, query params, headers, file uploads,
  webhooks, third-party API responses) validated and sanitized?
- Any risk of SQL/NoSQL injection, command injection, path traversal, SSRF,
  XSS, or template injection introduced or left unaddressed?
- Are outputs properly encoded/escaped for their context (HTML, SQL, shell,
  URL)?

## Authentication

- Does this change touch login, session, token issuance/validation, or
  password/credential handling?
- Are sessions/tokens generated securely, stored safely, and expired/revoked
  appropriately?
- Is sensitive data (passwords, tokens, secrets) hashed/encrypted at rest and
  never logged in plaintext?

## Authorization

- Does every new/changed endpoint, function, or UI action check that the
  *current* user is allowed to perform it (not just that they are logged
  in)?
- Object-level checks: can a user access/modify another user's data by
  changing an ID/parameter (IDOR)? Verify ownership/tenant checks are
  present.
- Are role/permission checks enforced server-side, not just hidden in the
  client/UI?

## Secrets & configuration

- No secrets, API keys, credentials, or tokens committed to source control or
  hardcoded - use the project's existing secrets/config mechanism.
- Are new dependencies from trusted sources, pinned appropriately, and free
  of known critical vulnerabilities (check lockfile/advisory tooling if
  available)?

## Data protection

- Is PII/sensitive data minimized, and handled per any stated compliance
  requirements in `PROJECT-STANDARDS.md`?
- Are error messages/logs free of sensitive data leakage (stack traces,
  secrets, PII) in responses seen by end users?

## Transport & infra (when relevant)

- HTTPS/TLS enforced where applicable; no plaintext transmission of
  sensitive data.
- Rate limiting/abuse protection considered for new public endpoints.

## Definition of done for this phase

- Applicable items above were checked (not blindly all, but the ones this
  change actually touches).
- Any accepted risk that wasn't fully mitigated is called out explicitly to
  the user, not silently shipped.
