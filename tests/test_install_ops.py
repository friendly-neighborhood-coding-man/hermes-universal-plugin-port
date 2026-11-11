"""P6.12 WP5: install / corrupted update / rollback / removal with manifests (offline, fixture home)."""
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p612w5_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p612w5_test_pkg import install_ops as IO
from uvp_p612w5_test_pkg.port_core import PortError


def make_pkg(root: Path, body="skill body\n") -> Path:
    p = root / "pkg"
    (p / "original" / "skills" / "s").mkdir(parents=True)
    (p / "skills" / "s").mkdir(parents=True)
    (p / "original" / "skills" / "s" / "SKILL.md").write_bytes(body.encode())
    (p / "skills" / "s" / "SKILL.md").write_bytes(body.encode())
    h = hashlib.sha256(body.encode()).hexdigest()
    (p / "SOURCE_HASHES.json").write_text(json.dumps({"skills/s/SKILL.md": h}), encoding="utf-8")
    (p / "PORTING_REPORT.json").write_text(json.dumps({"skill_reviews": [{"skill": "s", "original_sha256": h}]}), encoding="utf-8")
    (p / "plugin.yaml").write_text("name: ported-x\n", encoding="utf-8")
    (p / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    return p


class InstallOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.home = t / "home"
        (self.home / "plugins" / "unrelated").mkdir(parents=True)
        (self.home / "plugins" / "unrelated" / "plugin.yaml").write_text("name: unrelated\n", encoding="utf-8")
        (self.home / "config.yaml").write_text("plugins:\n  enabled:\n    - unrelated\n", encoding="utf-8")
        (self.home / IO.MARKER).write_text("disposable\n", encoding="utf-8")
        self.pkg = make_pkg(t)

        def enable(n):
            cfg = self.home / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + "    - %s\n" % n, encoding="utf-8")
        self.inst = IO.Installer(self.home, "ported-x", enable=enable, disable=lambda n: None,
                                 check=lambda: {"ok": (self.home / "plugins" / "ported-x" / "skills" / "s" / "SKILL.md").is_file()})

    def test_refuses_non_disposable_home(self):
        (self.home / IO.MARKER).unlink()
        with self.assertRaises(PortError):
            IO.Installer(self.home, "x")

    def test_full_cycle_returns_to_pre_install_state(self):
        s0 = IO.manifest(self.home)
        r = self.inst.install(self.pkg)
        self.assertTrue(r["ok"])
        s1 = IO.manifest(self.home)
        self.assertNotEqual(s0, s1)
        bad = Path(self.tmp.name) / "bad"
        shutil.copytree(self.pkg, bad)
        (bad / "skills" / "s" / "SKILL.md").write_text("tampered\n", encoding="utf-8")
        u = self.inst.update(bad)
        self.assertEqual(u["result"], "REFUSED_BEFORE_SWAP")
        self.assertEqual(IO.manifest(self.home), s1)
        broken = Path(self.tmp.name) / "broken"
        shutil.copytree(self.pkg, broken)
        self.inst.check = lambda: {"ok": False, "why": "resolution failed"}
        u2 = self.inst.update(broken)
        self.assertEqual(u2["result"], "ROLLED_BACK")
        self.assertTrue(u2["manifest_restored"])
        self.assertEqual(IO.manifest(self.home), s1)
        self.inst.rollback_to(Path(r["backup"]))
        self.assertEqual(IO.manifest(self.home), s0)
        self.assertTrue((self.home / "plugins" / "unrelated" / "plugin.yaml").is_file())

    def test_corrupt_init_refused(self):
        bad = Path(self.tmp.name) / "badinit"
        shutil.copytree(self.pkg, bad)
        (bad / "__init__.py").write_text("def register(ctx:\n", encoding="utf-8")
        self.assertFalse(IO.verify_package(bad)["ok"])

    def test_drop_from_plugin_lists(self):
        c = "plugins:\n  enabled:\n    - keep\n  disabled:\n    - ported-x\ndisplay:\n  compact: true\n"
        self.assertEqual(IO.drop_from_plugin_lists(c, "ported-x"),
                         "plugins:\n  enabled:\n    - keep\n  disabled: []\ndisplay:\n  compact: true\n")
        other = "tools:\n  enabled:\n    - ported-x\n"
        self.assertEqual(IO.drop_from_plugin_lists(other, "ported-x"), other)  # only the plugins block

    def test_remove(self):
        self.inst.install(self.pkg)
        r = self.inst.remove()
        self.assertTrue(r["ok"])
        self.assertFalse((self.home / "plugins" / "ported-x").exists())
        self.assertTrue((self.home / "plugins" / "unrelated").exists())


if __name__ == "__main__":
    unittest.main()
