# P6.7 semantic review

Evaluator: `deterministic`, model calls: 0. Applied: no. Semantic equivalence: **NOT_ESTABLISHED**.

| Obligation | Source | Verdict | Root cause | Disposition |
|---|---|---|---|---|
| OB-SR-ATTRIB | `skills/synthesize-research/SKILL.md:71` | ENTAILED | - | NO_ACTION |
| OB-SR-OPPORTUNITY | `skills/synthesize-research/SKILL.md:85` | CONTRADICTED | MODEL_OUTPUT_QUALITY | HOLD_NOT_A_PORTING_DEFECT |
| OB-SR-ASK | `skills/synthesize-research/SKILL.md:31` | CONTRADICTED | EXECUTION_HARNESS | REPAIR_CANDIDATE_PROPOSED |
| OB-WS-ASK | `skills/write-spec/SKILL.md:23` | CONTRADICTED | EXECUTION_HARNESS | REPAIR_CANDIDATE_PROPOSED |
| OB-WS-ARGS | `skills/write-spec/SKILL.md:16` | CONTRADICTED | HOST_SEMANTICS | DETERMINISTIC_REPAIR_EXISTS |
| OB-WS-TRACKER | `skills/write-spec/SKILL.md:41` | NOT_APPLICABLE | UNSUPPORTED_CAPABILITY | HOLD_UNSUPPORTED |
| OB-WS-NO-TOOLS | `skills/write-spec/SKILL.md:55` | ENTAILED | - | NO_ACTION |
| OB-RU-NOW | `skills/roadmap-update/SKILL.md:101` | CONTRADICTED | MODEL_OUTPUT_QUALITY | REPAIR_CANDIDATE_PROPOSED |

## Repair candidates (not applied)

- **RC-HARNESS-ASSUMPTIONS** (EXECUTION_HARNESS, addresses OB-SR-ASK, OB-WS-ASK): target `uvp_p6_recipe.py`, candidate sha256 `e0db326f0b7802a1d9e4000412a5bbd2781a7907748737b0d666183c2f34ed87`. Checks: execution=False, network=False, no_new_sensitive_tokens=True, permissions_added=[], string_literal_only=True, unique_anchors=True. Temp-copy tests: PASS.
- **RC-ROADMAP-NOW** (MODEL_OUTPUT_QUALITY, addresses OB-RU-NOW): target `onboarding-roadmap.md (copy)`, candidate sha256 `aefaa5148cc5ab313a88d3ec3810d49bb79c32b4a15412f7bf000ff4a019168a`. Checks: execution=False, network=False, no_new_sensitive_tokens=True, original_artifact_untouched=True, permissions_added=[], unique_anchors=True.

## Limitations

- The deterministic evaluator checks specific, declared evidence shapes; it is not general NLI.
- The LLM NLI evaluator is implemented but was not run (no paid call approved).
- Candidates are proposals; none was applied to code, Skills or artifacts.
