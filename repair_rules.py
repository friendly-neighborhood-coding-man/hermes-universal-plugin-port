"""P6.17 shared, rule-based Skill repair (one pipeline for every source ecosystem).

Each rule is deterministic, versioned and fail-closed. It rewrites only spans it recognises and adds
only files it can source from the pinned origin tree. Anything it cannot handle is returned as an
`unresolved` item and blocks the Skill (HOLD); nothing is guessed.

Rules
  RES-LOCAL-1 v1   Markdown link to a file outside the Skill folder (e.g. ../../CONNECTORS.md):
                   copy the pinned origin file next to SKILL.md with a change notice; rewrite the link.
                   (P6.14 rule, re-verified in P6.16.)
  RES-CLOSURE-1 v1 Path reference into the source plugin's shared `references/` tree
                   (e.g. `../../references/foundations/x.md`): copy that exact file into the Skill's
                   own `references/` support dir (which Hermes skill_view serves) and rewrite the path.
  SKILL-REF-1 v1   Path reference to a sibling Skill's SKILL.md (e.g. `../node-link-and-diagram-layout/SKILL.md`):
                   NOT bundled as an asset. Rewritten to name the separate Skill and how Hermes loads it;
                   the missing Skill stays a REQUIRED_SKILL dependency.
  INPUT-VARS-1 v1  GitHub Copilot `${input:Name}` / `${input:Name:hint}` placeholders, which Hermes does not
                   expand: each becomes `[input: Name]`, and a "Hermes inputs" block lists every input and says
                   to take values from the user's request or ask for missing ones, never invent them.
                   Other `${...}` variables, or `${input:...}` inside fenced code, are unsupported (HOLD).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

RULES = {
    "RES-LOCAL-1": {"version": 1, "origin": "P6.14 adapt_package.py; P6.16 migration_repair.py"},
    "RES-CLOSURE-1": {"version": 1, "origin": "P6.17"},
    "SKILL-REF-1": {"version": 1, "origin": "P6.17"},
    "INPUT-VARS-1": {"version": 1, "origin": "P6.17"},
}
MAX_FILE = 262144
MD_LINK = re.compile(r"\]\(([^)\s#]+)\)")
TICK_PATH = re.compile(r"`((?:\.\./)+[^`\s]+?\.(?:md|txt|json|ya?ml))`")
INPUT_VAR = re.compile(r"\$\{input:([A-Za-z][A-Za-z0-9_]*)(?::[^}]*)?\}")
ANY_VAR = re.compile(r"\$\{([^}]+)\}")
HERMES_VARS = {"HERMES_SKILL_DIR", "HERMES_SESSION_ID"}
LOCAL_NOTICE = ("<!-- Added by Universal Plugin Port repair {rule} v1: copied from {origin} (sha256 {sha}) so Hermes "
                "skill_view can open it. Upstream license applies; change notice. -->\n")
CONNECTOR_NOTE = ("> **UVP note:** this file only explains connectors. In this Hermes import the connectors are NOT "
                  "connected; no MCP server, OAuth grant or credential was configured.\n\n")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _is_redirect(p: Path) -> bool:
    import os
    if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
        return True
    try:
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def _fences(text: str) -> list[tuple[int, int]]:
    spans, start = [], None
    for m in re.finditer(r"^```.*$", text, flags=re.M):
        if start is None:
            start = m.start()
        else:
            spans.append((start, m.end()))
            start = None
    return spans


def _in(spans, pos):
    return any(a <= pos < b for a, b in spans)


def inventory(text: str) -> dict:
    """Every local reference and host variable in a SKILL.md, classified."""
    refs = sorted(set(MD_LINK.findall(text)) | set(TICK_PATH.findall(text)))
    local = [r for r in refs if "://" not in r and not r.startswith(("mailto:", "#"))]
    return {
        "markdown_links": sorted(set(MD_LINK.findall(text))),
        "path_references": sorted(set(TICK_PATH.findall(text))),
        "sibling_skills": sorted({r for r in local if re.fullmatch(r"\.\./[^/]+/SKILL\.md", r)}),
        "shared_plugin_files": sorted({r for r in local if r.startswith("../../")}),
        "outside_skill_other": sorted({r for r in local if r.startswith("../") and not r.startswith("../../")
                                       and not re.fullmatch(r"\.\./[^/]+/SKILL\.md", r)}),
        "input_variables": sorted(set(INPUT_VAR.findall(text))),
        "other_host_variables": sorted({v for v in ANY_VAR.findall(text) if not v.startswith("input:") and v not in HERMES_VARS}),
    }


def plan_skill(*, skill: str, text: str, skill_dir: Path, origin_root: Path, origin_skill_rel: str) -> dict:
    """Return {"applications": [...], "new_text", "added": {rel: bytes}, "unresolved": [...]}.
    `origin_root/origin_skill_rel` is the pinned upstream location of this Skill."""
    oroot = Path(origin_root).resolve(strict=True)
    oskill = (oroot / origin_skill_rel).resolve(strict=True)
    if not oskill.is_relative_to(oroot):
        raise ValueError("origin skill path escapes the origin root")
    apps, added, unresolved = [], {}, []
    new = text
    fences = _fences(text)

    def origin_file(rel):
        t = (oskill / rel).resolve(strict=False)
        if not t.is_relative_to(oroot) or not t.is_file() or _is_redirect(t) or t.stat().st_size > MAX_FILE:
            return None, None
        return t, t.relative_to(oroot).as_posix()

    inv = inventory(text)
    # SKILL-REF-1: sibling Skills stay separate Skills.
    for ref in inv["sibling_skills"]:
        name = ref.split("/")[1]
        target, _ = origin_file(ref)
        if target is None:
            unresolved.append({"rule": "SKILL-REF-1", "ref": ref, "why": "sibling Skill not found in pinned origin"})
            continue
        repl = "the separate Skill `%s` (Hermes: `skill_view(\"%s\")`; not bundled with this Skill)" % (name, name)
        count = new.count("`%s`" % ref)
        new = new.replace("`%s`" % ref, repl)
        if count == 0:
            unresolved.append({"rule": "SKILL-REF-1", "ref": ref, "why": "reference is not a backtick path span"})
            continue
        apps.append({"rule": "SKILL-REF-1", "ref": ref, "occurrences": count, "required_skill": name})
    # RES-CLOSURE-1: shared plugin references -> Skill-local references/.
    for ref in inv["shared_plugin_files"]:
        target, orel = origin_file(ref)
        parts = Path(orel).parts if orel else ()
        if target is None or "references" not in parts:
            if not re.fullmatch(r"\.\./\.\./[^/]+\.md", ref):  # ../../CONNECTORS.md style is RES-LOCAL-1
                unresolved.append({"rule": "RES-CLOSURE-1", "ref": ref, "why": "not a file under the origin's references/"})
            continue
        local = "references/" + "/".join(parts[parts.index("references") + 1:])
        if (Path(skill_dir) / local).exists():
            unresolved.append({"rule": "RES-CLOSURE-1", "ref": ref, "why": "%s already exists" % local})
            continue
        body = target.read_bytes()
        added[local] = LOCAL_NOTICE.format(rule="RES-CLOSURE-1", origin=orel, sha=sha(body)).encode() + body
        count = new.count("`%s`" % ref) + new.count("](%s)" % ref)
        new = new.replace("`%s`" % ref, "`%s`" % local).replace("](%s)" % ref, "](%s)" % local)
        apps.append({"rule": "RES-CLOSURE-1", "ref": ref, "to": local, "occurrences": count, "origin_sha256": sha(body)})
    # RES-LOCAL-1: markdown links leaving the folder to a single origin file.
    for ref in inv["markdown_links"]:
        if not ref.startswith("../") or ref in inv["sibling_skills"] or any(a["ref"] == ref for a in apps):
            continue
        target, orel = origin_file(ref)
        if target is None:
            unresolved.append({"rule": "RES-LOCAL-1", "ref": ref, "why": "target missing/outside origin/too large"})
            continue
        dest = target.name
        if (Path(skill_dir) / dest).exists():
            unresolved.append({"rule": "RES-LOCAL-1", "ref": ref, "why": "%s already exists" % dest})
            continue
        body = target.read_bytes()
        note = CONNECTOR_NOTE if "CONNECTOR" in dest.upper() else ""
        added[dest] = LOCAL_NOTICE.format(rule="RES-LOCAL-1", origin=orel, sha=sha(body)).encode() + note.encode() + body
        count = new.count("](%s)" % ref)
        new = new.replace("](%s)" % ref, "](%s)" % dest)
        apps.append({"rule": "RES-LOCAL-1", "ref": ref, "to": dest, "occurrences": count, "origin_sha256": sha(body)})
    for ref in inv["outside_skill_other"]:
        if not any(a["ref"] == ref for a in apps):
            unresolved.append({"rule": None, "ref": ref, "why": "unsupported reference outside the Skill folder"})
    # INPUT-VARS-1: Copilot input placeholders.
    if inv["other_host_variables"]:
        unresolved.append({"rule": "INPUT-VARS-1", "ref": inv["other_host_variables"],
                           "why": "host variables other than ${input:...} are unsupported"})
    names = []
    for m in INPUT_VAR.finditer(text):
        if _in(fences, m.start()):
            unresolved.append({"rule": "INPUT-VARS-1", "ref": m.group(0), "why": "${input:...} inside fenced code"})
        elif m.group(1) not in names:
            names.append(m.group(1))
    if names and not any(u["rule"] == "INPUT-VARS-1" for u in unresolved):
        new = INPUT_VAR.sub(lambda m: "[input: %s]" % m.group(1), new)
        # Correction 1 (P6.17 iteration-0 failure): this note must not itself contain the placeholder syntax.
        block = ("\n## Hermes inputs (UVP INPUT-VARS-1)\n\nThis Skill was written for GitHub Copilot, where each "
                 "named input field prompts the user. Hermes does not expand those fields; they appear below as "
                 "`[input: Name]`. Take each value from the text the user gave with the command or from the "
                 "conversation. If a value is missing, ask the user for it before writing anything, and never "
                 "invent it.\n\n" + "".join("- [input: %s]\n" % n for n in names))
        h1 = re.search(r"^# .+$", new, flags=re.M)
        if not h1:
            unresolved.append({"rule": "INPUT-VARS-1", "ref": names, "why": "no H1 title to anchor the inputs block"})
        else:
            new = new[:h1.end()] + "\n" + block + new[h1.end():]
            apps.append({"rule": "INPUT-VARS-1", "inputs": names, "occurrences": len(INPUT_VAR.findall(text))})
    return {"skill": skill, "inventory": inv, "applications": apps, "unresolved": unresolved,
            "new_text": new, "added": added}
