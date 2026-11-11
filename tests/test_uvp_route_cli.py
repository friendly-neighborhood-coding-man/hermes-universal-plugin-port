"""Subprocess smoke checks for the offline UVP routing CLI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "uvp_route_cli.py"


class RoutingCLITests(unittest.TestCase):
    def test_default_registry_is_empty_and_never_dispatches(self):
        proc = subprocess.run([sys.executable, str(CLI), "--prompt", "research paper"],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "PLAN_INCOMPLETE")
        self.assertFalse(result["execution_performed"])
        self.assertEqual(result["selected"], [])

    def test_offline_skills_snapshot_is_advisory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skills.json"
            path.write_text(json.dumps({"success": True, "skills": [
                {"name": "research", "description": "research skill"}]}), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(CLI), "--prompt", "research paper",
                                   "--skills-list", str(path)],
                                  capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["catalog_audit"]["skills_seen"], 1)
        self.assertFalse(result["selected"])
        self.assertEqual(result["status"], "PLAN_INCOMPLETE")

    def test_bad_skill_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skills.json"
            path.write_text('{"success":false,"skills":[]}', encoding="utf-8")
            proc = subprocess.run([sys.executable, str(CLI), "--prompt", "coding",
                                   "--skills-list", str(path)],
                                  capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(json.loads(proc.stdout)["execution_performed"])


if __name__ == "__main__":
    unittest.main()
