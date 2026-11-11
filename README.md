# Hermes Universal Port

**Bring a Claude/Cowork Skill package into Hermes Agent, and see exactly what works, what breaks, and why.**

Hermes Universal Port (UVP) is an experimental, standalone open-source tool for Hermes Agent. It stages a pinned foreign package without running it, and reports every capability Hermes cannot honour. It then applies only deterministic, hash-recorded adaptations and checks the result in a real, disposable Hermes home. It can roll the whole thing back.

> Independent community project; not an official Hermes / Nous Research or Anthropic component. Use a disposable Hermes home only; a disposable `HERMES_HOME` is **not** an OS sandbox.

## What it shows in one minute

The pinned target is Anthropic's Apache-2.0 `knowledge-work-plugins/product-management`. The check uses three of its Skills, the real Hermes v0.22.7 resolver and `skill_view`, and **no model calls** ([evidence](docs/evidence/p6-13/before-after-001.json)):

| What the installed Skill text tells the user or model to do | Verbatim copy in Hermes | After UVP adaptation |
|---|---|---|
| Run its documented Usage command (`/write-spec ...`) | **Fails**: the token does not resolve in Hermes | Resolves as `/ported-product-management:write-spec`; the argument is delivered |
| Open its referenced resource `../../CONNECTORS.md` | **Fails**: `Path traversal ('..') is not allowed.` | Opens; the file states the connectors are **NOT connected** |

This holds for all three pilot Skills. Both failures are real Hermes behaviour, not simulated. Each adaptation is recorded with before and after SHA-256 in `ADAPTATION_MANIFEST.json`, and `original/` stays byte-identical.

## Quickstart (guided, disposable)

Requires Python 3.12+ (tested on 3.12 and 3.14) and the Hermes CLI on `PATH` (or `HERMES_EXE`). Every step that downloads, stages or installs needs its own explicit flag.

```bash
python uvp_guided.py init    --workspace ./uvp-demo
python uvp_guided.py select  --workspace ./uvp-demo
python uvp_guided.py inspect --workspace ./uvp-demo --i-approve-fetch
python uvp_guided.py stage   --workspace ./uvp-demo --i-accept-skills-only-partial
python uvp_guided.py install --workspace ./uvp-demo --i-approve-install
python uvp_guided.py verify  --workspace ./uvp-demo
python uvp_guided.py demo    --workspace ./uvp-demo
python uvp_guided.py undo    --workspace ./uvp-demo
python uvp_guided.py status  --workspace ./uvp-demo
```

A clean first-time run took 9 commands, with **4 operator inputs** (the workspace and three approvals) and **19 automatic steps**. It made no model calls ([log](docs/evidence/p6-13/guided-e2e-002.log)).
- `init` bootstraps the new Hermes home once, which took about 6 minutes in that run.
- `install` validates the package before swapping it in and rolls back automatically on failure.
- `demo` prepares a three-Skill research to PRD to roadmap prompt and prints the command. Running that command calls a paid model, so UVP never runs it for you.

The guided `install` uses the verbatim stage. The adapted package (`adapt_package.py`) is exercised by `scripts/p6_before_after.py` and the tests.

## How it compares with Hermes's own importer

Hermes's `agent-importers` plugin documents that it copies Skills into `~/.hermes/skills/claude-code-imports/` and skips commands. UVP instead:
- pins the source commit and verifies it;
- keeps the originals byte-identical;
- reports unsupported capabilities by name (`SKILLS_ONLY_PARTIAL`);
- rewrites only what a deterministic, evidence-pinned rule covers;
- installs as a namespaced plugin with rollback.

This comparison is **documentation-based**: the official importer was **not executed**, so whether its copy hits the same two failures is NOT_RUN ([`importer_comparison.py`](importer_comparison.py)).

## Honest limits

- **Semantic equivalence between Claude and Hermes is NOT ESTABLISHED.** A model followed the ported Skills once (run-001). That is functional evidence, not equivalence.
- **Bounded LLM-NLI check:** one operator-approved run, 5 calls, $0.08 at list price. The result is diagnostic only: 1 of 6 verdicts was accepted, and every other one was routed to human review or discarded ([report](docs/P6_13_NLI_EXPERIMENT_REPORT.md)). That run also found that Hermes v0.22.7's `ctx.llm` ignores a plugin's `max_tokens` on the native Anthropic provider.
- **What is not ported:** connectors (MCP/OAuth), hooks, agents and commands.
- **Safebox is policy, not a sandbox.** It has 3 confirmed bypasses.

## P6 v0.6.0 hackathon prototype — EXPERIMENTAL

The pinned foreign target is Anthropic's Claude/Cowork product-management package with three demonstrable Skills: `synthesize-research`, `write-spec`, and `roadmap-update`. A synthetic eight-interview fixture supports an evidence-grounded three-step research → PRD → roadmap task.

**Operator-verified status, 2026-11-11** (details in the [runbook](docs/P6_OPERATOR_RUNBOOK.md)):

- **Tests:** Windows 427 OK (4 skipped) at `413b22e` (P6.12). Clean Ubuntu Python 3.12: 360 OK (2 skipped) on `525e3e7`. GitHub-hosted CI is `BILLING_BLOCKED / NOT_EXECUTED`.
- **Source and stage:** the pinned source is staged inert, and all 14 files match the upstream git blobs.
- **Generated package:** Doctor and validate PASS.
- **Deterministic compatibility engine:** maps 7 of 8 Skills with **0 model calls**. It reports unsupported connectors and the unresolvable `../../CONNECTORS.md` instead of hiding them. See [P6_COMPAT_ENGINE.md](docs/P6_COMPAT_ENGINE.md).
- **Runtime checks** in a disposable Hermes home (v0.22.7): namespaced registration, `skill_view` resolution, refusal of `..` traversal and slash-argument delivery all PASS.
- **One three-Skill Hermes run** loaded all three ported Skills and wrote three artifacts. It is accepted as functional execution evidence.
- **Cross-host semantic equivalence: NOT ESTABLISHED.** See the [final review reports](docs/final-review/).
- **`hermes plugins validate` on UVP itself: PASS** (security scan: caution) after the D2 representation fix (`3bd461d`). The scanner is unchanged; see [FINAL_REVIEW_LEDGER](docs/final-review/FINAL_REVIEW_LEDGER.md).

### Feature status

| Status | Features |
|---|---|
| **IMPLEMENTED** (tested; on by default where applicable) | Inert pinned staging with byte-preserved originals; unsupported-capability reporting (`SKILLS_ONLY_PARTIAL`); deterministic compatibility engine (`compat_engine.py`) with registry evidence pins; candidate promotion gate + rejected-candidate ledger; P6.10 namespace isolation runner for **UVP-owned workloads** in a disposable WSL distro; P6.12 install / update / rollback / removal for disposable homes (`install_ops.py`, exercised with the real Hermes CLI); P6.13 guided CLI (`uvp_guided.py`) and deterministic package adaptation (`adapt_package.py`: R-C001 usage lines, RES-LOCAL-1 resource localization) |
| **EXPERIMENTAL** (tested as library, callbacks or a TEST-ONLY harness; not registered by `register()`) | P6.7 semantic review loop (deterministic evaluator; LLM NLI evaluator: one bounded paid run, diagnostic only); P6.8/P6.12 authenticated Skill-continuity handoff (`skill_continuity.py`); P6.9 Safebox (`safebox.py`, **POLICY_ONLY / NOT_ISOLATED**, 3 confirmed bypasses); P6.12 Safebox-gated isolated task (`isolated_task.py`, **LIMITED_WORKLOAD_ISOLATION**); P6.11 routing + digest-validated lazy loading (`lazy_routing.py`) |
| **NOT_VERIFIED** | Cross-host semantic equivalence; a live delegated child under continuity or Safebox; OS isolation of the LLM, Hermes or Skill instruction delivery; billed-token cost savings (no offline tokenizer); GitHub-hosted CI on Python 3.13 |
| **ROADMAP** | Connector/OAuth porting; hooks/agents/commands porting; interactive E2E and a Claude-side baseline; automatic multi-Skill orchestration; general cross-agent migration |

The Safebox is policy at Hermes tool dispatch, **not a sandbox**. Slash invocation, `-s` preload and a validate-then-swap race bypass it ([adversarial matrix](docs/P6_12_ADVERSARIAL_MATRIX.md), [security boundaries](docs/P6_12_SECURITY_BOUNDARY_REPORT.md)). Context sizes are exact character counts with a chars/4 approximation, not billed tokens. Details: [P6.12 integration report](docs/P6_12_INTEGRATION_REPORT.md), [P6.8–P6.10](docs/P6_8_TO_10_CONTINUITY_SAFEBOX_ISOLATION.md), [P6.7](docs/P6_7_SEMANTIC_REVIEW.md).

Components on branch `feat/uvp-p6-foreign-multiskill`:

- `uvp_p6_cli.py`: explicit pinned-source fetch and inert partial-skill staging; no automatic install.
- `uvp_p6_stage.py`: SHA-256 source inventory; source-verbatim originals; generated Hermes `plugin.yaml` and namespaced `ctx.register_skill` entrypoint; unsupported MCP/OAuth connectors explicitly excluded.
- `/uvp --p6-preflight`: current Hermes Skill name collision report.
- `/uvp --p6-adapt` and `--p6-apply`: one user-triggered Hermes model call for a bounded `$ARGUMENTS` patch candidate, followed by exact SHA + fresh approval before altering **staging only**.
- `/uvp --p6-defaults` and `--p6-defaults-undo`: each domain asks separately; only installed Skill names are eligible; persistent mapping is reversible and never grants runtime permissions.
- `/uvp --p6-recipe`: outputs a prompt to submit in a new user turn; **does not** perform skill_view calls or claim execution.
- `compat_engine.py` / `compat_cli.py` and the `compat_rules.json` registry: deterministic 1:1 and composition mappings first, residual extraction next, and the approval-gated AI fallback last.
- `scripts/probe_hermes_target.py` / `scripts/p6_runtime_verify.py`: offline Hermes target probe and in-process runtime resolution checks (no model calls).

**Still incomplete:**
- the guided installer (`uvp_guided.py`) covers the one pinned package only;
- an interactive E2E and a Claude-side baseline for semantic comparison;
- a sandboxed write boundary for E2E runs (`HERMES_WRITE_SAFE_ROOT` was not set in run 001).

This pilot is **SKILLS_ONLY_PARTIAL**, not full Claude plugin equivalence.

See [P6 operator runbook](docs/P6_OPERATOR_RUNBOOK.md) and [acceptance contract](docs/P6_FOREIGN_MULTISKILL_HACKATHON.md). The earlier P5 v0.5.6 baseline remains separate and verified.

## Scope

- Detect losses instead of silently dropping unsupported features.
- Deterministically stage selected Claude Code slash commands for Hermes; preserve original command content as far as supported.
- Keep **text transport**, **operator semantic review**, and **runtime verification** separate.
- Require explicit per-command approval before registration and a pre-import integrity gate for generated adapters.
- Preserve function-specific Capability Passports and update impact analysis.

**P2/P3 previews:** `/uvp <prompt>` and `uvp_route` return an unexecuted route plan; `/uvp --candidates <task>` queries only visible Skill names and returns unapproved, non-executable candidates. The bundled approval registry remains empty.

**P4 proof-of-concept:** `/uvp --arxiv-plan <versioned-id>` builds a no-network plan. The standalone `uvp_arxiv_cli.py` requires a separate interactive, exact-request human confirmation to attempt a single pinned arXiv API GET and write a receipt. It is a UVP-owned bounded adapter, **not** execution of Hermes's `arxiv` SKILL.md. [P4 design and safety](docs/P4_ARXIV_BOUNDED_LOOKUP.md).

**P5 (v0.5.6 host binding, pending tests):** a direct user-typed Hermes `/uvp --arxiv-execute <id> <exact-request-sha256>` can access the same **UVP-owned** bounded adapter only after explicit process opt-in, verified local host slash context (concrete `cli`/`tui` or actual Hermes `SessionSource(LOCAL)` plus nonempty bound session ID/key and generic `local` dispatch), and fresh Hermes `ask_choice` approval. `/uvp --surface` reports only boolean presence and sanitized host binding status; **generic `local` alone grants no execution**. Other channels and the model-visible `uvp_route` stay non-executing. [P5 v0.5.6 protocol](docs/P5_HOST_BOUND_V056.md).

**Not yet supported:**
- automatic conversion of arbitrary cross-agent plugins (only the pinned P6 pilot is demonstrated);
- connectors, hooks, agents or commands beyond Skills;
- general semantic equivalence;
- protected approvals against malicious local processes;
- automatic multi-Skill orchestration. The P6 three-Skill run used an explicit, operator-submitted recipe prompt.

## Offline checks

From a reviewed v0.5 development worktree (P5 not yet verified):

```powershell
python -m unittest discover -s tests -v
```

The Windows `WINDOWS_REPAIR_SMOKE.ps1` dry-run Stage 1 does not run Hermes doctor/validate without explicit acknowledgment and a separately verified external adapter digest. A disposable `HERMES_HOME` is **not** an OS sandbox.

Do not run `INSTALL_WINDOWS.ps1` against production while this candidate remains runtime-unverified. For the **named disposable Windows test profile only**, `scripts/UPDATE_TEST_UVP.ps1` performs a staged Doctor check, backup and reversible install of v0.5.6, without enabling network access.

## References

- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [Hermes agent importers](https://hermes-agent.nousresearch.com/marketplace/agent-importers)
- [Hermes plugin development](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)
- [Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## License and affiliation

MIT licensed. Evidence files under `docs/evidence/` quote excerpts of Anthropic's Apache-2.0 `knowledge-work-plugins/product-management` Skills. The license copy is in `docs/evidence/LICENSE-anthropics-knowledge-work-plugins-Apache-2.0.txt`; see [ATTRIBUTION_AND_LICENSE](docs/final-review/ATTRIBUTION_AND_LICENSE.md). **Independent community project; not an official Hermes / Nous Research or Anthropic component.** This public repository does not include DIAPORIA's private orchestration, general Change Journal, or Failure Intelligence.
