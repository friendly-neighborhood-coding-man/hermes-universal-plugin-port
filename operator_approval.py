"""v0.4.2 (review R1/R2): adapter lock and explicit operator approval.

Transport adaptation, semantic review and runtime verification are separate:

* ``transport_status``: our fixed adapter delivers the original command text
  correctly. This is statically checked (``TRANSPORT_STATICALLY_VALID``).
* ``semantic_review``: a human operator has read the command and accepts its
  model-induced effects. Never inferred from the absence of risk phrases.
  Starts as ``NOT_REVIEWED``; ``approve()`` records ``OPERATOR_APPROVED``.
* runtime verification: still requires a trusted collector (none exists).

A generated adapter registers NOTHING until an approval record exists outside
the adapter folder (``<repair>/universal-port-approvals/<adapter>.json``,
installed as ``HERMES_HOME/universal-port-approvals/<adapter>.json``). The
record binds the approved commands to the digest of every adapter file, so
changing only ``ADAPTER_MANIFEST.json`` (for example an outcome string)
invalidates it and the adapter refuses to register anything.

Limits: this is an integrity binding with SHA-256, not cryptographic
authentication. Someone who can rewrite both the adapter folder and the
approval record (or the lock) can defeat it. Compare the adapter digest with
the value published outside the artifact (the external HANDOFF) before
review, doctor or enabling.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .port_core import PortError

LOCK_SCHEMA = 'universal-port.adapter-lock/2'  # v0.4.3: adds the exact per-file list
APPROVAL_SCHEMA = 'universal-port.operator-approval/1'
LOCK_NAME = 'ADAPTER_LOCK.json'
APPROVAL_DIR = 'universal-port-approvals'
APPROVABLE_OUTCOMES = frozenset({'ADAPTED_STATICALLY', 'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'})
INTEGRITY_NOTE = ('SHA-256 integrity binding, not cryptographic authentication: anyone able to rewrite both the '
                  'adapter folder and this record can defeat it. Compare adapter_package_sha256 with the value '
                  'published outside the artifact before doctor or enabling.')


def transport_status(result: dict) -> str:
    if result['outcome'] == 'UNSUPPORTED' or not result.get('static_checks'):
        return 'NOT_GENERATED'
    return 'TRANSPORT_STATICALLY_VALID' if result.get('static_checks_passed') else 'TRANSPORT_INVALID'


def registration_status(result: dict) -> str:
    if result['outcome'] in APPROVABLE_OUTCOMES and transport_status(result) == 'TRANSPORT_STATICALLY_VALID':
        return 'REQUIRES_OPERATOR_APPROVAL'
    return 'NOT_ELIGIBLE'


def build_lock(pkg: Path, entries: list[dict], results: list[dict], package_sha: str,
               template_sha: str, renderer_sha: str, files: dict | None = None) -> dict:
    rows = []
    for e, r in zip(entries, results):
        rows.append({'source_name': e['source_name'], 'hermes_command': e['hermes_command'],
                     'source_sha256': e['source_sha256'], 'outcome': r['outcome'],
                     'transport_status': transport_status(r), 'semantic_review': 'NOT_REVIEWED',
                     'registration': registration_status(r)})
    return {'schema': LOCK_SCHEMA, 'adapter': pkg.name, 'adapter_package_sha256': package_sha,
            'entry_template_sha256': template_sha, 'renderer_sha256': renderer_sha,
            'files': dict(sorted((files or {}).items())),
            'registered_by_default': [], 'commands': rows,
            'note': 'Nothing registers until an operator approval record exists. ' + INTEGRITY_NOTE}


def _load_lock(repair_dir: Path) -> dict:
    path = repair_dir / LOCK_NAME
    if not path.is_file():
        raise PortError('No ' + LOCK_NAME + ' in ' + str(repair_dir) + ' (not a v0.4.2 repair output)')
    lock = json.loads(path.read_text(encoding='utf-8'))
    if lock.get('schema') != LOCK_SCHEMA:
        raise PortError('Unknown adapter lock schema')
    return lock


def approval_path(repair_dir: Path, adapter_name: str) -> Path:
    return repair_dir / APPROVAL_DIR / (adapter_name + '.json')


def verify_adapter(repair_dir: str, *, adapter: str | None = None, expected_sha256: str | None = None) -> dict:
    """Check an adapter folder against the lock, the reviewed templates and (optionally) an external digest."""
    from .slash_repair import entry_template_sha256, renderer_sha256
    from .pre_import_gate import preflight
    import hashlib
    rdir = Path(repair_dir).expanduser().resolve()
    lock = _load_lock(rdir)
    pkg = Path(adapter).expanduser().resolve() if adapter else rdir / 'adapter' / lock['adapter']
    problems = []
    if pkg.name != lock['adapter']:
        problems.append('adapter folder name ' + pkg.name + ' != locked ' + lock['adapter'])
    if not pkg.is_dir():
        raise PortError('Adapter folder not found: ' + str(pkg))
    # v0.4.3 (review P0): exact-tree pre-import gate first (rejects __pycache__/.pyc/extension modules).
    gate = preflight(pkg, lock=lock, expected_sha256=expected_sha256)
    problems += gate['problems']
    actual = gate['package_sha256']
    for fname, reviewed, locked in (('__init__.py', entry_template_sha256(), lock['entry_template_sha256']),
                                    ('claude_command.py', renderer_sha256(), lock['renderer_sha256'])):
        f = pkg / fname
        got = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() and not f.is_symlink() else None
        if got != reviewed or got != locked:
            problems.append(fname + ' differs from the reviewed template in this plugin')
    ap = approval_path(rdir, lock['adapter'])
    approval_status, approved = 'NONE', []
    if ap.exists():
        try:
            rec = json.loads(ap.read_text(encoding='utf-8'))
            ok = rec.get('schema') == APPROVAL_SCHEMA and rec.get('adapter') == lock['adapter']
            approval_status = ('VALID' if actual and rec.get('adapter_package_sha256') == actual else 'STALE') \
                if ok else 'INVALID'
            approved = [a.get('hermes_command') for a in rec.get('approved', [])]
        except (ValueError, OSError):
            approval_status = 'INVALID'
    return {'ok': not problems, 'problems': problems, 'adapter': str(pkg), 'adapter_name': lock['adapter'],
            'pre_import_gate': 'PASS' if not gate['problems'] else 'FAIL',
            'actual_package_sha256': actual, 'locked_package_sha256': lock['adapter_package_sha256'],
            'external_digest_checked': bool(expected_sha256), 'approval_status': approval_status,
            'approved_commands': approved,
            'eligible_commands': [c['hermes_command'] for c in lock['commands']
                                  if c['registration'] == 'REQUIRES_OPERATOR_APPROVAL'],
            'integrity_note': INTEGRITY_NOTE}


def approve(repair_dir: str, commands: list[str], *, operator: str, reviewed_model_induced_effects: bool,
            expected_sha256: str | None = None, note: str = '') -> dict:
    """Write an explicit operator approval for named, eligible commands. Never approves anything implicitly."""
    if reviewed_model_induced_effects is not True:
        raise PortError('Approval requires confirming that you reviewed the model-induced effects of each command')
    if not (operator or '').strip():
        raise PortError('Approval requires an operator name')
    names = [c.lstrip('/') for c in commands or []]
    if not names:
        raise PortError('Name at least one command to approve (there is no approve-all)')
    if len(set(names)) != len(names):
        raise PortError('Duplicate command in approval request')
    rdir = Path(repair_dir).expanduser().resolve()
    check = verify_adapter(str(rdir), expected_sha256=expected_sha256)
    if not check['ok']:
        raise PortError('Adapter verification failed; nothing approved: ' + '; '.join(check['problems']))
    lock = _load_lock(rdir)
    approved = []
    for n in names:
        rows = [c for c in lock['commands'] if n in (c['source_name'], c['hermes_command'])]
        if len(rows) != 1:
            raise PortError('Unknown command: ' + n)
        row = rows[0]
        if row['registration'] != 'REQUIRES_OPERATOR_APPROVAL':
            raise PortError('/' + n + ' is not eligible for approval (outcome ' + row['outcome'] + ', transport '
                            + row['transport_status'] + ')')
        approved.append({k: row[k] for k in ('source_name', 'hermes_command', 'source_sha256', 'outcome')})
    path = approval_path(rdir, lock['adapter'])
    if path.exists():
        raise PortError('Approval record already exists (delete it deliberately to re-approve): ' + str(path))
    record = {
        'schema': APPROVAL_SCHEMA, 'adapter': lock['adapter'],
        'adapter_package_sha256': check['actual_package_sha256'],
        'approved': approved, 'operator': operator.strip(),
        'approved_utc': datetime.now(timezone.utc).isoformat(),
        'semantic_review': 'OPERATOR_APPROVED',
        'statement': 'Operator read each approved command and accepts its model-induced effects. This is NOT '
                     'runtime verification and does not make the command install-ready.',
        'external_digest_checked': bool(expected_sha256), 'note': note[:500],
        'integrity_note': INTEGRITY_NOTE,
    }
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return {'approval_path': str(path), **record}


def stage(repair_dir: str, hermes_home: str, *, confirm_disposable: bool, expected_sha256: str | None = None) -> dict:
    """v0.4.3: copy ONLY the locked files into a NEW <hermes_home>/plugins/<adapter> (clean staging).

    Every file is re-hashed against the lock while copying, the staged tree is
    re-checked by the pre-import gate, and a VALID approval record (if any) is
    copied to <hermes_home>/universal-port-approvals/. Nothing is enabled, and
    existing folders are never overwritten or deleted. Re-run `verify-adapter
    --adapter <staged>` right before starting Hermes.
    """
    from .pre_import_gate import preflight
    import hashlib
    if confirm_disposable is not True:
        raise PortError('Staging requires confirming that the Hermes home is a disposable test profile')
    rdir = Path(repair_dir).expanduser().resolve()
    check = verify_adapter(str(rdir), expected_sha256=expected_sha256)
    if not check['ok']:
        raise PortError('Adapter verification failed; nothing staged: ' + '; '.join(check['problems']))
    lock = _load_lock(rdir)
    home = Path(hermes_home).expanduser().resolve()
    if home.name.lower() == 'data':
        raise PortError('Refusing a Hermes home named like a real data folder: ' + str(home))
    src = Path(check['adapter'])
    dest = home / 'plugins' / lock['adapter']
    if dest.exists():
        raise PortError('Refusing to overwrite an existing plugin folder: ' + str(dest))
    approval_src = approval_path(rdir, lock['adapter'])
    approval_dest = home / APPROVAL_DIR / (lock['adapter'] + '.json')
    if check['approval_status'] == 'VALID' and approval_dest.exists():
        raise PortError('Refusing to overwrite an existing approval record: ' + str(approval_dest))
    for rel, sha in lock['files'].items():
        data = (src / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise PortError('File changed during staging: ' + rel)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    gate = preflight(dest, lock=lock, expected_sha256=expected_sha256)
    if not gate['ok']:
        raise PortError('Staged folder failed the pre-import gate (left in place for inspection): '
                        + '; '.join(gate['problems']))
    staged_approval = None
    if check['approval_status'] == 'VALID':
        approval_dest.parent.mkdir(parents=True, exist_ok=True)
        approval_dest.write_bytes(approval_src.read_bytes())
        staged_approval = str(approval_dest)
    return {'staged_adapter': str(dest), 'package_sha256': gate['package_sha256'],
            'pre_import_gate': 'PASS', 'approval_staged': staged_approval,
            'approval_status': check['approval_status'], 'enabled': False,
            'next': 'Set PYTHONDONTWRITEBYTECODE=1 for the Hermes process and run verify-adapter --adapter '
                    + str(dest) + ' immediately before starting Hermes.'}
