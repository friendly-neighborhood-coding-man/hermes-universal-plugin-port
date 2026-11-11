"""P6.12 WP5: install / update / rollback / remove of a ported plugin in a DISPOSABLE Hermes home.

Every operation:
  - refuses any home not explicitly marked disposable (a `.uvp-disposable` file),
  - snapshots the home manifest (path -> SHA-256, excluding caches and logs) before
    acting, and keeps a backup of the plugin dir and config.yaml,
  - validates a candidate BEFORE swapping it in (hash check against its own
    SOURCE_HASHES.json/PORTING_REPORT.json plus an optional external validator),
  - verifies AFTER the swap (optional resolution check) and rolls back automatically
    on failure, so the home returns to the pre-operation manifest.
Enabling/disabling is delegated to a caller-supplied function (the real `hermes
plugins enable/disable` CLI in the exercise script).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

if __package__:
    from .port_core import PortError
else:
    from port_core import PortError

MARKER = ".uvp-disposable"
SKIP_PARTS = {"__pycache__", "logs", "cache", "sessions", "state", "telemetry", ".uvp-backups"}
SKIP_FILES = {"state.db", "state.db-wal", "state.db-shm", ".usage.json", "gateway_state.json", "gateway.pid",
              "gateway.lock", "auth.lock", "install_id"}


def manifest(home: Path) -> dict:
    home = Path(home)
    out = {}
    for p in sorted(home.rglob("*")):
        rel = p.relative_to(home)
        if any(part in SKIP_PARTS for part in rel.parts) or p.name in SKIP_FILES or p.is_dir() or p.is_symlink():
            continue
        out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


COPY_IGNORE = ("__pycache__", "P6_REVIEW_CANDIDATES")


def is_redirect(p: Path) -> bool:
    """Symlink, or (Windows) a junction / other reparse point."""
    p = Path(p)
    if p.is_symlink():
        return True
    is_junction = getattr(p, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        attrs = getattr(os.lstat(p), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def package_files(pkg: Path) -> dict:
    """relpath -> SHA-256 of every file Installer copies. Refuses any redirect inside the package."""
    pkg = Path(pkg)
    if is_redirect(pkg):
        raise PortError("Package root is a symlink or junction")
    out = {}
    for p in sorted(pkg.rglob("*")):
        rel = p.relative_to(pkg)
        if any(part in COPY_IGNORE for part in rel.parts):
            continue
        if is_redirect(p):
            raise PortError("Package contains a symlink or junction: " + rel.as_posix())
        if p.is_file():
            out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def package_digest(pkg: Path) -> str:
    """One SHA-256 over the sorted (path, file SHA-256) list: the identity a user approves."""
    lines = "".join("%s\0%s\n" % kv for kv in sorted(package_files(pkg).items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _guard(home: Path) -> Path:
    home = Path(home).resolve()
    if not (home / MARKER).is_file():
        raise PortError("Refusing: %s is not marked disposable (%s)" % (home, MARKER))
    return home


def verify_package(pkg: Path) -> dict:
    """Self-consistency of a staged ported package: originals vs SOURCE_HASHES, active == original."""
    pkg = Path(pkg)
    try:
        hashes = json.loads((pkg / "SOURCE_HASHES.json").read_text(encoding="utf-8"))
        report = json.loads((pkg / "PORTING_REPORT.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "why": "manifest unreadable: " + type(exc).__name__}
    bad = [k for k, v in hashes.items()
           if not (pkg / "original" / k).is_file() or hashlib.sha256((pkg / "original" / k).read_bytes()).hexdigest() != v]
    # An adapted package declares every changed/added file with its expected SHA-256.
    adapted = {}
    if (pkg / "ADAPTATION_MANIFEST.json").is_file():
        try:
            man = json.loads((pkg / "ADAPTATION_MANIFEST.json").read_text(encoding="utf-8"))
            adapted = {c["path"]: c for c in man.get("changes", [])}
        except (OSError, ValueError, KeyError, TypeError):
            return {"ok": False, "why": "ADAPTATION_MANIFEST unreadable"}
        for path, c in adapted.items():
            f = pkg / path
            if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != c.get("after_sha256"):
                bad.append(path + " (adaptation hash)")
    for row in report.get("skill_reviews", []):
        rel = "skills/%s/SKILL.md" % row["skill"]
        a = pkg / rel
        if rel in adapted:
            if adapted[rel].get("original_sha256") != row["original_sha256"]:
                bad.append(rel + " (adaptation bound to a different original)")
            continue
        if not a.is_file() or hashlib.sha256(a.read_bytes()).hexdigest() != row["original_sha256"]:
            bad.append(rel)
    for f in ("plugin.yaml", "__init__.py"):
        if not (pkg / f).is_file():
            bad.append(f)
    try:
        compile((pkg / "__init__.py").read_text(encoding="utf-8"), "__init__.py", "exec")
    except (OSError, SyntaxError, ValueError):
        bad.append("__init__.py (does not compile)")
    return {"ok": not bad, "why": ", ".join(sorted(set(bad)))[:400]}


def drop_from_plugin_lists(config_text: str, name: str) -> str:
    """Remove exact `- <name>` items from plugins.enabled / plugins.disabled only.
    `hermes plugins disable` leaves the removed plugin in plugins.disabled."""
    lines = config_text.splitlines(keepends=True)
    out, in_plugins, current = [], False, None
    for line in lines:
        s = line.rstrip("\r\n")
        if s and not s.startswith(" "):
            in_plugins, current = s.startswith("plugins:"), None
        elif in_plugins and s.strip() in ("enabled:", "disabled:"):
            current = s.strip()[:-1]
        elif in_plugins and current and s.strip() == "- " + name:
            continue
        out.append(line)
    # A list left with no items becomes an explicit empty list.
    fixed = []
    for i, line in enumerate(out):
        s = line.rstrip("\r\n")
        nxt = out[i + 1].strip() if i + 1 < len(out) else ""
        if s.strip() in ("enabled:", "disabled:") and s.startswith("  ") and not nxt.startswith("- "):
            line = s + " []" + line[len(s):]
        fixed.append(line)
    return "".join(fixed)


class Installer:
    def __init__(self, home: Path, name: str, *, enable=None, disable=None, validate=None, check=None):
        self.home = _guard(home)
        self.name = name
        self.enable, self.disable = enable, disable
        self.validate, self.check = validate, check
        self.log: list = []

    @property
    def target(self) -> Path:
        return self.home / "plugins" / self.name

    def _backup(self) -> Path:
        b = self.home / ".uvp-backups" / ("%s-%d" % (self.name, time.time_ns()))
        b.mkdir(parents=True)
        shutil.copy2(self.home / "config.yaml", b / "config.yaml")
        if self.target.exists():
            shutil.copytree(self.target, b / "plugin")
        return b

    def _restore(self, b: Path):
        if self.target.exists():
            shutil.rmtree(self.target)
        if (b / "plugin").exists():
            shutil.copytree(b / "plugin", self.target)
        shutil.copy2(b / "config.yaml", self.home / "config.yaml")

    def _candidate_ok(self, pkg: Path) -> dict:
        r = verify_package(pkg)
        if r["ok"] and self.validate is not None:
            v = self.validate(pkg)
            r = {"ok": bool(v.get("ok")), "why": v.get("why", "")}
        return r

    def _apply(self, op: str, pkg: Path | None) -> dict:
        before = manifest(self.home)
        if pkg is not None:
            pre = self._candidate_ok(pkg)
            if not pre["ok"]:
                self.log.append({"op": op, "result": "REFUSED_BEFORE_SWAP", "why": pre["why"]})
                return {"ok": False, "result": "REFUSED_BEFORE_SWAP", "why": pre["why"],
                        "manifest_unchanged": manifest(self.home) == before}
        b = self._backup()
        try:
            if self.target.exists():
                if self.disable:
                    self.disable(self.name)
                shutil.rmtree(self.target)
            if pkg is not None:
                shutil.copytree(pkg, self.target, ignore=shutil.ignore_patterns(*COPY_IGNORE))
                if self.enable:
                    self.enable(self.name)
                if self.check is not None:
                    c = self.check()
                    if not c.get("ok"):
                        raise PortError("post-install check failed: " + str(c.get("why", ""))[:200])
        except Exception as exc:
            self._restore(b)
            restored = manifest(self.home) == before
            self.log.append({"op": op, "result": "ROLLED_BACK", "why": str(exc)[:200], "restored": restored})
            return {"ok": False, "result": "ROLLED_BACK", "why": str(exc)[:200], "manifest_restored": restored, "backup": str(b)}
        self.log.append({"op": op, "result": "APPLIED"})
        return {"ok": True, "result": "APPLIED", "backup": str(b)}

    def install(self, pkg: Path) -> dict:
        if self.target.exists():
            raise PortError("Already installed; use update")
        return self._apply("install", Path(pkg))

    def update(self, pkg: Path) -> dict:
        if not self.target.exists():
            raise PortError("Not installed")
        return self._apply("update", Path(pkg))

    def remove(self) -> dict:
        if not self.target.exists():
            raise PortError("Not installed")
        r = self._apply("remove", None)
        if r["ok"]:
            cfg = self.home / "config.yaml"
            cfg.write_text(drop_from_plugin_lists(cfg.read_text(encoding="utf-8"), self.name), encoding="utf-8")
        return r

    def rollback_to(self, backup: Path) -> dict:
        self._restore(Path(backup))  # plugin dir + config.yaml byte-for-byte from the backup
        self.log.append({"op": "rollback", "result": "RESTORED", "backup": str(backup)})
        return {"ok": True, "result": "RESTORED"}


# --- P6.14 WP3: exact home inventory and residual classification ------------------------------

# Hermes's own runtime environment (a full Python venv) is inventoried by size + mtime only.
_UNHASHED_PREFIXES = ("installs/",)
# Hermes-created runtime state, by path prefix (listed in docs/P6_14_INTEGRATION_REPORT.md).
_HERMES_RUNTIME = ("installs/", "logs/", "cache/", "sessions/", "state/", "telemetry/", "audio_cache/", "image_cache/",
                   "kanban", "state.db", ".skills_prompt_snapshot.json", ".usage.json", "gateway", "auth.lock",
                   "install_id", ".install_id.lock", ".hermes_history", "channel_directory.json",
                   ".hermes-update-in-progress.lock", "skills/.usage.json")


def full_inventory(home: Path) -> dict:
    """Every path under home: type, size, mtime_ns, SHA-256 (regular files outside installs/), link target."""
    home = Path(home)
    out = {}
    for root, dirs, files in os.walk(home, followlinks=False):
        for name in list(dirs) + files:
            p = Path(root) / name
            rel = p.relative_to(home).as_posix()
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if is_redirect(p):
                try:
                    tgt = os.readlink(p)
                except OSError:
                    tgt = "unreadable"
                out[rel] = {"type": "link", "target": str(tgt)}
                if name in dirs:
                    dirs.remove(name)
            elif p.is_dir():
                out[rel] = {"type": "dir"}
            else:
                row = {"type": "file", "size": st.st_size, "mtime_ns": st.st_mtime_ns}
                if not rel.startswith(_UNHASHED_PREFIXES):
                    try:
                        row["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
                    except OSError:
                        row["sha256"] = None
                out[rel] = row
    return out


def _same(a: dict, b: dict) -> bool:
    if a.get("type") != b.get("type"):
        return False
    if a["type"] == "file":
        if "sha256" in a and "sha256" in b:
            return a["sha256"] == b["sha256"]
        return a.get("size") == b.get("size") and a.get("mtime_ns") == b.get("mtime_ns")
    return a.get("target") == b.get("target")


def classify_residuals(before: dict, after: dict, *, plugin: str) -> dict:
    """Exact diff of two full_inventory() snapshots; every difference gets one class."""
    rows = []
    for rel in sorted(set(before) | set(after)):
        b, a = before.get(rel), after.get(rel)
        if b is not None and a is not None and _same(b, a):
            continue
        change = "added" if b is None else "removed" if a is None else "modified"
        if rel == "plugins/" + plugin or rel.startswith("plugins/%s/" % plugin):
            cls = "UNEXPECTED_RESIDUAL" if a is not None else "UVP_CREATED_AND_REMOVED"
        elif rel == ".uvp-backups" or rel.startswith(".uvp-backups/"):
            cls = "EXPECTED_AUDIT_BACKUP"
        elif rel == "backups" or rel.startswith("backups/"):
            cls = "HERMES_CREATED_BACKUP"
        elif rel in ("config.yaml", "plugins") or rel.startswith("plugins/"):
            cls = "UNEXPECTED_RESIDUAL"
        elif change == "removed":
            cls = "UNEXPECTED_RESIDUAL"          # something that existed before is gone
        elif rel.startswith(_HERMES_RUNTIME) or "__pycache__" in rel.split("/"):
            cls = "HERMES_RUNTIME_STATE"
        else:
            cls = "UNATTRIBUTED"
        rows.append({"path": rel, "change": change, "class": cls})
    preserved = sum(1 for rel in before if rel in after and _same(before[rel], after[rel]))
    summary = {"EXISTING_DATA_PRESERVED": preserved}
    for r in rows:
        summary[r["class"]] = summary.get(r["class"], 0) + 1
    return {"summary": summary, "differences": rows, "full_home_byte_identical": not rows,
            "config_yaml_identical": "config.yaml" not in {r["path"] for r in rows}}
