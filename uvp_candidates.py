"""P3 preview: bounded, unapproved *candidates* from real Hermes metadata.

A Skill is a document/instruction, not a standalone executable function.
Discovery and recommendation never imply operator approval or execution.
No direct skill_view, subprocess, install or model call here. The opted-in\nHermes skills_list dispatcher may initialize host plugin catalogs/caches.
"""
from __future__ import annotations

from .uvp_routing import RoutingError, classify_domains
from .uvp_discovery import parse_skills_list

# Small reviewed builtin seed list, not a universal ontology. A longer-term
# metadata/embedding index should preserve verified functionality and side effects.
# These entries ONLY describe candidates; none is an executable mapping.
SEEDS = {
    "arxiv": ("research", "paper_search", ["network", "external_send"], "Search arXiv papers"),
    "grounded-citations": ("research", "citation_support", ["network", "write", "external_send"], "Ground citations with a ledger"),
    "claude-code": ("coding", "code_implementation", ["execute", "write", "network", "external_send"], "Delegate code work to Claude CLI"),
    "codex": ("coding", "code_implementation", ["execute", "write", "network", "external_send"], "Delegate code work to Codex CLI"),
    "systematic-debugging": ("coding", "debugging_workflow", ["execute", "write"], "Debugging procedure; may call tools"),
    "codebase-inspection": ("coding", "code_metrics", ["execute", "read", "network", "write"], "Code statistics via pygount; dependency required"),
    "pdf": ("documents", "pdf_workflow", ["read", "write"], "PDF instructions and workflows"),
    "microsoft-office": ("documents", "office_workflow", ["read", "write"], "Office document workflows"),
}
DOMAIN_RANKS = {
    "research": ("arxiv", "grounded-citations"),
    "coding": ("claude-code", "codex"),
    "documents": ("pdf", "microsoft-office"),
}
MAX_CANDIDATES = 3


def candidates_from_catalog(prompt: str, catalog_json: str | dict) -> dict:
    """Only recommend reviewed seed names *actually visible* to this host.

    Metadata names are untrusted input and must never turn into approvals.
    Permissions are advisory expected needs, not an enforceable host policy.
    """
    domains = classify_domains(prompt)
    catalog = parse_skills_list(catalog_json)
    found = set(catalog["names"])
    output = []
    for domain in domains:
        ranks = DOMAIN_RANKS.get(domain, ())
        # Coarse intent-specific reordering avoids treating code metrics as
        # general software implementation, but is NOT semantic understanding.
        if domain == "coding" and any(k in prompt.lower() for k in ("디버그", "버그", "debug", "bug")):
            ranks = ("systematic-debugging", "claude-code", "codex", "codebase-inspection")
        elif domain == "coding" and any(k in prompt.lower() for k in ("loc", "코드 줄", "라인 수", "lines of code")):
            ranks = ("codebase-inspection",)
        for name in ranks:
            if name not in found:
                continue
            category, capability, permissions, meaning = SEEDS[name]
            if category != domain:
                continue
            output.append({
                "domain": domain,
                "skill": name,
                "capability": capability,
                "expected_effects": permissions,
                "description": meaning,
                "status": "DISCOVERED_UNAPPROVED",
                "executable": False,
            })
            if sum(x["domain"] == domain for x in output) >= MAX_CANDIDATES:
                break
    return {
        "schema": "universal-port.skill-candidate-preview/1",
        "domains": domains,
        "catalog_count": catalog["count"],
        "candidates": output,
        "approved_capabilities_added": 0,
        "execution_performed": False,
        "note": "Candidate metadata only; no Skill instructions read or invoked",
    }


def candidates_from_hermes(ctx, prompt: str) -> dict:
    """One explicit user-triggered native catalog query; never auto-invoke."""
    if not hasattr(ctx, "dispatch_tool"):
        raise RoutingError("Hermes tool dispatcher unavailable")
    listing = ctx.dispatch_tool("skills_list", {})
    return candidates_from_catalog(prompt, listing)
