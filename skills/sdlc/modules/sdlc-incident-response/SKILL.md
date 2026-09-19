---
name: sdlc-incident-response
description: "Use when an active production incident, material service degradation, security event, or customer-impacting data integrity failure requires containment, recovery, or a post-incident follow-up."
metadata:
  sdlc-provider-schema: "1"
  sdlc-compatible: ">=1.0.0 <2.0.0"
  sdlc-modules: "incident-response"
---

# Incident response module

## Bounded responsibility

Use this module only for an active production incident or after containment
when production harm, a material service degradation, a security event, or a
customer-impacting data integrity failure is in scope. It owns incident
containment, coordination, evidence preservation, recovery validation, and
follow-up tracking. Debugging owns root-cause analysis. Operational readiness
owns planned change rollout.

## Positive trigger

Trigger when current production impact requires mitigation, rollback,
communication, recovery, or a formal post-incident record.

## Non-trigger counterexamples

Do not trigger for a development-only test failure, a routine code review
finding, a planned release with no incident, or a historical incident that is
not being investigated or followed up.

## Evidence contract

- Record incident scope, affected users or services, severity, owner, and the
  observed impact without exposing secrets or unnecessary personal data.
- Prefer reversible containment. Distinguish containment, mitigation, and a
  permanent fix. Do not present mitigation as root-cause proof.
- Preserve relevant timestamps, configuration, deployment, diagnostic, and
  decision evidence before destructive repair where safe.
- Define recovery checks, monitoring window, and an explicit recovery
  decision. Escalate when impact or ownership is unknown.
- Produce a blameless post-incident record with timeline, contributing
  conditions, confirmed and unconfirmed causes, and owned corrective actions.

## Overlap rules

Run debugging for root cause. Run security-auth for security, identity, data,
or abuse impact. Run observability when diagnostic signals are absent or
unsafe. Run release-launch for a hotfix release. Do not delay reversible
containment for a complete root-cause analysis.

## Right-sizing

Minor, fully contained incidents need a concise timeline, recovery evidence,
and tracked corrective action. Material incidents require explicit incident
ownership, impact updates, recovery criteria, and a post-incident review.

## Steps

1. Establish impact, severity, owner, and immediate safety constraints.
2. Choose and record the least-risky reversible containment or mitigation.
3. Preserve diagnostic evidence and communicate only verified impact.
4. Validate recovery against defined signals and monitor for recurrence.
5. Hand root-cause work to debugging and record corrective actions with
   owners and completion evidence.

## Exit

Containment or recovery is verified by current evidence, remaining impact and
risk are explicit, root-cause status is honest, and follow-up actions have
owners and observable completion criteria.

## Common shortcuts to reject

- Blaming an individual instead of identifying system conditions.
- Calling a rollback complete without recovery checks.
- Deleting evidence before it is preserved.
- Treating an untested hotfix as a recovery decision.

## Behavioral cases

| Case | Type | Required behavior |
|---|---|---|
| `incident-active-harm-positive` | positive | Classify impact, contain safely, preserve evidence, and verify recovery. |
| `incident-development-bug-negative` | negative | Use debugging, not incident response, for a local development failure. |
| `incident-containment-counterexample` | counterexample | Label a reversible mitigation separately from root cause and permanent repair. |
| `incident-blameless-pressure` | pressure | Preserve blameless analysis and communication discipline under deadline pressure. |
