#requires -Version 5.1
<#
.SYNOPSIS
  Install the bundled SDLC skill by host profile or legacy project arguments.

.DESCRIPTION
  Resolves project/global and copy/link installation cells through the
  repository qualification manifest. Global installs require an explicit
  HomeRoot so this command never selects the operator's actual home.
#>
[CmdletBinding()]
param(
    [string]$TargetProject,
    [string]$ClientDir,
    [ValidateSet("copilot-vscode", "claude-code", "generic-agent-skills")]
    [string]$Profile,
    [ValidateSet("project", "global")]
    [string]$Scope = "project",
    [ValidateSet("copy", "link")]
    [string]$Mode = "copy",
    [string]$HomeRoot,
    [string]$DestinationRoot,
    [switch]$Link,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

try {
    $legacyClient = $PSBoundParameters.ContainsKey("ClientDir")
    $legacyTarget = $PSBoundParameters.ContainsKey("TargetProject") -and
        -not $PSBoundParameters.ContainsKey("Profile")
    if ($PSBoundParameters.ContainsKey("Profile") -and $legacyClient) {
        throw "-Profile cannot be combined with legacy -ClientDir."
    }
    if ($PSBoundParameters.ContainsKey("Profile") -and $legacyTarget) {
        throw "-Profile cannot be combined with legacy project arguments."
    }
    if ($Link -and $PSBoundParameters.ContainsKey("Mode") -and $Mode -ne "link") {
        throw "-Link conflicts with -Mode $Mode."
    }
    if ($Link) {
        $Mode = "link"
    }
    if (-not $Profile) {
        $Profile = "generic-agent-skills"
    }
    if ($legacyTarget -or $legacyClient) {
        $Scope = "project"
        if (-not $TargetProject) {
            throw "Legacy -ClientDir requires -TargetProject."
        }
        if (-not $ClientDir) {
            $ClientDir = ".agents/skills"
        }
        if ([IO.Path]::IsPathRooted($ClientDir) -or $ClientDir -match "(^|[\\/])\.\.([\\/]|$)") {
            throw "-ClientDir must be a safe relative path."
        }
        $DestinationRoot = Join-Path $TargetProject $ClientDir
    }
    if ($Scope -eq "project") {
        if (-not $TargetProject) {
            throw "Project scope requires -TargetProject."
        }
        if (-not (Test-Path -LiteralPath $TargetProject -PathType Container)) {
            throw "Target project path not found: $TargetProject"
        }
    }
    elseif (-not $HomeRoot) {
        throw "Global scope requires explicit -HomeRoot."
    }

    $qualify = Join-Path $PSScriptRoot "qualify.py"
    $arguments = @(
        $qualify, "install",
        "--profile", $Profile,
        "--scope", $Scope,
        "--mode", $Mode
    )
    if ($TargetProject) { $arguments += @("--project-root", $TargetProject) }
    if ($HomeRoot) { $arguments += @("--home-root", $HomeRoot) }
    if ($DestinationRoot) { $arguments += @("--destination-root", $DestinationRoot) }
    if ($DryRun) { $arguments += "--dry-run" }

    $output = & python @arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    if ($Json) {
        $output | Write-Output
    }
    else {
        $verb = if ($DryRun) { "Would install" } elseif ($Mode -eq "link") { "Linked" } else { "Copied" }
        [Console]::Error.WriteLine("$verb the sdlc suite for $Profile ($Scope/$Mode).")
        [Console]::Error.WriteLine("Reload the client and confirm sdlc and its sdlc-* implementations are discovered.")
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 2
}
