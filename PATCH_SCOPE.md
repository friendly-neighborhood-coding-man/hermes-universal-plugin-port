# v0.4.3 Patch Scope (pre-import bytecode gate)

## Changed in v0.4.3

- New `pre_import_gate.py`: exact-tree allowlist scan and preflight against `ADAPTER_LOCK.json` and the external digest. It never imports anything.
- `semantic_verification.load_adapter`: gate first.
- `operator_approval.py`: lock schema v2 (per-file list), `verify_adapter` via the gate, new `stage()`.
- `slash_repair.py`, `generated_command_entry.py`: digests cover every file (no `__pycache__` exclusion). Version 0.4.3.
- `repair_cli.py`: `stage` subcommand. `WINDOWS_REPAIR_SMOKE.ps1`: `PYTHONDONTWRITEBYTECODE=1` and the gate again before validate.
- Tests: new `tests/test_v043_bytecode_gate.py` (20); 2 tests adjusted in `tests/test_v042_approval.py`.
- Docs: `LIMITATIONS.md` §10, `HANDOFF.md`, `VERIFICATION_REPORT.md`, `CHANGELOG.md`, `README.md`, `CAPABILITY_PASSPORT.md`.

## Boundaries (unchanged)

Nothing is installed, enabled, activated or approved automatically. No foreign code is executed. `verified_mappings.json` is still empty. No runtime evidence was fabricated.

## Still deferred

1. Re-test the gate against Hermes' real plugin loader on the pinned version (Windows, disposable).
2. Steps 4–5 in `HANDOFF.md`.
3. Authenticated release provenance (signatures or attestations) and a trusted runtime collector.

---

# Historical: v0.4.2 Patch Scope (operator approval and adapter digest binding)

## Changed in v0.4.2

- `generated_command_entry.py`: `register()` needs an external approval record bound to `package_sha256()` of the whole folder (R1/R2). The renderer is checked first.
- New `operator_approval.py`: `ADAPTER_LOCK.json`, `verify_adapter()`, `approve()`, plus the transport and registration status helpers.
- `slash_repair.py`: writes the lock, writes the adapter text files as LF bytes, and hashes in a platform-independent order. Engine version 0.4.2.
- `capability_passport.py`, `workshop_view.py`: `transport_status`, `semantic_review` and `registration` fields, plus "(needs operator approval)" and "(not registered)" labels.
- `semantic_verification.py`: invocation and state conditions reworded (R3).
- `repair_cli.py`: `verify-adapter` and `approve` subcommands.
- `WINDOWS_REPAIR_SMOKE.ps1`: two stages, external digest required before doctor, logs (R4).
- Docs: `LIMITATIONS.md`, `HANDOFF.md`, `VERIFICATION_REPORT.md`, `CAPABILITY_PASSPORT.md`, `README.md`, `CHANGELOG.md`.
- Tests: new `tests/test_v042_approval.py` (21) and adjusted `tests/test_v040_repair.py`.

## Boundaries (unchanged)

Nothing is installed, enabled, activated or approved automatically. No foreign code is executed. `verified_mappings.json` is still empty. No runtime evidence was fabricated. Gateway injection is never enabled. No DIAPORIA internals.

## Still deferred (user work, disposable profile only)

1. `WINDOWS_REPAIR_SMOKE.ps1` Stage 1, then Stage 2 after review (Windows).
2. A benign `/summarize` observation after an explicit approval in a disposable profile (`HANDOFF.md` step 6). It is recorded as self-reported.
3. Official `agent-importers` A/B on the same fixture.
4. Signed releases or immutable attestations, and a trusted runtime collector. Both are design work that needs review.

---

# Historical: v0.4.1 Patch Scope (safety hardening)

## Changed in v0.4.1

- `generated_command_entry.py`: `REGISTRABLE_OUTCOMES` allowlist in `register()` (P0-1).
- `semantic_verification.py`: evidence files are `SELF_REPORTED_UNTRUSTED`, `runtime_trusted_pass()` promotion gate (P0-2), conservative approval/side-effects classification with an adapter-direct/model-induced split (P1-3), extra invocation conditions (P1-5).
- `slash_repair.py`: natural-language destructive, publish/transfer and approval-bypass markers. Engine version 0.4.1.
- `update_reconciliation.py`: snapshot runtime claims are `STILL_BOUND_UNTRUSTED_SNAPSHOT` and never carried forward as verified.
- `capability_passport.py`, `workshop_view.py`: `registered_by_default` flag and a "(not registered)" marker.
- `repair_cli.py`: help text says evidence is self-reported only.
- `WINDOWS_REPAIR_SMOKE.ps1`: rewritten fail-closed (P1-4).
- New: `LIMITATIONS.md`, `examples/adversarial-paraphrase-fixture/` (9 SYNTHETIC commands), 19 new tests.
- Version strings: `plugin.yaml`, `INSTALL_WINDOWS.ps1`.

## Boundaries (unchanged)

Nothing is installed, enabled or activated. No foreign code is executed. `verified_mappings.json` is still empty. No runtime evidence was fabricated. Gateway injection is never enabled. No DIAPORIA internals.

## Still deferred (user work, disposable profile only)

1. `WINDOWS_REPAIR_SMOKE.ps1` on Windows (doctor/validate).
2. A `/summarize`-style runtime observation in a disposable Hermes profile (see `HANDOFF.md` step 6). It is recorded as self-reported until a trusted collector exists.
3. Official `agent-importers` replay on the same fixture.

---

# Historical: v0.4.0 Patch Scope & Security Boundaries

## Implemented in this package

- Phase 1: deterministic Claude Code slash-command repair (`slash_repair.py`, `claude_command.py`, `generated_command_entry.py`, `hermes_target.py`). Six explicit outcomes. Original files reused byte-for-byte. Fixed reviewed adapter template. No model calls.
- Phase 2: 8-dimension static verification with a recording fake Hermes context, an AST allowlist, documented golden cases, and a separate bound runtime-evidence validator (`semantic_verification.py`).
- Phase 3: Capability Passport JSON/MD and Understanding Snapshot v2 (`capability_passport.py`).
- Phase 4: update-aware reconciliation, `UPDATE_IMPACT.json` (`update_reconciliation.py`).
- Phase 5: **documentation-based** official importer comparison (`importer_comparison.py`). The importer was not executed.
- Phase 6: Olympian Workshop terminal view (`workshop_view.py`).
- Security fix: staged SKILL.md never carries executable `` !`cmd` `` text.

## Hard boundaries (unchanged or tightened)

- Nothing is installed, enabled or activated by repair/passport/reconcile. `install` still requires a fully validated non-partial run. A repaired run keeps its prior status.
- No foreign code is executed. Adapters never run shell, tools or models. They only queue one user message.
- `verified_mappings.json` remains empty. No verification records were invented.
- Runtime evidence must come from a disposable profile without production credentials. It is bound to exact hashes and to the installed Hermes version.
- Gateway injection requires a Hermes setting (`allow_gateway_injection`) that this tool never writes.
- No private DIAPORIA code, Change Journal, Failure Intelligence or orchestration was used or reconstructed.

## Deferred (requires user approval or a different environment)

1. Real Hermes runtime verification of generated adapters (disposable profile).
2. `hermes plugins doctor/validate` on generated adapters (Windows script provided, not run).
3. Actual official `agent-importers` replay on the same fixture.
4. Bounded AI adaptation for `PARTIAL_REVIEW_REQUIRED` gaps (not attempted, to spend nothing).

---

# Historical: v0.3.5 Patch Scope

## Implemented in this package

- Offline source-to-staged capability loss inventory, including official Claude Code slash-command import gap, using the existing pinned source tree.
- Explicit preservation of uncertainty: a generated Hermes SKILL.md is **not** treated as equivalent to a source slash command, and verified individual tool aliases do not certify full workflows.
- Conservative Claude permission inspection for `allow`, `ask`, `deny` and other policy keys; reports only counts, safe key categories and SHA-256 digests (never raw rule strings).
- Deterministic metadata-only understanding snapshots and source/target diff between two separate pinned runs.
- Fail-closed installation guard when the loss inventory detects unverified functionality.
- Seven additional offline unit tests on top of the prior 84, including secret-free reports and symlink defense.

## Deferred behind explicit gates

1. **Hermes runtime integration:** execute synthetic target and foreign-source fixture in disposable isolated environments; test inputs, outputs, error propagation, side effects, permissions, approval, and state before any claim of semantic equivalence.
2. **Official importer baseline replay:** run its pinned version against the same concrete fixture and compare outputs; the current report cites official docs, not a replay.
3. **Minimal code adaptation:** add generated native adapters only for narrowly identified missing features, with source hashes and reproducible tests; keep untrusted executable code quarantined.
4. **Update recovery:** verify generated adapters against two actual upstream releases with no secrets or remote write permissions.
5. **Hermes-first UI / Dot mythology:** informational, UI-only state characters; the UI must never replace verification evidence.

No real model, remote repository mutation, third-party JS, Hermes gateway or installer was invoked while building this release. No private orchestration or learning-system internals were embedded.

## Inspect

`/universal-port inspect RUNID` -> `CAPABILITY_LOSS.json` and `UNDERSTANDING_SNAPSHOT.json`

`/universal-port compare OLD NEW` -> `REVIEW_REQUIRED` or `SOURCE_AND_ADAPTER_UNCHANGED_STATIC_ONLY`. Neither status certifies runtime behavior.

## Developer verification

`python -m unittest discover -s tests -v`

Additional manual checks for any deployment: `hermes plugins doctor PATH --ci`, `hermes plugins validate PATH`, then re-run the exact fixture on a no-credential disposable Hermes profile. The Windows installer was not executed in the patch environment.
