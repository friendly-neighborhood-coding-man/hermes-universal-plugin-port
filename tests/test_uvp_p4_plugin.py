"""P4 integration: Hermes command may prepare, but must not execute network."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p4_test_pkg", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)


class Context:
    def __init__(self):
        self.commands = {}
        self.tools = []
        self.dispatches = []

    def register_command(self, name, handler, **_kw):
        self.commands[name] = handler

    def register_tool(self, **kw):
        self.tools.append(kw["name"])

    def dispatch_tool(self, name, args):
        self.dispatches.append(name)
        raise AssertionError("P4 preview may not dispatch a tool")


class P4CommandTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Context()
        PKG.register(self.ctx)

    def test_registration_does_not_add_executor(self):
        self.assertEqual(self.ctx.tools, [
            "port_probe", "port_fetch", "port_stage", "uvp_route"])
        self.assertEqual(self.ctx.dispatches, [])

    def test_preview_requires_approval_and_does_not_execute(self):
        from uvp_p4_test_pkg import uvp_arxiv_p4 as P4
        with patch.object(P4, "make_opener", side_effect=AssertionError("network")):
            text = self.ctx.commands["uvp"]("--arxiv-plan 1706.03762v1")
        self.assertIn("APPROVAL REQUIRED", text)
        plan = json.loads(text.split("\n", 1)[1])
        self.assertEqual(plan["arxiv_id"], "1706.03762v1")
        self.assertEqual(plan["approval_status"], "AWAITING_OPERATOR_CONFIRMATION")
        self.assertFalse(plan["execution_performed"])
        self.assertEqual(self.ctx.dispatches, [])

    def test_invalid_id_fails_closed(self):
        text = self.ctx.commands["uvp"]("--arxiv-plan 1706.03762v1&max_results=99")
        self.assertIn("ARXIV PLAN ERROR", text)
        self.assertEqual(self.ctx.dispatches, [])

    def test_bare_route_semantics_unchanged(self):
        text = self.ctx.commands["uvp"]("논문을 조사하고 코드를 구현해줘")
        data = json.loads(text.split("\n", 1)[1])
        self.assertEqual(data["status"], "PLAN_INCOMPLETE")
        self.assertFalse(data["execution_performed"])
        self.assertEqual(self.ctx.dispatches, [])


if __name__ == "__main__":
    unittest.main()
