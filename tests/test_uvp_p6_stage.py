"""P6.1 staging checks; no network, foreign code execution or Hermes install."""
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p6_test_pkg", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)

from uvp_p6_test_pkg.port_core import PortError
from uvp_p6_test_pkg.uvp_p6_stage import stage_claude_skill_bundle

COMMIT = "e605d8ddbfb688da57dfaaceebd93f12a64ef1d3"


class P6StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "foreign"
        self.root.mkdir()
        (self.root / ".claude-plugin").mkdir()
        (self.root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "product-management", "version": "1.2.0"}),
            encoding="utf-8",
        )
        (self.root / ".mcp.json").write_text(json.dumps({
            "mcpServers": {"slack": {"type": "http", "url": "https://example.test/mcp"}}
        }), encoding="utf-8")
        for name in ("synthesize-research", "write-spec", "roadmap-update"):
            skill = self.root / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: " + name + "\ndescription: fixture\n---\n\n"
                "# " + name + "\nPerform $ARGUMENTS using the supplied notes.\n",
                encoding="utf-8",
            )
        self.out = Path(self.temp.name) / "staged"

    def _stage(self, **kwargs):
        return stage_claude_skill_bundle(
            str(self.root), str(self.out),
            declared_source_commit=COMMIT, **kwargs,
        )

    def test_no_implicit_staging(self):
        with self.assertRaises(PortError):
            self._stage(allow_partial=True)

    def test_no_implicit_unsupported_connector_discard(self):
        with self.assertRaises(PortError):
            self._stage(approved=True)

    def test_reject_weak_upstream_revision(self):
        with self.assertRaises(PortError):
            stage_claude_skill_bundle(
                str(self.root), str(self.out),
                approved=True, allow_partial=True,
                declared_source_commit="main",
            )

    def test_static_staged_plugin_preserves_all_three_skills(self):
        result = self._stage(approved=True, allow_partial=True)
        self.assertEqual(result["status"], "SKILLS_ONLY_PARTIAL")
        self.assertEqual(result["skills_staged"], 3)
        self.assertEqual(result["unported_connectors"], 1)
        self.assertFalse(result["installation_performed"])
        self.assertFalse(result["execution_performed"])
        target = Path(result["staged_path"])
        manifest = (target / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("name: ported-product-management", manifest)
        report = json.loads((target / "PORTING_REPORT.json").read_text(encoding="utf-8"))
        self.assertEqual(report["unported_connector_names"], ["slack"])
        self.assertTrue(all(x["copied_verbatim"] for x in report["skill_reviews"]))
        self.assertTrue(all(x["requires_manual_review"] for x in report["skill_reviews"]))
        originals = json.loads((target / "SOURCE_HASHES.json").read_text(encoding="utf-8"))
        self.assertIn("skills/write-spec/SKILL.md", originals)
        for name in ("synthesize-research", "write-spec", "roadmap-update"):
            before = (self.root / "skills" / name / "SKILL.md").read_bytes()
            self.assertEqual(before, (target / "original" / "skills" / name / "SKILL.md").read_bytes())
            self.assertEqual(before, (target / "skills" / name / "SKILL.md").read_bytes())

        # Exercise static registration without importing foreign code.
        generated = importlib.util.spec_from_file_location(
            "p6_static_generated", target / "__init__.py",
            submodule_search_locations=[str(target)],
        )
        pkg = importlib.util.module_from_spec(generated)
        generated.loader.exec_module(pkg)
        class Stub:
            def __init__(self):
                self.called = []
            def register_skill(self, name, path):
                self.called.append((name, path))
        stub = Stub()
        pkg.register(stub)
        self.assertEqual([n for n, _ in stub.called], sorted([
            "synthesize-research", "write-spec", "roadmap-update"
        ]))
        self.assertTrue(all(p.is_file() for _, p in stub.called))

    def test_refuse_overwrite_and_source_overlap(self):
        self._stage(approved=True, allow_partial=True)
        with self.assertRaises(PortError):
            self._stage(approved=True, allow_partial=True)
        with self.assertRaises(PortError):
            stage_claude_skill_bundle(
                str(self.root), str(self.root / "child"),
                approved=True, allow_partial=True,
                declared_source_commit=COMMIT,
            )

    def test_hermes_inline_shell_in_unreviewed_skill_is_blocked(self):
        skill = self.root / "skills" / "write-spec" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") +
                         "\nPotential auto-command !`whoami`\n", encoding="utf-8")
        with self.assertRaisesRegex(PortError, "inline-shell"):
            self._stage(approved=True, allow_partial=True)
        self.assertFalse((self.out / "ported-product-management").exists())

    def test_windows_crlf_preserved_in_hash_and_p6_patch_verification(self):
        from uvp_p6_test_pkg.uvp_p6_patch import checked_staged_skill
        name = "write-spec"
        source = self.root / "skills" / name / "SKILL.md"
        # Force Windows-style CRLF even when this test runs on Linux.
        source_bytes = source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        self.assertIn(b"\r\n", source_bytes)
        source.write_bytes(source_bytes)
        staged = self._stage(approved=True, allow_partial=True)
        location = Path(staged["staged_path"])
        report = json.loads((location / "PORTING_REPORT.json").read_text(encoding="utf-8"))
        row = next(x for x in report["skill_reviews"] if x["skill"] == name)
        self.assertEqual(row["original_sha256"], hashlib.sha256(source_bytes).hexdigest())
        self.assertEqual((location / "original" / "skills" / name / "SKILL.md").read_bytes(), source_bytes)
        self.assertEqual((location / "skills" / name / "SKILL.md").read_bytes(), source_bytes)
        _, verified = checked_staged_skill(str(location), name)
        self.assertEqual(verified, source_bytes)

    def test_without_connectors_no_partial_permission_required(self):
        (self.root / ".mcp.json").unlink()
        result = self._stage(approved=True)
        self.assertEqual(result["status"], "STAGED_UNVERIFIED")
        self.assertEqual(result["unported_connectors"], 0)
        self.assertFalse(result["execution_performed"])


if __name__ == "__main__":
    unittest.main()
