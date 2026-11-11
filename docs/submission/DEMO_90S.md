# 90-second demo package: Universal Plugin Port P6

**Recording status: NOT RECORDED. Publication: NOT PUBLISHED** (operator approval required).

Every scene below replays **existing evidence** or runs **zero-model-call** commands. No new paid E2E run is needed to record the demo. The E2E scene shows the accepted run-001 trace and artifacts. It does not run them again.

## Storyline (one claim per scene)

| Time | Scene | On screen | Voice-over (approx. words) |
|---|---|---|---|
| 0:00–0:10 | Problem | Upstream `product-management/` tree on GitHub at `e605d8dd…` | "This is a real Claude/Cowork plugin from Anthropic: 8 Skills, 16 MCP connectors. Hermes can't load it as is." (25) |
| 0:10–0:25 | Inspect and stage, source preserved | `PORTING_REPORT.json` (status `SKILLS_ONLY_PARTIAL`, 16 unported connectors), then the 14/14 git-blob match list | "UVP stages it without running anything. Every original file is byte-preserved, and every one matches the upstream commit. Connectors it can't support are listed, not converted." (30) |
| 0:25–0:45 | Deterministic mapping, 0 model calls | `COMPAT_REPORT.md` counts table + the exact one-line delta for `write-spec` | "Verified rules run before any AI. Seven Skills map deterministically with zero model calls. What's left is reported exactly: here, a resource path Hermes can't reach." (30) |
| 0:45–0:55 | The AI candidate stays a candidate | `check-candidates` output: `676ead16… NOT_PROMOTABLE`, unresolved `/write-spec` | "An earlier AI proposal kept a Claude-only command. UVP's independent checks block it from ever being applied." (20) |
| 0:55–1:05 | Real Hermes resolution | `verify-001.json` gates STRUCTURAL PASS / RESOLUTION PASS; `skill_view` and traversal-refused lines | "Installed in a disposable Hermes home, all eight Skills register under a namespace. `skill_view` resolves them, and path traversal is refused." (25) |
| 1:05–1:25 | Three-Skill execution | `stream.jsonl` tool-call sequence (3 `skill_view`, 3 `write_file`); quick scroll of the three artifacts; `RUN_RECEIPT.json` hashes | "One Hermes session loads the three ported Skills in order and writes the research synthesis, the PRD and the roadmap. Every artifact is hashed." (28) |
| 1:25–1:30 | Honest boundary | `SEMANTIC_FIDELITY_REPORT.md` summary line: `SEMANTIC_EQUIVALENCE = NOT_ESTABLISHED` | "It runs, but we don't claim it behaves exactly like Claude. UVP keeps that gap visible." (17) |

## Captures to take (no model calls)

| # | Capture | Command / file |
|---|---|---|
| C1 | Upstream tree | `https://github.com/anthropics/knowledge-work-plugins/tree/e605d8ddbfb688da57dfaaceebd93f12a64ef1d3/product-management` |
| C2 | Staging report | `D:\Hermes-Lab\p6-staged\ported-product-management\PORTING_REPORT.json` |
| C3 | Blob match | `docs/evidence/p6-final-review/upstream-tree-e605d8dd.txt` plus the comparison loop in runbook §2 |
| C4 | Mapping report | `python compat_cli.py map --stage <stage> --output D:\Hermes-Lab\p6-compat-demo` (new dir), then open `COMPAT_REPORT.md` |
| C5 | Candidate gate | `python compat_cli.py check-candidates --stage <stage>` |
| C6 | Runtime gates | `docs/evidence/p6-runtime/verify-001.json` |
| C7 | E2E trace | `docs/evidence/p6-e2e-run-001/stream.jsonl`, filtered to `tool_use` / `tool_result` lines |
| C8 | Artifacts + receipt | `docs/evidence/p6-e2e-run-001/*.md`, `RUN_RECEIPT.json` |
| C9 | Boundary | `docs/final-review/SEMANTIC_FIDELITY_REPORT.md` §5 |

## Claims to avoid in the video and post

- "Automatically migrates any plugin" or "full ecosystem migration".
- "Equivalent to Claude Code" or "semantic parity".
- "Connectors work".
- "CI green". GitHub Actions was billing-blocked; say "360 offline tests pass locally".
- "Listed in the Hermes catalog" (not yet submitted).

## Remaining work (operator)

1. Record the screen (OBS or Xbox Game Bar), at 90 s or less.
2. Review the voice-over against the claims-to-avoid list.
3. Approve any upload, post on X, or hackathon form submission.

## Storyboard v2 (P6.12): Port → Preserve → Confine → Verify, at most 90 s

Two **separate** execution paths are shown, and each is labelled on screen. They are never presented as one run.

| Time | Scene | On screen (existing evidence or zero-model-call commands) |
|---|---|---|
| 0:00–0:10 | Port | Upstream tree at `e605d8dd…`, then `PORTING_REPORT.json`: `SKILLS_ONLY_PARTIAL`, 16 connectors unported |
| 0:10–0:20 | Preserve | 14/14 git-blob match, plus the compat report: 7/8 mapped, 0 model calls; rejected AI candidate `NOT_PROMOTABLE` |
| 0:20–0:40 | Path A, Hermes execution (run-001) | 3 `skill_view` calls and 3 `write_file` calls in `stream.jsonl`; artifacts and receipt hashes |
| 0:40–0:55 | Confine: policy | `P6_12_ADVERSARIAL_MATRIX.md`: denied rows; **bypass rows shown openly** (slash, `-s`, race); label "POLICY_ONLY" |
| 0:55–1:15 | Path B, isolated workload (WP3) | `isolated-task-e2e-001.json`: real Hermes tool call, grant check, then namespace sandbox. Allowed read/write; denied `/etc`, the Windows drive, network, fork, shell. Label "LIMITED_WORKLOAD_ISOLATION: the LLM is not inside" |
| 1:15–1:30 | Verify | Continuity corpus: 0 false authorizations. Rollback exercise restores `config.yaml`. `SEMANTIC_EQUIVALENCE = NOT_ESTABLISHED` |

Redaction before recording: use the **public snapshot** files, in which the host and account name are sanitized. Show no terminal with the user profile path, and nothing from `auth.json` or `.env`.
