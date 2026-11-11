"""Operator CLI for the P6.7 semantic review loop. Deterministic evaluator only; no model calls.

  python semantic_review_cli.py --stage STAGE --run-dir RUN_DIR --verify VERIFY_JSON --output NEW_DIR [--test-candidates]
"""
from __future__ import annotations

import argparse
import json
import sys

from semantic_review import PortError, review, write_review


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P6.7 evidence-grounded semantic review (no model calls)")
    ap.add_argument("--stage", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--verify", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--test-candidates", action="store_true",
                    help="apply code candidates to a throwaway copy and run their offline tests")
    a = ap.parse_args(argv)
    try:
        r = review(stage=a.stage, run_dir=a.run_dir, verify_json=a.verify, run_candidate_tests=a.test_candidates)
        write_review(r, a.output)
        print(json.dumps({"output": a.output, "model_calls": r["model_calls"], "applied": r["applied"],
                          "verdicts": {f["obligation_id"]: [f["verdict"], f["root_cause"], f["disposition"]] for f in r["findings"]},
                          "candidates": [c["id"] for c in r["candidates"]]}, indent=2))
        return 0
    except (PortError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "status": "BLOCKED", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
