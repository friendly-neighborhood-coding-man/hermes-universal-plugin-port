"""P1: consume Hermes's existing progressive-disclosure skills_list JSON.

This module performs no filesystem scanning, skill loading, network calls,
registration, installation, model inference or permission changes.

Official Hermes skills_list exposes currently visible skill names. We only
use that evidence to *remove* stale/missing route candidates, never to grant
approval, verify runtime semantics, or manufacture new capabilities.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy

if __package__:
    from .uvp_routing import RoutingError
else:
    from uvp_routing import RoutingError

CATALOG_SCHEMA = "universal-port.observed-skill-catalog/1"
MAX_SKILLS = 512
MAX_CATALOG_BYTES = 262144
# Real Hermes load names can be nested paths or plugin-qualified.
SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}$")


def parse_skills_list(payload: str | dict) -> dict:
    """Validate a *snapshot*, not a claim of safety or runtime equivalence."""
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAX_CATALOG_BYTES:
            raise RoutingError("Hermes skill listing oversized")
        try:
            payload = json.loads(payload)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RoutingError("Invalid Hermes skill listing JSON") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RoutingError("Hermes skill listing unavailable or unsuccessful")
    rows = payload.get("skills")
    if not isinstance(rows, list) or len(rows) > MAX_SKILLS:
        raise RoutingError("Invalid Hermes skill listing")
    names = set()
    for item in rows:
        if not isinstance(item, dict):
            raise RoutingError("Malformed Hermes skill metadata")
        name = item.get("name")
        if not isinstance(name, str) or not SKILL_NAME.fullmatch(name) or name in names:
            raise RoutingError("Invalid or duplicate Hermes skill name")
        names.add(name)
    return {"schema": CATALOG_SCHEMA, "count": len(names), "names": sorted(names),
            "origin": "hermes.skills_list", "execution_performed": False,
            "runtime_semantics_verified": False}


def audit_skill_route(plan: dict, catalog: dict) -> dict:
    """Fail closed for Hermes Skill plans that disappeared from live catalog.

    Other kinds (Hermes tools / UVP adapters) are not certified by a skills
    catalog and stay marked as requiring their own separate live binding check.
    """
    if not isinstance(plan, dict) or plan.get("schema") != "universal-port.route-plan/1":
        raise RoutingError("Unknown route plan")
    if not isinstance(catalog, dict) or catalog.get("schema") != CATALOG_SCHEMA:
        raise RoutingError("Unknown observed skills catalog")
    names = catalog.get("names")
    if (not isinstance(names, list) or len(names) > MAX_SKILLS
            or any(not isinstance(n, str) or not SKILL_NAME.fullmatch(n) for n in names)
            or len(set(names)) != len(names)):
        raise RoutingError("Malformed observed skill catalog")
    if not isinstance(plan.get("selected"), list) or not isinstance(plan.get("unavailable"), list):
        raise RoutingError("Malformed route plan")
    result = deepcopy(plan)
    result["catalog_audit"] = {"skills_seen": len(names), "missing": [],
                               "other_bindings_unchecked": [],
                               "source": catalog.get("origin", "unknown")}
    observed = set(names)
    keep = []
    for choice in result["selected"]:
        if not isinstance(choice, dict):
            raise RoutingError("Malformed route selection")
        kind = choice.get("kind")
        invocation = choice.get("invocation")
        if kind == "hermes_skill":
            skill_name = invocation[1:] if isinstance(invocation, str) and invocation.startswith("/") else None
            if skill_name in observed:
                keep.append(choice)
            else:
                result["catalog_audit"]["missing"].append(choice.get("capability_id"))
                result["unavailable"].append({
                    "domain": choice.get("domain"),
                    "fallback": "VANILLA_RECOMMENDED",
                    "blocked": [{"capability_id": choice.get("capability_id"),
                                 "reason": "NOT_DISCOVERED_IN_HERMES_SKILLS_LIST"}],
                })
        else:
            # The skill catalog cannot attest a plugin tool or an adapter binding.
            result["catalog_audit"]["other_bindings_unchecked"].append(choice.get("capability_id"))
            keep.append(choice)
    result["selected"] = keep
    result["execution_performed"] = False
    if result["catalog_audit"]["missing"]:
        result["status"] = "PLAN_INCOMPLETE"
        result["reason"] = "A previously selected Skill is absent from this Hermes skill catalog"
    elif result["catalog_audit"]["other_bindings_unchecked"] and result.get("status") == "PLAN_READY":
        result["status"] = "LIVE_BINDING_REQUIRED"
        result["reason"] = "Non-Skill bindings require independent live verification"
    result["composition"] = len(keep) > 1
    return result
