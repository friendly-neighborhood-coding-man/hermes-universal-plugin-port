"""P6.16: outcome model, Doctor -> Planner -> Executor -> Apply, and the negative corpus (offline, synthetic)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import migration_repair as MR  # noqa: E402

SKILL_MD = "---\nname: synth\ndescription: x\n---\n\n> see [CONNECTORS.md](../../CONNECTORS.md).\n\n/synth $ARGUMENTS\n"


def rt(skills, links_ok=False, view_ok=True):
    return {"status": MR.PASS if view_ok else MR.FAIL, "verifier": MR.VERIFIER_VERSION, "skills": {
        s: {"skill_view": view_ok, "slash_key": "/" + s, "links": {"../../CONNECTORS.md": {"success": links_ok,
            "error": None if links_ok else "Path traversal ('..') is not allowed."}}} for s in skills}}


class GateTests(unittest.TestCase):
    def test_broken_resource_fails_functional_even_when_install_and_runtime_pass(self):
        v = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=rt(["synth"]), static={"synth": {}})
        self.assertEqual(v["gates"]["INSTALL_INTEGRITY"], "PASS")
        self.assertEqual(v["gates"]["RUNTIME_VERIFICATION"], "PASS")
        self.assertEqual(v["gates"]["FUNCTIONAL_COMPATIBILITY"], "FAIL")
        self.assertEqual(v["final_gate"], "HOLD")

    def test_missing_or_failed_runtime_verification_holds(self):
        cases = [{"status": "NOT_VERIFIED", "reason": "Hermes Python interpreter unavailable"},
                 {"status": "FAIL", "reason": "verifier exited 1"},
                 {"status": "FAIL", "reason": "malformed verifier output"}]
        for runtime in cases:
            v = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=runtime, static={"synth": {}})
            self.assertEqual(v["final_gate"], "HOLD", runtime)
            self.assertEqual(v["gates"]["FUNCTIONAL_COMPATIBILITY"], "NOT_VERIFIED")

    def test_runner_reports_not_verified_without_interpreter(self):
        r = MR.run_hermes_verifier(Path("."), ["synth"], None, None)
        self.assertEqual(r["status"], "NOT_VERIFIED")
        r = MR.run_hermes_verifier(Path("."), ["synth"], sys.executable, str(ROOT))  # no Hermes modules there
        self.assertEqual(r["status"], "FAIL")

    def test_declared_dependencies_are_not_verified_not_pass(self):
        ok = rt(["pdf"], links_ok=True)
        ok["skills"]["pdf"]["links"] = {}
        v = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=ok,
                              static={"pdf": {"python_packages_declared": ["pypdf"]}})
        self.assertEqual(v["gates"]["FUNCTIONAL_COMPATIBILITY"], "NOT_VERIFIED")
        self.assertEqual(v["final_gate"], "HOLD")

    def test_all_pass_only_when_everything_passes(self):
        ok = rt(["s"], links_ok=True)
        v = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=ok, static={"s": {}})
        self.assertEqual(v["final_gate"], "PASS")
        v = MR.evaluate_gates(install_ok=False, install_detail={}, runtime=ok, static={"s": {}})
        self.assertEqual(v["final_gate"], "HOLD")


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.home = t / "home"
        self.skill = self.home / "skills" / "claude-code-imports" / "synth"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        (self.home / ".uvp-disposable").write_text("x", encoding="utf-8")
        other = self.home / "skills" / "claude-code-imports" / "other"
        other.mkdir()
        (other / "SKILL.md").write_text("---\nname: other\n---\nok\n", encoding="utf-8")
        self.origin = t / "origin"
        (self.origin / "pm" / "skills" / "synth").mkdir(parents=True)
        (self.origin / "pm" / "CONNECTORS.md").write_text("# Connectors\n~~chat\n", encoding="utf-8")
        self.origins = {"synth": {"root": str(self.origin), "skill_rel": "pm/skills/synth", "commit": "abc"}}
        self.work = t / "work"
        self.work.mkdir()
        self.findings = MR.doctor_findings(rt(["synth"]), {"synth": {"host_argument_tokens": ["$ARGUMENTS"]}})
        self.plan = MR.plan_repairs(self.findings, home=self.home, agent_category="claude-code-imports", origins=self.origins)
        self.fid = next(f["finding_id"] for f in self.findings if f["kind"] == "BROKEN_RELATIVE_RESOURCE")

    def build(self, name="cand"):
        return MR.build_candidate(self.plan, self.fid, home=self.home, origins=self.origins, out_dir=self.work / name)

    def apply(self, cand, digest=None, tag="a"):
        return MR.apply_candidate(home=self.home, plan=self.plan, candidate=cand,
                                  approved_digest=digest or cand["candidate_digest"], ledger=self.work / "ledger.json",
                                  backup_dir=self.work / ("backup-" + tag), journal=self.work / ("journal-%s.json" % tag))

    def test_planner_classifies_each_finding(self):
        by = {p["finding_id"]: p["classification"] for p in self.plan["proposals"]}
        self.assertEqual(by[self.fid], "DETERMINISTIC_REPAIR_AVAILABLE")
        self.assertEqual(by["F-ARG-synth"], "INSUFFICIENT_EVIDENCE")
        prop = next(p for p in self.plan["proposals"] if p["finding_id"] == self.fid)
        self.assertEqual((prop["rule_id"], prop["rule_version"]), ("RES-LOCAL-1", 1))
        self.assertEqual([f["path"] for f in prop["files"]], ["SKILL.md", "CONNECTORS.md"])
        self.assertTrue(prop["acceptance_tests"] and prop["rollback"] and prop["human_approval_required"])

    def test_dependency_finding_is_never_auto_repaired(self):
        f = MR.doctor_findings({"status": "PASS", "skills": {}}, {"pdf": {"python_packages_declared": ["pypdf"]}})
        plan = MR.plan_repairs(f, home=self.home, agent_category="claude-code-imports", origins={})
        self.assertEqual(plan["proposals"][0]["classification"], "DEPENDENCY_ACTION_REQUIRED")
        with self.assertRaises(MR.RepairError):
            MR.build_candidate(plan, f[0]["finding_id"], home=self.home, origins={}, out_dir=self.work / "x")

    def test_unmatched_rule_gives_no_patch(self):
        (self.origin / "pm" / "CONNECTORS.md").unlink()
        plan = MR.plan_repairs(self.findings, home=self.home, agent_category="claude-code-imports", origins=self.origins)
        prop = next(p for p in plan["proposals"] if p["finding_id"] == self.fid)
        self.assertNotEqual(prop["classification"], "DETERMINISTIC_REPAIR_AVAILABLE")
        with self.assertRaises(MR.RepairError):
            MR.build_candidate(plan, self.fid, home=self.home, origins=self.origins, out_dir=self.work / "x")

    def test_candidate_is_isolated_and_bounded(self):
        before = MR.dir_digest(self.skill)
        cand = self.build()
        self.assertEqual(MR.dir_digest(self.skill), before)
        self.assertEqual(cand["changed_files"], ["CONNECTORS.md", "SKILL.md"])
        text = (Path(cand["candidate_dir"]) / "CONNECTORS.md").read_text(encoding="utf-8")
        self.assertIn("NOT connected", text)
        self.assertTrue(any("](CONNECTORS.md)" in l for l in cand["diff"]))
        with self.assertRaises(MR.RepairError):
            self.build()  # never overwrites a candidate directory

    def test_happy_apply_then_rollback(self):
        orig = MR.dir_digest(self.skill)
        cand = self.build()
        r = self.apply(cand)
        self.assertEqual(r["state"], "COMMITTED")
        self.assertEqual(MR.dir_digest(self.skill), cand["candidate_digest"])
        rb = MR.rollback_candidate(home=self.home, journal=self.work / "journal-a.json")
        self.assertEqual(rb["classification"], "ROLLED_BACK")
        self.assertEqual(MR.dir_digest(self.skill), orig)

    def test_wrong_digest_holds(self):
        cand = self.build()
        with self.assertRaises(MR.RepairError):
            self.apply(cand, digest="0" * 64)
        self.assertFalse((self.skill / "CONNECTORS.md").exists())

    def test_changed_candidate_holds(self):
        cand = self.build()
        (Path(cand["candidate_dir"]) / "extra.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(MR.RepairError):
            self.apply(cand)
        self.assertFalse((self.skill / "CONNECTORS.md").exists())

    def test_changed_target_holds(self):
        cand = self.build()
        (self.skill / "SKILL.md").write_text(SKILL_MD + "\nedited\n", encoding="utf-8")
        with self.assertRaises(MR.RepairError):
            self.apply(cand)

    def test_changed_source_origin_holds_at_build(self):
        (self.origin / "pm" / "CONNECTORS.md").write_text("# changed\n", encoding="utf-8")
        with self.assertRaises(MR.RepairError):
            self.build()

    def test_tampered_plan_holds(self):
        cand = self.build()
        self.plan["proposals"][0]["files"][0]["new"] = "](../../../etc/passwd)"
        with self.assertRaises(MR.RepairError):
            self.apply(cand)
        with self.assertRaises(MR.RepairError):
            self.build("cand2")

    def test_approval_replay_is_rejected(self):
        cand = self.build()
        self.apply(cand)
        MR.rollback_candidate(home=self.home, journal=self.work / "journal-a.json")
        with self.assertRaises(MR.RepairError) as cm:
            self.apply(cand, tag="b")
        self.assertIn("replay", str(cm.exception))

    def test_unexpected_change_in_candidate_is_refused_at_build(self):
        real = MR._plan_res_local

        def widened(*a, **k):
            p = real(*a, **k)
            p._new["evil.sh"] = b"rm -rf /"
            return p
        MR._plan_res_local = widened
        try:
            with self.assertRaises(MR.RepairError):
                self.build()
        finally:
            MR._plan_res_local = real

    def test_interrupted_apply_is_not_called_rolled_back(self):
        j = self.work / "journal-x.json"
        j.write_text(json.dumps({"state": "STARTED", "skill_dir": str(self.skill)}), encoding="utf-8")
        r = MR.rollback_candidate(home=self.home, journal=j)
        self.assertEqual(r["classification"], "INTERRUPTED_RECOVERY_NOT_VERIFIED")

    def test_broken_resource_after_repair_fails_functional(self):
        still_broken = rt(["synth"])
        still_broken["skills"]["synth"]["links"] = {"CONNECTORS.md": {"success": False, "error": "missing"}}
        v = MR.evaluate_gates(install_ok=True, install_detail={}, runtime=still_broken, static={"synth": {}},
                              repair={"status": "FAIL"})
        self.assertEqual(v["gates"]["FUNCTIONAL_COMPATIBILITY"], "FAIL")
        self.assertEqual(v["final_gate"], "HOLD")

    def test_paths_inside_target_are_refused(self):
        cand = self.build()
        with self.assertRaises(MR.RepairError):
            MR.apply_candidate(home=self.home, plan=self.plan, candidate=cand, approved_digest=cand["candidate_digest"],
                               ledger=self.home / "ledger.json", backup_dir=self.work / "b", journal=self.work / "j.json")


if __name__ == "__main__":
    unittest.main()
