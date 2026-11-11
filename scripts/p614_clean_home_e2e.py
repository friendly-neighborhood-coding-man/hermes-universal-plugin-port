"""P6.14 WP2: run the complete guided journey in a NEW workspace, one step at a time, exactly as a user would.

  python scripts/p614_clean_home_e2e.py <new-workspace> <evidence-dir>

Every step is a separate `python uvp_guided.py <step>` process. The `approve` step is
SIMULATED by this driver: it reads the digest shown in CANDIDATE_REVIEW.json and passes it
back, which is what an operator would type after reading the review. No model calls; `demo`
only PREPARES a prompt and prints a command.
"""
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(ws: Path, ev: Path):
    if ws.exists() or ev.exists():
        raise SystemExit("Refusing: workspace or evidence dir exists")
    ev.mkdir(parents=True)
    hermes = shutil.which("hermes") or "hermes"
    ver = (subprocess.run([hermes, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or "").strip().splitlines()
    log = {"schema": "universal-port.p614-e2e/1", "workspace": str(ws), "python": sys.version.split()[0],
           "os": platform.platform(), "hermes_version": next((l for l in ver if l.startswith("Hermes Agent")), "?"),
           "model_calls": 0, "approval_kind": "SIMULATED_BY_TEST_DRIVER (digest read from CANDIDATE_REVIEW.json)",
           "manual_filesystem_operations": 0, "steps": []}
    plan = [["init"], ["select"], ["inspect", "--i-approve-fetch"], ["stage", "--i-accept-skills-only-partial"],
            ["adapt"], ["approve"], ["install", "--i-approve-install"], ["verify"], ["demo"], ["undo"], ["status"]]
    for step in plan:
        args = list(step)
        if step[0] == "approve":
            digest = json.loads((ws / "CANDIDATE_REVIEW.json").read_text(encoding="utf-8"))["candidate_digest"]
            args += ["--candidate-digest", digest]
        t0 = time.time()
        p = subprocess.run([sys.executable, str(REPO / "uvp_guided.py"), *args, "--workspace", str(ws)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"})
        dt = round(time.time() - t0, 1)
        try:
            out = json.loads(p.stdout)
        except ValueError:
            out = {"raw": p.stdout[-2000:], "stderr": p.stderr[-2000:]}
        log["steps"].append({"command": "uvp_guided.py " + " ".join(args), "rc": p.returncode, "seconds": dt, "output": out})
        print("== %-8s rc=%d %6.1fs" % (step[0], p.returncode, dt), flush=True)
        if p.returncode != 0:
            log["failed_step"] = step[0]
            break
    for name in ("INSPECT_REPORT.json", "CANDIDATE_REVIEW.json", "CANDIDATE_REVIEW.md", "INSTALL_RECEIPT.json",
                 "UNDO_RECEIPT.json", "PREINSTALL_INVENTORY.json", "uvp-guided.json"):
        if (ws / name).is_file():
            shutil.copy2(ws / name, ev / name)
    done = [s for s in log["steps"] if s["rc"] == 0]
    log["summary"] = {"commands": len(log["steps"]), "passed": len(done),
                      "human_decisions": ["--workspace", "--i-approve-fetch", "--i-accept-skills-only-partial",
                                          "--candidate-digest (approve the exact candidate)", "--i-approve-install"],
                      "seconds_total": round(sum(s["seconds"] for s in log["steps"]), 1),
                      "setup_seconds_init": next((s["seconds"] for s in log["steps"] if s["command"].startswith("uvp_guided.py init")), None)}
    (ev / "E2E_LOG.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(log["summary"], indent=1))
    return 0 if "failed_step" not in log else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
