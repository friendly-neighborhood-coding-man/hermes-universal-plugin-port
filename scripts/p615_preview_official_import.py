"""Explicit read-only CLI bridge to a reviewed official agent-importers checkout.

Requires --package-sha256 to pin every file in the upstream plugin folder.
Does not import, enable, install, sync, or apply anything to Hermes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_import_assurance import AssuranceError, assess_official_preview


def package_digest(root: Path) -> str:
    if not root.is_dir() or root.is_symlink():
        raise AssuranceError('official package must be a real directory')
    files = []
    for p in root.rglob('*'):
        if '__pycache__' in p.parts or p.suffix in ('.pyc', '.pyo'):
            raise AssuranceError('unreviewed Python bytecode in official source tree')
        if p.is_symlink():
            raise AssuranceError('official package contains symbolic links')
        if p.is_file():
            files.append(p)
    if not (root / 'importer.py').is_file() or not (root / '__init__.py').is_file():
        raise AssuranceError('not an agent-importers package')
    h = hashlib.sha256()
    for p in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix().encode()
        data = p.read_bytes()
        h.update(len(rel).to_bytes(4, 'big') + rel)
        h.update(len(data).to_bytes(8, 'big') + data)
    return h.hexdigest()


def _is_redirect(p: Path) -> bool:
    """Symlink, or (Windows) a junction / other reparse point."""
    if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
        return True
    try:
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def redirects(root: Path, *, skip=("installs",)) -> list[str]:
    out = []
    for base, dirs, files in os.walk(root, followlinks=False):
        rel_base = Path(base).relative_to(root)
        for n in list(dirs) + files:
            if _is_redirect(Path(base) / n):
                out.append((Path(base) / n).relative_to(root).as_posix())
        dirs[:] = [d for d in dirs if not (rel_base == Path(".") and d in skip) and not _is_redirect(Path(base) / d)]
    return sorted(out)


def tree_digest(root: Path, *, skip=("installs",)) -> str:
    """SHA-256 over every path under root (type, link target, file bytes). Refuses nothing; records links."""
    h = hashlib.sha256()
    for base, dirs, files in os.walk(root, followlinks=False):
        rel_base = Path(base).relative_to(root)
        dirs[:] = sorted(d for d in dirs if not (rel_base == Path(".") and d in skip) and not _is_redirect(Path(base) / d))
        for name in sorted(dirs + files + [d for d in os.listdir(base) if d not in dirs and d not in files]):
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            if _is_redirect(path):
                try:
                    entry = "L:" + os.readlink(path)
                except OSError:
                    entry = "L:?"
            elif path.is_dir():
                entry = "D"
            else:
                entry = "F:" + hashlib.sha256(path.read_bytes()).hexdigest()
            h.update((rel + "\0" + entry + "\n").encode("utf-8"))
    return h.hexdigest()


def _target_config(target: Path) -> dict:
    cfg = target / "config.yaml"
    if not cfg.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise AssuranceError("PyYAML is required to read the target memory limits") from exc
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AssuranceError("target config.yaml is not a mapping")
    return data


def target_user_limit(target: Path) -> int:
    from official_import_assurance import configured_user_limit
    return configured_user_limit(_target_config(target))


def target_memory_limit(target: Path) -> int:
    """The target profile's effective memory.memory_char_limit (Hermes default 2200 when unset)."""
    from official_import_assurance import configured_memory_limit
    cfg = target / "config.yaml"
    if not cfg.is_file():
        return configured_memory_limit({})
    try:
        import yaml
    except ImportError as exc:
        raise AssuranceError("PyYAML is required to read the target memory limit") from exc
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AssuranceError("target config.yaml is not a mapping")
    return configured_memory_limit(data)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='UVP read-only assurance over official agent-importers preview')
    p.add_argument('--official-package', required=True, type=Path,
                   help='Reviewed, pinned agent-importers package directory (Python code will be imported)')
    p.add_argument('--package-sha256', required=True, help='Exact full SHA-256 of the package tree')
    p.add_argument('--agent', required=True, choices=('claude-code', 'codex', 'cursor'))
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--target', required=True, type=Path, help='Existing disposable Hermes home')
    p.add_argument('--memory-limit', required=True, type=int, help='Effective memory.memory_char_limit from target profile')
    p.add_argument('--output', required=True, type=Path, help='New local receipt outside the target home')
    p.add_argument('--i-confirm-disposable-home', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.official_package.is_symlink():
            raise AssuranceError('official package root must not be a symbolic link')
        root = args.official_package.resolve(strict=True)
        target = args.target.resolve(strict=True)
        source = args.source.resolve(strict=True)
        if not args.i_confirm_disposable_home:
            raise AssuranceError('disposable-home confirmation required')
        if root.name != 'agent-importers' or not source.is_dir() or not target.is_dir():
            raise AssuranceError('invalid official package, source, or disposable target')
        if len(args.package_sha256) != 64 or package_digest(root) != args.package_sha256.lower():
            raise AssuranceError('official package tree fingerprint mismatch')
        if args.output.exists() or args.output.resolve(strict=False).is_relative_to(target):
            raise AssuranceError('receipt must be create-only and outside target home')
        live_limit = target_memory_limit(target)
        if args.memory_limit != live_limit:
            raise AssuranceError('--memory-limit %d does not match the target profile memory.memory_char_limit %d'
                                 % (args.memory_limit, live_limit))
        if redirects(source):
            raise AssuranceError('source contains symlinks or junctions: %s' % ', '.join(redirects(source)[:5]))
        bad = [r for r in redirects(target) if r.split('/')[0] in ('memories', 'skills', 'config.yaml', 'cron')]
        if bad:
            raise AssuranceError('target import destinations contain symlinks or junctions: %s' % ', '.join(bad[:5]))
        source_before, target_before = tree_digest(source), tree_digest(target)
        if any(k == 'agent-importers' or k.startswith('agent-importers.') for k in sys.modules):
            raise AssuranceError('official module already loaded: refusing ambiguous import')
        sys.dont_write_bytecode = True  # avoid generating unreviewed pycache
        sys.path.insert(0, str(root.parent))
        official = importlib.import_module('agent-importers.importer')
        if not Path(official.__file__).resolve().is_relative_to(root):
            raise AssuranceError('official importer module resolved outside pinned package')
        imp = official.AgentImporter(args.agent, source, target, execute=False, overwrite=False)
        receipt = assess_official_preview(imp, memory_char_limit=args.memory_limit,
                            merge_entries=official.merge_entries,
                            parse_existing_memory_entries=official.parse_existing_memory_entries,
                            entry_delimiter=official.ENTRY_DELIMITER,
                            user_char_limit=target_user_limit(target))
        if package_digest(root) != args.package_sha256.lower():
            raise AssuranceError('official package changed during inspection')
        if tree_digest(target) != target_before:
            raise AssuranceError('official preview changed the target home (whole-home digest differs)')
        if tree_digest(source) != source_before:
            raise AssuranceError('official preview changed the source tree')
        receipt['source_tree_sha256'] = source_before
        receipt['target_tree_sha256'] = target_before
        receipt['agent'] = args.agent
        receipt['user_char_limit'] = target_user_limit(target)
        receipt['official_package_sha256'] = args.package_sha256.lower()
        receipt.pop('receipt_sha256', None)
        receipt['receipt_sha256'] = hashlib.sha256(json.dumps(receipt, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(receipt, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write('\n')
        print(json.dumps({'gate': receipt['gate'], 'receipt': str(args.output),
                          'memory_events': len(receipt['memory_events']),
                          'items': len(receipt['ledger']), 'apply_performed': False}))
        return 0 if receipt['gate'] == 'REVIEW_ONLY' else 2
    except (AssuranceError, OSError, ValueError, ImportError) as exc:
        print(f'HOLD: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
