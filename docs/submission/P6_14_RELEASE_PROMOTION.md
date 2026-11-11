# P6.14 release-promotion recommendation

**Disposition: `READY_FOR_RELEASE_PROMOTION_REVIEW`.** Nothing has been promoted. `VERIFIED_RELEASE` is unchanged.

| State | Value |
|---|---|
| VERIFIED_RELEASE (public, catalog pin in NousResearch/hermes-agent#153110) | `86b4e6d3097b4f96e26529e53daa09b9c314fef0` |
| ACTIVE_CANDIDATE (private, PR #4) | `9ea1ee92d6f630bec2242d619db1c53f1957945f` |
| Candidate public snapshot (local, not pushed) | `D:\Hermes-Lab\uvp-public-release-007`, commit `76eeed26a6c455c8765348e77c52f826a77c8a33`, tree `cd2aeeb8f3c4aeea0638b94b5ca18583ea91e937` |

## Gates

| Gate | Result |
|---|---|
| Full Windows regression (private `9ea1ee9`) | PASS: 449 tests OK, 5 skipped |
| Ubuntu regression (snapshot tree, disposable WSL distro, Python 3.12.3) | PASS: 449 OK, 15 skipped |
| Hermes Doctor (snapshot) | PASS: runtime discovery, import and registration; 4 tools, 0 hooks |
| Hermes Validate `--install-deps` (snapshot) | PASS: security scan caution only (`sudoers_mod`, a doc line) |
| Security / identity audit (snapshot tool) | CLEAN: 0 findings, 5 sanitized files recorded |
| License and provenance | Unchanged since `86b4e6d`: Apache-2.0 notices on every adapted file (4(b)), originals byte-preserved, upstream 14/14 blob match |
| Real clean-home integrated E2E | PASS (E2E-002 on `3172adf`; later commits change docs and evidence only) |
| Clean anonymous clone | **Not run.** Needs the snapshot published. |
| Public GitHub Actions CI | **Not run.** Needs the snapshot published. |

## What promotion would involve (needs operator approval)

1. Append the snapshot tree as a new commit on top of public `main`, with no force-push. `86b4e6d` stays in history as the fallback.
2. Re-run the anonymous clone, the tests, validate and public CI on the new SHA. Stop if any of them fails.
3. Push a SHA bump of the existing Catalog PR #153110 (rule 4: the same PR, old → new SHA), not a second entry.

Until then, the public release's guided `install` still installs the verbatim stage (risk R13). The P6.14 flow should be demoed from the private candidate or, after promotion, from the new release.

## Promotion executed (2026-11-11, operator-approved)

- Public `main` → **`1334cbbda8bd37f1a06178b72a533fde59686c06`** (parent `86b4e6d`, no force-push), tree `cd2aeeb8f3c4aeea0638b94b5ca18583ea91e937`, snapshot rebuilt from private `9ea1ee9` (audit CLEAN, 5 sanitized files reviewed).
- Gates on that exact commit, all PASS:
  - Anonymous clone: Windows 449 OK (5 skipped), Ubuntu 449 OK (15 skipped).
  - Public CI run 42965385161: Ubuntu and Windows success.
  - `validate --install-deps` passed (caution only). Doctor OK (4 tools, 0 hooks).
  - Clean-home guided E2E from the public clone passed 11/11, installed digest = approved (`docs/evidence/p6-14/public-1334cbb/`).
- Catalog PR NousResearch/hermes-agent#153110: SHA bump commit `b228d3f8` (86b4e6d → 1334cbb) in the same PR; description updated. Not merged. Its CI had not started at the time of the bump.
- VERIFIED_RELEASE is now `1334cbb`. `86b4e6d` remains in public history as the fallback.
