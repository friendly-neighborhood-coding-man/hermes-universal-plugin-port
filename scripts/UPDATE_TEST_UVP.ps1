# P6 SAFETY: This legacy updater modifies the existing P5 disposable profile.
# Do not repurpose it for the P6 v0.6.0 experiment; preserve v0.5.6 proof.
throw 'P6 branch: legacy v0.5.6 updater disabled. Use a NEW disposable P6 profile and docs/P6_OPERATOR_RUNBOOK.md.'

# Install ONLY reviewed UVP 0.5.6 into the dedicated disposable Windows
# Hermes test profile. Never enables network execution.
# Run: powershell -NoProfile -File .\scripts\UPDATE_TEST_UVP.ps1
param(
    [string]$Worktree = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$uvpHome = 'D:\Hermes-Lab\uvp-v050-hermes-test'
$requiredVersion = '0.5.6'
$previousHome = $env:HERMES_HOME
$previousExecutionFlag = $env:UVP_ENABLE_ARXIV_EXECUTION
try {
    $env:HERMES_HOME = $uvpHome
    $env:UVP_ENABLE_ARXIV_EXECUTION = '0'

    if (-not (Test-Path -LiteralPath $uvpHome -PathType Container)) {
        throw 'Disposable UVP Hermes home does not exist'
    }
    $dest = Join-Path $uvpHome 'plugins\universal-plugin-port'
    $manifest = Join-Path $Worktree 'plugin.yaml'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw 'Source plugin manifest is missing'
    }
    if (-not (Select-String -LiteralPath $manifest -Pattern ('^version:\s*' + [regex]::Escape($requiredVersion) + '\s*$') -Quiet)) {
        throw "Source manifest is not v$requiredVersion"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $dest 'plugin.yaml') -PathType Leaf)) {
        throw 'Installed UVP plugin missing; do not replace an unknown directory'
    }
    if (git -C $Worktree status --porcelain) {
        throw 'Worktree contains uncommitted changes'
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to verify worktree status'
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupRoot = Join-Path $uvpHome 'uvp-backups'
    $backup = Join-Path $backupRoot "universal-plugin-port-$stamp"
    $stage = Join-Path $uvpHome "uvp-stage-$stamp"
    if ((Test-Path $backup) -or (Test-Path $stage)) {
        throw 'Backup/stage destination already exists'
    }
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

    # Exclude Git metadata, tests, virtualenvs, Python caches.
    robocopy $Worktree $stage /E /XD .git .github tests __pycache__ .venv .pytest_cache /XF *.pyc
    $copyExit = $LASTEXITCODE
    if ($copyExit -ge 8) { throw "robocopy failed with $copyExit" }

    hermes plugins doctor $stage --ci
    if ($LASTEXITCODE -ne 0) {
        throw 'Staged plugin failed Hermes Doctor'
    }

    Move-Item -LiteralPath $dest -Destination $backup -ErrorAction Stop
    try {
        Move-Item -LiteralPath $stage -Destination $dest -ErrorAction Stop
        hermes plugins doctor $dest --ci
        if ($LASTEXITCODE -ne 0) { throw 'Installed plugin failed Hermes Doctor' }
        hermes plugins enable universal-plugin-port
        if ($LASTEXITCODE -ne 0) { throw 'Plugin enable failed' }
        hermes plugins list --plain --no-bundled
        if ($LASTEXITCODE -ne 0) { throw 'Plugin list verification failed' }
    }
    catch {
        # Never delete the new copy; quarantine and restore the old one.
        if (Test-Path -LiteralPath $dest) {
            $failed = Join-Path $backupRoot "failed-new-uvp-$stamp"
            Move-Item -LiteralPath $dest -Destination $failed -ErrorAction Stop
        }
        if (Test-Path -LiteralPath $backup) {
            Move-Item -LiteralPath $backup -Destination $dest -ErrorAction Stop
        }
        throw
    }
    Write-Host "UVP v$requiredVersion installed in disposable Hermes profile."
    Write-Host "Previous version kept at: $backup"
    Write-Host 'Network execution remains disabled by default.'
}
finally {
    $env:HERMES_HOME = $previousHome
    $env:UVP_ENABLE_ARXIV_EXECUTION = $previousExecutionFlag
}
