"""P6.15 Phase 4: real pinned GrokBotImporter / OpenBotImporter PREVIEW through UVP assurance.

Grok Bot: a synthetic two-Bot export (scheduled, event and schedule-text-only routines, two Skills,
memories with a fake token, user facts) is previewed with the official GrokBotImporter(execute=False).
UVP adds checks for the documented user problems:
  #265 several Bots merged into one profile      -> HOLD unless --bot selects one Bot
  #266 routines left without a schedule          -> counted and listed
  #264 imported routines deliver locally         -> WARN (delivery target is not chosen by the import)
OpenBot: the preview's scratch directory under <target>/cache is detected with a whole-home digest.

  python scripts/p615_grok_openbot_probe.py --official-package DIR --report NEW.json
No model calls; synthetic fixtures only; target homes are temporary.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_import_assurance import AssuranceError, assess_official_preview  # noqa: E402
from scripts.p615_preview_official_import import package_digest, tree_digest  # noqa: E402

FAKE_TOKEN = "sk-test" + "abcdefghijklmnopqrstuvwx"  # synthetic, split so no scanner sees a key literal
EXPORT = {"format": "grok-bot-export", "version": 1, "bots": [
    {"name": "Account Health", "title": "Customer success",
     "instructions": "Own the weekly account-health review. Never contact a customer without approval.",
     "memories": ["Churn signal: three weeks without a login", "Token %s is old" % FAKE_TOKEN],
     "user_facts": ["Works in America/New_York"],
     "skills": [{"name": "Weekly account health", "description": "Score accounts each week",
                 "instructions": "1. Pull usage.\n2. Flag churn."}],
     "routines": [
         {"name": "Morning watch list", "instruction": "Run the Weekly account health skill.", "trigger": "schedule",
          "schedule_cron": "0 8 * * 1-5", "schedule_text": "Every weekday at 8:00 AM", "timezone": "America/New_York",
          "paused": False, "skills": ["Weekly account health"]},
         {"name": "Escalations", "instruction": "Reproduce the ticket in staging.", "trigger": "slack",
          "trigger_details": "#customer-escalations, phrase 'needs repro'"},
         {"name": "Quarterly review", "instruction": "Summarise the quarter.", "trigger": "schedule",
          "schedule_text": "first Monday of each quarter"}]},
    {"name": "Release Notes", "title": "Docs",
     "instructions": "Draft release notes from merged PRs.",
     "memories": ["Release notes go out on Thursdays"],
     "skills": [{"name": "Draft notes", "description": "Draft notes", "instructions": "Collect PR titles."}],
     "routines": [{"name": "Thursday draft", "instruction": "Draft notes.", "trigger": "schedule",
                   "schedule_cron": "0 9 * * 4", "schedule_text": "Thursdays 9 AM", "paused": False}]}]}


def _official(root: Path, hermes_src: Path):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root.parent))
    sys.path.append(str(hermes_src))  # Hermes core (cron.jobs), used by the official Grok routine import
    return (importlib.import_module("agent-importers.importer"), importlib.import_module("agent-importers.grok_bot"),
            importlib.import_module("agent-importers.openbot"))


def grok_case(mods, work: Path, *, bot_names=()):
    importer, grok, _ = mods
    work.mkdir(parents=True)
    export = work / "export.json"
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    home = work / "home"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "MEMORY.md").write_text("Existing synthetic memory.\n", encoding="utf-8")
    before, src_before = tree_digest(home), tree_digest(work, skip=("home",))
    home_paths = {p.relative_to(home).as_posix() for p in home.rglob("*")}
    # Grok routines use Hermes core cron.jobs, which resolves HERMES_HOME at call time: pin it to the
    # temporary target so the operator's real cron store is never read or written.
    os.environ["HERMES_HOME"] = str(home)
    imp = grok.GrokBotImporter([export], home, execute=False, bot_names=bot_names)
    receipt = assess_official_preview(imp, memory_char_limit=2200, merge_entries=importer.merge_entries,
                                      parse_existing_memory_entries=importer.parse_existing_memory_entries,
                                      entry_delimiter=importer.ENTRY_DELIMITER, user_char_limit=1375)
    bots = EXPORT["bots"] if not bot_names else [b for b in EXPORT["bots"] if b["name"].lower() in {n.lower() for n in bot_names}]
    routines = [r for b in bots for r in b["routines"]]
    scheduled = [r["name"] for r in routines if r.get("schedule_cron")]
    unscheduled = [r["name"] for r in routines if not r.get("schedule_cron")]
    ledger_routines = [r for r in receipt["ledger"] if r["kind"] in ("routine", "event-routines", "routines")]
    findings = []
    if len(bots) > 1:
        findings.append({"issue": "#265", "level": "HOLD",
                         "text": "%d Bots would merge into one Hermes profile (one SOUL, one memory). Import one Bot per "
                                 "profile with --bot." % len(bots)})
    if unscheduled:
        findings.append({"issue": "#266", "level": "WARN",
                         "text": "%d routine(s) have no cron schedule and will not run: %s" % (len(unscheduled), ", ".join(unscheduled))})
    if scheduled:
        findings.append({"issue": "#264", "level": "WARN",
                         "text": "%d scheduled routine(s) become paused jobs delivering locally; choose a delivery "
                                 "target before resuming them: %s" % (len(scheduled), ", ".join(scheduled))})
    # Independent source inventory vs the official plan: every source routine with a cron schedule must
    # appear as a `routine` row. (Observed: without Hermes's own dependencies the official preview silently
    # turns scheduled routines into "no schedule" notes.)
    planned_jobs = sum(1 for r in receipt["ledger"] if r["kind"] == "routine" and r["status"] == "imported")
    if planned_jobs != len(scheduled):
        findings.append({"issue": "silent-downgrade", "level": "HOLD",
                         "text": "%d routine(s) have a cron schedule in the export but the official plan creates %d job(s); "
                                 "the rest would be saved as unscheduled notes" % (len(scheduled), planned_jobs)})
    created = sorted({p.relative_to(home).as_posix() for p in home.rglob("*")} - home_paths)
    if tree_digest(home) != before:
        findings.append({"issue": "dry-run-side-effect", "level": "HOLD",
                         "text": "the official PREVIEW changed the target home: %s" % ", ".join(created)})
    text = json.dumps(receipt)
    gate = "HOLD" if receipt["gate"] == "HOLD" or any(f["level"] == "HOLD" for f in findings) else "REVIEW_ONLY"
    return {"bots_selected": [b["name"] for b in bots], "official_gate": receipt["gate"], "uvp_gate": gate,
            "paths_created_by_preview": created, "python": sys.version.split()[0],
            "official_reasons": receipt["reasons"], "counts": receipt["counts"],
            "memory_events": [{k: e[k] for k in ("destination", "limit_chars", "projected_chars", "overflowed")}
                              for e in receipt["memory_events"]],
            "routine_ledger": [{k: r[k] for k in ("kind", "status", "reason")} for r in ledger_routines],
            "uvp_findings": findings, "target_home_unchanged": tree_digest(home) == before,
            "source_unchanged": tree_digest(work, skip=("home",)) == src_before,
            "fake_token_in_receipt": FAKE_TOKEN in text,
            "stripped_secrets_reported_by_official": len(getattr(imp, "stripped_secrets", []))}


def openbot_case(mods, work: Path):
    importer, _, openbot = mods
    user_data = work / "openbot-data"
    user_data.mkdir(parents=True)
    db = sqlite3.connect(user_data / openbot.DATABASE)
    db.execute("create table agents (id text primary key, name text, instructions text)")
    db.commit()
    db.close()
    home = work / "home"
    home.mkdir()
    before = sorted(p.relative_to(home).as_posix() for p in home.rglob("*"))
    digest = tree_digest(home)
    cls = getattr(openbot, "OpenBotImporter", None)
    try:
        imp = cls(user_data, home, execute=False) if cls else None
        rep = imp.run() if imp else None
        err = None
    except Exception as exc:  # the schema here is minimal; we only observe side effects
        rep, err = None, "%s: %s" % (type(exc).__name__, str(exc)[:200])
    after = sorted(p.relative_to(home).as_posix() for p in home.rglob("*"))
    return {"preview_error": err, "dry_run": (rep or {}).get("dry_run"),
            "target_home_unchanged": tree_digest(home) == digest,
            "paths_created_by_preview": sorted(set(after) - set(before)),
            "classification": "PREVIEW_SIDE_EFFECT: creates <target>/cache (scratch parent) during a dry run"
            if "cache" in set(after) - set(before) else "no side effect observed"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--official-package", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--hermes-src", type=Path, required=True)
    a = p.parse_args(argv)
    if a.report.exists():
        p.error("create-only report")
    root = a.official_package.resolve(strict=True)
    digest = package_digest(root)
    mods = _official(root, a.hermes_src)
    real_home = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory(prefix="p615-grok-") as d:
        d = Path(d)
        out = {"schema": "uvp.p615.grok-openbot-probe/1", "official_package_sha256": digest,
               "grok_all_bots": grok_case(mods, d / "all"),
               "grok_one_bot": grok_case(mods, d / "one", bot_names=("Account Health",)),
               "openbot_preview_side_effect": openbot_case(mods, d / "openbot"),
               "model_calls": 0, "scope": "official PREVIEW only; synthetic exports"}
    if real_home is None:
        os.environ.pop("HERMES_HOME", None)
    else:
        os.environ["HERMES_HOME"] = real_home
    if package_digest(root) != digest:
        raise AssuranceError("official package changed during the probe")
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: (v.get("uvp_gate"), v.get("uvp_findings"), v.get("target_home_unchanged"), v.get("fake_token_in_receipt"))
                      if "uvp_gate" in v else v for k, v in out.items() if isinstance(v, dict)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
