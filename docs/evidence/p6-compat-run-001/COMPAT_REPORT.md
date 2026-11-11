# P6 compatibility mapping report

Engine `uvp-compat-engine/2026-11-11.1`, registry `2026-11-11.1` (sha256 `5128904bb27843827817c5ef071504f66b92101dfe104ea25f1e1be10bac6ce8`).
Source semantics `claude-code-command-args/2026-11-07`; target `hermes-agent@b200f5bc60e31588ba2cb60e288029c4a54ba5fa`.
Stage fingerprint `56a2cac583cba7a28962d7cc02d5a9bc2e4e6dbb59781fe57e05bbb91fe3d83b`; declared upstream commit `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3` (declared, not independently linked).

**Model calls: 0.** Writes inside the stage: False. Installation: False.

| Count | Value |
|---|---|
| ai_eligible_residuals | 0 |
| composed_already_mapped | 0 |
| composed_mappings_applied | 7 |
| direct_exact_regions | 35 |
| files_changed | 7 |
| holds | 0 |
| provisional_verifications | 8 |
| skills | 8 |
| unresolved_residuals | 7 |
| unsupported_items | 16 |

Rules applied: R-C001 v1, R-D001 v1

## Per Skill

| Skill | Original SHA-256 | Status | Changed | Structural | Runtime | Semantic | Residuals |
|---|---|---|---|---|---|---|---|
| competitive-brief | `720916695f99a70e...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |
| metrics-review | `e92f364b668074c7...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |
| product-brainstorming | `53ee71b6863b277a...` | DETERMINISTIC_COMPLETE | False | VERIFIED | NOT_VERIFIED | NOT_ESTABLISHED | 0 |
| roadmap-update | `bdb121e290b590d6...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |
| sprint-planning | `c078d3f838c783e9...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |
| stakeholder-update | `bcdb8ee95dc34d02...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |
| synthesize-research | `ae98c11102545c91...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |
| write-spec | `ca6670913878b4ac...` | DETERMINISTIC_PARTIAL | True | NOT_VERIFIED (unresolved_resource) | NOT_VERIFIED | NOT_ESTABLISHED | 1 |

## Exact deltas

- `skills/competitive-brief/SKILL.md` line 16 via R-C001 v1
  - old: `/competitive-brief $ARGUMENTS`
  - new: `/ported-product-management:competitive-brief <competitor or feature area>`
  - sha256 720916695f99a70e723be02d0123908c9c968ce56e1ffdeeb423014587017cd2 -> 36117a7dacbdba5700148d326dbf8291dee84aa6ef562364b8e01dd1d2813f5b
- `skills/metrics-review/SKILL.md` line 16 via R-C001 v1
  - old: `/metrics-review $ARGUMENTS`
  - new: `/ported-product-management:metrics-review <time period or metric focus>`
  - sha256 e92f364b668074c72b36fd0f69a6adef2ead66640b2c17dc824c043fb613d278 -> 3cccab079062c2a454a9c54d894f529f886c3fbfb9d45696191c70817227fdbd
- `skills/roadmap-update/SKILL.md` line 16 via R-C001 v1
  - old: `/roadmap-update $ARGUMENTS`
  - new: `/ported-product-management:roadmap-update <update description>`
  - sha256 bdb121e290b590d60b94bca84d1700a8803c78db9f68f2a28fd04ccfe8aceb9e -> 0c9ebb2db61688fcf36908f406092432cb24212198619649491dc34a20696681
- `skills/sprint-planning/SKILL.md` line 16 via R-C001 v1
  - old: `/sprint-planning $ARGUMENTS`
  - new: `/ported-product-management:sprint-planning [sprint name or date range]`
  - sha256 c078d3f838c783e9ab53ca1a4b4c04dcd7930a55a995731b8c020cd656cb1edd -> 20e5b8c27f2917425a5e0a4bfb463cb7438f5c7cbf7f5488f58424c7156232be
- `skills/stakeholder-update/SKILL.md` line 16 via R-C001 v1
  - old: `/stakeholder-update $ARGUMENTS`
  - new: `/ported-product-management:stakeholder-update <update type and audience>`
  - sha256 bcdb8ee95dc34d025dcc3d98e7435c4dca45930581b3b7a8707f8770dd364e79 -> fbe4bbe49aad878b0437b7e1526954d5fd88b3396dab2e82f399fa2f8e7c272c
- `skills/synthesize-research/SKILL.md` line 16 via R-C001 v1
  - old: `/synthesize-research $ARGUMENTS`
  - new: `/ported-product-management:synthesize-research <research topic or question>`
  - sha256 ae98c11102545c911a1ea5d8527be0e08a3db8e53327f2865f0db19bbb2d7e9c -> 7373192c07d228414e9fdccbb50246dba073842d15b6aa1b040413c6d6d9c2c9
- `skills/write-spec/SKILL.md` line 16 via R-C001 v1
  - old: `/write-spec $ARGUMENTS`
  - new: `/ported-product-management:write-spec <feature or problem statement>`
  - sha256 ca6670913878b4ac4582727562bfced5271492a5a800d934f68c9e7bc1cd4dcc -> 8caffa0c0041d6045a140fdcd64f5227003d2e5a1a6d611ab33bac9e281fd36e

## Unresolved residuals

- competitive-brief line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)
- metrics-review line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)
- roadmap-update line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)
- sprint-planning line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)
- stakeholder-update line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)
- synthesize-research line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)
- write-spec line 9 `unresolved_resource`: Relative resource '../../CONNECTORS.md' does not resolve in the active target tree (attempted: none; AI eligible: False)

## Unsupported

Classification: **SKILLS_ONLY_PARTIAL**. Connectors not ported: amplitude, amplitude-eu, asana, atlassian, clickup, figma, fireflies, gmail, google calendar, intercom, linear, monday, notion, pendo, similarweb, slack.

- competitive-brief: connector placeholders [chat, knowledge base]; frontmatter not preserved []
- metrics-review: connector placeholders [product analytics]; frontmatter not preserved []
- roadmap-update: connector placeholders [project tracker]; frontmatter not preserved []
- stakeholder-update: connector placeholders [chat, knowledge base, meeting transcription, project tracker]; frontmatter not preserved []
- synthesize-research: connector placeholders [knowledge base, meeting transcription, product analytics, user feedback]; frontmatter not preserved []
- write-spec: connector placeholders [design, knowledge base, project tracker]; frontmatter not preserved []

## Existing review candidates (preserved, not modified)

- write-spec `676ead16cc3574dffdcf3b7aa6913fbe97b171d168c14467310507187d3851a8`: **NOT_PROMOTABLE**. candidate is recorded as REJECTED in the ledger; slash command does not resolve in the Hermes catalog: /write-spec

## Limitations

- Runtime compatibility is NOT verified: no Hermes session loaded these Skills.
- Semantic equivalence is NOT established for any rule; R-D001 guarantees identical input text only.
- Target identity is the probed Hermes source checkout; the installed Hermes binary was not compared.
- Catalog resolution is static (generated __init__.py), not the live Hermes catalog.
- Mapped files are review candidates outside the stage; nothing was applied to the stage.
