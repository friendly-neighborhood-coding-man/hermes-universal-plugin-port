# Verification Report — v0.4.3-BYTECODE-GATE (candidate)

**Bottom line:** every result in this release is **static**. In v0.4.3, **no adapter tree is imported, approved or staged unless it passes an exact-file pre-import gate** that rejects bytecode caches and other importable artifacts. Since v0.4.2, **no command registers without an explicit operator approval** bound to the full adapter digest. v0.4.1 also makes runtime promotion impossible from files: no evidence JSON can produce `ADAPTED_RUNTIME_VERIFIED`. No capability is runtime-verified on a real Hermes installation (`RUNTIME_NOT_VERIFIED` everywhere). Hermes `plugins doctor` / `plugins validate` were **not run**, because Hermes is not installed in the build sandbox and installing it from source was denied.

## 1. Test results (actually run)

```text
python -m unittest discover -s tests -v
Ran 204 tests ... OK
```

| Suite | Tests | Result |
|---|---|---|
| Original v0.3.5 suites (8 files) | 91 | passed, byte-identical to v0.4.0–v0.4.2 |
| `tests/test_v040_repair.py` | 72 | passed, byte-identical to v0.4.2 |
| `tests/test_v042_approval.py` | 21 | passed (2 adjusted, see below) |
| `tests/test_v043_bytecode_gate.py` (new) | 20 | passed |
| **Total** | **204** | **204 passed** (Linux, Python 3.13.18) |

Adjusted v0.4.2 tests. Both asserted the behavior the P0 finding rejected:

| Test | Change |
|---|---|
| `test_pycache_does_not_change_digest` | **reversed** into `test_pycache_is_rejected_not_ignored`: a `__pycache__` now makes the gate, the loader and `verify-adapter` fail |
| `test_added_file_after_approval_rejected` | an extra `.py` is now refused earlier, by the pre-import gate (same outcome: nothing registers) |

**PoC regression, before and after.** `BytecodeCachePoCTests` (7 tests) plants an unchecked-hash `.pyc` whose `register()` registers `CACHE_UNAPPROVED`. It uses only APIs that existed in v0.4.2.

| Tree | Result |
|---|---|
| v0.4.2 (unmodified, test file copied in) | **5 of 7 FAIL**: the loader registers `CACHE_UNAPPROVED`, `verify-adapter` is ok with the matching external digest, `approve` accepts, an existing approval stays VALID, and timestamp/checked-hash caches pass. The 2 passing tests are the guard proving the attack works without a gate, and cache removal. |
| v0.4.3 | **7 of 7 PASS** |

The guard test (`test_poc_is_real_on_this_interpreter`) imports the planted tree **without** the gate and asserts that `CACHE_UNAPPROVED` is registered. It confirms the attack is real on the interpreter running the suite, so a silent change in Python's cache behavior cannot make the other tests pass vacuously.

`test_v043_bytecode_gate.py` also covers:
- 13 kinds of unexpected entry: `__pycache__`, sourceless `.pyc`, `.so`/`.pyd`/abi3 extension modules, `.pth`, extra `.py`, `.zip`, case variant, `.DS_Store`, unlisted, nested or `.py` command files
- symlinks, and missing or unlisted files
- the gate never imports the adapter
- digest equality across gate, engine, template and lock
- digests no longer exclude `__pycache__`, and v1 locks are rejected
- staging: an exact copy plus approval; with no approval nothing is registrable; refusals (no confirmation, `data` home, overwrite, digest mismatch, planted source); a cache planted after staging is caught before import
- smoke-script ordering (static)

Not run (the PowerShell parts of P1-4/R4/v0.4.3 are covered by static text tests only, and the gate has not been tried against Hermes' real loader): the PowerShell scripts (`WINDOWS_SMOKE.ps1`, `WINDOWS_REPAIR_SMOKE.ps1`, `INSTALL_WINDOWS.ps1`), any Hermes CLI command, and any real Hermes runtime.

## 2. Static vs runtime — kept separate

| Layer | What produces it | Present in this build |
|---|---|---|
| Static classification | Original source + pinned Hermes facts + documented Claude semantics | Yes |
| Static behavioral checks | **Our** generated adapter (fixed template) exercised against a recording fake Hermes `ctx` | Yes (12–14 checks per command) |
| Runtime verification | A runtime-evidence record captured on a real, disposable Hermes and bound to exact hashes and version | **No.** None exists, and none was fabricated. |

A static pass never sets `runtime_behavior_verified`. **v0.4.1:** an evidence file is self-reported. When its binding and observed message hashes are consistent, its status is `SELF_REPORTED_UNTRUSTED`, never `PASS`. Promotion goes through `runtime_trusted_pass()`, which requires `trust == TRUSTED_COLLECTOR`, and no code path sets that. The validator recomputes observed message hashes. Evidence bound to another Hermes version, source hash, renderer or target-facts revision is `STALE`. Evidence from a non-disposable profile is `INVALID`.

## 3. The eight dimensions

Each command gets one **static** status per dimension: `PRESERVED_STATIC_VERIFIED`, `PRESERVED_WITH_CONDITIONS`, `NOT_PRESERVED`, `UNKNOWN`, `VIOLATION` or `NOT_APPLICABLE`. It also gets a separate **runtime** status: `NOT_RUN`, `FAIL`, `STALE`, `INVALID` or (v0.4.1) `SELF_REPORTED_UNTRUSTED`. `PASS` is reserved for a future trusted collector.

| Dimension | Static check performed |
|---|---|
| Input | Placeholder scan (ambiguous forms → `UNKNOWN`). 16 documented golden cases + 6 fail-closed refusals. `$ARGUMENTS` round-trip. Ambiguous `$N` inputs refused with no message sent. |
| Output | Original bytes shipped unchanged. Rendered body equals the shell-disabled original apart from placeholders. One provenance header line. `!` injections / `${CLAUDE_*}` / model override → `NOT_PRESERVED`. Possible `@file` → `UNKNOWN`. |
| Failure | Integrity, argument and injection refusals all report `NOT SENT` and never retry. A source with shell injections → `NOT_PRESERVED` (Claude aborts on command failure). |
| Permissions | `disallowed-tools` → `VIOLATION` (blocks). `allowed-tools` / hooks → `NOT_PRESERVED` (stricter in Hermes, no escalation). AST allowlist over adapter code. Template and renderer hashes must match the reviewed files. |
| Approval | Model-mediated approval markers (AskUserQuestion, checkpoints) or approval-bypass phrases ("without asking", "no confirmation", "automatically", "immediately") → `UNKNOWN`. Otherwise `PRESERVED_WITH_CONDITIONS` ("scan is not proof"), never `PRESERVED_STATIC_VERIFIED`. |
| Side effects | **Adapter-direct:** the recording ctx proves the adapter's only effect is one `inject_message` (`ONE_USER_MESSAGE_VERIFIED_STATIC`). **Model-induced:** never proven statically. Shell injection → `NOT_PRESERVED`. Git/GitHub/network/destructive/publish/transfer wording (including paraphrases such as "wipe", "get rid of", "push", "send", "purchase") or unmapped Claude tools → `UNKNOWN`. Otherwise `PRESERVED_WITH_CONDITIONS`, never `PRESERVED_STATIC_VERIFIED`. |
| State | `context: fork` / `agent` → `NOT_PRESERVED`. Otherwise preserved with a condition: busy CLI goes to the interrupt queue. |
| Invocation | Built-in collision renamed. Model-invocable Claude command → `NOT_PRESERVED`. Gateway needs `allow_gateway_injection`. Unknown frontmatter → `UNKNOWN`. Conditions: other-plugin collisions are not checked, and `inject_message` is not synchronous (see `LIMITATIONS.md`). |

Outcome rule, in order:

1. Unparseable source, model-only, or forked → `UNSUPPORTED`.
2. Any `VIOLATION` or failed static check → `BLOCKED_UNSAFE`.
3. Any `NOT_PRESERVED` or `UNKNOWN` → `PARTIAL_REVIEW_REQUIRED`.
4. Trusted-collector runtime PASS → `ADAPTED_RUNTIME_VERIFIED` (or `DIRECT_EQUIVALENT_VERIFIED` when a trusted registry mapping also applies). **Unreachable since v0.4.1.**
5. Otherwise → `ADAPTED_STATICALLY`.

Before any of this, the v0.4.3 pre-import gate must pass, or the adapter is never imported. Registration (v0.4.2) is separate from the outcome. A command is registered only if its outcome is one of the three fully adapted outcomes **and** an operator approval outside the adapter lists it **and** that approval's digest equals the current digest of the whole adapter folder.

## 4. Negative cases covered by tests

| Required negative case | Test(s) |
|---|---|
| Unknown tools | `test_unknown_tools_and_unknown_frontmatter_stay_unknown` |
| Missing approvals | `test_preapproval_not_preserved_but_no_escalation` (approval = UNKNOWN) |
| Malformed arguments | `test_malformed_arguments_refused_without_side_effect`, `test_documented_refusals_fail_closed` |
| Permission mismatch / escalation | `test_permission_restriction_blocks`, `test_adapter_code_allowlist_detects_escalation` |
| Unsupported source constructs | `test_unsupported_constructs`, `test_frontmatter_errors_are_not_guessed`, `test_shell_injection_partial_and_never_executed` |
| Source modified after approval | `test_source_modified_after_approval_refused`, `test_renderer_modification_refused`, `test_repair_refuses_tampered_pinned_source` |
| Unavailable dependencies | `test_refused_injection_is_reported_not_claimed` (gateway injection unavailable), `test_unknown_installed_version_is_stale` |
| Stale compatibility evidence | `test_stale_evidence_other_hermes_version`, `test_hermes_version_change_invalidates_runtime_evidence`, `test_engine_change_requires_static_reverification` |
| Partial conversion | `test_runtime_pass_cannot_override_partial_conversion` |
| Failed runtime behavior | `test_failed_runtime_behavior_not_promoted`, `test_hash_mismatch_is_invalid` |
| Static check crash | `test_static_check_crash_is_blocked_not_passed` |
| Install gate | `test_install_still_blocked_after_repair` |
| Partial command registered (P0-1) | `test_partial_commands_never_registered_by_default`, `test_unknown_or_missing_outcome_never_registered` |
| Forged evidence (P0-2) | `test_forged_bound_evidence_is_self_reported_not_promoted`, `test_evidence_cannot_claim_trusted_collector`, `test_no_evidence_path_reaches_runtime_verified` |
| Paraphrased destructive / no-approval prompts (P1-3) | `AdversarialParaphraseTests` (5 tests) |
| Smoke script fails open (P1-4/R4) | `WindowsSmokeScriptTests` (6 static tests) |
| Heuristic pass auto-registers (R1) | `test_default_registers_nothing_on_any_fixture`, `test_hollow_not_registered_by_default_but_eligible_for_review` |
| Planted bytecode cache / extension module (v0.4.2 P0) | `BytecodeCachePoCTests`, `PreImportGateTests`, `StagingTests` |
| Manifest-only outcome edit (R2) | `test_manifest_only_outcome_edit_rejected_after_approval`, `test_manifest_only_outcome_edit_without_approval_registers_nothing`, `test_forged_approval_cannot_enable_partial_command` |

Runtime-evidence records built inside tests are **synthetic** (`recorded_by: SYNTHETIC-UNIT-TEST`). They exist only to exercise the validator and are never written into the package or the reports.

## 5. Results produced (see `../reports-v0.4.3/`; every adapter there has no approval, so registers nothing; all pass the pre-import gate)

| Input | Outcomes |
|---|---|
| Synthetic `examples/claude-repair-fixture` (10 commands) | 4 ADAPTED_STATICALLY, 3 PARTIAL_REVIEW_REQUIRED, 1 BLOCKED_UNSAFE, 2 UNSUPPORTED; 0 runtime-verified |
| Real `git-pr-workflows` @ `4bde316` (3 commands) | 3 PARTIAL_REVIEW_REQUIRED (model-invocable; approval checkpoints / `Task` / `EnterPlanMode` / git writes unverified); 0 runtime-verified |
| Synthetic `examples/adversarial-paraphrase-fixture` (9 commands) | 7 PARTIAL_REVIEW_REQUIRED (not registered), 2 ADAPTED_STATICALLY (`gentle` benign control; `hollow` evades the vocabulary on purpose and carries the "not proof" condition) |
| Synthetic `update-fixture` rev-a → rev-b | 1 UNCHANGED (reusable), 1 MODIFIED, 1 MODIFIED_FRONTMATTER_ONLY, 1 ADDED, 1 REMOVED |

## 6. Runtime observation (user action, disposable profile only)

See `HANDOFF.md`, Step 5:
- approve exactly one command
- `stage` it into a fresh disposable `HERMES_HOME`
- set `PYTHONDONTWRITEBYTECODE=1`
- run `verify-adapter --adapter <staged>` immediately before starting Hermes
- record `hermes --version`
- check the transcript or logs

`Queued …` means queued, not executed. The result stays `SELF_REPORTED_UNTRUSTED`.
