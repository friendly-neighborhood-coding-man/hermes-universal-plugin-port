"""P6.9 UVP Safebox: opt-in, default-deny permission contract for imported Skills.

A *grant* binds one imported Skill (qualified name) to its pinned source SHA-256
and its P6.8 contract id, and lists what tool use is permitted while that Skill
is active in a session:

  fs.read / fs.write   path prefixes (resolved, no symlink escape)
  network, shell, credentials, process, skill_admin   booleans, default false
  tools                explicit allow-list of tool names (default: none)

Everything not granted is denied. Every denial is written to an audit list
(and optionally a JSONL file) with the grant hash and the source/contract binding.
Activation of an imported Skill without a matching grant is itself denied
(invocation authorization).

ENFORCEMENT CLASS: POLICY_ONLY / NOT_ISOLATED.
The checks run inside the Hermes process at tool dispatch (a `pre_tool_call`
callback). That is not an OS boundary. Known bypass paths are reported by
`bypass_report()`, and enforcement is never claimed while they are open:
 - slash invocation `/plugin:skill` injects the Skill text without a
   `skill_view` tool call, so activation is not observed;
 - `hermes chat -s <skill>` preloads the Skill the same way;
 - other plugins, the terminal tool, or the user can act outside the hook;
 - the hook is only active if registered (not registered by UVP's register()
   in this release: EXPERIMENTAL).
See P6.10 (`isolation_runner.py`) for the separate OS-level isolation path.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

if __package__:
    from .port_core import PortError
else:
    from port_core import PortError

SCHEMA = "universal-port.safebox-grant/1"
ENFORCEMENT_CLASS = "POLICY_ONLY / NOT_ISOLATED"
READ_TOOLS = {"read_file": "path", "search_files": "path"}
WRITE_TOOLS = {"write_file": "path", "patch": "path"}
SHELL_TOOLS = {"terminal", "execute_code", "process_manage"}
NETWORK_TOOLS = {"web_search", "web_extract", "web_crawl", "browser_navigate", "browser_click", "browser_type"}
CREDENTIAL_TOOLS = {"manage_connections", "memory"}
SKILL_ADMIN_TOOLS = {"skill_manage"}
ALWAYS_ALLOWED = {"skill_view", "skills_list", "todo_list"}
_FLAGS = ("network", "shell", "credentials", "process", "skill_admin")


def grant_hash(grant: dict) -> str:
    return hashlib.sha256(json.dumps(grant, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_grant(grant: dict) -> dict:
    keys = {"schema", "skill", "source_sha256", "contract_id", "fs", "tools", *_FLAGS}
    if not isinstance(grant, dict) or set(grant) != keys or grant["schema"] != SCHEMA:
        raise PortError("Malformed Safebox grant")
    if not (isinstance(grant["source_sha256"], str) and len(grant["source_sha256"]) == 64):
        raise PortError("Grant must bind a source SHA-256")
    if not (isinstance(grant["contract_id"], str) and len(grant["contract_id"]) == 24):
        raise PortError("Grant must bind a P6.8 contract id")
    fs = grant["fs"]
    if not isinstance(fs, dict) or set(fs) != {"read", "write"}:
        raise PortError("Grant fs scope must list read and write roots")
    for k in ("read", "write"):
        if not isinstance(fs[k], list) or any(not isinstance(p, str) or not os.path.isabs(p) for p in fs[k]):
            raise PortError("Grant fs roots must be absolute paths")
    if any(not isinstance(grant[f], bool) for f in _FLAGS):
        raise PortError("Grant permission flags must be booleans")
    if not isinstance(grant["tools"], list) or any(not isinstance(t, str) for t in grant["tools"]):
        raise PortError("Grant tools must be a list of names")
    return grant


def default_grant(skill: str, source_sha256: str, contract_id: str) -> dict:
    """The default: nothing beyond reading the Skill itself."""
    return validate_grant({"schema": SCHEMA, "skill": skill, "source_sha256": source_sha256,
                           "contract_id": contract_id, "fs": {"read": [], "write": []}, "tools": [],
                           **{f: False for f in _FLAGS}})


def _within(path: str, roots: list, cwd: str | None) -> bool:
    """Absolute paths only: the pre_tool_call hook does not learn the task's working
    directory, so a relative path cannot be resolved the way the tool will resolve it."""
    if not isinstance(path, str) or not path or not os.path.isabs(path):
        return False
    p = Path(path)
    try:
        real = os.path.realpath(p)
    except (OSError, ValueError):
        return False
    for r in roots:
        rr = os.path.realpath(r)
        if real == rr or real.startswith(rr.rstrip("\\/") + os.sep):
            return True
    return False


class Safebox:
    def __init__(self, grants: list, contracts: dict, *, audit_path: Path | None = None):
        self.grants = {}
        for g in grants:
            validate_grant(g)
            c = contracts.get(g["skill"])
            if c is None or c["source_sha256"] != g["source_sha256"] or c["contract_id"] != g["contract_id"]:
                raise PortError("Grant is not bound to the current contract for " + g["skill"])
            self.grants[g["skill"]] = g
        self.contracts = contracts
        self.active: dict[str, list] = {}
        self.audit: list = []
        self.audit_path = Path(audit_path) if audit_path else None

    def _deny(self, session_id, skill, tool, reason, args=None):
        g = self.grants.get(skill)
        rec = {"event": "deny", "session_id": session_id, "skill": skill, "tool": tool, "reason": reason,
               "grant_sha256": grant_hash(g) if g else None,
               "source_sha256": (g or self.contracts.get(skill) or {}).get("source_sha256"),
               "contract_id": (g or self.contracts.get(skill) or {}).get("contract_id"),
               "args_keys": sorted((args or {}).keys())}
        self.audit.append(rec)
        if self.audit_path:
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
        return {"action": "block", "message": "UVP Safebox (%s): %s denied for imported Skill %s: %s" % (
            ENFORCEMENT_CLASS, tool, skill, reason)}

    def pre_tool_call(self, tool_name="", args=None, session_id="", cwd=None, **kw):
        # Hermes runs pre_tool_call hooks fail-open on exceptions; never raise.
        try:
            return self._pre(tool_name, args, session_id, cwd)
        except Exception as exc:
            return {"action": "block", "message": "UVP Safebox internal error (%s); call blocked" % type(exc).__name__}

    def _pre(self, tool_name, args, session_id, cwd):
        args = args if isinstance(args, dict) else {}
        # Invocation authorization: activating a contracted imported Skill needs a grant.
        if tool_name == "skill_view" and args.get("name") in self.contracts and not args.get("file_path"):
            q = args["name"]
            if q not in self.grants:
                return self._deny(session_id, q, tool_name, "no Safebox grant for this imported Skill")
            lst = self.active.setdefault(session_id, [])
            if q not in lst:
                lst.append(q)
            return None
        active = self.active.get(session_id) or []
        if not active:
            return None  # no imported Skill active: Safebox does not apply
        for q in active:
            verdict = self._check(self.grants[q], tool_name, args, cwd)
            if verdict:
                return self._deny(session_id, q, tool_name, verdict, args)
        return None

    @staticmethod
    def _check(g, tool, args, cwd):
        if tool in ALWAYS_ALLOWED:
            return None
        if tool in READ_TOOLS:
            return None if _within(args.get(READ_TOOLS[tool]), g["fs"]["read"] + g["fs"]["write"], cwd) else "path outside fs.read scope"
        if tool in WRITE_TOOLS:
            return None if _within(args.get(WRITE_TOOLS[tool]), g["fs"]["write"], cwd) else "path outside fs.write scope"
        if tool in SHELL_TOOLS:
            return None if g["shell"] and g["process"] else "shell/process not granted"
        if tool in NETWORK_TOOLS or tool.startswith("browser_") or tool.startswith("web_"):
            return None if g["network"] else "network not granted"
        if tool in CREDENTIAL_TOOLS or tool.startswith("mcp_"):
            return None if g["credentials"] else "credential/connector access not granted"
        if tool in SKILL_ADMIN_TOOLS:
            return None if g["skill_admin"] else "Skill administration not granted"
        if tool == "delegate_task":
            return None if "delegate_task" in g["tools"] else "delegation not granted"
        return None if tool in g["tools"] else "tool not in grant (default deny)"


def bypass_report(hook_registered: bool) -> dict:
    """Known paths that reach an imported Skill without passing the Safebox hook."""
    paths = [
        {"path": "slash invocation /<plugin>:<skill>", "observed_by_hook": False,
         "why": "agent.skill_commands injects the Skill text into the user message; no skill_view tool call"},
        {"path": "hermes chat -s <skill> preload", "observed_by_hook": False, "why": "preloaded into the session prompt"},
        {"path": "other plugins / terminal / user actions", "observed_by_hook": False,
         "why": "tool-dispatch policy is not an OS boundary"},
    ]
    return {"enforcement_class": ENFORCEMENT_CLASS, "hook_registered": hook_registered,
            "enforcement_claimed": False, "bypass_paths": paths,
            "unsafe_execution": "DISABLED (no isolated runner is wired to Hermes Skill execution)"}
