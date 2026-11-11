# Final review ledger

Statuses: `ACCEPT_CANDIDATE` · `FIX_REQUIRED` · `HOLD` · `NOT_TESTED`.

**Every disposition here is the implementing agent's self-review recommendation. None of it is independent human approval.** The operator's own acceptances are marked as such.

| ID | Item | Status | Evidence | Blocks submission? |
|---|---|---|---|---|
| L01 | Offline regression (Windows) | ACCEPT_CANDIDATE | 373 OK, 3 skipped at `0e1c7af` (360 before P6.7) | no |
| L02 | Offline regression (clean Ubuntu, Python 3.12) | ACCEPT_CANDIDATE | 360 OK, 2 skipped on `525e3e7` | no |
| L03 | GitHub-hosted CI, run `42866486105` | HOLD (externally blocked) | `BILLING_BLOCKED / NOT_EXECUTED`; jobs never started | no (operator deferred) |
| L04 | Upstream provenance of the stage | ACCEPT_CANDIDATE | 14/14 git-blob match at `e605d8dd…` (`docs/evidence/p6-final-review/upstream-tree-e605d8dd.txt`) | no |
| L05 | Stage hash integrity (`SOURCE_HASHES`, `PORTING_REPORT`, active = original = installed) | ACCEPT_CANDIDATE | `RUNTIME_PERMISSION_AUDIT.md` §6 | no |
| L06 | Generated package Doctor + validate | ACCEPT_CANDIDATE | `docs/evidence/p6-final-review/{doctor,validate}-stage.txt`: PASS, security scan safe | no |
| L07 | UVP Doctor | ACCEPT_CANDIDATE | `doctor-uvp.txt`: PASS, 4 tools, 0 hooks | no |
| L08 | UVP `hermes plugins validate` (catalog CI gate) | ACCEPT_CANDIDATE (fixed in `3bd461d`) | `validate-uvp-after-d2.txt`: PASS, security scan caution (one audit-doc sudoers mention). Representation-only change; equivalence pinned by `tests/test_scan_representation.py`. Pre-D2 `validate-uvp.txt` FAIL kept as negative evidence. | no |
| L09 | Private core-import warnings (rule 9) | ACCEPT_CANDIDATE with disclosure | Warnings only (do not fail): `scripts/*` dev tools and `uvp_arxiv_p5.py` | no |
| L10 | `requires_hermes` floor | ACCEPT_CANDIDATE (fixed in `3bd461d`) | `plugin.yaml` declares `">=0.22.7"`; validate parses it | no |
| L11 | Repository visibility | **HOLD** | `hermes-universal-port` is **PRIVATE**; the catalog requires a public clonable repo. **Operator decision D1.** | **yes, for the catalog PR** |
| L12 | Compatibility registry integrity | ACCEPT_CANDIDATE | Hash-pinned evidence; loader refusal tests (31 in `tests/test_compat_engine.py`) | no |
| L13 | Candidate promotion gate + rejected-candidate ledger | ACCEPT_CANDIDATE | `apply_reviewed` gate tests; `676ead16…` NOT_PROMOTABLE twice over (ledger + independent check) | no |
| L14 | Connector exclusion (`SKILLS_ONLY_PARTIAL`) | ACCEPT_CANDIDATE | No active root MCP in the stage; 16 connectors unported; stage scan safe | no |
| L15 | Namespaced registration, `skill_view` resolution, traversal refusal, slash-argument delivery | ACCEPT_CANDIDATE | `docs/evidence/p6-runtime/verify-001.json` | no |
| L16 | Rollback of the foreign-package install | NOT_TESTED | Documented (runbook §7); config backup present. Not exercised, to keep the demo install. | no |
| L17 | Three-Skill E2E run 001 | ACCEPT_CANDIDATE (**operator-accepted** as functional evidence) | `docs/evidence/p6-e2e-run-001/` | no |
| L18 | Cross-host semantic equivalence | HOLD (NOT_ESTABLISHED) | `SEMANTIC_FIDELITY_REPORT.md` | no, if not claimed |
| L19 | PRD AT-1.4 vs AT-2.2 timeout/idempotency contradiction | FIX_REQUIRED (annotation only) | `ARTIFACT_TRACEABILITY_REPORT.md` C-1. The executed artifact stays unedited. | no |
| L20 | E2E write boundary | FIX_REQUIRED for any rerun | Writes outside the run dir were not prevented (`HERMES_WRITE_SAFE_ROOT` unset; gateway host); merely not attempted. Hardening documented in runbook §8. | no (disclose) |
| L21 | `skill_manage` available during E2E | HOLD (disclosed risk) | Part of the `skills` toolset; not called; drift check clean | no |
| L22 | Operator runbook corruption (duplicate sections, broken §4a code block) | ACCEPT_CANDIDATE (fixed) | WP3 commit | no |
| L23 | README and P6 doc stale or inaccurate claims | ACCEPT_CANDIDATE (fixed) | WP3 commit | no |
| L24 | Apache-2.0 attribution for redistributed excerpts | ACCEPT_CANDIDATE (fixed) | `ATTRIBUTION_AND_LICENSE.md`; license copy in `docs/evidence/` | no |
| L25 | Catalog entry, PR description, security disclosure | ACCEPT_CANDIDATE (prepared, not published) | `docs/submission/` | depends on L08, L11 |
| L26 | 90-second demo package | ACCEPT_CANDIDATE (script + capture list prepared); recording NOT_TESTED | `docs/submission/DEMO_90S.md` | recording pending (operator) |
| L27 | P6.7 semantic review loop (optional) | ACCEPT_CANDIDATE (slice); candidates HOLD for operator | `docs/P6_7_SEMANTIC_REVIEW.md`, `docs/evidence/p6-7-semantic-review/`; 13 tests; 0 model calls; nothing applied | no |
| L28 | P6.8 Skill continuity | ACCEPT_CANDIDATE as EXPERIMENTAL (not registered) | `ee748f2`; 10 tests; `docs/evidence/p6-runtime/continuity-001.json` (real skill_view loader) | no |
| L29 | P6.9 Safebox | ACCEPT_CANDIDATE as EXPERIMENTAL, POLICY_ONLY / NOT_ISOLATED | `b61d739`; 8 tests; bypass report never claims enforcement | no |
| L30 | P6.10 isolation runner | ACCEPT_CANDIDATE for UVP-owned workloads; Hermes execution NOT isolated | `763b066`; `docs/evidence/p6-10-isolation/probe-run-001.json` (7/7 denied, control allows) | no |
| L31 | P6.11 routing + lazy loading | ACCEPT_CANDIDATE as EXPERIMENTAL; no cost claim | `d2d7772`; 6 tests; `docs/evidence/p6-11-routing/measure-001.json` | no |
| L32 | P6.7 per-obligation NLI evidence | ACCEPT_CANDIDATE (mock-only) | `0d593fd`; 14 tests | no |
