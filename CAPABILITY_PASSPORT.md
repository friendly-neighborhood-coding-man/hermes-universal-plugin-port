# Capability Passport (Phase 3)

A Capability Passport is the machine-readable record of one migrated function. In this release that means one Claude Code slash command. It is generated from the actual pipeline state by `capability_passport.py`. Example outputs are in `../reports-v0.4.3/*/CAPABILITY_PASSPORT.{json,md}`.

## Files written per repair run

| File | Content |
|---|---|
| `CAPABILITY_PASSPORT.json` | Bundle: outcome counts, one passport per capability, installation policy (`performed: false`) |
| `CAPABILITY_PASSPORT.md` | Human-readable table + per-capability limitations |
| `VERIFICATION_RESULTS.json` | Full understanding, dimension statuses, every static check, runtime evaluation |
| `UNDERSTANDING_SNAPSHOT_V2.json` | Hash-only snapshot for update reconciliation (no source text, no reasoning) |
| `OFFICIAL_IMPORTER_COMPARISON.json` | Documentation-based comparison (Phase 5) |
| `WORKSHOP.txt` | Olympian Workshop view (Phase 6) |
| `adapter/repaired-<plugin>/` | Generated native Hermes plugin (review only; never installed) |

## Passport fields (schema `universal-port.capability-passport/1`)

- `capability_id`: `claude-code:<plugin>:command:<name>`
- `source`: platform, plugin, path, file SHA-256, `commit` (40-hex, or `null` with `revision_status: UNPINNED_LOCAL_TREE_FINGERPRINT_ONLY`), tree fingerprint
- `target`: pinned Hermes facts id + SHA-256, observed source commit, **installed** Hermes version (or `null`), match status (`UNKNOWN` unless runtime-verified)
- `integration`: `native_command_template` or `none`, Hermes command name, adapter package SHA-256, renderer SHA-256, entry-template SHA-256, `model_calls: 0`
- `semantic_contract`: reference doc + its SHA-256, semantics version, static status for each of the 8 dimensions
- `stages` (six separate flags, no single `success`):
  `source_functionality_understood`, `adapter_generated`, `static_checks_passed`, `runtime_behavior_verified`, `ready_for_installation`, `blocked_or_unverified`
- `outcome`: one of `DIRECT_EQUIVALENT_VERIFIED`, `ADAPTED_STATICALLY`, `ADAPTED_RUNTIME_VERIFIED`, `PARTIAL_REVIEW_REQUIRED`, `UNSUPPORTED`, `BLOCKED_UNSAFE`
- `verification`: static check totals and failures, runtime status per dimension, runtime evidence SHA-256, evidence references, direct-bridge applicability
- `known_limitations`: every non-preserved/unknown/violation reason, warnings and conditions
- `last_verified`: static engine + facts id; runtime Hermes version only when runtime PASS
- `update_compatibility`: `BASELINE` on first creation (see `UPDATE_RECOVERY.md`)

`ready_for_installation` can only be true for `ADAPTED_RUNTIME_VERIFIED` / `DIRECT_EQUIVALENT_VERIFIED`. Even then the tool installs nothing; installation stays an explicit user action.

## Results in this build

| Run | DIRECT | ADAPTED_RUNTIME | ADAPTED_STATICALLY | PARTIAL | UNSUPPORTED | BLOCKED |
|---|---|---|---|---|---|---|
| Synthetic repair fixture (10) | 0 | 0 | 4 | 3 | 2 | 1 |
| git-pr-workflows @4bde316 (3) | 0 | 0 | 0 | 3 | 0 | 0 |
| Synthetic update fixture rev-a (4) | 0 | 0 | 4 | 0 | 0 | 0 |

`ADAPTED_STATICALLY` means every dimension is statically preserved, some with stated conditions. It does **not** mean runtime equivalence.

## v0.4.1 changes

- `integration.registered_by_default` is `true` only for `ADAPTED_STATICALLY`, `ADAPTED_RUNTIME_VERIFIED` and `DIRECT_EQUIVALENT_VERIFIED`. Other rows may still list a reserved `hermes_command`, but the adapter does not register it. The Markdown table and the Workshop show "(not registered)".
- `verification.runtime_status` for an ingested evidence file is `SELF_REPORTED_UNTRUSTED`, `FAIL`, `INVALID` or `STALE`. It is never `PASS`, so `stages.runtime_behavior_verified` and `stages.ready_for_installation` stay `false`.
- `approval` and `side_effects` are never `PRESERVED_STATIC_VERIFIED`. With no markers they are `PRESERVED_WITH_CONDITIONS`, with the condition that the scan is not proof. `VERIFICATION_RESULTS.json` records `side_effects.adapter_direct` and `side_effects.model_induced` separately.

## v0.4.2 changes

- `integration.transport_status` (`TRANSPORT_STATICALLY_VALID` / `TRANSPORT_INVALID` / `NOT_GENERATED`), `integration.semantic_review` (`NOT_REVIEWED` at repair time) and `verification.runtime_status` are separate facts. None of them implies another.
- `integration.registration` is `REQUIRES_OPERATOR_APPROVAL` for `ADAPTED_*` rows with valid transport, and `NOT_ELIGIBLE` otherwise. `registered_by_default` is always `false`.
- The approval itself is a separate record outside the adapter. The passport is not rewritten, so the passport alone never shows a command as approved. `repair_cli.py verify-adapter` reports `approval_status` (`NONE` / `VALID` / `STALE` / `INVALID`).
- `ADAPTER_LOCK.json`, next to the passport, holds the adapter digest and the per-command registration eligibility.

## v0.4.3 changes

- `ADAPTER_LOCK.json` is schema `universal-port.adapter-lock/2`. It adds `files`, the exact list of allowed adapter files with their SHA-256. `adapter_package_sha256` now covers every file, with no `__pycache__` exclusion.
- `verify-adapter` output adds `pre_import_gate` (`PASS`/`FAIL`). A tree with any bytecode or other unexpected entry fails, even if every listed file is unchanged.
