"""P2 Hermes registration contract: no model, IO dispatch, or tool execution."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p2_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p2_test_pkg import uvp_plugin_router as ENTRY


class RecordingHermesContext:
    def __init__(self):
        self.commands = []
        self.tools = []
        self.tool_calls = []
        self.llm_calls = []

    def register_command(self, name, **kwargs):
        self.commands.append((name, kwargs))

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def dispatch_tool(self, name, args):
        self.tool_calls.append((name, args))
        raise AssertionError("UVP must not dispatch tools during route preview")

    @property
    def llm(self):
        self.llm_calls.append("read")
        raise AssertionError("UVP must not access the model during route preview")


class P2EntryTests(unittest.TestCase):
    def setUp(self):
        self.ctx = RecordingHermesContext()
        PKG.register(self.ctx)

    def command(self, name):
        return next(x["handler"] for n, x in self.ctx.commands if n == name)

    def tool(self, name):
        return next(x["handler"] for x in self.ctx.tools if x["name"] == name)

    def test_registration_is_append_only(self):
        self.assertEqual([n for n, _ in self.ctx.commands],
                         ["universal-port", "uvp"])
        self.assertEqual([x["name"] for x in self.ctx.tools],
                         ["port_probe", "port_fetch", "port_stage", "uvp_route"])

    def test_slash_route_classifies_without_execution(self):
        body = self.command("uvp")("논문을 조사하고 코드를 구현해줘")
        self.assertIn("NOT EXECUTED", body)
        obj = json.loads(body.split("\n", 1)[1])
        self.assertEqual(obj["domains"], ["research", "coding"])
        self.assertEqual(obj["status"], "PLAN_INCOMPLETE")
        self.assertFalse(obj["execution_performed"])
        self.assertEqual(self.ctx.tool_calls, [])
        self.assertEqual(self.ctx.llm_calls, [])

    def test_empty_slash_shows_usage(self):
        self.assertIn("Usage:", self.command("uvp")(""))

    def test_registered_tool_rejects_unexpected_keys(self):
        result = json.loads(self.tool("uvp_route")({
            "prompt": "research", "approved": True}))
        self.assertFalse(result["ok"])
        self.assertFalse(result["execution_performed"])

    def test_registered_tool_rejects_non_string(self):
        result = json.loads(self.tool("uvp_route")({"prompt": {"bad": 1}}))
        self.assertFalse(result["ok"])
        self.assertFalse(result["execution_performed"])

    def test_registered_tool_is_advisory(self):
        result = json.loads(self.tool("uvp_route")({"prompt": "debug code"}))
        self.assertEqual(result["domains"], ["coding"])
        self.assertFalse(result["execution_performed"])
        self.assertEqual(self.ctx.tool_calls, [])
        self.assertEqual(self.ctx.llm_calls, [])


if __name__ == "__main__":
    unittest.main()
