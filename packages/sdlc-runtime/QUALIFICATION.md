# Bounded runtime qualification

## Executable offline evidence

Final local gate:

```powershell
python -B -m unittest discover -s tests -q
npm --prefix packages\sdlc-runtime run check
npm --prefix packages\sdlc-runtime test
npm --prefix packages\sdlc-dashboard run check
npm --prefix packages\sdlc-dashboard run qualify
python -B scripts\qualify.py verify-manifest
python -B scripts\validate.py
```

Passed: **717 Python tests**, **17 runtime Node tests**, **40 unchanged
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
filesystem for all manager/tool operations. Only `respond(prompt, signal)`,
the external VS Code language-model text stream boundary, is synthetic.
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

## External gates not satisfied

- Actual model-selection/modal authorization, provider consent and streamed
  native response transport. The no-model trial does not qualify those paths.
- Attributable live provider/model identity, ignored preferences,
  availability changes and effective routing. Picker metadata and mocked
  streams cannot prove remote identity.
- Provider pricing, token usage, billing, monetary limits, remote
  cancellation acknowledgement or remote operation termination.
- Full success/consent/cancellation keyboard and focus flows, stable narrow
  picker reflow, screen-reader or switch trials and real host
  restart/extension termination during inference.
- Portable process-tree execution, executable/argv authorization and
  enforced subprocess output/timeout containment. Execute remains absent.
- Supervised/autonomous control policy activation and recovery of unknown
  external work. Existing manual controls are intentionally not weakened.
- Independent human acceptance of resulting work and the full roadmap's
  live-host criteria. This package cannot authorize publication or releases.

No external inference was authorized for development or qualification.
Keep this package opt-in and experimental until a maintainer separately
selects a concrete host/build, model/provider, scoped inference authorization
and evidence-retention policy and completes these gates.
