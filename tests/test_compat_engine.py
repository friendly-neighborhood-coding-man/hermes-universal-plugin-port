"""P6 deterministic compatibility engine: offline tests, no model, no network."""
import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_compat_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_compat_test_pkg import compat_engine as E
from uvp_compat_test_pkg import uvp_p6_patch as PATCH
from uvp_compat_test_pkg.port_core import PortError
from uvp_compat_test_pkg.uvp_p6_stage import stage_claude_skill_bundle

COMMIT = "e605d8ddbfb688da57dfaaceebd93f12a64ef1d3"
REAL_STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")
REJECTED_SHA = "676ead16cc3574dffdcf3b7aa6913fbe97b171d168c14467310507187d3851a8"

WRITE_SPEC = (
    "---\n"
    "name: write-spec\n"
    "description: Write a feature spec or PRD from a problem statement.\n"
    "argument-hint: \"<feature or problem statement>\"\n"
    "---\n"
    "\n"
    "# Write Spec\n"
    "\n"
    "> If you see unfamiliar placeholders, see [CONNECTORS.md](../../CONNECTORS.md).\n"
    "\n"
    "Write a feature specification or product requirements document (PRD).\n"
    "\n"
    "## Usage\n"
    "\n"
    "```\n"
    "/write-spec $ARGUMENTS\n"
    "```\n"
    "\n"
    "## Workflow\n"
    "\n"
    "If **~~project tracker** is connected:\n"
    "- Search for related tickets\n"
    "\n"
    "See the [template](template.md) for structure.\n"
)


class FakeLLM:
    def __init__(self, edits):
        self.calls = 0
        self.edits = edits

    def complete_structured(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(parsed={"edits": self.edits, "limitations": [], "requires_manual_review": True})


def tree_hashes(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        self.registry = E.load_registry()
        self.identity = E.default_identity(self.registry)

    def make_stage(self, skill_text=WRITE_SPEC, skill="write-spec", extra_files=None):
        self.n = getattr(self, "n", 0) + 1
        src = self.t / ("foreign-%s-%d" % (skill, self.n))
        (src / ".claude-plugin").mkdir(parents=True)
        (src / ".claude-plugin" / "plugin.json").write_text('{"name":"product-management"}', encoding="utf-8")
        (src / ".mcp.json").write_text('{"mcpServers":{"linear":{"type":"http","url":"https://example.invalid"}}}',
                                       encoding="utf-8")
        (src / "CONNECTORS.md").write_text("# Connectors\n", encoding="utf-8")
        d = src / "skills" / skill
        d.mkdir(parents=True)
        (d / "SKILL.md").write_bytes(skill_text.encode("utf-8"))
        (d / "template.md").write_text("# Template\n", encoding="utf-8")
        for rel, content in (extra_files or {}).items():
            (src / rel).write_text(content, encoding="utf-8")
        out = stage_claude_skill_bundle(str(src), str(self.t / ("stage-%s-%d" % (skill, self.n))), approved=True,
                                        allow_partial=True, declared_source_commit=COMMIT)
        return Path(out["staged_path"])

    def catalog(self, stage):
        return E.stage_catalog(stage)

    def map_text(self, text, skill="write-spec", identity=None, registry=None, stage=None):
        stage = stage or self.make_stage(text, skill)
        return E.map_skill_text(text, skill=skill, catalog=self.catalog(stage),
                                registry=registry or self.registry, identity=identity or self.identity,
                                source_skill_dir=stage / "original" / "skills" / skill,
                                source_root=stage / "original",
                                target_skill_dir=stage / "skills" / skill, target_root=stage)

    def registry_copy(self, mutate):
        d = self.t / ("reg-%d" % len(list(self.t.glob("reg-*"))))
        (d / "semantics").mkdir(parents=True)
        for f in ("hermes_target_probe.json", "claude_argument_cases.json"):
            shutil.copy(ROOT / "semantics" / f, d / "semantics" / f)
        data = json.loads((ROOT / "compat_rules.json").read_text(encoding="utf-8"))
        mutate(data, d)
        (d / "compat_rules.json").write_text(json.dumps(data), encoding="utf-8")
        return d / "compat_rules.json"


class RegistryTests(Base):
    def test_registry_statuses_and_evidence(self):
        by = {r["id"]: r for r in self.registry["rules"]}
        self.assertEqual(by["R-C001"]["status"], "COMPOSED_VERIFIED")
        self.assertEqual(by["R-D001"]["status"], "DIRECT_EXACT")
        self.assertEqual(by["R-D002"]["status"], "PROVISIONAL")
        self.assertEqual(by["R-D003"]["status"], "PROVISIONAL")
        self.assertEqual(by["R-C001"]["_graph_order"], ["s1", "s2", "t1", "t2"])
        for r in by.values():
            self.assertEqual(set(r["axes"]), {"structural", "runtime", "semantic"})
            self.assertNotEqual(r["axes"]["semantic"], "VERIFIED")

    def _rejects(self, mutate, msg):
        with self.assertRaisesRegex(E.CompatRegistryError, msg):
            E.load_registry(self.registry_copy(mutate))

    def test_ambiguous_duplicate_construct_rejected(self):
        def m(data, d):
            dup = copy.deepcopy(data["rules"][0]); dup["id"] = "R-C002"; data["rules"].append(dup)
        self._rejects(m, "Ambiguous")

    def test_permission_network_or_side_effect_growth_rejected(self):
        for key, value in (("permissions", {"adds": [], "network": True, "execution": False, "authorization": []}),
                           ("permissions", {"adds": ["terminal"], "network": False, "execution": False, "authorization": []}),
                           ("permissions", {"adds": [], "network": False, "execution": False, "authorization": ["oauth"]}),
                           ("side_effects", ["writes_file"])):
            def m(data, d, key=key, value=value):
                data["rules"][0][key] = value
            self._rejects(m, "may not add")

    def test_cycle_and_missing_binding_rejected(self):
        def cycle(data, d):
            g = data["rules"][0]["graph"]
            g["nodes"][0]["inputs"].append("loop")
            g["nodes"][1]["outputs"].append("back")
            g["bindings"].append({"to": "s1.loop", "from": "s2.back"})
        self._rejects(cycle, "cycle")

        def missing(data, d):
            g = data["rules"][0]["graph"]
            g["bindings"] = [b for b in g["bindings"] if b["to"] != "t2.instruction"]
        self._rejects(missing, "missing input binding")

    def test_cross_side_binding_rejected(self):
        def m(data, d):
            g = data["rules"][0]["graph"]
            for b in g["bindings"]:
                if b["to"] == "t2.instruction":
                    b["from"] = "s1.raw_args"
            g["nodes"][3]["inputs"] = ["instruction"]
        self._rejects(m, "exchange data")

    def test_auto_rule_needs_behavioral_pass_evidence(self):
        def only_code_review(data, d):
            data["rules"][1]["validation"]["target_cases"] = ["H-INLINE-SHELL-DEFAULT-OFF-1"]
        self._rejects(only_code_review, "behavioral")

        def failed_case(data, d):
            p = d / "semantics" / "hermes_target_probe.json"
            probe = json.loads(p.read_text(encoding="utf-8"))
            next(c for c in probe["cases"] if c["id"] == "H-PASSTHROUGH-1")["result"] = "FAIL"
            raw = (json.dumps(probe, indent=2, sort_keys=True) + "\n").encode("utf-8")
            p.write_bytes(raw)
            data["evidence"]["hermes_target_probe"]["sha256"] = hashlib.sha256(raw).hexdigest()
        self._rejects(failed_case, "PASS")

    def test_tampered_evidence_rejected(self):
        def m(data, d):
            p = d / "semantics" / "hermes_target_probe.json"
            p.write_bytes(p.read_bytes() + b" ")
        self._rejects(m, "hash mismatch")

    def test_direct_exact_must_be_one_to_one(self):
        def m(data, d):
            data["rules"][1]["target"]["capabilities"].append("hermes.extra_cap")
        self._rejects(m, "1:1")

    def test_unimplemented_matcher_rejected(self):
        def m(data, d):
            data["rules"][1]["match"]["kind"] = "regex:.*"
        self._rejects(m, "unimplemented")


class MappingTests(Base):
    def test_verified_direct_mapping_zero_model_calls(self):
        text = "---\nname: write-spec\ndescription: d\n---\n\n# Plain\n\nJust write a clear spec.\n"
        stage = self.make_stage(text)
        r = self.map_text(text, stage=stage)
        self.assertEqual(r["model_calls"], 0)
        self.assertFalse(r["changed"])
        self.assertEqual(r["status"], "DETERMINISTIC_COMPLETE")
        self.assertTrue(r["matches"])
        self.assertTrue(all(m["rule_id"] == "R-D001" and m["status"] == "DIRECT_EXACT" for m in r["matches"]))
        llm = FakeLLM([])
        self.assertEqual(E.ai_fallback(SimpleNamespace(llm=llm), str(stage), "write-spec", r, approved=True)["status"],
                         "AI_NOT_NEEDED")
        self.assertEqual(llm.calls, 0)

    def test_verified_composition_mapping_zero_model_calls(self):
        stage = self.make_stage()
        r = self.map_text(WRITE_SPEC, stage=stage)
        self.assertEqual(r["model_calls"], 0)
        self.assertEqual(r["deltas"], [{"rule_id": "R-C001", "rule_version": 1, "line": 16,
                                        "old": "/write-spec $ARGUMENTS",
                                        "new": "/ported-product-management:write-spec <feature or problem statement>"}])
        comp = [m for m in r["matches"] if m["kind"] == "composition"]
        self.assertEqual(comp[0]["status"], "COMPOSED_VERIFIED")
        self.assertEqual(len(comp[0]["source_capabilities"]), 2)
        self.assertEqual(len(comp[0]["target_capabilities"]), 2)
        llm = FakeLLM([])
        self.assertEqual(E.ai_fallback(SimpleNamespace(llm=llm), str(stage), "write-spec", r, approved=True)["status"],
                         "AI_NOT_NEEDED")
        self.assertEqual(llm.calls, 0)

    def test_crlf_preserved_by_delta(self):
        text = WRITE_SPEC.replace("\n", "\r\n")
        r = self.map_text(text)
        self.assertIn("/ported-product-management:write-spec <feature or problem statement>\r\n", r["mapped_text"])
        self.assertEqual(r["mapped_text"].replace("/ported-product-management:write-spec <feature or problem statement>",
                                                  "/write-spec $ARGUMENTS"), text)

    def test_repeated_application_is_deterministic_and_idempotent(self):
        stage = self.make_stage()
        a = self.map_text(WRITE_SPEC, stage=stage)
        b = self.map_text(WRITE_SPEC, stage=stage)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        again = self.map_text(a["mapped_text"], stage=stage)
        self.assertFalse(again["changed"])
        self.assertEqual(again["mapped_text"], a["mapped_text"])
        self.assertIn("ALREADY_MAPPED", [m["outcome"] for m in again["matches"]])
        r1 = E.map_stage(str(stage), str(self.t / "run1"), registry=self.registry)
        r2 = E.map_stage(str(stage), str(self.t / "run2"), registry=self.registry)
        self.assertEqual(E._canon(r1), E._canon(r2))
        self.assertEqual((self.t / "run1" / "COMPAT_REPORT.json").read_bytes(),
                         (self.t / "run2" / "COMPAT_REPORT.json").read_bytes())

    def test_wrong_version_holds_without_guessing(self):
        for ident in ({"source": self.identity["source"], "target": "hermes-agent@" + "0" * 40},
                      {"source": "claude-code-command-args/1999-01-01", "target": self.identity["target"]}):
            r = self.map_text(WRITE_SPEC, identity=ident)
            self.assertEqual(r["status"], "HOLD")
            self.assertFalse(r["changed"])
            self.assertEqual(r["deltas"], [])
            self.assertEqual(r["model_calls"], 0)

    def test_missing_preconditions_hold(self):
        no_hint = WRITE_SPEC.replace('argument-hint: "<feature or problem statement>"\n', "")
        two = WRITE_SPEC.replace("Write a feature specification", "For $ARGUMENTS, write a feature specification")
        other_name = WRITE_SPEC.replace("/write-spec $ARGUMENTS", "/brainstorm $ARGUMENTS")
        for text, why in ((no_hint, "argument_hint_single_line"),
                          (two, "single_all_arguments_placeholder_in_file"),
                          (other_name, "usage_line_names_this_skill")):
            r = self.map_text(text)
            self.assertEqual(r["status"], "HOLD", why)
            self.assertFalse(r["changed"], why)
            self.assertTrue(any(why in h for h in r["holds"]), (why, r["holds"]))
            res = [x for x in r["residuals"] if x["kind"] == "arguments_placeholder"]
            self.assertIn("R-C001", res[0]["attempted_rule_ids"])

    def test_unregistered_skill_holds(self):
        stage = self.make_stage()
        cat = dict(self.catalog(stage), qualified=[], slash_keys=[])
        r = E.map_skill_text(WRITE_SPEC, skill="write-spec", catalog=cat, registry=self.registry,
                             identity=self.identity)
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["changed"])

    def test_provisional_rule_never_applies(self):
        text = WRITE_SPEC.replace("Write a feature specification", "Read ${CLAUDE_SKILL_DIR}/x. Write a feature specification")
        r = self.map_text(text)
        self.assertEqual(r["status"], "HOLD")
        res = [x for x in r["residuals"] if x["kind"] == "claude_host_variable"]
        self.assertEqual(res[0]["attempted_rule_ids"], ["R-D002"])
        self.assertIn("${CLAUDE_SKILL_DIR}", r["mapped_text"])
        self.assertFalse(any(m["rule_id"] == "R-D002" for m in r["matches"]))

    def test_six_constructs_are_distinct(self):
        r = self.map_text(WRITE_SPEC)
        c = r["constructs"]
        self.assertEqual(set(c), {"markdown_usage_example", "host_command_invocation", "skill_definition",
                                  "hermes_namespaced_registration", "runtime_skill_view_resolution",
                                  "user_input_passing"})
        self.assertFalse(c["markdown_usage_example"][0]["executed_by_either_host"])
        self.assertEqual(c["host_command_invocation"]["hermes_slash_form"],
                         "/ported-product-management:write-spec <user_text>")
        self.assertFalse(c["host_command_invocation"]["runtime_resolved"])
        self.assertEqual(c["hermes_namespaced_registration"]["qualified_name"], "ported-product-management:write-spec")
        self.assertFalse(c["runtime_skill_view_resolution"]["executed"])
        self.assertIn("NONE", c["runtime_skill_view_resolution"]["user_input_channel"])
        self.assertFalse(c["user_input_passing"]["hermes_substitutes_ARGUMENTS"])

    def test_relative_resources_resolved_or_reported(self):
        r = self.map_text(WRITE_SPEC)
        by = {x["link"]: x for x in r["resources"]}
        up = by["../../CONNECTORS.md"]
        self.assertTrue(up["resolves_in_source_tree"])
        self.assertFalse(up["resolves_in_target_tree"])
        self.assertFalse(up["hermes_skill_view_file_path_loadable"])
        ok = by["template.md"]
        self.assertTrue(ok["resolves_in_target_tree"])
        self.assertTrue(ok["hermes_skill_view_file_path_loadable"])
        unresolved = [x for x in r["residuals"] if x["kind"] == "unresolved_resource"]
        self.assertEqual(len(unresolved), 1)
        self.assertFalse(unresolved[0]["ai_eligible"])
        self.assertEqual(unresolved[0]["span"]["start_line"], 9)

    def test_connectors_stay_skills_only_partial(self):
        r = self.map_text(WRITE_SPEC)
        conn = [u for u in r["unsupported"] if u["kind"] == "connector_placeholder"]
        self.assertEqual([(u["category"], u["classification"]) for u in conn],
                         [("project tracker", "SKILLS_ONLY_PARTIAL")])
        self.assertIn("~~project tracker", r["mapped_text"])

    def test_residual_has_exact_span_context_and_reason(self):
        text = WRITE_SPEC.replace("Write a feature specification",
                                  "Use ${CLAUDE_PLUGIN_ROOT}. Write a feature specification")
        r = self.map_text(text)
        res = next(x for x in r["residuals"] if x["kind"] == "claude_host_variable")
        self.assertEqual(res["span"]["start_line"], 11)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", res["span"]["text"])
        self.assertEqual(len(res["span"]["context"]), 5)
        self.assertIn("NO_RULE", res["reason"])


class FallbackAndCandidateTests(Base):
    PROSE = "---\nname: write-spec\ndescription: Spec\n---\n\nGenerate a PRD for $ARGUMENTS, with acceptance criteria.\n"

    def test_ai_fallback_requires_explicit_approval(self):
        stage = self.make_stage(self.PROSE)
        r = self.map_text(self.PROSE, stage=stage)
        self.assertEqual(sum(1 for x in r["residuals"] if x["ai_eligible"]), 1)
        llm = FakeLLM([{"old": "$ARGUMENTS", "new": "the current Hermes user's request"}])
        out = E.ai_fallback(SimpleNamespace(llm=llm), str(stage), "write-spec", r)
        self.assertEqual(out["status"], "HOLD_OPERATOR_APPROVAL_REQUIRED")
        self.assertEqual(llm.calls, 0)

    def test_approved_fallback_is_candidate_only_with_post_checks(self):
        stage = self.make_stage(self.PROSE)
        before = tree_hashes(stage / "skills")
        r = self.map_text(self.PROSE, stage=stage)
        llm = FakeLLM([{"old": "$ARGUMENTS", "new": "the current Hermes user's request"}])
        out = E.ai_fallback(SimpleNamespace(llm=llm), str(stage), "write-spec", r, approved=True)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(out["status"], "REVIEW_REQUIRED")
        self.assertFalse(out["applied"])
        self.assertEqual(out["post_proposal_checks"]["verdict"], "PROMOTABLE_TO_REVIEW")
        self.assertEqual(before, tree_hashes(stage / "skills"))

    def test_rejected_write_spec_shape_cannot_be_promoted(self):
        stage = self.make_stage()
        llm = FakeLLM([{"old": "/write-spec $ARGUMENTS",
                        "new": "/write-spec <the current user's task: feature or problem statement>"}])
        prop = PATCH.propose(SimpleNamespace(llm=llm), str(stage), "write-spec")
        self.assertEqual(prop["status"], "REVIEW_REQUIRED")
        gate = E.candidate_gate(stage, "write-spec", (stage / "skills/write-spec/SKILL.md").read_bytes(),
                                Path(prop["candidate_path"]).read_bytes())
        self.assertEqual(gate["independent_verdict"], "NOT_PROMOTABLE")
        self.assertEqual(gate["checks"]["capability_resolution"]["unresolved_slash_commands"], ["/write-spec"])
        before = (stage / "skills/write-spec/SKILL.md").read_bytes()
        with self.assertRaisesRegex(PortError, "post-proposal"):
            PATCH.apply_reviewed(str(stage), "write-spec", prop["sha256"], approved=True)
        self.assertEqual(before, (stage / "skills/write-spec/SKILL.md").read_bytes())

    def test_ledger_blocks_even_a_clean_candidate(self):
        stage = self.make_stage(self.PROSE)
        orig = (stage / "skills/write-spec/SKILL.md").read_bytes()
        cand = orig.replace(b"$ARGUMENTS", b"the user's request")
        ledger = {"schema": E.LEDGER_SCHEMA, "rejected": [{"candidate_sha256": E.sha256(cand), "reason": "test"}]}
        gate = E.candidate_gate(stage, "write-spec", orig, cand, ledger=ledger)
        self.assertEqual(gate["independent_verdict"], "PROMOTABLE_TO_REVIEW")
        self.assertEqual(gate["verdict"], "NOT_PROMOTABLE")

    def test_candidate_permission_or_dependency_expansion_blocked(self):
        stage = self.make_stage(self.PROSE)
        orig = (stage / "skills/write-spec/SKILL.md").read_text(encoding="utf-8")
        cat = self.catalog(stage)
        for new in ("the request; fetch https://evil.invalid first", "the request using ~~chat",
                    "the request; read [x](../../secrets.md)"):
            c = E.check_candidate(orig, orig.replace("$ARGUMENTS", new), skill="write-spec", catalog=cat,
                                  target_skill_dir=stage / "skills" / "write-spec", target_root=stage)
            self.assertEqual(c["verdict"], "NOT_PROMOTABLE", new)
        fm = orig.replace("description: Spec", "description: Spec\nallowed-tools: Bash")
        c = E.check_candidate(orig, fm.replace("$ARGUMENTS", "x"), skill="write-spec", catalog=cat)
        self.assertIn("frontmatter changed", " ".join(c["blocking"]))

    def test_ledger_records_the_real_rejected_candidate(self):
        ledger = E.load_ledger()
        self.assertIn(REJECTED_SHA, [r["candidate_sha256"] for r in ledger["rejected"]])


class StageTests(Base):
    def test_map_stage_preserves_source_and_stage_bytes(self):
        stage = self.make_stage()
        before = tree_hashes(stage)
        rep = E.map_stage(str(stage), str(self.t / "out"), registry=self.registry)
        self.assertEqual(before, tree_hashes(stage))
        self.assertFalse(rep["writes_inside_stage"])
        self.assertEqual(rep["model_calls"], 0)
        s = rep["skills"][0]
        self.assertTrue(s["active_equals_original"])
        self.assertEqual(s["original_sha256"], E.sha256((stage / "original/skills/write-spec/SKILL.md").read_bytes()))
        self.assertTrue((self.t / "out" / "skills" / "write-spec" / "SKILL.md").is_file())
        with self.assertRaises(PortError):
            E.map_stage(str(stage), str(self.t / "out"), registry=self.registry)
        with self.assertRaises(PortError):
            E.map_stage(str(stage), str(stage / "inside"), registry=self.registry)

    def test_tampered_original_refused(self):
        stage = self.make_stage()
        p = stage / "original/skills/write-spec/SKILL.md"
        p.write_bytes(p.read_bytes() + b"\nextra")
        with self.assertRaisesRegex(PortError, "Unverifiable"):
            E.map_stage(str(stage), registry=self.registry)

    def test_report_keeps_axes_separate_and_has_no_success_percentage(self):
        rep = E.map_stage(str(self.make_stage()), registry=self.registry)
        blob = E._canon(rep).decode("utf-8").lower()
        for banned in ("percent", "success_rate", "equivalence_score"):
            self.assertNotIn(banned, blob)
        for s in rep["skills"]:
            self.assertEqual(set(s["verification"]), {"structural", "structural_gaps", "runtime", "semantic"})
            self.assertEqual(s["verification"]["semantic"], "NOT_ESTABLISHED")
            self.assertTrue(s["verification"]["runtime"].startswith("NOT_VERIFIED"))
            # The unresolved ../../CONNECTORS.md keeps structural from being claimed.
            self.assertEqual(s["verification"]["structural"], "NOT_VERIFIED")
            self.assertIn("unresolved_resource", s["verification"]["structural_gaps"])

    @unittest.skipUnless((REAL_STAGE / "PORTING_REPORT.json").is_file(), "operator stage not present")
    def test_real_stage_read_only_and_rejected_candidate_preserved(self):
        before = tree_hashes(REAL_STAGE)
        rep = E.map_stage(str(REAL_STAGE), registry=self.registry)
        self.assertEqual(before, tree_hashes(REAL_STAGE))
        self.assertEqual(rep["model_calls"], 0)
        ws = next(s for s in rep["skills"] if s["skill"] == "write-spec")
        self.assertEqual(ws["original_sha256"], "ca6670913878b4ac4582727562bfced5271492a5a800d934f68c9e7bc1cd4dcc")
        self.assertEqual([d["rule_id"] for d in ws["deltas"]], ["R-C001"])
        cand = next(c for c in rep["existing_review_candidates"] if c["skill"] == "write-spec")
        self.assertEqual(cand["candidate_sha256"], REJECTED_SHA)
        self.assertEqual(cand["verdict"], "NOT_PROMOTABLE")
        self.assertEqual(cand["independent_verdict"], "NOT_PROMOTABLE")
        self.assertIn("/write-spec", cand["checks"]["capability_resolution"]["unresolved_slash_commands"])


if __name__ == "__main__":
    unittest.main()
