# P6.16 Migration Doctor → Repair Planner → Verified Repair: dogfood report

> Public v0.7.0 note: the raw evidence directories this report cites (`docs/evidence/p6-15/`, `docs/evidence/p6-16/`) are kept in the private development repository and are not part of this release. `scripts/uvp_repair_smoke.sh` reproduces the workflow.


**Disposition: `PARTIAL_REPAIR_VERIFIED`.**

One deterministic repair (RES-LOCAL-1 v1) is fully demonstrated, with Hermes verification, against the real official importer for Claude Code, Codex and Cursor. It is reproduced in a freshly bootstrapped Hermes home.

The disposition is not `READY_FOR_INDEPENDENT_REVIEW` because:
- **Functional compatibility of the migrated set stays NOT_VERIFIED.** The pdf Skill's declared dependencies are DEPENDENCY_ACTION_REQUIRED and are never installed.
- **Interrupted-Apply recovery is `INTERRUPTED_RECOVERY_NOT_VERIFIED`.**
- **Private CI is billing-blocked**, so only local runs exist.

## Primary sequence (reproduced in a fresh home, all three agent layouts)

`OFFICIAL_IMPORT_SUCCESS` → `UVP_DETECTS_REAL_FAILURE` → `DETERMINISTIC_REPAIR_PLAN` → `APPROVED_REPAIR_CANDIDATE` (test-only, simulated approval) → `ACTUAL_HERMES_VERIFICATION_PASS`.

| Stage | Claude Code | Codex | Cursor |
|---|---|---|---|
| Official import (`AgentImporter(execute=True)`) | 3 imported, 0 conflict, 0 error | same | same |
| Gates after the import | INSTALL PASS · RUNTIME PASS · **FUNCTIONAL FAIL** → HOLD | same | same |
| Doctor finding | `skill_view('synthesize-research', file_path='../../CONNECTORS.md')` → `Path traversal ('..') is not allowed.` | same | same |
| Plan | RES-LOCAL-1 v1 **DETERMINISTIC_REPAIR_AVAILABLE**; pdf **DEPENDENCY_ACTION_REQUIRED**; `$ARGUMENTS` **INSUFFICIENT_EVIDENCE** | same | same |
| Candidate (isolated; installed Skill unchanged by the build) | 2 files: `SKILL.md` (1 span), `CONNECTORS.md` (added) | same | same |
| Negative controls | wrong digest: HOLD; tampered plan: HOLD | same | same |
| Apply (simulated test approval of the full candidate digest) | COMMITTED; installed digest = approved | same | same |
| Independent Hermes verifier (fresh process) | repaired link opens; says NOT connected; old link gone; pdf still resolves; only the 2 allowed files changed; source and origin byte-identical | same | same |
| Gates after the repair | INSTALL PASS · RUNTIME PASS · **REPAIR_VERIFICATION PASS** · synthesize-research functional **PASS** · pdf functional **NOT_VERIFIED** → overall FUNCTIONAL NOT_VERIFIED → HOLD | same | same |
| Approval replay after Apply | refused (ledger) | refused | refused |
| Repair rollback | ROLLED_BACK; Skill digest = pre-repair digest | same | same |
| Import rollback | in-scope byte-identical | same | same |

Evidence: `docs/evidence/p6-16/fresh-{claude-code,codex,cursor}/`. Also `iter0-claude-code` (the first run, in the P6.15 home) and `neg-missing-hermes`.

The Claude Code candidate (Codex and Cursor are equivalent, with their own digests):
- Installed `synthesize-research` digest: `3cfe2821c2f5e6a201b9b67589ac7502419cb8ae1f84fc0249135c4a8c3daca2`.
- Candidate digest: `d719b6f135ec54fa434a59ca945be5a451cc751d13a801193b65fc4bc591303d`.

```diff
--- installed/SKILL.md
+++ candidate/SKILL.md
@@ -9 +9 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
```

The added `CONNECTORS.md` comes from the pinned origin `product-management/CONNECTORS.md` @ `e605d8dd…` (sha in `REPAIR_PLAN.json`), with a change notice. It states that **the connectors are NOT connected: no MCP server, OAuth grant or credential was configured.** The result is `BROKEN_RESOURCE → VERIFIED_RESOURCE_RESOLUTION`. It is **not** a connector connection.

## Section 2 fixes: outcome model

`migration_repair.evaluate_gates` and `run_hermes_verifier`, used by `scripts/p615_apply_official_import.py`:
- **Four separate gates:**
  - `INSTALL_INTEGRITY`;
  - `RUNTIME_VERIFICATION`;
  - `FUNCTIONAL_COMPATIBILITY` (per Skill: FAIL on a broken linked resource or a failed `skill_view`; NOT_VERIFIED for undeclared or unverified dependencies, or when the runtime check did not pass);
  - `REPAIR_VERIFICATION`.

  `final_gate` is PASS only if every required gate is PASS.
- **The Hermes check is mandatory.** A missing interpreter or source gives NOT_VERIFIED. A non-zero exit, malformed output, an unexpected verifier version or uninterpretable Skill rows give FAIL. Either way, the result is HOLD.
  - Real run (`neg-missing-hermes`): Apply without `--hermes-python` gave INSTALL PASS, RUNTIME NOT_VERIFIED, FUNCTIONAL NOT_VERIFIED → **HOLD, exit 1**.
- **P6.15 bug fixed:** P6.15's `postflight_pass: true` with `RESOURCE_LINKS_BROKEN` can no longer happen. The same import now reports FUNCTIONAL FAIL and HOLD.

## Repair Planner, Executor and Apply (`migration_repair.py`)

- **Doctor findings:**
  - `BROKEN_RELATIVE_RESOURCE`, from the Hermes verifier: every relative link in each `SKILL.md` is opened through `skill_view(file_path=…)`.
  - `DECLARED_DEPENDENCIES_UNVERIFIED`, from the static scan.
  - `HOST_ARGUMENT_TOKEN`, with the actual slash-key resolution.
- **Planner:** produces a typed `RepairProposal` per finding. Each records the finding and its reproduction, the root cause, the classification (one of the five), the evidence and confidence, the rule ID and version, exact files and spans with before/after SHA-256, preconditions, the expected outcome, acceptance tests, rollback, what stays unresolved, and whether human approval is required (always). The plan carries a `plan_sha256`.
- **RES-LOCAL-1 v1 preconditions:**
  - the link is relative, not a URL or absolute path;
  - it resolves to a regular file **inside the pinned origin tree** (not a link, at most 256 KB);
  - the installed Skill folder is real (not redirected);
  - the destination name is absent;
  - the exact span `](link)` is present.

  If any precondition fails, the result is `UNSUPPORTED`, `REQUIRES_USER_DECISION` or `INSUFFICIENT_EVIDENCE`, and **no patch** is produced.
- **R-C001 / `$ARGUMENTS`:** the imported user Skill resolves as `/synthesize-research`. The R-C001 precondition, a namespaced plugin slash key, does not hold, and no failure was reproduced. Result: INSUFFICIENT_EVIDENCE, no repair.
- **Dependencies:** pdf needs `reportlab`, `pdfplumber`, `pypdf`, Poppler `pdftoppm`, `uv`. Result: DEPENDENCY_ACTION_REQUIRED. **Nothing is installed.**
- **Executor:**
  - It requires the plan hash to be intact.
  - It **recomputes** the proposal from the live state and requires it to equal the plan.
  - It copies the installed Skill to a new candidate directory (never overwriting one), writes only the planned files, and checks each file's after-hash.
  - It refuses changes outside the allowed set, and refuses symlinks or junctions.
  - It emits `CANDIDATE.json` with the diff and full digest.
- **Apply:** applies only after it has re-checked these, immediately before writing:
  - the disposable marker;
  - that the ledger, backup and journal are outside the home;
  - plan integrity and plan/candidate binding;
  - that the approval equals the current candidate digest;
  - that this approval is not in the consumed-approval ledger;
  - that the target Skill is unchanged since the candidate was built.

  It then journals `STARTED`, backs up, stages a copy and checks it, swaps it in by rename, verifies the installed digest and journals `COMMITTED`. Finally it records the approval as consumed.
- **Rollback:** only a `COMMITTED` journal is rolled back. Anything else is reported `INTERRUPTED_RECOVERY_NOT_VERIFIED`; it is never called rolled back.

**Security boundary:** digests detect changes between steps of this process. They do **not** protect against a malicious local process that can rewrite files between the final check and the rename. Approvals in this report are **SIMULATED_BY_TEST_DRIVER**, not human approvals.

## Negative corpus (`tests/test_p616_repair.py`, 20 tests; plus the real runs above)

| Case | Result |
|---|---|
| Broken resource with install and runtime PASS | FUNCTIONAL FAIL, HOLD |
| Hermes check missing, exits non-zero or malformed | NOT_VERIFIED / FAIL, HOLD (unit tests and a real run) |
| Declared dependencies | NOT_VERIFIED, HOLD |
| Wrong digest | HOLD (unit tests and a real run) |
| Changed candidate / changed target / changed origin | HOLD |
| Tampered plan | HOLD (unit tests and a real run) |
| Unmatched rule (origin file missing) | no deterministic repair, no candidate |
| Dependency finding | never builds a candidate |
| Unexpected file in a candidate | refused at build |
| Broken resource after repair | FUNCTIONAL FAIL |
| Approval replay | refused (unit tests and a real run) |
| Interrupted Apply (journal `STARTED`) | `INTERRUPTED_RECOVERY_NOT_VERIFIED` |
| Ledger, backup or journal inside the target | refused |

## Correction iterations

- **Iteration 0** (implement, then the first real dogfood on Claude Code in the P6.15 home): all checks passed. No failure was recorded, so **iterations 1 and 2 were not used**.
- The fresh-home matrix (Claude Code, Codex, Cursor in a newly bootstrapped Hermes v0.22.7 home) also passed on the first run.

## Tests

| Suite | Result |
|---|---|
| Windows full regression | 489 OK, 6 skipped |
| Linux full regression (WSL, Python 3.12.3) | 489 OK, 16 skipped |
| `tests/test_p616_repair.py` | 20 OK |

## Identities

- Official importer: `NousResearch/hermes-official-plugins@8b5b6296bbb900f90e296b4729d2c9a5d1139825`, agent-importers git tree `25067206bc8e574072c0527065175956de43c352`, UVP folder digest `046035a6…cfe6` (Windows checkout).
- Skills:
  - `anthropics/knowledge-work-plugins@e605d8ddbfb688da57dfaaceebd93f12a64ef1d3`;
  - `openai/skills@49f948faa9258a0c61caceaf225e179651397431`.
- Hermes Agent v0.22.7 (`b200f5bc60e3`).
- No model calls. No upstream changes.

## Remaining issues and release blockers

1. **pdf Skill:** functional status is NOT_VERIFIED until its dependencies are installed by the operator, and it is never auto-installed.
2. **Crash safety:** crash-safe recovery of an interrupted Apply is not implemented (`INTERRUPTED_RECOVERY_NOT_VERIFIED`), so production use stays blocked.
3. **Second executable repair:** none. No second failure was reproduced that met a verified rule's preconditions.
4. **Grok Bot, OpenBot and OpenClaw:** not repaired; see P6.15.
5. **CI:** private CI is billing-blocked, so all evidence is from local Windows and Linux runs.

## Reproduce

```bash
python scripts/p616_repair_dogfood.py --official-package <upstream>/agent-importers --home <bootstrapped disposable Hermes home with .uvp-disposable> \
  --evidence <new dir> --anthropic-root <knowledge-work-plugins@e605d8dd> --openai-root <openai/skills@49f948fa> --agent claude-code
```
