"""TEST-ONLY: wires UVP Safebox + continuity into a disposable Hermes home (P6.12 WP2).

Reads harness.json next to this file on every call, so the adversarial driver can
change grants between cases. Any setup failure blocks imported-Skill activation.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_STATE = {}


def _cfg():
    return json.loads((HERE / "harness.json").read_text(encoding="utf-8"))


def _box():
    cfg = _cfg()
    if str(cfg["uvp_repo"]) not in sys.path:
        sys.path.insert(0, str(cfg["uvp_repo"]))
    import safebox as SB
    import skill_continuity as SC
    key = json.dumps(cfg, sort_keys=True)
    if _STATE.get("key") != key:
        contracts = SC.build_contracts(Path(cfg["ported_plugin"]), Path(cfg["uvp_repo"]) / "semantics" / "p6_obligations.json")
        audit = Path(cfg["audit"])
        try:
            box = SB.Safebox(cfg["grants"], contracts, audit_path=audit)
            err = None
        except Exception as exc:  # invalid/stale grant: fail closed for imported Skills
            box, err = None, "%s: %s" % (type(exc).__name__, exc)
        from tools.skills_tool import skill_view
        tracker = SC.ContinuityTracker(contracts, SC.hermes_skill_view_loader(skill_view))
        _STATE.update(key=key, box=box, err=err, contracts=contracts, tracker=tracker)
    return _STATE


def pre_tool_call(tool_name="", args=None, session_id="", **kw):
    try:
        st = _box()
        if st["box"] is None:
            if tool_name == "skill_view" and isinstance(args, dict) and args.get("name") in st["contracts"]:
                return {"action": "block", "message": "UVP Safebox grant invalid: " + st["err"]}
            return None
        r = st["box"].pre_tool_call(tool_name=tool_name, args=args, session_id=session_id, **kw)
        if r:
            return r
        return st["tracker"].pre_tool_call(tool_name=tool_name, args=args, session_id=session_id, **kw)
    except Exception as exc:
        return {"action": "block", "message": "UVP harness error " + type(exc).__name__}


def post_tool_call(tool_name="", args=None, result=None, session_id="", **kw):
    try:
        _box()["tracker"].post_tool_call(tool_name=tool_name, args=args, result=result, session_id=session_id)
    except Exception:
        pass
    return None


def _iso_handler(args, **kw):
    st = _box()
    import isolated_task as IT
    return IT.hermes_tool(lambda: st["contracts"], lambda: _cfg()["grants"])(args or {}, **kw)


def register(ctx):
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    cfg = _cfg()
    if str(cfg["uvp_repo"]) not in sys.path:
        sys.path.insert(0, str(cfg["uvp_repo"]))
    import isolated_task as IT
    ctx.register_tool(name=IT.TOOL, toolset="uvp_test_harness", schema=IT.SCHEMA, handler=_iso_handler)
