"""Offline preview command for UVP's experimental routing core.

Does not run Hermes or external commands, change settings, or enable plugins.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from uvp_routing import RoutingError, load_policy, load_registry, route_request
from uvp_discovery import parse_skills_list, audit_skill_route


ROOT = Path(__file__).resolve().parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preview UVP domain routing without execution")
    parser.add_argument("--prompt", required=True, help="Request text (avoid secrets in shell history)")
    parser.add_argument("--policy", type=Path,
                        default=ROOT / "examples" / "uvp-routing-policy.json")
    parser.add_argument("--registry", type=Path,
                        default=ROOT / "examples" / "uvp-routing-registry.json")
    parser.add_argument("--skills-list", type=Path, default=None,
                        help="Saved JSON output from Hermes skills_list() (offline audit)")
    args = parser.parse_args(argv)
    try:
        result = route_request(
            args.prompt, load_policy(args.policy), load_registry(args.registry))
        if args.skills_list is not None:
            if args.skills_list.is_symlink() or args.skills_list.stat().st_size > 262144:
                raise RoutingError("Invalid skills-list snapshot file")
            catalog = parse_skills_list(args.skills_list.read_text(encoding="utf-8"))
            result = audit_skill_route(result, catalog)
    except (RoutingError, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, RoutingError) else "Could not read offline skill snapshot"
        print(json.dumps({"ok": False, "error": message, "execution_performed": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
