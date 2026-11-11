"""P6.1: inert, source-preserving Claude/Cowork skill bundle -> Hermes plugin.

Not an installer or runtime executor. Unsupported MCP, hook and command
semantics are never silently ported. Imported docs are untrusted instructions.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

if __package__:
    from .port_core import (
        PortError, enumerate_files, detect, discover_skills, load_json,
        source_fingerprint, copy_dir_filtered, slug,
    )
    from .claude_command import HERMES_INLINE_SHELL
else:
    from port_core import (
        PortError, enumerate_files, detect, discover_skills, load_json,
        source_fingerprint, copy_dir_filtered, slug,
    )
    from claude_command import HERMES_INLINE_SHELL

_SHA = re.compile(r"^[0-9a-f]{40}$")
_HOST_TOKENS = ("$ARGUMENTS", "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PLUGIN_DATA}", "~~")


def stage_claude_skill_bundle(source: str, output_root: str, *,
                              approved: bool = False,
                              allow_partial: bool = False,
                              declared_source_commit: str = "") -> dict:
    """Stage a minimal Hermes skill-plugin, never install/enable/run it.

    declared_source_commit is operator-supplied lineage metadata, NOT
    independently proven provenance. The exact source fingerprint is computed
    locally, and an earlier pinned GitHub fetch must independently prove the
    connection between this local folder and its claimed upstream commit.
    """
    if approved is not True:
        raise PortError("Explicit staging approval is required")
    if not isinstance(declared_source_commit, str) or not _SHA.fullmatch(declared_source_commit):
        raise PortError("Supply a declared full 40-character upstream commit")
    path = Path(source).expanduser()
    if path.is_symlink():
        raise PortError("Symlink source is forbidden")
    root = path.resolve()
    files = enumerate_files(root)
    profile, manifest = detect(root)
    if profile != "claude-code":
        raise PortError("P6.1 only accepts a Claude Code/Cowork plugin")
    if not isinstance(manifest.get("name"), str) or not manifest["name"]:
        raise PortError("Claude source must have a named manifest")
    skills = discover_skills(root, manifest, profile)
    if not skills:
        raise PortError("No SKILL.md files discovered")
    names = [s["name"] for s in skills]
    if len(names) != len(set(names)):
        raise PortError("Duplicate normalized skill names")

    connectors = load_json(root / ".mcp.json").get("mcpServers", {})
    if not isinstance(connectors, dict):
        raise PortError("Invalid foreign MCP source declaration")
    unsupported = []
    if connectors:
        unsupported.append("Claude MCP/OAuth connectors are not ported")
    for name in ("hooks", "agents", "commands"):
        if (root / name).exists() or name in manifest:
            unsupported.append("Foreign host component not ported: " + name)
    if unsupported and allow_partial is not True:
        raise PortError("SKILLS_ONLY_PARTIAL needs explicit approval: " + "; ".join(unsupported))

    destbase = Path(output_root).expanduser().resolve()
    if destbase == root or destbase.is_relative_to(root) or root.is_relative_to(destbase):
        raise PortError("Output cannot overlap source")
    name = slug("ported-" + manifest["name"])
    destbase.mkdir(parents=True, exist_ok=True)
    target = destbase / name
    if target.exists():
        raise PortError("Existing staged plugin cannot be overwritten")

    sha = source_fingerprint(root, files)
    hashes = {str(f.relative_to(root)).replace("\\", "/"):
              hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    review = []
    for item in skills:
        # Hash the ORIGINAL FILE BYTES, never a read_text() round-trip.
        # Windows read_text() normalizes CRLF to LF, so re-encoding text
        # gives a different digest from the byte-preserved source snapshot.
        original_bytes = (root / item["path"] / "SKILL.md").read_bytes()
        try:
            raw = original_bytes.decode("utf-8")
        except UnicodeError as exc:
            raise PortError("Skill is not valid UTF-8: " + item["name"]) from exc
        # Literal Hermes inline-shell syntax would execute when viewed. Never
        # distribute an unreviewed raw Skill that could acquire that effect.
        if HERMES_INLINE_SHELL.search(raw):
            raise PortError("Hermes inline-shell syntax requires a separately reviewed safe adaptation: " + item["name"])
        review.append({
            "skill": item["name"],
            "source_path": item["path"] + "/SKILL.md",
            "original_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "copied_verbatim": True,
            "foreign_host_syntax_detected": any(tok in raw for tok in _HOST_TOKENS),
            "runtime_equivalence_verified": False,
            "requires_manual_review": True,
        })

    with tempfile.TemporaryDirectory(prefix=".p6-stage-", dir=destbase) as temp:
        out = Path(temp) / name
        out.mkdir()
        copy_dir_filtered(root, out / "original")
        for item in skills:
            source_dir = root / item["path"]
            copy_dir_filtered(source_dir, out / "skills" / item["name"])
        # Only static, trusted-generated Python is ever imported in Hermes.
        # The original source is packaged as inert data, not executable code.
        init = (
            '"""Static generated Hermes skill registration; untrusted docs need review."""\n'
            'from pathlib import Path\n'
            '_SKILLS = ' + repr(tuple(names)) + '\n'
            'def register(ctx):\n'
            '    base = Path(__file__).resolve().parent / "skills"\n'
            '    for name in _SKILLS:\n'
            '        path = base / name / "SKILL.md"\n'
            '        if not path.is_file() or path.is_symlink():\n'
            '            raise RuntimeError("Staged skill unavailable")\n'
            '        ctx.register_skill(name, path)\n'
        )
        (out / "__init__.py").write_text(init, encoding="utf-8")
        (out / "plugin.yaml").write_text(
            f"name: {name}\nversion: 0.6.0\n"
            "description: Staged Claude skill bundle; requires review before activation.\n",
            encoding="utf-8",
        )
        manifest_out = {
            "schema": "universal-port.p6-stage/1",
            "status": "SKILLS_ONLY_PARTIAL" if unsupported else "STAGED_UNVERIFIED",
            "source_profile": profile,
            "source_name": manifest["name"],
            "declared_source_commit_unverified": declared_source_commit,
            "source_fingerprint_sha256": sha,
            "registered_skill_names": names,
            "skill_reviews": review,
            "unsupported_source_components": unsupported,
            "unported_connector_names": sorted(connectors),
            "installation_performed": False,
            "runtime_execution_performed": False,
            "domain_defaults_changed": False,
            "model_rewrites_performed": False,
            "scope_note": "No model adaptation, approval prompts, installation or host execution in P6.1",
        }
        (out / "SOURCE_HASHES.json").write_text(
            json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out / "PORTING_REPORT.json").write_text(
            json.dumps(manifest_out, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (out / "REVIEW_REQUIRED.md").write_text(
            "# Inert conversion checkpoint\n\n"
            "No plugin was installed, enabled, or executed. Source SKILL.md "
            "files were byte-preserved. Review foreign syntax, permissions and "
            "connector gaps before approving runtime use.\n\n"
            "All foreign MCP connectors remain disconnected.\n",
            encoding="utf-8",
        )
        out.replace(target)
    return {
        "status": manifest_out["status"],
        "staged_path": str(target),
        "source_fingerprint_sha256": sha,
        "skills_staged": len(skills),
        "unported_connectors": len(connectors),
        "installation_performed": False,
        "execution_performed": False,
        "domain_defaults_changed": False,
        "next_gate": "Hermes Doctor + validate + exact-delta review before any install",
    }
