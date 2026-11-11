# Update Recovery (Phase 4)

`update_reconciliation.reconcile(old_snapshot, new_source, ...)` compares a previous `UNDERSTANDING_SNAPSHOT_V2.json` with a new source revision **before** re-running the pipeline. It makes no model calls. It writes `UPDATE_IMPACT.json` (schema `universal-port.update-impact/1`).

## What it compares

1. Pinned source revisions (`old_commit` / `new_commit`) and the tree fingerprints
2. Per-command SHA-256 (whole file) and body SHA-256, which separates `MODIFIED` from `MODIFIED_FRONTMATTER_ONLY`
3. Added / removed commands, and the affected Hermes adapter command for each
4. Installed Hermes version (old vs new; unknown counts as changed)
5. Pinned Hermes target facts SHA-256
6. Repair-engine identity: renderer, entry template, Claude semantics version and golden cases hashes

## Decision rules (each row lists its reasons)

| Situation | Re-analysis | Static re-verification | Runtime evidence |
|---|---|---|---|
| Command added | yes | yes | NONE: must be verified |
| Command removed | n/a | n/a | adapter command must be removed; passport retired |
| Command bytes changed | yes | yes | INVALIDATED |
| Frontmatter-only change | yes (permissions/invocation) | yes | INVALIDATED |
| Command identical, nothing else changed | **no (reused)** | no | v0.4.1: `STILL_BOUND_UNTRUSTED_SNAPSHOT` if the same Hermes version. Runtime re-verification is still required |
| Command identical, other plugin files changed | no | yes | stays bound unless the version/engine/facts changed |
| Engine or target facts changed | no | yes (all) | INVALIDATED |
| Installed Hermes version changed or unknown | no | no | INVALIDATED (unchanged source ≠ unchanged runtime) |

A previously `ADAPTED_RUNTIME_VERIFIED` capability is carried forward as `ADAPTED_STATICALLY` at most. Since v0.4.1 that is true even when every binding still matches, because a snapshot is self-written JSON and its runtime PASS is only a claim. `runtime_verified_after_update` is always empty, and bound claims are listed under `runtime_claims_still_bound_untrusted`. Nothing is ever promoted by reconciliation.

## Reproduce with the synthetic fixtures

```bash
python repair_cli.py repair examples/update-fixture/rev-a OUT_A
python repair_cli.py reconcile OUT_A/repair-update-fixture examples/update-fixture/rev-b --out UPDATE_IMPACT.json
python repair_cli.py workshop OUT_A/repair-update-fixture --impact UPDATE_IMPACT.json
```

Expected summary: `ADDED 1, MODIFIED 1, MODIFIED_FRONTMATTER_ONLY 1, REMOVED 1, UNCHANGED 1`. `alpha` is reusable without re-analysis. `beta`, `gamma` and `epsilon` need re-analysis. See `../reports-v0.4.3/update-fixture/`.

Inside Hermes: `/universal-port repair <old_run>`, then `/universal-port reconcile <old_run> <new_run>`. That writes `UPDATE_IMPACT.json` into the new run folder.

## Relation to v0.3.5

The v0.3.5 `compare` command and v1 snapshot are unchanged and still work. v2 adds engine identity, per-dimension statuses, runtime status and evidence hashes. Neither stores source text, credentials or model reasoning. This is a narrowly scoped plugin-compatibility registry, written independently. It is not DIAPORIA's Change Journal.
