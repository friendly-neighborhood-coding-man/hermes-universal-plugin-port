"""P6.11 routing and lazy loading: no silent defaults, single load, measured sizes."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p611_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p611_test_pkg import lazy_routing as LR

BODIES = {"ns:a": "A" * 400, "ns:b": "B" * 800}


class LazyRoutingTests(unittest.TestCase):
    def test_no_silent_default(self):
        plan = LR.route([{"id": 1, "domain": "research"}], {})
        self.assertIsNone(plan[0]["skill"])
        self.assertEqual(plan[0]["source"], "NO_DEFAULT")

    def test_stored_default_wins_over_explicit(self):
        plan = LR.route([{"id": 1, "domain": "research"}], {"research": "ns:a"}, explicit={"research": "ns:b"})
        self.assertEqual((plan[0]["skill"], plan[0]["source"]), ("ns:a", "STORED_DOMAIN_DEFAULT"))

    def test_lazy_loader_loads_once(self):
        calls = []
        # With an unchanged fingerprint the body is not reloaded at all.
        ld = LR.LazyLoader(lambda n: calls.append(n) or BODIES[n], stat=lambda n: ("fixed", 1))
        first, second = ld.get("ns:a"), ld.get("ns:a")
        self.assertTrue(first["loaded"])
        self.assertFalse(second["loaded"])
        self.assertLess(len(second["text"]), 200)
        self.assertEqual((ld.loads, ld.reuses, calls), (1, 1, ["ns:a"]))
        # Without a fingerprint, reuse is validated by reloading and comparing digests.
        calls.clear()
        ld2 = LR.LazyLoader(lambda n: calls.append(n) or BODIES[n])
        ld2.get("ns:a"), ld2.get("ns:a")
        self.assertEqual((ld2.loads, ld2.reuses, ld2.validated_reloads, ld2.reinjections, len(calls)), (1, 1, 1, 0, 2))

    def file_loader(self, root):
        def path(n):
            return Path(root) / (n.replace(":", "__") + ".md")

        def load(n):
            return path(n).read_text(encoding="utf-8")

        def stat(n):
            s = path(n).stat()
            return (str(path(n)), s.st_mtime_ns, s.st_size, s.st_ino)
        return path, load, stat

    def test_cache_invalidation_matrix(self):
        import os
        with tempfile.TemporaryDirectory() as t:
            path, load, stat = self.file_loader(t)
            path("ns:a").write_text("A1", encoding="utf-8")
            calls = []
            ld = LR.LazyLoader(lambda n: calls.append(n) or load(n), stat=stat)
            self.assertTrue(ld.get("ns:a", "s1")["loaded"])
            # repeated call, unchanged -> reuse without reloading
            self.assertFalse(ld.get("ns:a", "s1")["loaded"])
            self.assertEqual(len(calls), 1)
            # modified content -> reinjected
            path("ns:a").write_text("A2 changed", encoding="utf-8")
            r = ld.get("ns:a", "s1")
            self.assertTrue(r["loaded"] and r["changed"] and r["text"] == "A2 changed")
            # touched but same content -> validated reload, no reinjection
            st = path("ns:a").stat()
            os.utime(path("ns:a"), ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
            self.assertFalse(ld.get("ns:a", "s1")["loaded"])
            self.assertEqual(ld.validated_reloads, 2)
            # replaced file (new inode/size) with different content -> reinjected
            path("ns:a").unlink()
            path("ns:a").write_text("A3 replaced!", encoding="utf-8")
            self.assertEqual(ld.get("ns:a", "s1")["text"], "A3 replaced!")
            # other session never sees s1's cache
            self.assertTrue(ld.get("ns:a", "s2")["loaded"])
            # missing file -> refused and entry dropped
            path("ns:a").unlink()
            with self.assertRaises(LR.PortError):
                ld.get("ns:a", "s1")
            self.assertNotIn(("s1", "ns:a"), ld.cache)

    def test_stale_hash_without_stat_is_detected(self):
        bodies = {"ns:a": "v1"}
        ld = LR.LazyLoader(lambda n: bodies[n])
        ld.get("ns:a")
        self.assertFalse(ld.get("ns:a")["loaded"])  # validated reload, same digest
        bodies["ns:a"] = "v2"
        self.assertTrue(ld.get("ns:a")["changed"])
        self.assertEqual((ld.loads, ld.validated_reloads, ld.reinjections), (1, 2, 1))

    def test_contract_verification_refuses_load_and_reuse(self):
        bodies = {"ns:a": "good"}
        ok = {"good"}
        ld = LR.LazyLoader(lambda n: bodies[n], verify=lambda n, b: b in ok)
        ld.get("ns:a")
        bodies["ns:a"] = "tampered"
        with self.assertRaises(LR.PortError):
            ld.get("ns:a")
        self.assertNotIn(("default", "ns:a"), ld.cache)
        with self.assertRaises(LR.PortError):
            LR.LazyLoader(lambda n: "bad", verify=lambda n, b: False).get("ns:x")

    def test_measure_counts_repetition(self):
        plan = LR.route([{"id": i, "domain": d} for i, d in enumerate(["r", "d", "r", "d"])],
                        {}, explicit={"r": "ns:a", "d": "ns:b"})
        m = LR.measure(plan, eager_message=BODIES["ns:a"] + BODIES["ns:b"],
                       per_step_message=lambda n: BODIES[n], lazy_body=lambda n: BODIES[n])
        self.assertEqual(m["per_step_reinjection"]["chars"], 2 * (400 + 800))
        self.assertEqual(m["lazy_once"]["skill_loads"], 2)
        self.assertLess(m["lazy_once"]["chars"], m["per_step_reinjection"]["chars"])
        self.assertEqual(m["cost_claim"], "NONE (no billed-token measurement)")

    def test_read_stored_defaults_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(LR.read_stored_defaults(Path(t) / "none.json"), {})
            p = Path(t) / "d.json"
            p.write_text(json.dumps({"domains": {"research": "ns:a"}}), encoding="utf-8")
            self.assertEqual(LR.read_stored_defaults(p), {"research": "ns:a"})

    def test_measured_evidence_shape(self):
        ev = ROOT / "docs" / "evidence" / "p6-11-routing" / "measure-001.json"
        if not ev.is_file():
            self.skipTest("measurement evidence not present")
        d = json.loads(ev.read_text(encoding="utf-8-sig"))
        self.assertFalse(d["defaults_written"])
        self.assertEqual(d["model_calls"], 0)
        r = d["results"]["five_step_revisit"]
        self.assertEqual(r["lazy_once"]["skill_loads"], 3)
        self.assertLess(r["lazy_once"]["chars"], r["per_step_reinjection"]["chars"])


if __name__ == "__main__":
    unittest.main()
