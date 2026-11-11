# HANDOFF — Hermes Universal Plugin Port v0.4.3-BYTECODE-GATE (candidate)

Prepared 2026-11-08 in the cloud build sandbox in response to the independent review of v0.4.2. That review used a v0.4.1 tree patched with the v0.4.2 diff, because the v0.4.0 ZIP had been uploaded by mistake. Nothing was pushed, published, installed, approved or deployed. No access to your machine was requested or used.

## Which file to upload for review

| Release | File in `HERMES_HACKATHON/` | ZIP SHA-256 |
|---|---|---|
| **v0.4.3 (this one)** | **`Hermes-Universal-Port-v0.4.3-BYTECODE-GATE.zip`** | in the external `Hermes-Universal-Port-v0.4.3-HANDOFF.md` and `…zip.sha256` |
| v0.4.2 | `Hermes-Universal-Port-v0.4.2-OPERATOR-APPROVAL.zip` | `b3eefeed20235567a9709e0934dffe6691c1259a3f4cc0890d6ac87e05710748` |
| v0.4.1 | `Hermes-Universal-Port-v0.4.1-SAFETY-HARDENING.zip` | `34a6d47953850cda2efc95aecc9fb4b977055644dcb7b2e0c28b1c29d66fd541` |
| v0.4.0 | `Hermes-Universal-Port-v0.4.0-OVERNIGHT-PATCH.zip` | `8788bff90ea58634f401d4ed428c3eeb6695a4afe9aa398649ff45d9195ccee2` |

Earlier ZIPs are unchanged. Before uploading, check the hash with `Get-FileHash -Algorithm SHA256 <zip>`.

## Deliverable

| Item | Value |
|---|---|
| Fixture adapter digest | `752db7c4e5180eb3fe190ed41cd06b6297422f646272781b9ed7bdc9427ee636`, the folder digest of `repaired-repair-fixture` generated from `examples/claude-repair-fixture`. **Use the copy in the external handoff.** |
| Built from | `Hermes-Universal-Port-v0.4.2-OPERATOR-APPROVAL.zip` (hash above) |
| Layout | `hermes-universal-port-v0.4.3/`, `reports-v0.4.3/`, `V0.4.3_DIFF.patch` (`diff -ruN` against v0.4.2), `HANDOFF.md` |

## The P0 and its fix

- **Reproduced first on the real v0.4.2 tree.** A planted unchecked-hash `__pycache__/__init__.cpython-313.pyc` made the project loader register `CACHE_UNAPPROVED` with no approval. `verify-adapter` still said `ok: true`, with the matching external digest.
- **Fix:** a new pre-import gate (`pre_import_gate.py`) **outside the adapter**. It allows only the exact generated file set and never imports anything. It runs:
  - before our loader
  - inside `verify-adapter` (`pre_import_gate: PASS/FAIL`), `approve` and `stage`
  - during generation
  - in the smoke script, before doctor and again before validate
- Digests now cover every file, and the lock lists every file.
- **Clean staging:** `repair_cli.py stage` copies only the locked files into a **new** `HERMES_HOME/plugins/<adapter>`. Run Hermes with `PYTHONDONTWRITEBYTECODE=1`, and re-run `verify-adapter --adapter <staged>` right before each start.
- **Regression:** `BytecodeCachePoCTests` uses only v0.4.2 APIs. 5 of its 7 tests fail on v0.4.2. All 7 pass on v0.4.3.
- **Limits** (`LIMITATIONS.md` §10):
  - A pass only describes the folder at the moment of the check.
  - Only the adapter folder is covered, not the rest of Hermes' import path.
  - Not yet tested against Hermes' real loader.
  - SHA-256 plus a self-written approval is integrity, not authentication.

## Tests

`python -m unittest discover -s tests -v` → **204 run, 204 passed** (Linux, Python 3.13.18):
- 91 original, unchanged
- 72 in `test_v040_repair.py`, unchanged
- 21 in `test_v042_approval.py`, 2 adjusted
- 20 in the new `test_v043_bytecode_gate.py`

The suite was re-run from a clean extraction of the final ZIP.

## What is verified

Static only. **Nothing is runtime-verified, nothing is registered, nothing is install-ready.** Outcomes are unchanged from v0.4.2:
- Fixture: 4 need approval, 3 PARTIAL, 1 BLOCKED, 2 UNSUPPORTED.
- Adversarial fixture: 2 need approval, 7 PARTIAL.
- `git-pr-workflows`: 3 PARTIAL.

## Not done here, and why

No Hermes, Windows or PowerShell in the build sandbox, and installing Hermes there was denied. Doctor/validate, Hermes' real plugin loader, the runtime observation and the importer A/B were **not run**. `INSTALL_WINDOWS.ps1` changed only its version strings. **Do not enable on a real profile.**

Per the review, steps 4–5 should wait until the v0.4.3 ZIP itself has been independently reviewed.

## Step 4 — smoke check (Windows, disposable)

In a non-admin PowerShell, in the extracted `hermes-universal-port-v0.4.3` folder:

```powershell
# Stage 1: no switches. Doctor/validate are intentionally NOT_RUN; the script exits 0 and prints adapter_sha256.
.\WINDOWS_REPAIR_SMOKE.ps1
# Compare adapter_sha256 (and "pre_import_gate": "PASS") with the EXTERNAL handoff, then review
#   D:\Hermes-Lab\universal-port-repair-smoke-v0.4.3\repair-repair-fixture\adapter\repaired-repair-fixture

# Stage 2: only after that review, into new folders.
.\WINDOWS_REPAIR_SMOKE.ps1 -Out D:\Hermes-Lab\universal-port-repair-smoke-v0.4.3-s2 `
    -DisposableHome D:\Hermes-Lab\disposable-hermes-home-v0.4.3-s2 `
    -AcknowledgeDoctorExecutesAdapter -ExpectedAdapterSha256 <external digest>
```

Doctor imports the adapter in-process, and `HERMES_HOME` is not an OS sandbox. With no approval, the adapter registers nothing. Keep `SMOKE_STATUS.json`, `doctor.log`, `validate.log` and the recorded `hermes_version`.

## Step 5 — benign `/summarize` observation and importer A/B (disposable only)

Never use `D:\Hermes-Lab\data`, your Gateway or production credentials.

1. Run `hermes --version` and write the result down.
2. Configure a **non-production** model provider (a local model or a capped throwaway key) in a new disposable home. The `stage` step below creates the plugin folder inside it. Any cost is yours to decide.
3. **Approve exactly one command** after reading `commands/summarize.md`:
   ```powershell
   $rep  = 'D:\Hermes-Lab\universal-port-repair-smoke-v0.4.3-s2\repair-repair-fixture'
   $dhome = 'D:\Hermes-Lab\disposable-runtime-v0.4.3'     # must not contain plugins\repaired-repair-fixture yet; not $home ($HOME is read-only)
   python .\repair_cli.py approve $rep --command summarize --operator Eric --i-reviewed-model-induced-effects --expected-sha256 <external digest>
   ```
4. **Stage cleanly, then gate right before starting Hermes:**
   ```powershell
   python .\repair_cli.py stage $rep --hermes-home $dhome --i-confirm-disposable-home --expected-sha256 <external digest>
   $env:HERMES_HOME = $dhome
   $env:PYTHONDONTWRITEBYTECODE = '1'      # stops Hermes' Python from writing __pycache__ into the adapter
   $gate = { python .\repair_cli.py verify-adapter $rep --adapter "$dhome\plugins\repaired-repair-fixture" --expected-sha256 <external digest>; if ($LASTEXITCODE -ne 0) { throw 'pre-import gate failed' } }
   & $gate                                  # before enable (enable may import the plugin)
   hermes plugins enable repaired-repair-fixture
   hermes plugins list --plain --no-bundled
   & $gate                                  # again, immediately before starting Hermes
   hermes
   ```
   Do **not** set `allow_gateway_injection`. Run `& $gate` before **every** later Hermes start.
5. **Observe:**
   - `/summarize`: record the exact reply. `Queued …` means accepted, not executed. Then check the transcript or logs for a user message that starts with `[Ported Claude Code command /summarize`. Do not assume it will be visible in your client.
   - If the reply is `NOT SENT … allow_gateway_injection …`, stop and record it.
   - `/fix-issue 42`, `/commit`: these should be unknown commands.
   - After quitting Hermes, run `& $gate` again. If it reports `__pycache__`, Hermes' loader wrote a cache despite the variable. **Record that.** It is an important finding about the real loader.
6. **Importer A/B (optional):** in a second new disposable home, follow `reproduction_procedure` in `reports-v0.4.3/fixture-repair/OFFICIAL_IMPORTER_COMPARISON.json` (dry-run).
7. **Clean up:** `Remove-Item Env:HERMES_HOME, Env:PYTHONDONTWRITEBYTECODE`, then delete the disposable folders yourself.

Everything you record stays `SELF_REPORTED_UNTRUSTED`, and `ADAPTED_RUNTIME_VERIFIED` stays unreachable.

## Recommended next steps

1. Independent review of **this ZIP** (upload `Hermes-Universal-Port-v0.4.3-BYTECODE-GATE.zip` and check its SHA-256).
2. Steps 4–5 on Windows, especially whether Hermes' real loader writes or reads `__pycache__` in plugin folders.
3. Authenticated provenance (a signed release or attestation) and a trusted runtime collector, both reviewed before any promotion path.

## Not included

No credentials, `.env`, personal config, Hermes runtime data, caches (no `__pycache__` anywhere in the ZIP), approval records, third-party `git-pr-workflows` command files, or DIAPORIA internals.
