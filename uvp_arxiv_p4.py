"""P4 narrow, explicitly operator-approved arXiv metadata lookup.

Not an execution of Hermes's arxiv SKILL.md: this is a UVP-owned adapter
for the specific, version-pinned paper-lookup capability only.

This module never calls the network on import, plan, or validation. Network
execution must be gated by the separate human-interactive CLI.
"""
from __future__ import annotations

import hashlib
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

PLAN_SCHEMA = "universal-port.arxiv-plan/1"
ATOM = "{http://www.w3.org/2005/Atom}"
API_ORIGIN = "https://export.arxiv.org"
API_PATH = "/api/query"
MAX_BODY_BYTES = 131072
TIMEOUT_SECONDS = 8
ID = re.compile(r"^[0-9]{4}\.[0-9]{4,5}v[1-9][0-9]{0,2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class P4Error(ValueError):
    """Invalid request, response, or an explicitly blocked operation."""


def validate_id(arxiv_id: str) -> str:
    if not isinstance(arxiv_id, str) or not ID.fullmatch(arxiv_id):
        raise P4Error("Expected a single version-pinned modern arXiv ID, e.g. 1706.03762v1")
    return arxiv_id


def prepare(arxiv_id: str) -> dict:
    """A deterministic, no-network draft for operator review."""
    arxiv_id = validate_id(arxiv_id)
    url = API_ORIGIN + API_PATH + "?" + urllib.parse.urlencode(
        {"id_list": arxiv_id, "max_results": 1})
    digest = hashlib.sha256(("GET " + url).encode("ascii")).hexdigest()
    return {
        "schema": PLAN_SCHEMA,
        "arxiv_id": arxiv_id,
        "method": "GET",
        "url": url,
        "request_sha256": digest,
        "expected_effects": ["network", "external_send"],
        "request_count_limit": 1,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_response_bytes": MAX_BODY_BYTES,
        "approval_status": "AWAITING_OPERATOR_CONFIRMATION",
        "execution_performed": False,
    }


def verify_plan(plan: dict) -> dict:
    """Do not trust a caller-supplied URL, digest, or permission assertion."""
    if not isinstance(plan, dict):
        raise P4Error("Invalid arXiv plan")
    approved = prepare(plan.get("arxiv_id"))
    if plan != approved:
        raise P4Error("Plan does not match the pinned approved endpoint")
    return approved


def approval_phrase(plan: dict) -> str:
    valid = verify_plan(plan)
    return "APPROVE ARXIV " + valid["arxiv_id"] + " " + valid["request_sha256"][:12]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise P4Error("Redirect blocked: arXiv endpoint must remain pinned")


def make_opener():
    """Enforce TLS and ignore environment-provided HTTP(S) proxy settings."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        NoRedirect(),
    )


def _text(entry: ET.Element, key: str, required: bool = False) -> str:
    item = entry.find(ATOM + key)
    value = " ".join((item.text or "").split()) if item is not None else ""
    if required and not value:
        raise P4Error("Missing required arXiv response field")
    return value


def parse_atom(data: bytes, requested_id: str) -> dict:
    """Parse only one bounded Atom entry whose versioned ID matches request."""
    requested_id = validate_id(requested_id)
    if not isinstance(data, bytes) or not data or len(data) > MAX_BODY_BYTES:
        raise P4Error("Invalid or oversized Atom response")
    if b"<!doctype" in data.lower() or b"<!entity" in data.lower():
        raise P4Error("XML declarations with external entities are rejected")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise P4Error("Malformed Atom XML") from exc
    if root.tag != ATOM + "feed":
        raise P4Error("Unexpected arXiv Atom root")
    entries = root.findall(ATOM + "entry")
    if len(entries) != 1:
        raise P4Error("Expected precisely one paper in API response")
    entry = entries[0]
    raw_url = _text(entry, "id", required=True)
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.hostname not in {"arxiv.org", "www.arxiv.org"} or parsed.path != "/abs/" + requested_id:
        raise P4Error("Returned paper does not match the pinned requested version")
    if parsed.username or parsed.password or parsed.port or parsed.params or parsed.query or parsed.fragment:
        raise P4Error("Invalid paper identity URL in response")
    title = _text(entry, "title", required=True)
    published = _text(entry, "published")
    authors = []
    for author in entry.findall(ATOM + "author"):
        name = _text(author, "name")
        if name:
            authors.append(name)
        if len(authors) >= 32:
            break
    return {
        "arxiv_id": requested_id,
        "title": title[:512],
        "authors": authors,
        "published": published[:64],
        "abstract": _text(entry, "summary")[:1600],
        "paper_url": "https://arxiv.org/abs/" + requested_id,
    }


def fetch_once(plan: dict, *, opener=None) -> tuple[dict, str]:
    """Perform one GET; never retries, follows redirects, or sends credentials.

    Caller MUST have independently collected human approval before invoking.
    An injected opener is for offline tests only; this is not a permission
    boundary when arbitrary local Python can invoke this function.
    """
    approved = verify_plan(plan)
    parsed = urllib.parse.urlsplit(approved["url"])
    if (parsed.scheme, parsed.hostname, parsed.path, parsed.port, parsed.username,
            parsed.password) != ("https", "export.arxiv.org", API_PATH, None, None, None):
        raise P4Error("Endpoint not allowlisted")
    req = urllib.request.Request(
        approved["url"],
        headers={"User-Agent": "Hermes-UVP-P4/0.1 (single verified paper lookup)",
                 "Accept": "application/atom+xml"},
        method="GET",
    )
    try:
        transport = opener if opener is not None else make_opener()
        with transport.open(req, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise P4Error("Non-200 response")
            returned_url = response.geturl()
            if returned_url != approved["url"]:
                raise P4Error("Response URL changed")
            raw = response.read(MAX_BODY_BYTES + 1)
    except P4Error:
        raise
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise P4Error("arXiv network request failed") from exc
    if len(raw) > MAX_BODY_BYTES:
        raise P4Error("arXiv response body exceeded the limit")
    paper = parse_atom(raw, approved["arxiv_id"])
    return paper, hashlib.sha256(raw).hexdigest()
