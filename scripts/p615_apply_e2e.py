"""P6.15 Phase 3 driver: official preview -> UVP preflight -> SIMULATED test approval -> official apply ->
UVP postflight with real Hermes skill_view -> scoped rollback, in one bootstrapped disposable Hermes home.

  python scripts/p615_apply_e2e.py --official-package DIR --home DISPOSABLE_HOME --evidence NEW_DIR \
      --skill-pack DIR --skill-pack DIR [--agent claude-code]

The approval is SIMULATED_BY_TEST_DRIVER: the driver passes the receipt's own hash. No model calls.
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
from scripts.p615_preview_official_import import package_digest  # noqa: E402

LAYOUT = {"claude-code": (".claude", "CLAUDE.md"), "codex": (".codex", "AGENTS.md"), "cursor": (".cursor", "AGENTS.md")}


def run(cmd, log, **kw):
    log.append({"command": [str(c) for c in cmd]})
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, **kw)
    log[-1].update(rc=p.returncode, stdout=p.stdout[-3000:], stderr=p.stderr[-1500:])
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--official-package", type=Path, required=True)
    ap.add_argument("--home", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--skill-pack", type=Path, action="append", required=True)
    ap.add_argument("--agent", default="claude-code", choices=tuple(LAYOUT))
    a = ap.parse_args()
    if a.evidence.exists():
        raise SystemExit("evidence dir exists")
    a.evidence.mkdir(parents=True)
    log = []
    folder, mem = LAYOUT[a.agent]
    src = a.evidence / "source" / folder
    for pack in a.skill_pack:
        shutil.copytree(pack, src / "skills" / pack.name)
    (src / mem).write_text("# Synthetic project guidance\n\nCite interview IDs for every finding.\n\n"
                           "Ask before contacting any customer.\n", encoding="utf-8")
    facts = next(a.home.glob("installs/*/facts.json"))
    py = Path(json.loads(facts.read_text(encoding="utf-8"))["packages"]["venv"]["environment"]) / "Scripts" / "python.exe"
    hermes_src = r"D:\Hermes-Lab\hermes-agent"
    digest = package_digest(a.official_package)
    receipt = a.evidence / "preflight.json"
    pre = run([sys.executable, REPO / "scripts/p615_preview_official_import.py", "--official-package", a.official_package,
               "--package-sha256", digest, "--agent", a.agent, "--source", src, "--target", a.home,
               "--memory-limit", "2200", "--output", receipt, "--i-confirm-disposable-home"], log)
    result = {"approval_kind": "SIMULATED_BY_TEST_DRIVER", "model_calls": 0, "agent": a.agent, "preflight_rc": pre.returncode}
    if pre.returncode == 0:
        rh = json.loads(receipt.read_text(encoding="utf-8"))["receipt_sha256"]
        # Negative control: a wrong approval hash must be refused before anything is written.
        neg = run([sys.executable, REPO / "scripts/p615_apply_official_import.py", "--official-package", a.official_package,
                   "--package-sha256", digest, "--agent", a.agent, "--source", src, "--target", a.home,
                   "--receipt", receipt, "--approve-receipt-sha256", "0" * 64, "--backup-dir", a.evidence / "backup-neg",
                   "--output", a.evidence / "postflight-neg.json", "--i-approve-test-apply"], log)
        result["wrong_approval_refused"] = neg.returncode == 2 and not (a.evidence / "backup-neg").exists()
        apply_ = run([sys.executable, REPO / "scripts/p615_apply_official_import.py", "--official-package", a.official_package,
                      "--package-sha256", digest, "--agent", a.agent, "--source", src, "--target", a.home,
                      "--receipt", receipt, "--approve-receipt-sha256", rh, "--backup-dir", a.evidence / "backup",
                      "--output", a.evidence / "postflight.json", "--i-approve-test-apply",
                      "--hermes-python", py, "--hermes-src", hermes_src], log)
        result["apply_rc"] = apply_.returncode
        if (a.evidence / "postflight.json").is_file():
            result["postflight"] = json.loads((a.evidence / "postflight.json").read_text(encoding="utf-8"))
        # Replaying the same approval after Apply must be refused (target changed).
        replay = run([sys.executable, REPO / "scripts/p615_apply_official_import.py", "--official-package", a.official_package,
                      "--package-sha256", digest, "--agent", a.agent, "--source", src, "--target", a.home,
                      "--receipt", receipt, "--approve-receipt-sha256", rh, "--backup-dir", a.evidence / "backup-replay",
                      "--output", a.evidence / "postflight-replay.json", "--i-approve-test-apply"], log)
        result["approval_replay_refused"] = replay.returncode == 2
        rb = run([sys.executable, REPO / "scripts/p615_apply_official_import.py", "--rollback", a.evidence / "backup",
                  "--target", a.home], log)
        result["rollback_rc"] = rb.returncode
        try:
            result["rollback"] = json.loads(rb.stdout)
        except ValueError:
            result["rollback"] = rb.stdout[-500:]
    (a.evidence / "COMMANDS_AND_OUTPUT.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    (a.evidence / "APPLY_E2E.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result.get(k) for k in ("preflight_rc", "wrong_approval_refused", "apply_rc",
                                                 "approval_replay_refused", "rollback_rc")}))
    pf = result.get("postflight", {})
    print(json.dumps({"postflight_pass": pf.get("postflight_pass"), "post": pf.get("postflight")}, indent=1)[:3000])
    print(json.dumps(result.get("rollback"), indent=1)[:1500])


if __name__ == "__main__":
    main()
