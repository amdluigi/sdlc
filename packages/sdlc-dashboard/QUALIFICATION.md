# Dashboard qualification

The host evidence below was observed on 2026-11-01 and applies only to the
export viewer. The live manager dashboard was added on 2026-11-02 and now has
focused automated evidence plus a bounded actual-host run documented below.
The current branch extends its live contract with bounded context and a
project Gantt. The older host evidence does not qualify those new live rows.
This file does not claim activation or completion for supervised or autonomous
workers. Independent parent integration/review and CI remain separate gates.

## Exact owned files

```text
packages\sdlc-dashboard\
  package.json
  extension.js
  manager.js
  manager_bridge.py
  manager_provider.js
  snapshot.js
  provider.js
  README.md
  QUALIFICATION.md
  test\
    fixture.js
    snapshot.test.js
    io.test.js
    provider.test.js
    extension.test.js
    live-view.test.js
    manager-provider.test.js
    host.js
```

This optional package has no runtime dependency beyond the host-provided VS
Code API and Node built-ins. The larger orchestration change also updates the
project-level bridge, manager, shared contracts, qualification inventory and
documentation outside this package.

## Host and transport

- Actual installed VS Code **1.131.0**, build
  `e4c7e7b1d6d060162f4aa7f8225271b67ce1df75`, Windows x64.
- Actual extension-host Node **24.18.0**, Electron **42.7.0**.
- Package tests ran with Node **24.19.0**.
- A minimal disposable extension-development host qualified file transport
  and `TreeView` **before production UI implementation**. The probe was
  inactive before its explicit command; `workspace.fs.readFile` consumed
  57 local bytes, and a native tree rendered the literal label
  `Transport qualified: plain <script> Ω 😀` with accessible read-only
  naming, selection and focus.
- The probe exposed a real API requirement: `reveal` requires `getParent`.
  This was corrected and requalified in the probe before production.
- All hosts used distinct isolated user-data/extension directories and a
  disposable workspace. No global extension install or user-editor
  attachment occurred. Named agent-browser sessions attached only to
  explicitly launched loopback CDP endpoints.
- Subsequent isolated profiles disabled editor auto-update/extension-update
  and telemetry settings. Initial host logs did show the editor's own
  background update check/download; no download or installation command was
  used to qualify the package. This incidental host behavior is not package
  network behavior or an offline-host qualification claim.

## Current executable evidence

```powershell
npm --prefix packages\sdlc-dashboard test
npm --prefix packages\sdlc-dashboard run check
npm --prefix packages\sdlc-dashboard run qualify
```

**66 tests pass, 0 failures, 0 skips.** Syntax checks pass. No install,
third-party dependency, TypeScript build or downloaded test host is needed.
The current native-host seam additionally verifies that an explicit live
poller stops when the manager view becomes hidden, the selected execution
changes, or refresh fails; that unchanged polls during a confirmation do not
invalidate it; that real manager state changes are rejected under the writer
and refreshed; that a changed selection invalidates the pending action; that a
poll racing a successful write reports no false failure; and that bounded
batch results are accepted only with digest-bound independent validation,
and that version-2 snapshots and live views show that recorded acceptance
basis without presenting it as worker verification.
These are simulated-host checks; live manager
interaction and polling remain unqualified in VS Code.

Before implementation, the test set failed for missing validator/provider
implementation; an explicit assertion reported **Missing read-only snapshot
validator**. After implementation the set passed. A real-host finding about
an error-shaped view description surviving recovery received a separately
observed failing regression test and a verified fix.

The initial red run had seven failures and 24 passing negative assertions.
Those negative assertions could pass on a missing-module exception and are
not counted as behavioral red evidence. The final tests resolve the real
parser before entering rejection assertions, preventing that false-positive
path. The explicit missing-feature assertion and positive contract/provider
failures are the recorded initial red evidence; later boundary additions are
coverage, not retroactive test-first evidence.

`test\host.js` also passed in the installed isolated extension-development
host on the final implementation. It verifies:

- inactive until the explicit refresh command, followed by exactly the two
  registered extension commands;
- actual local Node filesystem transport and native TreeView construction;
- literal Unicode task text and accessible waiting/read-only names;
- a surviving selected task on refresh;
- failed reloads discard both data and selection;
- an unconfined selected file is rejected;
- view descriptions follow validation failure and recovery.

### Final overlapping-refresh native qualification

The parent-owned overlap fix received a bounded installed-host rerun on
2026-11-01 using a distinct disposable profile and the same actual Python
Unicode/int64 export. Update, extension-update and telemetry settings were
disabled **before** this host launched. The finite native test suite returned
successfully; no GUI exploration, browser attachment, package installation
or new download was required.

`test\host.js` wraps the original production `readSnapshot` function, verified
by function identity, and gates only completion after each actual filesystem
read. It does not fabricate snapshot values or replace native commands.
Two overlapping registered `sdlc.execution.refreshSnapshot` commands:

1. Perform two real reads while displayed data is cleared and the pending
   root/file/binding remains available.
2. Observe actual native loading invalidation clear the TreeView selection.
3. Complete the newer read first and prove its exact result object is
   promoted, pending selection clears, and the original task selection
   survives through the native command path.
4. Complete the older read and prove it cannot replace the promoted result
   or alter the restored task selection.

A second pair performs two more real reads: an older valid export read is
held while the actual disposable file is corrupted for the newer read.
The newer real parse failure clears data, active selection and pending
selection. Releasing the older valid completion cannot resurrect any of
them. All gates and waits are bounded, the original reader/file are restored
in `finally`, and the suite reports **four real reads total**.

Final actual host evidence records `concurrentRefresh.realReads=4`,
`overlapReads=2`, native loading-selection invalidation, newest-result
promotion, selected-task preservation, stale-success rejection, latest real
corruption failure and stale-completion non-resurrection. The unchanged
native semantics and viewport evidence below are reused, not relabelled as a
new broad GUI audit. Existing screen-reader, all-reparse-tag and exact
focused-child limitations remain unchanged.

The first native suite run found a test assumption error: querying registered
commands before extension activation is not proof of contributed command
availability. The corrected suite invokes the actual contributed command
first, then checks the registered commands. It was rerun successfully, not
replaced by a mock.

### Python interoperability

The actual `build_snapshot` manager output used a real disposable Git
project, an explicitly imported execution plan, title
`Plain <script> Ω 😀 and quoted "metadata"` and estimate
`9223372036854775807`. Python and the production Node parser both produced:

```text
sha256:600667b11a019208d1d370969e25f6b231731603724d367b224c79f0309f0b47
```

The production entry point for independently rerunning interoperability is:

```javascript
const {parseSnapshot, canonical} = require('./packages/sdlc-dashboard/snapshot');
const snapshot = parseSnapshot(require('node:fs').readFileSync(snapshotPath));
```

The standalone parser has no VS Code dependency. It preserves BigInt values
above JS's safe-integer ceiling and Python's sorted compact ASCII escaping.

## Real rendered UI and accessibility evidence

Actual Electron GUI automation used the installed agent-browser CLI, not
provider mocks, for:

| Flow/state | Observed evidence |
|------------|-------------------|
| Explicit open | Command Palette, confining workspace picker, VS Code's simple local file picker, valid export and focused binding row |
| Keyboard | End, Up/Down, Left/Right and Enter navigate, expand/collapse and select actual native tree rows |
| Refresh | Keyboard-selected task survives refresh; enclosing native tree retains keyboard focus |
| Invalid reload | After corrupting only the disposable export, refresh renders one accessible unavailable/invalid row and no previous task or binding |
| Cancel | Escape from the workspace picker renders a plain no-local-workspace-selected state |
| Recovery | Explicitly reopening the restored export renders validated snapshot data again |
| Desktop | Actual rendered viewport 1440 x 902; native scrollable tree and plain labels |
| Narrow | Actual emulated rendered viewport 800 x 600; no document horizontal overflow, accessible names retained, native ellipsis/scroll behavior |
| Reduced motion | Actual renderer media query reports reduced motion; the package adds no animation |
| Semantics | Native `tree` role, `tabindex=0`, named `treeitem` states, selected rows, literal metadata, theme icons and string tooltips |

The isolated file picker used `files.simpleDialog.enable=true`. The OS-native
file dialog was not instrumented. Screenshots, accessibility snapshots,
host logs, command results and generated fixtures were retained only in
disposable qualification artifacts, not committed or copied into the skill
bundle.

## Real versus simulated coverage

- **Real:** installed native APIs, Node filesystem reads, Windows junction
  rejection, actual Python export, native open/refresh/cancel/error/recovery,
  keyboard navigation and selected-node restoration.
- **Simulated seam:** Node provider and command-flow tests supply a declared
  minimal `vscode` API implementation. They exercise the real production
  provider/controller/extension logic; they do not qualify native semantics.
- **Synthetic data:** malformed schemas, duplicate keys, all status values,
  integer limits and empty task lists are bounded contract fixtures.
  Actual exported native UI evidence used one waiting task, disabled
  controls, missing attempt/report/model/interval and no approval.

## Remaining limitations and readiness

- **All arbitrary Windows reparse tags are not qualified.** Node's documented
  APIs do not expose every reparse attribute/tag. Actual junction rejection
  and realpath/identity checks do not prove rejection of every cloud/
  application-defined tag or hostile concurrent directory substitution.
  Strict all-tag environments must not enable this package.
- **Freshness is an export limitation, not a live success claim.** The fixed
  schema cannot identify an initially selected old export, and no watcher
  notices a subsequent file change until explicit refresh. Known revision
  rollback, execution changes and same-revision plan-digest rewriting are
  rejected. Digest consistency does not prove authenticity or current policy.
- **Focus restoration is bounded by the native API.** Selection and enclosing
  tree focus were observed to survive refresh. The renderer's active
  descendant may reset and expanded descendants may collapse after the
  mandatory loading invalidation; exact focused-but-unselected child-row
  restoration is not guaranteed. Refresh uses `focus:false` rather than
  stealing focus from another editor surface.
- **No actual screen reader, switch device, live-announcement capture,
  high-contrast theme, touch target, OS-native picker or verified 200% zoom
  qualification was available.** Native accessible semantics/keyboard and
  two viewport classes were observed, not full assistive-technology
  certification. Zoom-key input attempts were not accepted as zoom evidence.
- Minimum VS Code 1.85/Node 20 engines are declared, not runtime-qualified
  here. Only the listed installed Windows host was tested.
- There is no VSIX/Marketplace release or global installation qualification.

**Readiness: bounded native transport and package behavior qualified;
full AC-15/all-reparse and assistive-technology certification remain partial.**
The export viewer stays optional and command-activated. The live view only
mediates existing local manager APIs and adds no worker authority. Independent
review and final integrated CI belong to the parent change. Rollback is
removal of this optional package or closure of its isolated development host;
manager state is untouched.

## Live manager dashboard status

An isolated Visual Studio Code Insiders 1.145.0 host loaded a disposable
manager execution through the dashboard's live controller and rendered the
native manager TreeView. The host showed a two-activity Project Gantt, shared
context, and specialist context. The accessibility snapshot exposed the
manager as a `tree` with labeled `treeitem` rows; direct selection of the
Gantt row and native TreeView selection of a specialist-context row were
observed. This confirms live data loading and presentation in that host, not
the broader live interaction contract.

Explicit polling, stale-action rejection, confirmation flows, keyboard
navigation of the manager tree, screen-reader announcements, and other
assistive-technology behaviors were not exercised in this host run. The
separate export-viewer keyboard observations above do not qualify manager-tree
keyboard behavior. Autonomous model/provider execution, authoritative spend
limits, and remote host cancellation remain unsupported or unqualified.
