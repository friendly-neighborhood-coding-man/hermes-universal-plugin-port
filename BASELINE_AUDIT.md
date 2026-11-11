# Baseline Audit — v0.3.5 → v0.4.0 (Phase 0)

## Source of truth

| Item | Value |
|---|---|
| Archive | `Hermes-Universal-Port-v0.3.5-COMPATIBILITY-INSPECTION.zip` (from the project shared folder) |
| SHA-256 | `75de6f44096a8f50bb81611f86b0522d4143b34d45285745315b469eeca94bdd` |
| Handling | Copied, then extracted to a separate working directory. The original archive was not modified. |
| Top folder | `hermes-universal-port-v0.3.5/` (38 files, 4,409 Python lines incl. tests) |

## Environment actually used (verified, not assumed)

| Item | Observed |
|---|---|
| OS | Linux cloud sandbox (**not** the user's Windows/PowerShell machine) |
| Python | 3.13.18 |
| Node | v22.23.4 (not used by v0.4.0 code or tests) |
| `hermes` CLI | **Not installed.** Installing/running Hermes from source was **denied** by the sandbox's safety policy (executing externally downloaded code). |
| `D:\Hermes-Lab\data` | Not accessible and deliberately not requested. No user profile, Gateway or credentials were touched. |
| Network | Read-only `git clone` of public GitHub repositories worked; `api.github.com` returned 403; `hermes-agent.nousresearch.com` was blocked; `code.claude.com` docs were readable. |

## Baseline test run

```text
python -m unittest discover -s tests -v
Ran 91 tests in 0.718s
OK
```

91/91 passed, matching the expected baseline. No environmental or code failure.

## Reference sources consulted (read-only, never executed)

| Source | Pin | Used for |
|---|---|---|
| `NousResearch/hermes-agent` | commit `a9ff9799e273f525b82718cdc69fdec71b1dca5a` (2026-11-07) | Plugin API, skill invocation, inline shell, `inject_message`, built-in command list, official importer docs. Blob ids are recorded in `hermes_target.py`. `pyproject.toml` says version `0.0.0`, so the commit is the only reliable identity. |
| Claude Code docs "Extend Claude with skills" | `https://code.claude.com/docs/en/slash-commands`, fetched 2026-11-07, SHA-256 `977bb9f8d6a004c37e6731afd94bc3ad7bba1e64a2b2d7e7f22df910d4b06287` | Exact `$ARGUMENTS`, `$N`, `$ARGUMENTS[N]`, `$name`, escaping, `!` injection, `allowed-tools`, `disallowed-tools`, `context: fork` semantics. |
| `wshobson/agents` `plugins/git-pr-workflows` | commit `4bde3168b43c0655c4d00ea2726e631719908a6d` | Real-world command fixture (read as data; not redistributed). |

## Reusable components (kept intact)

| Module | Kept for | v0.4.0 relation |
|---|---|---|
| `port_core.py` | analysis, pinned GitHub fetch, staging, path safety | Reused (`analyze`, `safe_child`). One security fix: staged SKILL.md shell defusal. |
| `port_flow.py` | `/universal-port` job pipeline | Extended with `repair`, `passport`, `reconcile`; staged-skill defusal step. Existing commands unchanged. |
| `equivalence_router.py` + `verified_mappings.json` | strict direct-bridge registry | Unchanged. Registry still has **zero** mappings; no record invented. |
| `compatibility_contract.py` | loss report, v1 snapshot, permission inventory | Unchanged; `permission_inventory` reused by the importer comparison. |
| `host_capabilities.py` | static feature audit | Unchanged (see corrections below). |
| `runtime_bridge.py` | opt-in delegate probe, `args-preview` | Unchanged. |
| `adaptive_chunks.py` | model-patch chunking | Unchanged; the repair path makes no model calls. |

## Native Hermes interfaces identified (from source at the pinned commit)

- `ctx.register_command(name, handler, description, args_hint)`: handler gets the raw argument string; a name that collides with a built-in is skipped with a warning.
- `ctx.inject_message(content, role="user") -> bool`: classic CLI queues to pending input, or to the **interrupt** queue while the agent runs. Gateway/TUI require `plugins.entries.<id>.allow_gateway_injection: true`.
- `/skill-name <text>` appends the text as an instruction and has **no** `$ARGUMENTS` substitution. SKILL.md supports only `${HERMES_SKILL_DIR}` and `${HERMES_SESSION_ID}`.
- `skills.inline_shell` (default **off**) executes every `` !`cmd` `` anywhere in SKILL.md, with the skill directory as CWD.
- `ctx.ask_choice` works only in a synchronous slash handler.
- Official `agent-importers`: Claude `commands/*.md` → "Skipped with a note"; Bash allow/deny rules → `command_allowlist` / `approvals.deny`; non-Bash rules are unmapped.
- No per-command tool pre-approval or tool removal exists (nothing equivalent to `allowed-tools` / `disallowed-tools` was found).

## Findings that change earlier assumptions

1. **`allowed-tools` grants, it does not restrict.** Per the Claude docs it pre-approves the listed tools for one turn. `disallowed-tools` is the restricting key. v0.3.5's audit text treated `allowed-tools` as a limit. v0.4.0 classifies `allowed-tools` as "pre-approval not preserved (Hermes is stricter)" and `disallowed-tools` as a **permission VIOLATION** that blocks the command.
2. **Claude substitutes placeholders inside code fences.** v0.3.5 `compile_skill_invocations` deliberately skipped fenced `$ARGUMENTS`, so the SKILL.md fallback diverges, for example in `git-workflow.md`'s JSON block. The v0.4.0 native adapter reproduces Claude's behavior. The fallback is unchanged and documented as divergent.
3. **Inline-shell hazard in staged skills.** v0.3.5 copied `` !`cmd` `` verbatim into staged SKILL.md. If a user enables Hermes `skills.inline_shell`, that text would execute with the wrong CWD and without Claude's permission check. It would also run patterns that Claude treats as literal (`KEY=!`cmd``). Fixed: staged skills are defused.
4. **Command-name collisions.** Hermes silently skips plugin commands that collide with its 131 built-ins and aliases (e.g. `/review`, `/plan`, `/init`, `/status`). v0.4.0 renames to `<plugin>-<command>` and records it.
5. **Real-world latent bug, reproduced faithfully.** In `git-pr-workflows/commands/onboard.md`, "stipend processed (`$1,500`)" becomes the *second argument* under Claude Code whenever two or more arguments are given. v0.4.0 renders it exactly as Claude would and reports a `currency_like_$1` warning. It does not rewrite it.
