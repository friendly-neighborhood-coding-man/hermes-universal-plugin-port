"""P6.8 runtime check (no model): real Hermes skill_view as the contract loader.

Run with the disposable venv python and HERMES_HOME = disposable P6 home.
Builds contracts from the INSTALLED ported plugin and checks that a simulated
delegate_task gets the contract attached after a real reload, and fails closed
when the contract's installed SHA does not match what Hermes serves.
"""
import json
import os
import sys
from pathlib import Path

HOME = Path(r"D:\Hermes-Lab\uvp-p6-hermes-test")
if Path(os.environ.get("HERMES_HOME", "")).resolve() != HOME.resolve():
    raise SystemExit("HERMES_HOME must be the disposable P6 home")
sys.path.insert(0, r"D:\Hermes-Lab\hermes-agent")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_cli.plugins import discover_plugins
from tools.skills_tool import skill_view
import skill_continuity as SC

discover_plugins(force=True)
inst = HOME / "plugins" / "ported-product-management"
contracts = SC.build_contracts(inst, Path(__file__).resolve().parents[1] / "semantics" / "p6_obligations.json")
loader = SC.hermes_skill_view_loader(skill_view)
out = {"contracts": sorted(contracts), "model_calls": 0, "cases": []}
for q in sorted(contracts):
    t = SC.ContinuityTracker(contracts, loader)
    real = skill_view(q)
    t.post_tool_call(tool_name="skill_view", args={"name": q}, result=real, session_id="rt")
    r = t.pre_tool_call(tool_name="delegate_task", args={"goal": "continue"}, session_id="rt")
    ok = bool(r and r.get("action") == "modify" and contracts[q]["contract_id"] in r["args"]["context"])
    bad = dict(contracts)
    bad[q] = dict(contracts[q], installed_sha256="0" * 64)
    t2 = SC.ContinuityTracker(bad, loader)
    t2.post_tool_call(tool_name="skill_view", args={"name": q}, result=real, session_id="rt")
    r2 = t2.pre_tool_call(tool_name="delegate_task", args={"goal": "continue"}, session_id="rt")
    out["cases"].append({"skill": q, "handoff_attached_after_real_reload": ok,
                         "fail_closed_on_sha_mismatch": bool(r2 and r2.get("action") == "block")})
out["result"] = "PASS" if out["cases"] and all(c["handoff_attached_after_real_reload"] and c["fail_closed_on_sha_mismatch"] for c in out["cases"]) else "FAIL"
print(json.dumps(out, indent=2))
