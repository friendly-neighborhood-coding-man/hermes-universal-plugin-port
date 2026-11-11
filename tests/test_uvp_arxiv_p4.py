"""P4 offline tests: ZERO live API calls; fake network and operator TTY."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvp_arxiv_p4 as P4
import uvp_arxiv_cli as CLI


def atom(arxiv_id="1706.03762v1"):
    return ("""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/%s</id>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T00:00:00Z</published>
    <author><name>A. Researcher</name></author>
    <summary>Transformer architecture.</summary>
  </entry>
</feed>""" % arxiv_id).encode("utf-8")


class FakeResponse:
    status = 200

    def __init__(self, url, data=None):
        self.url = url
        self.data = atom() if data is None else data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def geturl(self):
        return self.url

    def read(self, length):
        return self.data[:length]


class FakeOpener:
    def __init__(self, *, reply=None):
        self.calls = []
        self.reply = reply

    def open(self, request, timeout):
        self.calls.append((request.full_url, request.get_method(), timeout))
        return self.reply if self.reply is not None else FakeResponse(request.full_url)


class TTY(io.StringIO):
    def isatty(self):
        return True


class P4Tests(unittest.TestCase):
    def test_prepare_never_calls_network(self):
        with patch.object(P4, "make_opener", side_effect=AssertionError("network!")):
            p = P4.prepare("1706.03762v1")
        self.assertEqual(p["approval_status"], "AWAITING_OPERATOR_CONFIRMATION")
        self.assertEqual(p["method"], "GET")
        self.assertEqual(p["request_count_limit"], 1)
        self.assertFalse(p["execution_performed"])
        self.assertEqual(p["url"],
                         "https://export.arxiv.org/api/query?id_list=1706.03762v1&max_results=1")

    def test_reject_unpinned_or_malicious_ids(self):
        for value in ("1706.03762", "1706.03762v0", "1706.03762v1,1706.03762v2",
                      "https://evil.test/", "1706.03762v1&max_results=99",
                      "cond-mat/0207270", "../", ""):
            with self.subTest(value=value):
                with self.assertRaises(P4.P4Error):
                    P4.prepare(value)

    def test_plan_tampering_is_rejected(self):
        plan = P4.prepare("1706.03762v1")
        for field, replacement in [("url", "https://bad.test/"),
                                    ("request_sha256", "0" * 64),
                                    ("request_count_limit", 10)]:
            with self.subTest(field=field):
                broken = dict(plan, **{field: replacement})
                with self.assertRaises(P4.P4Error):
                    P4.verify_plan(broken)

    def test_parse_atom_one_version_match(self):
        paper = P4.parse_atom(atom(), "1706.03762v1")
        self.assertEqual(paper["arxiv_id"], "1706.03762v1")
        self.assertEqual(paper["title"], "Attention Is All You Need")
        self.assertEqual(paper["paper_url"], "https://arxiv.org/abs/1706.03762v1")

    def test_wrong_version_response_rejected(self):
        with self.assertRaises(P4.P4Error):
            P4.parse_atom(atom("1706.03762v2"), "1706.03762v1")

    def test_no_extra_entries(self):
        payload = atom().replace(b"</feed>", b"<entry><id>http://arxiv.org/abs/1706.03762v1</id></entry></feed>")
        with self.assertRaises(P4.P4Error):
            P4.parse_atom(payload, "1706.03762v1")

    def test_dtd_rejected(self):
        data = atom().replace(b"<feed", b"<!DOCTYPE feed [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><feed", 1)
        with self.assertRaises(P4.P4Error):
            P4.parse_atom(data, "1706.03762v1")

    def test_oversized_response_rejected(self):
        with self.assertRaises(P4.P4Error):
            P4.parse_atom(b"a" * (P4.MAX_BODY_BYTES + 1), "1706.03762v1")

    def test_fetch_once_one_get_fake_transport(self):
        plan = P4.prepare("1706.03762v1")
        opener = FakeOpener()
        paper, digest = P4.fetch_once(plan, opener=opener)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0], (plan["url"], "GET", P4.TIMEOUT_SECONDS))
        self.assertEqual(len(digest), 64)
        self.assertEqual(paper["arxiv_id"], "1706.03762v1")

    def test_redirect_protection(self):
        with self.assertRaises(P4.P4Error):
            P4.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://bad.test")

    def test_changed_response_url_rejected(self):
        plan = P4.prepare("1706.03762v1")
        opener = FakeOpener(reply=FakeResponse("https://bad.test/"))
        with self.assertRaises(P4.P4Error):
            P4.fetch_once(plan, opener=opener)

    def test_no_terminal_means_no_network(self):
        plan = P4.prepare("1706.03762v1")
        with self.assertRaises(P4.P4Error):
            CLI.run_interactive(plan["arxiv_id"], plan["request_sha256"],
                                input_stream=io.StringIO(P4.approval_phrase(plan)),
                                output_stream=io.StringIO(),
                                fetcher=lambda _p: self.fail("network attempted"),
                                recorder=lambda _r: self.fail("evidence attempted"))

    def test_bad_digest_means_no_network(self):
        with self.assertRaises(P4.P4Error):
            CLI.run_interactive("1706.03762v1", "0" * 64,
                                input_stream=TTY("APPROVE"),
                                output_stream=io.StringIO(),
                                fetcher=lambda _p: self.fail("network attempted"))

    def test_denied_approval_never_dispatches(self):
        plan = P4.prepare("1706.03762v1")
        code = CLI.run_interactive(plan["arxiv_id"], plan["request_sha256"],
                                   input_stream=TTY("NO\n"),
                                   output_stream=io.StringIO(),
                                   fetcher=lambda _p: self.fail("network attempted"),
                                   recorder=lambda _r: self.fail("evidence attempted"))
        self.assertEqual(code, 2)

    def test_typed_approval_records_one_fake_success(self):
        plan = P4.prepare("1706.03762v1")
        receipts = []
        called = []
        def fake_fetch(p):
            called.append(p)
            return P4.parse_atom(atom(), p["arxiv_id"]), "f" * 64
        code = CLI.run_interactive(
            plan["arxiv_id"], plan["request_sha256"],
            input_stream=TTY(P4.approval_phrase(plan) + "\n"),
            output_stream=io.StringIO(), fetcher=fake_fetch,
            recorder=lambda r: (receipts.append(r) or Path("fake.json")))
        self.assertEqual(code, 0)
        self.assertEqual(len(called), 1)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["network_requests_attempted"], 1)
        self.assertEqual(receipts[0]["status"], "SUCCEEDED")

    def test_failed_attempt_still_records_failure(self):
        plan = P4.prepare("1706.03762v1")
        records = []
        code = CLI.run_interactive(
            plan["arxiv_id"], plan["request_sha256"],
            input_stream=TTY(P4.approval_phrase(plan) + "\n"),
            output_stream=io.StringIO(),
            fetcher=lambda _p: (_ for _ in ()).throw(P4.P4Error("no connection")),
            recorder=lambda r: (records.append(r) or Path("fake.json")))
        self.assertEqual(code, 1)
        self.assertEqual(records[0]["status"], "FAILED")
        self.assertEqual(records[0]["network_requests_attempted"], 1)

    def test_receipt_create_only_under_explicit_home(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"HERMES_HOME": tmp}):
            evidence = CLI.write_receipt({"schema": "test", "status": "SUCCEEDED"})
            self.assertTrue(evidence.is_file())
            self.assertEqual(evidence.parent, Path(tmp) / "uvp-evidence")
            self.assertEqual(json.loads(evidence.read_text())["status"], "SUCCEEDED")
            evidence2 = CLI.write_receipt({"schema": "test", "status": "FAILED"})
            self.assertNotEqual(evidence, evidence2)

    def test_missing_explicit_home_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(P4.P4Error):
                CLI.write_receipt({"schema": "test"})

    def test_cli_plan_no_network(self):
        out = io.StringIO()
        with patch.object(sys, "stdout", out), patch.object(P4, "make_opener",
                                                            side_effect=AssertionError("network")):
            rc = CLI.main(["plan", "1706.03762v1"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["request_count_limit"], 1)


if __name__ == "__main__":
    unittest.main()
