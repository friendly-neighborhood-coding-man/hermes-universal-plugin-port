# Hermes Universal Port roadmap

These are engineering targets, not evidence of delivered behavior.

## Current checkpoint — 2026-11-10

- v0.4.3: 205 offline tests on prior baseline; Claude `/summarize` E2E
  operator-observed through integration adapter (NOT Direct Bridge), with
  runtime differences and unverified semantic equivalence.
- v0.5 P0/P1: **232 tests PASS (3 skipped)** on operator's Windows worktree;
  `hermes plugins doctor <worktree> --ci` PASS with three existing tools.
- Hermes test profile doctor: SQLite/session stores writable, OpenRouter
  connectivity OK. Missing `.env`, config migration and optional tools
  reported; no evidence those warnings block P2 preview.
- P2: `/uvp` command and `uvp_route` tool added, preserving existing
  `/universal-port` and three port handlers. **Hermes CLI preview E2E PASS
  (operator-observed)**: research/coding classification, missing defaults,
  `PLAN_INCOMPLETE`, and `execution_performed: false`. This does NOT prove
  `uvp_route` model-tool invocation or actual Skill execution. See
  [P2 E2E](E2E_UVP_PREVIEW_V050.md).
- v0.5.1 P3 (operator-reported): **246 tests PASS (3 skipped)** on Windows;
  `hermes plugins doctor <worktree> --ci` PASS, plugin manifest 0.5.1,
  four tool registrations, zero hooks. This is offline + Doctor validation,
  **P3 live Skill candidate E2E PASS (operator-observed)**: Hermes returned
  the 38-Skill catalog, arxiv/grounded-citations/claude-code/codex candidates,
  all DISCOVERED_UNAPPROVED and executable=false; no execution claimed.
  See [P3 E2E](E2E_SKILL_CANDIDATES_V051.md).
- v0.5.2 P4 code added for a bounded, version-pinned arXiv metadata
  lookup: offline `/uvp --arxiv-plan`, operator-interactive standalone
  execution gate, one GET maximum, strict response bounds and a local receipt.
  **P4 offline tests PASS in operator's Windows checkout**: 269 tests
  (3 skipped), Hermes Plugin Doctor PASS (4 tools, 0 hooks), and standalone
  `uvp_arxiv_cli.py plan 1706.03762v1` generated a pinned GET URL,
  request_sha256 `25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84`,
  status AWAITING_OPERATOR_CONFIRMATION, execution_performed=false.
  **P4 live arXiv adapter E2E PASS (operator-observed)**: one approved
  request attempted, receipt SUCCEEDED, matching request SHA-256,
  matching paper ID/version and response body hash. The local receipt was
  not independently inspected; see [P4 live evidence](E2E_ARXIV_LIVE_V052.md).
  **P4 Hermes /uvp --arxiv-plan E2E has not yet been reported.**
  This is a UVP-owned function, **not execution of Hermes arxiv Skill.**
  See [P4 protocol](P4_ARXIV_BOUNDED_LOOKUP.md).
- v0.5.3 P5 authored: explicit Hermes CLI `/uvp --arxiv-execute`
  using a separate process environment opt-in, CLI-only session check,
  exact planned SHA-256, Hermes `ask_choice` human permission, and
  create-only evidence receipt. The model-visible `uvp_route` remains
  preview-only. **P5 tests, Plugin Doctor, and Hermes runtime E2E are
  NOT YET RUN**; no live request was attempted in this code-authoring step.
  See [P5 protocol](P5_HERMES_ARXIV_GATE.md).
- v0.5.3 operator-observed Hermes P5 preview E2E: `/uvp --arxiv-plan`
  returned the expected exact URL and digest with no execution.
  `/uvp --arxiv-execute` returned `CLI_ONLY`, execution_performed=false.
  This proves fail-closed behavior but did NOT prove the intended
  `DISABLED_BY_DEFAULT` gate. **Actual surface was not printed**; local
  `tui` is a grounded hypothesis from upstream Hermes docs.
  See [diagnostic evidence](P5_CLI_ONLY_DIAGNOSTIC_V054.md).
- v0.5.4 corrective code added: explicit local `cli`/`tui` surfaces,
  default-disabled flag checked first, no-execution `/uvp --surface`
  diagnostic and extra regression cases. **v0.5.4 tests, Doctor, and
  corrected Hermes E2E have not yet been reported.**
- v0.5.4 operator-confirmed default-deny E2E: `/uvp --surface`
  returned `unknown` and `/uvp --arxiv-execute` returned
  `DISABLED_BY_DEFAULT`, execution_performed=false. The old diagnostic
  did not differentiate empty, generic-local, or error cases.
- v0.5.5 adds **diagnostics only**: `session_surface_lookup` and
  host's slash command `platform` keyword, both read-only, no execution
  privilege change. Added negative tests for generic local and missing
  context; **v0.5.5 tests/Doctor/live UI output not yet reported**.
  See [P5 unknown-surface analysis](P5_UNKNOWN_SURFACE_V055.md).
- v0.5.5 operator report: `/uvp --surface` gave
  `session_surface=local`, `session_surface_lookup=generic_local`,
  `host_dispatch_platform=local`, and local_surface_permitted=false.
  No network executed. This supports the upstream gateway generic-local
  origin and explains the conservative block.
- v0.5.6 development patch: a generic local result can pass the **host
  identity gate** only if the slash handler receives the host's actual
  `SessionSource(platform=Platform.LOCAL)`, nonempty session ID/key and
  matching dispatch platform. The existing disabled-by-default, exact
  request digest, single GET, Hermes `ask_choice` and receipt constraints
  still apply. P5 tests now cover 32 focused methods, including
  opt-in/disabled read-only diagnostic behavior. Operator-reported
  **v0.5.6 full Windows regression: 301 tests OK (3 skipped)**;
  **Hermes Plugin Doctor PASS** (standalone v0.5.6, 4 tools, 0 hooks).
  This validates offline behavior and plugin registration.
  **P5 host-bound /uvp --surface diagnostic E2E PASS (operator-observed)**:
  session_surface=local, session_surface_lookup=generic_local,
  host_dispatch_platform=local, host_local_source_verified=true,
  host_context_status=HOST_BOUND_LOCAL, session_id_present=true,
  session_key_present=true, local_surface_permitted=true,
  live_execution_opt_in=false, execution_performed=false.
  This is a read-only host binding proof, **not** an approved P5
  network execution or cryptographic authentication.
  **P5 v0.5.6 default-deny command E2E PASS (operator-observed):**
  `/uvp --arxiv-execute 1706.03762v1 <full-digest>` returned
  `DISABLED_BY_DEFAULT`, execution_performed=false,
  approved_capabilities_added=0, with exact planned request digest.
  With the process flag disabled the execution handler returns before
  prompting or attempting its arXiv GET.
  See [P5 host-bound gate](P5_HOST_BOUND_V056.md).
- Official importer A/B functional comparison: **NOT RUN**.
- No production installation authorized.

## Immediate next

1. v0.5.6 301-test offline gate, Hermes Doctor, read-only host binding,
   and disabled-by-default `--arxiv-execute` E2E are verified by
   the operator in the disposable profile.
2. Before any enabled execution, separately review the Hermes approval
   UI and exactly one request-specific operator authorization. An opt-in
   flag is not itself a request approval; the fresh `ask_choice` is
   mandatory. Do not repeat an API GET automatically.
3. If an enabled execution is approved, inspect the create-only receipt
   and check execution origin, request/response hashes, exact paper ID,
   total attempts and any unknown/failed outcome.
4. Controlled native Hermes arxiv Skill A/B, Direct Bridge equivalence,
   and Research → Coding composition remain unverified.

## Later

- Prompt-native AGENTS.md guidance with measured invocation adherence;
  mandatory routing requires runtime enforcement, not prose alone.
- Bounded LLM escalation for ambiguous domain/capability selection.
- Selective porting invoked for a real, measured compatibility gap.
- Signed or otherwise trusted evidence provenance and independent witness.
- No silent write/network/execute/credential-sending permissions.


## Future proposal — UVP-optimized CLI components (not implemented)

After submission and stabilization, evaluate selectively adapting permissively licensed upstream CLI building blocks for UVP's specific workflow. **This is a roadmap proposal only**, not a claim of current functionality or permission to copy unreviewed code.

- **Rich** (terminal presentation): adapt only if necessary for compact compatibility reports, source/changed-file provenance, full-digest review and clear install/undo receipts.
- **Questionary** (interactive prompts): tailor for explicit source-fetch consent, `SKILLS_ONLY_PARTIAL` acknowledgement, candidate-bound approval and installation confirmation. Fail closed on EOF, non-TTY, cancellation or UI error.
- **filelock** (workspace concurrency): tailor for per-workspace mutual exclusion, interrupted-run recovery and atomic state transitions. A UI lock is not an authorization or OS sandbox.
- **Optional Agent Skills reference validation**: compare supported Skill syntax against the public format, with a non-authoritative reference check; do not replace UVP's provenance or execution-security gates.

**Implementation preference:** first try upstream libraries as optional, version-bounded dependencies. Fork or vendor only a small, independently reviewable component when a measured Hermes compatibility, dependency-size or performance issue justifies the ongoing maintenance. Preserve the upstream copyright notices, applicable license text, attribution and modification notices; review the actual file licenses and transitive inclusions at pinned versions. Maintain a `THIRD_PARTY_NOTICES.md` and source/patch provenance when copying. Do not confuse an MIT license with a blanket waiver of its conditions.

**Acceptance before activation:** unchanged noninteractive CLI and approval semantics; full source/candidate digest checks; Windows and Linux regression; Hermes catalog Doctor/Validate; dependency and license audit; no new model calls, foreign-code execution or permission bypasses. Keep experimental optimizations out of the catalog-pinned release until independently reviewed and approved.

Private DIAPORIA Change Journal / Failure Intelligence are not shipped here.
