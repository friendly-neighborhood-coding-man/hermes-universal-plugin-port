"""P6.7 semantic review loop: offline tests with mocks and fixtures. No model calls."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p67_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p67_test_pkg import semantic_review as SR
from uvp_p67_test_pkg.port_core import PortError

REAL_STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")
REAL_RUN = ROOT / "docs" / "evidence" / "p6-e2e-run-001"
REAL_VERIFY = ROOT / "docs" / "evidence" / "p6-runtime" / "verify-001.json"

SKILL = ("# S\n\n#### Opportunity Areas\nAsk the user what they have:\n"
         "If **~~project tracker** is connected:\n- **Now** (current sprint/month): Committed work.\n")
FIXTURE = '# fx\n\n## I01\n"Alpha beta."\n'
SYN_OK = '# Syn\n\n## Opportunity Areas\nSaid: "Alpha beta." I01 I02 I03 I04 I05 I06 I07 I08\n'
SYN_MISSING = '# Syn\n\nSaid: "Alpha beta." I01 I02 I03 I04 I05 I06 I07 I08\n'
PRD = "# PRD\n- OQ-2 (Eng, blocking for REQ-1): threshold?\n"
ROADMAP = ("# Onboarding Roadmap (Now / Next / Later) — PROPOSAL\n\n### NOW (proposed)\n\n"
           "| Item | Description | Status | Target | Owner | Key dependencies |\n|---|---|---|---|---|---|\n"
           "| B. Progress | spinner | Not Started | Now | TBD | OQ-2 timeout threshold (blocking) |\n\n### NEXT\n")
STREAM = "\n".join(json.dumps(e) for e in [
    {"type": "system", "subtype": "init"},
    {"type": "tool_use", "name": "skill_view", "input": {}},
    {"type": "tool_use", "name": "write_file", "input": {}},
    {"type": "result", "exit_code": 0},
]) + "\n"


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Fixture:
    def __init__(self, tmp, synthesis=SYN_MISSING, stream=STREAM):
        t = Path(tmp)
        self.stage = t / "stage"
        sk = self.stage / "original" / "skills" / "synthesize-research"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_bytes(SKILL.encode())
        (self.stage / "PORTING_REPORT.json").write_text(json.dumps(
            {"status": "SKILLS_ONLY_PARTIAL", "unported_connector_names": ["linear"]}), encoding="utf-8")
        self.run = t / "run"
        (self.run / "inputs").mkdir(parents=True)
        files = {"research-synthesis.md": synthesis, "onboarding-prd.md": PRD, "onboarding-roadmap.md": ROADMAP,
                 "stream.jsonl": stream, "RUN_RECEIPT.json": "{}\n", "inputs/p6-onboarding-interviews.md": FIXTURE}
        self.pins = {}
        for rel, text in files.items():
            (self.run / rel).write_bytes(text.encode())
            self.pins[rel] = sha(text.encode())
        self.verify = t / "verify.json"
        vb = json.dumps({"checks": [
            {"id": "R3-skill_view:synthesize-research", "result": "PASS", "observed": {"body_is_suffix": True}},
            {"id": "R5-slash-argument-delivery:write-spec", "result": "PASS",
             "observed": {"literal_ARGUMENTS_still_in_body": True, "ends_with_instruction": True}}]}).encode()
        self.verify.write_bytes(vb)
        self.verify_pin = sha(vb)
        rel = "skills/synthesize-research/SKILL.md"
        self.obligations = t / "obl.json"
        mk = lambda i, line, quote, check: {"id": i, "skill": "synthesize-research",
                                             "cite": {"file": rel, "line": line, "quote": quote},
                                             "obligation": i, "check": check}
        self.obligations.write_text(json.dumps({
            "schema": SR.OBLIGATIONS_SCHEMA,
            "source": {"repo": "x/y", "commit": "0" * 40, "files": {rel: sha(SKILL.encode())}},
            "obligations": [
                mk("OB-OPP", 3, "#### Opportunity Areas", {"kind": "heading_present", "artifact": "research-synthesis.md", "heading": "Opportunity Areas"}),
                mk("OB-ASK", 4, "Ask the user what they have:", {"kind": "interactive_turn_absent"}),
                mk("OB-TRACKER", 5, "If **~~project tracker** is connected:", {"kind": "capability_unsupported", "capability": "~~project tracker"}),
                mk("OB-RU-NOW", 6, "- **Now** (current sprint/month): Committed work.", {"kind": "now_items_blocked", "artifact": "onboarding-roadmap.md"}),
                mk("OB-ATTR", 3, "#### Opportunity Areas", {"kind": "quotes_verbatim_with_ids", "artifact": "research-synthesis.md"}),
            ]}), encoding="utf-8")

    def review(self, **kw):
        kw.setdefault("use_clarifications", False)
        return SR.review(stage=self.stage, run_dir=self.run, verify_json=self.verify, repo_root=ROOT,
                         obligations_path=self.obligations, pins=self.pins, verify_pin=self.verify_pin, **kw)

    def clarifications(self, questions):
        p = self.stage.parent / "clar.json"
        p.write_text(json.dumps({"schema": "x", "questions": questions}), encoding="utf-8")
        return p


class FakeLLM:
    def __init__(self, parsed):
        self.parsed, self.calls = parsed, 0

    def complete_structured(self, **kw):
        self.calls += 1
        assert kw["purpose"] == "universal-port.p67-nli"
        return SimpleNamespace(parsed=self.parsed, model="fake-model", usage={"input": 1})


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(self.tmp.name)

    def by(self, result):
        return {f["obligation_id"]: f for f in result["findings"]}

    def test_classification_and_dispositions(self):
        r = self.fx.review()
        f = self.by(r)
        self.assertEqual((f["OB-OPP"]["verdict"], f["OB-OPP"]["root_cause"], f["OB-OPP"]["disposition"]),
                         ("CONTRADICTED", "MODEL_OUTPUT_QUALITY", "HOLD_NOT_A_PORTING_DEFECT"))
        self.assertEqual((f["OB-ASK"]["root_cause"], f["OB-ASK"]["disposition"]),
                         ("EXECUTION_HARNESS", "REPAIR_CANDIDATE_PROPOSED"))
        self.assertEqual((f["OB-TRACKER"]["verdict"], f["OB-TRACKER"]["disposition"]),
                         ("NOT_APPLICABLE", "HOLD_UNSUPPORTED"))
        self.assertEqual(f["OB-RU-NOW"]["verdict"], "CONTRADICTED")
        self.assertEqual(f["OB-ATTR"]["verdict"], "ENTAILED")
        self.assertEqual(r["model_calls"], 0)
        self.assertFalse(r["applied"])
        self.assertEqual(r["semantic_equivalence"], "NOT_ESTABLISHED")
        for x in f.values():
            self.assertTrue(x["source_citation"]["verified"])
            self.assertEqual(len(x["source_citation"]["source_sha256"]), 64)

    def test_heading_present_is_entailed(self):
        fx = Fixture(Path(self.tmp.name) / "b", synthesis=SYN_OK)
        self.assertEqual(self.by(fx.review())["OB-OPP"]["verdict"], "ENTAILED")

    def test_unsupported_capability_gets_no_candidate(self):
        r = self.fx.review()
        self.assertFalse(any("OB-TRACKER" in c["addresses"] for c in r["candidates"]))

    def test_candidates_are_bounded_and_not_applied(self):
        before_recipe = (ROOT / "uvp_p6_recipe.py").read_bytes()
        before_road = (self.fx.run / "onboarding-roadmap.md").read_bytes()
        r = self.fx.review()
        cands = {c["id"]: c for c in r["candidates"]}
        self.assertEqual(set(cands), {"RC-HARNESS-ASSUMPTIONS", "RC-ROADMAP-NOW"})
        h = cands["RC-HARNESS-ASSUMPTIONS"]
        self.assertTrue(h["checks"]["string_literal_only"])
        self.assertEqual(h["checks"]["permissions_added"], [])
        self.assertFalse(h["applied"])
        self.assertIn("Next (blocked: OQ-2", r["_candidate_texts"]["RC-ROADMAP-NOW"])
        self.assertIn("NOT the executed run-001 artifact", r["_candidate_texts"]["RC-ROADMAP-NOW"])
        self.assertEqual(before_recipe, (ROOT / "uvp_p6_recipe.py").read_bytes())
        self.assertEqual(before_road, (self.fx.run / "onboarding-roadmap.md").read_bytes())

    def test_candidate_temp_copy_tests_pass(self):
        r = self.fx.review(run_candidate_tests=True)
        h = next(c for c in r["candidates"] if c["id"] == "RC-HARNESS-ASSUMPTIONS")
        self.assertEqual(h["temp_copy_tests"]["result"], "PASS", h["temp_copy_tests"])

    def test_write_review_refuses_overwrite(self):
        r = self.fx.review()
        out = Path(self.tmp.name) / "out"
        SR.write_review(r, out)
        self.assertTrue((out / "SEMANTIC_REVIEW.json").is_file())
        with self.assertRaises(PortError):
            SR.write_review(r, out)

    def test_tampered_evidence_or_citation_refused(self):
        (self.fx.run / "onboarding-roadmap.md").write_bytes(ROADMAP.encode() + b"edited")
        with self.assertRaisesRegex(PortError, "immutable"):
            self.fx.review()
        fx = Fixture(Path(self.tmp.name) / "c")
        skill = fx.stage / "original" / "skills" / "synthesize-research" / "SKILL.md"
        skill.write_bytes(SKILL.replace("Ask the user", "Tell the user").encode())
        with self.assertRaisesRegex(PortError, "hash mismatch"):
            fx.review()

    def test_citation_must_match_exact_line(self):
        data = json.loads(self.fx.obligations.read_text(encoding="utf-8"))
        data["obligations"][0]["cite"]["line"] = 4
        self.fx.obligations.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(PortError, "Citation"):
            self.fx.review()

    def test_edit_gate_rejects_expansion(self):
        text = "alpha\nbeta\ngamma\n"
        for new in ("alpha https://evil.invalid", "alpha use the terminal", "alpha run --yolo", "alpha skill_manage"):
            with self.assertRaises(PortError, msg=new):
                SR._check_edits(text, [{"old": "alpha", "new": new}])
        with self.assertRaises(PortError):
            SR._check_edits(text, [{"old": x, "new": x + "!"} for x in ("alpha", "beta", "gamma", "\n")])
        with self.assertRaises((PortError, ValueError)):
            SR._check_edits("a a\n", [{"old": "a", "new": "b"}])

    def test_string_only_detector(self):
        self.assertTrue(SR._string_only_python_change('x = "a"\n', 'x = "b"\n'))
        self.assertFalse(SR._string_only_python_change('x = "a"\n', 'import os\nx = "a"\n'))
        self.assertFalse(SR._string_only_python_change('x = "a"\n', 'x = "a" + str(1)\n'))

    def test_llm_nli_gated_and_grounded(self):
        with self.assertRaises(PortError):
            SR.LLMNLIEvaluator(SimpleNamespace(llm=FakeLLM({})))
        with self.assertRaises(PortError):
            SR.LLMNLIEvaluator(SimpleNamespace(llm=FakeLLM({})), approved=True, max_calls=0)
        good = FakeLLM({"verdict": "CONTRADICTED", "root_cause": "MODEL_OUTPUT_QUALITY",
                        "evidence_quotes": ["Said: \"Alpha beta.\""], "rationale": "no section"})
        ev = SR.LLMNLIEvaluator(SimpleNamespace(llm=good), approved=True, max_calls=1)
        r = self.fx.review(evaluator=ev)
        f = self.by(r)
        self.assertEqual(good.calls, 1)
        self.assertEqual(r["model_calls"], 1)
        self.assertEqual(r["evaluator"]["model"], "fake-model")
        self.assertEqual(f["OB-OPP"]["evaluator"], "llm_nli")
        # Budget of one call: every later obligation is INSUFFICIENT, never guessed.
        self.assertEqual(f["OB-ASK"]["verdict"], "INSUFFICIENT_EVIDENCE")
        bad = FakeLLM({"verdict": "ENTAILED", "root_cause": "UNKNOWN",
                       "evidence_quotes": ["text that is not in the evidence"], "rationale": "x"})
        r2 = self.fx.review(evaluator=SR.LLMNLIEvaluator(SimpleNamespace(llm=bad), approved=True, max_calls=5))
        self.assertTrue(all(x["verdict"] == "INSUFFICIENT_EVIDENCE" for x in r2["findings"]))

    def test_nli_evidence_is_per_obligation_and_never_truncated(self):
        obl = {o["id"]: o for o in SR.load_obligations(self.fx.stage / "original", self.fx.obligations)["obligations"]}
        self.assertEqual(SR.evidence_for(obl["OB-RU-NOW"])[0], ["onboarding-roadmap.md", "onboarding-prd.md"])
        self.assertEqual(SR.evidence_for(obl["OB-ASK"])[0], [])  # trace-only: not judged by NLI
        ev = SR.load_evidence(self.fx.run, self.fx.verify, self.fx.stage / "PORTING_REPORT.json",
                              pins=self.fx.pins, verify_pin=self.fx.verify_pin)
        llm = FakeLLM({"verdict": "ENTAILED", "root_cause": "UNKNOWN", "evidence_quotes": ["x"], "rationale": ""})
        e = SR.LLMNLIEvaluator(SimpleNamespace(llm=llm), approved=True, max_calls=5)
        ev["files"]["research-synthesis.md"] = "y" * (SR.LLMNLIEvaluator.WINDOW + 1)
        self.assertIn("truncated", e.evaluate(obl["OB-OPP"], ev)["rationale"])
        del ev["files"]["onboarding-prd.md"]
        self.assertIn("missing", e.evaluate(obl["OB-RU-NOW"], ev)["rationale"])
        self.assertEqual(llm.calls, 0)

    def test_heading_only_is_not_entailed(self):
        fx = Fixture(Path(self.tmp.name) / "h", synthesis='# Syn\n\n## Opportunity Areas\n\n## Next\nSaid: "Alpha beta." I01\n')
        f = self.by(fx.review())["OB-OPP"]
        self.assertEqual((f["verdict"], f["rationale"]), ("CONTRADICTED", "Heading present but the section is empty"))

    def test_invented_repair_claims_rejected(self):
        findings = [{"obligation_id": "A", "verdict": "ENTAILED", "root_cause": None},
                    {"obligation_id": "B", "verdict": "CONTRADICTED", "root_cause": "HOST_SEMANTICS"},
                    {"obligation_id": "C", "verdict": "CONTRADICTED", "root_cause": "EXECUTION_HARNESS"}]
        for bad in ({"id": "x", "addresses": ["A"], "root_cause": "EXECUTION_HARNESS"},
                    {"id": "y", "addresses": ["B"], "root_cause": "HOST_SEMANTICS"},
                    {"id": "z", "addresses": ["C"], "root_cause": "MODEL_OUTPUT_QUALITY"},
                    {"id": "w", "addresses": ["nope"], "root_cause": "EXECUTION_HARNESS"},
                    {"id": "v", "addresses": [], "root_cause": "EXECUTION_HARNESS"}):
            with self.assertRaises(PortError, msg=bad["id"]):
                SR.validate_candidates([bad], findings)
        self.assertEqual(len(SR.validate_candidates([{"id": "ok", "addresses": ["C"], "root_cause": "EXECUTION_HARNESS"}], findings)), 1)

    def test_mandatory_missing_holds_instead_of_assuming(self):
        q = [{"skill": "synthesize-research", "line": 4, "question": "Ask what they have", "mandatory": True, "answer": None}]
        r = self.fx.review(use_clarifications=True, clarifications_path=self.fx.clarifications(q))
        f = self.by(r)["OB-ASK"]
        self.assertEqual(f["disposition"], "HOLD_MANDATORY_INFORMATION_MISSING")
        self.assertFalse(any(c["id"] == "RC-HARNESS-ASSUMPTIONS" for c in r["candidates"]))
        self.assertEqual(r["clarifications"][0]["status"], "MANDATORY_MISSING")

    def test_clarification_answers_must_be_verbatim_and_cited(self):
        ok = [{"skill": "synthesize-research", "line": 4, "question": "Ask what they have", "mandatory": True,
               "answer": {"file": "research-synthesis.md", "quote": "Alpha beta."}}]
        r = self.fx.review(use_clarifications=True, clarifications_path=self.fx.clarifications(ok))
        self.assertEqual(r["clarifications"][0]["status"], "ANSWERED_BY_CONTEXT")
        self.assertTrue(any(c["id"] == "RC-HARNESS-ASSUMPTIONS" for c in r["candidates"]))
        bad = [dict(ok[0], answer={"file": "research-synthesis.md", "quote": "not in evidence"})]
        with self.assertRaises(PortError):
            self.fx.review(use_clarifications=True, clarifications_path=self.fx.clarifications(bad))
        wrong_line = [dict(ok[0], line=6)]
        with self.assertRaises(PortError):
            self.fx.review(use_clarifications=True, clarifications_path=self.fx.clarifications(wrong_line))

    def test_not_wired_into_plugin_registration(self):
        self.assertNotIn("semantic_review", (ROOT / "__init__.py").read_text(encoding="utf-8"))
        self.assertNotIn("semantic_review", (ROOT / "uvp_plugin_router.py").read_text(encoding="utf-8"))

    @unittest.skipUnless((REAL_STAGE / "PORTING_REPORT.json").is_file() and REAL_RUN.is_dir(), "operator evidence not present")
    def test_real_run001_review(self):
        hashes_before = {p: sha(p.read_bytes()) for p in REAL_RUN.rglob("*") if p.is_file()}
        r = SR.review(stage=REAL_STAGE, run_dir=REAL_RUN, verify_json=REAL_VERIFY, repo_root=ROOT)
        got = {f["obligation_id"]: (f["verdict"], f["root_cause"], f["disposition"]) for f in r["findings"]}
        self.assertEqual(got, {
            "OB-SR-ATTRIB": ("ENTAILED", None, "NO_ACTION"),
            "OB-SR-OPPORTUNITY": ("CONTRADICTED", "MODEL_OUTPUT_QUALITY", "HOLD_NOT_A_PORTING_DEFECT"),
            "OB-SR-ASK": ("CONTRADICTED", "EXECUTION_HARNESS", "REPAIR_CANDIDATE_PROPOSED"),
            "OB-WS-ASK": ("CONTRADICTED", "EXECUTION_HARNESS", "REPAIR_CANDIDATE_PROPOSED"),
            "OB-WS-ARGS": ("CONTRADICTED", "HOST_SEMANTICS", "DETERMINISTIC_REPAIR_EXISTS"),
            "OB-WS-TRACKER": ("NOT_APPLICABLE", "UNSUPPORTED_CAPABILITY", "HOLD_UNSUPPORTED"),
            "OB-WS-NO-TOOLS": ("ENTAILED", None, "NO_ACTION"),
            "OB-RU-NOW": ("CONTRADICTED", "MODEL_OUTPUT_QUALITY", "REPAIR_CANDIDATE_PROPOSED"),
        })
        self.assertEqual(r["model_calls"], 0)
        self.assertEqual(hashes_before, {p: sha(p.read_bytes()) for p in REAL_RUN.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
