# DRAFTS: X post and hackathon submission form (NOT POSTED / NOT SUBMITTED)

Operator approval is required before anything here is published. Links in `<…>` are filled in once the public repo (D1), the catalog PR and the video exist.

## X post (≤ 280 chars)

> Universal Plugin Port for Hermes @NousResearch: it took a real Claude/Cowork plugin (Anthropic's product-management), staged it byte-for-byte, mapped 7/8 Skills with zero AI calls, flagged what can't port, and ran a 3-Skill workflow in Hermes. <repo> <video>

That is about 270 characters with two shortened links. Check it against the claims-to-avoid list in `DEMO_90S.md`.

Alternative, more conservative:

> Built for Hermes @NousResearch: Universal Plugin Port inspects foreign agent plugins, keeps the originals intact, applies only verified mappings and keeps every unsupported capability visible. Demo: a Claude plugin's 3 Skills running in Hermes. <repo> <video>

## Submission form: field drafts

| Field | Draft |
|---|---|
| Project name | Universal Plugin Port (UVP) for Hermes |
| One-liner | Port foreign agent plugins into Hermes safely: preserve the source, apply only verified mappings, and keep the gaps visible. |
| Description (short) | UVP inspects a plugin from another agent ecosystem, stages a Hermes-native package without running foreign code, and maps compatibility deterministically from a hash-pinned rule registry. It reports what cannot be ported instead of hiding it. AI is used only as an approval-gated, single-edit fallback whose output can never be applied automatically. Demonstrated on Anthropic's Apache-2.0 product-management plugin: 14/14 files match upstream, 7/8 Skills mapped with 0 model calls, namespaced registration verified in a disposable Hermes v0.22.7 home, and one three-Skill research → PRD → roadmap run. |
| What is not claimed | Semantic equivalence with Claude Code; connector or OAuth compatibility; sandboxing of Hermes Skill execution (Safebox is policy-only); billed-cost savings. |
| Repository | `<public repo URL at pinned SHA>` |
| Catalog PR | `<NousResearch/hermes-agent PR URL>` |
| Demo video | `<URL>` (≤ 90 s; script in `DEMO_90S.md`) |
| Team | friendly-neighborhood-coding-man |
| License | MIT (UVP). Upstream excerpts are Apache-2.0 (attribution in `docs/final-review/ATTRIBUTION_AND_LICENSE.md`). |
