# SDLC delivery profile

Generated file. Do not edit by hand.

Each row states which plugin serves a capability and where that plugin
came from. A phase without a gate lies outside the per-change state
machine and carries no blocking authority.

To change a plugin, edit the project configuration, then regenerate:

```
python skills/sdlc/scripts/delivery_profile.py render \
  --registry skills/sdlc/modules/registry.json \
  --output docs/DELIVERY-PROFILE.md
```

## inception (no gate)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| project-memory | sdlc | bundled | default | yes |
| project-standards | sdlc | bundled | default | yes |
| prd | sdlc | bundled | default | yes |
| planning | sdlc | bundled | default | yes |

## triage (gate 1)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| change-contract | sdlc | bundled | default | yes |
| debugging | sdlc | bundled | default | yes |

## design (gate 2)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| accessibility-browser | sdlc | bundled | default | yes |
| performance-concurrency | sdlc | bundled | default | yes |
| observability | sdlc | bundled | default | yes |
| api-compatibility | sdlc | bundled | default | yes |
| data-migration | sdlc | bundled | default | yes |
| dependency-supply-chain | sdlc | bundled | default | yes |
| security-auth | sdlc | bundled | default | yes |

## implementation (gate 3)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| tdd | sdlc | bundled | default | yes |
| implementation | sdlc | bundled | default | yes |

## verification (gate 5)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| testing | sdlc | bundled | default | yes |
| operational-readiness | sdlc | bundled | default | yes |
| review | sdlc | bundled | default | yes |

## delivery (gate 5)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| release-launch | sdlc | bundled | default | yes |
| pr-handoff | sdlc | bundled | default | yes |

## operate (no gate)

| Capability | Plugin | Source | Role | Enabled |
|---|---|---|---|---|
| incident-response | sdlc | bundled | default | yes |
| continuous-improvement | sdlc | bundled | default | yes |
