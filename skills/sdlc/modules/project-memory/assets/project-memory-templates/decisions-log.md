# Decisions log

<!--
One entry per decision, newest at the bottom or top (pick one convention and
stay consistent). Example:

## 2025-01-15 - Use Postgres row-level security for multi-tenancy
Decision: Enforce tenant isolation via Postgres RLS policies instead of
  application-level filtering.
Why: Removes an entire class of "forgot the WHERE tenant_id" bugs.
Alternatives considered: App-level filtering only (rejected: error-prone),
  separate DB per tenant (rejected: too much ops overhead at current scale).
Status: active
-->
