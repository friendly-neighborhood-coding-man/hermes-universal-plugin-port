"""P6.17 shared repair rules: positive cases, idempotence and fail-closed negatives (offline)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import repair_rules as RR  # noqa: E402

ADR = ("---\nname: adr\n---\n\n# Create ADR\n\nCreate an ADR for `${input:DecisionTitle}`.\n\n"
       "- **Context**: `${input:Context}`\n- **Decision**: `${input:Decision:what was decided}`\n\n"
       "## Input Validation\nIf any of the required inputs are not provided, ask the user to provide the missing information.\n\n"
       "```md\n# ADR-NNNN: [Decision Title]\n```\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.origin = t / "origin"
        self.sk = self.origin / "plugin" / "skills" / "uml"
        self.sk.mkdir(parents=True)
        (self.origin / "plugin" / "skills" / "layout").mkdir()
        (self.origin / "plugin" / "skills" / "layout" / "SKILL.md").write_text("# layout\n", encoding="utf-8")
        (self.origin / "plugin" / "references" / "foundations").mkdir(parents=True)
        (self.origin / "plugin" / "references" / "foundations" / "mobile.md").write_text("# mobile\n", encoding="utf-8")
        (self.origin / "plugin" / "CONNECTORS.md").write_text("# connectors\n", encoding="utf-8")
        self.installed = t / "installed"
        self.installed.mkdir()

    def plan(self, text):
        return RR.plan_skill(skill="uml", text=text, skill_dir=self.installed, origin_root=self.origin,
                             origin_skill_rel="plugin/skills/uml")


class InputVarsTests(Base):
    def test_rewrites_all_inputs_and_lists_them(self):
        p = self.plan(ADR)
        self.assertEqual([a["rule"] for a in p["applications"]], ["INPUT-VARS-1"])
        self.assertNotIn("${input:", p["new_text"])  # regression: correction 1 (the note quoted the syntax)
        for n in ("DecisionTitle", "Context", "Decision"):
            self.assertIn("[input: %s]" % n, p["new_text"])
        self.assertIn("ask the user for it before writing anything, and never invent it", p["new_text"])
        self.assertIn("ask the user to provide the missing information", p["new_text"])

    def test_idempotent(self):
        once = self.plan(ADR)["new_text"]
        again = self.plan(once)
        self.assertEqual(again["applications"], [])
        self.assertEqual(again["new_text"], once)

    def test_fenced_template_untouched(self):
        new = self.plan(ADR)["new_text"]
        self.assertIn("```md\n# ADR-NNNN: [Decision Title]\n```", new)

    def test_input_inside_fence_holds(self):
        p = self.plan(ADR + "\n```\nuse ${input:Secret}\n```\n")
        self.assertTrue(any(u["rule"] == "INPUT-VARS-1" for u in p["unresolved"]))
        self.assertEqual(p["applications"], [])

    def test_other_host_variables_hold(self):
        p = self.plan(ADR + "\nOpen ${workspaceFolder}/docs.\n")
        self.assertTrue(any("other than" in u["why"] for u in p["unresolved"]))

    def test_hermes_variables_are_not_flagged(self):
        p = self.plan("# T\n\nRun from ${HERMES_SKILL_DIR}.\n")
        self.assertEqual(p["unresolved"], [])

    def test_no_title_holds(self):
        p = self.plan("Create `${input:X}`.\n")
        self.assertTrue(any("H1" in u["why"] for u in p["unresolved"]))


class ResourceTests(Base):
    def test_closure_copies_shared_reference_into_skill_references(self):
        p = self.plan("# U\n\nUse `../../references/foundations/mobile.md` here.\n")
        self.assertEqual(p["applications"][0]["rule"], "RES-CLOSURE-1")
        self.assertIn("references/foundations/mobile.md", p["added"])
        self.assertIn("`references/foundations/mobile.md`", p["new_text"])

    def test_closure_missing_file_holds(self):
        p = self.plan("# U\n\nUse `../../references/foundations/absent.md`.\n")
        self.assertTrue(p["unresolved"])
        self.assertEqual(p["added"], {})

    def test_closure_escape_outside_origin_holds(self):
        p = self.plan("# U\n\nUse `../../../../../etc/passwd.md`.\n")
        self.assertTrue(p["unresolved"])
        self.assertEqual(p["added"], {})

    def test_closure_existing_destination_holds(self):
        (self.installed / "references" / "foundations").mkdir(parents=True)
        (self.installed / "references" / "foundations" / "mobile.md").write_text("x", encoding="utf-8")
        p = self.plan("# U\n\nUse `../../references/foundations/mobile.md`.\n")
        self.assertTrue(any("already exists" in u["why"] for u in p["unresolved"]))

    def test_sibling_skill_is_named_not_bundled(self):
        p = self.plan("# U\n\nRoute via `../layout/SKILL.md` first.\n")
        self.assertEqual(p["applications"][0]["rule"], "SKILL-REF-1")
        self.assertEqual(p["applications"][0]["required_skill"], "layout")
        self.assertEqual(p["added"], {})
        self.assertIn('skill_view("layout")', p["new_text"])
        self.assertNotIn("../layout/SKILL.md", p["new_text"])

    def test_missing_sibling_holds(self):
        p = self.plan("# U\n\nRoute via `../ghost/SKILL.md`.\n")
        self.assertTrue(any(u["rule"] == "SKILL-REF-1" for u in p["unresolved"]))

    def test_res_local_marks_connectors_not_connected(self):
        p = self.plan("# U\n\nSee [CONNECTORS.md](../../CONNECTORS.md).\n")
        self.assertEqual(p["applications"][0]["rule"], "RES-LOCAL-1")
        self.assertIn(b"NOT connected", p["added"]["CONNECTORS.md"])

    def test_unsupported_outside_reference_holds(self):
        p = self.plan("# U\n\nSee `../other/notes.md`.\n")
        self.assertTrue(any(u["rule"] is None for u in p["unresolved"]))


if __name__ == "__main__":
    unittest.main()
