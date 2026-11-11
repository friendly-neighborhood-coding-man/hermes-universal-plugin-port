"""UVP guided first-time workflow (CLI): Inspect -> Adapt -> Review & Approve -> Install -> Verify -> Demo -> Undo.
Every risky step needs an explicit flag or the exact candidate digest; nothing is silent.

  python uvp_guided.py init     --workspace W                  disposable workspace + Hermes home
  python uvp_guided.py select   --workspace W [--source ID]    choose a pinned foreign plugin
  python uvp_guided.py inspect  --workspace W --i-approve-fetch   fetch the pinned commit; INSPECT_REPORT.json
  python uvp_guided.py stage    --workspace W --i-accept-skills-only-partial   inert verbatim Hermes package + compat report
  python uvp_guided.py adapt    --workspace W                  deterministic rules into a SEPARATE candidate; CANDIDATE_REVIEW.md
  python uvp_guided.py approve  --workspace W --candidate-digest D   approve exactly that candidate (digest from the review)
  python uvp_guided.py install  --workspace W --i-approve-install   install the approved candidate (re-verified) into the home
  python uvp_guided.py verify   --workspace W                  real Hermes: registration, skill_view, documented usage, resources
  python uvp_guided.py demo     --workspace W                  PREPARES a 3-Skill prompt and prints the command (does not run it)
  python uvp_guided.py undo     --workspace W                  restore plugin dir + config.yaml; exact residual diff
  python uvp_guided.py status   --workspace W                  progress, operator inputs vs automatic steps

No foreign code is executed. No connector is connected. No model is called by any step.
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
STEPS = ["init", "select", "inspect", "stage", "adapt", "approve", "install", "verify", "demo", "undo"]
CHECK = r"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from hermes_cli.plugins import discover_plugins, get_plugin_manager
from tools.skills_tool import skill_view
from agent.skill_commands import build_skill_invocation_message, get_interactive_skill_commands, resolve_skill_command_key
ns, home = sys.argv[2], Path(sys.argv[4])
discover_plugins(force=True)
names = sorted(m["name"] for m in get_plugin_manager().list_plugin_skill_metadata() if m["name"].startswith(ns + ":"))
cmds = get_interactive_skill_commands()
out = {"registered": names, "skill_view": {}, "slash_argument_delivered": {}, "documented_usage": {}, "resource": {}}
for q in json.loads(sys.argv[3]):
    v = json.loads(skill_view(q))
    out["skill_view"][q] = bool(v.get("success"))
    key = "/" + q.lower()
    msg = build_skill_invocation_message(key, "UVP-ARG-PROBE onboarding notes", task_id="uvp-guided") if key in cmds else None
    out["slash_argument_delivered"][q] = bool(msg and msg.rstrip().endswith("UVP-ARG-PROBE onboarding notes"))
    body = (home / "plugins" / ns / "skills" / q.split(":", 1)[1] / "SKILL.md").read_text(encoding="utf-8")
    usage = next((l.strip() for l in body.splitlines() if l.strip().startswith("/")), "")
    token = usage.split()[0][1:] if usage else ""
    k2 = resolve_skill_command_key(token, interactive=True) if token else None
    m2 = build_skill_invocation_message(k2, "UVP-ARG-PROBE SSO support", task_id="uvp-guided") if k2 else None
    out["documented_usage"][q] = {"line": usage, "resolves": k2 is not None,
                                  "argument_delivered": bool(m2 and m2.rstrip().endswith("UVP-ARG-PROBE SSO support"))}
    link = next((m.group(1) for m in re.finditer(r"\]\(([^)\s]+)\)", body) if "CONNECTORS" in m.group(1)), None)
    r = json.loads(skill_view(q, file_path=link)) if link else {}
    out["resource"][q] = {"link": link, "skill_view_success": bool(r.get("success")), "error": r.get("error"),
                          "states_connectors_not_connected": "NOT connected" in (r.get("content") or "")}
print(json.dumps(out))
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
    hashes = {p.relative_to(root).as_posix(): _sha_file(p) for p in sorted(root.rglob("*")) if p.is_file()}
    report = {"schema": "universal-port.inspect/1", "source": {"repo_url": src["url"], "commit": res.get("commit_sha")},
              "source_file_sha256": hashes, "supported": {"skills": inv["skills"]},
              "unsupported": {"connectors": inv["connectors"], "commands": inv["commands"],
                              "hooks": inv["hooks"], "agents": inv["agents"]},
              "required_adaptation_rules": "computed by `stage` (compat report) and applied by `adapt`",
              "filesystem_and_execution_effects": EFFECTS, "limitations": LIMITS, "model_calls": 0}
    (ws / "INSPECT_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    record(st, "inspect", operator_inputs=["--i-approve-fetch"],
           automatic=["download at the pinned commit", "commit check", "capability inventory"],
           result={"commit": res.get("commit_sha"), "source_path": str(root), "inventory": inv,
                   "files": len(hashes), "report": str(ws / "INSPECT_REPORT.json")})
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
                   "rules_applicable": report.get("rules_applied"),
                   "report": str(ws / "compat-report" / "COMPAT_REPORT.md")})
    save(ws, st)
    return st["steps"]["stage"]


def _installer(st, *, with_check=True, check=None):
    def enable(n):
        rc, out = hermes(st, "plugins", "enable", n)
        if rc != 0:
            raise PortError("hermes plugins enable failed: " + out[-200:])

    def validate(pkg):
        rc, out = hermes(st, "plugins", "validate", str(pkg))
        return {"ok": rc == 0, "why": out[-300:]}
    return IO.Installer(st["home"], "ported-" + st["source"], enable=enable,
                        disable=lambda n: hermes(st, "plugins", "disable", n), validate=validate,
                        check=check if check is not None else ((lambda: _verify(st, quiet=True)) if with_check else None))


# --- P6.14: Adapt -> Review & Approve -> Install the exact approved candidate ---------------

EFFECTS = [
    "Writes only inside the workspace (source, stage, candidate, reports) and the workspace's disposable Hermes home.",
    "install copies the approved candidate to <home>/plugins/ported-<source> and runs `hermes plugins enable` for it.",
    "No foreign code is executed: Skills are Markdown instructions; the generated __init__.py only calls ctx.register_skill.",
    "No connector, hook, agent or command from the source is installed or enabled.",
    "No model is called by any step.",
]
LIMITS = [
    "SKILLS_ONLY_PARTIAL: MCP/OAuth connectors and commands are not ported.",
    "SEMANTIC_EQUIVALENCE_NOT_ESTABLISHED: Hermes following a ported Skill is not proof of Claude-equivalent behaviour.",
    "A disposable HERMES_HOME is not an OS sandbox.",
]


def _sha_file(p: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _spans(before: str, after: str, path: str) -> list:
    import difflib
    out = []
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), "stage/" + path, "candidate/" + path, n=0, lineterm=""):
        out.append(line)
    return out[:80]


def _candidate_dir(ws: Path, st: dict) -> Path:
    return ws / "candidate" / ("ported-" + st["source"])


def cmd_adapt(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not st.get("stage"):
        raise PortError("Run `stage` first")
    import adapt_package as AP
    stage = Path(st["stage"])
    cand = _candidate_dir(ws, st)
    if cand.exists():
        raise PortError("A candidate already exists at %s; it is never overwritten. Use a new workspace to re-adapt." % cand)
    stage_digest_before = IO.package_digest(stage)
    man = AP.adapt(str(stage), str(cand))
    if IO.package_digest(stage) != stage_digest_before:
        raise PortError("The stage changed during adaptation; refusing")
    v = IO.verify_package(cand)
    if not v["ok"]:
        raise PortError("Adapted candidate failed self-verification: " + v["why"])
    changes = []
    for c in man["changes"]:
        rel = c["path"]
        before = (stage / rel).read_text(encoding="utf-8") if (stage / rel).is_file() else ""
        after = (cand / rel).read_text(encoding="utf-8")
        changes.append({"path": rel, "rules": c.get("rules") or [c.get("rule")], "added": bool(c.get("added")),
                        "before_sha256": c.get("before_sha256"), "after_sha256": c["after_sha256"],
                        "source": c.get("source"), "changed_spans": _spans(before, after, rel)})
    stage_files = IO.package_files(stage)
    cand_files = IO.package_files(cand)
    originals = {k: v for k, v in cand_files.items() if k.startswith("original/")}
    rep = json.loads((stage / "PORTING_REPORT.json").read_text(encoding="utf-8"))
    review = {
        "schema": "universal-port.candidate-review/1",
        "source": {"repo_url": CATALOG[st["source"]]["url"], "commit": CATALOG[st["source"]]["commit"]},
        "stage_digest": stage_digest_before, "candidate_path": str(cand),
        "candidate_digest": IO.package_digest(cand), "candidate_files": len(cand_files),
        "adaptation_manifest_sha256": _sha_file(cand / "ADAPTATION_MANIFEST.json"),
        "originals_preserved": {"count": len(originals),
                                "identical_to_stage": all(stage_files.get(k) == v for k, v in originals.items())},
        "files_changed_by_uvp": changes,
        "files_unchanged_from_stage": sorted(k for k, v in cand_files.items() if stage_files.get(k) == v and not k.startswith("original/")),
        "rules_applied": sorted({r for c in changes for r in c["rules"] if r}),
        "unsupported_not_installed": {"connectors": rep.get("unported_connector_names", []),
                                      "components": rep.get("unsupported_source_components", []),
                                      "status": rep.get("status")},
        "will_install": "%d files to <home>/plugins/ported-%s, then `hermes plugins enable ported-%s`"
                        % (len(cand_files), st["source"], st["source"]),
        "will_not_install_or_enable": ["MCP/OAuth connectors", "source commands/hooks/agents", "any other plugin"],
        "model_calls": 0,
    }
    (ws / "CANDIDATE_REVIEW.json").write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = ["# UVP candidate review", "",
          "Source: %s @ `%s`" % (review["source"]["repo_url"], review["source"]["commit"]), "",
          "**Candidate digest (approve this): `%s`**" % review["candidate_digest"], "",
          "- Original files preserved: %d (identical to the stage: %s)" % (len(originals), review["originals_preserved"]["identical_to_stage"]),
          "- Files changed or added by UVP: %d, rules %s" % (len(changes), ", ".join(review["rules_applied"])),
          "- Not installed or enabled: " + "; ".join(review["will_not_install_or_enable"]),
          "- Unsupported, stays inactive (%s): %d connectors (%s); %s" % (
              review["unsupported_not_installed"]["status"], len(review["unsupported_not_installed"]["connectors"]),
              ", ".join(review["unsupported_not_installed"]["connectors"]),
              "; ".join(review["unsupported_not_installed"]["components"])),
          "- Will install: " + review["will_install"], "", "## Changes", ""]
    for c in changes:
        md.append("### `%s` (%s%s)" % (c["path"], ", ".join(r for r in c["rules"] if r), ", added" if c["added"] else ""))
        md.append("```diff")
        md.extend(c["changed_spans"][:30])
        md.append("```")
    (ws / "CANDIDATE_REVIEW.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    st["candidate"] = str(cand)
    st["candidate_digest"] = review["candidate_digest"]
    st.pop("approval", None)
    record(st, "adapt", operator_inputs=[],
           automatic=["deterministic adaptation into a separate candidate (stage untouched)",
                      "candidate self-verification", "candidate digest + human-readable review"],
           result={"candidate_digest": review["candidate_digest"], "files_changed_by_uvp": len(changes),
                   "rules_applied": review["rules_applied"], "review": str(ws / "CANDIDATE_REVIEW.md"), "model_calls": 0})
    save(ws, st)
    return st["steps"]["adapt"]


def cmd_approve(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not st.get("candidate"):
        raise PortError("Run `adapt` first, then read CANDIDATE_REVIEW.md")
    if not a.candidate_digest:
        raise PortError("Approval binds to the exact candidate. Read %s and re-run with --candidate-digest <digest shown there>"
                        % (ws / "CANDIDATE_REVIEW.md"))
    now = IO.package_digest(Path(st["candidate"]))
    if a.candidate_digest != now or now != st.get("candidate_digest"):
        raise PortError("Digest does not match the current candidate (%s); nothing approved" % now)
    import time
    st["approval"] = {"candidate_digest": now, "candidate_path": st["candidate"], "approved_utc": time.time(),
                      "kind": "OPERATOR_CLI_FLAG", "note": "operator typed the digest on the command line"}
    record(st, "approve", operator_inputs=["--candidate-digest"], automatic=["digest recomputed and compared"],
           result={"approved_digest": now})
    save(ws, st)
    return st["steps"]["approve"]


def _preinstall_checks(st) -> Path:
    appr = st.get("approval")
    if not appr:
        raise PortError("No approval recorded: run `approve --candidate-digest <digest>` after reading CANDIDATE_REVIEW.md")
    cand = Path(st["candidate"])
    if appr["candidate_path"] != str(cand) or appr["candidate_digest"] != st.get("candidate_digest"):
        raise PortError("Stale approval: it does not belong to the current candidate. Re-run `approve`.")
    now = IO.package_digest(cand)
    if now != appr["candidate_digest"]:
        raise PortError("The candidate changed after approval (now %s); approval invalidated. Re-run `adapt` in a new "
                        "workspace or re-review and `approve` again." % now)
    v = IO.verify_package(cand)
    if not v["ok"]:
        raise PortError("Candidate manifest/content check failed: " + v["why"])
    man = json.loads((cand / "ADAPTATION_MANIFEST.json").read_text(encoding="utf-8"))
    stage = Path(st["stage"])
    rep = json.loads((stage / "PORTING_REPORT.json").read_text(encoding="utf-8"))
    if Path(man["from_stage"]).resolve() != stage.resolve() or man.get("stage_fingerprint") != rep.get("source_fingerprint_sha256"):
        raise PortError("Candidate is not bound to this workspace's stage")
    for k, h in json.loads((stage / "SOURCE_HASHES.json").read_text(encoding="utf-8")).items():
        if _sha_file(cand / "original" / k) != h:
            raise PortError("Source hash mismatch in candidate: original/" + k)
    for f in ("plugin.yaml", "__init__.py"):
        if _sha_file(cand / f) != _sha_file(stage / f):
            raise PortError("Unsupported permission escalation: %s differs from the reviewed stage" % f)
    home = Path(st["home"]).resolve()
    target = home / "plugins" / ("ported-" + st["source"])
    for p in (home, home / "plugins"):
        if IO.is_redirect(p):
            raise PortError("Refusing: %s is a symlink or junction" % p)
    if target.exists() or target.is_symlink():
        raise PortError("Refusing to overwrite an existing plugin at " + str(target))
    if (home / "plugins").resolve() != home / "plugins":
        raise PortError("Unexpected installation path")
    return cand


def cmd_install(a):
    ws = _ws(a.workspace)
    st = load(ws)
    if not a.i_approve_install:
        raise PortError("Installing changes the workspace's disposable Hermes home: re-run with --i-approve-install")
    cand = _preinstall_checks(st)
    home = Path(st["home"])
    (ws / "PREINSTALL_INVENTORY.json").write_text(json.dumps(IO.full_inventory(home), sort_keys=True) + "\n",
                                                 encoding="utf-8")
    approved = st["approval"]["candidate_digest"]
    target = home / "plugins" / ("ported-" + st["source"])

    def check():
        got = IO.package_digest(target)
        if got != approved:
            return {"ok": False, "why": "installed bytes %s != approved %s" % (got, approved)}
        return _verify(st, quiet=True)
    inst = _installer(st, check=check)
    r = inst.install(cand)
    st["install_backup"] = r.get("backup")
    installed = IO.package_digest(target) if r["ok"] else None
    receipt = {"approved_digest": approved, "installed_digest": installed, "installed_path": str(target),
               "match": installed == approved, "result": r["result"], "backup": r.get("backup"),
               "installed_files": IO.package_files(target) if r["ok"] else {}}
    (ws / "INSTALL_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    record(st, "install", operator_inputs=["--i-approve-install"],
           automatic=["re-verify approval, digest, manifest, source hashes, path", "validate before swap",
                      "copy the approved candidate", "hermes plugins enable", "installed-digest + runtime check",
                      "automatic rollback on failure"], result=receipt)
    save(ws, st)
    if not r["ok"]:
        raise PortError("Install failed and was rolled back: %s. The home is back to its pre-install state for the "
                        "plugin dir and config.yaml; see INSTALL_RECEIPT.json." % r.get("why", ""))
    return st["steps"]["install"]


def _verify(st, quiet=False):
    src, py = hermes_runtime(st)
    ns = "ported-" + st["source"]
    skills = [ns + ":" + s for s in CATALOG[st["source"]]["demo_skills"]]
    env = {**os.environ, "HERMES_HOME": st["home"], "PYTHONDONTWRITEBYTECODE": "1", "UVP_ENABLE_ARXIV_EXECUTION": "0"}
    p = subprocess.run([py, "-I", "-c", CHECK, src, ns, json.dumps(skills), st["home"]], env=env, capture_output=True,
                       text=True, timeout=300)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "why": p.stderr[-300:]}
    adapted = bool(st.get("approval"))
    ok = (len(r["registered"]) > 0 and all(r["skill_view"].values()) and all(r["slash_argument_delivered"].values()))
    if adapted:
        ok = ok and all(d["resolves"] and d["argument_delivered"] for d in r["documented_usage"].values()) \
            and all(d["skill_view_success"] and d["states_connectors_not_connected"] for d in r["resource"].values())
    target = Path(st["home"]) / "plugins" / ns
    if adapted and target.is_dir():
        r["installed_digest"] = IO.package_digest(target)
        r["installed_digest_matches_approval"] = r["installed_digest"] == st["approval"]["candidate_digest"]
        ok = ok and r["installed_digest_matches_approval"]
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
    home = Path(st["home"])
    _installer(st, with_check=False).rollback_to(Path(st["install_backup"]))
    plugin_gone = not (home / "plugins" / ("ported-" + st["source"])).exists()
    pre = ws / "PREINSTALL_INVENTORY.json"
    if not pre.is_file():
        raise PortError("Pre-install inventory missing; cannot compute an exact undo diff")
    diff = IO.classify_residuals(json.loads(pre.read_text(encoding="utf-8")), IO.full_inventory(home),
                                 plugin="ported-" + st["source"])
    rc_path = ws / "INSTALL_RECEIPT.json"
    installed = json.loads(rc_path.read_text(encoding="utf-8")).get("installed_files", {}) if rc_path.is_file() else {}
    tgt = "plugins/ported-%s/" % st["source"]
    diff["summary"]["UVP_CREATED_AND_REMOVED"] = sum(1 for k in installed if not (home / (tgt + k)).exists())
    diff["uvp_installed_files"] = len(installed)
    (ws / "UNDO_RECEIPT.json").write_text(json.dumps({"plugin_removed": plugin_gone, **diff}, indent=2) + "\n", encoding="utf-8")
    record(st, "undo", operator_inputs=[], automatic=["restore plugin dir and config.yaml from the pre-install backup",
                                                     "exact inventory diff against the pre-install snapshot"],
           result={"plugin_removed": plugin_gone, "summary": diff["summary"], "receipt": str(ws / "UNDO_RECEIPT.json")})
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
        if name == "approve":
            p.add_argument("--candidate-digest", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "select":
        a.source_given = a.source is not None
        a.source = a.source or "product-management"
    w = '--workspace "%s"' % a.workspace
    nxt = {"init": "select " + w, "select": "inspect %s --i-approve-fetch" % w,
           "inspect": "stage %s --i-accept-skills-only-partial" % w, "stage": "adapt " + w,
           "approve": "install %s --i-approve-install" % w, "install": "verify " + w, "verify": "demo " + w,
           "demo": "undo %s   (when you are done)" % w, "undo": "status " + w}
    try:
        out = globals()["cmd_" + a.cmd](a)
        if a.cmd == "adapt":
            nxt["adapt"] = "approve %s --candidate-digest %s   (after reading CANDIDATE_REVIEW.md)" % (
                w, out["result"]["candidate_digest"])
        res = {"ok": True, "step": a.cmd, **out}
        if a.cmd in nxt:
            res["next"] = "python uvp_guided.py " + nxt[a.cmd]
        print(json.dumps(res, indent=2, default=str))
        return 0
    except (PortError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "step": a.cmd, "error": str(exc),
                          "recovery": "Nothing was installed or changed by this failed step unless the error says it "
                                      "was rolled back. Fix the cause above, then re-run the same command; "
                                      "`status %s` shows progress." % w}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
