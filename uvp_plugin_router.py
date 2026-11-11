"""Hermes UVP slash command and preview-only uvp_route tool.

Only an explicit CLI slash command --arxiv-execute can attempt bounded
network access, under extra environment, digest and Hermes choice gates.
The model-visible uvp_route remains advisory and cannot execute skills.
"""
from __future__ import annotations

import json
from pathlib import Path

from .uvp_routing import RoutingError, load_policy, load_registry, route_request

_ROOT = Path(__file__).resolve().parent
_POLICY = _ROOT / "examples" / "uvp-routing-policy.json"
_REGISTRY = _ROOT / "examples" / "uvp-routing-registry.json"
_USAGE = ("Usage: /uvp <task> | --p6-defaults | --p6-defaults-undo | --p6-preflight | --p6-recipe <fixture-path> | --p6-adapt <skill> <stage> --approve-model-call | --p6-apply <skill> <sha> <stage> --approve-reviewed | --candidates <task> | --arxiv-plan <id> "
          "| --surface | --arxiv-execute <versioned-id> <request-sha256> "
          "(execution requires local TUI/CLI consent and is disabled by default)")


def preview(prompt: str) -> dict:
    """Make a routing plan from shipped, conservative default configs."""
    return route_request(prompt, load_policy(_POLICY), load_registry(_REGISTRY))


def slash_handler(raw: str = "") -> str:
    if not isinstance(raw, str) or not raw.strip():
        return _USAGE
    try:
        report = preview(raw)
    except (RoutingError, OSError, UnicodeError, TypeError, ValueError):
        return "UVP ROUTE ERROR: invalid or unavailable policy/registry; no execution occurred."
    return "UVP route preview (NOT EXECUTED):\n" + json.dumps(report, ensure_ascii=False, indent=2)


def tool_handler(args: dict, **_kwargs) -> str:
    """Strict tool input. Do not repeat user prompts or credentials in errors."""
    try:
        if not isinstance(args, dict) or set(args) != {"prompt"}:
            raise RoutingError("Invalid arguments")
        report = preview(args["prompt"])
        return json.dumps(report, ensure_ascii=False)
    except (RoutingError, OSError, UnicodeError, TypeError, ValueError):
        return json.dumps({
            "ok": False,
            "error": "Routing input or configuration invalid",
            "execution_performed": False,
        })


def register_router(ctx) -> None:
    # Candidate catalog lookup is deliberately user-triggered, never implicit.
    # It uses the host's official skills_list tool, not imported SKILL.md content.
    def command(raw: str = "", *, platform: str | None = None,
                source=None, session_id: str = "", session_key: str = "") -> str:
        if raw == "--p6-preflight":
            from .uvp_discovery import parse_skills_list
            from .uvp_p6_defaults import DOMAINS, PLUGIN
            try:
                listing = parse_skills_list(ctx.dispatch_tool("skills_list", {}))
                names = listing["names"]
                expected = [f"{PLUGIN}:{skill}" for _, skill in DOMAINS]
                collisions = [n for n in names
                              if n.split(":")[-1] in {s for _, s in DOMAINS}]
                status = ("ALREADY_INSTALLED" if all(e in names for e in expected)
                          else "REVIEW_NAME_COLLISIONS" if collisions
                          else "NO_EXACT_NAME_COLLISIONS_SEEN")
                report = {
                    "schema": "universal-port.p6-host-preflight/1",
                    "status": status,
                    "matched_skill_names": collisions,
                    "names_examined": len(names),
                    "semantic_equivalence_verified": False,
                    "installation_performed": False,
                    "execution_performed": False,
                }
            except Exception:
                report = {"status": "HOST_CATALOG_UNAVAILABLE",
                          "installation_performed": False,
                          "execution_performed": False}
            return "UVP P6 host Skill preflight (NOT EXECUTED):\n" + json.dumps(
                report, ensure_ascii=False, indent=2)
        if isinstance(raw, str) and raw.startswith("--p6-recipe "):
            from .uvp_p6_recipe import recipe
            # Pure prompt generation: no model call or skill_view execution.
            result = recipe(ctx, raw[len("--p6-recipe "):].strip())
            return "UVP P6 three-Skill recipe (NOT EXECUTED):\n" + json.dumps(
                result, ensure_ascii=False, indent=2)
        if isinstance(raw, str) and raw.startswith("--p6-adapt "):
            from .uvp_p6_defaults import _check_local
            from .uvp_p6_patch import propose
            from .port_core import PortError
            if not _check_local(ctx, source=source, platform=platform,
                                session_id=session_id, session_key=session_key):
                return "UVP P6 PATCH BLOCKED: local operator session required"
            if not raw.endswith(" --approve-model-call"):
                return "Usage: /uvp --p6-adapt <skill> <staged-path> --approve-model-call"
            command_args = raw[:-len(" --approve-model-call")].split(None, 2)
            if len(command_args) != 3:
                return "Usage: /uvp --p6-adapt <skill> <staged-path> --approve-model-call"
            try:
                result = propose(ctx, command_args[2], command_args[1])
            except (PortError, OSError, ValueError):
                return "UVP P6 PATCH BLOCKED: invalid stage, review state or source"
            return "UVP P6 AI patch (CANDIDATE ONLY):\n" + json.dumps(
                result, ensure_ascii=False, indent=2)
        if isinstance(raw, str) and raw.startswith("--p6-apply "):
            from .uvp_p6_defaults import _check_local
            from .uvp_p6_patch import apply_reviewed
            from .port_core import PortError
            if not _check_local(ctx, source=source, platform=platform,
                                session_id=session_id, session_key=session_key):
                return "UVP P6 APPLY BLOCKED: local operator session required"
            if not raw.endswith(" --approve-reviewed"):
                return "Usage: /uvp --p6-apply <skill> <candidate-sha256> <staged-path> --approve-reviewed"
            values = raw[:-len(" --approve-reviewed")].split(None, 3)
            if len(values) != 4 or len(values[2]) != 64:
                return "Usage: /uvp --p6-apply <skill> <candidate-sha256> <staged-path> --approve-reviewed"
            try:
                consent = ctx.ask_choice(
                    "Apply the separately reviewed P6 candidate " + values[1] +
                    " with SHA256 " + values[2] + " to the STAGED skill only? "
                    "No Hermes installation or execution will occur.",
                    [{"value": "apply", "label": "Apply reviewed candidate to stage"},
                     {"value": "deny", "label": "Do not apply"}],
                )
            except Exception:
                consent = None
            if consent != "apply":
                return "UVP P6 APPLY BLOCKED: fresh approval absent"
            try:
                result = apply_reviewed(values[3], values[1], values[2], approved=True)
            except (PortError, OSError, ValueError):
                return "UVP P6 APPLY BLOCKED: candidate/sha/source mismatch"
            return "UVP P6 staged patch (NOT INSTALLED):\n" + json.dumps(
                result, ensure_ascii=False, indent=2)
        if raw in {"--p6-defaults", "--p6-defaults-undo"}:
            from .uvp_p6_defaults import propose_domain_defaults, undo_last_defaults
            fn = (propose_domain_defaults if raw == "--p6-defaults"
                  else undo_last_defaults)
            result = fn(
                ctx, source=source, platform=platform,
                session_id=session_id, session_key=session_key,
            )
            return "UVP P6 domain preferences (NO SKILL EXECUTION):\n" + json.dumps(
                result, ensure_ascii=False, indent=2)
        if isinstance(raw, str) and raw.startswith("--candidates "):
            from .uvp_candidates import candidates_from_hermes
            try:
                report = candidates_from_hermes(ctx, raw[len("--candidates "):])
            except (RoutingError, OSError, UnicodeError, TypeError, ValueError):
                return "UVP CANDIDATES ERROR: host catalog unavailable; nothing was executed."
            return "UVP Skill candidates (UNAPPROVED; NOT EXECUTED):\n" + json.dumps(
                report, ensure_ascii=False, indent=2)
        if isinstance(raw, str) and raw.startswith("--arxiv-plan "):
            from .uvp_arxiv_p4 import prepare, P4Error
            try:
                report = prepare(raw[len("--arxiv-plan "):].strip())
            except P4Error:
                return "UVP ARXIV PLAN ERROR: expected one version-pinned ID, e.g. 1706.03762v1."
            return "UVP arXiv request preview (APPROVAL REQUIRED; NOT EXECUTED):\n" + json.dumps(
                report, ensure_ascii=False, indent=2)
        if raw == "--surface":
            from .uvp_arxiv_p5 import ALLOWED_SURFACES, ENV_ENABLE, validate_host_local_context
            import os
            # Slash command dispatch supplies platform=source.platform.value.
            # For local gateway sessions that can be the generic "local",
            # *not* the concrete "tui" or "cli" expected by session_surface.
            # These values are diagnostic ONLY and never grant execution.
            try:
                surface = ctx.session_surface()
                if surface == "":
                    lookup = "empty"
                elif surface == "local":
                    lookup = "generic_local"
                elif surface in {"cli", "tui", "desktop", "acp",
                                 "telegram", "discord", "slack"}:
                    lookup = "recognized"
                else:
                    lookup = "unrecognized"
            except Exception:
                surface = None
                lookup = "exception"
            # Sanitize labels and NEVER include session IDs or source objects.
            surface_label = surface if lookup in {"recognized", "generic_local"} else "unknown"
            host_platform = platform if platform in {
                "local", "telegram", "discord", "slack", "api_server",
            } else "unavailable_or_other"
            host_verified, host_reason = validate_host_local_context(
                source=source, platform=platform,
                session_id=session_id, session_key=session_key,
            )
            local = surface in ALLOWED_SURFACES or (surface == "local" and host_verified)
            return "UVP session diagnostic (NOT EXECUTED):\n" + json.dumps({
                "schema": "universal-port.session-diagnostic/3",
                "session_surface": surface_label,
                "session_surface_lookup": lookup,
                "host_dispatch_platform": host_platform,
                "host_local_source_verified": host_verified,
                "host_context_status": host_reason,
                "session_id_present": bool(isinstance(session_id, str) and session_id.strip()),
                "session_key_present": bool(isinstance(session_key, str) and session_key.strip()),
                "local_surface_permitted": local,
                "live_execution_opt_in": local and os.environ.get(ENV_ENABLE) == "1",
                "execution_performed": False,
            }, ensure_ascii=False, indent=2)
        if isinstance(raw, str) and raw.startswith("--arxiv-execute"):
            from .uvp_arxiv_p5 import run_with_choice
            parts = raw.split()
            if len(parts) != 3 or parts[0] != "--arxiv-execute":
                return "Usage: /uvp --arxiv-execute <versioned-id> <exact-plan-sha256> (CLI approval required)"
            report = run_with_choice(
                ctx, parts[1], parts[2],
                source=source, platform=platform,
                session_id=session_id, session_key=session_key,
            )
            return "UVP Hermes arXiv bounded execution gate:\n" + json.dumps(
                report, ensure_ascii=False, indent=2)
        return slash_handler(raw)

    ctx.register_command(
        "uvp",
        handler=command,
        description="Preview routing, discover candidates, or operator-gated arXiv single lookup",
        args_hint="<task> | --p6-defaults | --p6-defaults-undo | --surface | --candidates <task> | --arxiv-plan <id> | --arxiv-execute <id> <sha256>",
    )
    ctx.register_tool(
        name="uvp_route",
        toolset="universal_port",
        schema={
            "name": "uvp_route",
            "description": (
                "Advisory only: classify a task and propose operator-approved "
                "domain-default capabilities. No skills, tools or external "
                "agents are executed. Empty registry yields incomplete plans."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Task to classify"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        handler=tool_handler,
    )
