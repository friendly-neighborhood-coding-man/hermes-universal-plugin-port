# P6.7 checkpoint: evidence-grounded semantic review and repair proposals (optional)

**Status:** vertical slice implemented and run once on the accepted P6 evidence.

- **0 model calls.** The deterministic evaluator was used. The LLM NLI evaluator is implemented and mock-tested, but it was **not run**, because no paid call has been approved.
- **Nothing was applied** to code, Skills or artifacts.
- **Semantic equivalence: NOT_ESTABLISHED.**
- This is self-review by the implementing agent. It is not independent approval.

## What it is

| Part | File |
|---|---|
| Obligations: testable behaviors from the pinned upstream Skills, each citing an exact `file:line` | `semantics/p6_obligations.json` |
| Review engine | `semantic_review.py` (isolated; not imported by `register()`) |
| Operator CLI | `semantic_review_cli.py` |
| Tests (mocks and fixtures; one real-evidence test that skips without the operator stage) | `tests/test_semantic_review.py` (13 tests) |
| Run output on run-001 | `docs/evidence/p6-7-semantic-review/` |

**Grounding rules**

1. **Citations are re-verified.** Every citation is checked against the pinned upstream bytes: the file's SHA-256 must match, and the quoted line must match exactly.
2. **Evidence is hash-pinned.** Run-001 artifacts, the trace, the receipt, the fixture and `verify-001.json` are pinned with LF-normalized SHA-256. If any of them changes, the review stops.
3. **Model verdicts are advisory.** The LLM NLI evaluator refuses to run without `approved=True` and a positive call budget. If it cites any evidence quote that is not an exact substring of the evidence it was shown, the verdict is discarded as `INSUFFICIENT_EVIDENCE`.
4. **Candidates are gated.** Repair candidates must pass all of these checks, which do not depend on the evaluator:
   - unique exact-edit anchors, through the existing `adaptive_chunks.validate_edits`;
   - at most 3 edits;
   - no new network, shell, credential, approval, terminal or `skill_manage` tokens;
   - for Python targets, only string literals may change (compared at the AST level);
   - a temp-copy run of the affected offline tests.
5. **Nothing is applied.** Candidates are written as new files.

## Results on P6 E2E run-001

| Obligation (upstream citation) | Verdict | Root cause | Disposition |
|---|---|---|---|
| Findings cite quotes with source attribution (`synthesize-research:71`) | ENTAILED | n/a | no action |
| Opportunity Areas section (`synthesize-research:85`) | CONTRADICTED | MODEL_OUTPUT_QUALITY | **HOLD: not a porting defect.** The Skill body reached the model verbatim (`verify-001` R3). |
| Ask the user what research they have (`synthesize-research:31`) | CONTRADICTED | EXECUTION_HARNESS | **Repair candidate** RC-HARNESS-ASSUMPTIONS |
| Ask the user what to spec (`write-spec:23`) | CONTRADICTED | EXECUTION_HARNESS | **Repair candidate** RC-HARNESS-ASSUMPTIONS |
| `$ARGUMENTS` substitution (`write-spec:16`) | CONTRADICTED | HOST_SEMANTICS | **Deterministic repair exists** (R-C001). The literal sits in a Usage example, and the user's text is delivered after the body. It is not a task failure. |
| `~~project tracker` connected (`write-spec:41`) | NOT_APPLICABLE | UNSUPPORTED_CAPABILITY | **HOLD.** Connector compatibility is not invented. |
| Proceed without tools (`write-spec:55`) | ENTAILED | n/a | no action |
| Now = committed, high confidence (`roadmap-update:101`) | CONTRADICTED | MODEL_OUTPUT_QUALITY | **Editorial candidate** RC-ROADMAP-NOW |

## Repair candidates (proposals only)

**RC-HARNESS-ASSUMPTIONS.** This targets the genuinely actionable porting deviation.

- **What it changes:** one string literal in `uvp_p6_recipe.py`. Non-interactive runs are told to list the questions they would have asked, and the assumptions they used, under an *Assumptions* heading. A skipped clarification then becomes explicit instead of silent. It does **not** restore interactivity.
- **Checks:**
  - string-literal-only: PASS;
  - no new sensitive tokens: PASS;
  - permissions added: none;
  - temp-copy `test_uvp_p6_recipe.py`: PASS.
- Candidate SHA-256: `b96561e4…`.

**RC-ROADMAP-NOW.** An editorial reference copy, **not** the executed artifact.

- Items B and C have open questions the PRD itself marks blocking (OQ-2, OQ-3). The copy moves their targets from Now to Next and adds a header that labels the copy and records the original artifact's SHA-256.
- The executed `onboarding-roadmap.md` is unchanged.

Applying either candidate needs a separate operator decision. RC-HARNESS-ASSUMPTIONS would be a normal reviewed code commit, with the full regression run.

## Not done or not claimed

- No LLM NLI run, and no paid calls. Running one needs an approved scope and budget, for example ≤ 8 calls at `max_tokens=600`.
- The deterministic evaluator checks specific, declared evidence shapes. It is not general NLI.
- No runtime repair is claimed. Showing that RC-HARNESS-ASSUMPTIONS changes model behavior would need a new paid E2E run.
- **Reproduce:**

  ```powershell
  python semantic_review_cli.py --stage <stage> --run-dir docs/evidence/p6-e2e-run-001 --verify docs/evidence/p6-runtime/verify-001.json --output <new dir> --test-candidates
  ```

**Catalog impact:** with the pending D2 scan patch applied in a scratch copy, adding these P6.7 files keeps `hermes plugins validate` at PASS (security scan safe).
