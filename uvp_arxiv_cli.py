"""Operator-only P4 arXiv execution gate; never exposed as a Hermes tool.

Usage:
  python uvp_arxiv_cli.py plan 1706.03762v1
  python uvp_arxiv_cli.py run 1706.03762v1 --expect <plan.request_sha256>

The run command requires a live interactive terminal and an exact approval
phrase typed by the operator. No --yes / noninteractive approval escape hatch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys
from pathlib import Path

if __package__:
    from .uvp_arxiv_p4 import P4Error, approval_phrase, fetch_once, prepare
else:
    from uvp_arxiv_p4 import P4Error, approval_phrase, fetch_once, prepare


def _receipts_dir() -> Path:
    raw = os.environ.get("HERMES_HOME", "").strip()
    if not raw:
        raise P4Error("HERMES_HOME must be set explicitly for evidence storage")
    home = Path(raw)
    if not home.is_dir() or home.is_symlink():
        raise P4Error("HERMES_HOME must be an existing real directory")
    out = home / "uvp-evidence"
    if out.is_symlink():
        raise P4Error("Evidence directory cannot be a symlink")
    out.mkdir(mode=0o700, exist_ok=True)
    if out.is_symlink() or not out.is_dir():
        raise P4Error("Unsafe evidence directory")
    return out


def write_receipt(record: dict) -> Path:
    """Create a distinct record; never overwrite evidence from a prior run."""
    directory = _receipts_dir()
    now = dt.datetime.now(dt.timezone.utc)
    name = "arxiv-" + now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(5) + ".json"
    path = directory / name
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(payload + "\n")
    return path


def run_interactive(arxiv_id: str, expected_digest: str, *,
                    input_stream=None, output_stream=None,
                    fetcher=fetch_once, recorder=write_receipt) -> int:
    """A live operator must type a request-specific phrase, not a boolean."""
    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    plan = prepare(arxiv_id)
    if expected_digest != plan["request_sha256"]:
        raise P4Error("Prepared request digest does not match")
    if not input_stream.isatty():
        raise P4Error("P4 network access requires an interactive operator TTY")
    # Check that evidence can be safely saved before soliciting approval.
    if recorder is write_receipt:
        _receipts_dir()
    exact = approval_phrase(plan)
    output_stream.write("ONE arXiv API GET; network + external_send.\n")
    output_stream.write("Target: " + plan["url"] + "\n")
    output_stream.write("Request SHA-256: " + plan["request_sha256"] + "\n")
    output_stream.write("Type exactly to approve: " + exact + "\n> ")
    output_stream.flush()
    response = input_stream.readline().strip()
    if response != exact:
        output_stream.write("Denied; no arXiv request made.\n")
        return 2
    receipt = {
        "schema": "universal-port.arxiv-receipt/1",
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "request_sha256": plan["request_sha256"],
        "arxiv_id": plan["arxiv_id"],
        "target": plan["url"],
        "operator_confirmed": True,
        "network_requests_attempted": 1,
        "status": "FAILED",
        "execution_performed": True,
    }
    try:
        paper, body_digest = fetcher(plan)
        receipt.update(
            status="SUCCEEDED",
            response_sha256=body_digest,
            paper=paper,
        )
    except P4Error as exc:
        receipt.update(error_type=type(exc).__name__, error="Bounded lookup failed")
    except Exception as exc:
        receipt.update(error_type=type(exc).__name__, error="Unexpected adapter failure")
    path = recorder(receipt)
    output_stream.write("Evidence: " + str(path) + "\n")
    output_stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return 0 if receipt["status"] == "SUCCEEDED" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="P4 single-version arXiv lookup; no network without manual TTY approval")
    subs = parser.add_subparsers(dest="action", required=True)
    plan_cmd = subs.add_parser("plan", help="Print request preview (no network)")
    run_cmd = subs.add_parser("run", help="Run once after typed operator confirmation")
    for cmd in (plan_cmd, run_cmd):
        cmd.add_argument("arxiv_id", help="Version-pinned ID, e.g. 1706.03762v1")
    run_cmd.add_argument("--expect", required=True, help="Exact SHA-256 from plan")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            print(json.dumps(prepare(args.arxiv_id), indent=2))
            return 0
        return run_interactive(args.arxiv_id, args.expect)
    except (P4Error, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, P4Error) else "Local P4 I/O failed"
        print(json.dumps({
            "ok": False,
            "error": message,
            "execution_status": "NOT_STARTED" if args.action == "plan" else "UNKNOWN_ON_ERROR",
            "hint": "If approval was entered, inspect uvp-evidence and Hermes logs",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
