# Changelog

## 0.4.3-BYTECODE-GATE (candidate) — 2026-11-08

Built from `Hermes-Universal-Port-v0.4.2-OPERATOR-APPROVAL.zip` (SHA-256 `b3eefeed…0748`, unchanged). This release addresses the P0 in the independent review of v0.4.2, which was run on a v0.4.1 tree patched with the v0.4.2 diff. The full diff against v0.4.2 is in `V0.4.3_DIFF.patch`.

### Security fix (P0: ignored bytecode cache bypassed approval and digest)
- Reproduced first on the real v0.4.2 tree. A planted unchecked-hash `__pycache__/__init__.cpython-313.pyc` made the project loader register `CACHE_UNAPPROVED` with no approval. `verify-adapter` still reported `ok: true` with the external digest.
- New **`pre_import_gate.py`**, which runs outside the adapter and never imports it. It allows exactly `ADAPTER_MANIFEST.json`, `__init__.py`, `claude_command.py`, `plugin.yaml` and the manifest-listed `commands/*.md`. It rejects:
  - `__pycache__`, `.pyc`/`.pyo`
  - extension modules (`.so`/`.pyd`) and `.pth`
  - archives and extra `.py` files
  - case variants, unlisted or nested command files
  - symlinks and junctions
- The gate runs first in:
  - `semantic_verification.load_adapter` (our own loader)
  - `verify-adapter` (new `pre_import_gate` field), `approve` and the new `stage`
  - the generation step itself
  - `WINDOWS_REPAIR_SMOKE.ps1`, before doctor and again before validate
- Both digest implementations (`slash_repair._package_files_sha256`, template `package_sha256`) now cover **every** file. There are no `__pycache__` exclusions.
- `ADAPTER_LOCK.json` is schema v2. It adds the exact per-file SHA-256 list; v1 locks are rejected.
- New **`repair_cli.py stage REPAIR_DIR --hermes-home H --i-confirm-disposable-home [--expected-sha256 D]`**. It copies only the locked files, re-hashed, into a **new** `H/plugins/<adapter>`, gates the copy, and copies a VALID approval record. It never overwrites, deletes or enables anything.
- The smoke script runs doctor/validate with `PYTHONDONTWRITEBYTECODE=1`. That variable only stops *writing* caches; the gate stops *reading* planted ones. The template's digest-mismatch message now says that a `__pycache__` counts.

### Tests
- 204 total:
  - 91 original, byte-identical
  - 72 in `test_v040_repair.py`, unchanged
  - 21 in `test_v042_approval.py`: 2 adjusted, because v0.4.2 asserted that `__pycache__` is ignored. `test_pycache_does_not_change_digest` is reversed into `test_pycache_is_rejected_not_ignored`.
  - 20 in the new `test_v043_bytecode_gate.py`
- `BytecodeCachePoCTests` uses only v0.4.2 APIs. **Against v0.4.2, 5 of its 7 tests fail.** The remaining 2 are the guard proving the attack works without a gate, and cache removal. Against v0.4.3 all 7 pass.

### Unchanged
- All outcomes, the renderer, the semantics, the approval model, the evidence trust rules, `verified_mappings.json` (0) and install gating.
- The fixture adapter digest changed only because the template and version strings changed. The new value is in the external handoff.

## 0.4.2-OPERATOR-APPROVAL (candidate) — 2026-11-08

Built from `Hermes-Universal-Port-v0.4.1-SAFETY-HARDENING.zip` (SHA-256 `34a6d479…d541`, unchanged). Addresses the independent review of v0.4.1 (R1–R4). The full diff against v0.4.1 is in `V0.4.2_DIFF.patch`.

### Security fixes
- **R1: transport adaptation was treated as semantic safety.** Passports now carry three separate fields:
  - `integration.transport_status`: `TRANSPORT_STATICALLY_VALID` / `TRANSPORT_INVALID` / `NOT_GENERATED`
  - `integration.semantic_review`: `NOT_REVIEWED` until an operator approves
  - the existing runtime status
  - `registration` is `REQUIRES_OPERATOR_APPROVAL` or `NOT_ELIGIBLE`, and `registered_by_default` is always `false`.
  - **Generated adapters register nothing by default**, including `hollow` and `/summarize`.
  - New `repair_cli.py approve REPAIR_DIR --command NAME --operator NAME --i-reviewed-model-induced-effects` writes an explicit approval for the named commands. There is no approve-all, and `PARTIAL`/`BLOCKED`/`UNSUPPORTED` cannot be approved. Approval is recorded as a human judgment. It is not verification and does not make anything install-ready.
  - The marker vocabulary was **not** expanded.
- **R2: a manifest-only outcome edit enabled a blocked command.**
  - The approval record lives **outside** the adapter folder: `<repair>/universal-port-approvals/<adapter>.json`, or `HERMES_HOME/universal-port-approvals/<adapter>.json` when installed. It binds the approved commands to the SHA-256 of **every** adapter file, manifest included.
  - `register()` refuses to register anything if the folder digest differs. It also requires the manifest outcome to be fully adapted and the command (name + source hash) to be listed.
  - New `ADAPTER_LOCK.json` next to the adapter. New `repair_cli.py verify-adapter REPAIR_DIR [--expected-sha256 D]` checks the folder against the lock, the reviewed templates and an external digest.
  - The fixture adapter digest is published in the external HANDOFF, outside the ZIP. Documented as integrity, not authentication.
- **Platform-independent adapter digest.** The generated `plugin.yaml`/`ADAPTER_MANIFEST.json` are written as LF bytes, and the digest uses explicit POSIX-path order, because `WindowsPath` sorts case-insensitively. Otherwise Windows would compute a different digest than the published one.

### Smoke script and docs
- **R4:** `WINDOWS_REPAIR_SMOKE.ps1` now runs in two stages.
  - Stage 1 (no switches) ends with doctor/validate intentionally `NOT_RUN` and exit 0. It prints the adapter digest.
  - Stage 2 needs `-AcknowledgeDoctorExecutesAdapter` **and** `-ExpectedAdapterSha256`. It verifies the whole folder via `verify-adapter` before doctor.
  - `hermes --version` is recorded. Doctor/validate output goes to `doctor.log`/`validate.log`. Native stderr no longer becomes a terminating error under Windows PowerShell 5.1.
  - The warnings say that `HERMES_HOME` is not an OS sandbox.
- **R3:** the handoff and `LIMITATIONS.md` no longer predict that an injected command appears as a visible next turn.
  - Routing depends on the installed version and runtime mode, and gateway-backed CLI turns may not be displayed.
  - "Queued" never means executed.
  - Step 6 pins `hermes --version`, checks the transcript or logs, and stops (rather than enabling `allow_gateway_injection`) if injection is refused.
  - Passport conditions were reworded to match.

### Tests
- 184 total:
  - 91 original, byte-identical
  - 72 in `test_v040_repair.py`
  - 21 in the new `test_v042_approval.py`
- In `test_v040_repair.py`, 8 tests and one helper were edited, because they assumed default registration or the v0.4.1 smoke-script shape. 1 test was added. Details are in `VERIFICATION_REPORT.md` §1.

### Unchanged
- Outcomes on all fixtures, the renderer, the Claude semantics, the evidence trust rules from v0.4.1, `verified_mappings.json` (0 mappings) and install gating.

## 0.4.1-SAFETY-HARDENING (candidate) — 2026-11-08

Built from `Hermes-Universal-Port-v0.4.0-OVERNIGHT-PATCH.zip` (SHA-256 `8788bff9…ccee2`, unchanged). This release addresses the independent v0.4.0 review. The full diff is in `V0.4.1_DIFF.patch`.

### Security fixes
- **P0-1 — partial commands were registered.** `generated_command_entry.register()` now registers only outcomes in `REGISTRABLE_OUTCOMES` (`ADAPTED_STATICALLY`, `ADAPTED_RUNTIME_VERIFIED`, `DIRECT_EQUIVALENT_VERIFIED`). `PARTIAL_REVIEW_REQUIRED`, `BLOCKED_UNSAFE`, `UNSUPPORTED`, missing, unknown or mis-cased outcomes are skipped. Passports carry `integration.registered_by_default`, and the Workshop and Markdown show "(not registered)".
- **P0-2 — arbitrary JSON evidence could promote to `ADAPTED_RUNTIME_VERIFIED`.** `evaluate_runtime_evidence` now returns `SELF_REPORTED_UNTRUSTED` (or `FAIL`/`INVALID`/`STALE`) with `trust: SELF_REPORTED`, never `PASS`. Promotion and `runtime_behavior_verified` go through the new `runtime_trusted_pass()` gate, which requires `trust == TRUSTED_COLLECTOR`. No code path produces that, and a file cannot claim it. `--evidence FILE` therefore never promotes. `reconcile` no longer trusts a snapshot's runtime PASS: it reports `STILL_BOUND_UNTRUSTED_SNAPSHOT`, caps `carried_outcome` at `ADAPTED_STATICALLY`, always requires runtime re-verification, and `runtime_verified_after_update` is always empty.
- **P1-3 — missing regex markers were treated as proof.** `approval` and `side_effects` are never `PRESERVED_STATIC_VERIFIED`. Side effects are split into `adapter_direct` (`ONE_USER_MESSAGE_VERIFIED_STATIC`) and `model_induced` (always `UNKNOWN*`). New natural-language markers cover destructive wording (delete/remove/wipe/purge/get rid of/clear out/…), publish/transfer wording (push/deploy/send/e-mail/purchase/…) and approval bypass ("without asking", "do not ask", "no confirmation", "immediately", "automatically"). Any match gives `UNKNOWN`, so the command is `PARTIAL` and not registered. New `examples/adversarial-paraphrase-fixture` (9 SYNTHETIC commands, including the reviewer's example and one deliberately evasive case).
- **P1-4 — the smoke script failed open.** `WINDOWS_REPAIR_SMOKE.ps1` was rewritten. It throws if `hermes` is missing, compares the adapter code with the reviewed templates, requires `-AcknowledgeDoctorExecutesAdapter` (doctor imports and runs `register` in-process), throws on any nonzero exit code, always writes `SMOKE_STATUS.json` (`DOCTOR_PASS`/`DOCTOR_FAIL`/`NOT_RUN`, `VALIDATE_PASS`/`VALIDATE_FAIL`/`NOT_RUN`), refuses `D:\Hermes-Lab\data` and anything inside it, and never enables or installs.

### Documentation
- **P1-5:** new `LIMITATIONS.md`. It covers asynchronous `inject_message` and the interrupt queue, gateway permission, unpreserved `allowed-tools`/`disallowed-tools`/`model`/model-only/hooks/fork, no AI transformation (`model_calls: 0`), unchecked third-party plugin collisions, heuristic-only side-effect scanning and untrusted evidence. Invocation conditions in every passport now mention collisions and asynchronous injection.
- `VERIFICATION_REPORT.md`, `README.md`, `PATCH_SCOPE.md`, `CAPABILITY_PASSPORT.md`, `UPDATE_RECOVERY.md` and `HANDOFF.md` were updated. Reports were regenerated as `../reports-v0.4.1/` (adds `adversarial-paraphrase/`).

### Tests
- 162 total: the 91 original tests (byte-identical) plus 71 in `test_v040_repair.py` (v0.4.0 had 54).
- 3 tests were edited and 2 replaced, because the review rejected the behavior they asserted. 19 tests are new. The details are in `VERIFICATION_REPORT.md` §1.

### Unchanged
- Fixture outcomes (4 static / 3 partial / 1 blocked / 2 unsupported), `git-pr-workflows` (3 partial) and update impact are the same as v0.4.0.
- `verified_mappings.json` has 0 mappings. Install gating, the renderer (`claude_command.py`) and the Claude semantics are unchanged. `INSTALL_WINDOWS.ps1` changed only its version strings.

## 0.4.0-OVERNIGHT-PATCH — 2026-11-07

Built from `Hermes-Universal-Port-v0.3.5-COMPATIBILITY-INSPECTION.zip` (SHA-256 `75de6f44…4bdd`).

### Added
- `claude_command.py`: standard-library-only parser and renderer for Claude Code command files. It implements the documented `$ARGUMENTS`, `$ARGUMENTS[N]`, `$N`, `$name`, backslash-escape, append-when-unreceived and single-pass rules. Undocumented forms fail closed.
- `hermes_target.py`: Hermes host facts read from source at commit `a9ff979`, with file blob ids and the 131 built-in command names and aliases.
- `generated_command_entry.py`: fixed, reviewed template for the generated native Hermes adapter. It re-verifies hashes, renders the original body, disables `!` injections using Claude's documented placeholder, and queues one user message via `ctx.inject_message`.
- `slash_repair.py`: understand → adapt → verify → passport pipeline. Picks collision-free command names. Defuses staged SKILL.md shell text.
- `semantic_verification.py`: 8-dimension static classification, adapter behavior checks with a recording fake ctx, AST allowlist, a bound runtime-evidence validator, and the outcome rules.
- `capability_passport.py`: Capability Passport JSON/MD and Understanding Snapshot v2.
- `update_reconciliation.py`: `UPDATE_IMPACT.json`.
- `importer_comparison.py`: documentation-based official importer comparison, with a reproduction procedure.
- `workshop_view.py`: Olympian Workshop terminal view of real pipeline state.
- `repair_cli.py`: offline CLI (`repair`, `reconcile`, `workshop`).
- New `/universal-port` subcommands: `repair <run_id>`, `passport <run_id>`, `reconcile <old> <new>`.
- Fixtures: `examples/claude-repair-fixture` (10 commands), `examples/update-fixture/rev-a|rev-b`. Golden cases: `semantics/claude_argument_cases.json`.
- `tests/test_v040_repair.py`: 54 tests.
- `WINDOWS_REPAIR_SMOKE.ps1`: doctor/validate against a disposable `HERMES_HOME` (not executed here).

### Security
- Staged SKILL.md files (from `port_core.stage` and `/universal-port` runs) no longer carry executable `` !`cmd` `` text. Previously, Hermes' optional `skills.inline_shell` could have run it.
- Generated adapters prepend a provenance line, so caller text such as `/yolo` can never become a Hermes slash command.
- `disallowed-tools` commands are `BLOCKED_UNSAFE`. Hermes cannot remove tools per command.

### Changed
- `plugin.yaml` version 0.4.0. `INSTALL_WINDOWS.ps1` version strings updated (logic unchanged; stale "Expected 0.3.4" message fixed).

### Unchanged on purpose
- `verified_mappings.json` still has **0** mappings. Direct-bridge rules, `install` gating, the delegate probe and the v0.3.5 inspect/compare commands are unchanged. All 91 original tests pass unmodified.
