"""Static compatibility report for a Skill package as the official importer would copy it (no execution).

For each Skill package: which relative links leave the Skill folder (they break after the official
importer copies only the folder), declared runtime dependencies (Python packages, system tools,
install commands), host-specific metadata the Hermes loader ignores, and host argument tokens.

  python scripts/p615_skill_compat_report.py --skill-pack DIR [--skill-pack DIR ...] --report OUT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
PIP = re.compile(r"(?:uv pip install|pip(?:3)? install|python3? -m pip install)\s+([^\n`]+)")
SYSTEM = re.compile(r"(?:brew install|apt-get install(?: -y)?|apt install(?: -y)?)\s+([^\n`]+)")
TOOLS = re.compile(r"`(pdftoppm|pdftotext|libreoffice|soffice|ffmpeg|node|npm|uv|docker|git|gh)`")
ARGS = re.compile(r"\$ARGUMENTS")
SHELL_VARS = re.compile(r"\$[A-Z][A-Z_]+")


def analyze(root: Path) -> dict:
    root = root.resolve(strict=True)
    files = sorted(p for p in root.rglob("*") if p.is_file())
    body = (root / "SKILL.md").read_text(encoding="utf-8")
    broken, local = [], []
    for m in LINK.finditer(body):
        link = m.group(1).split("#", 1)[0]
        if not link or re.match(r"^[a-z]+://", link) or link.startswith("mailto:"):
            continue
        target = (root / link).resolve(strict=False)
        (local if target.is_relative_to(root) and target.exists() else broken).append(link)
    host_meta = [p.relative_to(root).as_posix() for p in files
                 if p.relative_to(root).parts[0] in ("agents", ".claude-plugin", ".codex", ".cursor")]
    return {
        "skill": root.name,
        "files": len(files),
        "tree_sha256": hashlib.sha256("".join("%s\0%s\n" % (p.relative_to(root).as_posix(),
                                                            hashlib.sha256(p.read_bytes()).hexdigest())
                                              for p in files).encode()).hexdigest(),
        "links_resolving_inside_skill": sorted(set(local)),
        "links_leaving_skill_folder": sorted(set(broken)),
        "python_packages_declared": sorted({w for m in PIP.finditer(body) for w in m.group(1).split() if not w.startswith("-")}),
        "system_packages_declared": sorted({w for m in SYSTEM.finditer(body) for w in m.group(1).split() if not w.startswith("-")}),
        "external_tools_referenced": sorted(set(TOOLS.findall(body))),
        "host_argument_tokens": sorted(set(ARGS.findall(body))),
        "shell_placeholders": sorted(set(SHELL_VARS.findall(body)) - {"$ARGUMENTS"}),
        "host_specific_metadata_files": host_meta,
        "runtime_behavior": "NOT_EXECUTED (static analysis only)",
        "semantic_equivalence": "NOT_ESTABLISHED",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skill-pack", type=Path, action="append", required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args(argv)
    if a.report.exists():
        p.error("create-only report path required")
    rows = [analyze(x) for x in a.skill_pack]
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps({"schema": "uvp.p615.skill-compat/1", "packages": rows}, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        print(r["skill"], "broken links:", r["links_leaving_skill_folder"], "deps:", r["python_packages_declared"],
              r["system_packages_declared"], "tools:", r["external_tools_referenced"], "args:", r["host_argument_tokens"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
