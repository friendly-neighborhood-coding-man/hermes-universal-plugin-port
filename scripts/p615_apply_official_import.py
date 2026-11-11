"""TEST-ONLY digest-bound Apply of the official importer, with UVP preflight and postflight.

Official Importer preview -> UVP preflight receipt (p615_preview_official_import.py) -> explicit test
approval of that exact receipt -> official AgentImporter(execute=True) -> UVP postflight.

  python scripts/p615_apply_official_import.py --official-package DIR --package-sha256 HEX \
      --agent claude-code --source DIR --target DISPOSABLE_HOME --receipt PREFLIGHT.json \
      --approve-receipt-sha256 HEX --backup-dir NEW_DIR_OUTSIDE_HOME --output POSTFLIGHT.json \
      --i-approve-test-apply [--hermes-python PY --hermes-src DIR]

Refuses unless: the target carries the `.uvp-disposable` marker; the preflight gate is REVIEW_ONLY;
the receipt hash equals the approved hash; the official package, source tree and whole target home
are byte-identical to the preflight; a fresh preview reproduces the same ledger and memory events.
It backs up the target (excluding Hermes's runtime environment) before Apply. It never calls a model.
Rollback (`--rollback BACKUP --target HOME`) restores the backed-up paths only (scoped, not full-home).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_import_assurance import AssuranceError, assess_official_preview  # noqa: E402
from scripts.p615_preview_official_import import package_digest, target_memory_limit, target_user_limit, tree_digest  # noqa: E402

SKIP = ("installs",)
CATEGORY = {"claude-code": "claude-code-imports", "codex": "codex-imports", "cursor": "cursor-imports"}


def _receipt_hash(receipt: dict) -> str:
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _comparable(receipt: dict) -> dict:
    keep = ("gate", "reasons", "memory_events", "ledger", "counts", "memory_char_limit", "source_agent")
    return {k: receipt.get(k) for k in keep}


def _inventory(root: Path) -> dict:
    out = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        rel = Path(base).relative_to(root)
        dirs[:] = [d for d in dirs if not (rel == Path(".") and d in SKIP)]
        for n in dirs + files:
            p = Path(base) / n
            k = p.relative_to(root).as_posix()
            out[k] = ("L:" + os.readlink(p)) if p.is_symlink() else "D" if p.is_dir() else \
                "F:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _skill_digest(d: Path) -> str:
    return hashlib.sha256("".join("%s\0%s\n" % (p.relative_to(d).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
                                  for p in sorted(d.rglob("*")) if p.is_file()).encode()).hexdigest()


HERMES_CHECK = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from tools.skills_tool import skill_view
from tools.memory_tool_store import MemoryStore
import re
out = {"skill_view": {}, "linked_resources": {}}
for name in json.loads(sys.argv[2]):
    r = json.loads(skill_view(name))
    out["skill_view"][name] = {"success": bool(r.get("success")), "error": r.get("error")}
    # Every relative Markdown link in the imported SKILL.md, opened the way the model would.
    for link in sorted(set(re.findall(r"\]\(([^)\s#]+)", r.get("content") or ""))):
        if "://" in link or link.startswith("mailto:"):
            continue
        rr = json.loads(skill_view(name, file_path=link))
        out["linked_resources"][name + " -> " + link] = {"success": bool(rr.get("success")), "error": rr.get("error")}
try:
    st = MemoryStore(int(sys.argv[3]), 1375)
    st.load_from_disk() if hasattr(st, "load_from_disk") else None
    out["memory_store_loaded"] = True
except Exception as exc:
    out["memory_store_loaded"] = False
    out["memory_store_error"] = type(exc).__name__ + ": " + str(exc)[:200]
print(json.dumps(out))
"""


def apply(a) -> dict:
    root = a.official_package.resolve(strict=True)
    target = a.target.resolve(strict=True)
    source = a.source.resolve(strict=True)
    if not a.i_approve_test_apply:
        raise AssuranceError("test Apply needs --i-approve-test-apply")
    if not (target / ".uvp-disposable").is_file():
        raise AssuranceError("target is not marked disposable (.uvp-disposable)")
    for p in (a.backup_dir, a.output):
        if p.exists() or p.resolve(strict=False).is_relative_to(target):
            raise AssuranceError("backup and output must be new paths outside the target home")
    receipt = json.loads(a.receipt.read_text(encoding="utf-8"))
    if receipt.get("gate") != "REVIEW_ONLY":
        raise AssuranceError("preflight gate is %s, not REVIEW_ONLY" % receipt.get("gate"))
    if _receipt_hash(receipt) != receipt.get("receipt_sha256") or receipt["receipt_sha256"] != a.approve_receipt_sha256:
        raise AssuranceError("approval does not match this exact preflight receipt")
    if receipt.get("agent") != a.agent:
        raise AssuranceError("receipt was made for another agent")
    if package_digest(root) != a.package_sha256 or receipt.get("official_package_sha256") != a.package_sha256:
        raise AssuranceError("official package differs from the preflight")
    if tree_digest(source) != receipt.get("source_tree_sha256"):
        raise AssuranceError("source changed after preflight; approval invalid")
    if tree_digest(target) != receipt.get("target_tree_sha256"):
        raise AssuranceError("target home changed after preflight; approval invalid")
    limit = target_memory_limit(target)
    if limit != receipt.get("memory_char_limit"):
        raise AssuranceError("target memory limit changed after preflight")

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root.parent))
    official = importlib.import_module("agent-importers.importer")
    # A fresh preview must reproduce the approved plan exactly.
    fresh = assess_official_preview(official.AgentImporter(a.agent, source, target, execute=False, overwrite=False),
                                    memory_char_limit=limit, merge_entries=official.merge_entries,
                                    parse_existing_memory_entries=official.parse_existing_memory_entries,
                                    entry_delimiter=official.ENTRY_DELIMITER,
                                    user_char_limit=target_user_limit(target))
    if _comparable(fresh) != _comparable(receipt):
        raise AssuranceError("a fresh preview differs from the approved preflight")
    if tree_digest(target) != receipt["target_tree_sha256"]:
        raise AssuranceError("preview changed the target home")

    before = _inventory(target)
    backed = []
    a.backup_dir.mkdir(parents=True)
    for rel in ("config.yaml", "memories", "skills", "import-sync.json"):
        src = target / rel
        if src.is_dir():
            shutil.copytree(src, a.backup_dir / rel, symlinks=True)
            backed.append(rel)
        elif src.is_file():
            shutil.copy2(src, a.backup_dir / rel)
            backed.append(rel)
    (a.backup_dir / "BACKUP_MANIFEST.json").write_text(json.dumps({"target": str(target), "paths": backed,
                                                                    "inventory_before": before}, indent=2), encoding="utf-8")

    report = official.AgentImporter(a.agent, source, target, execute=True, overwrite=False).run()
    after = _inventory(target)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

    planned_skills = {Path(r["source"]).name: r for r in receipt["ledger"] if r["kind"] == "skill" and r["status"] == "imported"}
    skill_root = target / "skills" / CATEGORY[a.agent]
    skills = {}
    for name, row in planned_skills.items():
        d = skill_root / name
        skills[name] = {"present": d.is_dir(),
                        "bytes_equal_source": d.is_dir() and _skill_digest(d) == _skill_digest(Path(row["source"]))}
    mem = target / "memories" / "MEMORY.md"
    entries = official.parse_existing_memory_entries(mem)
    mem_chars = len(official.ENTRY_DELIMITER.join(entries))
    expected_prefixes = ["memories/", "skills/" + CATEGORY[a.agent], "skills", "import-sync.json"]
    unexpected = [k for k in changed if not any(k == p.rstrip("/") or k.startswith(p) for p in expected_prefixes)]
    post = {"official_report_dry_run": report.get("dry_run"), "official_counts": {
                s: sum(1 for i in report.get("items", []) if i.get("status") == s) for s in ("imported", "skipped", "conflict", "error")},
            "skills": skills, "memory_chars": mem_chars, "memory_limit": limit, "memory_within_limit": mem_chars <= limit,
            "changed_paths": changed, "unexpected_changed_paths": unexpected}
    # P6.16 outcome model: separate gates; a missing or failed Hermes check can never become a PASS.
    from migration_repair import evaluate_gates, run_hermes_verifier
    from scripts.p615_skill_compat_report import analyze
    install_ok = (post["official_counts"]["error"] == 0 and post["official_counts"]["conflict"] == 0
                  and all(s["present"] and s["bytes_equal_source"] for s in skills.values())
                  and post["memory_within_limit"] and not unexpected)
    runtime = run_hermes_verifier(target, list(planned_skills), a.hermes_python, a.hermes_src)
    after2 = _inventory(target)
    post["changed_by_hermes_check"] = sorted(k for k in set(after) | set(after2) if after.get(k) != after2.get(k))
    post["hermes"] = runtime
    static = {n: analyze(skill_root / n) for n in planned_skills if (skill_root / n / "SKILL.md").is_file()}
    post["static"] = static
    verdict = evaluate_gates(install_ok=install_ok, install_detail={"skills": skills, "unexpected": unexpected},
                             runtime=runtime, static=static, require_runtime=True)
    post.update(verdict)
    post["broken_linked_resources"] = sorted("%s -> %s" % (n, l) for n, r in (runtime.get("skills") or {}).items()
                                             for l, v in r.get("links", {}).items() if not v["success"])
    result = {"schema": "uvp.p616.official-apply/2", "approved_receipt_sha256": receipt["receipt_sha256"],
              "official_package_sha256": a.package_sha256, "agent": a.agent, "backup_dir": str(a.backup_dir),
              "postflight": post, "install_integrity_pass": install_ok, "final_gate": verdict["final_gate"],
              "postflight_pass": verdict["final_gate"] == "PASS", "model_calls": 0,
              "rollback_scope": "config.yaml, memories/, skills/, import-sync.json restored from backup; other paths are not covered"}
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def rollback(backup: Path, target: Path) -> dict:
    man = json.loads((backup / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    target = target.resolve(strict=True)
    if Path(man["target"]) != target or not (target / ".uvp-disposable").is_file():
        raise AssuranceError("backup belongs to another target, or the target is not disposable")
    for rel in ("config.yaml", "memories", "skills", "import-sync.json"):
        cur = target / rel
        if cur.is_dir():
            shutil.rmtree(cur)
        elif cur.exists():
            cur.unlink()
        if rel in man["paths"]:
            src = backup / rel
            (shutil.copytree(src, cur, symlinks=True) if src.is_dir() else shutil.copy2(src, cur))
    after = _inventory(target)
    before = man["inventory_before"]
    diff = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return {"restored": man["paths"], "differences_vs_pre_apply": diff, "byte_identical_in_scope": not diff}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rollback", type=Path)
    p.add_argument("--official-package", type=Path)
    p.add_argument("--package-sha256")
    p.add_argument("--agent", choices=tuple(CATEGORY))
    p.add_argument("--source", type=Path)
    p.add_argument("--target", type=Path, required=True)
    p.add_argument("--receipt", type=Path)
    p.add_argument("--approve-receipt-sha256")
    p.add_argument("--backup-dir", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--hermes-python")
    p.add_argument("--hermes-src")
    p.add_argument("--i-approve-test-apply", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.rollback:
            r = rollback(a.rollback, a.target)
        else:
            r = apply(a)
            r = {"postflight_pass": r["postflight_pass"], "final_gate": r["final_gate"],
                 "gates": r["postflight"]["gates"], "output": str(a.output)}
        print(json.dumps(r, indent=2))
        return 0 if r.get("postflight_pass", r.get("byte_identical_in_scope")) else 1
    except (AssuranceError, OSError, ValueError, ImportError) as exc:
        print("HOLD: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
