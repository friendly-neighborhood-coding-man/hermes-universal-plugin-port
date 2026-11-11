# P6.14 integration report: the adapted package is what gets installed

## The gap (confirmed)

Before P6.14, `uvp_guided.py install` called `Installer.install(st["stage"])`, which installs the **verbatim** stage. The deterministic adaptation (`adapt_package.py`) ran only on the separate path in `scripts/p6_before_after.py` and the tests. A first-time user following the Quickstart got the unadapted package, the one whose usage tokens and resource links fail in Hermes. The public release `86b4e6d` still behaves this way (risk R13).

## What changed (private branch, commits `2dc81b1`, `2b50a84`, `3172adf` and the commit adding this report)

| Step | Behaviour |
|---|---|
| `inspect` | Writes `INSPECT_REPORT.json`. It holds the source URL and commit, a SHA-256 for every source file, supported Skills, unsupported connectors/commands/hooks/agents, filesystem and execution effects, and limits. |
| `adapt` (new) | Calls `adapt_package.adapt` into `<workspace>/candidate/` and never touches the stage. The stage digest is checked before and after. Only the previously verified deterministic rules run (R-C001, RES-LOCAL-1); no AI transformation. It self-verifies the candidate, then writes `CANDIDATE_REVIEW.json` and `.md`: candidate digest, originals preserved, every changed or added file with rule IDs, before/after SHA-256 and exact changed spans (unified diff), unsupported connectors, and what will and will not be installed or enabled. It refuses to overwrite an existing candidate. |
| `approve` (new) | `--candidate-digest D` must equal the recomputed candidate digest. The approval records the digest, path and kind (`OPERATOR_CLI_FLAG`). Re-running `adapt` clears it. |
| `install` | Before copying, it refuses in each of these cases: no approval; a stale approval (another candidate); a candidate modified after approval; a failed manifest or content check; a stage-binding mismatch; a source-hash mismatch; `plugin.yaml` or `__init__.py` differing from the reviewed stage (permission escalation); a symlink or junction anywhere in the candidate, the home or `plugins/`; an existing target (no overwrite). It then takes the full-home inventory, runs `hermes plugins validate`, copies, enables, and checks that the installed digest equals the approved digest and that the runtime check passes. Any failure rolls back the plugin dir and `config.yaml`. `INSTALL_RECEIPT.json` lists every installed file. |
| `verify` | Runs real Hermes in the home's own runtime. It checks namespaced registration, `skill_view`, slash argument delivery, the **documented usage line** of each pilot Skill (token resolves, argument delivered), the localized `CONNECTORS.md` through `skill_view(file_path=…)`, and the "NOT connected" note. It also checks that the installed digest still matches the approval. |
| `undo` | Restores the plugin dir and `config.yaml` from the pre-install backup. It writes `UNDO_RECEIPT.json` with an exact, classified diff against the pre-install inventory. |
| every step | Prints the exact next command. A failure prints a recovery hint. |

Library additions in `install_ops.py`: `package_files`, `package_digest`, `is_redirect` (symlink, junction or reparse point), `full_inventory`, `classify_residuals`.

## Evidence

- **Unit tests:** `tests/test_p614_adapted_install.py` (11 tests). They cover each refusal above, the byte-exact install of the candidate (not the stage), rollback on a failed runtime check, residual classes, and the symlink refusal (skipped where symlinks are not permitted).
- **Clean-home E2E:** 11 of 11 commands passed twice in new homes. The installed digest equalled the approved digest, the documented usage resolved, and the resource opened. Details: [P6_14_CLEAN_HOME_E2E.md](P6_14_CLEAN_HOME_E2E.md), `docs/evidence/p6-14/`.
- **BEFORE reproduced** in a fresh verbatim home on the same Hermes: `docs/evidence/p6-14/before-verbatim-fresh-home-001.json`.

## Defects found and fixed during the sprint

- E2E-001's `CANDIDATE_REVIEW` listed 0 connectors because it read the wrong `PORTING_REPORT` key; the inspect report was correct. Fixed in `3172adf` and re-run as E2E-002, which lists 16. E2E-001 evidence is kept as recorded.
- In E2E-001, `skills/.usage.json` was unattributed. It was attributed as Hermes's skill-usage ledger, and the classifier was updated.

## Limits (unchanged)

- SKILLS_ONLY_PARTIAL.
- SEMANTIC_EQUIVALENCE_NOT_ESTABLISHED.
- Safebox and Continuity remain unregistered.
- A disposable home is not an OS sandbox.
- The approval in the recorded E2E was simulated by a test driver.
- The guided flow was exercised end to end on Windows only.
