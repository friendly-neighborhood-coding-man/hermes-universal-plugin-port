<#
Update Universal Plugin Port development plugin without deleting user data.
Run in a NON-ADMIN PowerShell after closing TUI and important Gateway jobs.
Backups go outside the plugin discovery root to avoid a stale same-name plugin.
#>
param([string]$HermesHome = 'D:\Hermes-Lab\data')
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Use a non-administrator PowerShell. Elevated Gateway previously blocked non-elevated TUI clients.'
}
$env:HERMES_HOME = $HermesHome
$src = $PSScriptRoot
$pluginsRoot = Join-Path $HermesHome 'plugins'
$dst = Join-Path $pluginsRoot 'universal-plugin-port'
$sourceManifest = Join-Path $src 'plugin.yaml'
if (-not (Test-Path -LiteralPath $sourceManifest)) { throw "Missing source manifest: $sourceManifest" }
if (-not (Select-String -LiteralPath $sourceManifest -Pattern '^version:\s*0\.4\.3\s*$' -Quiet)) {
    throw 'Expected source version 0.4.3'
}
if (-not (Get-Command hermes -ErrorAction SilentlyContinue)) { throw 'hermes executable not found in PATH' }

# Detect the earlier duplicate plugin backup problem *before* changing anything.
$duplicates = @()
if (Test-Path -LiteralPath $pluginsRoot) {
    foreach ($folder in (Get-ChildItem -LiteralPath $pluginsRoot -Directory)) {
        $manifest = Join-Path $folder.FullName 'plugin.yaml'
        if ((Test-Path -LiteralPath $manifest) -and
            (Select-String -LiteralPath $manifest -Pattern '^name:\s*universal-plugin-port\s*$' -Quiet)) {
            $duplicates += $folder.FullName
        }
    }
}
if ($duplicates.Count -gt 1 -or ($duplicates.Count -eq 1 -and $duplicates[0] -ne $dst)) {
    throw "Multiple same-name plugin directories detected. Move backups OUTSIDE '$pluginsRoot' before installing: $($duplicates -join ', ')"
}

Write-Host 'Checking v0.4.3 source with Hermes Doctor / Validator...'
hermes plugins doctor $src --ci
if ($LASTEXITCODE -ne 0) { throw 'Source Doctor failed' }
hermes plugins validate $src
if ($LASTEXITCODE -ne 0) { throw 'Source Validator failed' }

# Backup must be outside the plugins directory! The prior v0.2.1 backup inside
# HERMES_HOME/plugins shadowed the upgraded manifest.
$backupRoot = Join-Path (Split-Path $HermesHome -Parent) 'plugin-backups'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backup = Join-Path $backupRoot ('universal-plugin-port-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $backup) { throw "Backup already exists: $backup" }

Write-Host 'Stopping Gateway gracefully; no force-kill is used...'
hermes gateway stop
if ($LASTEXITCODE -ne 0) { throw 'Gateway stop failed. No plugin files were changed.' }

$backedUp = $false
try {
    if (Test-Path -LiteralPath $dst) {
        Move-Item -LiteralPath $dst -Destination $backup -ErrorAction Stop
        $backedUp = $true
    }
    Copy-Item -LiteralPath $src -Destination $dst -Recurse -ErrorAction Stop
    hermes plugins doctor $dst --ci
    if ($LASTEXITCODE -ne 0) { throw 'Installed Doctor failed' }
    hermes plugins validate $dst
    if ($LASTEXITCODE -ne 0) { throw 'Installed Validator failed' }
    hermes plugins enable universal-plugin-port
    if ($LASTEXITCODE -ne 0) { throw 'Plugin enable failed' }
    $row = @(hermes plugins list --plain --no-bundled | Select-String 'universal-plugin-port')
    if ($LASTEXITCODE -ne 0 -or $row.Count -ne 1 -or
        $row[0].Line -notmatch '^enabled\s+user\s+0\.4\.3\s+universal-plugin-port\s*$') {
        throw "Discovery did not report one enabled v0.4.3 plugin: $row"
    }
    Write-Host "Backup saved outside plugin discovery: $backup"
} catch {
    Write-Warning 'Update verification failed. Attempting to restore the original plugin.'
    if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
    if ($backedUp) { Move-Item -LiteralPath $backup -Destination $dst -ErrorAction Stop }
    hermes gateway start
    throw
}

hermes gateway start
if ($LASTEXITCODE -ne 0) { throw 'Plugin updated, but Gateway start failed. Check hermes gateway status.' }
Write-Host 'Universal Plugin Port v0.4.3 installed and enabled. Gateway restarted.'
Write-Host 'Use Hermes TUI: /universal-port audit 244e3cef48ed'
