"""Operator CLI for the P6 deterministic compatibility engine. No model calls.

  python compat_cli.py map --stage STAGE_DIR --output NEW_EVIDENCE_DIR [--target-identity hermes-agent@SHA]
  python compat_cli.py check-candidates --stage STAGE_DIR

`map` reads the stage only and writes mapped review candidates plus
COMPAT_REPORT.json/.md into a NEW directory outside the stage. Nothing is
applied, installed, enabled or executed. AI fallback is not reachable here.
"""
from __future__ import annotations

import argparse
import json
import sys

from compat_engine import PortError, default_identity, load_registry, map_stage


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P6 deterministic mapping (read-only on the stage)")
    sub = ap.add_subparsers(dest="action", required=True)
    m = sub.add_parser("map")
    m.add_argument("--stage", required=True)
    m.add_argument("--output", required=True)
    m.add_argument("--target-identity")
    c = sub.add_parser("check-candidates")
    c.add_argument("--stage", required=True)
    args = ap.parse_args(argv)
    try:
        registry = load_registry()
        identity = default_identity(registry)
        if getattr(args, "target_identity", None):
            identity["target"] = args.target_identity
        if args.action == "map":
            rep = map_stage(args.stage, args.output, registry=registry, identity=identity)
            print(json.dumps({"status": "WRITTEN", "output": args.output, "counts": rep["counts"],
                              "model_calls": rep["model_calls"], "rules_applied": rep["rules_applied"]}, indent=2))
        else:
            rep = map_stage(args.stage, None, registry=registry, identity=identity)
            print(json.dumps([{k: c[k] for k in ("skill", "candidate_sha256", "verdict", "independent_verdict", "blocking")}
                              for c in rep["existing_review_candidates"]], indent=2, ensure_ascii=False))
        return 0
    except (PortError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "BLOCKED", "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
