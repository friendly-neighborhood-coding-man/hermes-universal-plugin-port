"""v0.4.3 (review P0): pre-import gate for generated adapters.

Runs OUTSIDE the adapter, before anything imports it: before our own loader,
`verify-adapter`, `approve`, `stage`, doctor/validate, installation, enabling
or starting a Hermes process. It must not be implemented inside the adapter's
``__init__.py``: by the time that code runs, Python has already chosen what to
execute, and a planted ``__pycache__/__init__.cpython-XY.pyc`` (for example an
unchecked-hash .pyc) can replace it entirely while the ``.py`` source, the
manifest and the folder digest still look correct.

The gate allows EXACTLY this tree and nothing else (case-sensitive names, no
symlinks or junctions, no other file types):

    ADAPTER_MANIFEST.json  __init__.py  claude_command.py  plugin.yaml
    commands/<file>.md     (only the files the manifest lists)

so ``__pycache__``, ``*.pyc``/``*.pyo``, extension modules (``*.so``/``*.pyd``,
which Python's finder prefers over ``.py``), ``*.pth``, zip/egg/whl archives
and extra ``.py`` modules are all rejected. The digest covers every file, with
no exclusions. A pass is a statement about the tree at the moment of the scan:
anyone with write access afterwards can still change it, so stage into a
fresh, access-controlled folder and run the gate again right before import.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ALLOWED_TOP_FILES = frozenset({'ADAPTER_MANIFEST.json', '__init__.py', 'claude_command.py', 'plugin.yaml'})
ALLOWED_DIRS = frozenset({'commands'})
IMPORTABLE_HINTS = ('.pyc', '.pyo', '.so', '.pyd', '.dll', '.dylib', '.pth', '.zip', '.egg', '.whl', '.py')


def _is_link(entry: os.DirEntry) -> bool:
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, 'is_junction', None)  # Python 3.12+ (Windows junctions)
    return bool(is_junction and is_junction())


def _describe(rel: str) -> str:
    low = rel.lower()
    if '__pycache__' in low or low.endswith(('.pyc', '.pyo')):
        return 'Python bytecode cache (could replace the reviewed source at import)'
    if low.endswith(IMPORTABLE_HINTS):
        return 'importable or executable artifact'
    return 'not part of the generated adapter'


def digest_files(files: dict[str, bytes]) -> str:
    """Same construction as slash_repair._package_files_sha256 and the template's package_sha256."""
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b'\0' + hashlib.sha256(files[rel]).digest())
    return h.hexdigest()


def scan(pkg) -> dict:
    """Structural allowlist scan. Never imports or executes anything from pkg."""
    pkg = Path(pkg)
    problems: list[str] = []
    contents: dict[str, bytes] = {}
    if os.path.islink(pkg) or not pkg.is_dir():
        return {'ok': False, 'problems': ['adapter path is not a real directory: ' + str(pkg)],
                'files': {}, 'package_sha256': None}

    def walk(folder: Path, rel_prefix: str, depth: int):
        with os.scandir(folder) as it:
            for entry in sorted(it, key=lambda e: e.name):
                rel = rel_prefix + entry.name
                if _is_link(entry):
                    problems.append('symlink/junction not allowed: ' + rel)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth == 0 and entry.name in ALLOWED_DIRS:
                        walk(Path(entry.path), rel + '/', depth + 1)
                    else:
                        problems.append('unexpected directory ' + rel + '/ (' + _describe(rel + '/') + ')')
                    continue
                if not entry.is_file(follow_symlinks=False):
                    problems.append('unexpected special file: ' + rel)
                    continue
                allowed = entry.name in ALLOWED_TOP_FILES if depth == 0 else entry.name.endswith('.md')
                if not allowed:
                    problems.append('unexpected file ' + rel + ' (' + _describe(rel) + ')')
                    continue
                contents[rel] = Path(entry.path).read_bytes()

    walk(pkg, '', 0)
    for required in sorted(ALLOWED_TOP_FILES):
        if required not in contents:
            problems.append('missing required file: ' + required)
    listed = None
    if 'ADAPTER_MANIFEST.json' in contents:
        try:
            manifest = json.loads(contents['ADAPTER_MANIFEST.json'].decode('utf-8'))
            listed = {'commands/' + c['file'] for c in manifest.get('commands', [])}
        except (ValueError, KeyError, TypeError, UnicodeError):
            problems.append('ADAPTER_MANIFEST.json is not a valid manifest')
    if listed is not None:
        present = {r for r in contents if r.startswith('commands/')}
        for extra in sorted(present - listed):
            problems.append('command file not listed in the manifest: ' + extra)
        for missing in sorted(listed - present):
            problems.append('manifest lists a missing command file: ' + missing)
    return {'ok': not problems, 'problems': problems,
            'files': {r: hashlib.sha256(b).hexdigest() for r, b in sorted(contents.items())},
            'package_sha256': digest_files(contents) if not problems else None}


def preflight(pkg, *, lock: dict | None = None, expected_sha256: str | None = None) -> dict:
    """Scan plus exact comparison with the lock's file list and digests (and an optional external digest)."""
    res = scan(pkg)
    problems = list(res['problems'])
    if lock is not None and res['ok']:
        locked = lock.get('files') or {}
        if set(locked) != set(res['files']):
            problems.append('file set differs from ADAPTER_LOCK.json')
        for rel, sha in res['files'].items():
            if rel in locked and locked[rel] != sha:
                problems.append('content of ' + rel + ' differs from ADAPTER_LOCK.json')
        if res['package_sha256'] != lock.get('adapter_package_sha256'):
            problems.append('adapter folder digest differs from ADAPTER_LOCK.json')
    if expected_sha256 and res['package_sha256'] != expected_sha256.strip().lower():
        problems.append('adapter folder digest differs from the externally supplied digest')
    return {**res, 'ok': not problems, 'problems': problems}
