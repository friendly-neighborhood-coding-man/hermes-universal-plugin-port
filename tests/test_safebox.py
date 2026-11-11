"""P6.9 Safebox: default-deny grants, binding, audit, bypass report. POLICY_ONLY."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p69_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p69_test_pkg import safebox as SB
from uvp_p69_test_pkg import skill_continuity as SC
from uvp_p69_test_pkg.port_core import PortError

Q = "ported-product-management:write-spec"
SRC = "a" * 64


class SafeboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "work").mkdir()
        (self.root / "outside").mkdir()
        self.contracts = {Q: {"skill": Q, "source_sha256": SRC, "contract_id": SC.contract_id(Q, SRC)}}

    def grant(self, **over):
        g = SB.default_grant(Q, SRC, SC.contract_id(Q, SRC))
        g.update(over)
        return SB.validate_grant(g)

    def box(self, grant=None, audit=None):
        return SB.Safebox([grant or self.grant(fs={"read": [str(self.root / "work")], "write": [str(self.root / "work")]})],
                          self.contracts, audit_path=audit)

    def activate(self, b, s="s"):
        return b.pre_tool_call(tool_name="skill_view", args={"name": Q}, session_id=s)

    def test_default_grant_denies_everything_but_skill_reads(self):
        b = SB.Safebox([self.grant()], self.contracts)
        self.assertIsNone(self.activate(b))
        for tool, args in (("read_file", {"path": str(self.root / "work" / "a")}),
                           ("write_file", {"path": str(self.root / "work" / "a")}),
                           ("terminal", {"command": "echo hi"}), ("web_search", {"query": "x"}),
                           ("browser_navigate", {"url": "x"}), ("manage_connections", {}),
                           ("skill_manage", {}), ("delegate_task", {"goal": "g"}), ("unknown_tool", {})):
            r = b.pre_tool_call(tool_name=tool, args=args, session_id="s")
            self.assertEqual(r["action"], "block", tool)
        self.assertIsNone(b.pre_tool_call(tool_name="skills_list", args={}, session_id="s"))

    def test_fs_scope_and_symlink_escape(self):
        b = self.box()
        self.activate(b)
        inside = str(self.root / "work" / "out.md")
        self.assertIsNone(b.pre_tool_call(tool_name="write_file", args={"path": inside}, session_id="s"))
        self.assertIsNone(b.pre_tool_call(tool_name="read_file", args={"path": inside}, session_id="s"))
        for p in (str(self.root / "outside" / "x.md"), str(self.root / "work" / ".." / "outside" / "x.md"),
                  str(self.root / "work2" / "x.md")):
            self.assertEqual(b.pre_tool_call(tool_name="write_file", args={"path": p}, session_id="s")["action"], "block", p)
        for rel in ("x.md", "work/x.md", "./x.md"):
            r = b.pre_tool_call(tool_name="write_file", args={"path": rel}, session_id="s", cwd=str(self.root / "work"))
            self.assertEqual(r["action"], "block", rel)  # relative paths are never trusted
        try:
            os.symlink(self.root / "outside", self.root / "work" / "link", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        esc = b.pre_tool_call(tool_name="write_file", args={"path": str(self.root / "work" / "link" / "x.md")}, session_id="s")
        self.assertEqual(esc["action"], "block")

    def test_invocation_requires_bound_grant(self):
        b = SB.Safebox([], self.contracts)
        self.assertEqual(self.activate(b)["action"], "block")
        with self.assertRaises(PortError):
            SB.Safebox([dict(self.grant(), source_sha256="b" * 64)], self.contracts)
        with self.assertRaises(PortError):
            SB.Safebox([dict(self.grant(), contract_id="0" * 24)], self.contracts)

    def test_no_implicit_escalation(self):
        g = self.grant(shell=True)  # shell without process stays denied
        b = SB.Safebox([g], self.contracts)
        self.activate(b)
        self.assertEqual(b.pre_tool_call(tool_name="terminal", args={}, session_id="s")["action"], "block")
        for bad in ({"network": "yes"}, {"fs": {"read": ["relative/path"], "write": []}}, {"extra": True}):
            with self.assertRaises(PortError):
                SB.validate_grant(dict(self.grant(), **bad))

    def test_inactive_session_not_affected(self):
        b = self.box()
        self.assertIsNone(b.pre_tool_call(tool_name="terminal", args={}, session_id="other"))

    def test_denials_are_audited_with_binding(self):
        audit = self.root / "audit.jsonl"
        b = self.box(audit=audit)
        self.activate(b)
        b.pre_tool_call(tool_name="terminal", args={"command": "x"}, session_id="s")
        rec = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((rec["event"], rec["tool"], rec["source_sha256"]), ("deny", "terminal", SRC))
        self.assertEqual(len(rec["grant_sha256"]), 64)
        self.assertEqual(rec["contract_id"], SC.contract_id(Q, SRC))
        self.assertEqual(rec["args_keys"], ["command"])  # argument values are not logged

    def test_bypass_report_never_claims_enforcement(self):
        r = SB.bypass_report(hook_registered=True)
        self.assertFalse(r["enforcement_claimed"])
        self.assertEqual(r["enforcement_class"], "POLICY_ONLY / NOT_ISOLATED")
        self.assertTrue(any("slash" in p["path"] for p in r["bypass_paths"]))

    def test_internal_error_blocks(self):
        b = self.box()
        self.activate(b)
        b.grants = None  # corrupt state
        self.assertEqual(b.pre_tool_call(tool_name="write_file", args={"path": "/x"}, session_id="s")["action"], "block")

    def test_not_registered_in_release(self):
        self.assertNotIn("safebox", (ROOT / "__init__.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
