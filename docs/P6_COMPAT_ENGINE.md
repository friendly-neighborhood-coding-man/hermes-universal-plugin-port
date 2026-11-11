# P6 deterministic compatibility engine (vertical slice), 2026-11-11

**Status:** code, tests and one read-only operator run on the real staged plugin are done. **Zero model calls were made.** Nothing was installed, enabled, executed or written inside the stage. Runtime compatibility (a Hermes session loading these Skills) and semantic equivalence are **not** established.

## What it does

The order for each staged Skill is:

1. Verified composition rules first, then verified 1:1 rules, both from the declarative registry `compat_rules.json`.
2. Everything left becomes a **residual**. A residual records its exact span, ±2 lines of context, the rule IDs it tried and why each one failed. It also says whether the bounded AI pipeline may handle it.
3. The model is used only when two things hold: an AI-eligible residual remains, and the operator passed `approved=True`. Even then the call goes through the existing single-delta pipeline (`uvp_p6_patch.propose`). Its output stays an immutable review candidate and is never applied.

| File | Role |
|---|---|
| `compat_rules.json` | Versioned registry (`2026-11-11.1`). Each rule declares its source/target host, capability and version, I/O contract, preconditions, permissions, side effects, graph (for compositions), delta kind, validation case IDs, three verification axes and provenance. |
| `compat_engine.py` | Registry validator, construct scanner, matcher, executor, residual extraction, post-proposal checks, rejected-candidate gate, approval-gated AI fallback and report writer. It reuses `claude_command.py` (frontmatter, placeholder scanning, inline-shell patterns) and `port_core.PortError`. |
| `compat_cli.py` | `map` (read-only on the stage; writes into a new directory) and `check-candidates`. |
| `scripts/probe_hermes_target.py` | Offline behavioral probe of the local Hermes source. It writes `semantics/hermes_target_probe.json`, the target-side evidence. |
| `p6_candidate_ledger.json` | Operator-recorded rejected candidates. It records the `write-spec` candidate `676ead16…51a8`. |
| `uvp_p6_patch.apply_reviewed` | Now also requires `candidate_gate` to pass: the ledger check plus independent checks. |

The registry cannot carry code, regexes, permissions, network access or side effects. It can only select matcher and delta kinds that are implemented in `compat_engine.py`. The loader refuses the whole registry in any of these cases:

- A rule adds a permission, network access, execution, authorization or a side effect.
- Two rules target the same construct, which would make the match ambiguous.
- A composition graph has a cycle, a missing input binding, a source↔target data exchange, or mismatched external inputs.
- A `DIRECT_EXACT` rule is not 1:1.
- An auto-applied rule lacks PASS source and target evidence, or has only code-review target evidence and no behavioral case.
- An evidence file's SHA-256 does not match, or the probe ran on modified Hermes source.

## Rules: verified versus provisional

| Rule | Kind | Status | Structural | Runtime | Semantic | Effect |
|---|---|---|---|---|---|---|
| R-C001 v1 | 2:2 composition: `claude.slash_command_invocation` + `claude.arguments_all_substitution` → `hermes.plugin_skill_slash_invocation` + `hermes.user_instruction_append` | COMPOSED_VERIFIED | VERIFIED | TARGET_FUNCTIONS_PROBED | NOT_ESTABLISHED | Rewrites the Usage-example line `/<skill> $ARGUMENTS` to `/<plugin>:<skill> <argument-hint>` |
| R-D001 v1 | 1:1 literal Markdown passthrough | DIRECT_EXACT | VERIFIED | TARGET_FUNCTIONS_PROBED | INPUT_TEXT_IDENTICAL | Identity |
| R-D002 v1 | `${CLAUDE_SKILL_DIR}` → `${HERMES_SKILL_DIR}` | PROVISIONAL | NOT_VERIFIED | NOT_VERIFIED | NOT_ESTABLISHED | Never applied; a match gives HOLD. The Claude-side meaning is not in the pinned Claude evidence. |
| R-D003 v1 | Skill definition → namespaced `ctx.register_skill` | PROVISIONAL | VERIFIED | NOT_VERIFIED | NOT_ESTABLISHED | Verification only. Claude auto-activation is not Hermes opt-in loading, and no `skill_view` has been executed. |

Target evidence comes from the Hermes source checkout `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`, probed offline. The probe file SHA-256 is `cad380f2…4022`, with 9/9 cases PASS: 6 behavioral and 3 source assertions. **It is not a Hermes session, and the installed Hermes binary was not compared to this checkout.**

The probe established these Hermes facts:

- Hermes does **not** substitute `$ARGUMENTS`.
- It rewrites `${HERMES_SKILL_DIR}` and `${HERMES_SESSION_ID}`.
- Slash invocation appends the user text after the Skill body as `The user has provided the following instruction alongside the skill invocation: <text>`.
- Plugin Skills get the interactive-only key `/<plugin>:<skill>`.
- `skill_view(file_path=...)` rejects any `..` component.

Source evidence comes from `semantics/claude_argument_cases.json` (SHA-256 `77a4542a…06db`). This file is the documented-contract oracle; it was not captured from a running Claude Code.

## write-spec: the six constructs are kept separate

| # | Construct | In write-spec | Engine classification |
|---|---|---|---|
| 1 | Markdown usage example | Line 16, `/write-spec $ARGUMENTS`, inside the `## Usage` fence | Documentation. Neither host executes it. |
| 2 | Host command invocation | A runtime user action | Claude `/write-spec <text>`; Hermes `/ported-product-management:write-spec <text>`. The key is in the static catalog. `runtime_resolved: false`. |
| 3 | Skill definition | Frontmatter: name, description, argument-hint | R-D003, provisional |
| 4 | Hermes namespaced registration | Generated `__init__.py`, `ctx.register_skill("write-spec", …)` | Qualified name `ported-product-management:write-spec`, read statically. The live catalog was not checked. |
| 5 | Runtime `skill_view()` resolution | `skill_view("ported-product-management:write-spec")` | Not executed. It has no user-input channel; the task arrives through conversation context. |
| 6 | Passing user input to the workflow | `$ARGUMENTS` | Claude inlines the text at the placeholder. Hermes slash invocation appends it after the body. Hermes never substitutes `$ARGUMENTS`. |

The rejected AI candidate (`676ead16…51a8`) merged constructs 1, 2 and 6. It replaced the placeholder with prose and left `/write-spec`, which does not resolve in Hermes. The candidate file and its JSON remain **unmodified** in `P6_REVIEW_CANDIDATES/`. The engine gives it `NOT_PROMOTABLE` for two independent reasons: it is in the ledger, and the independent capability-resolution check reports `/write-spec` as unresolved. `apply_reviewed(..., approved=True)` now refuses a candidate of this shape, and a test covers that refusal.

R-C001 produces the deterministic replacement with no model call:

```diff
-/write-spec $ARGUMENTS
+/ported-product-management:write-spec <feature or problem statement>
```

`<feature or problem statement>` is the Skill's own `argument-hint`, copied verbatim.

### Relative resource `../../CONNECTORS.md`

The link resolves in the **source** tree (`original/CONNECTORS.md`) but **not** in the active plugin tree: the stage has no root `CONNECTORS.md`. Hermes `skill_view(file_path=...)` would also refuse the `..` path. Seven Skills report it as an `unresolved_resource` residual. It is not AI-eligible, because fixing it is an operator packaging decision, not a text adaptation. It keeps those Skills' structural axis at `NOT_VERIFIED`.

### Connectors

The `~~category` placeholders, such as `~~project tracker`, are reported as `SKILLS_ONLY_PARTIAL` items. They are not mapped, connected or emulated. The text is left unchanged, and each Skill already says to proceed without them. The 16 `.mcp.json` connectors remain unported.

## Operator run 001 (read-only on the real stage)

```powershell
python compat_cli.py map --stage D:\Hermes-Lab\p6-staged\ported-product-management --output D:\Hermes-Lab\p6-compat-run-001
```

- Registry SHA-256 `5128904b…6ce8`. A copy of the report is in `docs/evidence/p6-compat-run-001/`.
- **Counts:** 8 Skills; 35 DIRECT_EXACT identity regions; 7 composed mappings applied; 0 already mapped; 8 provisional verifications; 7 unresolved residuals (all `../../CONNECTORS.md`); **0 AI-eligible residuals**; 16 unsupported items; 7 files changed in the *output* directory; 0 holds.
- **Model calls: 0.**
- The SHA-256 of every file in the stage was identical before and after the run.

`product-brainstorming` has no `$ARGUMENTS`, so it is unchanged. The `HOLD` paths are covered by tests, not by this run: wrong version, missing argument-hint, multiple placeholders and a provisional rule.

## Tests

`tests/test_compat_engine.py` has 31 tests, all offline. They cover:

- A direct mapping and a composition mapping each need 0 model calls; a fake LLM records 0 calls.
- Determinism, and idempotence on the engine's own output (`ALREADY_MAPPED`). Two stage runs produce byte-identical reports.
- CRLF is preserved.
- Wrong source or target version, missing preconditions, an unregistered Skill and a provisional rule each give HOLD with no bytes changed.
- The registry is refused for: ambiguous rules, permission/network/authorization/side-effect growth, cycles, missing or cross-side bindings, a non-1:1 DIRECT_EXACT, evidence that is only code review or has failed, tampered evidence, and unimplemented matchers.
- Candidates are blocked when they add a URL, a connector, an unresolved resource or a frontmatter permission change.
- Relative resources are resolved or reported.
- The AI fallback holds without approval. With approval it produces a candidate only, plus post-proposal checks.
- The rejected write-spec shape cannot be applied, and the ledger blocks even a clean candidate.
- Original and stage bytes are unchanged, and tampered originals are refused.
- The report has no success percentage, and the three axes stay separate.
- The real stage is read-only (this test is skipped if the stage is absent).

Full Windows regression on the final code: **360 tests OK, 3 skipped**. That is the prior 329 plus these 31. Existing P5/P6 tests are unchanged, and the 28 focused P6 tests still pass with the new `apply_reviewed` gate.

## Known limitations

- **Runtime:** no Hermes session has loaded any ported Skill. The three-Skill E2E is still not established.
- **Target identity:** the target is a source checkout. Before installing, rerun `scripts/probe_hermes_target.py` against the Hermes that will actually be used, then update the registry hashes. With a different version the engine gives HOLD.
- **Semantics:** R-C001 verifies only that the user text is delivered. Its *placement* differs: inline on Claude, appended on Hermes. Model-level equivalence is not claimed for any rule.
- **Catalog:** resolution reads the generated `__init__.py` statically, not the live Hermes catalog.
- **Mapped files:** they are review candidates outside the stage. Applying them to the stage, or packaging a root `CONNECTORS.md`, needs a separate operator decision.
