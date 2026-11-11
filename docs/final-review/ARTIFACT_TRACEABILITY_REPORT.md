# Artifact traceability report: P6 E2E run 001

**Scope:** the chain from the fictional interviews I01–I08 to the research synthesis, the PRD and the roadmap, for the single accepted run in `docs/evidence/p6-e2e-run-001/`.

**Method:** offline reading of the executed artifacts, the fixture and the stream-json session trace (`stream.jsonl`). No model was called. The three artifacts are quoted, never edited. Any correction proposed here is an annotation, not a change to the executed output.

**Author:** Claude, as the implementing agent. This is a self-review, not independent human approval.

## 1. What the trace actually shows

Session `local-41e6e4558efcfc3ec6d6f3d5d5e4dda0d9d4c736a8caad6f44558cbcd966923b` made seven tool calls. They are listed in emitted order, with `tool_call_id` suffixes from `stream.jsonl`:

| # | Call | Target | Result |
|---|---|---|---|
| 1 | `skill_view` (…Q4Zjz2) | `ported-product-management:synthesize-research` | success. Emitted in the same turn as #2. |
| 2 | `read_file` (…Tt93Tr) | `inputs/p6-onboarding-interviews.md` | content returned. **This is the only file read in the session.** |
| 3 | `write_file` (…KCr3td) | `research-synthesis.md` | 11,766 bytes, `verified: true` |
| 4 | `skill_view` (…neSRQP) | `ported-product-management:write-spec` | success |
| 5 | `write_file` (…sZbFzH) | `onboarding-prd.md` | 12,319 bytes, `verified: true`. Emitted in the same turn as #6. |
| 6 | `skill_view` (…PdmgwG) | `ported-product-management:roadmap-update` | success |
| 7 | `write_file` (…ng8gBs) | `onboarding-roadmap.md` | 7,796 bytes, `verified: true` |

**Observed versus carried in context:**

- The fixture was read from disk once.
- `research-synthesis.md` was **not** re-read before the PRD was written.
- `onboarding-prd.md` was **not** re-read before the roadmap was written.
- The PRD's header line "Input: research-synthesis.md" and the roadmap's "Input: onboarding-prd.md" therefore describe lineage carried in the model's session context, not observed file reads.
- No file on disk was the source for step 2 or step 3.

Byte identity:

- For each file, the `content` argument of each `write_file` call is byte-identical to the file on disk. The SHA-256 values match `RUN_RECEIPT.json`: `33f87623…`, `dd8c7e4a…`, `a7892715…`.
- The stream truncates each tool *result* at about 5,000 characters. The full `skill_view` bodies are therefore not in the trace.
- Runtime verification `verify-001` separately showed that `skill_view` returns the installed body verbatim, with a sibling-bundle banner in front.

## 2. Interview → finding

All eight `Said:` quotes in the synthesis are verbatim, whitespace-normalized substrings of the fixture. I checked them programmatically. Every interview ID is cited at least 6 times.

| Finding (synthesis) | Cited interviews | Matches fixture | Note |
|---|---|---|---|
| F1 Invitation lifecycle opaque | I02, I03, I07 | yes | |
| F2 No in-progress feedback → repeats | I04, I06 (+I07) | yes | The synthesis itself flags I07 as a different mechanism, a status gap rather than a spinner. |
| F3 Progress/status meaning unclear | I05, I08 (+I03) | yes | |
| F4 Entry/orientation confusing | I01, I03 | yes | |
| F5 Fallback on people | I01, I05 | yes | Correctly labeled a symptom of F3/F4. |
| F6 Short checklist works; example wanted | I08 | yes | Correctly labeled a stated preference. |

The synthesis separates observations (Part A) from recommendations (Part B), as the fixture requires. Counts are expressed as "n of 8 fictional notes" throughout. I found no invented user counts.

## 3. Finding → PRD requirement

| PRD req | PRD traceability table | My check against the synthesis | Status |
|---|---|---|---|
| REQ-1 progress state | F2; I04, I06 | consistent | OK |
| REQ-2 idempotent submit | F2; I04, I06 | The synthesis F2 also counts I07, and the roadmap item C cites I07. The PRD table omits it. | minor inconsistency |
| REQ-3 send confirmation | F1; I02 | consistent | OK |
| REQ-4 status list + re-invite guard | F1, F2; I07 | consistent | OK |
| REQ-5 invite landing | F1, F4; I03 | consistent | OK |
| REQ-6 persistent checklist | F3, F5; I05 | consistent | OK |
| REQ-7 status labels | F3, F6; I08 | Mapping to F6 is loose: F6 is about the checklist *helping*. The label confusion is F3. | minor |

The P2 items (workspace selector I01, example project I08) are correctly kept out of v1. That matches the synthesis confidence of Low or Low-Medium.

## 4. PRD → roadmap item

| Roadmap item | PRD ref | Evidence column | Check |
|---|---|---|---|
| A Baseline instrumentation | Sec. 8, OQ-5 | (enables goals) | Not a PRD requirement. The PRD puts it in Phase 1 of its suggested phasing. The roadmap promotes it to rank 1 and labels it "Must". This is priority drift; see §6. |
| B Progress state | REQ-1 | I04, I06 | OK |
| C Idempotent submission | REQ-2 | I04, I06, I07 | The extra I07 matches the synthesis, not the PRD table. |
| D Invitation status model | dependency of REQ-4 | I03, I07 | This is a derived enabler, not in the PRD as an item. Citing I03 is a stretch, because REQ-4 traces to I07 only. |
| E Send confirmation | REQ-3 | I02 | OK |
| F Status list + guard | REQ-4 | I07 | OK |
| G Invite landing | REQ-5 | I03 | OK |
| H Checklist + labels | REQ-6, REQ-7 | I05, I08 | OK |
| I Discovery | P2, OQ-6 | I01, I08 | OK |

Every PRD requirement appears on the roadmap. No roadmap item is unsupported by either the PRD or an explicit enabler rationale.

## 5. Contradictions and ambiguities

**C-1, the timeout versus idempotency ambiguity in the PRD (material).**

- AT-1.4: on timeout, "the control re-enables and a message states the action **did not complete** and can be retried."
- AT-2.2 explicitly covers the case where "account creation **succeeded server-side** but the client did not receive the response."
- After a client-side timeout, the client cannot know whether the action completed. The AT-1.4 message would be false in exactly the AT-2.2 case.
- Telling the user it is safe to retry is only true once REQ-2 idempotency exists.
- The roadmap then makes this worse. Risk R-1's contingency is "ship B first, which reduces retries even without C." That would ship a retry prompt *without* idempotency, which reproduces the I06 failure ("email already exists").
- Suggested annotation: AT-1.4 should say the outcome is unknown ("may not have completed"). The "safe to retry" wording should be gated on REQ-2, or B and C should ship together.

**C-2, roadmap internal tension (minor).** Item D is placed in "Next (start early)", yet the critical-path note recommends starting D "during NOW". Both statements are hedged as proposals, but the table and the narrative disagree.

**C-3, roadmap "highest-frequency theme" (minor).** The roadmap calls F1 "the highest-frequency theme, 3 of 8 notes". The synthesis gives F2 the same 3 of 8 when I07 is included. They are tied, not ranked.

## 6. Priority drift across the chain

| Stage | Top priority stated |
|---|---|
| Synthesis | F1 and F2 tied as "High frequency + high impact". Recommendation R1 (F2) is ordered first because it is the "smallest change". |
| PRD | P0 = REQ-1…REQ-5 (F2 + F1). Phasing: instrumentation + REQ-1/2, then REQ-3/4/5. |
| Roadmap | Rank 1 = instrumentation (A), then F2 items (B, C), then F1 items (D–G). |

The ordering is consistent with the PRD's own phasing. The drift is:

1. Instrumentation is elevated from a measurement section to rank-1 "Must".
2. F1, which every stage calls high-frequency and high-impact, is deferred entirely to "Next".

Both choices are defensible and explicitly labeled recommendations. They are still choices the model made, not things traceable to the interviews.

## 7. Unsupported or extrapolated claims

- PRD problem statement: "teams don't get invited (I02 skipped it)". This generalizes from one note.
- PRD AT-5.3 (expired or already-used invite links) and AT-1.1 ("within the same UI frame") are design additions, not evidence. They are acceptable as edge cases under write-spec guidance, but they are not traceable to I01–I08.
- Roadmap item D's "Enabler / Medium" effort and all "Value / Effort" judgments are model judgments. They are labeled as such.
- Every numeric target is labeled a proposed hypothesis or "baseline first". The only `%` in the outputs is a metric definition with "no target until measured".

## 8. Verdict

| Check | Result |
|---|---|
| Every finding cites source interviews | PASS |
| Quotes verbatim from the fixture | PASS (8/8) |
| Observations separated from recommendations | PASS |
| No invented counts or baselines | PASS |
| Every PRD requirement on the roadmap | PASS |
| Intermediate artifacts re-read from disk | **NOT OBSERVED.** Carried through session context. |
| Internal consistency | **FIX_REQUIRED as an annotation only** (C-1). The executed artifact stays as produced. |

Traceability is good at the evidence level. It is weaker at the lineage level: the session trace cannot show that the PRD was built from the *file* `research-synthesis.md` rather than from the model's memory of it. A rerun that requires a `read_file` of each prior artifact would close that gap. That rerun would make model calls, so it needs separate approval.
