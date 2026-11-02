# Optional SDK-free bounded worker

This experimental VS Code extension owns a small native Language Model API
loop. It is not the read-only dashboard, the old native bookkeeping helper,
or a full-roadmap completion claim. Nothing installs, activates or calls a
model automatically. No dependencies, SDK, network client or global settings
are added. Start with the independently usable
[manual tryout](../../docs/EXECUTION-TRYOUT.md).

## Run from the public source checkout

Requirements: VS Code 1.95 or newer with a native chat model available,
Node 20 or newer for offline tests, and an installed Python 3 executable
named `python` on the extension host's PATH. Keep this package in the public
checkout: its bridge is fixed to
`skills/sdlc/scripts/manage_runtime.py` in that same checkout. Copying just
this folder or shipping it as a standalone VSIX is not supported.

Open a **separate local target project**, not the trusted extension/helper
source, in an Extension Development Host:

```powershell
code --new-window --extensionDevelopmentPath "$SdlcCheckout\packages\sdlc-runtime" "$TargetProject"
```

In the target project, explicitly install native profiles, enable execution,
import and approve a plan using the existing manager/native CLI. These steps
are separate from starting this extension. The selected source plan must
exist and its SHA-256 must match the imported plan's `sourcePlan.digest`.
Create a current bound task brief with exact owned files and guidance.
Supported actions are only `read`, `search` and `edit`. Remove `execute`
from a brief deliberately; do not silently downgrade an approved brief.
Explicit task model/modelProfile assignments remain unsupported by the old
native request path. Use `model: null` and `modelProfile: "host-default"`;
the picker is a separate per-run user choice, not effective-routing proof.

Run **SDLC: Run Bounded Worker** explicitly. Select the local project,
brief, matching role, and one model from `vscode.lm.selectChatModels`.
The modal confirmation shows the exact native request digest and a separate
runtime digest binding selected model metadata, bounds and control state.
Authorize only after checking the project, files and provider/model.
VS Code/provider consent can additionally be required by the host.
Choosing a model alone does not dispatch. Dismissing any prompt starts
nothing. This development task did not authorize or perform inference.

The default per-run allowance is 8 iterations, 16 tool calls, 128 KiB
cumulative input, 128 KiB cumulative output and a 120-second local lease.
Portable hard ceilings are 16 iterations, 32 tool calls, 256 KiB input and
output, and 300 seconds. Files are bounded to 64 KiB. Input accounting
includes every full submitted protocol/context/history prompt and every
tool argument; output includes streamed model text and tool results.
These byte limits are **not token, billing or monetary caps**.

## Supported tools and authority

- Read and literal line search: only exact brief ownership/guidance paths.
- Edit: full UTF-8 LF replacement of one exact owned file, using the digest
  from a previous read as compare-and-swap protection. New files require an
  existing parent. Atomic same-directory staging preserves existing file
  mode and is cleaned on normal failure; interrupted staging requires
  inspection. No automatic retry or rollback is attempted.
- Execute: **unsupported**. No worker-selected shell, executable, argv,
  subprocess, network tool, agent, or manager operation exists. An exact
  executable/argv allowlist and qualified process-tree termination would
  need a separately approved implementation before execute can be enabled.

Every model iteration, observation, tool and receipt crosses the real fixed
Python CLI. It rechecks current manager approval, consent generation,
profile/source/guidance digests, exact native attempt, root, control bindings,
and wall-time lease. Edits and manager writes use the same serial writer.
Reparse/symlink paths, hardlinked files, aliases, source/guidance ownership,
manager controls and trusted implementation paths are refused.
This is a cooperative same-user boundary, **not an OS sandbox**.

Enabled manual controls remain incompatible with native dispatch. The
runtime refuses them without changing them. Do not disable existing
safeguards just to run it. If an operator deliberately chooses a different
control posture, they must do so separately; paused state, pending stop
intents and changed bindings still block the runtime. Supervised and
autonomous controls modes are not qualified.

The model uses a strict one-object text JSON protocol rather than access to
VS Code's general agent tools. Only the extension maps permitted messages
to the confined tools. Completion returns a structured task receipt through
`native_execution.receive_receipt`; it never accepts the result, runs
verification, approves a plan or advances an SDLC gate. Command verification
must remain `unavailable`, `not-run` or `skipped`.

## Failure, cancellation and retention

Invalid protocol, errors, changed bindings, exhausted budgets, timeout or
local cancellation stop the loop without another provider attempt or a
success receipt. A failure after dispatch leaves native manager work
unresolved; restart never redispatches that attempt. The persistent runtime
marker is active, unknown or reported, not evidence that a remote model
stopped. The local lease prevents later privileged operations after expiry;
cleanup and a timed-out CLI can take additional time. A host/process failure
can leave a writer lock or partial staging that requires inspection.

Cancellation requests the VS Code cancellation token and stops local
progress. It is **not remote acknowledgement**. Do not resolve unknown work
by assuming that cancellation rolled back an already-started atomic tool
operation or receipt transaction. Do not resolve unknown work
by deleting files, stealing locks or falsely declaring completion. Inspect
using the existing manager and controls reconciliation; authoritative remote
stop recovery is not supplied by this slice.

No automatic telemetry, transcript, prompt, response stream, tool-content
log or export is written. Context/history lives only in memory. Ignored
manager-local storage retains counters, binding digests, local call ID and
status and lease-enforcement clock boundaries; the existing manager retains
its structured task receipt metadata.
Workers must not embed transcripts or file contents in receipt text fields.
Selected brief and requested allowed file content are sent to the selected
model only after explicit consent. Provider retention and billing are
external policies, not controlled by this package.

## Offline validation and CLI

```powershell
python -B -m unittest tests.test_bounded_runtime tests.test_native_execution tests.test_execution_controls -q
npm --prefix packages\sdlc-runtime run check
npm --prefix packages\sdlc-runtime test
```

These tests replace only the external model response seam. Filesystem,
CLI subprocess, profile installation, manager approval, native request,
tools and receipt boundaries are real. No external model is invoked.

The bridge is also directly runnable:

```powershell
$Payload | python -I -S skills\sdlc\scripts\manage_runtime.py prepare --project-root "$TargetProject"
```

JSON stdin is strict and bounded. `prepare` accepts exactly `executionId`,
`brief`, `role`, `model` (`id`, `vendor`, `family`, `version`) and `limits`.
It returns a read-only runtime envelope. `start` requires that envelope plus
independently confirmed `approvedRuntimeDigest` and `approvedRequestDigest`.
`check`, `step` (plus `prompt`), `observe` (plus `response`),
`tool` (plus `name`, `arguments`), `receive` (plus `result`) and `stop`
all require the exact envelope. The extension, not worker text, owns these
operations. There is no arbitrary import path, command runner or approval
operation. Diagnostics contain neutral classes rather than model content.

See [qualification and external gates](QUALIFICATION.md) before considering
live use.
