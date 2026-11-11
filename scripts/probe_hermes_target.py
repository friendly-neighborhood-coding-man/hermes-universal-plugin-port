"""Offline behavioral probe of a LOCAL Hermes source checkout (no model, no network).

Produces target-side validation evidence for the P6 compatibility-rule registry
(`compat_rules.json`). It imports a handful of pure Hermes functions from the
checkout, runs fixed cases, and records the checkout commit, the SHA-256 of
every probed Hermes source file, and each case result.

Scope limits (recorded in the output):
- This probes Hermes *source functions* at one commit. It is not a Hermes
  session, does not load any plugin, and does not prove the installed Hermes
  binary has the same behavior.
- `source_assertion` cases only check that an exact line is present in the
  probed file; they are code review evidence, not behavior.

Usage (operator):
  python -I scripts/probe_hermes_target.py --hermes-src D:\\Hermes-Lab\\hermes-agent \
      --output semantics/hermes_target_probe.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCHEMA = "universal-port.hermes-target-probe/1"
PROBED_FILES = (
    "agent/skill_preprocessing.py",
    "agent/skill_commands.py",
    "agent/skill_utils.py",
    "tools/path_security.py",
    "tools/skills_tool_plugin.py",
)
PASSTHROUGH_FIXTURES = (
    "Plain Markdown line with no host tokens.\n",
    "```\n/write-spec $ARGUMENTS\n```\n",
    "If **~~project tracker** is connected:\n",
    "See [CONNECTORS.md](../../CONNECTORS.md).\n",
    "Root ${CLAUDE_PLUGIN_ROOT} and dir ${CLAUDE_SKILL_DIR}.\n",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _commit(src: Path) -> str:
    out = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    value = out.stdout.strip()
    if len(value) != 40:
        raise SystemExit("Could not read Hermes checkout commit")
    return value


def _dirty(src: Path) -> bool:
    out = subprocess.run(["git", "-C", str(src), "status", "--porcelain", "--"] + list(PROBED_FILES),
                         capture_output=True, text=True, check=True)
    return bool(out.stdout.strip())


def run(src: Path) -> dict:
    sys.path.insert(0, str(src))
    from agent.skill_preprocessing import preprocess_skill_content, substitute_template_vars
    from agent.skill_commands import append_user_instruction
    from agent.skill_utils import parse_qualified_name
    from tools.path_security import has_traversal_component

    cases = []

    def case(cid, kind, ok, observed):
        cases.append({"id": cid, "kind": kind, "result": "PASS" if ok else "FAIL",
                      "observed": observed})

    cfg = {"template_vars": True, "inline_shell": False}
    same = [preprocess_skill_content(t, Path("SKILLDIR"), "SID", skills_cfg=cfg) == t
            for t in PASSTHROUGH_FIXTURES]
    case("H-PASSTHROUGH-1", "behavioral", all(same),
         {"fixtures": len(PASSTHROUGH_FIXTURES), "unchanged": sum(same),
          "note": "preprocess_skill_content with template_vars on, inline_shell off"})

    sub = substitute_template_vars("A ${HERMES_SKILL_DIR} B", Path("SKILLDIR"), "SID")
    case("H-TEMPLATE-VARS-1", "behavioral", sub == "A SKILLDIR B",
         {"output": sub, "note": "Hermes DOES rewrite ${HERMES_*} tokens; literal ones in foreign text collide"})

    kept = substitute_template_vars("x $ARGUMENTS y", None, None)
    case("H-NO-ARGUMENTS-SUBST-1", "behavioral", kept == "x $ARGUMENTS y",
         {"output": kept, "note": "Hermes has no $ARGUMENTS substitution"})

    parts = ["NOTE", "", "BODY"]
    append_user_instruction(parts, "SSO support")
    msg = "\n".join(parts)
    marker = "The user has provided the following instruction alongside the skill invocation: "
    case("H-INSTRUCTION-APPEND-1", "behavioral",
         msg.startswith("NOTE\n\nBODY\n") and msg.endswith(marker + "SSO support"),
         {"message": msg, "marker": marker})

    case("H-QUALIFIED-NAME-1", "behavioral",
         parse_qualified_name("ported-product-management:write-spec") == ("ported-product-management", "write-spec"),
         {"input": "ported-product-management:write-spec"})

    case("H-SKILL-VIEW-TRAVERSAL-1", "behavioral",
         has_traversal_component("../../CONNECTORS.md") is True,
         {"input": "../../CONNECTORS.md",
          "note": "skill_view(file_path=...) refuses any '..' component"})

    assertions = (
        ("H-PLUGIN-SLASH-KEY-1", "agent/skill_commands.py", 'key = f"/{qualified.lower()}"'),
        ("H-INLINE-SHELL-DEFAULT-OFF-1", "agent/skill_preprocessing.py", 'cfg.get("inline_shell", False)'),
        ("H-PLUGIN-SKILL-FILE-TRAVERSAL-1", "tools/skills_tool_plugin.py", "if has_traversal_component(file_path):"),
    )
    for cid, rel, needle in assertions:
        text = (src / rel).read_text(encoding="utf-8")
        case(cid, "source_assertion", needle in text, {"file": rel, "needle": needle})

    commit = _commit(src)
    return {
        "schema": SCHEMA,
        "target_identity": "hermes-agent@" + commit,
        "hermes_commit": commit,
        "probed_files_dirty": _dirty(src),
        "probed_files": {rel: _sha((src / rel).read_bytes()) for rel in PROBED_FILES},
        "cases": cases,
        "model_calls": 0,
        "network_access": False,
        "limitations": [
            "Probes Hermes source functions at one commit; not a Hermes session.",
            "No plugin was loaded; plugin registration and skill_view were not executed.",
            "Installed Hermes binary version was not compared to this checkout.",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes-src", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    result = run(Path(args.hermes_src).resolve())
    data = (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    out = Path(args.output)
    out.write_bytes(data)
    print(json.dumps({"output": str(out), "sha256": _sha(data),
                      "failed": [c["id"] for c in result["cases"] if c["result"] != "PASS"]}))
    return 0 if all(c["result"] == "PASS" for c in result["cases"]) else 1


if __name__ == "__main__":
    sys.exit(main())
