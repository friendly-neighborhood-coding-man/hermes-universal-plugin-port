# Offline fixtures only. Never installs or enables generated plugins.
$ErrorActionPreference = 'Stop'
$env:HERMES_HOME = 'D:\Hermes-Lab\data'
$root = $PSScriptRoot
$stage = 'D:\Hermes-Lab\universal-port-smoke-v0.3.5'
if (Test-Path $stage) { throw "Smoke output already exists: $stage (won't overwrite)" }
New-Item -ItemType Directory -Path $stage -Force | Out-Null

python -m unittest discover -s "$root\tests" -v
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }

python "$root\port_cli.py" stage "$root\examples\codex-sample" $stage --approve
if ($LASTEXITCODE -ne 0) { throw 'Codex stage failed' }
python "$root\port_cli.py" stage "$root\examples\claude-sample" $stage --approve --allow-partial
if ($LASTEXITCODE -ne 0) { throw 'Claude stage failed' }
# Explicit foreign JS consent is safe ONLY for this bundled synthetic fixture.
python "$root\port_cli.py" stage "$root\examples\openclaw-sample" $stage --approve --execute-foreign
if ($LASTEXITCODE -ne 0) { throw 'OpenClaw stage failed' }

$paths = @(
    "$stage\port-codex-codex-sample",
    "$stage\port-claude-code-claude-sample",
    "$stage\port-openclaw-openclaw-sample"
)
foreach ($p in $paths) {
    hermes plugins doctor $p --ci
    if ($LASTEXITCODE -ne 0) { throw "Doctor failed: $p" }
    hermes plugins validate $p
    if ($LASTEXITCODE -ne 0) { throw "Validate failed: $p" }
}
Write-Host 'All 3 staged fixture packages passed local checks. NO PLUGIN INSTALLED.'
