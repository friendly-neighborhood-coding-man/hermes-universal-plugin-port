"""P6.3 pilot: explicit, transactional, reversible multi-domain preferences.

Domain defaults are user preferences, never permissions and never automatic
skill execution. No foreign package may modify this module or its choices.
Only Hermes's live skills_list plus an attached local session is accepted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .uvp_arxiv_p5 import validate_host_local_context
from .uvp_discovery import parse_skills_list
from .uvp_routing import RoutingError

SCHEMA = "universal-port.p6-domain-defaults/1"
PLUGIN = "ported-product-management"
DOMAINS = (
    ("research", "synthesize-research"),
    ("documents", "write-spec"),
    ("planning", "roadmap-update"),
)
CHOICES = (
    {"value": "make_default", "label": "Make this skill the default"},
    {"value": "keep_existing", "label": "Keep the existing default"},
    {"value": "not_now", "label": "Not now"},
)
SAFE_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")


class DefaultsError(ValueError):
    pass


def _result(status: str, *, choices=None, changed=0, defaults=None):
    return {
        "schema": "universal-port.p6-defaults-result/1",
        "status": status,
        "choices": choices or {},
        "changed_domains": changed,
        "domain_defaults": defaults or {},
        "skill_execution_performed": False,
        "network_execution_performed": False,
        "permissions_added": 0,
    }


def _check_local(ctx, *, source=None, platform=None, session_id="", session_key=""):
    try:
        surface = ctx.session_surface()
    except Exception:
        return False
    if surface in {"cli", "tui"}:
        return True
    if surface != "local":
        return False
    verified, _ = validate_host_local_context(
        source=source, platform=platform,
        session_id=session_id, session_key=session_key)
    return verified


def _home():
    value = os.environ.get("HERMES_HOME", "")
    if not value:
        raise DefaultsError("HERMES_HOME must be explicitly set")
    root = Path(value)
    if root.is_symlink() or not root.is_dir():
        raise DefaultsError("Hermes home unavailable or linked")
    if (root / "uvp-data").is_symlink():
        raise DefaultsError("UVP data folder must not be a symlink")
    return root / "uvp-data" / "p6-domain-defaults.json"


def _valid_defaults(obj):
    if not isinstance(obj, dict) or len(obj) > 32:
        raise DefaultsError("Invalid stored defaults")
    if any(not isinstance(k, str) or not SAFE_ID.fullmatch(k)
           or not isinstance(v, str) or not SAFE_ID.fullmatch(v)
           for k, v in obj.items()):
        raise DefaultsError("Malformed stored default mapping")
    return dict(obj)


def _read(path: Path):
    if path.is_symlink():
        raise DefaultsError("Refusing symlink defaults file")
    if not path.exists():
        return {"schema": SCHEMA, "revision": 0, "domains": {}, "history": []}
    if not path.is_file() or path.stat().st_size > 65536:
        raise DefaultsError("Invalid defaults file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise DefaultsError("Cannot parse defaults file") from exc
    if (not isinstance(value, dict)
            or set(value) != {"schema", "revision", "domains", "history"}
            or value["schema"] != SCHEMA
            or not isinstance(value["revision"], int) or value["revision"] < 0
            or not isinstance(value["history"], list) or len(value["history"]) > 5):
        raise DefaultsError("Invalid defaults schema")
    _valid_defaults(value["domains"])
    for entry in value["history"]:
        if not isinstance(entry, dict) or set(entry) != {"before", "at", "choices"}:
            raise DefaultsError("Invalid history entry")
        _valid_defaults(entry["before"])
        if not isinstance(entry["at"], str) or not isinstance(entry["choices"], dict):
            raise DefaultsError("Invalid stored history")
    return value


def _save(path: Path, value: dict):
    # Atomic on a single filesystem, no network or arbitrary command calls.
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise DefaultsError("Refusing linked defaults path")
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(payload.encode("utf-8")) > 65536:
        raise DefaultsError("Defaults file size limit exceeded")
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=".p6-defaults-", suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        if path.is_symlink():
            raise DefaultsError("Refusing linked defaults path")
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _ask(ctx, domain: str, skill: str, previous: str | None):
    old_label = previous if previous else "(none)"
    question = (
        f"UVP imported skill: {PLUGIN}:{skill}\n"
        f"Domain: {domain}; current default: {old_label}.\n"
        "Set as the default for this domain? This does NOT authorize "
        "network, filesystem writes, model tools, or any execution.")
    try:
        return ctx.ask_choice(question, list(CHOICES))
    except Exception:
        return None


def propose_domain_defaults(ctx, *, source=None, platform=None, session_id="", session_key=""):
    if not _check_local(ctx, source=source, platform=platform,
                        session_id=session_id, session_key=session_key):
        return _result("LOCAL_SESSION_REQUIRED")
    try:
        observed = parse_skills_list(ctx.dispatch_tool("skills_list", {}))
    except Exception:
        return _result("HOST_CATALOG_UNAVAILABLE")
    expected = {f"{PLUGIN}:{skill}" for _, skill in DOMAINS}
    if not expected.issubset(set(observed["names"])):
        return _result("PORTED_SKILLS_NOT_INSTALLED")
    try:
        path = _home()
        before = _read(path)
    except DefaultsError:
        return _result("DEFAULT_STORE_UNAVAILABLE")
    proposed = dict(before["domains"])
    choices = {}
    for domain, skill in DOMAINS:
        selected = _ask(ctx, domain, skill, proposed.get(domain))
        if selected not in {"make_default", "keep_existing", "not_now"}:
            # No partial batch write on prompt refusal, missing viewer or error.
            return _result("CHOICE_UNAVAILABLE_OR_CANCELLED", choices=choices,
                           defaults=before["domains"])
        choices[domain] = selected
        if selected == "make_default":
            proposed[domain] = f"{PLUGIN}:{skill}"
    if proposed == before["domains"]:
        return _result("UNCHANGED", choices=choices, defaults=before["domains"])
    history = (before["history"] + [{
        "before": dict(before["domains"]),
        "at": datetime.now(timezone.utc).isoformat(),
        "choices": choices,
    }])[-5:]
    try:
        # An external edit between prompt and write must not be overwritten.
        if _read(path) != before:
            return _result("CONCURRENT_CHANGE_REFUSED", choices=choices,
                           defaults=before["domains"])
        _save(path, {
            "schema": SCHEMA,
            "revision": before["revision"] + 1,
            "domains": proposed, "history": history,
        })
    except (DefaultsError, OSError):
        return _result("SAVE_FAILED", choices=choices, defaults=before["domains"])
    n = sum(before["domains"].get(k) != v for k, v in proposed.items())
    return _result("UPDATED", choices=choices, changed=n, defaults=proposed)


def undo_last_defaults(ctx, *, source=None, platform=None, session_id="", session_key=""):
    if not _check_local(ctx, source=source, platform=platform,
                        session_id=session_id, session_key=session_key):
        return _result("LOCAL_SESSION_REQUIRED")
    try:
        path = _home()
        before = _read(path)
    except DefaultsError:
        return _result("DEFAULT_STORE_UNAVAILABLE")
    if not before["history"]:
        return _result("NO_HISTORY", defaults=before["domains"])
    try:
        consent = ctx.ask_choice(
            "Restore the exact domain defaults before the latest P6 change?",
            [{"value": "restore", "label": "Restore previous defaults"},
             {"value": "cancel", "label": "Cancel"}],
        )
    except Exception:
        consent = None
    if consent != "restore":
        return _result("RESTORE_NOT_APPROVED", defaults=before["domains"])
    previous = before["history"][-1]["before"]
    try:
        if _read(path) != before:
            return _result("CONCURRENT_CHANGE_REFUSED", defaults=before["domains"])
        _save(path, {
            "schema": SCHEMA,
            "revision": before["revision"] + 1,
            "domains": previous,
            "history": before["history"][:-1],
        })
    except (DefaultsError, OSError):
        return _result("SAVE_FAILED", defaults=before["domains"])
    return _result("RESTORED", defaults=previous)
