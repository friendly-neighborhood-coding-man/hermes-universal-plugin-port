# v0.3.4 Hermes Gateway acceptance — staged in small steps

Pinned test: `https://github.com/wshobson/agents/tree/main/plugins/git-pr-workflows`

Existing Run ID: `244e3cef48ed`, pinned commit `4bde3168b43c0655c4d00ea2726e631719908a6d`.

## 0. Verify installation and connection

Non-admin PowerShell, no live porting job while upgrading:

```powershell
$env:HERMES_HOME = 'D:\Hermes-Lab\data'
hermes plugins list --plain --no-bundled | Select-String 'universal-plugin-port'
hermes gateway status
hermes --tui --in 'D:\Hermes-Lab\e2e-sandbox'
```

The plugin should show enabled v0.3.4, not an old backup. Use the temporary/scratch workspace, never a production checkout.

## 1. Re-audit the earlier run (restores inert Agent reference)

```text
/universal-port audit 244e3cef48ed
```

This verifies source identity, copies any missing foreign Agent definition to `references/foreign-agent-source/` **without executing it**, then recomputes the static audit. No LLM invocation, download, or installation.

## 2. Read-only argument handling test — no model calls

```text
/universal-port args-preview 244e3cef48ed git-workflow -- main --no-push --draft-pr
```

Check exact `raw` and `argv`, with `executed=false`. This is a real call into the native plugin's parser, but **not** a full execution of the foreign Git command.

## 3. Read-only preserved role preview — no model calls

```text
/universal-port delegate-preview 244e3cef48ed git-pr-workflows-code-reviewer -- Explain three possible review concerns in a fictional Python authentication module; do not request or access local files.
```

Check `agent_name`, source path, pinned commit, digest and the prominent `INHERITED_FROM_PARENT` capability warning. No code runs and no child is created.

## 4. Optional live Hermes child probe — USE ONLY A DISPOSABLE PROFILE/WORKSPACE

**Do not do this if your current Hermes profile has production file, terminal, GitHub or MCP permissions.** The current Hermes child implementation inherits parent toolsets; a prompt warning is not enough to sandbox it. Use a separate minimal-privilege test profile if you decide to test real delegation.

```text
/universal-port delegate-run 244e3cef48ed git-pr-workflows-code-reviewer --allow-inherited-tools -- Provide a text-only review checklist for a fictional Python login function; do not read local files, make changes or access tools.
```

The Hermes TUI should show a real `ctx.ask_choice` picker. Choose **Cancel** first: expected `DENIED_OR_UNAVAILABLE`, no `delegate_task` call. Choose **Run** only after deliberately configuring safe child permissions. Expected `DISPATCH_RETURNED` only means the tool returned; it does not imply the child finished. The child may continue in the Hermes agents UI.

```text
/universal-port bridge-evidence 244e3cef48ed
```

The record must never say `semantic_parity_verified: true` just because a child was launched.

## 5. No privilege escalation / no promotion

```text
/universal-port status 244e3cef48ed
```

Expected status remains `VALIDATED_PARTIAL_REVIEW_REQUIRED`; `installed=false`. Do not run the generated `git-workflow` against a production checkout. The native bridge tests do not reproduce Claude Code phase checkpoints or enforce approvals before Git writes.

### If a live probe fails

Record the returned `status`, not the full untrusted child output or credentials. The local `BRIDGE_EVIDENCE` folder saves checksums, role identity and dispatch state. A network/transport error after dispatch may mean the child was started; **do not retry blindly**.

## Cost-aware routing check (new in v0.3.4)

Before a costly new retry, inspect the completed run without model calls:

```text
/universal-port route 244e3cef48ed
```

Inspect `D:\Hermes-Lab\data\plugin-data\universal-plugin-port\runs\244e3cef48ed\COST_ROUTE.json`. Confirm:

- `verified_mapping_count` is **0** on this distribution, unless a maintainer independently added tested trusted contracts.
- `direct_bridge_calls` should be **0** with the initial registry.
- Claude Task delegation, approval, and caller-argument semantics remain AI Integration candidates, not "verified direct bridges".
- `semantic_parity_verified` stays **false**; status remains Partial; nothing installed.

Any later direct mapping must be evaluated with matching source commit, command SHA-256, Hermes distribution version, and contract tests. A synthetic unit test is never sufficient to certify a production mapping.
