"""Offline P6 per-domain defaults consent and undo; no real Hermes actions."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p6_default_test_pkg", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)

from uvp_p6_default_test_pkg import uvp_p6_defaults as P6
from uvp_p6_default_test_pkg import uvp_plugin_router as ROUTER


class Host:
    def __init__(self, answers=(), *, surface="cli", installed=True):
        self.answers = list(answers)
        self.questions = []
        self.surface = surface
        self.installed = installed
        self.commands = {}
        self.calls = []
    def session_surface(self):
        return self.surface
    def ask_choice(self, q, options):
        self.questions.append((q, options))
        return self.answers.pop(0) if self.answers else None
    def dispatch_tool(self, name, args):
        self.calls.append((name, args))
        assert name == "skills_list" and args == {}
        names = [f"{P6.PLUGIN}:{skill}" for _, skill in P6.DOMAINS]
        if not self.installed:
            names.pop()
        return json.dumps({"success": True, "skills": [{"name": n} for n in names]})
    def register_command(self, name, handler=None, **kwargs):
        self.commands[name] = handler
    def register_tool(self, **kwargs):
        pass


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"HERMES_HOME": self.tmp.name}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.path = Path(self.tmp.name) / "uvp-data" / "p6-domain-defaults.json"

    def test_no_implicit_write_for_uninstalled_skills(self):
        h = Host(["make_default"] * 3, installed=False)
        r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "PORTED_SKILLS_NOT_INSTALLED")
        self.assertEqual(len(h.questions), 0)
        self.assertFalse(self.path.exists())

    def test_all_three_domains_separately_and_no_execution(self):
        h = Host(["make_default", "make_default", "make_default"])
        r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "UPDATED")
        self.assertEqual(r["changed_domains"], 3)
        self.assertEqual(len(h.questions), 3)
        self.assertEqual(len(h.calls), 1)
        self.assertEqual(r["permissions_added"], 0)
        self.assertFalse(r["skill_execution_performed"])
        self.assertFalse(r["network_execution_performed"])
        state = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(state["revision"], 1)
        self.assertEqual(set(state["domains"]), {"research", "documents", "planning"})
        self.assertEqual(state["domains"]["research"],
                         "ported-product-management:synthesize-research")

    def test_keep_existing_preserves_unrelated_domains(self):
        state = {"schema": P6.SCHEMA, "revision": 2,
                 "domains": {"research": "existing:research", "coding": "other:code"},
                 "history": []}
        P6._save(self.path, state)
        h = Host(["keep_existing", "make_default", "not_now"])
        r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "UPDATED")
        self.assertEqual(r["changed_domains"], 1)
        updated = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(updated["domains"]["research"], "existing:research")
        self.assertEqual(updated["domains"]["coding"], "other:code")
        self.assertNotIn("planning", updated["domains"])
        self.assertEqual(updated["domains"]["documents"],
                         "ported-product-management:write-spec")

    def test_cancel_discards_full_batch_even_after_prior_approval(self):
        h = Host(["make_default", None, "make_default"])
        r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "CHOICE_UNAVAILABLE_OR_CANCELLED")
        self.assertEqual(len(h.questions), 2)
        self.assertFalse(self.path.exists())

    def test_all_keep_now_means_no_write(self):
        h = Host(["not_now", "keep_existing", "not_now"])
        r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "UNCHANGED")
        self.assertFalse(self.path.exists())

    def test_undo_requires_fresh_confirmation(self):
        added = Host(["make_default", "not_now", "not_now"])
        self.assertEqual(P6.propose_domain_defaults(added)["status"], "UPDATED")
        denied = Host(["cancel"])
        self.assertEqual(P6.undo_last_defaults(denied)["status"], "RESTORE_NOT_APPROVED")
        self.assertTrue(json.loads(self.path.read_text())["domains"])
        approved = Host(["restore"])
        restored = P6.undo_last_defaults(approved)
        self.assertEqual(restored["status"], "RESTORED")
        self.assertEqual(json.loads(self.path.read_text())["domains"], {})

    def test_remote_surface_denied_before_catalog_read(self):
        h = Host(["make_default"] * 3, surface="telegram")
        r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "LOCAL_SESSION_REQUIRED")
        self.assertEqual(h.calls, [])
        self.assertEqual(h.questions, [])
        self.assertFalse(self.path.exists())

    def test_missing_hermes_home_denied(self):
        with patch.dict(os.environ, {"HERMES_HOME": ""}):
            h = Host(["make_default"] * 3)
            r = P6.propose_domain_defaults(h)
        self.assertEqual(r["status"], "DEFAULT_STORE_UNAVAILABLE")
        self.assertEqual(h.questions, [])

    def test_router_invokes_safe_host_scoped_path(self):
        h = Host(["make_default", "keep_existing", "not_now"])
        ROUTER.register_router(h)
        out = h.commands["uvp"]("--p6-defaults")
        report = json.loads(out.split("\n", 1)[1])
        self.assertEqual(report["status"], "UPDATED")
        self.assertEqual(report["changed_domains"], 1)
        self.assertTrue(self.path.exists())
        h.answers = ["restore"]
        out2 = h.commands["uvp"]("--p6-defaults-undo")
        report2 = json.loads(out2.split("\n", 1)[1])
        self.assertEqual(report2["status"], "RESTORED")
        self.assertFalse(report2["skill_execution_performed"])


if __name__ == "__main__":
    unittest.main()
