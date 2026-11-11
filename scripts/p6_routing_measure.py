"""P6.11 measurement with real Hermes message builders (no model calls).

Comparable input: the P6 research -> PRD -> roadmap task, plus a 5-step variant
that revisits write-spec and synthesize-research. Run with the disposable venv
python and HERMES_HOME = disposable P6 home. Reads defaults read-only.
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
from agent.skill_commands import build_skill_invocation_message, build_stacked_skill_invocation_message
import lazy_routing as LR

discover_plugins(force=True)
NS = "ported-product-management"
recipe = {"research": NS + ":synthesize-research", "documents": NS + ":write-spec", "planning": NS + ":roadmap-update"}
stored = LR.read_stored_defaults(HOME / "uvp-data" / "p6-domain-defaults.json")
instr = "Fictional onboarding interviews I01-I08; produce the artifact for this step."
tasks = {
    "three_step": [{"id": 1, "domain": "research"}, {"id": 2, "domain": "documents"}, {"id": 3, "domain": "planning"}],
    "five_step_revisit": [{"id": 1, "domain": "research"}, {"id": 2, "domain": "documents"}, {"id": 3, "domain": "planning"},
                          {"id": 4, "domain": "documents"}, {"id": 5, "domain": "research"}],
}
out = {"stored_defaults": stored, "defaults_written": False, "model_calls": 0, "results": {}}
for name, steps in tasks.items():
    plan = LR.route(steps, stored, explicit=recipe)
    distinct = sorted({p["skill"] for p in plan})
    eager = build_stacked_skill_invocation_message(["/" + s.lower() for s in distinct], instr)[0]
    m = LR.measure(plan, eager_message=eager,
                   per_step_message=lambda s: build_skill_invocation_message("/" + s.lower(), instr),
                   lazy_body=lambda s: json.loads(skill_view(s))["content"],
                   stat=lambda s: (lambda f: (str(f), f.stat().st_mtime_ns, f.stat().st_size))(
                       HOME / "plugins" / NS / "skills" / s.split(":", 1)[1] / "SKILL.md"))
    out["results"][name] = {"routing_sources": sorted({p["source"] for p in plan}), **m}
print(json.dumps(out, indent=2, sort_keys=True))
