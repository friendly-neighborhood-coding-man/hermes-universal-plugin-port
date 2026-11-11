# Known Limitations — v0.4.3 (reviews P1-5, R1–R4, v0.4.2 P0)

These limits are real and are not fixed by v0.4.1. Each one also shows up as a `known_limitations` entry or a dimension condition in every Capability Passport where it applies.

## 1. `inject_message` is not a synchronous command execution

The generated adapter queues **one additional user message** through `ctx.inject_message`. It does not run the command inline or wait for the model's answer.

- What Hermes does with the queued message depends on the **installed Hermes version and runtime mode**. In the pinned source (`a9ff979`), classic CLI puts it on the pending-input queue when idle and on the **interrupt** queue while the agent is running. Current Hermes docs describe host- and session-specific routing, and say that gateway-backed CLI turns may not be shown to the attached client even when queued. **None of this has been observed at runtime.**
- So this release does **not** claim that an injected command appears as a visible next turn. Confirm it in the session transcript or logs of a disposable profile, with `hermes --version` recorded.
- The handler returns `Queued /<command> ...` once Hermes accepts the message. That means *queued*, never *executed* or *succeeded*.

## 2. Gateway / TUI injection needs explicit permission

Hermes refuses plugin injection in Gateway and TUI sessions, and possibly in gateway-backed CLI sessions depending on version and mode, unless `plugins.entries.<adapter>.allow_gateway_injection: true` is set. This tool **never** sets it. Without it, the handler reports `NOT SENT` (tested by `test_refused_injection_is_reported_not_claimed`). Turning it on is your decision, per adapter, and is not part of the step-6 check.

## 3. Claude Code semantics that are NOT preserved

| Claude Code feature | What happens in Hermes | Outcome effect |
|---|---|---|
| `allowed-tools` (pre-approval) | Not preserved. Hermes asks with its own approval policy, so it asks **more**, never less. | `PARTIAL_REVIEW_REQUIRED` |
| `disallowed-tools` (restriction) | Cannot be preserved. Hermes has no per-command tool removal. | `BLOCKED_UNSAFE` (never registered) |
| `model:` override | Not preserved. Hermes uses the session's model. | `PARTIAL_REVIEW_REQUIRED` |
| Model-only commands (`user-invocable: false`) | Cannot be represented as a native user command. | `UNSUPPORTED` |
| Model-invocable commands (default in Claude Code) | Only the user-typed path exists. The model cannot call the command itself. | `PARTIAL_REVIEW_REQUIRED` |
| `hooks` | Not preserved. | `PARTIAL_REVIEW_REQUIRED` |
| `context: fork` / `agent:` | No forked sub-agent context. | `UNSUPPORTED` |
| `` !`cmd` `` shell injection | Never executed. It is replaced with Claude's documented "disabled" placeholder, so its output is missing. | `PARTIAL_REVIEW_REQUIRED` |

## 4. No AI transformation

`model_calls` is `0` for every capability. The adaptation is a fixed, reviewed template plus the original command bytes. Nothing rewrites prompts to close semantic gaps. `PARTIAL` rows stay partial until a human (or a future bounded AI step under the existing budget/approval rules) addresses them.

## 5. Collisions with other third-party plugins are not checked

Collisions with Hermes' **131 built-in** commands and aliases are detected and renamed (for example `/review` becomes `/repair-fixture-review`). Collisions with commands from **other installed plugins** are not checked. In the pinned Hermes source, a later plugin registration of the same name displaces the earlier one, so the winner depends on load order. Check `hermes plugins list` in your disposable profile before enabling an adapter.

## 6. Side effects and approval are only scanned heuristically (P1-3 context)

The adapter's **own** effect is statically proven: exactly one `inject_message` (the recording-ctx tests and the AST allowlist). What the **model** does after reading the prompt is not provable statically.

v0.4.1 scans for destructive, publish/transfer and approval-bypass vocabulary. A match makes the dimension `UNKNOWN`, so the command stays `PARTIAL`. **No match is not proof of safety.** The bundled `hollow` fixture ("Make this folder empty…") deliberately evades the vocabulary and stays `ADAPTED_STATICALLY`.

**v0.4.2 (review R1):** the scan no longer decides registration. Passports separate `transport_status` (our adapter delivers the text correctly, checked statically), `semantic_review` (`NOT_REVIEWED` until an operator approves) and runtime status. **No command registers by default**, including `hollow` and `/summarize`. A command registers only after `repair_cli.py approve ... --command NAME --operator NAME --i-reviewed-model-induced-effects`. Only `ADAPTED_*` commands can be approved; `PARTIAL`, `BLOCKED` and `UNSUPPORTED` cannot. Approval is a human judgment, not verification, and it does not make anything install-ready. The marker vocabulary will not keep growing, and it is not proof.

## 7. Runtime evidence cannot be trusted yet

There is no trusted Hermes-side collector in v0.4.1. Any evidence JSON passed with `--evidence` is recorded as `SELF_REPORTED_UNTRUSTED` (or `FAIL`/`INVALID`/`STALE`) and can **never** produce `ADAPTED_RUNTIME_VERIFIED` or `ready_for_installation`. For the same reason, update reconciliation never carries a snapshot's runtime PASS forward. A future collector must be designed and reviewed before any promotion path exists.

## 8. Integrity check scope (v0.4.2, review R2)

- The approval record lives **outside** the adapter folder (`<repair>/universal-port-approvals/<adapter>.json`; installed as `HERMES_HOME/universal-port-approvals/<adapter>.json`). It binds the approved commands to the SHA-256 of **every** adapter file, manifest included. Any edit, including changing only an `outcome` string, makes `register()` refuse to register anything.
- `ADAPTER_LOCK.json` (next to the adapter, outside its folder) records the generated digest. `repair_cli.py verify-adapter` checks the folder against the lock, the reviewed templates and an optional external digest. `WINDOWS_REPAIR_SMOKE.ps1` requires the external digest before doctor.
- **This is integrity, not authentication.** SHA-256 binding detects changes. It cannot tell *who* made them. Someone who can rewrite both the adapter folder and the approval record (or the lock) can defeat it. The only independent reference is the digest published outside the artifact, in the external HANDOFF next to the ZIP. Compare it before review, doctor or enabling. Signed releases or immutable attestations are future work.
- v0.4.3: the digest covers **every** file. `__pycache__` is no longer excluded (see §10).

## 10. Bytecode and other importable artifacts (v0.4.3, review P0 on v0.4.2)

- v0.4.2 ignored `__pycache__`. Python may execute `__pycache__/__init__.cpython-XY.pyc` (for example an unchecked-hash `.pyc`) **instead of** the reviewed `__init__.py`. The reviewer's PoC registered `CACHE_UNAPPROVED`, while `verify-adapter` still reported the matching external digest. That is reproduced and covered by `tests/test_v043_bytecode_gate.py`.
- The fix is a **pre-import gate outside the adapter** (`pre_import_gate.py`). It allows exactly `ADAPTER_MANIFEST.json`, `__init__.py`, `claude_command.py`, `plugin.yaml` and the manifest-listed `commands/*.md`, and nothing else. It rejects `__pycache__`, `.pyc`/`.pyo`, extension modules (`.so`/`.pyd`, which Python's finder prefers over `.py`), `.pth`, archives, extra `.py`, case variants, symlinks and junctions. It never imports the adapter. `verify-adapter`, `approve`, `stage`, our own loader and the smoke script all run it first.
- **A pass describes the tree at the moment of the scan.** Anyone who can write to the folder afterwards can still plant files before Hermes imports it. So:
  - stage into a **fresh** folder with `repair_cli.py stage` (only the locked files are copied)
  - keep that folder access-controlled
  - run `verify-adapter --adapter <staged>` **immediately** before every Hermes start
  - run Hermes with `PYTHONDONTWRITEBYTECODE=1`, so its own Python does not write a cache. That variable stops *writing* caches, not *reading* them; the gate covers reading.
- If Hermes runs without that variable, its Python writes `__pycache__` into the adapter on first import. The gate then fails on the next check, and an approved adapter refuses to register (digest mismatch). That is fail-closed by design: re-stage and set the variable.
- The gate covers the **adapter folder only**. Code elsewhere on Hermes' import path (other plugins, site-packages, `.pth` files there, Universal Port's own folder) is outside its scope. Each of those can run code regardless of this adapter.
- The gate is checked with a mock loader. Hermes' real plugin loader (pinned source `a9ff979`) has not been exercised against it. Re-test on the pinned Hermes version.

## 9. Not executed in the build environment

No Hermes CLI, no Windows and no PowerShell were available (v0.4.3 included). `WINDOWS_REPAIR_SMOKE.ps1` and `INSTALL_WINDOWS.ps1` are covered only by static text tests. Their Windows path handling, native exit-code behavior, stderr handling and the doctor/validate interaction have not been observed. `HERMES_HOME` isolation redirects Hermes' data folder. It is **not** an OS sandbox for the code that doctor imports and runs in-process.
