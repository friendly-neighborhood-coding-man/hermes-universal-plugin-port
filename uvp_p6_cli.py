"""Operator-only P6 source fetch + inert skill staging; never installs or runs.

Commands:
  python uvp_p6_cli.py fetch --output SOURCE_DIR --confirm P6_FETCH_PINNED_SOURCE
  python uvp_p6_cli.py stage --source PINNED_SOURCE_PATH --output STAGE_DIR \
      --commit FULL_SHA --confirm P6_STAGE_SKILLS_ONLY_PARTIAL
"""
from __future__ import annotations

import argparse
import json
import sys

from port_core import PortError, fetch_github
from uvp_p6_stage import stage_claude_skill_bundle

UPSTREAM_COMMIT = "e605d8ddbfb688da57dfaaceebd93f12a64ef1d3"
SOURCE_URL = (
    "https://github.com/anthropics/knowledge-work-plugins/"
    f"tree/{UPSTREAM_COMMIT}/product-management"
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="P6 inert source staging (no install)")
    sub = parser.add_subparsers(dest="action", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--output", required=True)
    fetch.add_argument("--confirm", required=True)

    stage = sub.add_parser("stage")
    stage.add_argument("--source", required=True)
    stage.add_argument("--output", required=True)
    stage.add_argument("--commit", required=True)
    stage.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "fetch":
            if args.confirm != "P6_FETCH_PINNED_SOURCE":
                raise PortError("Explicit fetch confirmation missing")
            result = fetch_github(SOURCE_URL, args.output, approved=True)
            if result.get("commit_sha") != UPSTREAM_COMMIT:
                raise PortError("Fetched source did not match pinned revision")
        else:
            if args.confirm != "P6_STAGE_SKILLS_ONLY_PARTIAL":
                raise PortError("Explicit SKILLS_ONLY_PARTIAL approval missing")
            if args.commit != UPSTREAM_COMMIT:
                raise PortError("Wrong pinned pilot revision")
            result = stage_claude_skill_bundle(
                args.source, args.output,
                approved=True, allow_partial=True,
                declared_source_commit=args.commit,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PortError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "BLOCKED",
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
