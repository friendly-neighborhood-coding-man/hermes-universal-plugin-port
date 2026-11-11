# P6.15 — Official Importer Assurance MVP

**Disposition: EXPERIMENTAL_ONLY.** This PR is separate from the verified P6.14 release; no public release or Hermes Catalog changes are authorized.

## Strategy and upstream source

Base the migration on NousResearch's MIT-licensed official agent-importers, not on a new converter:

https://github.com/NousResearch/hermes-official-plugins/tree/main/agent-importers

Keep official source and conversion logic upstream; introduce UVP's separate, optional verification layer.

Real upstream user complaints:
- Memory budget mismatch: https://github.com/NousResearch/hermes-agent/issues/123569 and https://github.com/NousResearch/hermes-agent/issues/148472
- Dry-run effects: https://github.com/NousResearch/hermes-agent/issues/149495 (separately addressed in upstream PR #149513)
- Grok Bot identity, delivery, lost routines: https://github.com/NousResearch/hermes-official-plugins/issues/264 through #266 (NOT yet fixed by this PR).

## Implemented in this PR

- **OfficialImportAssurance** (official_import_assurance.py): wraps the real official AgentImporter(execute=False) instance with an instance-scoped, temporary intercept of memory merge callbacks. Uses upstream merge_entries and parse_existing_memory_entries helpers, but projects cumulative memory entries against the effective configured limit rather than the hardcoded 20,000 limit. It restores the original method after the preview. Existing over-budget memory or any would-be discarded entry causes HOLD.
- **Loss Ledger**: retains official preview categories imported, skipped, conflict and error, with explicit limitation OFFICIAL_REPORTED_ITEMS_ONLY. An independent source inventory is not implemented, so it is NOT an exhaustive loss ledger.
- **Read-only CLI** (scripts/p615_preview_official_import.py): can load an already present, manually reviewed official agent-importers Python package pinned by a caller-provided whole-tree SHA-256. Supports Claude Code, Codex and Cursor preview only. Requires a disposable target home, an explicit true target memory limit, and a create-only receipt path outside the home.
- **No apply**: never imports a package into the target Hermes profile, changes official plugin files, creates approval, or runs paid models. It does not fix upstream itself.

No official source code was copied into UVP; the optional bridge imports a separately provided upstream package. If vendoring later, retain the MIT copyright/license and applicable notices.

## Example (disposable profile ONLY)

From the UVP repository root:

~~~sh
python -c "from pathlib import Path; from scripts.p615_preview_official_import import package_digest; print(package_digest(Path('/reviewed/hermes-official-plugins/agent-importers')))"
~~~

After reviewing and recording the actual full tree SHA-256:

~~~sh
python scripts/p615_preview_official_import.py \
  --official-package /reviewed/hermes-official-plugins/agent-importers \
  --package-sha256 FULL_TREE_SHA256 \
  --agent claude-code \
  --source /fixture/.claude \
  --target /disposable/hermes-home \
  --memory-limit 2200 \
  --output /outside-home/preflight-receipt.json \
  --i-confirm-disposable-home
~~~

The memory limit above is an **example only**: use the live effective profile setting, not an assumed default. The CLI executes Python from the reviewed upstream package; this is NOT OS sandboxing and requires pinning and trust assessment. Output includes local paths and needs redaction before publication.

Exit 0 = REVIEW_ONLY, never apply approval. Exit 2 = HOLD/refusal.

## Evidence and limitations

- Local, synthetic-interface unit tests: **15/15 PASS**. Tests cover cumulative two-batch overflow, pre-existing oversized memory, missing approval capability, bad digest, create-only receipt and refusal when execute=True.
- These are synthetic fixtures and subprocess tests, **not a real official importer Hermes E2E**.
- The code checks unchanged memory destinations but does not yet establish entire-home no-side-effect guarantees.
- A whole-tree digest checks consistency, not source trust; no source execution isolation is provided.
- Grok Bot/OpenBot importers, multi-profile identity, delivery routing, model equivalence and actual postflight are NOT implemented.
- A checked plan is NOT bound to any future apply transaction. There is no permission to execute an import.

## Gates required before any promotion

1. Run reviewed/pinned real official source in a disposable Hermes environment with actual source fixtures.
2. Independently verify read-only behavior across the entire target home; do not call Hermes core migrate --dry-run while unresolved side effects are reported.
3. Add independent source inventory coverage and clarify the remaining unknown losses.
4. Design a digest-bound approval/apply transaction and real postflight with rollback, without bypassing official preview/confirmation semantics.
5. Test Windows and Linux; run all UVP regressions and Hermes Doctor/Validate.
6. Do security, license and provenance audits; request separate operator release approval.

Preserve P6.14 verified public release and Catalog pin without changes. Keep this PR DRAFT and unmerged.
