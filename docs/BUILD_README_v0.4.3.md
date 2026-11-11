# Hermes Universal Plugin Port v0.4.3 — BYTECODE GATE (candidate)

**Status: OFFLINE-TESTED / HERMES-RUNTIME-UNVERIFIED / NOT READY FOR INSTALLATION.** v0.4.3 closes the P0 found in the review of v0.4.2. A planted `__pycache__/*.pyc` could replace the reviewed adapter code while the digest and approval checks still passed. A **pre-import gate outside the adapter** (`pre_import_gate.py`) now allows only the exact generated file set. It runs before every import path this project controls. `repair_cli.py stage` copies only the locked files into a fresh disposable `HERMES_HOME`.

```bash
python -m unittest discover -s tests -v     # 204 tests (91 original, unchanged), all passing in the build sandbox
```

Read next: `HANDOFF.md`, `LIMITATIONS.md` §10, `VERIFICATION_REPORT.md`, `CHANGELOG.md`. Example outputs: `../reports-v0.4.3/`.

---

# Historical: v0.4.2 — OPERATOR APPROVAL (candidate)

**Status: OFFLINE-TESTED / HERMES-RUNTIME-UNVERIFIED / NOT READY FOR INSTALLATION.** v0.4.2 answers the independent review of v0.4.1:

- **Nothing registers by default.** A statically valid transport (`transport_status`) is not a semantic review (`semantic_review`), and neither is runtime verification. Commands register only after an explicit `repair_cli.py approve ... --i-reviewed-model-induced-effects` (R1).
- **Approvals are bound to the whole adapter folder**, through a digest stored outside it. Editing only the manifest disables registration (R2). `repair_cli.py verify-adapter` checks the folder against the lock, the reviewed templates and an external digest.
- The smoke script runs a no-switch Stage 1 (`NOT_RUN`, not a failure) before any doctor run. The docs no longer claim that injection shows up as a visible turn (R3/R4).

```bash
python -m unittest discover -s tests -v     # 184 tests (91 original, unchanged), all passing in the build sandbox
```

Read next: `HANDOFF.md`, `LIMITATIONS.md`, `VERIFICATION_REPORT.md`, `CHANGELOG.md`. Example outputs: `../reports-v0.4.2/`.

---

# Historical: v0.4.1 — SAFETY HARDENING (candidate)

**Status: OFFLINE-TESTED / HERMES-RUNTIME-UNVERIFIED / NOT READY FOR INSTALLATION.** v0.4.1 is the safety-hardening candidate requested by the independent review of v0.4.0. It keeps the v0.4.0 repair design and closes these gaps:

- **P0-1:** generated adapters register **only** `ADAPTED_STATICALLY` / `ADAPTED_RUNTIME_VERIFIED` / `DIRECT_EQUIVALENT_VERIFIED` commands. `PARTIAL_REVIEW_REQUIRED`, `BLOCKED_UNSAFE`, `UNSUPPORTED` and unknown outcomes are never registered.
- **P0-2:** `--evidence` JSON is a claim. It is recorded as `SELF_REPORTED_UNTRUSTED` and can never promote to `ADAPTED_RUNTIME_VERIFIED`. The promotion gate requires a trusted collector that does not exist yet. Snapshot runtime claims are no longer carried forward by `reconcile`.
- **P1-3:** side effects are split into *adapter-direct* (proven: one user message) and *model-induced* (never proven statically). Destructive, publish/transfer and approval-bypass paraphrases make the dimension `UNKNOWN`. No marker match is never treated as proof. Adversarial fixtures are included.
- **P1-4:** `WINDOWS_REPAIR_SMOKE.ps1` requires `hermes`, checks the adapter code against the reviewed templates, needs `-AcknowledgeDoctorExecutesAdapter` before doctor (which runs `register` in-process), throws on nonzero exit codes, writes `SMOKE_STATUS.json` (`DOCTOR_PASS`/`VALIDATE_PASS`/`NOT_RUN`) and never enables anything.
- **P1-5:** limits are documented in `LIMITATIONS.md`.

```bash
python -m unittest discover -s tests -v     # 162 tests (91 original, unchanged + 71 repair-suite), all passing in the build sandbox
```

Read next: `HANDOFF.md`, `LIMITATIONS.md`, `VERIFICATION_REPORT.md`, `CHANGELOG.md`. Example outputs are in each release's ZIP.

---

# Historical: v0.4.0 — OVERNIGHT PATCH (Compatibility Repair, Phase 1)

**Status: OFFLINE-TESTED / HERMES-RUNTIME-UNVERIFIED.** v0.4.0 goes beyond detection. For Claude Code slash commands (which the official Hermes importer skips), it builds an evidence-driven **repair**: a deterministic native Hermes command adapter that reuses the original command file byte-for-byte and reproduces Claude Code's documented `$ARGUMENTS` semantics. Each command is checked across 8 semantic dimensions and gets a Capability Passport. Nothing is installed automatically. No result in this build is runtime-verified. This is **not** a universal compatibility layer.

### What a repaired command does

`/fix-issue 42` in Hermes → the adapter re-verifies the SHA-256 of the original `fix-issue.md` and of the renderer, renders the body exactly as Claude Code documents (`$ARGUMENTS`, `$0`, `$ARGUMENTS[1]`, named `$issue`, `\$` escapes, `ARGUMENTS:` append), replaces `` !`cmd` `` injections with Claude's own documented *disabled-by-policy* placeholder, and queues the result as **one user message** via `ctx.inject_message`. It runs no shell, calls no tools, writes no files and changes no approvals. Ambiguous inputs are refused, not guessed.

### Outcomes (per command, never a single "success")

`DIRECT_EQUIVALENT_VERIFIED` · `ADAPTED_RUNTIME_VERIFIED` · `ADAPTED_STATICALLY` · `PARTIAL_REVIEW_REQUIRED` · `UNSUPPORTED` · `BLOCKED_UNSAFE`

Results here: synthetic fixture 4 static / 3 partial / 1 blocked / 2 unsupported. Real `git-pr-workflows@4bde316`: 3 partial (approval checkpoints, `Task`, `EnterPlanMode`, git writes and model-invocation are not proven). Runtime-verified: **0**.

### New commands

```text
/universal-port repair <run_id>              # adapters + CAPABILITY_PASSPORT + VERIFICATION_RESULTS (offline, 0 model calls)
/universal-port passport <run_id>            # Olympian Workshop view of the latest repair
/universal-port reconcile <old_run> <new_run> # UPDATE_IMPACT.json for a new upstream revision
```

Offline CLI (no Hermes needed): `python repair_cli.py repair SOURCE OUT [--hermes-version V] [--source-commit SHA] [--evidence FILE]`, `python repair_cli.py reconcile OLD_REPAIR_DIR NEW_SOURCE`, `python repair_cli.py workshop REPAIR_DIR`.

### Verify

```bash
python -m unittest discover -s tests -v     # v0.4.0: 145 tests (see v0.4.1 above for the current count)
```

On Windows, `WINDOWS_REPAIR_SMOKE.ps1` also runs `hermes plugins doctor/validate` on the generated adapter with a **disposable** `HERMES_HOME`. It was not executed in the build environment.

Read next: `HANDOFF.md`, `BASELINE_AUDIT.md`, `VERIFICATION_REPORT.md`, `CAPABILITY_PASSPORT.md`, `UPDATE_RECOVERY.md`, `PATCH_SCOPE.md`, `CHANGELOG.md`. Example outputs: `../reports-v0.4.1/` (v0.4.0's are in the v0.4.0 ZIP).

### Not implemented (roadmap, not current capability)

Runtime verification on a real Hermes; executing or emulating `!` shell injections; `context: fork` subagents; per-command tool pre-approval/removal; model-invocable commands with argument semantics; `@file` attachment; `${CLAUDE_*}` variables; verified `AskUserQuestion`→Hermes approval mapping; actual official-importer replay; non-Claude command sources.

---

# Historical: v0.3.5 — Compatibility Inspection

**Status: OFFLINE-PATCHED / HERMES-RUNTIME-UNVERIFIED.** This release builds on v0.3.4, preserves the strict cost-aware Direct Bridge rules, and adds truthful compatibility visibility. It does **not** claim to repair, install, or certify all skipped official importer features. No private DIAPORIA core is bundled.

### New commands

```text
/universal-port route <run_id>                   # existing strict name-alias cost routing
/universal-port inspect <run_id>                 # capability loss + permission gaps + snapshot
/universal-port compare <old_run_id> <new_run_id> # conservative source/adapter/target diff
```

### New versioned artifacts

- `CAPABILITY_LOSS.json` — identifies original Claude Code commands that the *official importer documents as skipped*, while showing that this port's generated SKILL.md **is not a runtime-equivalent slash command until proven**. Includes host-specific gaps, unported components, a per-command proof gap and conservative permission inventory. No settings rule values are copied.
- `UNDERSTANDING_SNAPSHOT.json` — records source commit, source fingerprint, installed target version (when available), mapping registry hash, SHA-256 command fingerprints and high-level feature gaps. Enables comparing two independently fetched runs without copying source or model reasoning.
- `compare` output — classifies changed, added and removed source commands, adapter changes, permission changes, source commit changes, and target-version/registry changes. Even an unchanged result remains *static-only*, never runtime-certified.

**What this does not yet do:** auto-port Cursor `.mdc` routing semantics, rewrite permission policies, execute live Hermes Hook parity tests, implement full Claude `Task` control flow, or automatically install partial packages. Those are gated follow-on phases. Unsupported source platforms still fail closed. Do not mistake a green unit test for a real plugin compatibility proof.

**Official importer behavior:** https://hermes-agent.nousresearch.com/marketplace/agent-importers ; Hermes plugin API: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins .

**Windows:** the included installer expects the v0.3.5 manifest, stops Gateway only after Doctor/Validate, creates an external backup, checks one enabled plugin, and restarts Gateway. Do not run it while your gateway has important running tasks. It has **not** been exercised against the user's Windows Hermes installation in this patch environment.

**Local check:** `python -m unittest discover -s tests -q` — 91 offline tests passed in this environment as of build.

---

# Hermes Universal Plugin Port v0.3.4 — Historical Cost-Aware Routing Notes

This is a **Hermes-first experimental plugin** for importing user-selected GitHub plugins (Codex, Claude Code, selected OpenClaw). It is not a universal-runtime compatibility guarantee. This historical v0.3.4 release **does not** add private orchestration adapters or refactor the source parser/long-command converter.

## New in v0.3.4: Low-cost vs high-cost *function* routing

**Policy:** A direct bridge is permitted only for a function whose input/return, side effects, permissions, approval, failure behavior and state semantics are already known to be equivalent. Similar-purpose functions are **not** a direct bridge; they go to **AI Integration**. This release does not add DIAPORIA adapters.

- `equivalence_router.py`: deterministic, evidence-bound semantic equivalence classifier; one restricted direct transformer for exact standalone `Tool: NAME` lines outside Markdown code fences. No LLM-generated Python/JS or arbitrary regex transforms are accepted.
- `verified_mappings.json`: **production registry intentionally starts empty (`mappings: []`)**. The mapping is not "verified" because a JSON file claims PASS. Maintainers must run real source-vs-Hermes contract tests, review their evidence, and record the exact foreign source commit + source command SHA-256 + Hermes distribution version. The JSON metadata is a *record* of evidence, not independent proof.
- `/universal-port route <run_id>`: inspect a pinned previously staged run and write `COST_ROUTE.json` with `DIRECT_BRIDGE_ONLY`, `MIXED_DIRECT_AND_AI`, or `AI_INTEGRATION` for each command. This is offline static analysis: no LLM, no foreign code execution, no installation.
- For **direct-only** commands whose all recognized tool labels have trusted, version-matched mappings, the port pipeline applies a deterministic name substitution and **skips the command adaptation model call**. It still flags the whole command for manual review: function alias evidence is not full workflow equivalence.
- If a command has unverified features (e.g. Claude `Task`, `AskUserQuestion`, `$ARGUMENTS`, Git writes) or mixed verified/unverified elements, the existing bounded Adaptive Chunking / LLM Integration path remains active. Mixed commands are **not yet partially rewritten**; the router only labels direct candidates and escalates the complete command conservatively.
- When mapping evidence is missing, stale or incompatible with the source commit, exact command digest or installed Hermes version, the route fails closed to AI Integration. Unknown Hermes version also fails closed. A registry change during resume refuses silent rerouting.
- Reported counts are **classification counts**, not actual billing savings. No measured USD cost or real-world parity certification is claimed.

To inspect your existing run after v0.3.4 installation:

```text
/universal-port route 244e3cef48ed
```

Expect `verified_mapping_count: 0` and `direct_bridge_calls: 0` initially, with remaining unverified constructs in `AI_INTEGRATION`. A zero direct count is intentional until real function contracts are verified. `COST_ROUTE.json` is a research artifact, not a port installation.

### Strict registry record contract

Every trusted mapping must identify its source profile/tool, target tool, restricted syntax (`exact_tool_label_line_v1`), seven semantic-contract dimensions, exact 40-character source commit, exact source-command SHA-256, target Hermes version, and SHA-256 hashes of source contract, target contract and test evidence, plus test-suite name and human reviewer. A malformed or conflicting entry is rejected. The tool does not generate or promote entries from a third-party plugin or LLM output. For now, **there are no bundled real-world direct mappings**.

## Kept from v0.3.3 (unchanged)

- **Native role delegation probe** (`runtime_bridge.py`): resolve a named Agent from the pinned original source, verify it matches the byte-for-byte staged reference, then optionally invoke the actual Hermes `ctx.dispatch_tool('delegate_task', ...)` API. The role definition is supplied as untrusted context, not installed as a Claude subagent.
- **Live user approval**: a real `ctx.ask_choice()` prompt in the synchronous Hermes slash-command handler is required for model dispatch. Missing/cancelled/timed-out picker means **zero delegate calls**. In addition, the command itself requires `--allow-inherited-tools`.
- **Argument-binding preview**: parse caller-tail arguments with quoted-token preservation, and show the invocation that would be sent to the Hermes skill. This does **not** execute the skill.
- **Existing-run repair**: re-running `audit <run_id>` on a v0.3.1-origin run copies pinned foreign Agent source as inert references if missing; no re-download or LLM call.
- **Identity and integrity**: both previews and delegation require a fully analyzed, validated, pinned, uninstalled run. The pinned source fingerprint and byte-identical Agent reference must match. Changes during the approval dialog block dispatch. Local evidence logs contain hashes/metadata, not raw prompts or child responses.
- **Read-only evidence inspection**: `/universal-port bridge-evidence <run_id>` reports the bridge attempts and explicitly never certifies semantic equivalence.
- **Original safety rules unchanged**: no automatic Git commit/push/PR creation; no installation of partial ports; no foreign JS execution; no auto-discovery.

### Critical Hermes limitation: child tool permissions

**Current Hermes `tools/delegate_tool.py::_build_children()` calls the child builder with `toolsets=None`, so the child inherits its parent's toolsets.** Do *not* assume `toolsets` fields in a task object restrict them. The child can have terminal, file-write, and MCP access according to active Hermes configuration. Written “do not modify” instructions are not a security sandbox. The live probe is therefore **explicitly opt-in**, intended ONLY for a disposable workspace with no production credentials or remotes. `delegate_task(background=True)` requests a background subagent, but returning a dispatch handle does not prove child completion.

Official implementation: https://github.com/NousResearch/hermes-agent/blob/main/tools/delegate_tool.py ; plugin API: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins ; delegation: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation

### Commands

For a v0.3.1-origin run, invoke `/universal-port audit <run_id>` **after installing v0.3.4**, before `delegate-preview`; this ensures foreign Agent references exist.

```text
/universal-port <GitHub URL>
/universal-port status <run_id>
/universal-port audit <run_id>
/universal-port route <run_id>
/universal-port args-preview <run_id> <command> -- <raw arguments>
/universal-port delegate-preview <run_id> <foreign-agent-name> -- <text task>
/universal-port delegate-run <run_id> <foreign-agent-name> --allow-inherited-tools -- <text task>
/universal-port bridge-evidence <run_id>
/universal-port cancel <run_id>
/universal-port resume <run_id>
/universal-port install <run_id> --confirm
```

`delegate-preview` and `args-preview` invoke no model, no tools and no Git. `delegate-run` asks the user to choose **Run** or **Cancel**; only **Run** sends the untrusted role reference and task to one `delegate_task` child. An existing partial run remains `VALIDATED_PARTIAL_REVIEW_REQUIRED` even if that child responds. All three imported Claude commands and their write/approval workflow are **not** automatically executable by this release. Creating a role probe is not equivalent to reproducing an entire Claude Code `Task` workflow.

## Historical Windows update from 0.3.3 (for v0.3.4; use v0.3.5 installer now)

1. Save `Hermes-Universal-Port-v0.3.4-COST-ROUTER.zip` under `D:\Downloads`.
2. Exit TUI and confirm no important Gateway task is running. Use **non-admin** PowerShell.
3. Unzip and inspect the installer:

```powershell
Expand-Archive -LiteralPath 'D:\Downloads\Hermes-Universal-Port-v0.3.4-COST-ROUTER.zip' -DestinationPath 'D:\Hermes-Lab' -Force
Get-Content 'D:\Hermes-Lab\hermes-universal-port-v0.3.4\INSTALL_WINDOWS.ps1'
```

4. Run it only after reviewing its effects:

```powershell
& 'D:\Hermes-Lab\hermes-universal-port-v0.3.4\INSTALL_WINDOWS.ps1'
```

The installer validates sources, stops the Gateway gracefully, backs up the existing plugin **outside** `D:\Hermes-Lab\data\plugins`, copies the new code, validates/activates it, verifies that the loader sees *one* enabled v0.3.4, then restarts the Gateway. Prior `plugin-data` runs and Causal Thread are not changed.

5. Confirm from the same PowerShell environment:

```powershell
$env:HERMES_HOME = 'D:\Hermes-Lab\data'
hermes plugins list --plain --no-bundled | Select-String 'universal-plugin-port'
```

Expected row: `enabled user 0.3.4 universal-plugin-port`.

## Validation and scope

Run `python -m unittest discover -s tests -v`. Unit tests use fake Hermes contexts and pinned fixture files: **no live Hermes model calls**. On Windows, `hermes plugins doctor` and `hermes plugins validate` should be run by the installer; their outcome has not been independently observed here.

### Not yet implemented

- Automatic transformation of Claude `Task` blocks into a fully executable Hermes workflow with identical role/tool/permission semantics.
- Per-Git-operation durable approval fences protecting actual commit/push/PR creation.
- Full end-to-end test of the original `git-pr-workflows` commands on a disposable repository.
- Runtime sandbox for untrusted Agents or OpenClaw code; private orchestration backend adapter.

Those gaps remain **Partial**. The next iteration should focus on the actual stage-by-stage Git workflow and hard enforcement of approvals before exposing repository mutations.

## Validation notes for v0.3.4

Run `python -m unittest discover -s tests -q` to verify all offline tests, including synthetic contract fixtures. Those synthetic mappings exercise the decision logic but **do not prove** any actual Claude/Codex/Hermes tool pair is equivalent. Exact host-version matching deliberately requires locally installed `hermes-agent` distribution metadata; if absent, the direct lane remains disabled. Windows Hermes Gateway and the existing run have not been exercised with this build here.
