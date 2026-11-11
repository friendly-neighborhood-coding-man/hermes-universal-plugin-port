# DRAFT: catalog PR description (NOT SUBMITTED; operator approval required)

**Title:** `plugin-catalog: add universal-plugin-port (community)`

---

Adds `plugin-catalog/universal-plugin-port.yaml`, pinned to `<40-hex SHA>` of https://github.com/friendly-neighborhood-coding-man/hermes-universal-port. I am the repository owner (rule 5).

## What it does

Universal Plugin Port (UVP) helps a Hermes user bring a plugin from another agent ecosystem into Hermes without trusting it blindly. Given a user-named source it:

1. **Inspects** the plugin's capabilities without running its code (Claude Code/Cowork, Codex, OpenClaw).
2. **Reports what cannot be ported** (MCP/OAuth connectors, hooks, agents, host-specific commands) instead of dropping them silently.
3. **Stages** a Hermes-native package (`plugin.yaml` plus a static `ctx.register_skill` entrypoint) with the original files byte-preserved under `original/`. It never installs or enables anything.
4. **Maps compatibility deterministically.**
   - A versioned rule registry applies only mappings backed by hash-pinned behavioral evidence.
   - Each remaining difference is reported as a residual with its exact source span.
   - A residual reaches the model only through an operator-approved, single-edit fallback. The output stays an unapplied review candidate and must pass independent post-proposal checks plus a rejected-candidate ledger.

It is demonstrated on Anthropic's Apache-2.0 `knowledge-work-plugins/product-management`, pinned at `e605d8dd…`:

- The 8 Skills were staged inert, with 14/14 files matching the upstream git blobs.
- The deterministic engine mapped 7/8 Skills with 0 model calls.
- In a disposable Hermes v0.22.7 home, namespaced registration, `skill_view` resolution and `..`-traversal refusal were verified.
- One three-Skill research → PRD → roadmap run loaded all three ported Skills and wrote three artifacts.

**What it does not claim:** semantic equivalence with Claude Code, connector compatibility, or automatic migration of arbitrary plugins.

## Hermes surfaces used

`ctx.register_command` (`/universal-port`, `/uvp`), `ctx.register_tool` (4 tools: `port_probe`, `port_fetch`, `port_stage`, `uvp_route`), `ctx.llm.complete_structured` (only on explicit operator approval), `ctx.dispatch_tool("skills_list")` (read-only) and `ask_choice` approvals. No hooks, middleware, core overrides or Desktop code.

`hermes plugins validate` warns about private core imports (rule 9). These occur in:

- `scripts/probe_hermes_target.py` and `scripts/p6_runtime_verify.py`: offline operator verification tools, never imported by `register()`.
- `uvp_arxiv_p5.py`: `gateway.session.SessionSource` for local-host binding.

## Disclosures (rule 13)

- **Network:**
  - `port_fetch` / `/uvp` fetch a user-named public GitHub repository at an immutable commit, only when the user explicitly asks.
  - The P5 arXiv adapter can make a single bounded GET to `export.arxiv.org`. It is default-off and needs both an environment opt-in (`UVP_ENABLE_ARXIV_EXECUTION=1`) and a fresh approval.
- **Files outside plugin data:**
  - Staging output goes to a user-chosen directory.
  - P6 domain defaults are written to one JSON file in `HERMES_HOME`, with undo.
  - Source folders the user names are read.
- **Child processes:**
  - `hermes plugins doctor` / `validate` run on a staged package (no shell, 65 s timeout).
  - For **OpenClaw** sources, foreign JavaScript can run through a local `node` sidecar, **only after a separate explicit `run_foreign_code` consent**. This is **not sandboxed** and is disclosed in the tool schema.
- **Model calls:** only through `ctx.llm.complete_structured` after explicit operator approval, for one bounded edit candidate.
- **Credentials and telemetry:** none stored, none read, no telemetry, no background processes, no self-updater (rule 3).

## Validation

`hermes plugins validate --install-deps` on a fresh clone at the pinned SHA: `<paste output>`. Local results before pinning are in `docs/final-review/FINAL_REVIEW_LEDGER.md`.

Offline tests: 360 OK on Windows and Ubuntu.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
