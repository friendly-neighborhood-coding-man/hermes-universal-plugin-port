"""WP3 genuine before/after: the verbatim port vs the UVP-adapted port in a REAL Hermes home.

No model calls. A NEW disposable home (refuses if it exists). For each pilot Skill it
follows what the installed Skill text itself tells the user/model to do:
  BA1  run the Skill's documented Usage command (the token on its `/...` Usage line)
       through Hermes's real slash resolver and message builder, with an argument;
  BA2  open the Skill's referenced resource link through Hermes's real
       skill_view(file_path=...).
Then it rolls the home back to the pre-install state.

  python scripts/p6_before_after.py <evidence.json>
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import adapt_package as AP  # noqa: E402
import install_ops as IO  # noqa: E402

HOME = Path(os.environ.get("UVP_BA_HOME", r"D:\Hermes-Lab\uvp-before-after-home"))
WORK = Path(os.environ.get("UVP_BA_WORK", r"D:\Hermes-Lab\uvp-before-after-work"))
STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")
NAME = "ported-product-management"
PILOT = ["synthesize-research", "write-spec", "roadmap-update"]
HERMES = os.environ.get("HERMES_EXE") or shutil.which("hermes") or "hermes"
ENV = {**os.environ, "HERMES_HOME": str(HOME), "PYTHONDONTWRITEBYTECODE": "1", "UVP_ENABLE_ARXIV_EXECUTION": "0"}
PROBE = r"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from hermes_cli.plugins import discover_plugins
from tools.skills_tool import skill_view
from agent.skill_commands import resolve_skill_command_key, build_skill_invocation_message
discover_plugins(force=True)
home, ns = Path(sys.argv[2]), sys.argv[3]
out = {}
for skill in json.loads(sys.argv[4]):
    body = (home / "plugins" / ns / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    usage = next((l.strip() for l in body.splitlines() if l.strip().startswith("/")), "")
    token = usage.split()[0][1:] if usage else ""
    key = resolve_skill_command_key(token, interactive=True)
    msg = build_skill_invocation_message(key, "UVP-ARG-PROBE SSO support", task_id="ba") if key else None
    link = next((m.group(1) for m in re.finditer(r"\]\(([^)\s]+)\)", body) if "CONNECTORS" in m.group(1)), None)
    res = json.loads(skill_view(ns + ":" + skill, file_path=link)) if link else {}
    out[skill] = {
        "BA1_documented_usage_line": usage,
        "BA1_token_resolves": key is not None,
        "BA1_argument_delivered": bool(msg and msg.rstrip().endswith("UVP-ARG-PROBE SSO support")),
        "BA2_link": link,
        "BA2_skill_view_success": bool(res.get("success")),
        "BA2_error": res.get("error"),
        "BA2_states_connectors_unavailable": "NOT connected" in (res.get("content") or ""),
    }
print(json.dumps(out))
"""


def hermes(*args, timeout=1800):
    p = subprocess.run([HERMES, *args], env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-400:]


def runtime():
    rc, out = hermes("--version")
    src = next(l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("Install directory:"))
    for f in HOME.glob("installs/*/facts.json"):
        env = json.loads(f.read_text(encoding="utf-8"))["packages"]["venv"]["environment"]
        return src, str(Path(env) / "Scripts" / "python.exe")
    raise SystemExit("no runtime")


def probe():
    src, py = runtime()
    p = subprocess.run([py, "-I", "-c", PROBE, src, str(HOME), NAME, json.dumps(PILOT)], env=ENV, capture_output=True, text=True, timeout=600)
    return json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {"error": p.stderr[-400:]}


def main(out_path):
    if HOME.exists() or WORK.exists():
        raise SystemExit("Refusing: before/after home or work dir exists")
    (HOME / "plugins").mkdir(parents=True)
    (HOME / IO.MARKER).write_text("disposable before/after home\n", encoding="utf-8")
    (HOME / "config.yaml").write_text("plugins:\n  enabled: []\n  disabled: []\n", encoding="utf-8")
    WORK.mkdir()
    ev = {"model_calls": 0, "stage": str(STAGE), "bootstrap_rc": hermes("plugins", "list")[0]}
    s0 = IO.manifest(HOME)
    inst = IO.Installer(HOME, NAME, enable=lambda n: hermes("plugins", "enable", n),
                        disable=lambda n: hermes("plugins", "disable", n),
                        validate=lambda p: (lambda r: {"ok": r[0] == 0, "why": r[1]})(hermes("plugins", "validate", str(p))))
    r = inst.install(STAGE)
    ev["install_verbatim"] = r["result"]
    ev["before"] = probe()
    adapted = WORK / "adapted"
    ev["adaptation"] = AP.adapt(str(STAGE), str(adapted))
    u = inst.update(adapted)
    ev["update_to_adapted"] = u["result"]
    ev["after"] = probe()
    inst.rollback_to(Path(r["backup"]))
    diff = sorted({k for k, _ in set(s0.items()) ^ set(IO.manifest(HOME).items())})
    ev["rollback_diff_only_hermes_backups"] = all(k.startswith("backups/") for k in diff)
    Path(out_path).write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    for k in ("before", "after"):
        print(k, json.dumps({s: {kk: v for kk, v in d.items() if kk.startswith("BA")} for s, d in ev[k].items()}, indent=1)[:1800])


if __name__ == "__main__":
    main(sys.argv[1])
