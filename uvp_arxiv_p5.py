"""P5: narrowly bounded arXiv network execution via an explicit Hermes slash command.

NOT a native Hermes arxiv SKILL.md execution, Direct Bridge or model tool.
A slash-command handler may only execute after all independent gates:
  - manual, explicit command with request-specific exact SHA-256 digest,
  - exactly UVP_ENABLE_ARXIV_EXECUTION=1 set in this process,
  - concrete cli/tui OR verified Hermes local slash source+session binding,
    never generic local string alone (messaging, cron, desktop and acp denied),
  - existing safe HERMES_HOME evidence location,
  - live operator ask_choice approval on the bound Hermes session.
No approval or live transport available means *no* network request.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from . import uvp_arxiv_cli as evidence
from . import uvp_arxiv_p4 as p4

P5_SCHEMA = "universal-port.arxiv-hermes-execution/1"
ENV_ENABLE = "UVP_ENABLE_ARXIV_EXECUTION"
ALLOWED_SURFACES = frozenset({"cli", "tui"})


def _result(status: str, request_sha256: str = "", *, executed: bool = False,
            evidence_path: str | None = None, paper: dict | None = None) -> dict:
    result = {
        "schema": P5_SCHEMA,
        "status": status,
        "execution_performed": executed,
        "approved_capabilities_added": 0,
    }
    if request_sha256:
        result["request_sha256"] = request_sha256
    if evidence_path is not None:
        result["evidence_path"] = evidence_path
    if paper is not None:
        result["paper"] = paper
    return result



def validate_host_local_context(*, source=None, platform=None,
                                session_id="", session_key="") -> tuple[bool, str]:
    """Check Hermes-provided slash-dispatch identity, not ambient cwd/env.

    A generic "local" string is never by itself proof of a user-attached
    session. Require Hermes's real SessionSource object, Platform.LOCAL,
    both session identifiers and matching host-dispatch platform.

    This is a trusted-host contract check, not a security boundary against
    malicious in-process Python or a compromised Hermes gateway.
    """
    if platform != "local":
        return False, "DISPATCH_PLATFORM_NOT_LOCAL"
    if (not isinstance(session_id, str) or not session_id.strip()
            or not isinstance(session_key, str) or not session_key.strip()):
        return False, "SESSION_IDENTIFIERS_UNAVAILABLE"
    try:
        from gateway.config import Platform
        from gateway.session import SessionSource
    except (ImportError, AttributeError):
        return False, "HERMES_SOURCE_TYPE_UNAVAILABLE"
    if (not isinstance(source, SessionSource)
            or source.platform is not Platform.LOCAL
            or not isinstance(source.chat_id, str)
            or not source.chat_id.strip()):
        return False, "LOCAL_SOURCE_UNVERIFIED"
    return True, "HOST_BOUND_LOCAL"


def run_with_choice(ctx, arxiv_id: str, expected_digest: str, *,
                    source=None, platform=None, session_id="",
                    session_key="") -> dict:
    """Attempt at most one HTTP GET, never until a real host choice approves.

    The gate is designed to prevent accidental API calls in the ordinary
    assistant/plugin workflow, not a sandbox from malicious local Python.
    """
    try:
        plan = p4.prepare(arxiv_id)
    except p4.P4Error:
        return _result("INVALID_VERSIONED_ID")
    if not isinstance(expected_digest, str) or expected_digest != plan["request_sha256"]:
        return _result("REQUEST_DIGEST_MISMATCH", plan["request_sha256"])

    # Default deny takes precedence, even for a surface we cannot identify.
    # This also keeps the observable result stable across classic CLI and TUI.
    if os.environ.get(ENV_ENABLE) != "1":
        return _result("DISABLED_BY_DEFAULT", plan["request_sha256"])

    # The host's session-scoped surface is authoritative, not a caller-
    # supplied CLI argument. Only local classic CLI or local TUI is accepted.
    # All chat/gateway, desktop, ACP and unknown surfaces fail closed.
    try:
        surface = ctx.session_surface()
    except Exception:
        return _result("UNVERIFIED_SURFACE", plan["request_sha256"])
    if surface not in ALLOWED_SURFACES:
        if surface != "local":
            return _result("LOCAL_CLI_OR_TUI_ONLY", plan["request_sha256"])
        verified, _reason = validate_host_local_context(
            source=source, platform=platform,
            session_id=session_id, session_key=session_key,
        )
        if not verified:
            return _result("LOCAL_CONTEXT_UNVERIFIED", plan["request_sha256"])

    # Verify receipt destination *before* asking the operator / sending data.
    try:
        evidence._receipts_dir()
    except (p4.P4Error, OSError, UnicodeError, ValueError):
        return _result("EVIDENCE_STORE_UNAVAILABLE", plan["request_sha256"])

    question = (
        "UVP arXiv single-paper lookup. EXACTLY ONE HTTPS GET; "
        "network + external_send. No retries. "
        "Target: " + plan["url"] + " | Request SHA-256: " +
        plan["request_sha256"] + ". Proceed?"
    )
    try:
        selected = ctx.ask_choice(question, [
            {"value": "deny", "label": "Cancel — do not call arXiv"},
            {"value": "approve", "label": "Approve one arXiv GET"},
        ])
    except Exception:
        return _result("APPROVAL_UI_UNAVAILABLE", plan["request_sha256"])
    if selected != "approve":
        return _result("OPERATOR_DENIED_OR_UNAVAILABLE", plan["request_sha256"])

    # Only a user-submitted slash command can reach here. Runtime profile and
    # id constraints were checked above, with fresh consent bound to the URL.
    receipt = {
        "schema": "universal-port.arxiv-receipt/1",
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "execution_origin": "hermes_slash_command",
        "operator_confirmation": "hermes.ask_choice",
        "operator_confirmed": True,
        "request_sha256": plan["request_sha256"],
        "arxiv_id": plan["arxiv_id"],
        "target": plan["url"],
        "network_requests_attempted": 1,
        "status": "FAILED",
        "execution_performed": True,
    }
    try:
        paper, body_hash = p4.fetch_once(plan)
        receipt.update(status="SUCCEEDED", response_sha256=body_hash,
                       paper=paper)
    except p4.P4Error:
        receipt.update(error_type="P4Error", error="Bounded lookup failed")
    except Exception:
        receipt.update(error_type="UnexpectedError", error="Adapter failed")

    try:
        path = evidence.write_receipt(receipt)
    except Exception:
        # Network was already attempted. Failure writing local evidence MUST
        # NOT be reported as a non-execution or safe retry condition.
        return _result("EXECUTION_OUTCOME_UNRECORDED", plan["request_sha256"],
                       executed=True)
    if receipt["status"] == "SUCCEEDED":
        return _result("SUCCEEDED", plan["request_sha256"], executed=True,
                       evidence_path=str(path), paper=receipt["paper"])
    return _result("FAILED", plan["request_sha256"], executed=True,
                   evidence_path=str(path))
