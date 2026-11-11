"""P6.16 dogfood: OFFICIAL import -> UVP Doctor -> deterministic Repair Plan -> isolated candidate ->
SIMULATED test approval -> Apply -> independent Hermes verification (fresh process) -> rollbacks.

  python scripts/p616_repair_dogfood.py --official-package DIR --home DISPOSABLE_HOME --evidence NEW_DIR \
      --anthropic-root CLONE --openai-root CLONE [--agent claude-code|codex|cursor]

Approvals are SIMULATED_BY_TEST_DRIVER and authorize this disposable test Apply only. No model calls.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import migration_repair as MR  # noqa: E402
from scripts.p615_preview_official_import import package_digest, tree_digest  # noqa: E402
from scripts.p615_skill_compat_report import analyze  # noqa: E402

LAYOUT = {"claude-code": (".claude", "CLAUDE.md"), "codex": (".codex", "AGENTS.md"), "cursor": (".cursor", "AGENTS.md")}
CATEGORY = {"claude-code": "claude-code-imports", "codex": "codex-imports", "cursor": "cursor-imports"}
HERMES_SRC = r"D:\Hermes-Lab\hermes-agent"


def sh(cmd, log):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    log.append({"command": [str(c) for c in cmd], "rc": p.returncode, "stdout": p.stdout[-2500:], "stderr": p.stderr[-1500:]})
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--official-package", type=Path, required=True)
    ap.add_argument("--home", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--anthropic-root", type=Path, required=True)
    ap.add_argument("--openai-root", type=Path, required=True)
    ap.add_argument("--agent", default="claude-code", choices=tuple(LAYOUT))
    a = ap.parse_args()
    if a.evidence.exists():
        raise SystemExit("evidence dir exists")
    ev = a.evidence
    ev.mkdir(parents=True)
    log, R = [], {"agent": a.agent, "approval_kind": "SIMULATED_BY_TEST_DRIVER (test-only, disposable home)", "model_calls": 0}
    packs = {"synthesize-research": a.anthropic_root / "product-management" / "skills" / "synthesize-research",
             "pdf": a.openai_root / "skills" / ".curated" / "pdf"}
    origins = {"synthesize-research": {"root": str(a.anthropic_root), "skill_rel": "product-management/skills/synthesize-research",
                                       "commit": subprocess.run(["git", "-C", str(a.anthropic_root), "rev-parse", "HEAD"],
                                                                capture_output=True, text=True).stdout.strip()}}
    folder, mem = LAYOUT[a.agent]
    src = ev / "source" / folder
    for name, pack in packs.items():
        shutil.copytree(pack, src / "skills" / ("reviewed" if a.agent == "cursor" else "") / name)
    (src / mem).write_text("# Synthetic project guidance\n\nCite interview IDs for every finding.\n", encoding="utf-8")
    source_digest = tree_digest(ev / "source")
    origin_digest = MR.dir_digest(a.anthropic_root / "product-management")
    facts = next(a.home.glob("installs/*/facts.json"))
    py = str(Path(json.loads(facts.read_text(encoding="utf-8"))["packages"]["venv"]["environment"]) / "Scripts" / "python.exe")
    R["hermes_python_present"] = Path(py).is_file()
    digest = package_digest(a.official_package)
    R["official_package_sha256"] = digest

    # 1. Official import (preflight -> test approval -> official execute=True -> postflight with gates)
    rec = ev / "preflight.json"
    pre = sh([sys.executable, REPO / "scripts/p615_preview_official_import.py", "--official-package", a.official_package,
              "--package-sha256", digest, "--agent", a.agent, "--source", src, "--target", a.home, "--memory-limit", "2200",
              "--output", rec, "--i-confirm-disposable-home"], log)
    R["import_preflight_gate"] = json.loads(rec.read_text(encoding="utf-8"))["gate"] if rec.is_file() else "NO_RECEIPT"
    if pre.returncode != 0:
        raise SystemExit("preflight HOLD: " + pre.stderr[-400:])
    rh = json.loads(rec.read_text(encoding="utf-8"))["receipt_sha256"]
    sh([sys.executable, REPO / "scripts/p615_apply_official_import.py", "--official-package", a.official_package,
        "--package-sha256", digest, "--agent", a.agent, "--source", src, "--target", a.home, "--receipt", rec,
        "--approve-receipt-sha256", rh, "--backup-dir", ev / "import-backup", "--output", ev / "import-postflight.json",
        "--i-approve-test-apply", "--hermes-python", py, "--hermes-src", HERMES_SRC], log)
    imp = json.loads((ev / "import-postflight.json").read_text(encoding="utf-8"))
    R["official_import"] = {"official_counts": imp["postflight"]["official_counts"], "gates": imp["postflight"]["gates"],
                            "final_gate": imp["final_gate"], "functional_by_skill": imp["postflight"]["functional_by_skill"]}

    # 2. Doctor
    runtime, static = imp["postflight"]["hermes"], imp["postflight"]["static"]
    findings = MR.doctor_findings(runtime, static)
    (ev / "FINDINGS.json").write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
    R["findings"] = [{k: f[k] for k in ("finding_id", "kind", "skill")} for f in findings]

    # 3. Planner
    plan = MR.plan_repairs(findings, home=a.home, agent_category=CATEGORY[a.agent], origins=origins)
    (ev / "REPAIR_PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    R["plan"] = {"plan_sha256": plan["plan_sha256"],
                 "classifications": {p["finding_id"]: p["classification"] for p in plan["proposals"]}}
    det = [p for p in plan["proposals"] if p["classification"] == "DETERMINISTIC_REPAIR_AVAILABLE"]
    if not det:
        R["result"] = "NO_DETERMINISTIC_REPAIR"
    for prop in det:
        fid = prop["finding_id"]
        # 4. Executor (isolated candidate)
        installed_before = MR.dir_digest(a.home / "skills" / CATEGORY[a.agent] / prop["preconditions"][0]["skill_dir"])
        cand = MR.build_candidate(plan, fid, home=a.home, origins=origins, out_dir=ev / ("candidate-" + fid))
        R["candidate"] = {k: cand[k] for k in ("finding_id", "rule", "candidate_digest", "installed_digest", "changed_files", "diff")}
        R["installed_unchanged_by_candidate_build"] = MR.dir_digest(
            a.home / "skills" / CATEGORY[a.agent] / cand["skill"]) == installed_before
        # 5. Negative controls before the real Apply
        neg = {}
        for label, kwargs in (("wrong_digest", {"approved_digest": "0" * 64}),):
            try:
                MR.apply_candidate(home=a.home, plan=plan, candidate=cand, ledger=ev / "ledger.json",
                                   backup_dir=ev / ("neg-backup-" + label), journal=ev / ("neg-journal-%s.json" % label), **kwargs)
                neg[label] = "APPLIED (UNEXPECTED)"
            except MR.RepairError as exc:
                neg[label] = "HOLD: " + str(exc)
        tampered = json.loads(json.dumps(plan))
        tampered["proposals"][0]["rollback"] = "tampered"
        try:
            MR.apply_candidate(home=a.home, plan=tampered, candidate=cand, approved_digest=cand["candidate_digest"],
                               ledger=ev / "ledger.json", backup_dir=ev / "neg-backup-plan", journal=ev / "neg-journal-plan.json")
            neg["tampered_plan"] = "APPLIED (UNEXPECTED)"
        except MR.RepairError as exc:
            neg["tampered_plan"] = "HOLD: " + str(exc)
        R["negative_controls"] = neg
        # 6. Apply with the simulated test approval of the full candidate digest
        inv_before = {k: v for k, v in tree_inventory(a.home).items()}
        R["apply"] = MR.apply_candidate(home=a.home, plan=plan, candidate=cand, approved_digest=cand["candidate_digest"],
                                        ledger=ev / "ledger.json", backup_dir=ev / "repair-backup", journal=ev / "repair-journal.json")
        inv_after = tree_inventory(a.home)
        changed = sorted(k for k in set(inv_before) | set(inv_after) if inv_before.get(k) != inv_after.get(k))
        skill_prefix = "skills/%s/%s/" % (CATEGORY[a.agent], cand["skill"])
        allowed = {skill_prefix + f for f in cand["changed_files"]}
        # 7. Independent verification in a fresh Hermes process
        names = sorted(packs)
        v = MR.run_hermes_verifier(a.home, names, py, HERMES_SRC)
        row = (v.get("skills") or {}).get(cand["skill"], {})
        link = row.get("links", {}).get("CONNECTORS.md", {})
        checks = {"runtime_ok": v.get("status") == MR.PASS,
                  "repaired_link_resolves": bool(link.get("success")),
                  "resource_states_not_connected": bool(link.get("says_not_connected")),
                  "old_broken_link_gone": "../../CONNECTORS.md" not in row.get("links", {}),
                  "other_skills_resolve": all(v.get("skills", {}).get(n, {}).get("skill_view") for n in names),
                  "only_allowed_files_changed": set(changed) <= allowed | {skill_prefix.rstrip("/")},
                  "source_byte_identical": tree_digest(ev / "source") == source_digest,
                  "origin_byte_identical": MR.dir_digest(a.anthropic_root / "product-management") == origin_digest}
        repair_status = MR.PASS if all(checks.values()) else MR.FAIL
        static_after = {n: analyze(a.home / "skills" / CATEGORY[a.agent] / n) for n in names}
        gates = MR.evaluate_gates(install_ok=imp["install_integrity_pass"], install_detail={}, runtime=v,
                                  static=static_after, repair={"status": repair_status})
        R["verification"] = {"checks": checks, "changed_paths": changed, "hermes": v, "gates": gates["gates"],
                             "final_gate": gates["final_gate"], "functional_by_skill": gates["functional_by_skill"]}
        # 8. Replay of the same approval is refused
        try:
            MR.apply_candidate(home=a.home, plan=plan, candidate=cand, approved_digest=cand["candidate_digest"],
                               ledger=ev / "ledger.json", backup_dir=ev / "replay-backup", journal=ev / "replay-journal.json")
            R["approval_replay"] = "APPLIED (UNEXPECTED)"
        except MR.RepairError as exc:
            R["approval_replay"] = "HOLD: " + str(exc)
        # 9. Rollback of the repair, then of the official import
        R["repair_rollback"] = MR.rollback_candidate(home=a.home, journal=ev / "repair-journal.json")
        R["repair_rollback"]["skill_digest_equals_pre_repair"] = R["repair_rollback"]["restored_digest"] == installed_before
    rb = sh([sys.executable, REPO / "scripts/p615_apply_official_import.py", "--rollback", ev / "import-backup",
             "--target", a.home], log)
    try:
        R["import_rollback"] = json.loads(rb.stdout)
    except ValueError:
        R["import_rollback"] = {"raw": rb.stdout[-400:], "rc": rb.returncode}
    (ev / "COMMANDS.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    (ev / "REPAIR_DOGFOOD.json").write_text(json.dumps(R, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"agent": a.agent, "import_final_gate": R["official_import"]["final_gate"],
                      "import_gates": R["official_import"]["gates"], "plan": R["plan"]["classifications"],
                      "negative": R.get("negative_controls"), "checks": R.get("verification", {}).get("checks"),
                      "repair_gates": R.get("verification", {}).get("gates"), "replay": R.get("approval_replay"),
                      "repair_rollback": R.get("repair_rollback"), "import_rollback": R.get("import_rollback")}, indent=1))


def tree_inventory(root: Path) -> dict:
    out = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        rel = Path(base).relative_to(root)
        dirs[:] = [d for d in dirs if not (rel == Path(".") and d == "installs")]
        for n in files:
            p = Path(base) / n
            out[p.relative_to(root).as_posix()] = MR.sha(p.read_bytes())
    return out


if __name__ == "__main__":
    main()
