# SDLC delivery profile

Generated file. Do not edit by hand.

Each row states which plugin serves a capability and where that plugin
came from. A capability is an interface and its plugin is the
implementation bound to it. Implementations the bundle ships are named
after the capability they serve, so `sdlc-testing` is the bundled
implementation of `testing`.

A phase heading shows its entry gate: the earliest lifecycle gate at
which any of its capabilities participates. It is not a per-phase
identifier, so one gate can open two phases and a gate that opens no
phase does not appear. A phase without an entry gate lies outside the
per-change state machine and carries no blocking authority.

To change a plugin, edit the project configuration, then regenerate:

```
python skills/sdlc/scripts/delivery_profile.py render \
  --registry skills/sdlc/modules/registry.json \
  --output docs/DELIVERY-PROFILE.md
```

## inception (no entry gate)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| project-memory | sdlc-project-memory | bundled | default | yes |
| project-standards | sdlc-project-standards | bundled | default | yes |
| prd | sdlc-prd | bundled | default | yes |
| planning | sdlc-planning | bundled | default | yes |

## triage (entry gate 1)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| change-contract | sdlc-change-contract | bundled | default | yes |
| debugging | sdlc-debugging | bundled | default | yes |

## design (entry gate 2)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| accessibility-browser | sdlc-accessibility-browser | bundled | default | yes |
| performance-concurrency | sdlc-performance-concurrency | bundled | default | yes |
| observability | sdlc-observability | bundled | default | yes |
| api-compatibility | sdlc-api-compatibility | bundled | default | yes |
| data-migration | sdlc-data-migration | bundled | default | yes |
| dependency-supply-chain | sdlc-dependency-supply-chain | bundled | default | yes |
| security-auth | sdlc-security-auth | bundled | default | yes |

## implementation (entry gate 3)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| tdd | sdlc-tdd | bundled | default | yes |
| implementation | sdlc-implementation | bundled | default | yes |

## verification (entry gate 5)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| testing | sdlc-testing | bundled | default | yes |
| operational-readiness | sdlc-operational-readiness | bundled | default | yes |
| review | sdlc-review | bundled | default | yes |

## delivery (entry gate 5)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| release-launch | sdlc-release-launch | bundled | default | yes |
| pr-handoff | sdlc-pr-handoff | bundled | default | yes |

## operate (no entry gate)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| incident-response | sdlc-incident-response | bundled | default | yes |
| continuous-improvement | sdlc-continuous-improvement | bundled | default | yes |
