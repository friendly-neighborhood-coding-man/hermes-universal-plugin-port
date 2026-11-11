"""P6.13 WP2/WP3: guided CLI gating (offline) and the adapted-package path (adapt + verify_package)."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import adapt_package as AP  # noqa: E402
import install_ops as IO  # noqa: E402
import uvp_guided as G  # noqa: E402
from port_core import PortError  # noqa: E402

REAL_STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = G.main(argv)
    return rc, json.loads(buf.getvalue())


class GuidedGatingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name) / "ws"
        self.ws.mkdir()
        st = {"schema": "universal-port.guided/1", "workspace": str(self.ws), "home": str(self.ws / "hermes-home"),
              "steps": {}, "source": "product-management", "source_path": str(self.ws / "source"),
              "stage": str(self.ws / "stage")}
        (self.ws / G.STATE).write_text(json.dumps(st), encoding="utf-8")

    def test_risky_steps_refuse_without_their_flag(self):
        for step in ("inspect", "stage", "install"):
            rc, out = run([step, "--workspace", str(self.ws)])
            self.assertEqual(rc, 1, step)
            self.assertFalse(out["ok"])
            self.assertIn("re-run with --i-", out["error"])
        self.assertEqual(json.loads((self.ws / G.STATE).read_text(encoding="utf-8"))["steps"], {})

    def test_unknown_source_and_missing_workspace(self):
        self.assertEqual(run(["select", "--workspace", str(self.ws), "--source", "nope"])[0], 1)
        rc, out = run(["status", "--workspace", str(self.ws / "missing")])
        self.assertEqual(rc, 1)
        self.assertIn("init", out["error"])

    def test_select_records_default_as_automatic(self):
        rc, out = run(["select", "--workspace", str(self.ws)])
        self.assertEqual(rc, 0)
        self.assertEqual(out["operator_inputs"], [])
        self.assertEqual(out["result"]["commit"], G.CATALOG["product-management"]["commit"])

    def test_undo_without_install_and_init_on_non_empty(self):
        self.assertEqual(run(["undo", "--workspace", str(self.ws)])[0], 1)
        rc, out = run(["init", "--workspace", str(self.ws)])
        self.assertEqual(rc, 1)
        self.assertIn("not empty", out["error"])

    def test_status_separates_operator_inputs(self):
        st = json.loads((self.ws / G.STATE).read_text(encoding="utf-8"))
        G.record(st, "init", operator_inputs=["--workspace"], automatic=["a", "b"], result={})
        G.record(st, "install", operator_inputs=["--i-approve-install"], automatic=["c"], result={})
        G.save(self.ws, st)
        rc, out = run(["status", "--workspace", str(self.ws)])
        self.assertEqual((rc, out["operator_input_count"], out["automatic_count"]), (0, 2, 3))


def _pkg(root: Path) -> Path:
    body = b"skill body\n"
    p = root / "pkg"
    for d in ("original/skills/s", "skills/s"):
        (p / d).mkdir(parents=True)
    (p / "original" / "skills" / "s" / "SKILL.md").write_bytes(body)
    h = hashlib.sha256(body).hexdigest()
    (p / "SOURCE_HASHES.json").write_text(json.dumps({"skills/s/SKILL.md": h}), encoding="utf-8")
    (p / "PORTING_REPORT.json").write_text(json.dumps({"skill_reviews": [{"skill": "s", "original_sha256": h}]}), encoding="utf-8")
    (p / "plugin.yaml").write_text("name: ported-x\n", encoding="utf-8")
    (p / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    adapted = b"<!-- notice -->\nskill body\n"
    (p / "skills" / "s" / "SKILL.md").write_bytes(adapted)
    man = {"changes": [{"path": "skills/s/SKILL.md", "after_sha256": hashlib.sha256(adapted).hexdigest(), "original_sha256": h}]}
    (p / "ADAPTATION_MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")
    return p


class AdaptationManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pkg = _pkg(Path(self.tmp.name))

    def test_declared_adaptation_verifies(self):
        self.assertTrue(IO.verify_package(self.pkg)["ok"])

    def test_undeclared_edit_after_adaptation_is_refused(self):
        (self.pkg / "skills" / "s" / "SKILL.md").write_bytes(b"<!-- notice -->\nskill body TAMPERED\n")
        r = IO.verify_package(self.pkg)
        self.assertFalse(r["ok"])
        self.assertIn("adaptation hash", r["why"])

    def test_adaptation_bound_to_another_original_is_refused(self):
        man = json.loads((self.pkg / "ADAPTATION_MANIFEST.json").read_text(encoding="utf-8"))
        man["changes"][0]["original_sha256"] = "0" * 64
        (self.pkg / "ADAPTATION_MANIFEST.json").write_text(json.dumps(man), encoding="utf-8")
        self.assertIn("different original", IO.verify_package(self.pkg)["why"])

    def test_without_manifest_active_must_equal_original(self):
        (self.pkg / "ADAPTATION_MANIFEST.json").unlink()
        self.assertFalse(IO.verify_package(self.pkg)["ok"])


@unittest.skipUnless(REAL_STAGE.is_dir(), "real P6 stage not present")
class AdaptRealStageTests(unittest.TestCase):
    def test_adapt_localizes_resources_and_keeps_originals(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "adapted"
            man = AP.adapt(str(REAL_STAGE), str(out))
            self.assertEqual(man["model_calls"], 0)
            self.assertTrue(IO.verify_package(out)["ok"])
            for f in (REAL_STAGE / "original").rglob("*"):
                if f.is_file():
                    self.assertEqual(f.read_bytes(), (out / "original" / f.relative_to(REAL_STAGE / "original")).read_bytes())
            added = [c for c in man["changes"] if c.get("rule") == "RES-LOCAL-1"]
            self.assertTrue(added)
            for c in added:
                text = (out / c["path"]).read_text(encoding="utf-8")
                self.assertIn("NOT connected", text)
                self.assertIn("4(b)", text)
            for skill in ("synthesize-research", "write-spec", "roadmap-update"):
                body = (out / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertNotIn("](../../CONNECTORS.md)", body)
                self.assertIn("](CONNECTORS.md)", body)
                self.assertTrue(body.startswith("---"))
            with self.assertRaises(PortError):
                AP.adapt(str(REAL_STAGE), str(out))


if __name__ == "__main__":
    unittest.main()
