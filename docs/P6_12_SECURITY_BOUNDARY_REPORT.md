# P6.12 security boundary report

This report is a self-assessment by the implementing agent, not an external audit. Each boundary below states what enforces it, what was demonstrated and what is not covered.

## Boundaries, from strongest to weakest

| # | Boundary | Enforced by | Demonstrated | Not covered |
|---|---|---|---|---|
| B1 | **OS isolation of UVP-owned workloads** | Linux mount, network and PID namespaces; tmpfs root; uid 65534; `RLIMIT_NPROC=1`; no `/bin/sh` (P6.10 runner in the disposable WSL distro `ae2e-t01`) | 7/7 out-of-scope probes denied while the control allows all of them (`p6-10-isolation/probe-run-001.json`). The same denials hold when reached through a real Hermes tool call (`p6-12/isolated-task-e2e-001.json`). Timeout cleanup tested live. | WSL2/kernel escape. The Hermes process and the LLM are **not** inside the boundary. `/usr/lib` is readable inside. |
| B2 | **Safebox-gated isolated task** (`uvp_isolated_task`) | Safebox grant bound to source SHA and contract ID, plus allow-listed workloads; B1 for execution | Through real Hermes dispatch: an allowed task ran; out-of-grant input, a non-allow-listed workload and a stale grant were refused before running (`isolated-task-e2e-001.json`). | Only allow-listed UVP workloads. No model-driven or Skill-supplied code runs there. Classification: **LIMITED_WORKLOAD_ISOLATION**. |
| B3 | **Safebox tool policy** | `pre_tool_call` hook inside the Hermes process | 14 DENIED and 3 ENFORCED through real `model_tools.handle_function_call` (`P6_12_ADVERSARIAL_MATRIX.md`) | **3 BYPASS_CONFIRMED:** slash invocation, `-s` preload, validate-then-swap race. **2 NOT_INTERCEPTED:** sessions with no active imported Skill, and host-side actions. **1 NOT_TESTED:** a live delegated child. Classification: **POLICY_ONLY / NOT_ISOLATED**. |
| B4 | **Continuity handoff authenticity** | HMAC-SHA256 under a per-process key plus a single-use issued registry | 11-case adversarial corpus, 0 false authorizations. Fail closed on a missing loader, a changed body or an internal error. | The child cannot re-verify, because no Hermes hook exposes the child context. A model can ignore the block. |
| B5 | **Candidate / registry / install gates** | Hash pins, the rejected-candidate ledger, validate-before-swap, rollback | Unit tests plus real Hermes CLI rollback (`p6-12/rollback-exercise-001.json`) | Hermes's own `backups/config/*.good.*` files are not reverted. They are Hermes audit data, kept by design. |
| B6 | **Hermes write denylist** | Hermes `agent.file_safety` | Credentials and `state.db` are denied even without `HERMES_WRITE_SAFE_ROOT` (final-review probe) | Everything else is writable unless `HERMES_WRITE_SAFE_ROOT` is set in the process that runs the tool (the gateway). |

## Hermes behaviors that matter for UVP

- **`pre_tool_call` hook exceptions fail open.** `model_tools._pre_dispatch_guards` logs them at debug level and proceeds. Every UVP callback catches its own errors and returns a block.
- **Skill text reaches the model without any tool call** on two routes: slash invocation (`agent.skill_commands.build_skill_invocation_message`) and `-s` preload (`build_preloaded_skills_prompt`). No public hook intercepts Skill loading itself.
- **The hook sees a path string, not a file handle.** A junction swapped in after validation redirects the write (A15).
- **The hook does not receive the task's working directory.** Safebox therefore denies all relative paths.
- **`HERMES_*` variables in the client shell do not reach gateway-hosted turns.** `client_env` drops them.

## Minimal host capabilities that would close the gaps

1. A Skill-load hook for slash, preload and `skill_view`, able to veto. This would close A16/A17 and give Safebox real invocation authorization.
2. Handle-based write enforcement inside `write_file`/`patch`: open the validated directory, then create relative to it with no-follow. This would close A15.
3. A child-session start hook exposing the delegated context and the parent link. This would allow child-side contract verification (B4) and Safebox propagation (A22).
4. Running Hermes tool execution inside an OS sandbox (for example the same namespaces) instead of only allow-listed UVP workloads. This would turn B2 into INTEGRATED_AND_ISOLATED.

None of these exist in the Hermes `b200f5b` public surface. UVP does not patch Hermes to add them; catalog rule 9 forbids core overrides.

## Verdict

**HOLD_SECURITY does not apply to the release**, because the release registers none of the experimental hooks or tools:

- P6.8, P6.9 and the `uvp_isolated_task` tool exist only as libraries and a TEST-ONLY harness plugin.
- The released plugin's capabilities are unchanged: 4 tools, 0 hooks.

The limits above are disclosed rather than claimed as enforcement.
