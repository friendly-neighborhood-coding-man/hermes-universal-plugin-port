"""P6.12 WP5 exercise: real Hermes CLI in a NEW disposable home (no model calls).

Creates D:\\Hermes-Lab\\uvp-p612-rollback-home (refuses if it exists) with an unrelated
fixture plugin and settings, then: clean install of the validated stage -> real
discovery + namespaced resolution -> corrupted update (refused) -> update that fails
the post-swap resolution check (auto rollback) -> rollback to pre-install -> manifest
equality with the pre-install state -> fresh install + removal. Writes evidence JSON.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import install_ops as IO

HOME = Path(r"D:\Hermes-Lab\uvp-p612-rollback-home")
STAGE = Path(r"D:\Hermes-Lab\p6-staged\ported-product-management")
WORK = Path(r"D:\Hermes-Lab\uvp-p612-rollback-work")
HERMES = os.environ.get("HERMES_EXE") or shutil.which("hermes") or "hermes"  # operator-local launcher
PY = r"D:\Hermes-Lab\uvp-p6-hermes-test\installs\544a4d40e77d70ca\environments\fa614ea5f2034b70993a5b719fdf251a\venv\Scripts\python.exe"
NAME = "ported-product-management"
ENV = {**os.environ, "HERMES_HOME": str(HOME), "PYTHONDONTWRITEBYTECODE": "1", "UVP_ENABLE_ARXIV_EXECUTION": "0"}
CHECK = r"""
import json, sys
sys.path.insert(0, r"D:\Hermes-Lab\hermes-agent")
from hermes_cli.plugins import discover_plugins, get_plugin_manager
from tools.skills_tool import skill_view
discover_plugins(force=True)
names = sorted(m["name"] for m in get_plugin_manager().list_plugin_skill_metadata() if m["name"].startswith("ported-product-management:"))
v = json.loads(skill_view("ported-product-management:write-spec")) if names else {}
print(json.dumps({"skills": names, "write_spec_resolves": bool(v.get("success"))}))
"""


def same_ignoring_backups(a, b):
    strip = lambda m: {k: v for k, v in m.items() if not k.startswith("backups/config/")}
    return strip(a) == strip(b)


def hermes(*args):
    p = subprocess.run([HERMES, *args], env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    return p.returncode, (p.stdout + p.stderr)[-400:]


def resolution():
    p = subprocess.run([PY, "-I", "-c", CHECK], env=ENV, capture_output=True, text=True, timeout=300)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": p.stderr[-300:]}


def main(out_path):
    if HOME.exists() or WORK.exists():
        raise SystemExit("Refusing: rollback home or work dir already exists")
    (HOME / "plugins" / "uvp-unrelated-fixture").mkdir(parents=True)
    (HOME / "plugins" / "uvp-unrelated-fixture" / "plugin.yaml").write_text(
        "name: uvp-unrelated-fixture\nversion: 0.0.1\ndescription: harmless unrelated fixture plugin\n", encoding="utf-8")
    (HOME / "plugins" / "uvp-unrelated-fixture" / "__init__.py").write_text("def register(ctx):\n    pass\n", encoding="utf-8")
    (HOME / "config.yaml").write_text("plugins:\n  enabled:\n    - uvp-unrelated-fixture\n  disabled: []\ndisplay:\n  compact: true\n"
                                      "telemetry:\n  shared_metrics:\n    enabled: false\n    send: false\n", encoding="utf-8")
    (HOME / "uvp-data").mkdir()
    (HOME / "uvp-data" / "p6-domain-defaults.json").write_text(json.dumps(
        {"schema": "universal-port.p6-domain-defaults/1", "revision": 1, "domains": {"research": "other:skill"}, "history": []}), encoding="utf-8")
    (HOME / IO.MARKER).write_text("disposable P6.12 rollback exercise\n", encoding="utf-8")
    WORK.mkdir()

    def check():
        r = resolution()
        return {"ok": len(r.get("skills", [])) == 8 and r.get("write_spec_resolves"), "why": json.dumps(r)[:200]}

    def validate(pkg):
        rc, tail = hermes("plugins", "validate", str(pkg))
        return {"ok": rc == 0, "why": tail}

    ev = {"model_calls": 0, "home": str(HOME), "steps": []}
    # Let Hermes do its own first-run bootstrap (SOUL.md, bin/, bundled skills) BEFORE the baseline.
    ev["bootstrap"] = hermes("plugins", "list")[0]
    s0 = IO.manifest(HOME)
    ev["s0_files"] = len(s0)
    inst = IO.Installer(HOME, NAME, enable=lambda n: hermes("plugins", "enable", n),
                        disable=lambda n: hermes("plugins", "disable", n), validate=validate, check=check)
    r = inst.install(STAGE)
    ev["steps"].append({"step": "1-3 clean install + discovery + namespaced resolution", **{k: r[k] for k in ("ok", "result")},
                        "resolution": resolution()})
    s1 = IO.manifest(HOME)
    bad = WORK / "corrupt"
    shutil.copytree(STAGE, bad, ignore=shutil.ignore_patterns("__pycache__", "P6_REVIEW_CANDIDATES"))
    (bad / "skills" / "write-spec" / "SKILL.md").write_bytes(b"tampered body\n")
    u = inst.update(bad)
    ev["steps"].append({"step": "4 corrupted update (tampered SKILL.md)", "result": u["result"], "why": u.get("why", "")[:160],
                        "state_unchanged": IO.manifest(HOME) == s1})
    broken = WORK / "broken"
    shutil.copytree(STAGE, broken, ignore=shutil.ignore_patterns("__pycache__", "P6_REVIEW_CANDIDATES"))
    (broken / "__init__.py").write_text((broken / "__init__.py").read_text(encoding="utf-8").replace(
        '_SKILLS = (', '_SKILLS = ("does-not-exist", '), encoding="utf-8")
    u2 = inst.update(broken)
    ev["steps"].append({"step": "5 failed update recovery (registers a missing Skill)", "result": u2["result"],
                        "why": u2.get("why", "")[:200], "restored_to_installed_state": IO.manifest(HOME) == s1, "restored_ignoring_hermes_config_backups": same_ignoring_backups(IO.manifest(HOME), s1),
                        "resolution_after": resolution()})
    # A candidate that passes validate but registers under another namespace: caught only after the swap.
    renamed = WORK / "renamed"
    shutil.copytree(STAGE, renamed, ignore=shutil.ignore_patterns("__pycache__", "P6_REVIEW_CANDIDATES"))
    (renamed / "plugin.yaml").write_text((renamed / "plugin.yaml").read_text(encoding="utf-8").replace(
        "name: ported-product-management", "name: ported-product-management-v2"), encoding="utf-8")
    u3 = inst.update(renamed)
    ev["steps"].append({"step": "5b update passing validate but failing post-swap resolution", "result": u3["result"],
                        "why": u3.get("why", "")[:200], "restored_to_installed_state": IO.manifest(HOME) == s1, "restored_ignoring_hermes_config_backups": same_ignoring_backups(IO.manifest(HOME), s1),
                        "resolution_after": resolution()})
    inst.rollback_to(Path(r["backup"]))
    s_after = IO.manifest(HOME)
    diff = sorted({k for k, _ in set(s0.items()) ^ set(s_after.items())})
    hermes_owned = [k for k in diff if k.startswith("backups/") or k.endswith(".lock")]
    ev["steps"].append({"step": "6 rollback to pre-install backup", "manifest_equals_pre_install": s_after == s0,
                        "diff_paths": diff[:20], "diff_only_hermes_owned_backups": diff == hermes_owned,
                        "resolution_after": resolution()})
    r2 = inst.install(STAGE)
    rm = inst.remove()
    s_rm = IO.manifest(HOME)
    rm_diff = sorted(set(s0.items()) ^ set(s_rm.items()))
    ev["steps"].append({"step": "7 reinstall then remove", "install": r2["result"], "remove": rm["result"],
                        "plugin_dir_gone": not (HOME / "plugins" / NAME).exists(),
                        "diff_vs_pre_install": [d[0] for d in rm_diff][:10]})
    ev["steps"].append({"step": "8 unrelated plugin, defaults and settings unchanged",
                        "unrelated_plugin_same": all(s_rm.get(k) == v for k, v in s0.items() if k.startswith("plugins/uvp-unrelated-fixture/")),
                        "defaults_same": s_rm.get("uvp-data/p6-domain-defaults.json") == s0.get("uvp-data/p6-domain-defaults.json"),
                        "config_same_after_remove": s_rm.get("config.yaml") == s0.get("config.yaml")})
    ev["log"] = inst.log
    Path(out_path).write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{k: v for k, v in s.items() if k not in ("resolution", "resolution_after", "diff")} for s in ev["steps"]], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
