"""Offline-only contract tests for the experimental UVP routing core."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_router_test_pkg", ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_router_test_pkg import uvp_routing as R


def policy():
    return {
        "schema": R.POLICY_SCHEMA,
        "domains": {
            domain: {"preferred": domain + ".default", "fallbacks": [],
                     "allow_vanilla": True}
            for domain in R.DOMAIN_PATTERNS
        },
    }


def cap(domain, *, cap_id=None, approved=True, verified=True,
        permission="read", kind="hermes_skill"):
    return {
        "id": cap_id or domain + ".default",
        "domain": domain,
        "kind": kind,
        "invocation": "/example-" + domain,
        "approved": approved,
        "runtime_verified": verified,
        "evidence_sha256": "a" * 64 if verified else None,
        "permissions": [permission],
    }


def registry(*caps):
    return {"schema": R.REGISTRY_SCHEMA, "capabilities": list(caps)}


class RoutingCoreTests(unittest.TestCase):
    def test_english_token_boundaries(self):
        self.assertEqual(R.classify_domains("encoded symbols only"), [])
        self.assertEqual(R.classify_domains("Debug the code"), ["coding"])

    def test_korean_multidomain_mention_order(self):
        self.assertEqual(R.classify_domains("논문을 분석하고 코드를 구현해줘"),
                         ["research", "coding"])
        self.assertEqual(R.classify_domains("코드 짜고 관련 논문 조사"), ["coding", "research"])

    def test_explicit_default_selected_without_model(self):
        report = R.route_request("논문을 연구해줘", policy(),
                                 registry(cap("research")))
        self.assertEqual(report["status"], "PLAN_READY")
        self.assertEqual(report["selected"][0]["capability_id"], "research.default")
        self.assertFalse(report["execution_performed"])
        self.assertNotIn("논문을 연구해줘", json.dumps(report, ensure_ascii=False))

    def test_empty_registry_does_not_invent_available_skills(self):
        report = R.route_request("fix the bug", policy(), registry())
        self.assertEqual(report["status"], "PLAN_INCOMPLETE")
        self.assertEqual(report["selected"], [])
        self.assertEqual(report["unavailable"][0]["fallback"], "VANILLA_RECOMMENDED")

    def test_unapproved_or_static_only_never_selected(self):
        for approved, verified in ((False, True), (True, False), (False, False)):
            with self.subTest(approved=approved, verified=verified):
                report = R.route_request(
                    "research paper", policy(),
                    registry(cap("research", approved=approved, verified=verified)))
                self.assertEqual(report["status"], "PLAN_INCOMPLETE")
                self.assertFalse(report["selected"])

    def test_fallback_only_after_primary_fails(self):
        prefs = policy()
        prefs["domains"]["coding"]["fallbacks"] = ["coding.backup"]
        report = R.route_request(
            "debug code", prefs,
            registry(cap("coding", approved=False),
                     cap("coding", cap_id="coding.backup")))
        self.assertEqual(report["status"], "PLAN_READY")
        self.assertEqual(report["selected"][0]["capability_id"], "coding.backup")

    def test_side_effect_capability_needs_approval(self):
        report = R.route_request(
            "research this", policy(), registry(cap("research", permission="write")))
        self.assertEqual(report["status"], "APPROVAL_REQUIRED")
        self.assertEqual(report["selected"], [])
        self.assertEqual(report["unavailable"][0]["blocked"][0]["reason"],
                         "SIDE_EFFECT_REQUIRES_APPROVAL")

    def test_two_domains_propose_only_not_execute(self):
        result = R.route_request(
            "논문 연구하고 코드 구현", policy(),
            registry(cap("research"), cap("coding")))
        self.assertEqual(result["status"], "PLAN_READY")
        self.assertTrue(result["composition"])
        self.assertFalse(result["execution_performed"])
        self.assertEqual([x["domain"] for x in result["selected"]],
                         ["research", "coding"])

    def test_three_domains_require_review(self):
        result = R.route_request(
            "연구하고 코드를 만들고 데이터를 분석", policy(),
            registry(cap("research"), cap("coding"), cap("data")))
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["selected"], [])

    def test_unknown_prompt_does_not_guess(self):
        result = R.route_request("hello there", policy(), registry(cap("coding")))
        self.assertEqual(result["status"], "NATIVE_FALLBACK_RECOMMENDED")
        self.assertFalse(result["selected"])

    def test_unexpected_registry_shape_rejected(self):
        bad = cap("research")
        bad["dangerous_extension"] = "run shell"
        with self.assertRaises(R.RoutingError):
            R.validate_registry(registry(bad))

    def test_runtime_claim_requires_evidence_digest(self):
        bad = cap("research")
        bad["evidence_sha256"] = None
        with self.assertRaisesRegex(R.RoutingError, "evidence"):
            R.validate_registry(registry(bad))

    def test_policy_cannot_reference_duplicate_default(self):
        prefs = policy()
        prefs["domains"]["research"]["fallbacks"] = ["research.default"]
        with self.assertRaises(R.RoutingError):
            R.validate_policy(prefs)

    def test_config_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "routing.json"
            path.write_text(json.dumps(policy()), encoding="utf-8")
            self.assertEqual(R.load_policy(path), policy())


if __name__ == "__main__":
    unittest.main()
