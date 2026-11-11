# Runtime permission audit: P6 E2E run 001

**Question:** in the accepted run, were writes outside the run directory technically prevented, or merely not attempted?

**Answer: merely not attempted.** The only enforced write boundary was Hermes's protected-path denylist. No directory sandbox was active. The evidence follows.

**Method:**

- Static reading of Hermes `b200f5bc60e3` (the runtime the run used).
- Non-destructive local probes that wrote only inside this session's scratch directory.
- The run's own trace.

Nothing was written to production, credential paths or unrelated directories.

## 1. Run configuration (what actually applied)

| Setting | Value in run 001 | Source |
|---|---|---|
| Hermes | v0.22.7, local `b200f5bc60e3`, Python 3.14.9 | `hermes --version`; `docs/evidence/p6-runtime/preflight-001.json` |
| `HERMES_HOME` | `D:\Hermes-Lab\uvp-p6-hermes-test` (disposable P6 home) | launch env; gateway state file |
| Execution host | **The disposable home's gateway process** (PID 37836, `gateway run --quiet --idle-exit`, started 2026-11-10 15:42 UTC, before this session) | Attempt 0 was rejected with "Unsupported gateway CLI options: --run-budget", which shows the CLI forwards to the gateway; `gateway_state.json` |
| Toolsets | `-t skills,file` → `skills_list`, `skill_view`, `skill_manage`, `read_file`, `write_file`, `patch`, `search_files` | `toolsets.py`; `-t` is a forwarded session policy (`gateway_chat._POLICY`) |
| Tools actually used | `skill_view` ×3, `read_file` ×1, `write_file` ×3 | `stream.jsonl` |
| Turn bound | `--max-turns 40` (forwarded policy) | launch command |
| Wall-clock bound | **none.** `--run-budget` is unsupported via the gateway; `agent.run_budget_seconds` is not set in config. | attempt-0 error; `config.yaml` |
| `HERMES_WRITE_SAFE_ROOT` | **Unset.** Not in the User or Machine environment. Not forwarded either way: `HERMES_*` names do not travel in `client_env` (`agent/session_client_env._travels`). | registry query; source |
| `--yolo` / approvals | not used; default approval policy | launch command |

## 2. The write authorization model (static)

`tools/file_tools._write_precheck_error` runs these guards in order, for every `write_file` and `patch`:

1. **`_check_sensitive_path` → `agent.file_safety`:** a hard deny for:
   - OS credential stores (`~/.ssh/*` except `config`, `~/.aws`, `~/.kube`, `/etc/sudoers*`, `.netrc`).
   - Hermes secret stores and protected subpaths: `state.db`, `sessions/`, `mcp-tokens/`, `pairing/`, `vault/`, `browser-profile/`, `webapp/`.
   - The runtime's own interpreter/venv.
   - NT/device-namespace paths.
2. **`HERMES_WRITE_SAFE_ROOT`:** hard-blocks writes outside the listed prefixes, **only if the variable is set**.
3. Cross-profile mirror check, binary-document guard and protected-instruction-file approval.
4. **Approval gate:** applies only to approval-required paths (today `~/.ssh/config`). Single-query sessions fail closed there.

There is **no working-directory confinement**: `--in DIR` sets the cwd and nothing more. Control files (`config.yaml`, `auth.json`) are read-denied but **writable** by design (Hermes `user-guide/security.md`).

## 3. Probe (non-destructive, scratch directory only)

The probe used the runtime venv's Python, `HERMES_HOME` set to the disposable home, and the real `tools.file_tools.write_file_tool` with an `inside` and an `outside` sibling directory under the session scratch dir. Script: `docs/evidence/p6-final-review/permtest/probe_write.py`.

| Case | `HERMES_WRITE_SAFE_ROOT` unset | set to `inside` |
|---|---|---|
| Write `inside/a.md` | written | written |
| Write `outside/b.md` | **written** | **`Write denied: … outside HERMES_WRITE_SAFE_ROOT`**, file not created |
| `<home>/state.db` (checked with `get_write_denied_error` only, never written) | denied (protected) | denied |
| `~/.ssh/id_ed25519` (checked only, never written) | denied (credential) | denied |

## 4. Conclusions

| Question | Finding |
|---|---|
| Were writes outside `p6-e2e-run-001\` technically prevented? | **No.** With the safe root unset, any non-denylisted path was writable, including the disposable home's `config.yaml`. |
| Were any attempted? | **No.** The trace has exactly three `write_file` calls, all into the run directory. The post-run drift check shows `plugins/`, `skills/` and `config.yaml` unchanged, except Hermes's own `skills/.usage.json` counter. |
| Did credential paths stay protected? | Yes, by the hard denylist, independent of the safe root. |
| Could the model have changed Skills? | `skill_manage` was **available** (part of the `skills` toolset) but never called. The drift check confirms nothing changed. |
| Were file writes approval-gated? | No. Ordinary paths are not approval-gated in Hermes. The approval the run had was the operator's pre-launch approval in the thread. |
| Was the toolset restriction enforced? | The policy was forwarded and accepted, and only those tools were used. That no *other* tool was available was **not independently observed**, because the stream does not list the tool schema. |

## 5. Hardening for any future run (documentation; not yet applied to a run)

1. Start the disposable gateway with `HERMES_WRITE_SAFE_ROOT=<run dir>` set in **its** environment. Setting it in the client shell has no effect on gateway-hosted turns. Restart the gateway after setting it.
2. Set `agent.run_budget_seconds` in the disposable `config.yaml` instead of `--run-budget`.
3. Drop `skill_manage` from the run. A toolset that excludes it would need a narrower toolset definition, so until then treat its availability as a disclosed risk.
4. Keep the before/after hash drift check as a mandatory post-run step.

Applying these needs no model call. *Verifying* them in a real run needs a new paid run and separate approval.

## 6. Provenance checks performed during this audit

- **Upstream:** all 14 files of `product-management/` at `e605d8dd…` match the local `original/` tree by **git blob SHA** (GitHub tree API vs. local `git hash-object`). This independently links the stage to the pinned upstream commit, which closes the earlier "declared, not independently linked" gap.
- **Hashes:**
  - `SOURCE_HASHES.json`: 14/14 match.
  - `PORTING_REPORT.json` original SHA-256 values: 8/8 match.
  - Active staged Skills equal the originals (8/8), and the installed Skills equal the originals (8/8).
  - The rejected candidate is still `676ead16…51a8`.
- **Artifacts:** each `write_file` input is byte-identical to the file on disk, and its SHA-256 matches `RUN_RECEIPT.json`.
