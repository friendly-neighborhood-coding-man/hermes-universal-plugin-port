"""P6.12 WP3: Safebox-gated execution of a deterministic task inside the P6.10 isolation runner.

Flow (one narrow path, no model inside):
  1. resolve the imported Skill's verified contract (P6.8),
  2. require a Safebox grant bound to that contract that lists the `uvp_isolated_task`
     tool, with the task's host inputs inside fs.read and its host output dir inside fs.write,
  3. run an ALLOW-LISTED, UVP-owned workload in the namespace-isolated runner
     (read-only /input, read-write /work, no network, no fork, no /bin/sh),
  4. copy only the produced files back into the granted host output dir and return a
     receipt with hashes.

What is isolated: the workload process. What is NOT: the LLM, Hermes, and Skill
instruction delivery (those use the normal Hermes path, where Safebox is POLICY_ONLY).
Classification: LIMITED_WORKLOAD_ISOLATION.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

if __package__:
    from . import isolation_runner as IR
    from . import safebox as SB
    from .port_core import PortError
else:
    import isolation_runner as IR
    import safebox as SB
    from port_core import PortError

CLASSIFICATION = "LIMITED_WORKLOAD_ISOLATION"
TOOL = "uvp_isolated_task"

# Allow-listed workloads: fixed UVP code, never model- or Skill-supplied code.
WORKLOADS = {
    "evidence_index": rb'''
import hashlib, json, os
inp, work = os.environ["UVP_ISO_INPUT"], os.environ["UVP_ISO_WORK"]
rows = []
for name in sorted(os.listdir(inp)):
    if name == "workload.py":
        continue
    data = open(os.path.join(inp, name), "rb").read()
    rows.append({"file": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                 "lines": data.count(b"\n")})
open(os.path.join(work, "evidence_index.json"), "w").write(json.dumps(rows, indent=2, sort_keys=True))
print(json.dumps({"indexed": len(rows)}))
''',
    "boundary_probe": IR.PROBE_WORKLOAD,
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_isolated_task(skill: str, task: dict, *, contracts: dict, grants: list, runner=IR.run,
                      distro: str = IR.DEFAULT_DISTRO, timeout: int = 120) -> dict:
    if not isinstance(task, dict) or set(task) - {"workload", "inputs", "output_dir"}:
        raise PortError("Malformed isolated task")
    if task.get("workload") not in WORKLOADS:
        raise PortError("Workload not allow-listed")
    box = SB.Safebox(grants, contracts)  # validates grants and their binding to current contracts
    g = box.grants.get(skill)
    if g is None:
        raise PortError("No Safebox grant for " + skill)
    if TOOL not in g["tools"]:
        raise PortError("Grant does not allow " + TOOL)
    inputs = task.get("inputs") or []
    out_dir = task.get("output_dir")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(p, str) for p in inputs):
        raise PortError("Inputs must be a non-empty list of paths")
    for p in inputs:
        if not SB._within(p, g["fs"]["read"] + g["fs"]["write"], None) or not os.path.isfile(p):
            raise PortError("Input outside fs.read scope or missing: " + p)
    if not isinstance(out_dir, str) or not SB._within(os.path.join(out_dir, "x"), g["fs"]["write"], None):
        raise PortError("Output dir outside fs.write scope")
    files = {}
    for p in inputs:
        name = os.path.basename(p)
        if name in files or name == "workload.py":
            raise PortError("Duplicate or reserved input name: " + name)
        files[name] = Path(p).read_bytes()
    workload = WORKLOADS[task["workload"]]
    res = runner(workload, files, mode="isolated", distro=distro, timeout=timeout)
    os.makedirs(out_dir, exist_ok=True)
    written = {}
    for name, data in sorted(res.get("outputs", {}).items()):
        # Plain file names only, on every OS: no separators of either flavor, no dot names.
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith(".") \
                or ":" in name or len(name) > 128:
            raise PortError("Unsafe output name from runner: %r" % (name,))
        dest = os.path.join(out_dir, name)
        if not SB._within(dest, g["fs"]["write"], None):
            raise PortError("Output path escaped fs.write scope")
        with open(dest, "xb") as f:
            f.write(data)
        written[name] = _sha(data)
    return {"classification": CLASSIFICATION, "skill": skill, "contract_id": g["contract_id"],
            "source_sha256": g["source_sha256"], "grant_sha256": SB.grant_hash(g),
            "workload": task["workload"], "workload_sha256": _sha(workload),
            "inputs": {os.path.basename(p): _sha(files[os.path.basename(p)]) for p in inputs},
            "outputs": written, "runner": {k: res.get(k) for k in ("mode", "distro", "returncode", "result")},
            "isolated": ["workload process"], "not_isolated": ["LLM", "Hermes process", "Skill instruction delivery"]}


def hermes_tool(contracts_loader, grants_loader):
    """A Hermes tool handler (args, **kw) -> JSON string. Used by the TEST-ONLY harness."""
    def handler(args, **kw):
        try:
            r = run_isolated_task(args.get("skill"), args.get("task"), contracts=contracts_loader(), grants=grants_loader())
            return json.dumps({"ok": True, **r})
        except Exception as exc:
            return json.dumps({"ok": False, "status": "REFUSED", "error": "%s: %s" % (type(exc).__name__, str(exc)[:200])})
    return handler


SCHEMA = {"name": TOOL, "description": "TEST-ONLY: run an allow-listed UVP workload in the isolation runner under a Safebox grant.",
          "parameters": {"type": "object", "properties": {
              "skill": {"type": "string"},
              "task": {"type": "object", "properties": {
                  "workload": {"type": "string", "enum": sorted(WORKLOADS)},
                  "inputs": {"type": "array", "items": {"type": "string"}},
                  "output_dir": {"type": "string"}}}},
              "required": ["skill", "task"]}}
