# P6 — Foreign multi-skill plugin port: product-management (2026-11-10)

**Decision:** One real non-native Claude/Cowork plugin; multi-domain opt-in defaults; full multi-skill artifact E2E; preserve source and make only strictly necessary host adaptation.

**Status (updated 2026-11-11):** see the [runbook status table](P6_OPERATOR_RUNBOOK.md#status-as-of-2026-11-11) and the "Runtime verification and E2E run 001" section at the end of this file. Staging, Doctor/validate, deterministic mapping, runtime resolution and one three-Skill Hermes E2E are operator-verified. Cross-host semantic equivalence is NOT established. The original 2026-11-10 status line, kept for history, was: Status: P6 v0.6.0 staged converter, source-pinned fetch CLI, per-domain consent and undo, exact-delta AI patch proposal/apply, collision preflight and three-Skill recipe are CODE AUTHORED. P6 tests, Doctor/validate, real pinned source staging, installation, AI model calls and the three-Skill Hermes E2E have NOT BEEN OPERATOR VERIFIED. This is a hackathon demonstration target, not a claim of general-purpose automatic compatibility.

## Pinned independent source

- Publisher/source: [Anthropic knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins), Apache-2.0. This is a Claude/Cowork plugin collection, not currently a Hermes-native `plugin.yaml` package.
- Subdirectory: `product-management/`
- Pinned repository commit: `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3`
- Immutable source input:
  `https://github.com/anthropics/knowledge-work-plugins/tree/e605d8ddbfb688da57dfaaceebd93f12a64ef1d3/product-management`
- Expected source identity: `product-management/.claude-plugin/plugin.json` name `product-management`, version `1.2.0`.
- Verified original Skill Markdown paths include:
  `skills/synthesize-research/SKILL.md`,
  `skills/write-spec/SKILL.md`,
  `skills/roadmap-update/SKILL.md`,
  and `skills/competitive-brief/SKILL.md`.
- Other skills and optional connectors must be enumerated from the pinned fetched subtree; **do not claim seven installed until inspected**.
- `.mcp.json` includes 16 declared connectors including Slack, Notion, Linear and analytics providers (some incomplete). UVP's existing `normalize_mcp` does **not** support their `type:http`+OAuth semantics. NEVER silently convert, connect or authenticate them. Include in `UNSUPPORTED_CONNECTORS.json`, preserve original bytes in the inert provenance snapshot, and require explicit approval for `SKILLS_ONLY_PARTIAL`. No external API credentials for this demo.

**Crucial preflight:** Hermes must verify the demo source is not already installed (native plugin, exact skill names or equivalent existing capabilities). Otherwise change the candidate and preserve that result in evidence. The source's lack of a Hermes manifest does **not** prove that nobody ported it elsewhere.

## The user-facing workflow

1. User explicitly requests one pinned GitHub plugin. UVP fetches only the selected subdirectory into a disposable profile, records upstream SHA and source file hashes. It never executes foreign code or installs dependencies during analysis.
2. Show all proposed components: native-copy candidates, AI integration-needed items, unsupported connectors, permissions, file changes and provenance. The source remains **read-only as untrusted data**.
3. **Minimal semantic adaptation only:** preserve the original Markdown and helper assets verbatim whenever possible; migrate metadata as required by Hermes. Use the existing bounded Hermes `ctx.llm.complete_structured` exact old/new patch harness only for unresolved host syntax, with deterministic input hashes, strictly bounded edits, resume checkpoints, independent review, per-file before/after SHA and reject-on-error. No unrestricted prose rewriting. No new tool/endpoint/capability permissions may be introduced by the model.
4. Generate actual Hermes `plugin.yaml` and `__init__.py` registering the imported docs with official `ctx.register_skill(name, path)`. Bundle them under a **namespaced plugin**; never overwrite native Hermes bare skill names. Preserve original source files under a non-executing snapshot with manifest. Commands requiring nontrivial host behavior must be adapters, not silent aliases.
5. Verify Hermes Plugin Doctor AND `hermes plugins validate` against staged output; security scan; explicit user approval to install and enable **only in disposable test HERMES_HOME**. Preserve original output and rollback path.
6. Enumerate all applicable domains for the imported package and **ask separately for each domain** whether this package becomes its default. Available choices: `Make default`, `Keep existing`, `Not now`. Default selection never grants run/network/write/credential permissions. Do not overwrite existing defaults without explicitly disclosing the current selection and receiving a fresh choice.
7. Record a versioned per-domain mapping with source SHA, Hermes skill namespace, operator's exact choices and prior defaults. Keep unused domains untouched. Multi-domain support must not be artificially capped at 2 for an **explicitly approved finite recipe**; do not weaken existing preview-only routing's safety limit.
8. Accept one user-submitted multi-skill task. Emit a bounded, explicit 3-step skill invocation plan; only after human initiation load each imported skill using Hermes's native `skill_view("plugin-name:skill")` and execute its step with real Hermes model/tool interactions. Capture invocation logs, intermediate artifact hashes, final artifact content and operator judgment. **A text answer that merely mentions the skills is not execution proof.**
9. Compare source instructions vs adapted skill instructions and resulting artifacts. If actual host tools/dependencies are missing, return `HOLD / PARTIAL` with the missing capability; do not claim success.
10. Record verified run and collect **90-second maximum** screen demo. Catalog PR remains a separate submission from this project's Draft PR.

## Demo: one composite task, three imported Skills

**User task:** "Below are eight fictional customer interview notes about onboarding. Synthesize the research, propose the first-release PRD for reducing onboarding confusion, and create a prioritized Now/Next/Later product roadmap. Avoid inventing user counts or evidence. Save a reviewable Markdown report."

Pipeline:

| Order | Original foreign Skill (source) | Domain default offered | Observable artifact |
|---|---|---|---|
| 1 | `synthesize-research` | research (+ product optional) | `research-synthesis.md` with evidence IDs |
| 2 | `write-spec` | documents / product | `onboarding-prd.md` with must-haves and acceptance tests |
| 3 | `roadmap-update` | planning / product | `onboarding-roadmap.md` with dependencies and tradeoffs |

Three named original Skills must each be loaded in Hermes as their **ported namespaced version**. Record distinct `skill_view` invocations with real session evidence and all three output artifacts. The fixture is `examples/p6-onboarding-interviews.md`.

## Proof and acceptance checklist

- **Provenance:** upstream source SHA exact; source bytes and hashes preserved; no unknown fetched entrypoints executed.
- **Conversion:** Hermes manifest/plugin entry present; all three required Skills registered; original code/instruction preservation diff measured; minimal model patches and rejected proposals recorded; unsupported MCP connectors explicitly blocked and not connected.
- **Default:** operator prompted for each applicable category independently; choices and rollback recorded; no preference change without consent; collisions are detectable.
- **Execution:** Hermès runtime actually loads all 3 namespaced imported skills and completes 3 outputs; no preconstructed hardcoded demo answer; generated files reproducibly trace back to fixture and recorded prompts.
- **Safety:** no secrets, unrelated network, arbitrary shell post-install, or production HERMES_HOME changes. All write/execute actions require user authorization and ordinary Hermes tool policies.
- **Evidence:** local tests, Doctor, validate, code scan, installed manifest, session trace, diff, artifacts and final outcome recorded. Never mark PASS on code alone.

## Engineering order (no premature integrations)

- P6.0 pinned-source and host catalog preflight; failure inventory and scope lock
- P6.1 native Hermes package generation with immutable original and 3 registered Skills
- P6.2 targeted exact-delta adaptation + review checks, fallback on unsupported connectors
- P6.3 per-domain defaults transactional choice, persisted and reversible
- P6.4 explicit 3-step composition and runtime evidence
- P6.5 demo, security/validate, submission

## Non-goals

- General conversion of arbitrary tools, hooks, MCP OAuth, remote browser platforms or credentialed connectors.
- Reproducing the original Claude Code automatic Skill activation exactly. Hermes `ctx.register_skill` is namespaced and opt-in; UVP's controlled domain-default orchestration is an **integration** unless semantic parity is proven.
- Calling the result a Direct Bridge merely because names match.
- Promoting a partially converted source as 100% equivalent, or mutating production profile.

## Technical risk discovered

Current `port_core.stage_portable` for Claude/Codex produces `plugin.json` and an inert `skills/` directory, but not Hermes-native `plugin.yaml` or a `register(ctx)` entrypoint. Existing `uvp_route` is advisory-only and requires all capabilities preapproved/verified and read-only. This P6 must explicitly close both gaps instead of continuing P5 arXiv work.

Official Hermes plugin guidance: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins

Official Hermes plugin skills via `ctx.register_skill`: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/plugins/index.md

## P6.1 implementation checkpoint (code only)

- New `uvp_p6_stage.py`: requires explicit staging consent and a declared 40-char upstream commit; never executes or installs foreign source; preserves source tree in inert `original/` and each source `skills/*/SKILL.md` byte-for-byte; generates Hermes `plugin.yaml` plus static `__init__.py` registering each namespaced skill via `ctx.register_skill`.
- Explicit `allow_partial=true` is mandatory for source MCP/OAuth connectors or host-specific hooks/agents/commands. Unported names are itemized in `PORTING_REPORT.json`; they are not authenticated/connected.
- Original file SHA-256 inventory and source fingerprint recorded. Full commit supplied by caller is explicitly **declared, not cryptographically independently linked** to local files; verify source against the preexisting pinned fetch receipt before installation.
- A marker for foreign syntax such as `$ARGUMENTS` or connector placeholders flags skills for human/model review. **No AI adaptation has yet run.** Generated SKILL.md files still contain the original content.
- Six new offline tests (`tests/test_uvp_p6_stage.py`) cover required consent, blocked connector drop, immutable revision format, source byte preservation, actual static registration, path collisions and no-connector staging. New branch tests have NOT yet been run on Windows or Hermes.
- **This code is not connected to the user's Hermes slash-command installation workflow yet**, and no new real-world skills were registered or executed.

## P6.1 operator test gate

~~~powershell
$work = 'D:\\Hermes-Lab\\uvp-p6-foreign-multiskill' # separate disposable checkout
Set-Location $work
$env:HERMES_HOME = 'D:\\Hermes-Lab\\uvp-v050-hermes-test'
$env:UVP_ENABLE_ARXIV_EXECUTION = '0'
python -m unittest discover -s tests -p 'test_uvp_p6_stage.py' -v
if ($LASTEXITCODE -ne 0) { throw 'P6 staging tests failed' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Full regression failed' }
hermes plugins doctor $work --ci
if ($LASTEXITCODE -ne 0) { throw 'UVP Doctor failed' }
~~~

Above commands are **future test steps**, not evidence of a PASS; do not replace the existing v0.5.6 test plugin with this branch until separately reviewed.

## New P6 implementation checkpoint — CODE ONLY (2026-11-10)

- `uvp_p6_cli.py` exposes explicit pinned-source fetch and opt-in SKILLS_ONLY_PARTIAL inert staging, but neither was actually executed in the operator's Windows profile.
- `uvp_p6_stage.py` generates static Hermes skill registrations, original byte-preserving snapshots and source fingerprints; rejects raw `!\`...` inline-shell syntax rather than silently installing executable foreign content.
- `uvp_p6_patch.py` requests a bounded single Hermes model delta to remove unique Claude `$ARGUMENTS` placeholders; writes only review candidates. A separate `--p6-apply` path verifies the exact candidate SHA and fresh Hermes choice before changing a staged Skill. No model call or application has occurred yet.
- `uvp_p6_defaults.py` requires all three qualified Skills to appear in the real Hermes catalog, then asks individually for `research`, `documents`, `planning`; commits selected preferences in a single JSON file, retains previous values and supports confirmed undo. **This does not grant execution permissions.**
- `uvp_p6_recipe.py` generates a transparent three-Skill task prompt from the current catalog, not an executed result. Real Hermes skill_view calls and output files are still mandatory evidence.
- New focused P6 unit test files: stage (8 tests), defaults (9), patch (8), recipe (3): **28 tests authored; rerun after the byte-hash patch is pending**. Full v0.6.0 regression has not been run; baseline v0.5.6's 301 PASS does not cover P6.
- Old P5 test profile updater is disabled on the P6 branch to avoid accidental replacement of the validated v0.5.6 installation.
- See [operator runbook](P6_OPERATOR_RUNBOOK.md) for safe, check-pointed Windows commands. No new public plugin distribution or official catalog submission has happened.

## Operator-discovered Windows CRLF regression — corrected in source, rerun pending

In the first P6 focused test run on Windows, the operator reported:
```text
Ran 25 tests in 0.735s
FAILED (errors=6)
```
All six exceptions originated in `uvp_p6_patch.checked_staged_skill`:
`PortError: Unverifiable original Skill`. In P6.1 stage the per-Skill
`original_sha256` was computed using `read_text(encoding="utf-8")`
followed by `encode("utf-8")`. The latter method normalizes CRLF to LF
on Windows when reading text, whereas the original source snapshot is
preserved byte-for-byte and P6.2's verifier computes SHA from
`read_bytes()`. Identical source content could therefore fail SHA
comparison due to newline representation.

**Fix:** P6.1 now computes the digest of raw source `read_bytes()`,
decoding those same bytes only for the explicit UTF-8 validity and
inline-shell checks. P6.2's byte-identity check is unchanged. New
cross-platform fixture forces CRLF bytes and confirms the stored hash
and both copies are identical; two tampering regression tests confirm
changed original bytes or forged stored hashes are still refused.

**Status update (operator console, 2026-11-10 KST):**
the patched full v0.6.0 Windows suite completed
`Ran 329 tests in 377.016s` / `OK (skipped=3)`.
Hermes Plugin Doctor on the P6 UVP repository returned
`universal-plugin-port 0.6.0 (standalone)`, discovery, manifest,
import and registration `OK`, `4 tool(s)` and `0 hook(s)`.
Thus **P6 code offline regression / UVP host registration PASS**.
The operator did not separately paste the focused 28-test results;
the 329-test full suite includes test discovery from the full tests
folder. **The actual foreign package has not yet been downloaded,
staged, Doctor/validated, enabled or executed in Hermes.**

## P6 post-fix operator evidence — 2026-11-10

```text
Ran 329 tests in 377.016s
OK (skipped=3)
Plugin Doctor: D:\Hermes-Lab\uvp-p6-foreign-multiskill
  manifest: universal-plugin-port 0.6.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 4 tool(s), 0 hook(s)
```

`P6_CODE_OFFLINE_PASS`: operator-observed, not independently replayed.
`FOREIGN_SOURCE_FETCH`, `STAGED_PLUGIN_DOCTOR`, `STAGED_PLUGIN_VALIDATE`,
`INSTALLED_SKILLS_VISIBLE`, `MULTI_DOMAIN_DEFAULTS` and
`THREE_SKILL_E2E`: **NOT YET RUN**.
Next gate: follow `docs/P6_OPERATOR_RUNBOOK.md` steps 2–3,
fetch pinned foreign source and inspect/validate the generated package
without installing or executing it.

## Operator-observed actual foreign package stage + Hermes validation — 2026-11-10

The operator provided an end-to-end PowerShell console transcript for the
pinned Anthropic `product-management` subtree.

- `uvp_p6_cli.py fetch` exited 0; parsed `fetch.commit_sha` matched
  `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3`. The fetch JSON
  `source_path` and the upstream byte comparison were not pasted.
- `uvp_p6_cli.py stage` exited 0 and produced
  `D:\Hermes-Lab\p6-staged\ported-product-management`.
  The stage status check confirmed `SKILLS_ONLY_PARTIAL`.
- **Generated foreign plugin Doctor PASS**:
  `ported-product-management 0.6.0 (standalone)`, load/manifest/import/
  registration OK, `0 tool(s), 0 hook(s)`. These counts do not report the
  number of registered skills.
- **Generated foreign plugin `hermes plugins validate` PASS**, including
  loadable, capability probe, declared tool/hook matching, no core override,
  and security scan `safe`. Host isolation mode reported `plugins.isolation:
  host`, not a sandbox claim.
- The printed stage report `universal-port.p6-stage/1` lists **8**
  registered skill candidates: `competitive-brief`, `metrics-review`,
  `product-brainstorming`, `roadmap-update`, `sprint-planning`,
  `stakeholder-update`, `synthesize-research`, `write-spec`.
  All rows report `copied_verbatim=true`,
  `runtime_equivalence_verified=false`,
  `requires_manual_review=true`.
- `source_fingerprint_sha256` =
  `56a2cac583cba7a28962d7cc02d5a9bc2e4e6dbb59781fe57e05bbb91fe3d83b`.
- **Explicitly not ported:** 16 MCP/OAuth connector declarations (including
  Notion, Slack, Linear, Figma, Amplitude, Asana) and Claude-specific
  `commands`. No connector authorization or network execution claimed.
- Stage report confirms `installation_performed=false`,
  `runtime_execution_performed=false`,
  `domain_defaults_changed=false`,
  `model_rewrites_performed=false`.

**Gate classification:** `FOREIGN_PINNED_FETCH_OBSERVED`,
`FOREIGN_HERMES_STAGE_DOCTOR_PASS`, `FOREIGN_HERMES_VALIDATE_PASS`
(**operator-observed**).
`ORIGINAL_BYTE_INDEPENDENT_AUDIT`, `P6_MODEL_DELTA`,
`HERMES_INSTALLED_SKILLS_VISIBLE`, `P6_DOMAIN_DEFAULTS`,
`P6_THREE_SKILL_E2E` are all **pending**. A stage manifest's 8 Skill names
are not equivalent to eight verified `skills_list` or `skill_view` results.

**Next gate:** independently compare the immutable original source and
each staged Skill SHA-256 against the reported hashes, verify no root-level
MCP config is activated, and check generated namespaced Hermes registration.
Only then perform reviewed adaptation/installation in a brand-new disposable
Hermes profile, preserving P5 evidence and production profile.

## Operator-observed byte integrity — 2026-11-10 KST

A separate PowerShell read-only audit iterated the eight `skill_reviews` entries
from `D:\Hermes-Lab\p6-staged\ported-product-management\PORTING_REPORT.json`.
For every Skill, it computed `Get-FileHash -Algorithm SHA256` independently
over both `original/skills/<name>/SKILL.md` and
`skills/<name>/SKILL.md` and compared each to the recorded
`original_sha256`. All **16 of 16 file comparisons passed**:

```text
PASS: competitive-brief
PASS: metrics-review
PASS: product-brainstorming
PASS: roadmap-update
PASS: sprint-planning
PASS: stakeholder-update
PASS: synthesize-research
PASS: write-spec
P6 BYTE INTEGRITY PASS — 8 skills, no root MCP configuration
```

The operator also checked the staged *root* for both `mcp.json`
and `.mcp.json` and found neither file. The upstream `.mcp.json`
may remain in the inert `original/` snapshot; that is not an
active root MCP declaration. This does **not** prove the upstream remote
files were independently compared, that Hermes installed/loaded eight
Skills, or that the foreign Markdown is semantically equivalent.

**New gate classification:** `LOCAL_STAGE_BYTE_INTEGRITY_PASS`,
`NO_ACTIVE_ROOT_MCP_CONFIG_OBSERVED`. Remaining:
`P6_MODEL_DELTA`, `P6_INSTALLED_SKILLS_VISIBLE`,
`MULTI_DOMAIN_DEFAULTS`, `THREE_SKILL_E2E`: **PENDING**.
Preserve stage files unchanged until patch proposals are reviewed.

## Operator first real model-generated patch candidate — REVIEW HOLD (2026-11-11 KST)

The operator invoked
`/uvp --p6-adapt write-spec D:\Hermes-Lab\p6-staged\ported-product-management --approve-model-call`.
The actual Hermes runtime returned `status=REVIEW_REQUIRED`,
`model_calls=1`, `registered_skill_modified=false`, and SHA-256
`676ead16cc3574dffdcf3b7aa6913fbe97b171d168c14467310507187d3851a8`.
The proposal's unique edit is:

- old: `/write-spec $ARGUMENTS`
- new: `/write-spec <the current user's task: feature or problem statement>`

**Manual review decision: HOLD, do not apply.**
The new invocation keeps the Claude-specific `/write-spec` slash
command, whereas the generated Hermes package registers a namespaced
Skill at `ported-product-management:write-spec`, accessible via
`skill_view("ported-product-management:write-spec")`. Replacing a
placeholder in the example does not demonstrate that a usable Hermes
entrypoint exists or bind any runtime argument. No `--p6-apply` approval
was given. The model's recorded limitations included an incomplete
excerpt and unseen full frontmatter.

Additional independent review of the pinned upstream skill shows a
relative `[CONNECTORS.md](../../CONNECTORS.md)` link. The P6
staging code preserves full upstream source under inert `original/`
but copies individual Skill directories separately under `skills/`;
the link therefore does not automatically resolve in the ACTIVE
`skills/write-spec/SKILL.md` tree. Treat this as a separate
`RESOURCE_PATH_REVIEW_REQUIRED` before execution; retain originals.

A new candidate must be generated in a separately reviewed path/run
without overwriting or silently deleting the existing rejected
proposal. No active Skill has been modified or executed.

## Runtime verification and E2E run 001 — 2026-11-11 KST

- **Runtime:** Hermes Agent v0.22.7, local `b200f5bc60e3`, in the disposable P6 home. The target probe re-run under the runtime venv is byte-identical (`cad380f2…`).
- **Install:** the verbatim validated stage was installed and enabled in the disposable home only, after operator approval. `verify-001`: STRUCTURAL PASS and RESOLUTION PASS. All 8 namespaced Skills register; `skill_view` resolves the three pilot Skills; `../../CONNECTORS.md` is refused (traversal); slash-argument delivery is verbatim. 0 model calls.
- **E2E run 001** (`docs/evidence/p6-e2e-run-001/`): one bounded `--oneshot` session.
  - Three distinct successful `skill_view` calls; three artifacts written.
  - The harness wrote `RUN_RECEIPT.json` afterwards, because the model had no hash tool.
  - A first launch attempt was rejected before any model call (`--run-budget` is unsupported via the gateway). It is preserved.
- **Accepted** by the operator as functional execution evidence. Semantic equivalence is NOT established; see `docs/final-review/`.

