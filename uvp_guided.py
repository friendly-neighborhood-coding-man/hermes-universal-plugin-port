"""UVP guided first-time workflow (CLI). Every risky step needs an explicit flag; nothing is silent.

  python uvp_guided.py init     --workspace W                  disposable workspace + Hermes home
  python uvp_guided.py select   --workspace W [--source ID]    choose a pinned foreign plugin
  python uvp_guided.py inspect  --workspace W --i-approve-fetch   fetch the pinned commit; provenance + capability inventory
  python uvp_guided.py stage    --workspace W --i-accept-skills-only-partial   inert Hermes package; supported vs unsupported
  python uvp_guided.py install  --workspace W --i-approve-install   into the workspace's disposable Hermes home only
  python uvp_guided.py verify   --workspace W                  real Hermes: namespaced registration, skill_view, argument delivery
  python uvp_guided.py demo     --workspace W                  representative 3-Skill workflow prompt from the live catalog
  python uvp_guided.py undo     --workspace W                  roll the home back to its pre-install state
  python uvp_guided.py status   --workspace W                  progress, operator inputs vs automatic steps

No foreign code is executed. No connector is connected. No model is called: `demo` prepares the
workflow and prints the exact command; running it is a separate, operator-approved paid step.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compat_engine as CE  # noqa: E402
import install_ops as IO  # noqa: E402
from port_core import PortError, fetch_github  # noqa: E402
from uvp_p6_stage import stage_claude_skill_bundle  # noqa: E402

CATALOG = {
    "product-management": {
        "title": "Anthropic knowledge-work-plugins / product-management (Apache-2.0)",
        "url": "https://github.com/anthropics/knowledge-work-plugins/tree/"
               "e605d8ddbfb688da57dfaaceebd93f12a64ef1d3/product-management",
        "commit": "e605d8ddbfb688da57dfaaceebd93f12a64ef1d3",
        "demo_skills": ["synthesize-research", "write-spec", "roadmap-update"],
    },
}
STATE = "uvp-guided.json"
STEPS = ["init", "select", "inspect", "stage", "install", "verify", "demo", "undo"]
CHECK = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from hermes_cli.plugins import discover_plugins, get_plugin_manager
from tools.skills_tool import skill_view
from agent.skill_commands import build_skill_invocation_message, get_interactive_skill_commands
ns = sys.argv[2]
discover_plugins(force=True)
names = sorted(m["name"] for m in get_plugin_manager().list_plugin_skill_metadata() if m["name"].startswith(ns + ":"))
cmds = get_interactive_skill_commands()
views, delivery = {}, {}
for q in json.loads(sys.argv[3]):
    v = json.loads(skill_view(q))
    views[q] = bool(v.get("success"))
    key = "/" + q.lower()
    msg = build_skill_invocation_message(key, "UVP-ARG-PROBE onboarding notes", task_id="uvp-guided") if key in cmds else None
    delivery[q] = bool(msg and msg.rstrip().endswith("UVP-ARG-PROBE onboarding notes"))
print(json.dumps({"registered": names, "skill_view": views, "slash_argument_delivered": delivery}))
"""


def _ws(path) -> Path:
    return Path(path).expanduser().resolve()


def load(ws: Path) -> dict:
    p = ws / STATE
    if not p.is_file():
        raise PortError("Not a UVP guided workspace; run `init` first")
    return json.loads(p.read_text(encoding="utf-8"))


def save(ws: Path, st: dict):
    (ws / STATE).write_text(json.dumps(st, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record(st, step, *, operator_inputs, automatic, result):
    st["steps"][step] = {"operator_inputs": operator_inputs, "automatic": automatic, "result": result}


def hermes_exe() -> str:
    exe = os.environ.get("HERMES_EXE") or shutil.which("hermes")
    if not exe:
        raise PortError("Hermes CLI not found on PATH (or set HERMES_EXE)")
    return exe


def hermes(ws_state, *args, timeout=900):
    env = {**os.environ, "HERMES_HOME": ws_state["home"], "PYTHONDONTWRITEBYTECODE": "1", "UVP_ENABLE_ARXIV_EXECUTION": "0"}
    p = subprocess.run([hermes_exe(), *args], env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def hermes_runtime(st) -> tuple[str, str]:
    """Auto-resolve the Hermes source dir and the home's own runtime Python."""
    rc, out = hermes(st, "--version")
    src = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("Install directory:")), None)
    facts = sorted(Path(st["home"], "installs").glob("*/facts.json"))
    py = None
    for f in facts:
        env = json.loads(f.read_text(encoding="utf-8")).get("packages", {}).get("venv", {}).get("environment")
        for cand in (Path(env or "") / "Scripts" / "python.exe", Path(env or "") / "bin" / "python"):
            if env and cand.is_file():
                py = str(cand)
    if not src or not py:
        raise PortError("Could not resolve the Hermes runtime for this home (run `hermes --version` once)")
    return src, py


def cmd_init(a):
    ws = _ws(a.workspace)
    if ws.exists() and any(ws.iterdir()):
        raise PortError("Workspace exists and is not empty; choose a new directory")
    home = ws / "hermes-home"
    (home / "plugins").mkdir(parents=True)
    (home / IO.MARKER).write_text("disposable UVP guided workspace\n", encoding="utf-8")
    (home / "config.yaml").write_text("plugins:\n  enabled: []\n  disabled: []\ntelemetry:\n  shared_metrics:\n"
                                      "    enabled: false\n    send: false\n", encoding="utf-8")
    st = {"schema": "universal-port.guided/1", "workspace": str(ws), "home": str(home), "steps": {}}
    import time
    t0 = time.time()
    rc_boot, _ = hermes(st, "plugins", "list", timeout=1800)  # Hermes builds this home's runtime once, before any baseline
    boot_s = round(time.time() - t0)
    rc, out = hermes(st, "--version")
    record(st, "init", operator_inputs=["--workspace"], automatic=["disposable Hermes home", "Hermes first-run bootstrap"],
           result={"home": str(home), "bootstrap_seconds": boot_s, "bootstrap_rc": rc_boot,
                   "hermes": next((l.strip() for l in out.splitlines() if l.strip().startswith("Hermes Agent")), "?")})
    save(ws, st)
    return st["steps"]["init"]


def cmd_select(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if a.source not in CATALOG:
        raise PortError("Unknown source; available: " + ", ".join(CATALOG))
    st["source"] = a.source
    record(st, "select", operator_inputs=["--source " + a.source] if a.source_given else [],
           automatic=["pinned commit from the UVP source catalog"], result=CATALOG[a.source])
    save(ws, st)
    return st["steps"]["select"]


def cmd_inspect(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not a.i_approve_fetch:
        raise PortError("Fetching downloads public source code: re-run with --i-approve-fetch")
    src = CATALOG[st["source"]]
    res = fetch_github(src["url"], str(ws / "source"), approved=True)
    if res.get("commit_sha") != src["commit"]:
        raise PortError("Fetched commit does not match the pinned commit")
    root = Path(res["source_path"])
    inv = {"skills": sorted(p.parent.name for p in root.glob("skills/*/SKILL.md")),
           "connectors": sorted(json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers", {}))
           if (root / ".mcp.json").is_file() else [],
           "commands": sorted(p.name for p in root.glob("commands/*.md")),
           "hooks": (root / "hooks").exists(), "agents": (root / "agents").exists()}
    st["source_path"] = str(root)
    record(st, "inspect", operator_inputs=["--i-approve-fetch"],
           automatic=["download at the pinned commit", "commit check", "capability inventory"],
           result={"commit": res.get("commit_sha"), "source_path": str(root), "inventory": inv,
                   "files": sum(1 for p in root.rglob("*") if p.is_file())})
    save(ws, st)
    return st["steps"]["inspect"]


def cmd_stage(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not a.i_accept_skills_only_partial:
        raise PortError("Connectors/commands are NOT ported (SKILLS_ONLY_PARTIAL). Review `inspect`, then re-run "
                        "with --i-accept-skills-only-partial")
    src = CATALOG[st["source"]]
    out = stage_claude_skill_bundle(st["source_path"], str(ws / "stage"), approved=True, allow_partial=True,
                                    declared_source_commit=src["commit"])
    report = CE.map_stage(out["staged_path"], str(ws / "compat-report"))
    st["stage"] = out["staged_path"]
    record(st, "stage", operator_inputs=["--i-accept-skills-only-partial"],
           automatic=["inert Hermes package (originals byte-preserved)", "deterministic compatibility report"],
           result={"status": out["status"], "staged_path": out["staged_path"], "unported_connectors": out["unported_connectors"],
                   "compat_counts": report["counts"], "model_calls": report["model_calls"],
                   "report": str(ws / "compat-report" / "COMPAT_REPORT.md")})
    save(ws, st)
    return st["steps"]["stage"]


def _installer(st, *, with_check=True):
    def enable(n):
        rc, out = hermes(st, "plugins", "enable", n)
        if rc != 0:
            raise PortError("hermes plugins enable failed: " + out[-200:])

    def validate(pkg):
        rc, out = hermes(st, "plugins", "validate", str(pkg))
        return {"ok": rc == 0, "why": out[-300:]}
    return IO.Installer(st["home"], "ported-" + st["source"], enable=enable,
                        disable=lambda n: hermes(st, "plugins", "disable", n), validate=validate,
                        check=(lambda: _verify(st, quiet=True)) if with_check else None)


def cmd_install(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not a.i_approve_install:
        raise PortError("Installing changes the workspace's disposable Hermes home: re-run with --i-approve-install")
    inst = _installer(st)
    r = inst.install(Path(st["stage"]))
    st["install_backup"] = r.get("backup")
    record(st, "install", operator_inputs=["--i-approve-install"],
           automatic=["validate before swap (hashes + hermes plugins validate)", "hermes plugins enable",
                      "post-install resolution check", "automatic rollback on failure"], result=r)
    save(ws, st)
    if not r["ok"]:
        raise PortError("Install failed and was rolled back: " + r.get("why", ""))
    return st["steps"]["install"]


def _verify(st, quiet=False):
    src, py = hermes_runtime(st)
    ns = "ported-" + st["source"]
    skills = [ns + ":" + s for s in CATALOG[st["source"]]["demo_skills"]]
    env = {**os.environ, "HERMES_HOME": st["home"], "PYTHONDONTWRITEBYTECODE": "1", "UVP_ENABLE_ARXIV_EXECUTION": "0"}
    p = subprocess.run([py, "-I", "-c", CHECK, src, ns, json.dumps(skills)], env=env, capture_output=True, text=True, timeout=300)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "why": p.stderr[-300:]}
    ok = len(r["registered"]) > 0 and all(r["skill_view"].values()) and all(r["slash_argument_delivered"].values())
    return {"ok": ok, **r}


def cmd_verify(a):
    ws = _ws(a.workspace)
    st = load(ws)
    r = _verify(st)
    record(st, "verify", operator_inputs=[], automatic=["resolve Hermes runtime", "plugin discovery", "skill_view",
                                                         "slash argument delivery"], result=r)
    save(ws, st)
    return st["steps"]["verify"]


def cmd_demo(a):
    ws = _ws(a.workspace)
    st = load(ws)
    ns = "ported-" + st["source"]
    fixture = HERE / "examples" / "p6-onboarding-interviews.md"
    run_dir = ws / "demo-run"
    run_dir.mkdir(exist_ok=True)
    shutil.copy2(fixture, run_dir / fixture.name)
    skills = [ns + ":" + s for s in CATALOG[st["source"]]["demo_skills"]]
    prompt = ("Execute this three-step research-to-roadmap task. Use only the fixture at %s.\n"
              "1) Load and FOLLOW skill_view(\"%s\"); write research-synthesis.md with interview IDs.\n"
              "2) Load and FOLLOW skill_view(\"%s\"); write onboarding-prd.md with acceptance tests.\n"
              "3) Load and FOLLOW skill_view(\"%s\"); write onboarding-roadmap.md (Now/Next/Later).\n"
              "Where a Skill says to ask the user, use the supplied context; if a required answer is missing, report HOLD."
              % (run_dir / fixture.name, *skills))
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = ('set HERMES_HOME=%s && set HERMES_WRITE_SAFE_ROOT=%s && hermes chat --query-file "%s" --oneshot '
               '--format stream-json --in "%s" -t skills,file --max-turns 40' % (st["home"], run_dir, run_dir / "prompt.txt", run_dir))
    record(st, "demo", operator_inputs=[], automatic=["fixture copy", "prompt from the installed Skill names"],
           result={"prompt": str(run_dir / "prompt.txt"), "model_calls": 0,
                   "to_run_with_a_model": command,
                   "note": "Running it makes paid model calls; UVP does not run it for you. HERMES_WRITE_SAFE_ROOT bounds "
                           "file writes only when set in the environment of the process that executes tools."})
    save(ws, st)
    return st["steps"]["demo"]


def cmd_undo(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not st.get("install_backup"):
        raise PortError("Nothing to undo")
    before = IO.manifest(Path(st["home"]))
    _installer(st, with_check=False).rollback_to(Path(st["install_backup"]))
    after = IO.manifest(Path(st["home"]))
    plugin_gone = not (Path(st["home"]) / "plugins" / ("ported-" + st["source"])).exists()
    record(st, "undo", operator_inputs=[], automatic=["restore plugin dir and config.yaml from the pre-install backup"],
           result={"plugin_removed": plugin_gone, "files_changed": len(set(before.items()) ^ set(after.items()))})
    st["install_backup"] = None
    save(ws, st)
    return st["steps"]["undo"]


def cmd_status(a):
    st = load(_ws(a.workspace))
    rows = []
    for s in STEPS:
        d = st["steps"].get(s)
        rows.append({"step": s, "done": d is not None, "operator_inputs": (d or {}).get("operator_inputs", []),
                     "automatic": (d or {}).get("automatic", [])})
    return {"steps": rows, "operator_input_count": sum(len(r["operator_inputs"]) for r in rows),
            "automatic_count": sum(len(r["automatic"]) for r in rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UVP guided first-time workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in STEPS + ["status"]:
        p = sub.add_parser(name)
        p.add_argument("--workspace", required=True)
        if name == "select":
            p.add_argument("--source", default=None)
        if name == "inspect":
            p.add_argument("--i-approve-fetch", action="store_true")
        if name == "stage":
            p.add_argument("--i-accept-skills-only-partial", action="store_true")
        if name == "install":
            p.add_argument("--i-approve-install", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "select":
        a.source_given = a.source is not None
        a.source = a.source or "product-management"
    try:
        out = globals()["cmd_" + a.cmd](a)
        print(json.dumps({"ok": True, "step": a.cmd, **out}, indent=2, default=str))
        return 0
    except (PortError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "step": a.cmd, "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
