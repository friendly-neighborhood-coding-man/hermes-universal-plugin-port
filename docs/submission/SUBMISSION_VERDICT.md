# Submission verdict (2026-11-11, KST)

**Verdict: READY_FOR_SUBMISSION_REVIEW.** The operator still approves, and performs, every outward step.

## Verified release

- Public repo: https://github.com/friendly-neighborhood-coding-man/hermes-universal-plugin-port
- Release SHA: **`86b4e6d3097b4f96e26529e53daa09b9c314fef0`**. Its tree is byte-identical to the audited `git archive` snapshot built from private `28520b2` (audit CLEAN, 257 files). The history was appended to; nothing was force-pushed.
- Anonymous clone (no credentials), Windows, Python 3.14: **438 tests OK** (4 skipped).
- Public GitHub Actions run 42938106750: **success** on ubuntu-latest and windows-latest, Python 3.13.
- `hermes plugins validate` (v0.22.7) on the anonymous clone: **Validation passed**. The security scan reports caution only: `sudoers_mod`, a documentation line naming a Hermes denylist path. No `--install-deps` was needed because no dependencies are declared.
- The superseded public `2bfc222` failed validate on the recorded injection phrase; it is kept in history. The earlier `e21ca26` remains as it was.

## Evidence index

| Claim | Evidence |
|---|---|
| First-time-user flow: 9 steps, 4 operator inputs, 19 automatic, 0 model calls | `docs/evidence/p6-13/guided-e2e-002.log` |
| Genuine before/after in real Hermes: both failure classes fail on the verbatim copy and pass after adaptation, 3 of 3 Skills | `docs/evidence/p6-13/before-after-001.json` |
| Bounded NLI: 5 calls, $0.080 list-price equivalent, diagnostic only | `docs/P6_13_NLI_EXPERIMENT_REPORT.md`, `docs/evidence/p6-13/nli-experiment-001/` |
| Earlier evidence, unchanged: run-001, P6.7 review, P6.10–P6.12 matrices; rejected candidate `676ead16…` kept | `docs/evidence/` |
| Risks | `docs/submission/RISK_REGISTER.md` |
| Demo script (storyboard v3) | `docs/submission/DEMO_90S.md` |
| Catalog entry (draft, pinned to the release SHA) | `docs/submission/universal-plugin-port.yaml`, `CATALOG_PR_DESCRIPTION.md` |

## Needs operator approval (not done)

- File the Hermes Catalog PR.
- Record and upload the demo.
- Post on X.
- Submit the hackathon form.
- Report the `ctx.llm` `max_tokens` host finding (S10) to Hermes maintainers.

## Not done

- WP6, a second foreign package.
- Executing the official importer for the comparison.
- Attributing the non-backup files that differed after the before/after rollback (R4).
