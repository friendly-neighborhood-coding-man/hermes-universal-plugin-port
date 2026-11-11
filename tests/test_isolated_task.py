"""P6.12 WP3: Safebox-gated isolated task. Offline gate tests + live WSL tests (skip without distro)."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p612w3_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p612w3_test_pkg import isolated_task as IT
from uvp_p612w3_test_pkg import isolation_runner as IR
from uvp_p612w3_test_pkg import safebox as SB
from uvp_p612w3_test_pkg import skill_continuity as SC
from uvp_p612w3_test_pkg.port_core import PortError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_isolation_runner import _distro_available  # noqa: E402

Q, SRC = "ported-product-management:write-spec", "a" * 64


class IsolatedTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.inp, self.out = t / "in", t / "out"
        self.inp.mkdir()
        (self.inp / "notes.txt").write_text("harmless\n", encoding="utf-8")
        self.contracts = {Q: {"skill": Q, "source_sha256": SRC, "contract_id": SC.contract_id(Q, SRC)}}
        g = SB.default_grant(Q, SRC, SC.contract_id(Q, SRC))
        g.update(fs={"read": [str(self.inp)], "write": [str(self.out)]}, tools=[IT.TOOL])
        self.grant = g
        self.calls = []

    def fake_runner(self, workload, files, **kw):
        self.calls.append((workload, sorted(files)))
        return {"mode": "isolated", "distro": "fake", "returncode": 0, "result": {"ok": 1},
                "outputs": {"report.json": b"{}"}}

    def task(self, **over):
        t = {"workload": "evidence_index", "inputs": [str(self.inp / "notes.txt")], "output_dir": str(self.out / "r")}
        t.update(over)
        return t

    def run_task(self, grants=None, **over):
        return IT.run_isolated_task(Q, self.task(**over), contracts=self.contracts,
                                    grants=[self.grant] if grants is None else grants, runner=self.fake_runner)

    def test_happy_path_receipt(self):
        r = self.run_task()
        self.assertEqual(r["classification"], "LIMITED_WORKLOAD_ISOLATION")
        self.assertEqual(r["not_isolated"], ["LLM", "Hermes process", "Skill instruction delivery"])
        self.assertTrue((self.out / "r" / "report.json").is_file())
        self.assertEqual(self.calls[0][1], ["notes.txt"])

    def test_refusals_before_runner(self):
        bad = [
            dict(grants=[]),
            dict(grants=[dict(self.grant, tools=[])]),
            dict(grants=[dict(self.grant, contract_id="0" * 24)]),
            dict(grants=[dict(self.grant, source_sha256="b" * 64)]),
            dict(grants=[dict(self.grant, extra=1)]),
            dict(workload="arbitrary"),
            dict(inputs=[str(Path(self.tmp.name) / "elsewhere.txt")]),
            dict(inputs="notes.txt"),
            dict(inputs=["notes.txt"]),
            dict(output_dir=str(Path(self.tmp.name) / "not-granted")),
            dict(output_dir="relative/out"),
        ]
        for case in bad:
            with self.assertRaises(PortError, msg=str(case)):
                self.run_task(**case)
        self.assertEqual(self.calls, [])

    def test_runner_output_cannot_escape(self):
        def evil(workload, files, **kw):
            return {"outputs": {"..\\..\\escape.txt": b"x"}}
        with self.assertRaises(PortError):
            IT.run_isolated_task(Q, self.task(), contracts=self.contracts, grants=[self.grant], runner=evil)

    def test_hermes_tool_handler_never_raises(self):
        h = IT.hermes_tool(lambda: self.contracts, lambda: [])
        r = json.loads(h({"skill": Q, "task": self.task()}))
        self.assertEqual((r["ok"], r["status"]), (False, "REFUSED"))

    def test_runner_unavailable_fails_closed(self):
        with self.assertRaises(PortError):
            IR.run(b"print(1)", {}, distro="uvp-no-such-distro-xyz", timeout=60)

    @unittest.skipUnless(_distro_available(), "WSL disposable distro not available")
    def test_live_isolated_task_and_boundary(self):
        r = IT.run_isolated_task(Q, self.task(), contracts=self.contracts, grants=[self.grant])
        idx = json.loads((self.out / "r" / "evidence_index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx[0]["file"], "notes.txt")
        p = IT.run_isolated_task(Q, self.task(workload="boundary_probe", output_dir=str(self.out / "p")),
                                 contracts=self.contracts, grants=[self.grant])["runner"]["result"]
        for denied in ("write_input_readonly", "read_etc_hostname", "list_windows_drive", "connect_host_loopback_listener",
                       "fork_process", "shell_binary_present"):
            self.assertFalse(p[denied]["ok"], denied)

    @unittest.skipUnless(_distro_available(), "WSL disposable distro not available")
    def test_live_interrupted_run_is_cleaned_up(self):
        rid = "p612cleanup1"
        with self.assertRaises(PortError):
            IR.run(b"import time\ntime.sleep(60)\n", {}, mode="isolated", timeout=8, run_id_override=rid)
        self.assertTrue(IR.cleanup(rid))


if __name__ == "__main__":
    unittest.main()
