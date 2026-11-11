# Risk register: submission candidate (P6.13)

Severity reflects impact on the **submission claims**, not on production systems. UVP is used only in disposable homes.

| # | Risk | Severity | Status / mitigation |
|---|---|---|---|
| R1 | A reader takes "ported" to mean "behaves like Claude". | High | Every surface says `SKILLS_ONLY_PARTIAL` and `SEMANTIC_EQUIVALENCE = NOT_ESTABLISHED`. The NLI run is labelled diagnostic only. |
| R2 | Overclaiming security. Safebox is policy at tool dispatch and has 3 confirmed bypasses. | High | Labelled POLICY_ONLY / NOT_ISOLATED and not registered by `register()`. The isolation runner is LIMITED_WORKLOAD_ISOLATION, for UVP-owned workloads only. |
| R3 | The before/after demo covers one pinned package and two failure classes (usage-token resolution, `..` resource links). | Medium | Stated in the README. A second foreign package (WP6) was not done. |
| R4 | After rollback in `p6_before_after.py`, files outside `backups/` still differed from the pre-install manifest. | Medium | The plugin dir and `config.yaml` are restored byte-for-byte from the backup. The remaining differing files were not attributed: the script kept no per-file diff. The guided `undo` reports `plugin_removed: true`. Do not claim "byte-identical home" after rollback. |
| R5 | Host defect: in Hermes v0.22.7, `ctx.llm` ignores a plugin's `max_tokens` on the native Anthropic provider. | Medium (cost) | Disclosed as S10. The UVP P6 adapt path (`/uvp --p6-adapt`) uses `ctx.llm` and inherits this. Its run-001 call predates the finding. |
| R6 | The official Hermes importer comparison is documentation-based; the importer was not executed. | Medium | Labelled NOT_RUN in the README. |
| R7 | Run-001 is a single model run (about 165k tokens), so it does not show variance. | Medium | Presented as functional evidence only. |
| R8 | Guided `init` takes about 6 minutes on a fresh home (Hermes builds its runtime). | Low (UX) | Documented in the Quickstart. |
| R9 | The guided CLI was exercised on Windows only. On Linux, the runtime resolution looks for `bin/python`, but this path is untested end to end. | Low | Offline gating tests run on both OSes in CI. |
| R10 | The public repo is a sanitized snapshot of the private branch. A drift between them could publish unreviewed content. | Medium | Republish only through `scripts/make_public_snapshot.py` (git archive, then audit, then tree-hash equality). Never copy from a working tree (the d8253e0 lesson). |
| R11 | The catalog entry SHA must match the verified public release. | Medium | Sync it after the final public SHA is verified. Publishing the Catalog PR requires operator approval. |
| R12 | Paid-call surfaces | Low | Paid calls are made only after operator approval: P6.13 used 5 calls, about $0.08 at list price. The guided `demo` prints a command and never runs it. |

## Not done by design (needs operator approval)

- Official Hermes Catalog PR
- Demo upload or X post
- Hackathon form submission
- Any production Hermes change
