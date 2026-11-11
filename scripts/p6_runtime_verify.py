"""P6 Runtime Mapping Verification harness. In-process Hermes calls only; no model calls.

Run with the disposable profile's own Hermes venv interpreter and
HERMES_HOME pointing at the disposable P6 home (the script refuses any other home).

  preflight : records the Hermes runtime identity and confirms the foreign
              plugin is NOT installed or enabled. Changes nothing.
  verify    : after a separately approved install+enable into the disposable
              home, checks namespaced registration, skill_view resolution,
              relative-resource behavior and slash-command argument delivery.

Evidence gates are reported separately and never merged:
  STRUCTURAL  - bytes installed == validated stage bytes
  RESOLUTION  - Hermes actually registers / resolves / delivers (this script)
  SEMANTIC    - NOT TESTED here (needs a real model run and operator judgment)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

DISPOSABLE_HOME = Path(r"D:\Hermes-Lab\uvp-p6-hermes-test")
HERMES_SRC = Path(r"D:\Hermes-Lab\hermes-agent")
STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")
PLUGIN = "ported-product-management"
EXPECTED_COMMIT = "b200f5bc60e31588ba2cb60e288029c4a54ba5fa"
PROBE_SHA = "cad380f2a3147e5e6d932caecda3f9f62860df6530642c95d439460b8c764022"
PILOT = ("synthesize-research", "write-spec", "roadmap-update")
MARKER = "The user has provided the following instruction alongside the skill invocation: "
ARG = "Onboarding confusion for first-week admins"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tree(root: Path, skip=("__pycache__", "P6_REVIEW_CANDIDATES")) -> dict:
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in sorted(root.rglob("*"))
            if p.is_file() and not any(s in p.parts for s in skip)}


def guard_home() -> Path:
    home = Path(os.environ.get("HERMES_HOME", "")).resolve()
    if home != DISPOSABLE_HOME.resolve():
        raise SystemExit("Refusing: HERMES_HOME must be the disposable P6 home " + str(DISPOSABLE_HOME))
    return home


def identity() -> dict:
    commit = subprocess.run(["git", "-C", str(HERMES_SRC), "rev-parse", "HEAD"], capture_output=True,
                            text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(HERMES_SRC), "status", "--porcelain"], capture_output=True,
                           text=True, check=True).stdout.strip()
    return {"hermes_commit": commit, "hermes_src_dirty": bool(dirty), "python": sys.version.split()[0],
            "executable": sys.executable, "matches_registry_target": commit == EXPECTED_COMMIT and not dirty}


def config_plugins(home: Path) -> dict:
    sys.path.insert(0, str(HERMES_SRC))
    from hermes_cli.plugins_discovery import _get_disabled_plugins, _get_enabled_plugins
    return {"enabled": sorted(_get_enabled_plugins() or []), "disabled": sorted(_get_disabled_plugins() or [])}


def preflight(home: Path) -> dict:
    cfg = config_plugins(home)
    installed = (home / "plugins" / PLUGIN).exists()
    return {"mode": "preflight", "identity": identity(), "plugins_config": cfg,
            "foreign_plugin_dir_present": installed,
            "foreign_plugin_enabled": PLUGIN in cfg["enabled"],
            "ok": not installed and PLUGIN not in cfg["enabled"], "model_calls": 0}


def verify(home: Path) -> dict:
    sys.path.insert(0, str(HERMES_SRC))
    from hermes_cli.plugins import discover_plugins, get_plugin_manager
    from tools.skills_tool import skill_view
    from agent.skill_commands import build_skill_invocation_message, get_interactive_skill_commands

    gates, checks = {}, []

    def check(gate, cid, ok, observed):
        checks.append({"gate": gate, "id": cid, "result": "PASS" if ok else "FAIL", "observed": observed})

    inst = home / "plugins" / PLUGIN
    staged, installed = tree(STAGE), tree(inst)
    check("STRUCTURAL", "S1-installed-bytes-equal-validated-stage", staged == installed,
          {"files": len(installed), "differences": sorted(set(staged.items()) ^ set(installed.items()))[:10]})

    discover_plugins(force=True)
    pm = get_plugin_manager()
    meta = {m["name"]: m for m in pm.list_plugin_skill_metadata()}
    ours = sorted(n for n in meta if n.startswith(PLUGIN + ":"))
    check("RESOLUTION", "R1-namespaced-registration", len(ours) == 8, {"qualified": ours})
    commands = get_interactive_skill_commands()
    check("RESOLUTION", "R2-no-bare-name-shadowing", all(("/" + s) not in commands or
          commands["/" + s].get("source") != "plugin" for s in PILOT),
          {s: commands.get("/" + s, {}).get("source") for s in PILOT})
    for s in PILOT:
        q = PLUGIN + ":" + s
        md = inst / "skills" / s / "SKILL.md"
        view = json.loads(skill_view(q, preprocess=True))
        body = md.read_text(encoding="utf-8")
        check("RESOLUTION", "R3-skill_view:" + s, bool(view.get("success")) and view.get("content", "").endswith(body)
              and Path(view.get("skill_dir", "")).resolve() == md.parent.resolve(),
              {"success": view.get("success"), "name": view.get("name"), "skill_dir": view.get("skill_dir"),
               "content_sha256": sha(view.get("content", "").encode("utf-8")),
               "body_is_suffix": view.get("content", "").endswith(body),
               "prefix_banner": view.get("content", "")[:len(view.get("content", "")) - len(body)][:300]})
        res = json.loads(skill_view(q, file_path="../../CONNECTORS.md"))
        check("RESOLUTION", "R4-relative-resource-refused:" + s, res.get("success") is not True,
              {"response": {k: res.get(k) for k in ("success", "error")},
               "on_disk_target_exists": (md.parent / "../../CONNECTORS.md").resolve().is_file()})
        key = "/" + q.lower()
        msg = build_skill_invocation_message(key, ARG, task_id="p6-runtime-verify") if key in commands else None
        check("RESOLUTION", "R5-slash-argument-delivery:" + s,
              msg is not None and msg.rstrip().endswith(MARKER + ARG) and body.strip() in msg,
              {"key_present": key in commands, "ends_with_instruction": bool(msg and msg.rstrip().endswith(MARKER + ARG)),
               "body_verbatim_inside": bool(msg and body.strip() in msg),
               "literal_ARGUMENTS_still_in_body": "$ARGUMENTS" in body,
               "message_sha256": sha(msg.encode("utf-8")) if msg else None})
    for g in ("STRUCTURAL", "RESOLUTION"):
        rows = [c for c in checks if c["gate"] == g]
        gates[g] = "PASS" if rows and all(c["result"] == "PASS" for c in rows) else "FAIL"
    gates["SEMANTIC"] = "NOT_TESTED"
    return {"mode": "verify", "identity": identity(), "plugins_config": config_plugins(home),
            "gates": gates, "checks": checks, "model_calls": 0,
            "notes": ["build_skill_invocation_message bumps Hermes skill-usage counters in the disposable home.",
                      "No agent turn, model call or tool execution was started."]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["preflight", "verify"])
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    out = Path(args.output)
    if out.exists():
        raise SystemExit("Output exists; refusing to overwrite")
    home = guard_home()
    result = preflight(home) if args.mode == "preflight" else verify(home)
    data = (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    out.write_bytes(data)
    summary = {"output": str(out), "sha256": sha(data), "model_calls": 0}
    summary.update({"ok": result.get("ok")} if args.mode == "preflight" else {"gates": result["gates"]})
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
