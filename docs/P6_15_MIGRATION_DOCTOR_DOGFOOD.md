# P6.15 Migration Doctor: real dogfood of the official Hermes agent-importers

> Public v0.7.0 note: the raw evidence directories this report cites (`docs/evidence/p6-15/`, `docs/evidence/p6-16/`) are kept in the private development repository and are not part of this release. `scripts/uvp_repair_smoke.sh` reproduces the workflow.


**Exit decision: `PARTIAL_DOGFOOD_VERIFIED`.** The real official importer, the two real Skill packages and a real Apply plus postflight in a fresh Hermes home all pass their gates. Grok Bot, OpenBot and OpenClaw are **not** supported: UVP detects their issues and HOLDs, but no Apply was attempted for them. Interrupted-import recovery is not implemented. Private CI is blocked by billing.

Evidence: `docs/evidence/p6-15/import-assurance/`. No model calls, no paid usage, no production profile. The upstream code was not modified.

## Pinned sources

| Source | Pin | Identity |
|---|---|---|
| NousResearch/hermes-official-plugins `agent-importers` (MIT) | commit `8b5b6296bbb900f90e296b4729d2c9a5d1139825` | git tree `25067206bc8e574072c0527065175956de43c352`; UVP whole-folder digest `046035a6c0f7be4cca7e86fbb9caf9cae924c18096355c53c25999908514cfe6` (computed on a Windows `core.autocrlf=true` checkout and reproduced on the same bytes under Linux; a native-LF checkout gives a different digest, so the git tree is the canonical identity) |
| anthropics/knowledge-work-plugins `product-management/skills/synthesize-research` (Apache-2.0) | `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3` | tree SHA in `skill-compat-001.json` |
| openai/skills `skills/.curated/pdf` (Apache-2.0 per its LICENSE.txt) | `49f948faa9258a0c61caceaf225e179651397431` | tree SHA in `skill-compat-001.json` |

Hermes Agent: v0.22.7 (`b200f5bc60e3`), in a new disposable home bootstrapped for this run.

## CI diagnosis

The PR #6 jobs ended about 1 s after starting, with no steps. The check-run annotation says: "The job was not started because recent account payments have failed or your spending limit needs to be increased." **INFRASTRUCTURE (billing), not a test or workflow failure.** The public repository's Actions are unaffected.

## Phase 1: real official importer, three agent formats (`matrix-002.json`, `matrix-linux.txt`)

`scripts/p615_dogfood_matrix.py` runs the real `AgentImporter(execute=False)`.

| Scenario | Claude Code | Codex CLI | Cursor |
|---|---|---|---|
| Two Skills, normal memory | REVIEW_ONLY | REVIEW_ONLY | REVIEW_ONLY |
| Memory over the Hermes limit (2,200) | HOLD | HOLD | HOLD |
| Existing Skill collision | HOLD | HOLD | HOLD |

The matrix passed 9/9 on Windows and 9/9 on Linux (WSL, Python 3.12.3). In every case both Skills were accounted for, the target home and source were unchanged, and no approval or install happened.

The official importer itself budgets memory against a hard-coded `MEMORY_CHAR_LIMIT = 20_000`. Hermes's `memory.memory_char_limit` defaults to 2,200. UVP simulates against the target's real limit.

## Phase 2: two real Skill packages (`skills-002.json`, `skill-compat-001.json`)

| | synthesize-research (Anthropic) | pdf (OpenAI) |
|---|---|---|
| Official preview, 3 layouts | imported (3/3) | imported (3/3) |
| Hermes registration after the official Apply | `skill_view` success (Claude Code, Codex, Cursor) | `skill_view` success (all three) |
| Relative resources | **`../../CONNECTORS.md` broken.** Hermes: `Path traversal ('..') is not allowed.` | no links leaving the folder |
| Dependencies and tools | none declared | Python `reportlab`, `pdfplumber`, `pypdf`; system Poppler (`pdftoppm`), `uv`; **not installed, not checked** |
| Host-specific content | `$ARGUMENTS` (Claude command syntax) | `agents/openai.yaml` (Codex metadata; Hermes ignores it); shell placeholders `$INPUT_PDF`, `$OUTPUT_PREFIX` |
| Runnable behaviour | NOT_EXECUTED (no model calls) | NOT_EXECUTED |
| Semantic equivalence | NOT_ESTABLISHED | NOT_ESTABLISHED |

**A copied Skill is not a working Skill.** The official importer reports both as imported. UVP's postflight shows that one has a broken resource and the other depends on tools the importer never checks.

## Phase 3: real Apply in a disposable Hermes home (`apply-e2e-004`, `apply-e2e-005-codex`, `-cursor`)

The flow is: official preview, UVP preflight receipt (`scripts/p615_preview_official_import.py`), **simulated test approval** of that exact receipt hash, official `AgentImporter(execute=True)`, then UVP postflight (`scripts/p615_apply_official_import.py`). The driver is `scripts/p615_apply_e2e.py`.

Before Apply, UVP checks:
- the disposable marker;
- `REVIEW_ONLY`;
- the receipt hash equals the approval;
- the official package digest;
- the source tree digest;
- the whole-home target digest;
- the target `memory_char_limit` and `user_char_limit`;
- that a **fresh preview reproduces the approved plan**.

It then backs up `config.yaml`, `memories/`, `skills/` and `import-sync.json`.

| Check | Claude Code | Codex | Cursor |
|---|---|---|---|
| Wrong approval hash refused before any write | yes | yes | yes |
| Official counts | 3 imported, 0 conflict, 0 error | same | same |
| Both Skills present and byte-equal to source | yes | yes | yes |
| Hermes `skill_view` (real Hermes runtime) | both succeed | both succeed | both succeed |
| `MEMORY.md` within the Hermes limit; Hermes `MemoryStore` loads | 190 / 2,200; loads | yes | yes |
| Unexpected changed paths | none | none | none |
| Broken linked resources (postflight) | `synthesize-research -> ../../CONNECTORS.md` | same | same |
| Replaying the same approval after Apply | refused (target changed) | refused | refused |
| Scoped rollback | the home is byte-identical to the pre-Apply inventory, excluding `installs/` (Hermes's runtime environment) | same | same |

## Phase 4: other agent families (`grok-openbot-003-system-python.json`, `-004-hermes-venv.json`)

**Grok Bot, synthetic two-Bot export, official `GrokBotImporter(execute=False)`:**

| Problem | Evidence | UVP |
|---|---|---|
| #265 several Bots merged into one profile | export with 2 Bots, no `--bot` | **HOLD** |
| #266 routines without a schedule | 2 routines (event trigger, schedule text only) | listed (WARN) |
| #264 imported routines deliver locally | scheduled routines become paused local jobs | listed (WARN) |
| **New: dry-run side effect** | the preview creates `cron/` and `cron/output/` in the target home | **HOLD** (whole-home digest) |
| **New: silent downgrade** | under a Python without `croniter`, the official preview plans 0 cron jobs and saves all routines as "no schedule" notes, with no error. Under Hermes's own runtime it plans 1 or 2 jobs correctly. | **HOLD** (UVP's independent count of scheduled routines differs from the plan) |
| Secret in memories (`sk-…` fake) | not present in UVP's receipt | PASS |

**OpenBot:** the preview creates `<target>/cache` (the scratch parent) during a dry run. Classified as **PREVIEW_SIDE_EFFECT**; the evidence is kept.

**OpenClaw:** NOT_TESTED. It uses a separate migration and backup engine.

None of these families is supported for Apply.

## Phase 5: UVP-side fixes in this PR

- **Whole-home side effects:** the preview CLI digests the **whole** target home (everything except `installs/`) and the source before and after the preview, and HOLDs on any change. The earlier check covered only the memory destinations.
- **Memory limits:** the target's `config.yaml` is the source of truth. A `--memory-limit` that disagrees is refused. `USER.md` is budgeted with `user_char_limit` (1,375), not the `MEMORY.md` limit.
- **Redirects:** symlinks or junctions in the source, or in the target's `memories/`, `skills/`, `cron/` or `config.yaml`, are refused. There is a Windows junction test; the symlink test needs a privilege Windows does not grant here.
- **Approval binding:** the approval is bound to the exact receipt hash. It is refused if the official package, source or target home changed since the preflight, or if a fresh preview differs.
- **Postflight:** checks installed bytes, Hermes resolution of each Skill and **of every link inside it**, memory size against the Hermes limit, and unexpected writes. It offers a scoped rollback.
- **Grok checks:** an independent routine inventory (catches the silent downgrade) and checks for #264, #265 and #266.

**Not done:**
- Recovery from an interrupted import and partial rollback.
- An exhaustive source inventory for Claude Code, Codex and Cursor (the loss ledger is still `OFFICIAL_REPORTED_ITEMS_ONLY`).
- Grok, OpenBot or OpenClaw Apply.

## Proposed upstream patches (not submitted)

1. `importer.py`: budget against the target profile's `memory.memory_char_limit` and `user_char_limit` instead of `MEMORY_CHAR_LIMIT = 20_000`. Reproduce with the memory-overflow cases in `matrix-002.json`.
2. `grok_bot.py`: when `cron_jobs.parse_schedule` fails because `croniter` is missing, record an **error** instead of treating the routine as unscheduled. Reproduce with `grok-openbot-003-system-python.json`.
3. `grok_bot.py` (or core `cron.jobs`): do not create `cron/` or `cron/output/` during `execute=False`.
4. `openbot.py`: use a scratch directory outside the target (for example the system temp dir) when `execute=False`.

## Tests

| Suite | Result |
|---|---|
| Windows full regression | 469 OK, 6 skipped |
| Linux full regression (WSL, Python 3.12.3) | 469 OK, 16 skipped |
| PR #6 tests: `test_official_import_assurance`, `test_p615_official_cli`, `test_p615_dogfood_contract` | 12 + 7 (1 skipped: symlink privilege) + 1 OK |

## Reproduce

```bash
git clone https://github.com/NousResearch/hermes-official-plugins.git upstream-official && git -C upstream-official checkout 8b5b6296bbb900f90e296b4729d2c9a5d1139825
python scripts/p615_dogfood_matrix.py --official-package upstream-official/agent-importers --report matrix.json
python scripts/p615_external_skill_probe.py --official-package upstream-official/agent-importers --skill-pack <synthesize-research> --skill-pack <pdf> --report skills.json
python scripts/p615_skill_compat_report.py --skill-pack <synthesize-research> --skill-pack <pdf> --report compat.json
python scripts/p615_grok_openbot_probe.py --official-package upstream-official/agent-importers --hermes-src <hermes-agent> --report grok.json
python scripts/p615_apply_e2e.py --official-package upstream-official/agent-importers --home <bootstrapped disposable home with .uvp-disposable> --evidence <new dir> --skill-pack <synthesize-research> --skill-pack <pdf> [--agent codex|cursor]
```
