# P6.12 integration report (2026-11-11 KST)

Self-review by the implementing agent; not independent approval. **0 paid model calls in P6.12.** All Hermes interaction is in-process or through the Hermes CLI, in disposable homes only:

- `uvp-p6-hermes-test`
- `uvp-p612-hermes-test` (new)
- `uvp-p612-rollback-home` (new)

Production and P5 homes were not touched.

## Work packages

| WP | Commit | What is verified | How | Status |
|---|---|---|---|---|
| WP1 continuity authenticity | `0fe9278` | Authenticated handoff (HMAC under a UVP-held key, single-use nonce, bound to source/body SHA, obligation digest, parent session and call, with expiry). The 11-case adversarial corpus gives **0 false authorizations**. Missing loader, changed body and internal errors fail closed. | 13 unit tests | EXPERIMENTAL (not registered). The child cannot re-verify. |
| WP2 Safebox adversarial | `e5b0c36` | 23-route matrix through **real Hermes dispatch**: 14 DENIED, 3 ENFORCED, **3 BYPASS_CONFIRMED**, 2 NOT_INTERCEPTED, 1 NOT_TESTED. Relative paths are now denied; errors block. | `scripts/p612_adversarial.py`, TEST-ONLY harness plugin, `P6_12_ADVERSARIAL_MATRIX.md` | **POLICY_ONLY / NOT_ISOLATED** |
| WP3 Safebox → isolation | `cd8823e` | Real Hermes tool call → contract and grant check → allow-listed workload in the namespace runner. Out-of-scope operations are denied at the OS boundary; bad grant, input or workload is refused before running; timeout cleanup works. | `scripts/p612_isolated_e2e.py`, 7 tests (2 live) | **LIMITED_WORKLOAD_ISOLATION** |
| WP4 lazy cache | `b9797e7` | Cache bound to (session, Skill), body SHA and fingerprint. Invalidated on change, replacement or deletion. No cross-session reuse. Contract-verification failure refuses both load and reuse. | 9 tests. Re-measured with real Hermes builders (`p6-11-routing/measure-002.json`). | EXPERIMENTAL. Tokenizer: NOT_AVAILABLE_OFFLINE. No cost claim. |
| WP5 install/rollback | `f4f8f61` | With the real Hermes CLI in a new home: clean install, 8 namespaced Skills resolve. A tampered update is refused before swap. A namespace-renamed update is rolled back after swap. Rollback to pre-install leaves only Hermes's own config backups. Reinstall plus remove restores `config.yaml` byte-for-byte. The unrelated plugin and defaults are unchanged. | `scripts/p612_rollback_exercise.py`, `p6-12/rollback-exercise-001.json`, 5 tests | VERIFIED (disposable home) |
| WP6 semantic repair | `413b22e` | Heading-only false positives fixed. Clarification triage on run-001: 7 answered by context, 3 optional skipped, 0 mandatory missing. A mandatory gap gives HOLD, not an invented assumption. Unsupported repair claims are rejected. | 18 tests, `p6-7-semantic-review-002/` | **LLM_RUNTIME_NOT_TESTED** |
| WP7 public snapshot | `db35a1c` | `git archive` snapshot with 3 files sanitized (account name and host name), each recorded with private and public SHA. Audit CLEAN. A single local commit with noreply identity. | `scripts/make_public_snapshot.py` | Prepared locally; **not published** |

## Distinctions kept explicit

- **Skill instruction delivery to the model:** normal Hermes path. Not isolated, and not gated on the slash or preload routes.
- **Tool authorization:** Safebox policy at `pre_tool_call` (POLICY_ONLY).
- **Execution inside the isolated OS environment:** only allow-listed UVP workloads (WP3).
- The P6 three-Skill E2E (run-001) and the WP3 isolated task are **separate execution paths** and are never presented as one workflow.

## Unresolved risks (exact list)

1. Safebox bypasses: slash invocation (A16), `-s` preload (A17), validate-then-swap race (A15).
2. No live delegated-child test (A22). Children are not covered by Safebox.
3. The continuity child side cannot verify the handoff.
4. The LLM and Hermes process are not OS-isolated. Run-001 writes were bounded only by the Hermes denylist (`HERMES_WRITE_SAFE_ROOT` unset).
5. Semantic equivalence is NOT_ESTABLISHED. The LLM NLI evaluator has never been run.
6. No local Claude tokenizer, so context-size figures are characters only.
7. GitHub-hosted CI is billing-blocked. Local Windows and clean-Ubuntu runs only.
8. The isolation runner depends on a disposable WSL distro with root.

## Submission-readiness verdict

**READY_FOR_RELEASE_REVIEW**, subject to:

- the operator's go to create the new public repository from the prepared snapshot;
- a final freeze rebuild: snapshot, validate and tests on the exact release commit.

The release plugin's capabilities are unchanged: 4 tools, 0 hooks. Every P6.8–P6.12 component is EXPERIMENTAL and unregistered. The one exception is the isolation runner, which is IMPLEMENTED for UVP-owned workloads.
