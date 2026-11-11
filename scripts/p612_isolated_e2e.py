"""P6.12 WP3: Safebox -> isolation runner through a REAL Hermes tool call (no model).

Disposable venv python, HERMES_HOME = uvp-p612-hermes-test (after p612_adversarial.py setup).
The TEST-ONLY harness registers the `uvp_isolated_task` tool; this driver activates the
imported Skill via skill_view (Safebox grant check), then calls the tool through
model_tools.handle_function_call. Harmless fixtures only.
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path(r"D:\Hermes-Lab\uvp-p612-hermes-test")
FIX = Path(r"D:\Hermes-Lab\uvp-p612-fixtures")
if Path(os.environ.get("HERMES_HOME", "")).resolve() != HOME.resolve():
    raise SystemExit("HERMES_HOME must be the NEW disposable P6.12 home")
sys.path.insert(0, r"D:\Hermes-Lab\hermes-agent")
sys.path.insert(0, str(REPO))
from hermes_cli.plugins import discover_plugins
import model_tools
import safebox as SB
import skill_continuity as SC

NS = "ported-product-management"
Q = NS + ":write-spec"
contracts = SC.build_contracts(HOME / "plugins" / NS, REPO / "semantics" / "p6_obligations.json")
iso_in, iso_out = FIX / "iso-in", FIX / "iso-out"
iso_in.mkdir(exist_ok=True)
(iso_in / "notes.txt").write_text("harmless fixture note\n", encoding="utf-8")
g = SB.default_grant(Q, contracts[Q]["source_sha256"], contracts[Q]["contract_id"])
g.update(fs={"read": [str(iso_in)], "write": [str(iso_out)]}, tools=["uvp_isolated_task"])


def configure(grants):
    (HOME / "plugins" / "uvp-safebox-harness" / "harness.json").write_text(json.dumps(
        {"uvp_repo": str(REPO), "ported_plugin": str(HOME / "plugins" / NS), "audit": str(FIX / "audit-iso.jsonl"),
         "grants": grants}), encoding="utf-8")


def call(name, args, s):
    return json.loads(model_tools.handle_function_call(name, args, task_id=s, session_id=s, tool_call_id="tc"))


configure([g])
discover_plugins(force=True)
out = {"model_calls": 0, "cases": {}}
out["cases"]["activate"] = call("skill_view", {"name": Q}, "w3")["success"]
r = call("uvp_isolated_task", {"skill": Q, "task": {"workload": "evidence_index", "inputs": [str(iso_in / "notes.txt")],
                                                    "output_dir": str(iso_out / "run1")}}, "w3")
out["cases"]["evidence_index"] = r
r = call("uvp_isolated_task", {"skill": Q, "task": {"workload": "boundary_probe", "inputs": [str(iso_in / "notes.txt")],
                                                    "output_dir": str(iso_out / "run2")}}, "w3")
out["cases"]["boundary_probe"] = r
r = call("uvp_isolated_task", {"skill": Q, "task": {"workload": "evidence_index", "inputs": [str(FIX / "work" / "input.txt")],
                                                    "output_dir": str(iso_out / "run3")}}, "w3")
out["cases"]["input_outside_grant"] = r
r = call("uvp_isolated_task", {"skill": Q, "task": {"workload": "arbitrary_code", "inputs": [str(iso_in / "notes.txt")],
                                                    "output_dir": str(iso_out / "run4")}}, "w3")
out["cases"]["non_allowlisted_workload"] = r
configure([dict(g, contract_id="0" * 24)])
r = call("uvp_isolated_task", {"skill": Q, "task": {"workload": "evidence_index", "inputs": [str(iso_in / "notes.txt")],
                                                    "output_dir": str(iso_out / "run5")}}, "w3-stale")
out["cases"]["stale_grant"] = r
print(json.dumps(out, indent=2))
