"""Build an ADAPTED copy of a staged package (the stage itself is never modified).

Two deterministic adaptations, both recorded with before/after SHA-256 in
ADAPTATION_MANIFEST.json:

  R-C001  Usage lines `/<skill> $ARGUMENTS` -> `/<plugin>:<skill> <argument-hint>`
          (the existing verified composition rule, via compat_engine.map_skill_text).
  RES-LOCAL-1  A Markdown link that resolves in the ORIGINAL tree but not in the
          active Hermes tree (e.g. `../../CONNECTORS.md`) is localized: the original
          file is copied into the Skill directory with a UVP change notice, and the
          link is rewritten to the local name, which Hermes `skill_view(file_path=...)`
          can serve. The notice states that the referenced connectors are NOT
          connected (SKILLS_ONLY_PARTIAL); nothing is emulated.

`original/` stays byte-identical. Every changed or added file carries a change
notice (Apache-2.0 section 4(b)).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

if __package__:
    from . import compat_engine as CE
    from .port_core import PortError
else:
    import compat_engine as CE
    from port_core import PortError

SCHEMA = "universal-port.adaptation/1"
LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\s]+)\)")
NOTICE_MD = ("<!-- Modified by Universal Plugin Port (%s): %s. Original: original/%s (sha256 %s). "
             "Apache-2.0 section 4(b) change notice. -->\n")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def adapt(stage: str, output: str, *, registry=None, identity=None) -> dict:
    root, report = CE.checked_stage(stage)
    out = Path(output).resolve()
    if out.exists():
        raise PortError("Output exists; refusing to overwrite")
    registry = registry or CE.load_registry()
    identity = identity or CE.default_identity(registry)
    catalog = CE.stage_catalog(root)
    shutil.copytree(root, out, ignore=shutil.ignore_patterns("__pycache__", "P6_REVIEW_CANDIDATES"))
    changes = []
    for skill in catalog["skills"]:
        rel = "skills/%s/SKILL.md" % skill
        active = out / rel
        before = active.read_bytes()
        text = before.decode("utf-8")
        r = CE.map_skill_text(text, skill=skill, catalog=catalog, registry=registry, identity=identity,
                              source_skill_dir=root / "original" / "skills" / skill, source_root=root / "original",
                              target_skill_dir=root / "skills" / skill, target_root=root)
        if r["status"] == "HOLD":
            raise PortError("Mapping HOLD for %s: %s" % (skill, r["holds"]))
        new = r["mapped_text"]
        rules = [d["rule_id"] for d in r["deltas"]]
        for res in r.get("resources", []):
            link = res["link"]
            if res["resolves_in_source_tree"] and not res["resolves_in_target_tree"]:
                src = (root / "original" / "skills" / skill / link.split("#", 1)[0]).resolve()
                if not src.is_relative_to((root / "original").resolve()) or not src.is_file():
                    continue
                local = src.name
                dest = out / "skills" / skill / local
                if dest.exists():
                    raise PortError("Localized resource name collides: " + str(dest))
                body = src.read_bytes()
                origin_rel = src.relative_to((root / "original").resolve()).as_posix()
                header = (NOTICE_MD % ("RES-LOCAL-1", "copied next to the Skill so Hermes skill_view can serve it",
                                       origin_rel, _sha(body))
                          + "> **UVP note:** In this Hermes port the connectors described below are NOT connected "
                            "(SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool "
                            "for it is actually present.\n\n").encode("utf-8")
                dest.write_bytes(header + body)
                changes.append({"path": "skills/%s/%s" % (skill, local), "rule": "RES-LOCAL-1", "added": True,
                                "source": "original/" + origin_rel, "source_sha256": _sha(body),
                                "after_sha256": _sha(header + body)})
                new = new.replace("](%s)" % link, "](%s)" % local)
                rules.append("RES-LOCAL-1")
        if new != text:
            notice = NOTICE_MD % (",".join(sorted(set(rules))), "host-semantic adaptation", rel, _sha(before))
            # Keep YAML frontmatter first: insert the notice after the closing '---'.
            if new.startswith("---"):
                end = new.find("\n---", 3)
                cut = new.find("\n", end + 4) + 1 if end >= 0 else 0
                new = new[:cut] + notice + new[cut:]
            else:
                new = notice + new
            after = new.encode("utf-8")
            active.write_bytes(after)
            changes.append({"path": rel, "rules": sorted(set(rules)), "before_sha256": _sha(before), "after_sha256": _sha(after),
                            "original_sha256": _sha((root / "original" / rel).read_bytes())})
    manifest = {"schema": SCHEMA, "from_stage": str(root), "stage_fingerprint": report.get("source_fingerprint_sha256"),
                "registry_sha256": registry["sha256"], "identity": identity, "changes": changes, "model_calls": 0}
    (out / "ADAPTATION_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
