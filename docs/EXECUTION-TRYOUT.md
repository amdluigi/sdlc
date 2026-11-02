# Try SDLC in another repository

Merging SDLC updates its source repository, not copies already installed in
your projects or home directory. Reloading VS Code alone does not refresh
copied skills.

## What to expect

- Normal **Use SDLC to ...** requests still use the existing delivery workflow.
- Execution management, controls and detailed telemetry remain disabled until
  separately configured. Installing SDLC does not start workers or collect data.
- The manual preview can record approved plans, attempts, receipts, independent
  acceptance and reports. Receiving a result is not accepting it.
- Snapshots, selected-history analysis and inactive proposals are available
  through explicit commands. The optional dashboard is a separate extension,
  not installed by the skill installer.
- Native worker preparation is not proof of automatic execution, live billing
  or acknowledged remote cancellation. Check the optional
  [bounded worker](../packages/sdlc-runtime/README.md) and its
  [qualification](../packages/sdlc-runtime/QUALIFICATION.md) before enabling it.

## Install a project-local copy first

Use a disposable Git repository before an existing project. These commands
create a new folder; choose a name that does not already exist:

```powershell
$source = 'C:\dev\sdlc'
$demo = 'C:\dev\sdlc-tryout'
if (Test-Path -LiteralPath $demo) { throw 'Choose a new disposable folder.' }
New-Item -ItemType Directory -Path $demo | Out-Null
git init -q $demo
if ($LASTEXITCODE -ne 0) { throw 'Git initialization failed.' }
& "$source\scripts\install.ps1" -Profile copilot-vscode -Scope project -Mode copy -TargetProject $demo -DryRun
& "$source\scripts\install.ps1" -Profile copilot-vscode -Scope project -Mode copy -TargetProject $demo
$helpers = Join-Path $demo '.github\skills\sdlc\scripts'
if (-not (Test-Path -LiteralPath "$helpers\manage_execution.py")) {
    throw 'The installed copy does not contain execution management.'
}
```

Open the disposable repository in a **new VS Code window and chat**. Confirm
that the project-local `sdlc` and `sdlc-*` skills are discovered. If an old
global installation is also present, verify which source the host actually
loads rather than assuming project precedence.

For an existing repository, first use `-DryRun` and review the destination.
The installer refuses unsafe collisions; do not delete or overwrite a
customized installation to bypass that check. Do not copy this example's
execution policy into a real project as an installation step.

## Manual smoke test without any model calls

Continue in the same PowerShell session. This example explicitly enables the
manual preview **only in the disposable repository**, writes synthetic input
files and records one arithmetic verification. It does not test your app,
invoke an agent, enable telemetry or demonstrate automatic workers.

```powershell
function Invoke-DemoManager {
    param([string[]]$Arguments)
    $output = & python -B "$helpers\manage_execution.py" @Arguments --project-root $demo
    if ($LASTEXITCODE -ne 0) { throw 'Execution manager command failed.' }
    return ($output -join "`n")
}
function Write-DemoJson {
    param([string]$Name, $Value)
    $json = ConvertTo-Json -InputObject $Value -Depth 20
    [IO.File]::WriteAllText((Join-Path $demo $Name), $json, [Text.UTF8Encoding]::new($false))
}
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText((Join-Path $demo 'demo-source.md'), '# Synthetic arithmetic smoke test', $utf8)
$sourceDigest = 'sha256:' + (Get-FileHash -LiteralPath (Join-Path $demo 'demo-source.md') -Algorithm SHA256).Hash.ToLowerInvariant()
$policy = @{
    schemaVersion = 1; enabled = $true; mode = 'manual'
    retention = 'manual'; detailedTelemetry = $false
}
$plan = @{
    schemaVersion = 1; executionId = 'smoke-test'; revision = 1
    sourcePlan = @{
        path = 'demo-source.md'; digest = $sourceDigest
        prd = @{ id = 'smoke-test'; version = 1 }
    }
    tasks = @(@{
        id = 'verify'; title = 'Check synthetic arithmetic'; outcome = 'A checked assertion'
        prdRefs = @('FR-1', 'AC-1'); prerequisites = @(); consumes = @(); produces = @()
        execution = @{ mode = 'sequential'; group = $null }
        assignment = @{ agent = 'review'; modelProfile = 'host-default'; model = $null }
        estimateMs = $null; ownership = @(); acceptanceCriteria = @('AC-1')
        verification = 'python -c "assert 2 + 2 == 4"'
    })
}
Write-DemoJson 'policy.json' $policy
Write-DemoJson 'plan.json' $plan
Invoke-DemoManager -Arguments @('configure', '--input', "$demo\policy.json", '--dry-run')
Invoke-DemoManager -Arguments @('configure', '--input', "$demo\policy.json")
Invoke-DemoManager -Arguments @('import', '--input', "$demo\plan.json")
$current = Invoke-DemoManager -Arguments @('inspect', '--execution-id', 'smoke-test') | ConvertFrom-Json
# Review this synthetic plan before explicitly approving its current digests.
Invoke-DemoManager -Arguments @('approve', '--execution-id', 'smoke-test',
    '--plan-digest', $current.planDigest, '--policy-digest', $current.policyDigest)
Invoke-DemoManager -Arguments @('record', '--execution-id', 'smoke-test', '--task-id', 'verify', '--action', 'ready')
Invoke-DemoManager -Arguments @('record', '--execution-id', 'smoke-test', '--task-id', 'verify',
    '--action', 'start', '--attempt-id', 'attempt-one')
python -c "assert 2 + 2 == 4"
if ($LASTEXITCODE -ne 0) { throw 'The synthetic assertion failed; do not record passed evidence.' }
$binding = @{ executionId = 'smoke-test'; planRevision = 1; planDigest = $current.planDigest }
$brief = @{
    schemaVersion = 1; binding = $binding; taskId = 'verify'; attemptId = 'attempt-one'
    allowedActions = @('read'); ownership = @(); guidance = @()
    acceptanceCriteria = @('AC-1'); verification = 'python -c "assert 2 + 2 == 4"'
}
$result = @{
    schemaVersion = 1; binding = $binding; taskId = 'verify'; attemptId = 'attempt-one'
    status = 'completed'; artifacts = @(); findings = @(); blockers = @()
    verification = @(@{
        acceptanceCriterion = 'AC-1'; command = 'python -c "assert 2 + 2 == 4"'
        result = 'passed'; revision = 'synthetic-fixture'; summary = 'Synthetic assertion exited zero'
    })
}
Write-DemoJson 'brief.json' $brief
Write-DemoJson 'result.json' $result
Invoke-DemoManager -Arguments @('receive', '--execution-id', 'smoke-test',
    '--result-id', 'result-one', '--brief', "$demo\brief.json", '--result', "$demo\result.json")
$reported = Invoke-DemoManager -Arguments @('inspect', '--execution-id', 'smoke-test') | ConvertFrom-Json
if ($reported.state.tasks.verify.status -ne 'reported') { throw 'Expected reported, not accepted.' }
python -c "assert 2 + 2 == 4"
if ($LASTEXITCODE -ne 0) { throw 'Independent verification failed; do not accept.' }
$acceptance = @{
    schemaVersion = 1; taskId = 'verify'; attemptId = 'attempt-one'; resultId = 'result-one'
    acceptanceCriteria = @('AC-1'); revision = 'synthetic-fixture'
    command = 'python -c "assert 2 + 2 == 4"'; summary = 'Operator independently reran the synthetic assertion'
}
Write-DemoJson 'acceptance.json' $acceptance
Invoke-DemoManager -Arguments @('accept', '--execution-id', 'smoke-test', '--input', "$demo\acceptance.json")
Invoke-DemoManager -Arguments @('report', '--execution-id', 'smoke-test')
$snapshot = & python -B "$helpers\manage_insights.py" snapshot --project-root $demo --execution-id smoke-test
if ($LASTEXITCODE -ne 0) { throw 'Snapshot export failed.' }
[IO.File]::WriteAllText((Join-Path $demo 'execution-snapshot.json'), ($snapshot -join "`n"), $utf8)
```

Expected: the task is `reported` before independent acceptance and `accepted`
afterward. The report retains unknown estimates and does not grant PR or
release readiness. The explicit snapshot can be opened in the separately
installed [optional dashboard](../packages/sdlc-dashboard/README.md).

The helper records your assertions; it does not authenticate the actor or
prove that a command was honestly reported. Use actual project tests and
independent review for real work, not the arithmetic fixture.

## Stop the disposable preview

In the same session, explicitly disable subsequent manager writes:

```powershell
$policy.enabled = $false
Write-DemoJson 'policy.json' $policy
Invoke-DemoManager -Arguments @('configure', '--input', "$demo\policy.json")
```

Records remain available for inspection. This does not disable skills, erase
history, stop a native worker or revoke a remote request. See
[execution management](EXECUTION-MANAGEMENT.md) for explicit retention/deletion
and recovery, [controls](EXECUTION-CONTROLS.md) for persistent safety barriers,
and [telemetry](EXECUTION-TELEMETRY.md) for its separate consent.
