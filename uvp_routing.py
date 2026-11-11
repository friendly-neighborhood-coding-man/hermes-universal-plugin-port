"""UVP v0.5 experimental routing core: deterministic, advisory, fail-closed.

This module does NOT load plugins, invoke tools, inject messages, port code,
grant permissions or infer semantic equivalence. The operator-owned registry
is an input; arbitrary plugin metadata must never be treated as approval.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REGISTRY_SCHEMA = "universal-port.routing-registry/1"
POLICY_SCHEMA = "universal-port.routing-policy/1"
MAX_PROMPT_CHARS = 8192
MAX_CAPABILITIES = 128
MAX_DOMAINS_PER_PLAN = 2
SAFE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
INVOCATION = re.compile(r"^(?:/[a-z][a-z0-9_-]{0,79}|tool:[a-z][a-z0-9_.-]{0,79})$")
KINDS = frozenset({"hermes_skill", "hermes_tool", "uvp_adapter"})
PERMISSIONS = frozenset({"read", "write", "network", "execute", "external_send"})

# These patterns are only an inexpensive candidate filter, NOT semantic understanding.
# English words require boundaries; Korean phrases are substring matches.
DOMAIN_PATTERNS = {
    "research": (r"\b(?:research|papers?|literature|citations?|studies)\b", r"논문|연구|문헌|학술"),
    "coding": (r"\b(?:code|coding|bugs?|debug|implement|refactor|tests?)\b", r"코드|버그|구현|개발|테스트|리팩터"),
    "data": (r"\b(?:data|dataset|csv|spreadsheet|statistics|plot|chart)\b", r"데이터|통계|그래프|시각화|스프레드시트"),
    "browser": (r"\b(?:browser|browse|navigate|website|webpage)\b", r"브라우저|웹사이트|웹페이지|사이트 탐색"),
    "documents": (r"\b(?:document|docx|pdf|report|presentation|slides)\b", r"문서|보고서|발표자료|슬라이드"),
}


class RoutingError(ValueError):
    """Malformed input or untrusted routing metadata."""


def _read_json(path: Path) -> dict:
    """Read local operator-maintained data; never follow symlink files."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise RoutingError("Routing configuration missing, linked or oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, OSError, json.JSONDecodeError) as exc:
        raise RoutingError("Invalid routing configuration JSON") from exc
    if not isinstance(value, dict):
        raise RoutingError("Routing configuration must be an object")
    return value


def load_policy(path: Path) -> dict:
    policy = _read_json(path)
    validate_policy(policy)
    return policy


def load_registry(path: Path) -> dict:
    registry = _read_json(path)
    validate_registry(registry)
    return registry


def _valid_id(value) -> bool:
    return isinstance(value, str) and bool(SAFE_ID.fullmatch(value))


def validate_policy(policy: dict) -> None:
    if not isinstance(policy, dict) or set(policy) != {"schema", "domains"} or policy["schema"] != POLICY_SCHEMA:
        raise RoutingError("Unrecognized routing policy schema")
    domains = policy["domains"]
    if not isinstance(domains, dict) or set(domains) != set(DOMAIN_PATTERNS):
        raise RoutingError("Policy must explicitly configure all supported domains")
    for domain, config in domains.items():
        if not isinstance(config, dict) or set(config) != {"preferred", "fallbacks", "allow_vanilla"}:
            raise RoutingError("Invalid domain policy: " + domain)
        selected = [config["preferred"], *config["fallbacks"]] if isinstance(config["fallbacks"], list) else []
        if (not isinstance(config["fallbacks"], list) or len(config["fallbacks"]) > 8
                or not all(_valid_id(x) for x in selected)
                or len(selected) != len(set(selected))
                or not isinstance(config["allow_vanilla"], bool)):
            raise RoutingError("Invalid preferred/fallback routing entries: " + domain)


def validate_registry(registry: dict) -> None:
    if not isinstance(registry, dict) or set(registry) != {"schema", "capabilities"} or registry["schema"] != REGISTRY_SCHEMA:
        raise RoutingError("Unrecognized capability routing registry schema")
    entries = registry["capabilities"]
    if not isinstance(entries, list) or len(entries) > MAX_CAPABILITIES:
        raise RoutingError("Invalid capability count")
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {
            "id", "domain", "kind", "invocation", "approved", "runtime_verified",
            "evidence_sha256", "permissions"
        }:
            raise RoutingError("Malformed capability entry")
        cap_id = item["id"]
        if not _valid_id(cap_id) or cap_id in seen or item["domain"] not in DOMAIN_PATTERNS:
            raise RoutingError("Invalid, duplicate or unknown capability")
        seen.add(cap_id)
        if item["kind"] not in KINDS or not isinstance(item["invocation"], str) or not INVOCATION.fullmatch(item["invocation"]):
            raise RoutingError("Invalid capability invocation")
        if not isinstance(item["approved"], bool) or not isinstance(item["runtime_verified"], bool):
            raise RoutingError("Approval and verification must be booleans")
        evidence = item["evidence_sha256"]
        if evidence is not None and (not isinstance(evidence, str) or not SHA256.fullmatch(evidence)):
            raise RoutingError("Malformed evidence SHA-256")
        if item["runtime_verified"] and evidence is None:
            raise RoutingError("Runtime verification requires evidence SHA-256")
        permissions = item["permissions"]
        if (not isinstance(permissions, list) or not permissions or len(permissions) != len(set(permissions))
                or not all(isinstance(p, str) and p in PERMISSIONS for p in permissions)):
            raise RoutingError("Invalid capability permissions")


def classify_domains(prompt: str) -> list[str]:
    """Return candidate domains in first-mention order. Not a semantic oracle."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise RoutingError("Prompt missing or too large")
    found = []
    for domain, patterns in DOMAIN_PATTERNS.items():
        positions = [hit.start() for pattern in patterns for hit in re.finditer(pattern, prompt, re.I)]
        if positions:
            found.append((min(positions), domain))
    return [domain for _, domain in sorted(found)]


def route_request(prompt: str, policy: dict, registry: dict) -> dict:
    """Return a route recommendation ONLY. Never dispatch or auto-install."""
    validate_policy(policy)
    validate_registry(registry)
    domains = classify_domains(prompt)
    result = {
        "schema": "universal-port.route-plan/1",
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "domains": domains,
        "selected": [],
        "unavailable": [],
        "execution_performed": False,
        "reason": "",
    }
    if not domains:
        result.update(status="NATIVE_FALLBACK_RECOMMENDED",
                      reason="No domain matched; automatic capability selection is unsafe")
        return result
    if len(domains) > MAX_DOMAINS_PER_PLAN:
        result.update(status="REVIEW_REQUIRED",
                      reason="More than two domains; no automatic composition")
        return result

    by_id = {item["id"]: item for item in registry["capabilities"]}
    approval_needed = False
    for domain in domains:
        config = policy["domains"][domain]
        candidates = [config["preferred"], *config["fallbacks"]]
        chosen = None
        blocked = []
        for cap_id in candidates:
            item = by_id.get(cap_id)
            if item is None or item["domain"] != domain:
                blocked.append({"capability_id": cap_id, "reason": "NOT_IN_DOMAIN_REGISTRY"})
                continue
            if not item["approved"] or not item["runtime_verified"]:
                blocked.append({"capability_id": cap_id, "reason": "NOT_APPROVED_AND_RUNTIME_VERIFIED"})
                continue
            if set(item["permissions"]) != {"read"}:
                blocked.append({"capability_id": cap_id, "reason": "SIDE_EFFECT_REQUIRES_APPROVAL"})
                approval_needed = True
                continue
            chosen = {"domain": domain, "capability_id": cap_id,
                      "kind": item["kind"], "invocation": item["invocation"],
                      "evidence_sha256": item["evidence_sha256"]}
            break
        if chosen:
            result["selected"].append(chosen)
        else:
            result["unavailable"].append({
                "domain": domain,
                "fallback": "VANILLA_RECOMMENDED" if config["allow_vanilla"] else "NONE",
                "blocked": blocked,
            })

    if approval_needed:
        result.update(status="APPROVAL_REQUIRED",
                      reason="An explicitly configured capability requires new side-effect permission")
    elif result["unavailable"]:
        result.update(status="PLAN_INCOMPLETE",
                      reason="Some domains have no eligible capability; fallback is advisory only")
    else:
        result.update(status="PLAN_READY",
                      reason="All selected capabilities are operator-approved and runtime-attested")
    result["composition"] = len(result["selected"]) > 1
    return result
