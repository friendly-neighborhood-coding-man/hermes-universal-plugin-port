"""P6.14 WP1: the guided installer installs the exact approved ADAPTED candidate, never the verbatim stage."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install_ops as IO  # noqa: E402
import uvp_guided as G  # noqa: E402

REAL_STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = G.main(argv)
    return rc, json.loads(buf.getvalue())


@unittest.skipUnless(REAL_STAGE.is_dir(), "real P6 stage not present")
class AdaptedInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name) / "ws"
        home = self.ws / "hermes-home"
        (home / "plugins").mkdir(parents=True)
        (home / IO.MARKER).write_text("test\n", encoding="utf-8")
        (home / "config.yaml").write_text("plugins:\n  enabled: []\n  disabled: []\n", encoding="utf-8")
        (home / "existing-user-note.txt").write_text("keep me\n", encoding="utf-8")
        stage = self.ws / "stage" / "ported-product-management"
        shutil.copytree(REAL_STAGE, stage, ignore=shutil.ignore_patterns("__pycache__", "P6_REVIEW_CANDIDATES"))
        self.stage = stage
        st = {"schema": "universal-port.guided/1", "workspace": str(self.ws), "home": str(home), "steps": {},
              "source": "product-management", "stage": str(stage)}
        (self.ws / G.STATE).write_text(json.dumps(st), encoding="utf-8")
        self.home = home
        # No real Hermes in unit tests: CLI calls succeed, the runtime check is replaced.
        p1 = mock.patch.object(G, "hermes", lambda st, *a, **k: (0, ""))
        p2 = mock.patch.object(G, "_verify", lambda st, quiet=False: {"ok": True})
        p1.start(), p2.start()
        self.addCleanup(mock.patch.stopall)

    def ws_arg(self):
        return ["--workspace", str(self.ws)]

    def adapt(self):
        rc, out = run(["adapt"] + self.ws_arg())
        self.assertEqual(rc, 0, out)
        return out["result"]["candidate_digest"]

    def test_adapt_makes_a_separate_candidate_and_review(self):
        before = IO.package_digest(self.stage)
        digest = self.adapt()
        self.assertEqual(IO.package_digest(self.stage), before)
        review = json.loads((self.ws / "CANDIDATE_REVIEW.json").read_text(encoding="utf-8"))
        self.assertEqual(review["candidate_digest"], digest)
        self.assertNotEqual(digest, before)
        self.assertTrue(review["originals_preserved"]["identical_to_stage"])
        self.assertIn("RES-LOCAL-1", review["rules_applied"])
        self.assertTrue(any(c["changed_spans"] for c in review["files_changed_by_uvp"]))
        self.assertIn(digest, (self.ws / "CANDIDATE_REVIEW.md").read_text(encoding="utf-8"))
        self.assertEqual(len(review["unsupported_not_installed"]["connectors"]), 16)
        self.assertEqual(run(["adapt"] + self.ws_arg())[0], 1)  # never overwrites a candidate

    def test_approval_binds_to_the_exact_digest(self):
        digest = self.adapt()
        self.assertEqual(run(["approve"] + self.ws_arg())[0], 1)
        self.assertEqual(run(["approve"] + self.ws_arg() + ["--candidate-digest", "0" * 64])[0], 1)
        rc, out = run(["approve"] + self.ws_arg() + ["--candidate-digest", digest])
        self.assertEqual((rc, out["result"]["approved_digest"]), (0, digest))

    def test_install_refuses_without_approval(self):
        self.adapt()
        rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 1)
        self.assertIn("No approval", out["error"])
        self.assertFalse((self.home / "plugins" / "ported-product-management").exists())

    def test_install_refuses_a_candidate_modified_after_approval(self):
        digest = self.adapt()
        run(["approve"] + self.ws_arg() + ["--candidate-digest", digest])
        f = self.ws / "candidate" / "ported-product-management" / "skills" / "write-spec" / "SKILL.md"
        f.write_bytes(f.read_bytes() + b"\nInjected after review.\n")
        rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 1)
        self.assertIn("changed after approval", out["error"])
        self.assertFalse((self.home / "plugins" / "ported-product-management").exists())

    def test_install_refuses_permission_escalation_even_if_reapproved(self):
        self.adapt()
        cand = self.ws / "candidate" / "ported-product-management"
        (cand / "__init__.py").write_text("def register(ctx):\n    ctx.register_tool(name='x')\n", encoding="utf-8")
        st = json.loads((self.ws / G.STATE).read_text(encoding="utf-8"))
        st["candidate_digest"] = IO.package_digest(cand)
        G.save(self.ws, st)
        run(["approve"] + self.ws_arg() + ["--candidate-digest", st["candidate_digest"]])
        rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 1)
        self.assertIn("escalation", out["error"])

    def test_install_refuses_source_hash_mismatch(self):
        self.adapt()
        cand = self.ws / "candidate" / "ported-product-management"
        f = next((cand / "original").rglob("SKILL.md"))
        f.write_bytes(f.read_bytes() + b" ")
        st = json.loads((self.ws / G.STATE).read_text(encoding="utf-8"))
        st["candidate_digest"] = IO.package_digest(cand)
        G.save(self.ws, st)
        run(["approve"] + self.ws_arg() + ["--candidate-digest", st["candidate_digest"]])
        rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 1)
        self.assertRegex(out["error"], "hash|failed")

    def test_install_refuses_overwrite(self):
        digest = self.adapt()
        run(["approve"] + self.ws_arg() + ["--candidate-digest", digest])
        (self.home / "plugins" / "ported-product-management").mkdir()
        rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 1)
        self.assertIn("overwrite", out["error"])

    def test_install_puts_down_the_approved_bytes_and_undo_reports_residuals(self):
        digest = self.adapt()
        run(["approve"] + self.ws_arg() + ["--candidate-digest", digest])
        rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 0, out)
        target = self.home / "plugins" / "ported-product-management"
        self.assertEqual(IO.package_digest(target), digest)
        self.assertNotEqual(IO.package_digest(target), IO.package_digest(self.stage))
        receipt = json.loads((self.ws / "INSTALL_RECEIPT.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt["match"])
        self.assertTrue((target / "skills" / "write-spec" / "CONNECTORS.md").is_file())
        rc, out = run(["undo"] + self.ws_arg())
        self.assertEqual(rc, 0, out)
        self.assertFalse(target.exists())
        u = json.loads((self.ws / "UNDO_RECEIPT.json").read_text(encoding="utf-8"))
        self.assertTrue(u["config_yaml_identical"])
        classes = {d["class"] for d in u["differences"]}
        self.assertLessEqual(classes, {"EXPECTED_AUDIT_BACKUP"})
        self.assertGreaterEqual(u["summary"]["EXISTING_DATA_PRESERVED"], 3)
        self.assertEqual(u["summary"]["UVP_CREATED_AND_REMOVED"], u["uvp_installed_files"])
        self.assertGreater(u["uvp_installed_files"], 20)

    def test_failed_runtime_check_rolls_back(self):
        digest = self.adapt()
        run(["approve"] + self.ws_arg() + ["--candidate-digest", digest])
        with mock.patch.object(G, "_verify", lambda st, quiet=False: {"ok": False, "why": "simulated"}):
            rc, out = run(["install"] + self.ws_arg() + ["--i-approve-install"])
        self.assertEqual(rc, 1)
        self.assertIn("rolled back", out["error"])
        self.assertFalse((self.home / "plugins" / "ported-product-management").exists())


class RedirectTests(unittest.TestCase):
    def test_symlink_inside_package_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            pkg = Path(t) / "pkg"
            pkg.mkdir()
            (pkg / "a.txt").write_text("a", encoding="utf-8")
            try:
                os.symlink(str(pkg / "a.txt"), str(pkg / "link.txt"))
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not permitted here")
            with self.assertRaises(G.PortError):
                IO.package_digest(pkg)

    def test_classify_residuals(self):
        before = {"config.yaml": {"type": "file", "sha256": "a"}, "logs": {"type": "dir"}}
        after = {"config.yaml": {"type": "file", "sha256": "a"}, "logs": {"type": "dir"},
                 "logs/x.log": {"type": "file", "sha256": "b"}, "weird.txt": {"type": "file", "sha256": "c"},
                 "plugins/p/left.txt": {"type": "file", "sha256": "d"}}
        r = IO.classify_residuals(before, after, plugin="p")
        by = {d["path"]: d["class"] for d in r["differences"]}
        self.assertEqual(by, {"logs/x.log": "HERMES_RUNTIME_STATE", "weird.txt": "UNATTRIBUTED",
                              "plugins/p/left.txt": "UNEXPECTED_RESIDUAL"})
        self.assertTrue(r["config_yaml_identical"])
        self.assertFalse(r["full_home_byte_identical"])


if __name__ == "__main__":
    unittest.main()
