"""P5 regression: no real network. Fake Hermes choices and fake fetch."""
import importlib.util
import json
import os
import types
from contextlib import contextmanager
from enum import Enum
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p5_test_pkg", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)

from uvp_p5_test_pkg import uvp_arxiv_p4 as P4
from uvp_p5_test_pkg import uvp_arxiv_p5 as P5
from uvp_p5_test_pkg import uvp_arxiv_cli as EVIDENCE


@contextmanager
def fake_host_gateway():
    """Simulate Hermes's exact bound SessionSource and Platform types."""
    gateway = types.ModuleType("gateway")
    gateway.__path__ = []
    config = types.ModuleType("gateway.config")
    session = types.ModuleType("gateway.session")

    class Platform(Enum):
        LOCAL = "local"
        TELEGRAM = "telegram"

    class SessionSource:
        def __init__(self, platform=Platform.LOCAL, chat_id="local-chat"):
            self.platform = platform
            self.chat_id = chat_id

    config.Platform = Platform
    session.SessionSource = SessionSource
    gateway.config = config
    gateway.session = session
    with patch.dict(sys.modules, {
        "gateway": gateway, "gateway.config": config, "gateway.session": session,
    }):
        yield Platform, SessionSource


class FakeContext:
    def __init__(self, *, surface="cli", choice="deny", fail_choice=False):
        self.surface = surface
        self.choice = choice
        self.fail_choice = fail_choice
        self.asked = []
        self.commands = {}
        self.tools = []

    def session_surface(self):
        return self.surface

    def ask_choice(self, question, choices):
        self.asked.append((question, choices))
        if self.fail_choice:
            raise RuntimeError("No UI")
        return self.choice

    def register_command(self, name, handler, **_kw):
        self.commands[name] = handler

    def register_tool(self, **kwargs):
        self.tools.append(kwargs["name"])


class P5Tests(unittest.TestCase):
    def setUp(self):
        self.plan = P4.prepare("1706.03762v1")
        self.ctx = FakeContext()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            P5.ENV_ENABLE: "1",
            "HERMES_HOME": self.tmp.name,
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake_store(self):
        return patch.object(EVIDENCE, "_receipts_dir", return_value=Path(self.tmp.name))

    def test_inactive_by_default(self):
        os.environ.pop(P5.ENV_ENABLE)
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            result = P5.run_with_choice(self.ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(result["status"], "DISABLED_BY_DEFAULT")
        self.assertFalse(result["execution_performed"])
        self.assertEqual(self.ctx.asked, [])

    def test_wrong_digest_denied_before_asker(self):
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(self.ctx, self.plan["arxiv_id"], "0" * 64)
        self.assertEqual(report["status"], "REQUEST_DIGEST_MISMATCH")
        self.assertEqual(self.ctx.asked, [])
        self.assertFalse(report["execution_performed"])

    def test_invalid_or_injected_id_denied(self):
        report = P5.run_with_choice(self.ctx, "1706.03762v1&x=3", self.plan["request_sha256"])
        self.assertEqual(report["status"], "INVALID_VERSIONED_ID")
        self.assertEqual(self.ctx.asked, [])

    def test_gateway_telegram_not_allowed(self):
        ctx = FakeContext(surface="telegram", choice="approve")
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "LOCAL_CLI_OR_TUI_ONLY")
        self.assertEqual(ctx.asked, [])

    def test_unknown_surface_denied(self):
        ctx = FakeContext(surface="future_surface", choice="approve")
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "LOCAL_CLI_OR_TUI_ONLY")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])


    def test_tui_without_enable_flag_is_disabled_not_surface_rejected(self):
        os.environ[P5.ENV_ENABLE] = "0"
        ctx = FakeContext(surface="tui", choice="approve")
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "DISABLED_BY_DEFAULT")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_telegram_without_enable_flag_is_also_disabled(self):
        os.environ[P5.ENV_ENABLE] = "0"
        ctx = FakeContext(surface="telegram", choice="approve")
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "DISABLED_BY_DEFAULT")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_tui_with_flag_but_denied_never_calls_network(self):
        ctx = FakeContext(surface="tui", choice="deny")
        with self.fake_store(), patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "OPERATOR_DENIED_OR_UNAVAILABLE")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(len(ctx.asked), 1)

    def test_tui_with_flag_approval_one_bounded_fake_get(self):
        ctx = FakeContext(surface="tui", choice="approve")
        calls = []
        records = []
        def fake_get(p):
            calls.append(p)
            return {"arxiv_id": p["arxiv_id"]}, "0" * 64
        with self.fake_store(), \
             patch.object(P4, "fetch_once", side_effect=fake_get), \
             patch.object(EVIDENCE, "write_receipt", side_effect=lambda r: records.append(r) or Path("fake.json")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "SUCCEEDED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operator_confirmation"], "hermes.ask_choice")
        self.assertEqual(records[0]["network_requests_attempted"], 1)

    def test_desktop_acp_and_empty_surface_remain_blocked(self):
        for surface in ("desktop", "acp", ""):
            with self.subTest(surface=surface):
                ctx = FakeContext(surface=surface, choice="approve")
                with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
                    report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
                self.assertEqual(report["status"], "LOCAL_CLI_OR_TUI_ONLY")
                self.assertFalse(report["execution_performed"])
                self.assertEqual(ctx.asked, [])

    def test_evidence_store_failure_blocks_before_question(self):
        with patch.object(EVIDENCE, "_receipts_dir", side_effect=P4.P4Error("no evidence")):
            with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
                report = P5.run_with_choice(self.ctx, self.plan["arxiv_id"],
                                            self.plan["request_sha256"])
        self.assertEqual(report["status"], "EVIDENCE_STORE_UNAVAILABLE")
        self.assertEqual(self.ctx.asked, [])

    def test_no_asker_denied(self):
        ctx = FakeContext(choice=None)
        with self.fake_store(), patch.object(P4, "fetch_once",
                                             side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "OPERATOR_DENIED_OR_UNAVAILABLE")
        self.assertEqual(len(ctx.asked), 1)
        self.assertIn(self.plan["request_sha256"], ctx.asked[0][0])
        self.assertFalse(report["execution_performed"])

    def test_explicit_no_denied(self):
        with self.fake_store(), patch.object(P4, "fetch_once",
                                             side_effect=AssertionError("network!")):
            report = P5.run_with_choice(self.ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "OPERATOR_DENIED_OR_UNAVAILABLE")
        self.assertFalse(report["execution_performed"])

    def test_choice_exception_denies(self):
        ctx = FakeContext(choice="approve", fail_choice=True)
        with self.fake_store(), patch.object(P4, "fetch_once",
                                             side_effect=AssertionError("network!")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "APPROVAL_UI_UNAVAILABLE")
        self.assertFalse(report["execution_performed"])

    def test_success_one_get_and_evidence(self):
        ctx = FakeContext(choice="approve")
        calls = []
        records = []
        def fake_fetch(plan):
            calls.append(plan)
            return {"arxiv_id": plan["arxiv_id"], "title": "fixture"}, "1" * 64
        def record(receipt):
            records.append(receipt)
            return Path(self.tmp.name) / "fixture.json"
        with self.fake_store(), patch.object(P4, "fetch_once", side_effect=fake_fetch), \
             patch.object(EVIDENCE, "write_receipt", side_effect=record):
            result = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertTrue(result["execution_performed"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["network_requests_attempted"], 1)
        self.assertEqual(records[0]["operator_confirmation"], "hermes.ask_choice")
        self.assertEqual(records[0]["status"], "SUCCEEDED")
        self.assertEqual(result["paper"]["arxiv_id"], self.plan["arxiv_id"])

    def test_failure_one_get_and_evidence(self):
        ctx = FakeContext(choice="approve")
        recorded = []
        with self.fake_store(), \
             patch.object(P4, "fetch_once", side_effect=P4.P4Error("offline")), \
             patch.object(EVIDENCE, "write_receipt", side_effect=lambda r: recorded.append(r) or Path("bad.json")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "FAILED")
        self.assertTrue(report["execution_performed"])
        self.assertEqual(recorded[0]["status"], "FAILED")

    def test_receipt_failure_never_claims_no_execution(self):
        ctx = FakeContext(choice="approve")
        with self.fake_store(), \
             patch.object(P4, "fetch_once", return_value=({"arxiv_id": "1706.03762v1"}, "0" * 64)), \
             patch.object(EVIDENCE, "write_receipt", side_effect=OSError("cannot save")):
            report = P5.run_with_choice(ctx, self.plan["arxiv_id"], self.plan["request_sha256"])
        self.assertEqual(report["status"], "EXECUTION_OUTCOME_UNRECORDED")
        self.assertTrue(report["execution_performed"])


    def test_surface_diagnostic_reports_local_tui_without_any_network(self):
        os.environ[P5.ENV_ENABLE] = "0"
        ctx = FakeContext(surface="tui", choice="approve")
        PKG.register(ctx)
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            raw = ctx.commands["uvp"]("--surface")
        self.assertTrue(raw.startswith("UVP session diagnostic (NOT EXECUTED):\n"))
        self.assertNotIn(r"\n{", raw)
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["schema"], "universal-port.session-diagnostic/3")
        self.assertEqual(report["session_surface"], "tui")
        self.assertEqual(report["session_surface_lookup"], "recognized")
        self.assertEqual(report["host_dispatch_platform"], "unavailable_or_other")
        self.assertTrue(report["local_surface_permitted"])
        self.assertFalse(report["live_execution_opt_in"])
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_surface_diagnostic_unknown_never_enables(self):
        ctx = FakeContext(surface="unrecognized-custom-client")
        PKG.register(ctx)
        raw = ctx.commands["uvp"]("--surface")
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["session_surface"], "unknown")
        self.assertFalse(report["local_surface_permitted"])
        self.assertFalse(report["live_execution_opt_in"])
        self.assertEqual(ctx.asked, [])

    def test_gateway_local_dispatch_does_not_grant_local_session_privilege(self):
        ctx = FakeContext(surface="local", choice="approve")
        PKG.register(ctx)
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            raw = ctx.commands["uvp"]("--surface", platform="local")
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["schema"], "universal-port.session-diagnostic/3")
        self.assertEqual(report["session_surface"], "local")
        self.assertEqual(report["session_surface_lookup"], "generic_local")
        self.assertEqual(report["host_dispatch_platform"], "local")
        self.assertFalse(report["local_surface_permitted"])
        self.assertFalse(report["live_execution_opt_in"])
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_empty_host_session_surface_is_diagnosed(self):
        ctx = FakeContext(surface="")
        PKG.register(ctx)
        raw = ctx.commands["uvp"]("--surface", platform="local")
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["session_surface"], "unknown")
        self.assertEqual(report["session_surface_lookup"], "empty")
        self.assertEqual(report["host_dispatch_platform"], "local")
        self.assertFalse(report["local_surface_permitted"])

    def test_session_surface_exception_is_diagnosed_without_leaking(self):
        ctx = FakeContext()
        ctx.session_surface = lambda: (_ for _ in ()).throw(ValueError("private key"))
        PKG.register(ctx)
        raw = ctx.commands["uvp"]("--surface", platform="local")
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["session_surface"], "unknown")
        self.assertEqual(report["session_surface_lookup"], "exception")
        self.assertNotIn("private key", raw)
        self.assertFalse(report["local_surface_permitted"])

    def test_host_local_platform_is_not_an_execution_authorization(self):
        ctx = FakeContext(surface="local", choice="approve")
        PKG.register(ctx)
        cmd = ctx.commands["uvp"]
        with patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            raw = cmd("--arxiv-execute " + self.plan["arxiv_id"] +
                      " " + self.plan["request_sha256"], platform="local")
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["status"], "LOCAL_CONTEXT_UNVERIFIED")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_verified_host_local_session_requires_complete_metadata(self):
        with fake_host_gateway() as (Platform, SessionSource):
            source = SessionSource()
            for fields in (
                {"source": source, "platform": "local", "session_id": "", "session_key": "route"},
                {"source": source, "platform": "local", "session_id": "sid", "session_key": ""},
                {"source": source, "platform": "discord", "session_id": "sid", "session_key": "route"},
                {"source": SessionSource(chat_id=""), "platform": "local",
                 "session_id": "sid", "session_key": "route"},
                {"source": SessionSource(platform=Platform.TELEGRAM), "platform": "local",
                 "session_id": "sid", "session_key": "route"},
                {"source": object(), "platform": "local",
                 "session_id": "sid", "session_key": "route"},
            ):
                with self.subTest(fields={k: str(v) for k, v in fields.items()}):
                    good, _ = P5.validate_host_local_context(**fields)
                    self.assertFalse(good)

    def test_verified_host_local_metadata_allows_bounded_mock_execution(self):
        ctx = FakeContext(surface="local", choice="approve")
        records, calls = [], []
        with fake_host_gateway() as (_, SessionSource):
            source = SessionSource()
            with self.fake_store(), \
                 patch.object(P4, "fetch_once", side_effect=lambda plan: (
                     calls.append(plan) or ({"arxiv_id": plan["arxiv_id"]}, "f" * 64))), \
                 patch.object(EVIDENCE, "write_receipt",
                              side_effect=lambda receipt: records.append(receipt) or Path("fake.json")):
                report = P5.run_with_choice(
                    ctx, self.plan["arxiv_id"], self.plan["request_sha256"],
                    source=source, platform="local", session_id="sid", session_key="route",
                )
        self.assertEqual(report["status"], "SUCCEEDED")
        self.assertEqual(len(ctx.asked), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["operator_confirmation"], "hermes.ask_choice")
        self.assertEqual(records[0]["network_requests_attempted"], 1)

    def test_verified_host_local_denial_never_dispatches(self):
        ctx = FakeContext(surface="local", choice="deny")
        with fake_host_gateway() as (_, SessionSource), self.fake_store(), \
             patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(
                ctx, self.plan["arxiv_id"], self.plan["request_sha256"],
                source=SessionSource(), platform="local",
                session_id="sid", session_key="route",
            )
        self.assertEqual(report["status"], "OPERATOR_DENIED_OR_UNAVAILABLE")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(len(ctx.asked), 1)

    def test_bound_host_local_diagnostic_no_execution(self):
        # setUp opts in by default for positive execution-path unit tests;
        # this case explicitly checks the production-safe disabled state.
        os.environ[P5.ENV_ENABLE] = "0"
        ctx = FakeContext(surface="local", choice="approve")
        PKG.register(ctx)
        with fake_host_gateway() as (_, SessionSource), \
             patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            raw = ctx.commands["uvp"](
                "--surface", source=SessionSource(),
                platform="local", session_id="sid", session_key="route",
            )
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["schema"], "universal-port.session-diagnostic/3")
        self.assertEqual(report["host_dispatch_platform"], "local")
        self.assertEqual(report["session_surface_lookup"], "generic_local")
        self.assertTrue(report["host_local_source_verified"])
        self.assertEqual(report["host_context_status"], "HOST_BOUND_LOCAL")
        self.assertTrue(report["session_id_present"])
        self.assertTrue(report["session_key_present"])
        self.assertTrue(report["local_surface_permitted"])
        self.assertFalse(report["live_execution_opt_in"])
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_host_bound_diagnostic_with_opt_in_is_still_read_only(self):
        # Diagnostic may report readiness when the test opt-in flag is 1,
        # but it must NEVER ask the user or execute the adapter.
        os.environ[P5.ENV_ENABLE] = "1"
        ctx = FakeContext(surface="local", choice="approve")
        PKG.register(ctx)
        with fake_host_gateway() as (_, SessionSource), \
             patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            raw = ctx.commands["uvp"](
                "--surface", source=SessionSource(),
                platform="local", session_id="sid", session_key="route",
            )
        report = json.loads(raw.split("\n", 1)[1])
        self.assertEqual(report["schema"], "universal-port.session-diagnostic/3")
        self.assertTrue(report["host_local_source_verified"])
        self.assertTrue(report["local_surface_permitted"])
        self.assertTrue(report["live_execution_opt_in"])
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_host_local_with_flag_zero_still_fails_closed(self):
        os.environ[P5.ENV_ENABLE] = "0"
        ctx = FakeContext(surface="local", choice="approve")
        with fake_host_gateway() as (_, SessionSource), \
             patch.object(P4, "fetch_once", side_effect=AssertionError("network!")):
            report = P5.run_with_choice(
                ctx, self.plan["arxiv_id"], self.plan["request_sha256"],
                source=SessionSource(), platform="local",
                session_id="sid", session_key="route",
            )
        self.assertEqual(report["status"], "DISABLED_BY_DEFAULT")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_hermes_command_defaults_to_disabled(self):
        os.environ.pop(P5.ENV_ENABLE)
        ctx = FakeContext(choice="approve")
        PKG.register(ctx)
        self.assertEqual(ctx.tools, ["port_probe", "port_fetch", "port_stage", "uvp_route"])
        cmd = ctx.commands["uvp"]
        result = json.loads(cmd("--arxiv-execute " + self.plan["arxiv_id"] +
                                " " + self.plan["request_sha256"]).split("\n", 1)[1])
        self.assertEqual(result["status"], "DISABLED_BY_DEFAULT")
        self.assertFalse(result["execution_performed"])
        self.assertEqual(ctx.asked, [])

    def test_hermes_command_no_extra_arguments(self):
        ctx = FakeContext(choice="approve")
        PKG.register(ctx)
        output = ctx.commands["uvp"]("--arxiv-execute " + self.plan["arxiv_id"] +
                                     " " + self.plan["request_sha256"] + " evil")
        self.assertIn("Usage", output)
        self.assertEqual(ctx.asked, [])

    def test_model_tool_still_preview_only(self):
        ctx = FakeContext()
        PKG.register(ctx)
        from uvp_p5_test_pkg import uvp_plugin_router as ROUTER
        report = json.loads(ROUTER.tool_handler({"prompt": "논문을 조사하고 코드를 구현해줘"}))
        self.assertEqual(report["status"], "PLAN_INCOMPLETE")
        self.assertFalse(report["execution_performed"])
        self.assertEqual(ctx.asked, [])


if __name__ == "__main__":
    unittest.main()
