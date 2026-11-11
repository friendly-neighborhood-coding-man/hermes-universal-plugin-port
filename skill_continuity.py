"""P6.8 / P6.12 Skill Continuity: authenticated contract handoff to delegated children.

Contract = qualified Skill + pinned source SHA-256 + installed body SHA-256 +
contract version + mandatory obligations. When a parent delegates, UVP:

  1. reloads the Skill through a host loader and requires its body to hash to the
     contract's installed SHA (fail closed otherwise, including a missing loader);
  2. strips EVERY contract-like block from the child context. Text that merely
     looks like a contract is never trusted;
  3. issues a fresh handoff from the HandoffAuthority, bound to the parent session,
     the delegate tool-call id and a single-use nonce. The block carries an
     HMAC-SHA256 tag computed with a per-process key that never enters any model
     context; the authoritative record stays in UVP memory, not in the text.

Verification (`verify_context`) accepts a block only when the nonce is known,
unexpired, issued for this parent session and call, the tag verifies, the
obligation text hashes to the issued digest and the contract still matches the
current registry. Anything else is FORGED / STALE / INCOMPLETE / DUPLICATE /
CONFLICT.

TRUST LIMITATION (Hermes hook surface): `pre_tool_call` lets UVP rewrite the
`delegate_task` arguments in the parent, which is the trusted channel. No hook
exposes the child's initial context to UVP, so the child cannot independently
re-verify the block. A model inside the child could ignore or misquote it.
Authenticity is therefore guaranteed at HANDOFF time only, and the feature
stays EXPERIMENTAL and unregistered in the release.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

if __package__:
    from .port_core import PortError
else:
    from port_core import PortError

SCHEMA = "universal-port.skill-contract/2"
CONTRACT_VERSION = 2
DEFAULT_TTL = 1800
MAX_BLOCK_CHARS = 2400
BLOCK = re.compile(r"\[UVP-CONTRACT(?P<head>[^\]\n]*)\](?P<body>.*?)(?:\[/UVP-CONTRACT\]|\Z)", re.S)
HEAD = re.compile(r"^ skill=(?P<skill>[a-z0-9_-]+:[a-z0-9_-]+) cid=(?P<cid>[0-9a-f]{24}) v=(?P<v>\d+) "
                  r"nonce=(?P<nonce>[0-9a-f]{32}) tag=(?P<tag>[0-9a-f]{64})$")
# Anything resembling a contract opener, including malformed or truncated ones.
LOOSE = re.compile(r"\[/?UVP-CONTRACT[^\]\n]*\]?")


def _sha_lf(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def contract_id(qualified: str, source_sha: str, version: int = CONTRACT_VERSION) -> str:
    return hashlib.sha256(("%s|%s|%d" % (qualified, source_sha, version)).encode()).hexdigest()[:24]


def build_contracts(stage: Path, obligations_path: Path) -> dict:
    stage = Path(stage)
    report = json.loads((stage / "PORTING_REPORT.json").read_text(encoding="utf-8"))
    ns = next(l.split(":", 1)[1].strip() for l in (stage / "plugin.yaml").read_text(encoding="utf-8").splitlines()
              if l.startswith("name:"))
    obl = json.loads(Path(obligations_path).read_text(encoding="utf-8"))["obligations"]
    out = {}
    for row in report.get("skill_reviews", []):
        skill = row["skill"]
        mand = [{"id": o["id"], "text": o["obligation"], "cite": "%s:%d" % (o["cite"]["file"], o["cite"]["line"])}
                for o in obl if o["skill"] == skill]
        if not mand:
            continue
        body = (stage / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        q = ns + ":" + skill
        src = row["original_sha256"]
        out[q] = {"schema": SCHEMA, "contract_id": contract_id(q, src), "contract_version": CONTRACT_VERSION,
                  "skill": q, "source_sha256": src, "installed_sha256": _sha_lf(body),
                  "obligations": mand, "reload": {"tool": "skill_view", "args": {"name": q}}}
    return out


def _obligation_text(c: dict) -> str:
    lines = ["Delegated work continues the imported Skill %s. Reload it with skill_view(\"%s\") before acting;"
             " these obligations are mandatory:" % (c["skill"], c["skill"])]
    lines += ["- %s: %s (%s)" % (o["id"], o["text"], o["cite"]) for o in c["obligations"]]
    return "\n".join(lines)


class HandoffAuthority:
    """Issues and verifies handoffs. The key lives only in this process."""

    def __init__(self, *, key: bytes | None = None, ttl: int = DEFAULT_TTL, clock=time.time):
        self._key = key if key is not None else os.urandom(32)
        self.ttl, self.clock = ttl, clock
        self.issued: dict = {}

    def _tag(self, rec: dict) -> str:
        msg = json.dumps({k: rec[k] for k in ("skill", "contract_id", "contract_version", "source_sha256",
                                              "installed_sha256", "obligations_sha256", "parent_session",
                                              "call_id", "nonce", "expires")}, sort_keys=True).encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def issue(self, c: dict, *, parent_session: str, call_id: str) -> str:
        body = _obligation_text(c)
        rec = {"skill": c["skill"], "contract_id": c["contract_id"], "contract_version": c["contract_version"],
               "source_sha256": c["source_sha256"], "installed_sha256": c["installed_sha256"],
               "obligations_sha256": _sha_lf(body), "parent_session": parent_session, "call_id": call_id,
               "nonce": os.urandom(16).hex(), "expires": int(self.clock()) + self.ttl}
        rec["tag"] = self._tag(rec)
        self.issued[rec["nonce"]] = rec
        block = "[UVP-CONTRACT skill=%s cid=%s v=%d nonce=%s tag=%s]\n%s\n[/UVP-CONTRACT]" % (
            rec["skill"], rec["contract_id"], rec["contract_version"], rec["nonce"], rec["tag"], body)
        if len(block) > MAX_BLOCK_CHARS:
            raise PortError("Contract block exceeds bound; refusing to truncate obligations")
        return block

    def verify_context(self, text: str, contracts: dict, *, parent_session: str, call_id: str) -> dict:
        """Classify every contract-like block. Only VALID blocks are trusted."""
        blocks, per_skill = [], {}
        for m in BLOCK.finditer(text or ""):
            h = HEAD.match(m.group("head"))
            closed = m.group(0).rstrip().endswith("[/UVP-CONTRACT]")
            body = m.group("body").strip("\n")
            if not h:
                blocks.append({"skill": None, "state": "FORGED", "why": "malformed header"})
                continue
            q = h.group("skill")
            per_skill.setdefault(q, []).append(h.group("cid"))
            rec = self.issued.get(h.group("nonce"))
            c = contracts.get(q)
            if rec is None or not hmac.compare_digest(rec["tag"], h.group("tag")) or rec["skill"] != q \
                    or rec["contract_id"] != h.group("cid") or str(rec["contract_version"]) != h.group("v"):
                state, why = "FORGED", "unknown nonce or bad tag"
            elif not closed:
                state, why = "INCOMPLETE", "block truncated"
            elif _sha_lf(body) != rec["obligations_sha256"]:
                state, why = "INCOMPLETE", "obligation text altered or missing"
            elif rec["expires"] < self.clock():
                state, why = "STALE", "handoff expired"
            elif rec["parent_session"] != parent_session or rec["call_id"] != call_id:
                state, why = "STALE", "issued for another session or call"
            elif c is None or (c["contract_id"], c["installed_sha256"], c["source_sha256"]) != \
                    (rec["contract_id"], rec["installed_sha256"], rec["source_sha256"]):
                state, why = "STALE", "contract changed since issue"
            else:
                state, why = "VALID", ""
            blocks.append({"skill": q, "state": state, "why": why})
        for q, cids in per_skill.items():
            if len(cids) > 1:
                kind = "CONFLICT" if len(set(cids)) > 1 else "DUPLICATE"
                for b in blocks:
                    if b["skill"] == q:
                        b["state"], b["why"] = kind, "%d blocks for one Skill" % len(cids)
        stray = len(LOOSE.findall(text or "")) - 2 * sum(1 for _ in BLOCK.finditer(text or ""))
        return {"blocks": blocks, "stray_markers": max(0, stray),
                "valid": sorted({b["skill"] for b in blocks if b["state"] == "VALID"})}


def strip_contract_text(text: str) -> str:
    out = BLOCK.sub("", text or "")
    return LOOSE.sub("", out)


def restore(text: str, contracts: dict, active: list, loader, authority: HandoffAuthority, *,
            parent_session: str, call_id: str) -> dict:
    """Return {'ok', 'text', 'changed', 'report', 'reloaded'} or fail closed with ok=False."""
    if loader is None:
        return {"ok": False, "reason": "NO_HOST_LOADER"}
    report = authority.verify_context(text, contracts, parent_session=parent_session, call_id=call_id)
    reloaded = []
    for q in sorted(active):
        c = contracts.get(q)
        if c is None:
            return {"ok": False, "reason": "UNKNOWN_CONTRACT: " + q}
        try:
            body = loader(q)
        except Exception as exc:  # any loader failure fails closed
            return {"ok": False, "reason": "RELOAD_FAILED: %s: %s" % (q, type(exc).__name__)}
        if not isinstance(body, str) or _sha_lf(body) != c["installed_sha256"]:
            return {"ok": False, "reason": "CONTRACT_BODY_MISMATCH: " + q}
        reloaded.append(q)
    trusted_all = set(active) <= set(report["valid"]) and all(b["state"] == "VALID" for b in report["blocks"]) \
        and report["stray_markers"] == 0
    if trusted_all and report["blocks"]:
        return {"ok": True, "text": text, "changed": False, "report": report, "reloaded": reloaded}
    base = strip_contract_text(text).rstrip("\n")
    blocks = [authority.issue(contracts[q], parent_session=parent_session, call_id=call_id) for q in sorted(active)]
    out = ((base + "\n\n") if base.strip() else "") + "\n\n".join(blocks) + "\n"
    check = authority.verify_context(out, contracts, parent_session=parent_session, call_id=call_id)
    if set(check["valid"]) != set(active) or any(b["state"] != "VALID" for b in check["blocks"]):
        return {"ok": False, "reason": "CONTRACT_NOT_RESTORED"}
    return {"ok": True, "text": out, "changed": True, "report": report, "reloaded": reloaded}


class ContinuityTracker:
    """Per-session active contracts plus Hermes hook callbacks. Callbacks never raise:
    Hermes runs pre_tool_call hooks under `except Exception: debug` (fail open), so an
    exception would silently allow the call; errors become explicit blocks here."""

    def __init__(self, contracts: dict, loader, authority: HandoffAuthority | None = None):
        self.contracts, self.loader = contracts, loader
        self.authority = authority or HandoffAuthority()
        self.active: dict[str, list] = {}
        self.audit: list = []

    def post_tool_call(self, tool_name="", args=None, result=None, session_id="", **_):
        try:
            if tool_name != "skill_view" or not isinstance(args, dict):
                return None
            q = args.get("name")
            if q in self.contracts and not args.get("file_path") and isinstance(result, str) \
                    and json.loads(result).get("success") is True:
                lst = self.active.setdefault(session_id, [])
                if q not in lst:
                    lst.append(q)
        except Exception:
            pass
        return None

    def pre_tool_call(self, tool_name="", args=None, session_id="", tool_call_id="", **_):
        try:
            return self._pre(tool_name, args, session_id, tool_call_id)
        except Exception as exc:
            return self._block(session_id, {"reason": "INTERNAL_ERROR: " + type(exc).__name__})

    def _pre(self, tool_name, args, session_id, call_id):
        if tool_name != "delegate_task":
            return None
        active = self.active.get(session_id) or []
        if not active:
            return None
        args = dict(args or {})
        changed = False
        kw = {"parent_session": session_id, "call_id": call_id or "no-call-id"}
        if isinstance(args.get("tasks"), list) and args["tasks"]:
            tasks = []
            for i, t in enumerate(args["tasks"]):
                t = dict(t) if isinstance(t, dict) else {}
                r = restore(t.get("context") or "", self.contracts, active, self.loader, self.authority,
                            parent_session=session_id, call_id="%s#%d" % (kw["call_id"], i))
                if not r["ok"]:
                    return self._block(session_id, r)
                changed |= r["changed"]
                t["context"] = r["text"]
                tasks.append(t)
            new = {"tasks": tasks}
        else:
            r = restore(args.get("context") or "", self.contracts, active, self.loader, self.authority, **kw)
            if not r["ok"]:
                return self._block(session_id, r)
            changed = r["changed"]
            new = {"context": r["text"]}
        self.audit.append({"session_id": session_id, "event": "handoff", "contracts": list(active), "modified": changed})
        return {"action": "modify", "args": new} if changed else None

    def _block(self, session_id, r):
        self.audit.append({"session_id": session_id, "event": "fail_closed", "reason": r["reason"]})
        return {"action": "block", "message": "UVP Skill continuity: delegation blocked (%s). The imported Skill "
                "contract could not be restored for the child; reload the Skill or delegate without it." % r["reason"]}


def hermes_skill_view_loader(skill_view):
    """Adapt Hermes tools.skills_tool.skill_view: return the body without Hermes's banner."""
    def load(q):
        res = json.loads(skill_view(q, preprocess=False))
        if not res.get("success"):
            raise PortError("skill_view failed")
        content = res.get("content", "")
        banner_end = content.find("]\n\n")
        return content[banner_end + 3:] if content.startswith("[Bundle context:") and banner_end >= 0 else content
    return load
