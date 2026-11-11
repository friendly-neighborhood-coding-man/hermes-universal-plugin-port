"""UVP Migration Doctor -> Repair Plan -> Approved Repair -> Hermes Verification (CLI).

Works on Skills that the OFFICIAL Hermes agent-importers already installed into a disposable Hermes home
(a home carrying UVP's `.uvp-disposable` marker). UVP never re-implements or modifies the importer.

  python uvp_repair.py doctor   --home HOME --work WORKDIR [--agent claude-code|codex|cursor]
                                [--origin SKILL=SOURCE_REPO::PATH/TO/SKILL ...]
  python uvp_repair.py plan     --work WORKDIR
  python uvp_repair.py candidate --work WORKDIR --finding ID
  python uvp_repair.py apply    --work WORKDIR --finding ID --approve-digest CANDIDATE_DIGEST
  python uvp_repair.py verify   --work WORKDIR
  python uvp_repair.py rollback --work WORKDIR --finding ID
  python uvp_repair.py status   --work WORKDIR

- doctor: a fresh Hermes process opens every imported Skill and every link it contains, plus a static scan;
  each problem becomes a finding with an ID.
- plan: deterministic repair rules only (RES-LOCAL-1: a help file the importer left behind is copied from the
  pinned original source next to SKILL.md and the link is rewritten). Anything else is reported, not guessed.
- candidate: builds the repaired Skill in WORKDIR; the installed Skill is not touched. Prints the diff and digest.
- apply: you approve that exact candidate digest, then type `APPLY <last 12>` in an interactive terminal.
  Backup, journal and a one-time-use ledger live in WORKDIR (outside the home); replays are refused.
- verify: a fresh Hermes process re-checks every Skill; the gates are reported separately, never as one boolean.
- rollback: restores the Skill bytes from the backup recorded in the journal.
No model calls, no network, no package installs, no Skill code executed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import migration_repair as MR  # noqa: E402
from scripts.p615_skill_compat_report import analyze  # noqa: E402

CATEGORY = {"claude-code": "claude-code-imports", "codex": "codex-imports", "cursor": "cursor-imports"}
STATE = "uvp-repair.json"


class CliError(RuntimeError):
    pass


def hermes_exe() -> str:
    exe = os.environ.get("HERMES_EXE") or shutil.which("hermes")
    if not exe:
        raise CliError("Hermes CLI not found on PATH (or set HERMES_EXE)")
    return exe


def hermes_runtime(home: Path) -> tuple[str, str]:
    """(Hermes source dir, this home's runtime Python), the same way uvp_guided resolves them."""
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run([hermes_exe(), "--version"], env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600, stdin=subprocess.DEVNULL)
    src = next((l.split(":", 1)[1].strip() for l in (p.stdout + p.stderr).splitlines()
                if l.startswith("Install directory:")), None)
    py = None
    for f in sorted(Path(home, "installs").glob("*/facts.json")):
        venv = json.loads(f.read_text(encoding="utf-8")).get("packages", {}).get("venv", {}).get("environment")
        for cand in (Path(venv or "") / "Scripts" / "python.exe", Path(venv or "") / "bin" / "python"):
            if venv and cand.is_file():
                py = str(cand)
    if not src or not py:
        raise CliError("could not resolve the Hermes runtime for this home (run `hermes --version` with HERMES_HOME set once)")
    return src, py


def load(work: Path) -> dict:
    p = work / STATE
    if not p.is_file():
        raise CliError("not a UVP repair work directory; run `doctor` first")
    return json.loads(p.read_text(encoding="utf-8"))


def save(work: Path, st: dict) -> None:
    (work / STATE).write_text(json.dumps(st, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def skills_in(home: Path, category: str) -> list[str]:
    d = home / "skills" / category
    return sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()) if d.is_dir() else []


def check(home: Path, category: str) -> dict:
    names = skills_in(home, category)
    if not names:
        raise CliError("no imported Skills under %s; run the official Hermes importer first" % (home / "skills" / category))
    src, py = hermes_runtime(home)
    runtime = MR.run_hermes_verifier(home, names, py, src)
    static = {n: analyze(home / "skills" / category / n) for n in names}
    return {"skills": names, "runtime": runtime, "static": static}


def parse_origin(spec: str) -> tuple[str, dict]:
    try:
        skill, rest = spec.split("=", 1)
        root, rel = rest.split("::", 1)
    except ValueError:
        raise CliError("--origin must look like SKILL=SOURCE_REPO::PATH/TO/SKILL")
    root_p = Path(root).resolve()
    if not (root_p / rel / "SKILL.md").is_file():
        raise CliError("origin %s has no SKILL.md at %s" % (skill, rel))
    commit = subprocess.run(["git", "-C", str(root_p), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return skill, {"root": str(root_p), "skill_rel": rel, "commit": commit or None}


def cmd_doctor(a) -> dict:
    home = Path(a.home).resolve(strict=True)
    work = Path(a.work).resolve()
    if work.exists() and (work / STATE).exists():
        raise CliError("work directory already used; choose a new one")
    if work.resolve().is_relative_to(home):
        raise CliError("the work directory must be outside the Hermes home")
    work.mkdir(parents=True, exist_ok=True)
    category = CATEGORY[a.agent]
    origins = dict(parse_origin(s) for s in (a.origin or []))
    c = check(home, category)
    findings = MR.doctor_findings(c["runtime"], c["static"])
    gates = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=c["runtime"], static=c["static"])
    (work / "DOCTOR.json").write_text(json.dumps({"check": c, "findings": findings, "gates": gates}, indent=2) + "\n",
                                      encoding="utf-8")
    st = {"schema": "uvp.repair/1", "home": str(home), "agent": a.agent, "category": category, "origins": origins,
          "work": str(work), "steps": {"doctor": {"t": time.time(), "findings": len(findings)}}}
    save(work, st)
    return {"skills": c["skills"], "runtime": c["runtime"].get("status"), "final_gate": gates["final_gate"],
            "findings": [{k: f[k] for k in ("finding_id", "kind", "skill", "link", "hermes_error", "dependencies") if k in f}
                         for f in findings],
            "next": "uvp_repair.py plan --work %s" % work if findings else "nothing to repair"}


def cmd_plan(a) -> dict:
    work = Path(a.work).resolve()
    st = load(work)
    findings = json.loads((work / "DOCTOR.json").read_text(encoding="utf-8"))["findings"]
    plan = MR.plan_repairs(findings, home=Path(st["home"]), agent_category=st["category"], origins=st["origins"])
    (work / "REPAIR_PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    st["steps"]["plan"] = {"t": time.time(), "plan_sha256": plan["plan_sha256"]}
    save(work, st)
    return {"plan_sha256": plan["plan_sha256"],
            "proposals": [{k: p[k] for k in ("finding_id", "classification", "rule_id", "root_cause", "expected_after",
                                             "unresolved") if p.get(k)} for p in plan["proposals"]],
            "next": "uvp_repair.py candidate --work %s --finding <ID with DETERMINISTIC_REPAIR_AVAILABLE>" % work}


def _plan(work: Path) -> dict:
    p = work / "REPAIR_PLAN.json"
    if not p.is_file():
        raise CliError("no repair plan; run `plan` first")
    return json.loads(p.read_text(encoding="utf-8"))


def cmd_candidate(a) -> dict:
    work = Path(a.work).resolve()
    st = load(work)
    plan = _plan(work)
    out = work / ("candidate-" + a.finding)
    if out.exists():
        raise CliError("candidate already built: %s" % out)
    cand = MR.build_candidate(plan, a.finding, home=Path(st["home"]), origins=st["origins"], out_dir=out)
    st["steps"].setdefault("candidates", {})[a.finding] = {"t": time.time(), "digest": cand["candidate_digest"]}
    save(work, st)
    return {k: cand[k] for k in ("finding_id", "rule", "skill", "candidate_digest", "installed_digest", "changed_files", "diff")} | {
        "installed_skill_untouched": True,
        "next": "review the diff, then: uvp_repair.py apply --work %s --finding %s --approve-digest %s" % (
            work, a.finding, cand["candidate_digest"])}


def _candidate(work: Path, finding: str) -> dict:
    p = work / ("candidate-" + finding) / "CANDIDATE.json"
    if not p.is_file():
        raise CliError("no candidate for %s; run `candidate` first" % finding)
    return json.loads(p.read_text(encoding="utf-8"))


def cmd_apply(a) -> dict:
    work = Path(a.work).resolve()
    st = load(work)
    plan, cand = _plan(work), _candidate(work, a.finding)
    if a.approve_digest != cand["candidate_digest"]:
        raise CliError("--approve-digest does not match this candidate; nothing changed")
    if a.test_driver:
        kind = "TEST_DRIVER (not operator consent)"
    else:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise CliError("apply needs an interactive terminal (operator confirmation); refused")
        expected = "APPLY " + a.approve_digest[-12:]
        if input("Approve this exact repair by typing %s: " % expected).strip() != expected:
            raise CliError("confirmation did not match; nothing changed")
        kind = "OPERATOR_TYPED_CONFIRMATION"
    try:
        r = MR.apply_candidate(home=Path(st["home"]), plan=plan, candidate=cand, approved_digest=a.approve_digest,
                               ledger=work / "ledger.json", backup_dir=work / ("backup-" + a.finding),
                               journal=work / ("journal-" + a.finding + ".json"))
    except MR.RepairError as exc:
        raise CliError("HOLD: %s" % exc)
    st["steps"].setdefault("applied", {})[a.finding] = {"t": time.time(), "approval_kind": kind, **r}
    save(work, st)
    return {"approval_kind": kind, **r, "next": "uvp_repair.py verify --work %s" % work}


def cmd_verify(a) -> dict:
    work = Path(a.work).resolve()
    st = load(work)
    home = Path(st["home"])
    c = check(home, st["category"])
    findings = MR.doctor_findings(c["runtime"], c["static"])
    applied = st["steps"].get("applied", {})
    repaired = {_candidate(work, fid)["skill"] for fid in applied}
    still_broken = [f for f in findings if f["kind"] == "BROKEN_RELATIVE_RESOURCE" and f["skill"] in repaired]
    repair = ({"status": MR.FAIL if still_broken or c["runtime"].get("status") != MR.PASS else MR.PASS}
              if applied else None)
    gates = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=c["runtime"], static=c["static"], repair=repair)
    (work / "VERIFY.json").write_text(json.dumps({"check": c, "findings": findings, "gates": gates}, indent=2) + "\n",
                                      encoding="utf-8")
    st["steps"]["verify"] = {"t": time.time(), "final_gate": gates["final_gate"], "remaining_findings": len(findings)}
    save(work, st)
    links = {n: {k: v.get("success") for k, v in (c["runtime"].get("skills", {}).get(n, {}).get("links") or {}).items()}
             for n in c["skills"]}
    return {"runtime": c["runtime"].get("status"), "gates": gates["gates"], "final_gate": gates["final_gate"],
            "repaired_skills": sorted(repaired), "functional_by_skill": gates["functional_by_skill"],
            "remaining_findings": [{k: f.get(k) for k in ("finding_id", "kind", "skill") if k in f} for f in findings],
            "links_resolve": links}


def cmd_rollback(a) -> dict:
    work = Path(a.work).resolve()
    st = load(work)
    j = work / ("journal-" + a.finding + ".json")
    if not j.is_file():
        raise CliError("no journal for %s" % a.finding)
    r = MR.rollback_candidate(home=Path(st["home"]), journal=j)
    st["steps"].setdefault("rolled_back", {})[a.finding] = {"t": time.time(), **r}
    save(work, st)
    return r


def cmd_status(a) -> dict:
    return load(Path(a.work).resolve())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UVP Migration Doctor and approved deterministic repair for officially imported Skills")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--home", required=True, help="disposable Hermes home the official importer wrote into")
    d.add_argument("--work", required=True, help="new work directory outside the home (reports, candidates, backups)")
    d.add_argument("--agent", default="claude-code", choices=tuple(CATEGORY))
    d.add_argument("--origin", action="append", help="SKILL=SOURCE_REPO::PATH/TO/SKILL for the pinned original source")
    for name in ("plan", "verify", "status"):
        sub.add_parser(name).add_argument("--work", required=True)
    for name in ("candidate", "rollback"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        p.add_argument("--finding", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--work", required=True)
    p.add_argument("--finding", required=True)
    p.add_argument("--approve-digest", required=True)
    p.add_argument("--test-driver", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        out = globals()["cmd_" + a.cmd](a)
    except (CliError, MR.RepairError, OSError, ValueError, KeyError) as exc:
        print("UVP REPAIR HOLD: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
