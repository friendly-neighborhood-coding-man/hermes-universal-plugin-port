# Risk register: submission candidate (P6.13, updated P6.14)

Severity reflects impact on the **submission claims**, not on production systems. UVP is used only in disposable homes.

| # | Risk | Severity | Status / mitigation |
|---|---|---|---|
| R1 | A reader takes "ported" to mean "behaves like Claude". | High | Every surface says `SKILLS_ONLY_PARTIAL` and `SEMANTIC_EQUIVALENCE = NOT_ESTABLISHED`. The NLI run is labelled diagnostic only. |
| R2 | Overclaiming security. Safebox is policy at tool dispatch and has 3 confirmed bypasses. | High | Labelled POLICY_ONLY / NOT_ISOLATED and not registered by `register()`. The isolation runner is LIMITED_WORKLOAD_ISOLATION, for UVP-owned workloads only. |
| R3 | The before/after demo covers one pinned package and two failure classes (usage-token resolution, `..` resource links). | Medium | Stated in the README. A second foreign package was not done. |
| R13 | The P6.14 guided flow (adapt, approve, install of the candidate) is not yet in the public release `86b4e6d`. That release's guided `install` puts down the **verbatim** stage. | Medium | It is an ACTIVE_CANDIDATE on the private branch. Promotion needs operator approval plus the release gates; until then, do not demo P6.14 from the public release. |
| R4 | After undo, files outside the plugin dir differ from the pre-install snapshot. | Low (attributed) | P6.14 closed the attribution with an exact full-home inventory diff on a fresh home ([report](../P6_14_CLEAN_HOME_E2E.md)). The plugin's 35 files are removed and `config.yaml` is byte-identical. The rest is UVP's own backup, Hermes's config backup, Hermes update receipts in `logs/`, and Hermes's skill-usage ledger `skills/.usage.json`, which keeps stale usage rows for the removed Skills. UVP deliberately leaves the ledger because it also holds the user's skill locks. The home is **not** byte-identical after undo; never claim it is. |
| R5 | Host defect: in Hermes v0.22.7, `ctx.llm` ignores a plugin's `max_tokens` on the native Anthropic provider. | Medium (cost) | Disclosed as S10. The UVP P6 adapt path (`/uvp --p6-adapt`) uses `ctx.llm` and inherits this. Its run-001 call predates the finding. |
| R6 | The official Hermes importer comparison is documentation-based; the importer was not executed. | Medium | Labelled NOT_RUN in the README. |
| R7 | Run-001 is a single model run (about 165k tokens), so it does not show variance. | Medium | Presented as functional evidence only. |
| R8 | Guided `init` takes about 2.5 to 6 minutes on a fresh home (Hermes builds its runtime; 146 s in P6.14 E2E-001). | Low (UX) | Documented in the Quickstart. |
| R9 | The guided CLI was exercised end to end on Windows only. On Linux, the runtime resolution looks for `bin/python`, but this path is untested end to end. | Low | Offline gating tests run on both OSes in CI. |
| R10 | The public repo is a sanitized snapshot of the private branch. A drift between them could publish unreviewed content. | Medium | Republish only through `scripts/make_public_snapshot.py` (git archive, then audit, then tree-hash equality). Never copy from a working tree (the d8253e0 lesson). |
| R11 | The catalog entry SHA must match the verified public release. | Medium | Sync it after the final public SHA is verified. Publishing the Catalog PR requires operator approval. |
| R12 | Paid-call surfaces | Low | Paid calls are made only after operator approval: P6.13 used 5 calls, about $0.08 at list price. The guided `demo` prints a command and never runs it. |

## Not done by design (needs operator approval)

- Updating the Catalog PR pin (filed as NousResearch/hermes-agent#153110, pinned 86b4e6d)
- Demo upload or X post
- Hackathon form submission
- Any production Hermes change
