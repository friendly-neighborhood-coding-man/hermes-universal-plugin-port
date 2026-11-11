"""Read-only assurance bridge for NousResearch's agent-importers preview.

This module does not vendor the official importer or permit apply. Callers supply
its AgentImporter(execute=False) instance and its exact memory helpers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA = "uvp.official-import-preflight/1"
STATUS = frozenset({"imported", "skipped", "conflict", "error"})


class AssuranceError(RuntimeError):
    """The preview could not be safely or unambiguously assessed."""


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def configured_memory_limit(config: Mapping[str, Any]) -> int:
    """Read the live profile's memory limit; caller must supply its parsed config.

    The default of 2200 matches the affected Hermes versions; consumers must
    confirm that default when upgrading Hermes rather than assuming it forever.
    """
    memory = config.get("memory", {})
    if not isinstance(memory, Mapping):
        raise AssuranceError("memory settings must be a mapping")
    value = memory.get("memory_char_limit", 2200)
    if isinstance(value, bool):
        raise AssuranceError("memory_char_limit must be a positive integer")
    try:
        limit = int(value)
    except (ValueError, TypeError) as exc:
        raise AssuranceError("invalid memory_char_limit") from exc
    if limit < 1 or limit > 1_000_000:
        raise AssuranceError("memory_char_limit is outside the supported bounds")
    return limit


def assess_official_preview(
    importer: Any, *, memory_char_limit: int,
    merge_entries: Callable[[Sequence[str], Sequence[str], int], tuple[list[str], dict]],
    parse_existing_memory_entries: Callable[[Path], list[str]],
    entry_delimiter: str = "\n§\n", user_char_limit: int | None = None,
) -> dict[str, Any]:
    """Inspect an official importer preview without applying any migration.

    Intercepts the official merge_memory_entries callbacks so multiple incoming
    batches for the same memory file are cumulatively simulated against the
    configured limit, not the upstream hard-coded 20,000-char ceiling.

    Does not authorize or perform apply. The official implementation must be
    pinned/reviewed by the caller; importing arbitrary Python is not sandboxed.
    """
    if getattr(importer, "execute", None) is not False:
        raise AssuranceError("refusing importer unless execute is exactly False")
    if getattr(importer, "items", None) != []:
        raise AssuranceError("preview requires a fresh importer with no prior items")
    if not isinstance(memory_char_limit, int) or isinstance(memory_char_limit, bool) or not 1 <= memory_char_limit <= 1_000_000:
        raise AssuranceError("memory_char_limit must be a positive integer")
    if not entry_delimiter:
        raise AssuranceError("missing entry delimiter")
    if not callable(getattr(importer, "merge_memory_entries", None)) or not callable(getattr(importer, "record", None)):
        raise AssuranceError("official importer interface is incompatible")
    if not hasattr(importer, "__dict__"):
        raise AssuranceError("importer does not allow safe instance-scoped interception")

    had_instance_override = "merge_memory_entries" in importer.__dict__
    prior_override = importer.__dict__.get("merge_memory_entries")
    virtual: dict[str, list[str]] = {}
    initial: dict[str, tuple[Path, bytes | None]] = {}
    budget_events: list[dict[str, Any]] = []
    failures: list[str] = []

    def intercept(kind: str, source: Any, destination: Path, incoming: Sequence[str]) -> None:
        dest = Path(destination)
        key = str(dest.resolve(strict=False))
        if key not in virtual:
            if dest.is_symlink():
                raise AssuranceError("memory destination is a symlink")
            before = dest.read_bytes() if dest.is_file() else None
            initial[key] = (dest, before)
            virtual[key] = list(parse_existing_memory_entries(dest))
        current = virtual[key]
        # Hermes budgets USER.md (user profile) separately from MEMORY.md (memory_tool_store.MemoryStore).
        limit = user_char_limit if (user_char_limit and dest.name.upper() == "USER.MD") else memory_char_limit
        total_before = len(entry_delimiter.join(current))
        proposed, stats = merge_entries(current, list(incoming), limit)
        if not isinstance(proposed, list) or not isinstance(stats, Mapping):
            raise AssuranceError("official memory merge returned an invalid result")
        over = stats.get("overflowed")
        added = stats.get("added")
        if not isinstance(over, int) or not isinstance(added, int) or over < 0 or added < 0:
            raise AssuranceError("official memory merge returned invalid counts")
        total_after = len(entry_delimiter.join(proposed))
        if total_after > limit:
            failures.append("projected memory exceeds the configured limit")
        if total_before > limit:
            failures.append("existing memory already exceeds the configured limit")
        if over:
            failures.append("incoming memory entries would be silently excluded")
        virtual[key] = proposed
        budget_events.append({"kind": kind, "source": str(source), "destination": key,
                              "before_chars": total_before, "projected_chars": total_after,
                              "limit_chars": limit, "added": added, "overflowed": over,
                              "duplicates": stats.get("duplicates", 0)})
        importer.record(kind, source, dest, "imported" if added else "skipped",
                        "Would merge entries (UVP configured-budget simulation)",
                        added_entries=added, overflowed_entries=over,
                        preview_only=True)

    importer.merge_memory_entries = intercept
    try:
        report = importer.run()
    finally:
        if had_instance_override:
            importer.merge_memory_entries = prior_override
        else:
            del importer.merge_memory_entries

    if not isinstance(report, dict) or report.get("dry_run") is not True:
        raise AssuranceError("official importer did not produce a dry-run report")
    items = report.get("items")
    if not isinstance(items, list) or any(not isinstance(r, dict) or r.get("status") not in STATUS for r in items):
        raise AssuranceError("unexpected official preview item schema")
    for dest, previous in initial.values():
        now = dest.read_bytes() if dest.is_file() else None
        if previous != now:
            raise AssuranceError("official preview mutated a memory destination")

    ledger = [{"kind": str(r.get("kind", "")), "source": str(r.get("source") or ""),
               "destination": str(r.get("destination") or ""), "status": r["status"],
               "reason": str(r.get("reason") or "")}
              for r in items]
    counts = {k: sum(1 for r in ledger if r["status"] == k) for k in sorted(STATUS)}
    if counts["error"]:
        failures.append("official preview reported errors")
    if counts["conflict"]:
        failures.append("official preview reported conflicts")
    gate = "HOLD" if failures else "REVIEW_ONLY"
    receipt: dict[str, Any] = {"schema": SCHEMA, "gate": gate,
         "reasons": sorted(set(failures)), "source_agent": str(report.get("agent") or ""),
         "memory_char_limit": memory_char_limit, "memory_events": budget_events,
         "ledger": ledger, "counts": counts, "loss_coverage": "OFFICIAL_REPORTED_ITEMS_ONLY",
         "source_inventory_exhaustive": False,
         "approval_created": False, "apply_performed": False,
         "status_note": "REVIEW_ONLY is not permission to import; source completeness and runtime equivalence are unverified."}
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt


def configured_user_limit(config: Mapping[str, Any]) -> int:
    """memory.user_char_limit (Hermes default 1375): the separate budget for USER.md."""
    memory = config.get("memory", {})
    if not isinstance(memory, Mapping):
        raise AssuranceError("memory settings must be a mapping")
    value = memory.get("user_char_limit", 1375)
    if isinstance(value, bool):
        raise AssuranceError("user_char_limit must be a positive integer")
    try:
        limit = int(value)
    except (ValueError, TypeError) as exc:
        raise AssuranceError("invalid user_char_limit") from exc
    if limit < 1 or limit > 1_000_000:
        raise AssuranceError("user_char_limit is outside the supported bounds")
    return limit
