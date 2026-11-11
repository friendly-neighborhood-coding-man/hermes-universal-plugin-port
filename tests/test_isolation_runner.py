"""P6.10 isolation runner: bundle safety offline; live namespace demo only where WSL + the disposable distro exist."""
import importlib.util
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uvp_p610_test_pkg", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from uvp_p610_test_pkg import isolation_runner as IR
from uvp_p610_test_pkg.port_core import PortError


def _distro_available():
    if not shutil.which("wsl"):
        return False
    try:
        out = subprocess.run(["wsl", "-l", "-q"], capture_output=True, timeout=20).stdout.decode("utf-16-le", "ignore")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return IR.DEFAULT_DISTRO in out.split()


class IsolationRunnerTests(unittest.TestCase):
    def test_rejects_bad_mode_and_member_names(self):
        with self.assertRaises(PortError):
            IR.run(b"", mode="host")
        with self.assertRaises(PortError):
            IR.run(b"", {"/etc/x": b""})
        with self.assertRaises(PortError):
            IR.run(b"", {"a/../../x": b""})

    def test_bundle_is_deterministic(self):
        self.assertEqual(IR._bundle({"a": b"1", "b": b"2"}), IR._bundle({"b": b"2", "a": b"1"}))

    @unittest.skipUnless(_distro_available(), "WSL disposable distro not available")
    def test_live_isolation_denies_out_of_scope_and_control_allows(self):
        fx = {"fixture.txt": b"harmless fixture\n"}
        iso = IR.run(IR.PROBE_WORKLOAD, fx, mode="isolated")["result"]
        ctl = IR.run(IR.PROBE_WORKLOAD, fx, mode="control")["result"]
        for allowed in ("read_input_fixture", "write_work_output"):
            self.assertTrue(iso[allowed]["ok"], allowed)
        for denied in ("write_input_readonly", "read_etc_hostname", "list_windows_drive", "list_root_home",
                       "connect_host_loopback_listener", "fork_process", "shell_binary_present"):
            self.assertFalse(iso[denied]["ok"], denied)
            self.assertTrue(ctl[denied]["ok"], "control must show the probe is meaningful: " + denied)
        self.assertEqual(iso["uid"]["detail"], "65534")


if __name__ == "__main__":
    unittest.main()
