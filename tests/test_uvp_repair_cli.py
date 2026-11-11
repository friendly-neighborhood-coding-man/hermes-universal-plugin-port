"""Offline tests for uvp_repair.py gates (no Hermes, no network). The real chain is reproduced by
scripts/uvp_repair_smoke.sh on a disposable Hermes home."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvp_repair as U  # noqa: E402


class RepairCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home, self.work = root / "home", root / "work"
        (self.home / "skills" / "claude-code-imports").mkdir(parents=True)
        (self.home / ".uvp-disposable").write_text("x")
        self.work.mkdir()
        U.save(self.work, {"schema": "uvp.repair/1", "home": str(self.home), "agent": "claude-code",
                           "category": "claude-code-imports", "origins": {}, "work": str(self.work), "steps": {}})
        (self.work / "REPAIR_PLAN.json").write_text(json.dumps({"plan_sha256": "p" * 64, "proposals": []}))
        (self.work / "candidate-F1").mkdir()
        (self.work / "candidate-F1" / "CANDIDATE.json").write_text(json.dumps({"candidate_digest": "c" * 64, "skill": "s"}))

    def main(self, *argv):
        err = io.StringIO()
        with patch("sys.stderr", err), patch("sys.stdout", io.StringIO()) as out, patch("sys.stdin", io.StringIO()):
            rc = U.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_apply_wrong_digest_never_reaches_apply(self):
        with patch.object(U.MR, "apply_candidate") as ap:
            rc, _, err = self.main("apply", "--work", str(self.work), "--finding", "F1", "--approve-digest", "0" * 64)
            ap.assert_not_called()
        self.assertEqual(rc, 2)
        self.assertIn("does not match", err)

    def test_apply_requires_interactive_operator_terminal(self):
        with patch.object(U.MR, "apply_candidate") as ap:
            rc, _, err = self.main("apply", "--work", str(self.work), "--finding", "F1", "--approve-digest", "c" * 64)
            ap.assert_not_called()
        self.assertEqual(rc, 2)
        self.assertIn("interactive terminal", err)

    def test_apply_hold_from_engine_is_reported(self):
        with patch.object(U.MR, "apply_candidate", side_effect=U.MR.RepairError("replay refused")):
            rc, _, err = self.main("apply", "--work", str(self.work), "--finding", "F1", "--approve-digest", "c" * 64,
                                   "--test-driver")
        self.assertEqual(rc, 2)
        self.assertIn("replay refused", err)

    def test_typed_confirmation_must_match(self):
        a = type("A", (), {"work": str(self.work), "finding": "F1", "approve_digest": "c" * 64, "test_driver": False})
        with patch.object(U.sys.stdin, "isatty", return_value=True, create=True), \
                patch.object(U.sys.stdout, "isatty", return_value=True, create=True), \
                patch("builtins.input", return_value="APPLY wrong"), patch.object(U.MR, "apply_candidate") as ap:
            with self.assertRaises(U.CliError):
                U.cmd_apply(a)
            ap.assert_not_called()

    def test_doctor_refuses_work_dir_inside_home_and_empty_import(self):
        rc, _, err = self.main("doctor", "--home", str(self.home), "--work", str(self.home / "w"))
        self.assertEqual(rc, 2)
        self.assertIn("outside the Hermes home", err)
        rc, _, err = self.main("doctor", "--home", str(self.home), "--work", str(Path(self.tmp.name) / "w2"))
        self.assertEqual(rc, 2)
        self.assertIn("official Hermes importer", err)

    def test_origin_spec_is_validated(self):
        with self.assertRaises(U.CliError):
            U.parse_origin("no-equals-sign")
        with self.assertRaises(U.CliError):
            U.parse_origin("s=%s::missing/skill" % self.tmp.name)

    def test_steps_need_doctor_first(self):
        rc, _, err = self.main("plan", "--work", str(Path(self.tmp.name) / "fresh"))
        self.assertEqual(rc, 2)
        self.assertIn("run `doctor` first", err)


if __name__ == "__main__":
    unittest.main()
