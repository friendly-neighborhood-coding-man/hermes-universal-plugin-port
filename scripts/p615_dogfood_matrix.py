"""Dogfood the actual pinned NousResearch agent-importers *preview* across agent layouts.

Three source families x three scenarios, with two synthetic Skills per source.
Never applies imports, never calls models, and does not establish semantic equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.p615_preview_official_import import package_digest

PINNED_OFFICIAL_COMMIT = "8b5b6296bbb900f90e296b4729d2c9a5d1139825"
AGENTS = ("claude-code", "codex", "cursor")
CASES = ("nominal", "memory-overflow", "skill-conflict")


def _write(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def _home_snapshot(root: Path) -> dict[str, str]:
    """Content/type/mode inventory; not a monitor for transient write/delete."""
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            p = Path(base) / name
            key = p.relative_to(root).as_posix()
            value = ("link:" + os.readlink(p) if p.is_symlink()
                     else "dir" if p.is_dir()
                     else "file:" + hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file()
                     else "other")
            result[key] = value + ":mode=" + oct(p.lstat().st_mode & 0o7777)
    return result


def _fixture(root: Path, agent: str, case: str):
    source = root / {"claude-code":".claude", "codex":".codex", "cursor":".cursor"}[agent]
    source.mkdir(parents=True)
    memory = "# Synthetic guidance\n\n" + ("Long memory entry " * 250 if case == "memory-overflow"
                                       else "Follow verified evidence only.") + "\n"
    if agent == "claude-code":
        _write(source / "CLAUDE.md", memory)
        _write(source / "commands/research.md", "# Foreign-only slash command\n")
        dirs = [source / "skills" / n for n in ("audit-evidence", "plan-changes")]
    elif agent == "codex":
        _write(source / "AGENTS.md", memory)
        _write(source / "memories/notes.md", "# Prior experiment\n\nEvidence-backed plan only.\n")
        dirs = [source / "skills" / n for n in ("audit-evidence", "plan-changes")]
    else:
        _write(source / "AGENTS.md", memory)
        _write(source / "rules/risk.mdc", "---\ndescription: migration caution\nalwaysApply: true\n---\n\nUse review gates.\n")
        dirs = [source / "skills" / "safety" / "audit-evidence",
                source / "skills" / "planning" / "plan-changes"]
    for folder in dirs:
        _write(folder / "SKILL.md", "---\nname: " + folder.name +
               "\ndescription: synthetic fixture\n---\n\n# " + folder.name +
               "\n\nNo model or tools should run automatically.\n")
    return source, [p.name for p in dirs]


def run_matrix(official_package: Path, *, expected_upstream_sha: str = PINNED_OFFICIAL_COMMIT):
    official_package = official_package.resolve(strict=True)
    version = subprocess.run(["git", "-C", str(official_package.parent), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=20)
    if version.returncode or version.stdout.strip() != expected_upstream_sha:
        raise RuntimeError("official checkout SHA does not match pinned upstream")
    digest = package_digest(official_package)
    results = []
    with tempfile.TemporaryDirectory(prefix="uvp-p615-official-dogfood-") as d:
        root = Path(d)
        for agent in AGENTS:
            for case in CASES:
                workspace = root / agent / case
                source, expected_skills = _fixture(workspace, agent, case)
                home = workspace / "hermes-home"
                home.mkdir()
                _write(home / "memories/MEMORY.md", "Original user memory.\n")
                if case == "skill-conflict":
                    category = {"claude-code":"claude-code-imports", "codex":"codex-imports",
                                "cursor":"cursor-imports"}[agent]
                    _write(home / "skills" / category / expected_skills[0] / "SKILL.md",
                           "# Existing user-owned skill\n")
                before = _home_snapshot(home)
                receipt_path = workspace / "receipt.json"
                command = [sys.executable, str(Path(__file__).with_name("p615_preview_official_import.py")),
                           "--official-package", str(official_package),
                           "--package-sha256", digest, "--agent", agent,
                           "--source", str(source), "--target", str(home),
                           "--memory-limit", "2200", "--output", str(receipt_path),
                           "--i-confirm-disposable-home"]
                task = subprocess.run(command, capture_output=True, text=True, timeout=45,
                                      env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1"})
                unchanged = before == _home_snapshot(home)
                receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else None
                desired = "REVIEW_ONLY" if case == "nominal" else "HOLD"
                skill_rows = [] if receipt is None else [x for x in receipt["ledger"] if x["kind"] == "skill"]
                accounted = {Path(x["source"]).name for x in skill_rows}
                checks = {
                    "receipt_exists": receipt is not None,
                    "expected_gate": receipt is not None and receipt["gate"] == desired,
                    "expected_exit": task.returncode == (0 if desired == "REVIEW_ONLY" else 2),
                    "target_unchanged": unchanged,
                    "two_skills_accounted": all(n in accounted for n in expected_skills),
                    "no_apply": receipt is not None and receipt.get("apply_performed") is False,
                    "overflow_detected": case != "memory-overflow" or (
                        receipt is not None and any(x["overflowed"] for x in receipt["memory_events"])),
                    "skill_conflict_detected": case != "skill-conflict" or (
                        receipt is not None and receipt["counts"]["conflict"] > 0)
                }
                results.append({"agent":agent,"scenario":case,"expected_gate":desired,
                                "actual_gate":receipt["gate"] if receipt else "NO_RECEIPT",
                                "assertions":checks,"pass":all(checks.values()),
                                "official_counts":receipt["counts"] if receipt else None,
                                "stderr_excerpt":task.stderr[:2000]})
    return {"schema":"uvp.p615.real-upstream-dogfood/1","upstream_sha":expected_upstream_sha,
            "package_sha256":digest,"cases":results,"pass":sum(x["pass"] for x in results),
            "total":len(results),
            "scope":"real official importer preview on synthetic agent fixtures, NOT live Hermes installation",
            "limits":["No actual apply or model execution","No semantic cross-host equivalence",
                      "Snapshot cannot detect transient write then deletion"]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--official-package",type=Path,required=True)
    p.add_argument("--expected-upstream-sha",default=PINNED_OFFICIAL_COMMIT)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    if a.report.exists():
        p.error("create-only report destination required")
    try:
        report=run_matrix(a.official_package,expected_upstream_sha=a.expected_upstream_sha)
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("Official importer dogfood: "+str(report["pass"])+"/"+str(report["total"])+" pass")
        return 0 if report["pass"]==report["total"] else 1
    except Exception as ex:
        print("DOGFOOD_HOLD: "+type(ex).__name__+": "+str(ex),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
