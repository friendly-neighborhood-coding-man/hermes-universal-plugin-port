<#
v0.4.3 repair-path smoke test (reviews P1-4, R4 and the v0.4.2 bytecode P0). NOT EXECUTED in the build environment
(no Windows, PowerShell or Hermes there). Its Windows behavior has not been observed.

Run it in two stages:

  Stage 1 (no switches): unit tests, repair of the SYNTHETIC fixture, adapter verification
  against ADAPTER_LOCK.json and the reviewed templates. Doctor/validate are intentionally
  NOT_RUN. The script exits 0 and prints the adapter digest. NOT_RUN is not a failure.

  Stage 2 (after you reviewed the adapter folder): pass BOTH
    -AcknowledgeDoctorExecutesAdapter
    -ExpectedAdapterSha256 <digest published in the external HANDOFF, outside the ZIP>
  The script re-verifies the adapter against that external digest, then runs
  `hermes plugins doctor` and `hermes plugins validate` with HERMES_HOME pointed at a NEW
  disposable folder. Any nonzero exit code throws (DOCTOR_FAIL / VALIDATE_FAIL).

Always writes SMOKE_STATUS.json plus doctor.log / validate.log when those run.

v0.4.3: verify-adapter now includes the pre-import gate (exact file allowlist: rejects __pycache__,
*.pyc, extension modules, extra .py and anything else). It runs before doctor AND again right
before validate, and doctor/validate run with PYTHONDONTWRITEBYTECODE=1 so Hermes' Python does
not write a cache into the adapter. (That variable only stops writing; the gate stops reading.)

WARNING: `hermes plugins doctor` IMPORTS the adapter and runs its register(ctx) IN-PROCESS.
HERMES_HOME isolation only redirects Hermes' data folder; it is NOT an operating-system
sandbox for code that doctor imports. With no operator approval record the v0.4.2 adapter
registers nothing, so doctor exercises loading only.

Never: installs, enables or activates anything; touches D:\Hermes-Lab\data; stops or restarts
the Gateway; sets allow_gateway_injection; writes an approval record.
DOCTOR_PASS / VALIDATE_PASS are load checks only, NOT runtime verification of any command.
#>
param(
    [string]$Out = 'D:\Hermes-Lab\universal-port-repair-smoke-v0.4.3',
    [string]$DisposableHome = 'D:\Hermes-Lab\disposable-hermes-home-v0.4.3',
    [switch]$AcknowledgeDoctorExecutesAdapter,
    [string]$ExpectedAdapterSha256 = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = $PSScriptRoot
$realData = 'D:\Hermes-Lab\data'

function Assert-NotRealProfile([string]$path) {
    $full = [System.IO.Path]::GetFullPath($path).TrimEnd('\')
    $real = [System.IO.Path]::GetFullPath($realData).TrimEnd('\')
    if ($full -ieq $real -or $full.StartsWith($real + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use the real Hermes profile or anything inside it: $path"
    }
    if ($full -match '\\data$') { throw "Disposable home must not be named like a real Hermes data folder: $path" }
    if ($env:HERMES_HOME -and ([System.IO.Path]::GetFullPath($env:HERMES_HOME).TrimEnd('\') -ieq $full)) {
        throw "Disposable home equals the current HERMES_HOME: $path"
    }
}

foreach ($p in @($Out, $DisposableHome)) {
    if (Test-Path -LiteralPath $p) { throw "Refusing to reuse existing folder: $p" }
}
Assert-NotRealProfile $DisposableHome
Assert-NotRealProfile $Out

$status = [ordered]@{
    schema               = 'universal-port.windows-smoke-status/2'
    version              = '0.4.3'
    started_utc          = (Get-Date).ToUniversalTime().ToString('o')
    stage                = 'STAGE_1'
    unit_tests           = 'NOT_RUN'
    repair               = 'NOT_RUN'
    adapter_verification = 'NOT_RUN'
    adapter_sha256       = $null
    external_digest_match = 'NOT_RUN'
    approval_status      = $null
    hermes_on_path       = $false
    hermes_version       = $null
    doctor               = 'NOT_RUN'
    doctor_exit_code     = $null
    validate             = 'NOT_RUN'
    validate_exit_code   = $null
    disposable_home      = $DisposableHome
    installed_or_enabled = $false
    runtime_verified     = $false
    note                 = 'NOT_RUN is intentional when a stage was not requested. DOCTOR_PASS/VALIDATE_PASS are load checks only, not runtime verification.'
}
$statusDir = $Out
function Write-Status {
    if (-not (Test-Path -LiteralPath $statusDir)) { New-Item -ItemType Directory -Path $statusDir | Out-Null }
    $status.finished_utc = (Get-Date).ToUniversalTime().ToString('o')
    $status | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $statusDir 'SMOKE_STATUS.json') -Encoding UTF8
}

$previousHome = $env:HERMES_HOME
try {
    # 1. Unit tests
    python -m unittest discover -s "$root\tests" -v
    if ($LASTEXITCODE -ne 0) { $status.unit_tests = 'FAIL'; throw "Unit tests failed (exit $LASTEXITCODE)" }
    $status.unit_tests = 'PASS'

    # 2. Repair the SYNTHETIC fixture (writes ADAPTER_LOCK.json; no approval record)
    python "$root\repair_cli.py" repair "$root\examples\claude-repair-fixture" $Out
    if ($LASTEXITCODE -ne 0) { $status.repair = 'FAIL'; throw "Repair failed (exit $LASTEXITCODE)" }
    $status.repair = 'PASS'
    $repairDir = Join-Path $Out 'repair-repair-fixture'
    python "$root\repair_cli.py" workshop $repairDir
    if ($LASTEXITCODE -ne 0) { throw "Workshop view failed (exit $LASTEXITCODE)" }

    # 3. Whole-folder verification against the lock and the reviewed templates
    $verifyArgs = @("$root\repair_cli.py", 'verify-adapter', $repairDir)
    if ($ExpectedAdapterSha256) { $verifyArgs += @('--expected-sha256', $ExpectedAdapterSha256) }
    $verifyJson = (& python @verifyArgs | Out-String)
    $verifyCode = $LASTEXITCODE
    Write-Host $verifyJson
    if ($verifyCode -ne 0) { $status.adapter_verification = 'FAIL'; throw "Adapter verification failed (exit $verifyCode)" }
    $verify = $verifyJson | ConvertFrom-Json
    $status.adapter_sha256 = $verify.actual_package_sha256
    $status.approval_status = $verify.approval_status
    $status.adapter_verification = 'PASS'
    if ($ExpectedAdapterSha256) { $status.external_digest_match = 'PASS' }
    $adapter = $verify.adapter

    # 4. Stage 2 only on explicit request with an external digest
    if (-not $AcknowledgeDoctorExecutesAdapter -or -not $ExpectedAdapterSha256) {
        Write-Warning ('Stage 1 complete. doctor/validate intentionally NOT_RUN. Review ' + $adapter +
                       ', compare adapter_sha256 ' + $status.adapter_sha256 + ' with the external HANDOFF, then re-run ' +
                       'into NEW folders with -AcknowledgeDoctorExecutesAdapter -ExpectedAdapterSha256 <digest>. ' +
                       'Doctor runs adapter code in-process; HERMES_HOME is not an OS sandbox.')
        return
    }
    $status.stage = 'STAGE_2'

    $hermes = Get-Command hermes -ErrorAction SilentlyContinue
    if (-not $hermes) {
        throw 'hermes is not on PATH: doctor/validate NOT_RUN. Install Hermes in a disposable environment first.'
    }
    $status.hermes_on_path = $true

    New-Item -ItemType Directory -Path $DisposableHome | Out-Null
    $env:HERMES_HOME = $DisposableHome
    # Windows PowerShell 5.1 turns redirected native stderr into terminating errors under
    # ErrorActionPreference=Stop; relax it only around native calls and check exit codes instead.
    $ErrorActionPreference = 'Continue'
    $ver = (& hermes --version 2>&1 | Out-String).Trim()
    $verCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($verCode -ne 0) { throw "hermes --version failed (exit $verCode)" }
    $status.hermes_version = $ver

    $doctorLog = Join-Path $Out 'doctor.log'
    $ErrorActionPreference = 'Continue'
    $previousNoBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & hermes plugins doctor $adapter --ci *> $doctorLog
    $doctorCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    Get-Content -LiteralPath $doctorLog | Write-Host
    $status.doctor_exit_code = $doctorCode
    if ($doctorCode -ne 0) { $status.doctor = 'DOCTOR_FAIL'; throw "hermes plugins doctor failed (exit $doctorCode)" }
    $status.doctor = 'DOCTOR_PASS'

    # Re-run the pre-import gate right before the next import (narrows the check-to-use window).
    & python @verifyArgs | Out-Null
    if ($LASTEXITCODE -ne 0) { $status.adapter_verification = 'FAIL_AFTER_DOCTOR'; throw 'Adapter changed during doctor (pre-import gate failed)' }

    $validateLog = Join-Path $Out 'validate.log'
    $ErrorActionPreference = 'Continue'
    & hermes plugins validate $adapter *> $validateLog
    $validateCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    Get-Content -LiteralPath $validateLog | Write-Host
    $status.validate_exit_code = $validateCode
    if ($validateCode -ne 0) { $status.validate = 'VALIDATE_FAIL'; throw "hermes plugins validate failed (exit $validateCode)" }
    $status.validate = 'VALIDATE_PASS'

    Write-Host 'Stage 2 checks passed. NOTHING INSTALLED OR ENABLED. This is NOT runtime verification.'
} finally {
    $ErrorActionPreference = 'Stop'
    $env:HERMES_HOME = $previousHome
    if (Get-Variable -Name previousNoBytecode -ErrorAction SilentlyContinue) { $env:PYTHONDONTWRITEBYTECODE = $previousNoBytecode }
    Write-Status
    Write-Host ("Status written to " + (Join-Path $statusDir 'SMOKE_STATUS.json'))
}
