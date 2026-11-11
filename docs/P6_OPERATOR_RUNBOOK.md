# P6 v0.6.0: operator runbook

## Status as of 2026-11-11

| Step | Result | Evidence |
|---|---|---|
| Offline tests | **Done.** Windows 360 OK (3 skipped). Clean Ubuntu Python 3.12: 360 OK (2 skipped). | §1 |
| Pinned fetch and staging | **Done.** All 14 local files independently match upstream git blobs at `e605d8dd…`. | §2; `docs/evidence/p6-final-review/upstream-tree-e605d8dd.txt` |
| Doctor and validate on the stage | **PASS** | §3 |
| Deterministic mapping engine | **Run read-only on the stage, 0 model calls.** | §6; `docs/P6_COMPAT_ENGINE.md` |
| Install into the disposable home | **Done**, verbatim stage | §7 |
| Runtime resolution checks | **PASS** | §7; `docs/evidence/p6-runtime/` |
| Three-Skill E2E | **Executed once and accepted** as functional evidence | §8; `docs/evidence/p6-e2e-run-001/` |

Cross-host semantic equivalence is **not established**. See `docs/final-review/SEMANTIC_FIDELITY_REPORT.md`.

GitHub Actions run `42866486105` is `BILLING_BLOCKED / NOT_EXECUTED`. It is neither a pass nor a failure.

This runbook is for the dedicated disposable P6 profile `D:\Hermes-Lab\uvp-p6-hermes-test` only. Never use the P5 profile `D:\Hermes-Lab\uvp-v050-hermes-test` or production `D:\Hermes-Lab\data`. The old `UPDATE_TEST_UVP.ps1` is v0.5.6-specific and is disabled on this branch.

> Repair note (2026-11-11): commit `f55a966` had spliced §4 and §5 into the middle of the §4a code block and duplicated both sections. This version restores the code block and keeps one copy of each section. The commands are unchanged.

## 1. Prepare isolated checkout and run tests

~~~powershell
$repo = 'D:\Hermes-Lab\uvp-v050-routing-core'
$p6 = 'D:\Hermes-Lab\uvp-p6-foreign-multiskill'
git -C $repo fetch origin feat/uvp-p6-foreign-multiskill
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
if (Test-Path -LiteralPath $p6) { throw 'P6 worktree exists; inspect before updating' }
git -C $repo worktree add --detach $p6 origin/feat/uvp-p6-foreign-multiskill
if ($LASTEXITCODE -ne 0) { throw 'Worktree creation failed' }
Set-Location $p6
$env:UVP_ENABLE_ARXIV_EXECUTION = '0'
python -m unittest discover -s tests -p 'test_uvp_p6_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'P6 focused tests failed' }
python -m unittest discover -s tests -p 'test_compat_engine.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Compat engine tests failed' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Full regression failed' }
hermes plugins doctor $p6 --ci
if ($LASTEXITCODE -ne 0) { throw 'P6 UVP Doctor failed' }
~~~

Use `python -m unittest discover -s tests -p <file>`. Running `python -m unittest tests.<name>` fails to import, because `tests/` is not a package.

## 2. Fetch exact foreign source and stage, without execution

Pinned upstream:
https://github.com/anthropics/knowledge-work-plugins/tree/e605d8ddbfb688da57dfaaceebd93f12a64ef1d3/product-management

~~~powershell
Set-Location $p6
$sourceRoot = 'D:\Hermes-Lab\p6-foreign-source'
$stageRoot = 'D:\Hermes-Lab\p6-staged'
python .\uvp_p6_cli.py fetch --output $sourceRoot --confirm P6_FETCH_PINNED_SOURCE
if ($LASTEXITCODE -ne 0) { throw 'Pinned fetch failed' }
~~~

Copy the exact `source_path` from the successful JSON output, and verify that `commit_sha` is `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3`.

~~~powershell
$sourcePath = '<EXACT source_path FROM FETCH RESULT>'
python .\uvp_p6_cli.py stage --source $sourcePath --output $stageRoot --commit e605d8ddbfb688da57dfaaceebd93f12a64ef1d3 --confirm P6_STAGE_SKILLS_ONLY_PARTIAL
if ($LASTEXITCODE -ne 0) { throw 'Inert staging failed' }
~~~

- Original Skill Markdown is kept byte-for-byte in `original/`.
- The generated Hermes registration is static.
- Upstream MCP/OAuth connectors are NOT installed or authenticated, and the status is `SKILLS_ONLY_PARTIAL`.

**Independent upstream link (optional, read-only network).** Compare each local file's git blob SHA with the upstream tree:

~~~bash
gh api "repos/anthropics/knowledge-work-plugins/git/trees/e605d8ddbfb688da57dfaaceebd93f12a64ef1d3?recursive=1" \
  --jq '.tree[]|select(.path|startswith("product-management/"))|select(.type=="blob")|.path+" "+.sha'
# then, inside <stage>/original:  git hash-object <file>   (must equal the listed sha)
~~~

**Attribution.** The upstream product-management package is Apache-2.0, and its `LICENSE` is kept in `original/LICENSE`. There is no upstream `NOTICE` file. The staged Skills are verbatim copies. Any modified copy, such as the deterministic mapping output in §6, must state that it was changed before it is redistributed. See `docs/final-review/ATTRIBUTION_AND_LICENSE.md`.

## 3. Validate inert staged plugin first

~~~powershell
$stagedPath = '<EXACT staged_path FROM STAGE RESULT>'
hermes plugins doctor $stagedPath --ci
if ($LASTEXITCODE -ne 0) { throw 'Staged Doctor failed' }
hermes plugins validate $stagedPath
if ($LASTEXITCODE -ne 0) { throw 'Staged validate failed' }
~~~

Do not install or enable anything before reviewing the staged artifact. Review its `PORTING_REPORT.json`, `SOURCE_HASHES.json`, the original Skill files and `REVIEW_REQUIRED.md`. Do not automatically install dependencies.

## 4a. Provision a brand-new disposable P6 Hermes home (UVP itself)

**Do not copy or reconfigure production/P5 homes.** If the dedicated P6 home already exists, STOP and inspect it separately.

~~~powershell
$p6Repo = 'D:\Hermes-Lab\uvp-p6-foreign-multiskill'
$p6Home = 'D:\Hermes-Lab\uvp-p6-hermes-test'
if (Test-Path -LiteralPath $p6Home) { throw 'P6 home exists; refuse overwrite' }
if (-not (Select-String -LiteralPath (Join-Path $p6Repo 'plugin.yaml') -Pattern '^version:\s*0\.6\.0\s*$' -Quiet)) {
    throw 'Wrong UVP version'
}
if (git -C $p6Repo status --porcelain) { throw 'Dirty P6 source; do not install' }
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect P6 worktree' }
New-Item -ItemType Directory -Path (Join-Path $p6Home 'plugins') -Force | Out-Null
$target = Join-Path $p6Home 'plugins\universal-plugin-port'
robocopy $p6Repo $target /E /XD .git .github tests __pycache__ .venv .pytest_cache /XF *.pyc | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'UVP copy failed' }
$env:HERMES_HOME = $p6Home
$env:UVP_ENABLE_ARXIV_EXECUTION = '0'
hermes plugins doctor $target --ci
if ($LASTEXITCODE -ne 0) { throw 'New P6 profile plugin Doctor failed' }
~~~

This creates a **new test-profile-local copy only**. It is not a production deployment and grants no permissions. Confirm any Hermes first-run setup interactively, and do not copy auth or credentials from production. Only after a user-initiated approval and inspection of the plugin:

~~~powershell
hermes plugins enable universal-plugin-port
if ($LASTEXITCODE -ne 0) { throw 'P6 UVP enable failed' }
~~~

If the new home has no model configuration, configure it through Hermes's supported setup and secrets workflow, or stop. Credentials are never migrated silently.

## 4. AI exact-delta review (optional fallback; makes model calls)

With UVP enabled in the disposable profile, these explicit slash actions exist:

~~~text
/uvp --p6-preflight
/uvp --p6-adapt synthesize-research <stagedPath> --approve-model-call
/uvp --p6-adapt write-spec <stagedPath> --approve-model-call
/uvp --p6-adapt roadmap-update <stagedPath> --approve-model-call
~~~

Each adapt action makes one Hermes-managed LLM request and creates only an exact-delta candidate; the real staged Skill stays unchanged. Review each proposed MD and JSON file, then approve that candidate's exact digest and a fresh Hermes choice. For example:

~~~text
/uvp --p6-apply write-spec <CANDIDATE_SHA256> <stagedPath> --approve-reviewed
~~~

- `--p6-apply` modifies STAGING ONLY and never installs anything.
- It now also requires the independent post-proposal checks and the rejected-candidate ledger (`p6_candidate_ledger.json`) to pass.
- The first real candidate for `write-spec` (`676ead16…51a8`) is recorded as REJECTED and cannot be applied.
- Run the deterministic engine (§6) first. For this package it leaves **0** AI-eligible residuals.

## 5. Domain defaults (optional)

With the foreign plugin installed and enabled (§7), `skills_list` must include:

- `ported-product-management:synthesize-research`
- `ported-product-management:write-spec`
- `ported-product-management:roadmap-update`

~~~text
/uvp --p6-defaults
/uvp --p6-defaults-undo
~~~

These ask separately for research, documents and planning. Choosing a default never grants execution or network rights. Run 001 **did not change** any defaults.

## 6. Deterministic compatibility mapping (no model calls)

~~~powershell
python compat_cli.py map --stage <stagedPath> --output D:\Hermes-Lab\p6-compat-run-NNN
python compat_cli.py check-candidates --stage <stagedPath>
~~~

This reads the stage only. It writes mapped review candidates and `COMPAT_REPORT.json`/`.md` into a NEW directory. Run 001 report: `docs/evidence/p6-compat-run-001/`.

## 7. Install the verbatim stage and verify runtime resolution (no model calls)

Use the disposable home's own Hermes interpreter (`installs\<id>\environments\<env>\venv\Scripts\python.exe`):

~~~powershell
$env:HERMES_HOME = 'D:\Hermes-Lab\uvp-p6-hermes-test'
$py = '<disposable venv python.exe>'
& $py -I .\scripts\p6_runtime_verify.py preflight --output D:\Hermes-Lab\p6-runtime-preflight-NNN.json
# backup, then copy the validated stage (exclude caches and review candidates)
Copy-Item "$env:HERMES_HOME\config.yaml" D:\Hermes-Lab\backups\p6-runtime-install-NNN\config.yaml
robocopy <stagedPath> "$env:HERMES_HOME\plugins\ported-product-management" /E /XD __pycache__ P6_REVIEW_CANDIDATES
hermes plugins enable ported-product-management
& $py -I .\scripts\p6_runtime_verify.py verify --output D:\Hermes-Lab\p6-runtime-verify-NNN.json
~~~

`verify` must report STRUCTURAL PASS and RESOLUTION PASS. SEMANTIC is always `NOT_TESTED` there.

**Rollback:**

~~~powershell
hermes plugins disable ported-product-management
Remove-Item -Recurse "$env:HERMES_HOME\plugins\ported-product-management"
Copy-Item D:\Hermes-Lab\backups\p6-runtime-install-NNN\config.yaml "$env:HERMES_HOME\config.yaml"
~~~

Rollback is documented but was **not exercised** live, because the plugin remains installed for the demo.

## 8. Three-Skill E2E (one paid model run; separate approval)

Hardening to apply **before** any rerun. These were not in effect for run 001; see `docs/final-review/RUNTIME_PERMISSION_AUDIT.md`.

1. Set `HERMES_WRITE_SAFE_ROOT=<run dir>` in the environment of the **gateway** process, then restart the disposable gateway. A client-shell value does not reach gateway-hosted turns.
2. Set `agent.run_budget_seconds` in the disposable `config.yaml`. `--run-budget` is rejected by the gateway CLI.
3. Record before/after hashes of `plugins/`, `skills/` and `config.yaml`.

~~~powershell
$R = 'D:\Hermes-Lab\p6-e2e-run-NNN'
# prompt generated from the live catalog via the /uvp recipe (see docs/evidence/p6-e2e-run-001/make_prompt.py)
hermes chat --query-file "$R\prompt.txt" --oneshot --format stream-json --in $R -t 'skills,file' --max-turns 40 2> "$R\stderr.txt" > "$R\stream.jsonl"
~~~

Call it E2E PASS ONLY when the trace shows:

- three distinct successful `skill_view` calls of the namespaced Skills;
- the three artifact files written, with hashes recorded by the harness (the model has no hash tool);
- interview-ID grounding;
- no drift in Skills or config.

Staging, a recipe or a route plan is NEVER proof of execution. There is no claim of Claude connector compatibility or of a Direct Bridge.
