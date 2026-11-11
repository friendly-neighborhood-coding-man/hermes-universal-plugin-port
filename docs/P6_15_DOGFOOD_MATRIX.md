# P6.15 multi-agent / multi-Skill dogfood

Status (updated): REAL OFFICIAL IMPORTER PREVIEW 9/9 (Windows and Linux); real Skill packages 3/3; real Apply + postflight in a disposable Hermes home PASS for Claude Code, Codex and Cursor. See P6_15_MIGRATION_DOCTOR_DOGFOOD.md. Grok Bot / OpenBot: HOLD-detected, not supported. OpenClaw: NOT_TESTED.
PR #5 is held; PR #6 stays Draft; public / Catalog release remains 1334cbb.

## Pinned repositories and licenses

1. Official NousResearch agent-importers (MIT):
https://github.com/NousResearch/hermes-official-plugins/tree/8b5b6296bbb900f90e296b4729d2c9a5d1139825/agent-importers

2. Anthropic product-management / synthesize-research Skill (Apache-2.0):
https://github.com/anthropics/knowledge-work-plugins/tree/e605d8ddbfb688da57dfaaceebd93f12a64ef1d3/product-management/skills/synthesize-research

3. OpenAI curated PDF Skill (Apache-2.0 according to its local LICENSE.txt):
https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/pdf

The third-party Skill sources are only used as test inputs: their tools, dependencies, runtime behavior and semantic portability are NOT assumed to work.

## Reproducible operator commands (disposable environment)

From a reviewed PR #6 checkout:

~~~bash
git clone https://github.com/NousResearch/hermes-official-plugins.git upstream-official
git -C upstream-official checkout 8b5b6296bbb900f90e296b4729d2c9a5d1139825

git clone https://github.com/anthropics/knowledge-work-plugins.git skill-anthropic
git -C skill-anthropic checkout e605d8ddbfb688da57dfaaceebd93f12a64ef1d3

git clone https://github.com/openai/skills.git skill-openai
git -C skill-openai checkout 49f948faa9258a0c61caceaf225e179651397431

python -m unittest discover -s tests -p "test_official_import_assurance.py" -v
python -m unittest discover -s tests -p "test_p615_official_cli.py" -v

python scripts/p615_dogfood_matrix.py \
  --official-package upstream-official/agent-importers \
  --report p615-real-upstream-matrix.json

python scripts/p615_external_skill_probe.py \
  --official-package upstream-official/agent-importers \
  --skill-pack skill-anthropic/product-management/skills/synthesize-research \
  --skill-pack skill-openai/skills/.curated/pdf \
  --report p615-two-real-skills.json
~~~

Use new report file names on retries; output is create-only. Redact local paths before any publication. Imported Skill scripts are NEVER executed by these preview tests.

## Acceptance matrix

| Scenario | Claude Code | Codex CLI | Cursor |
|---|---|---|---|
| Two synthetic Skills + normal memory | REVIEW_ONLY | REVIEW_ONLY | REVIEW_ONLY |
| Excessive source memory | HOLD | HOLD | HOLD |
| Skill name collision in target | HOLD | HOLD | HOLD |
| Real Anthropic + OpenAI Skill folders | 2 Skills accounted | 2 Skills accounted | 2 Skills accounted |

Every source/agent scenario must keep the target-home before/after inventory identical, preserve original source content and produce no model call, import approval or actual install.

LOCAL_MOCK_PASS confirms only the runner against a synthetic upstream-compatible double.
OFFICIAL_PREVIEW_PASS requires running the pinned NousResearch importer code with real or synthetic Skill fixtures.
HERMES_DOGFOOD_PASS requires a separately approved disposable Hermes apply plus actual Skill resolution, memory-write validation and scoped recovery.
SEMANTIC_EQUIVALENCE stays NOT_ESTABLISHED.

## Additional importer families — NOT_YET_TESTED

- Grok Bot: export JSON, per-bot roles, event routines, schedule-text-only routines and two Skills. Separate GrokBotImporter path, needs dedicated work and test fixtures.
- OpenBot: SQLite-based importer; in current upstream source, read_agents creates scratch cache directory under target root even during preview in some cases. Isolate and inspect this side effect before offering read-only claims.
- OpenClaw: separate migration/backup engine; cannot be treated as an AgentImporter subclass.

## Current CI evidence

Root cause confirmed from the check-run annotation: "The job was not started because recent account payments have failed or your spending limit needs to be increased." INFRASTRUCTURE (billing), not a code failure. Real upstream dogfood must be executed with an operator-controlled clone.

NO release promotion, no Catalog pin change, no merge. This is an experimental branch.
