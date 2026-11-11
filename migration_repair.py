"""P6.16 Migration Doctor -> Repair Planner -> Repair Executor -> independent verification.

Operates on what the OFFICIAL Hermes agent-importers installed into a disposable Hermes home.
Nothing here imports, modifies or re-implements the official importer.

Outcome model (never collapsed into one boolean):
  INSTALL_INTEGRITY        the importer's own result: files present, byte-equal, no unexpected writes
  RUNTIME_VERIFICATION     a real Hermes process resolved the Skills (NOT_VERIFIED if it did not run)
  FUNCTIONAL_COMPATIBILITY every linked resource resolves and nothing required is unverified
  REPAIR_VERIFICATION      a repair's acceptance tests passed in a separate verifier process
Any FAIL or NOT_VERIFIED in a required gate makes the final gate HOLD.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PASS, FAIL, NOT_VERIFIED, NOT_APPLICABLE = "PASS", "FAIL", "NOT_VERIFIED", "NOT_APPLICABLE"
CLASSIFICATIONS = ("DETERMINISTIC_REPAIR_AVAILABLE", "REQUIRES_USER_DECISION", "DEPENDENCY_ACTION_REQUIRED",
                   "UNSUPPORTED", "INSUFFICIENT_EVIDENCE")
VERIFIER_VERSION = "uvp.p616.hermes-verifier/1"
NOTICE = ("<!-- Added by Universal Plugin Port repair RES-LOCAL-1 v1: copied from {origin} (sha256 {sha}) so Hermes "
          "skill_view can open it. Apache-2.0 section 4(b) change notice. -->\n"
          "> **UVP note:** this file only explains connectors. In this Hermes import the connectors are NOT "
          "connected; no MCP server, OAuth grant or credential was configured.\n\n")


class RepairError(RuntimeError):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def is_redirect(p: Path) -> bool:
    if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
        return True
    try:
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def dir_files(root: Path) -> dict[str, str]:
    root = Path(root)
    if is_redirect(root) or not root.is_dir():
        raise RepairError("not a real directory: %s" % root)
    out = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for n in list(dirs) + files:
            p = Path(base) / n
            if is_redirect(p):
                raise RepairError("symlink or junction inside %s: %s" % (root, p.relative_to(root).as_posix()))
        for n in files:
            p = Path(base) / n
            out[p.relative_to(root).as_posix()] = sha(p.read_bytes())
    return dict(sorted(out.items()))


def dir_digest(root: Path) -> str:
    return sha("".join("%s\0%s\n" % kv for kv in dir_files(root).items()).encode())


def body_digest(obj: dict, key: str) -> str:
    body = {k: v for k, v in obj.items() if k != key}
    return sha(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


# --- independent Hermes verifier (runs in the target home's own Hermes runtime) -------------------

HERMES_VERIFIER = r"""
import json, re, sys
sys.path.insert(0, sys.argv[1])
from tools.skills_tool import skill_view
from agent.skill_commands import resolve_skill_command_key
req = json.loads(sys.argv[2])
out = {"verifier": "%s", "skills": {}}
for name in req["skills"]:
    r = json.loads(skill_view(name))
    row = {"skill_view": bool(r.get("success")), "error": r.get("error"),
           "slash_key": resolve_skill_command_key(name), "links": {}}
    for link in sorted(set(re.findall(r"\]\(([^)\s#]+)", r.get("content") or ""))):
        if "://" in link or link.startswith("mailto:"):
            continue
        rr = json.loads(skill_view(name, file_path=link))
        row["links"][link] = {"success": bool(rr.get("success")), "error": rr.get("error"),
                              "says_not_connected": "NOT connected" in (rr.get("content") or "")}
    out["skills"][name] = row
print(json.dumps(out))
""" % VERIFIER_VERSION


def run_hermes_verifier(home: Path, skills: list[str], hermes_python: str | None, hermes_src: str | None,
                        timeout: int = 300) -> dict:
    """Never raises: returns {"status": PASS|FAIL|NOT_VERIFIED, ...} so a missing check is visible."""
    if not hermes_python or not Path(hermes_python).is_file():
        return {"status": NOT_VERIFIED, "reason": "Hermes Python interpreter unavailable"}
    if not hermes_src or not Path(hermes_src).is_dir():
        return {"status": NOT_VERIFIED, "reason": "Hermes source directory unavailable"}
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        p = subprocess.run([hermes_python, "-I", "-c", HERMES_VERIFIER, hermes_src, json.dumps({"skills": skills})],
                           capture_output=True, text=True, env=env, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": FAIL, "reason": "verifier did not run: %s" % type(exc).__name__}
    if p.returncode != 0:
        return {"status": FAIL, "reason": "verifier exited %d" % p.returncode, "stderr": p.stderr[-600:]}
    try:
        data = json.loads(p.stdout.strip().splitlines()[-1])
        rows = data["skills"]
        if data.get("verifier") != VERIFIER_VERSION or set(rows) != set(skills):
            raise ValueError("unexpected verifier output")
        for r in rows.values():
            if not isinstance(r.get("skill_view"), bool) or not isinstance(r.get("links"), dict):
                raise ValueError("uninterpretable skill result")
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        return {"status": FAIL, "reason": "malformed verifier output: %s" % exc, "stdout": p.stdout[-600:]}
    data["status"] = PASS if all(r["skill_view"] for r in rows.values()) else FAIL
    return data


def evaluate_gates(*, install_ok: bool, install_detail: dict, runtime: dict, static: dict[str, dict],
                   require_runtime: bool = True, repair: dict | None = None) -> dict:
    """Combine evidence into separate gates. `static[skill]` may carry declared dependencies/tools."""
    gates = {"INSTALL_INTEGRITY": PASS if install_ok else FAIL}
    rt = runtime.get("status", NOT_VERIFIED)
    gates["RUNTIME_VERIFICATION"] = rt
    per_skill = {}
    for name, info in static.items():
        if rt != PASS:
            per_skill[name] = {"status": NOT_VERIFIED, "why": "runtime verification is %s" % rt}
            continue
        row = runtime["skills"].get(name, {})
        broken = sorted(l for l, v in row.get("links", {}).items() if not v["success"])
        deps = info.get("python_packages_declared", []) + info.get("system_packages_declared", []) + \
            info.get("external_tools_referenced", [])
        if not row.get("skill_view"):
            per_skill[name] = {"status": FAIL, "why": "skill_view failed"}
        elif broken:
            per_skill[name] = {"status": FAIL, "why": "linked resources do not resolve in Hermes", "broken": broken}
        elif deps:
            per_skill[name] = {"status": NOT_VERIFIED, "why": "declared dependencies/tools were not installed or checked",
                               "dependencies": sorted(set(deps))}
        else:
            per_skill[name] = {"status": PASS, "why": "resolves; every linked resource opens; no declared dependency"}
    statuses = {v["status"] for v in per_skill.values()}
    gates["FUNCTIONAL_COMPATIBILITY"] = FAIL if FAIL in statuses else NOT_VERIFIED if (NOT_VERIFIED in statuses or not statuses) else PASS
    gates["REPAIR_VERIFICATION"] = (repair or {}).get("status", NOT_APPLICABLE)
    required = ["INSTALL_INTEGRITY", "FUNCTIONAL_COMPATIBILITY"] + (["RUNTIME_VERIFICATION"] if require_runtime else [])
    if repair is not None:
        required.append("REPAIR_VERIFICATION")
    final = "PASS" if all(gates[g] == PASS for g in required) else "HOLD"
    return {"gates": gates, "required": required, "final_gate": final, "functional_by_skill": per_skill,
            "install_detail": install_detail}


# --- Doctor findings -------------------------------------------------------------------------------

def doctor_findings(runtime: dict, static: dict[str, dict]) -> list[dict]:
    out = []
    for name, row in sorted((runtime.get("skills") or {}).items()):
        for link, v in sorted(row.get("links", {}).items()):
            if not v["success"]:
                out.append({"finding_id": "F-RES-%s-%s" % (name, sha(link.encode())[:8]), "kind": "BROKEN_RELATIVE_RESOURCE",
                            "skill": name, "link": link, "hermes_error": v.get("error"),
                            "reproduction": "skill_view(%r, file_path=%r)" % (name, link)})
    for name, info in sorted(static.items()):
        deps = sorted(set(info.get("python_packages_declared", []) + info.get("system_packages_declared", [])
                          + info.get("external_tools_referenced", [])))
        if deps:
            out.append({"finding_id": "F-DEP-%s" % name, "kind": "DECLARED_DEPENDENCIES_UNVERIFIED", "skill": name,
                        "dependencies": deps, "reproduction": "static scan of SKILL.md (no execution)"})
        if info.get("host_argument_tokens"):
            row = (runtime.get("skills") or {}).get(name, {})
            out.append({"finding_id": "F-ARG-%s" % name, "kind": "HOST_ARGUMENT_TOKEN", "skill": name,
                        "tokens": info["host_argument_tokens"], "slash_key_resolves": bool(row.get("slash_key")),
                        "reproduction": "resolve_skill_command_key(%r) -> %r" % (name, row.get("slash_key"))})
    return out


# --- Repair Planner ---------------------------------------------------------------------------------

RULES = {"RES-LOCAL-1": {"version": 1, "source": "P6.14 adapt_package.py RES-LOCAL-1, verified in P6.14 E2E-002"}}


@dataclass
class RepairProposal:
    finding_id: str
    reproduction: str
    root_cause: str
    classification: str
    evidence: list = field(default_factory=list)
    confidence: str = "HIGH"
    rule_id: str | None = None
    rule_version: int | None = None
    files: list = field(default_factory=list)
    preconditions: list = field(default_factory=list)
    expected_after: str = ""
    acceptance_tests: list = field(default_factory=list)
    rollback: str = ""
    unresolved: list = field(default_factory=list)
    human_approval_required: bool = True


def plan_repairs(findings: list[dict], *, home: Path, agent_category: str, origins: dict[str, dict]) -> dict:
    """`origins[skill] = {"root": pinned repo dir, "skill_rel": path of the Skill in it, "commit": sha}`."""
    proposals = []
    for f in findings:
        if f["kind"] == "BROKEN_RELATIVE_RESOURCE":
            proposals.append(asdict(_plan_res_local(f, home=home, category=agent_category, origin=origins.get(f["skill"]))))
        elif f["kind"] == "DECLARED_DEPENDENCIES_UNVERIFIED":
            proposals.append(asdict(RepairProposal(
                f["finding_id"], f["reproduction"], "Skill instructions require packages/tools Hermes does not provide",
                "DEPENDENCY_ACTION_REQUIRED", evidence=[{"dependencies": f["dependencies"]}], confidence="MEDIUM",
                expected_after="unchanged; the operator installs or declines the dependencies",
                unresolved=["UVP never installs packages or system tools"] + f["dependencies"])))
        elif f["kind"] == "HOST_ARGUMENT_TOKEN":
            proposals.append(asdict(RepairProposal(
                f["finding_id"], f["reproduction"],
                "Claude `$ARGUMENTS` token in a usage example; R-C001 applies to namespaced plugin commands only",
                "INSUFFICIENT_EVIDENCE", evidence=[{"slash_key_resolves": f["slash_key_resolves"], "tokens": f["tokens"]}],
                confidence="MEDIUM",
                expected_after="unchanged: the imported user Skill resolves as /<name>; no failure was reproduced",
                unresolved=["R-C001 precondition (namespaced plugin slash key) not met; no automatic patch"])))
        else:
            proposals.append(asdict(RepairProposal(f["finding_id"], f.get("reproduction", ""), "unknown", "UNSUPPORTED")))
    plan = {"schema": "uvp.p616.repair-plan/1", "home": str(home), "category": agent_category,
            "rules": RULES, "proposals": proposals}
    plan["plan_sha256"] = body_digest(plan, "plan_sha256")
    return plan


def _plan_res_local(f: dict, *, home: Path, category: str, origin: dict | None) -> RepairProposal:
    p = RepairProposal(f["finding_id"], f["reproduction"], "relative link leaves the Skill folder; Hermes skill_view "
                       "refuses '..' traversal", "INSUFFICIENT_EVIDENCE",
                       evidence=[{"hermes_error": f.get("hermes_error"), "link": f["link"]}])
    link = f["link"]
    skill_dir = Path(home) / "skills" / category / f["skill"]
    if "://" in link or link.startswith(("/", "\\")) or ":" in link.split("/")[0]:
        p.classification, p.unresolved = "UNSUPPORTED", ["absolute or URL link"]
        return p
    if not origin:
        p.unresolved = ["no pinned origin tree for this Skill; cannot locate the referenced file"]
        return p
    oroot = Path(origin["root"]).resolve(strict=True)
    oskill = (oroot / origin["skill_rel"]).resolve(strict=True)
    target = (oskill / link).resolve(strict=False)
    if not target.is_relative_to(oroot) or not target.is_file() or is_redirect(target) or target.stat().st_size > 262144:
        p.classification, p.unresolved = "UNSUPPORTED", ["referenced file is outside the pinned origin, missing, a link, or too large"]
        return p
    if not skill_dir.is_dir() or is_redirect(skill_dir):
        p.unresolved = ["installed Skill directory missing or redirected"]
        return p
    dest_name = target.name
    if (skill_dir / dest_name).exists():
        p.classification, p.unresolved = "REQUIRES_USER_DECISION", ["%s already exists in the Skill folder" % dest_name]
        return p
    md = (skill_dir / "SKILL.md").read_bytes()
    text = md.decode("utf-8")
    needle = "](%s)" % link
    lines = [i + 1 for i, l in enumerate(text.splitlines()) if needle in l]
    if not lines:
        p.unresolved = ["link span not found in installed SKILL.md"]
        return p
    origin_bytes = target.read_bytes()
    origin_rel = target.relative_to(oroot).as_posix()
    new_md = text.replace(needle, "](%s)" % dest_name).encode("utf-8")
    new_res = NOTICE.format(origin="%s@%s" % (origin_rel, origin.get("commit", "?")), sha=sha(origin_bytes)).encode() + origin_bytes
    p.classification, p.rule_id, p.rule_version = "DETERMINISTIC_REPAIR_AVAILABLE", "RES-LOCAL-1", 1
    p.evidence.append({"origin_file": origin_rel, "origin_sha256": sha(origin_bytes), "origin_commit": origin.get("commit")})
    p.files = [
        {"path": "SKILL.md", "action": "replace_spans", "lines": lines, "old": needle, "new": "](%s)" % dest_name,
         "before_sha256": sha(md), "after_sha256": sha(new_md)},
        {"path": dest_name, "action": "add", "before_sha256": None, "after_sha256": sha(new_res),
         "content_from": origin_rel, "notice": "NOT connected"}]
    p.preconditions = [
        {"check": "installed Skill tree digest", "skill_dir": f["skill"], "sha256": dir_digest(skill_dir)},
        {"check": "origin file digest", "path": origin_rel, "sha256": sha(origin_bytes)},
        {"check": "destination absent", "path": dest_name}]
    p.expected_after = "skill_view(%r, file_path=%r) succeeds and the file states connectors are NOT connected" % (
        f["skill"], dest_name)
    p.acceptance_tests = ["skill_view(skill) succeeds", "skill_view(skill, file_path=%r) succeeds" % dest_name,
                          "resource says 'NOT connected'", "every other imported Skill still resolves",
                          "only SKILL.md and %s changed in the Skill folder" % dest_name,
                          "source package byte-identical"]
    p.rollback = "restore the Skill folder from the pre-apply backup and compare its digest with the precondition"
    p.unresolved = ["connectors remain unavailable: no MCP/OAuth is configured or emulated"]
    p._new = {"SKILL.md": new_md, dest_name: new_res}  # not serialized (asdict ignores non-fields)
    return p


# --- Repair Executor -------------------------------------------------------------------------------

def build_candidate(plan: dict, finding_id: str, *, home: Path, origins: dict[str, dict], out_dir: Path) -> dict:
    """Recompute the proposal from the live state, require it to equal the plan, then write an isolated candidate."""
    if body_digest(plan, "plan_sha256") != plan.get("plan_sha256"):
        raise RepairError("repair plan was modified after planning")
    prop = next((x for x in plan["proposals"] if x["finding_id"] == finding_id), None)
    if not prop or prop["classification"] != "DETERMINISTIC_REPAIR_AVAILABLE" or prop["rule_id"] not in RULES:
        raise RepairError("no deterministic repair for %s" % finding_id)
    skill = prop["preconditions"][0]["skill_dir"]
    skill_dir = Path(home) / "skills" / plan["category"] / skill
    if dir_digest(skill_dir) != prop["preconditions"][0]["sha256"]:
        raise RepairError("installed Skill changed since planning")
    finding = {"finding_id": finding_id, "kind": "BROKEN_RELATIVE_RESOURCE", "skill": skill,
               "link": prop["files"][0]["old"][2:-1], "reproduction": prop["reproduction"]}
    again = _plan_res_local(finding, home=home, category=plan["category"], origin=origins.get(skill))
    if [dict(f) for f in again.files] != prop["files"]:
        raise RepairError("live state no longer produces the planned change")
    if Path(out_dir).exists():
        raise RepairError("candidate directory exists; candidates are never overwritten")
    cand = Path(out_dir) / skill
    shutil.copytree(skill_dir, cand, symlinks=True)
    for rel, data in again._new.items():
        (cand / rel).write_bytes(data)
    files = dir_files(cand)
    for f in prop["files"]:
        if files.get(f["path"]) != f["after_sha256"]:
            raise RepairError("candidate file %s does not match the plan" % f["path"])
    before = dir_files(skill_dir)
    changed = sorted(k for k in set(before) | set(files) if before.get(k) != files.get(k))
    if changed != sorted(f["path"] for f in prop["files"]):
        raise RepairError("candidate changes files outside the allowed set: %s" % changed)
    import difflib
    diff = list(difflib.unified_diff((skill_dir / "SKILL.md").read_text(encoding="utf-8").splitlines(),
                                     (cand / "SKILL.md").read_text(encoding="utf-8").splitlines(),
                                     "installed/SKILL.md", "candidate/SKILL.md", n=0, lineterm=""))
    rec = {"schema": "uvp.p616.repair-candidate/1", "plan_sha256": plan["plan_sha256"], "finding_id": finding_id,
           "rule": "%s v%s" % (prop["rule_id"], prop["rule_version"]), "skill": skill,
           "installed_digest": prop["preconditions"][0]["sha256"], "candidate_dir": str(cand),
           "candidate_digest": dir_digest(cand), "changed_files": changed, "diff": diff}
    (Path(out_dir) / "CANDIDATE.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def apply_candidate(*, home: Path, plan: dict, candidate: dict, approved_digest: str, ledger: Path,
                    backup_dir: Path, journal: Path) -> dict:
    """Test-only Apply of an approved candidate. Every precondition is re-checked immediately before."""
    home = Path(home).resolve(strict=True)
    if not (home / ".uvp-disposable").is_file():
        raise RepairError("target home is not marked disposable")
    for pth in (ledger, backup_dir, journal):
        if Path(pth).resolve(strict=False).is_relative_to(home):
            raise RepairError("ledger, backup and journal must be outside the target home")
    if body_digest(plan, "plan_sha256") != plan.get("plan_sha256") or candidate.get("plan_sha256") != plan["plan_sha256"]:
        raise RepairError("plan was modified or the candidate belongs to another plan")
    cand = Path(candidate["candidate_dir"])
    now = dir_digest(cand)
    if approved_digest != candidate["candidate_digest"] or now != approved_digest:
        raise RepairError("approval does not match the current candidate digest")
    used = json.loads(Path(ledger).read_text(encoding="utf-8")) if Path(ledger).is_file() else []
    if any(u["candidate_digest"] == approved_digest and u["plan_sha256"] == plan["plan_sha256"] for u in used):
        raise RepairError("this approval was already consumed by a completed Apply (replay refused)")
    skill_dir = home / "skills" / plan["category"] / candidate["skill"]
    if dir_digest(skill_dir) != candidate["installed_digest"]:
        raise RepairError("target Skill changed since the candidate was built")
    if Path(backup_dir).exists() or Path(journal).exists():
        raise RepairError("backup or journal path already exists")
    Path(journal).write_text(json.dumps({"state": "STARTED", "skill_dir": str(skill_dir)}) + "\n", encoding="utf-8")
    shutil.copytree(skill_dir, Path(backup_dir) / candidate["skill"], symlinks=True)
    staged = skill_dir.with_name(skill_dir.name + ".uvp-new")
    if staged.exists():
        raise RepairError("staging path exists")
    shutil.copytree(cand, staged, symlinks=True)
    if dir_digest(staged) != approved_digest:
        shutil.rmtree(staged)
        raise RepairError("staged copy differs from the approved candidate")
    old = skill_dir.with_name(skill_dir.name + ".uvp-old")
    os.replace(skill_dir, old)
    os.replace(staged, skill_dir)
    shutil.rmtree(old)
    installed = dir_digest(skill_dir)
    state = "COMMITTED" if installed == approved_digest else "MISMATCH"
    Path(journal).write_text(json.dumps({"state": state, "skill_dir": str(skill_dir), "installed_digest": installed,
                                         "backup": str(Path(backup_dir) / candidate["skill"])}) + "\n", encoding="utf-8")
    if state != "COMMITTED":
        raise RepairError("installed bytes differ from the approved candidate (journal MISMATCH; restore from backup)")
    used.append({"plan_sha256": plan["plan_sha256"], "candidate_digest": approved_digest, "finding_id": candidate["finding_id"]})
    Path(ledger).write_text(json.dumps(used, indent=2) + "\n", encoding="utf-8")
    return {"state": state, "installed_digest": installed, "backup": str(Path(backup_dir) / candidate["skill"])}


def rollback_candidate(*, home: Path, journal: Path) -> dict:
    j = json.loads(Path(journal).read_text(encoding="utf-8"))
    if j.get("state") != "COMMITTED":
        return {"classification": "INTERRUPTED_RECOVERY_NOT_VERIFIED", "journal_state": j.get("state"),
                "action": "none; manual inspection required"}
    skill_dir, backup = Path(j["skill_dir"]), Path(j["backup"])
    if not Path(home).resolve() in skill_dir.resolve().parents:
        raise RepairError("journal points outside the target home")
    shutil.rmtree(skill_dir)
    shutil.copytree(backup, skill_dir, symlinks=True)
    return {"classification": "ROLLED_BACK", "restored_digest": dir_digest(skill_dir), "backup_digest": dir_digest(backup)}
