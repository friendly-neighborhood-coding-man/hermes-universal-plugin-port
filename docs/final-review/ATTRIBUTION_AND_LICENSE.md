# Attribution, license obligations and redistribution scope

> This is a self-review by the implementing agent. It is not legal advice and not an independent human review.

## Components

| Component | License | Where it appears in this repository |
|---|---|---|
| Universal Plugin Port (UVP) code and docs | MIT (`LICENSE`) | the whole repository except as listed below |
| Anthropic `knowledge-work-plugins/product-management` @ `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3` | Apache-2.0 (upstream `product-management/LICENSE`, copied as `docs/evidence/LICENSE-anthropics-knowledge-work-plugins-Apache-2.0.txt`) | **Excerpts only**, inside evidence files (see below). No upstream file is committed as a standalone source file. |
| Fictional interview fixture `examples/p6-onboarding-interviews.md` | MIT (UVP-authored test data) | `examples/`, copied into `docs/evidence/p6-e2e-run-001/inputs/` |
| E2E artifacts `research-synthesis.md`, `onboarding-prd.md`, `onboarding-roadmap.md` | Model output produced by Hermes from the fixture and the ported Skills. Kept verbatim as evidence. | `docs/evidence/p6-e2e-run-001/` |

## Where upstream Apache-2.0 text is redistributed

1. **`docs/evidence/p6-e2e-run-001/stream.jsonl`** holds the `skill_view` tool results. Each one is the beginning, up to about 5,000 characters, of a ported Skill body, which is verbatim upstream text.
2. **`docs/evidence/p6-compat-run-001/COMPAT_REPORT.json` and `.md`** hold residual spans with ±2 lines of upstream context and the exact one-line deltas.
3. **`docs/final-review/SEMANTIC_FIDELITY_REPORT.md`** paraphrases upstream instructions and quotes short phrases.

## Obligations under Apache-2.0 §4 and how they are met

| Obligation | Status |
|---|---|
| 4(a) give recipients a copy of the License | **Met.** The license is copied at `docs/evidence/LICENSE-anthropics-knowledge-work-plugins-Apache-2.0.txt`, byte-identical to upstream `product-management/LICENSE`. |
| 4(b) modified files carry prominent change notices | **Applies only to the R-C001 mapped Skill files** (one line changed each). They live outside this repository, in `D:\Hermes-Lab\p6-compat-run-001\skills\`. Their report records the exact delta. If they are ever redistributed, add a header note: "Modified by Universal Plugin Port R-C001 v1: Usage line rewritten". |
| 4(c) retain copyright, patent, trademark and attribution notices | **Met** for the excerpts. The upstream Skill files contain no per-file notices, and the package ships no `NOTICE` file (checked in the upstream tree at the pinned commit). |
| 4(d) include the NOTICE file, if any | **Not applicable.** Upstream has no `NOTICE` file at that commit. |
| Trademarks (§6) | UVP does not use Anthropic or Claude marks to brand itself. "Claude Code" and "Anthropic" appear only to describe the source host. |

## The generated Hermes package (not in this repository)

`ported-product-management` (stage and disposable-home install) redistributes the full upstream `product-management/` tree under `original/`, including its `LICENSE`, plus verbatim copies of the Skills under `skills/`.

- **Disposable-home use is local only.**
- **Public redistribution** of the generated package is **not done** and is out of scope for the catalog submission. The catalog entry is for UVP itself, not for the ported Anthropic package.
- If the generated package is ever published, it must keep `original/LICENSE` and add an attribution line to its `plugin.yaml` description or README.

## Recommendation

No blocker for submitting UVP. Keep the third-party license copy next to the evidence. Do not publish the generated `ported-product-management` package as part of this submission.
