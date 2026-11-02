# Bounded runtime qualification

## Executable offline evidence

Previous version-1 baseline full local gate (not evidence for later changes):

```powershell
python -B -m unittest discover -s tests -q
npm --prefix packages\sdlc-runtime run check
npm --prefix packages\sdlc-runtime test
npm --prefix packages\sdlc-dashboard run check
npm --prefix packages\sdlc-dashboard run qualify
python -B scripts\qualify.py verify-manifest
python -B scripts\validate.py
```

Before the supervised/execute additions, passed: **717 Python tests**, **17 runtime Node tests**, **40 unchanged
dashboard Node tests**, syntax, exact bundle inventory and source validation.
No tests were skipped. These are local results, not a fresh remote CI claim.
The documented manual tryout was also executed against an exact-byte final
source snapshot in a fresh separate Git repository: project-local
installation included `manage_runtime.py`, receiving produced `reported`,
independent acceptance produced `accepted`, snapshot export succeeded and
the final manual consent was disabled.

The Python unittest module `tests.test_bounded_runtime` exercises actual
project Git repositories, native profile installation, immutable manager
plans/approvals, exact digest start, real reads/searches/atomic CAS edits,
receipt reporting without acceptance, default-disabled behavior, unsupported
execute, stale source/guidance/profile/consent/control bindings, enabled
manual controls refusal, input/output/tool/iteration/wall-time exhaustion,
hardlinks, competing writers, Unicode digest parity, duplicate dispatch,
malformed/duplicate-key CLI input and isolated trusted imports.

The Node tests `test/driver.test.js` invoke the actual Python CLI and actual
filesystem for all manager/tool operations. `respond(prompt, signal)`,
the external VS Code language-model text stream boundary, is synthetic.
Two deadline cases additionally use explicit Node monotonic-clock/watchdog
seams, advancing only after the actual provider boundary is reached. Their
real Python manager lease remains valid. This prevents slow subprocess startup
from expiring a short fixture lease before the intended provider test begins;
it does not weaken production deadlines or assert real provider latency.
Tests cover bounded tool-to-result flow, provider failure, invalid JSON,
unsupported execute, excessive model output, iteration exhaustion, source
drift during inference, nonresponsive provider cancellation, no automatic
retry/redispatch, no fallback receipt and independent acceptance remaining
absent.

These are offline behavior tests, not fabricated provider observations.
The host ID describes this local adapter, and its call ID is locally
generated. Neither proves authenticated external identity or routing.

Independent review found an immediate-stream starvation bug: empty model
chunks consumed no byte budget and continuous microtasks prevented timers
from running. Observed failing regressions preceded the fix. Streaming now
checks a monotonic deadline for each chunk, rejects 128 consecutive empty
chunks and yields to the event loop every 32 chunks, including nonempty
streams. Regression cases assert unknown work, no receipt and no redispatch.

Fixtures use standard operating-system temporary directories. The original
repository-local fixtures exposed an environmental Windows directory-rename
failure reproduced by a minimal mkdir/write/rename probe without runtime or
manager code. No production permission/promotion retry was introduced.

## Actual host qualification without inference

Observed in an isolated installed VS Code **1.131.0**, build
`e4c7e7b1d6d060162f4aa7f8225271b67ce1df75`, on Windows x64:

- The contributed command appeared in the actual Command Palette and
  activated this development extension.
- Keyboard navigation reached the real explicitly named project picker,
  local brief-file dialog and four-role picker. These were native controls,
  not mocked UI. The selected brief belonged to a disposable manager-approved
  synthetic project.
- Native model discovery returned no models in the isolated unsigned-in
  profile. This is not a claim that the host or other profiles are unsupported.
  The first run exposed an empty model picker with no actionable explanation.
  An observed failing extension regression preceded an explicit no-model error
  notification. A real-host reload then displayed that error.
- The native accessibility tree contained the complete error text in an
  `alert`, notification list and dialog. The actual desktop viewport was
  1440 by 902; an emulated 800 by 600 viewport showed the native ellipsized
  notification while its full accessible name remained available. The final
  error-state view had no document horizontal overflow. Intermediate resize
  geometry is not proof of stable picker reflow.
- Escape exited the initial no-model picker and returned focus to the prior
  editor input. A later attempted project-picker cancellation check timed out
  waiting for that picker and is not counted as successful cancellation proof.
- The final real manager inspection retained only `PLAN_PROPOSED` and
  `PLAN_APPROVED`, with zero worker attempts and zero receipts. No provider
  request, model-run authorization, telemetry activation, credential copying,
  global extension installation or real application edit occurred.
- Only the exact owned isolated editor/browser instance was closed afterward.
  Editor updates, extension updates and telemetry were disabled in its
  disposable settings before launch.

The extension regression uses a declared VS Code API substitute to check the
empty-model logic; it is not the native-host evidence above. No authenticated
provider or streamed native model response was exercised by this trial.

### Native version-2 UI with an offline synthetic model

A separate pre-review source snapshot was exercised in actual VS Code
**1.131.0**, Windows x64, Electron **42.7**, Node **24.18.0**. Only native
model discovery and response production were replaced by an explicitly
labelled offline synthetic seam; the extension UI, file dialogs, fixed
Python bridge, filesystem, manager and contained command process were real.

- Actual project, brief, role, model and command-definitions file selection
  reached the exact-command and runtime authorization modals.
- Escape from exact-command consent started nothing. Separately, Escape
  from runtime consent after exact-command authorization also started nothing.
- The authorized synthetic flow performed a real read, compare-and-swap edit
  and contained trusted Python check. The manager recorded `reported`, with
  no independent acceptance. A later project-picker Escape preserved state.
- The observation used four synthetic response iterations and three synthetic
  inventory selections, with **zero actual provider requests**, credentials,
  spend or consumer installation. All owned editor/browser processes stopped.

This qualifies those native interaction/transport observations for that
snapshot, not real provider identity, inference, billing, remote stop,
assistive-technology completeness or the later cancellation review fixes.
The fixes below have separate current automated regression evidence.

The corrected driver then passed an actual native progress-Cancel trial
against an exact-byte final-source snapshot in the same isolated host build.
The trusted ten-second command's observed heartbeat lifetime was **1044.50 ms**,
and its heartbeat remained stopped afterward. This is command lifetime, not
remote cancellation latency. Three synthetic responses, one synthetic
selection and zero actual providers left no receipt or acceptance.
The actual error notification explicitly retained the unknown-work warning;
dismissing it and then escaping the project picker preserved manager state.
All owned native editor/browser processes were stopped.

### Reproduce the offline native dialogs and command trial

Run from the public checkout. This creates a fresh disposable Git project
and isolated editor profile, not an installed consumer or authenticated
provider session. The fixture explicitly approves synthetic local manager
inputs. Do not reuse the development harness in a real project.
Use `$cancelTrial = $true` for the separate active-command cancellation case.

```powershell
$cancelTrial = $false
$SdlcCheckout = (Get-Location).Path
$trial = Join-Path $env:TEMP ('sdlc-native-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $trial | Out-Null
$env:SDLC_HOST_ROOT = Join-Path $trial 'workspace'
$env:SDLC_CANCEL_TRIAL = $cancelTrial.ToString()
@'
import json, os, pathlib, sys
from tests.test_bounded_runtime import fixture
from tests.test_execution_contracts import result
import execution_controls as controls
import execution_manager as manager
root = pathlib.Path(os.environ["SDLC_HOST_ROOT"])
plan, brief = fixture(root)
brief["allowedActions"].append("execute")
controls.configure_controls(root, {
    "schemaVersion": 2, "enabled": True, "mode": "supervised",
    "maxAttempts": 1, "allowEscalation": False,
    "permittedModels": ["synthetic-native-model"]
})
current = manager.inspect_execution(root, "feature-one")
controls.approve_controls(root, "feature-one", current["planDigest"],
    current["policyDigest"], controls.inspect_controls(root)["controlsDigest"])
cancel = os.environ["SDLC_CANCEL_TRIAL"].lower() == "true"
code = ("import pathlib,time; p=pathlib.Path('.synthetic-command-heartbeat');\n"
        "while True: p.write_text(str(time.time_ns())); time.sleep(0.02)") if cancel else (
        "import pathlib; assert pathlib.Path('src/feature.py').read_text() == "
        "'after native\\n'; print('offline synthetic check')")
compile(code, "<synthetic-command>", "exec")
commands = [{"id": "check", "executable": str(pathlib.Path(sys.executable).resolve()),
    "argv": ["-I", "-B", "-S", "-c", code], "cwd": str(root),
    "timeoutMs": 10000 if cancel else 2000, "maxOutputBytes": 2048}]
for name, value in {
    "brief.json": brief, "commands.json": commands,
    "host-fixture.json": {"result": result(plan), "execute": True,
                          "cancelDuringExecute": cancel}
}.items():
    (root / name).write_text(json.dumps(value), encoding="utf-8")
(root / ".synthetic-runtime-host").write_text(
    "offline synthetic provider only\n", encoding="utf-8", newline="\n")
'@ | python -B -
if ($LASTEXITCODE -ne 0) { throw 'Synthetic fixture preparation failed.' }
New-Item -ItemType Directory -Path "$trial\user-data\User", "$trial\extensions" | Out-Null
$settings = '{"update.mode":"none","extensions.autoCheckUpdates":false,"extensions.autoUpdate":false,"telemetry.telemetryLevel":"off","workbench.startupEditor":"none","workbench.enableExperiments":false,"security.workspace.trust.enabled":false,"files.simpleDialog.enable":true,"git.enabled":false,"window.dialogStyle":"custom"}'
[IO.File]::WriteAllText("$trial\user-data\User\settings.json", $settings)
code --user-data-dir "$trial\user-data" --extensions-dir "$trial\extensions" --disable-extensions --disable-workspace-trust --skip-welcome --skip-release-notes --extensionDevelopmentPath "$SdlcCheckout\packages\sdlc-runtime" --extensionDevelopmentPath "$SdlcCheckout\packages\sdlc-runtime\test\interactive" --new-window "$trial\workspace"
```

Follow the automatic trial phases shown in the fixture's `host-phase.json`:
select the project, `brief.json`, developer, **OFFLINE SYNTHETIC TEST ONLY**
and `commands.json`. In the normal trial, first dismiss exact-command consent,
then repeat and authorize exact commands but dismiss runtime consent.
Repeat and authorize both for the actual read/edit/command/report path.
Finally escape the project picker. Inspect `host-result.json`; failures
produce `host-failure.json` only in an exactly marked synthetic workspace.

The cancellation variant runs one authorization flow. Click the actual
progress **Cancel** only after `.synthetic-command-heartbeat` appears,
well before the ten-second command timeout. Dismiss the explicit error
notification so the command promise settles, then escape the project picker.
Its result must show a stopped heartbeat below five seconds and no receipt.
Close only the isolated trial window afterward.

Do not pass `--extensionTestsPath`: VS Code deliberately refuses modal prompts
in extension-test mode. The separate development-only startup harness imports
the same guarded suite without weakening production consent. Never treat
these synthetic streams as provider, billing or remote-stop qualification.

## External gates not satisfied

- Actual provider consent and provider response transport. Native selection
  and authorization have the separately labelled synthetic observations
  above; the no-model trial alone did not qualify those paths.
- Attributable live provider/model identity, ignored preferences,
  availability changes and effective routing. Picker metadata and mocked
  streams cannot prove remote identity.
- Provider pricing, token usage, billing, monetary limits, remote
  cancellation acknowledgement or remote operation termination.
- Full success/consent/cancellation keyboard and focus flows, stable narrow
  picker reflow, screen-reader or switch trials and real host
  restart/extension termination during inference.
- POSIX execute is explicitly unsupported: process-group cleanup does not
  survive arbitrary supervisor termination. Any future POSIX support needs
  a separately qualified owner-death lifecycle, not merely a group-kill test.
- Autonomous policies and recovery of unknown external work. Explicit
  version-2 supervised local controls do not establish remote-stop evidence.
  Existing version-1 manual controls are intentionally not weakened.
- Independent human acceptance of resulting work and the full roadmap's
  live-host criteria. This package cannot authorize publication or releases.

No external inference was authorized for development or qualification.
Keep this package opt-in and experimental until a maintainer separately
selects a concrete host/build, model/provider, scoped inference authorization
and evidence-retention policy and completes these gates.

## Additive supervised and execute qualification

The local extension now has separately selected version-2 execute envelopes
and version-2 supervised controls. Original version-1 policy, runtime and
native request semantics remain unchanged. No old policy is automatically
converted; explicit adoption retains the complete prior manual record and old
readers fail closed. Automatic downgrade is refused rather than erasing
history or reviving stale approvals.

Observed missing-behavior regressions failed before implementation for
supervised controls, exact-ID execute, descendant timeout and output flood.
`tests.test_runtime_commands` uses actual executable subprocesses, temporary
Git projects, profiles, manager approvals and the fixed CLI. Windows uses
real native suspended process creation, restricted handle inheritance,
kill-on-close jobs, assignment before resume and active-job termination
observation. Timeout and pause tests start a real heartbeat descendant and
verify that its heartbeat stops after termination. A separately declared
fault injection forces only `AssignProcessToJobObject` to fail while native
process creation remains real; it proves no resume or first-instruction
marker occurs, not a simulated process-tree success.

Other cases cover exact executable/argv/cwd binding and digest approval,
nonzero exit, bounded output flood, invalid cwd spawn failure, provenance
rejection/receipt without acceptance, single-use IDs, missing controls
reapproval, original native dispatch rejection, original readers executed
from the baseline source, retention/downgrade refusal, unknown-work
retention and default-disabled no-write. Existing stream starvation/yield
regressions remain mandatory.

A further observed failing regression showed that a worker could copy
in-memory command output into a free-text receipt finding. Version-2
receipts now reject findings/blockers and constrain verification text to
observed provenance or closed unavailable/not-run/skipped statuses.
Version-1/manual receipt contracts are unchanged.

Focused commands:

```powershell
python -B -m unittest tests.test_runtime_commands tests.test_bounded_runtime tests.test_execution_controls tests.test_native_execution -q
node --test packages\sdlc-runtime\test\driver.test.js
```

Pre-review focused Windows run: **83 Python tests** and **20 runtime Node tests**
passed with no skips, including the existing stream starvation/deadline cases.
Syntax, exact 83-file bundle inventory, real copy/link installation parity,
source validation and diff whitespace checks passed. Run timing-sensitive
Node tests separately from a concurrently loaded Python suite: one parallel
stress run exhausted the existing three-second test lease before its model
stream began; the complete serial rerun passed without relaxing that test.

Final full-suite and independent review evidence must be refreshed after
these additions. No actual provider call, billing claim, remote-stop
acknowledgment, consumer activation or full-roadmap acceptance is implied.

## Review corrections: cancellation and owner death

Observed failing regressions preceded both fixes:

- A real execute command started a real heartbeat descendant. Aborting the
  driver/UI signal made no stop call while the command bridge remained
  pending. The tool wait now races abort; stop persistence happens promptly,
  explicit writer-lock contention is bounded/retried, and the actual helper
  is awaited through descendant cleanup rather than killed on UI abort.
  An independent actual native-UI trial against the pre-fix snapshot also
  reproduced the defect: clicking the real progress Cancel left a trusted
  ten-second command's heartbeat active for **9894.95 ms**. Its native
  regression failed the five-second bound with zero actual provider calls.
  This is pre-fix red evidence; the separate post-fix native trial above
  observed a 1044.50 ms heartbeat lifetime. Notification dismissal can delay command-promise
  settlement and is not included as process-lifetime evidence.
- Process-group `finally` cleanup cannot handle POSIX supervisor SIGTERM or
  bridge watchdog termination. The POSIX path was removed, not presented as
  qualified. Preparation, start and execute reject unsupported owner-death
  containment before command spawn. Historical records remain inspectable.

Windows regressions cover UI abort during real execution, real temporary
writer contention, exhausted stop persistence reported explicitly, stopped
descendant heartbeats, no receipts and no redispatch of unknown provider
work. The POSIX unsupported gate is tested on Windows through an explicitly
selected platform gate and runs on POSIX CI as the real unsupported path;
Windows-only execution qualification cases are explicitly platform-scoped.
No actual POSIX process-tree qualification or real inference is claimed.

After these corrections, the serial focused Windows run passed **84 Python
tests** and **23 runtime Node tests**, with no skips. Syntax, the normalized
83-file manifest, source validation and whitespace checks passed. This does
not replace the parent's final full suite or fresh independent review.

## Final coherent local gate

The final Windows source passed **734 Python tests**, **26 runtime Node tests**
and **40 unchanged dashboard Node tests**, with no failures or skips.
The three new complete schemas passed Draft 2020-12 validation. Source,
83-file manifest, runtime/harness syntax, installer shell syntax and whitespace
checks passed. Both independent reviewers verified the lifecycle fixes and
reported no remaining blocking findings in their scoped re-reviews.

The exact manual tryout's three PowerShell fences were executed against a
fresh project-local installed copy of this bundle. The task was reported
before independent acceptance, snapshot export succeeded and the final manual
consent was disabled. The native reproduction's fixture/setup block above was
also executed independently. Native success/decline and corrected active-Cancel
evidence are separately scoped above; none used an actual provider.

An intermediate full run correctly rejected three generated helper bytecode
files as transient bundle contents. Only those identified cache files and their
empty directory were removed; the complete rerun passed with inherited
`PYTHONDONTWRITEBYTECODE=1` and `python -B`. No inventory rule was weakened.
An intermediate five-second provider fixture also expired during slow real
CLI setup, before its provider was invoked. Its watchdog/clock tests now use
the explicitly declared seams above rather than increasing production limits,
relaxing assertions or retrying until a test happens to pass.

These are local results, not a claim that CI ran Windows process or optional
Node tests. POSIX execution remains explicitly unsupported, and full-roadmap
provider, autonomous-mode and assistive qualification remains incomplete.
