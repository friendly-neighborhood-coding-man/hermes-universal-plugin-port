"""Phase 3: Capability Passports + Understanding Snapshot v2, built from pipeline state.

Every value here is copied from the actual repair/verification results passed
in; nothing is defaulted to a success value. There is deliberately no single
`success` boolean: six stage flags are reported separately.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import claude_command as CC
from . import operator_approval as OA

PASSPORT_SCHEMA = 'universal-port.capability-passport/1'
SNAPSHOT_SCHEMA = 'universal-port.understanding-snapshot/2'
_HERE = Path(__file__).resolve().parent


def _sha_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def golden_cases_sha256() -> str:
    return hashlib.sha256((_HERE / 'semantics' / 'claude_argument_cases.json').read_bytes()).hexdigest()


def non_command_fingerprint(plan: dict) -> str:
    """Fingerprint of every source file EXCEPT command files (settings, agents, hooks...)."""
    from .port_core import enumerate_files
    root = Path(plan['source'])
    commands = {Path(c['path']).as_posix() for c in plan.get('commands') or []}
    h = hashlib.sha256()
    for f in enumerate_files(root):
        rel = f.relative_to(root).as_posix()
        if rel not in commands:
            h.update(rel.encode() + b'\0' + hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def engine_identity() -> dict:
    from .slash_repair import REPAIR_ENGINE_VERSION, entry_template_sha256, renderer_sha256
    return {'repair_engine_version': REPAIR_ENGINE_VERSION, 'renderer_sha256': renderer_sha256(),
            'entry_template_sha256': entry_template_sha256(),
            'claude_semantics_version': CC.SEMANTICS_VERSION,
            'claude_semantics_source_sha256': CC.SEMANTICS_SOURCE_SHA256,
            'golden_cases_sha256': golden_cases_sha256()}


def passport_for(plan: dict, u: dict, r: dict, adapter_sha: str, target: dict, source_commit) -> dict:
    limitations = []
    for dim, v in (r.get('dimensions') or {}).items():
        if v['static'] in {'NOT_PRESERVED', 'UNKNOWN', 'VIOLATION'}:
            limitations += [f'{dim} [{v["static"]}]: {x}' for x in v['reasons']]
        else:
            limitations += [f'{dim} [warning]: {x}' for x in v['reasons'] if x.startswith('Warning')]
        limitations += [f'{dim} [condition]: {x}' for x in v.get('conditions', [])]
    if r['outcome'] in {'UNSUPPORTED', 'BLOCKED_UNSAFE'}:
        limitations += list(r.get('reasons', []))
    eng = engine_identity()
    adapted = r['outcome'] not in {'UNSUPPORTED'} and u['parse']['ok']
    return {
        'schema': PASSPORT_SCHEMA,
        'capability_id': u['capability_id'],
        'source': {
            'platform': 'claude-code', 'plugin': plan['name'], 'kind': 'slash_command',
            'path': u['source_path'], 'sha256': u['source_sha256'],
            'commit': source_commit or None,
            'revision_status': 'PINNED_COMMIT' if source_commit else 'UNPINNED_LOCAL_TREE_FINGERPRINT_ONLY',
            'tree_fingerprint_sha256': plan['fingerprint_sha256'],
        },
        'target': {'platform': 'hermes-agent', **target},
        'integration': {
            'method': 'native_command_template' if adapted else 'none',
            'hermes_command': ('/' + u['hermes_command']) if u.get('hermes_command') and adapted else None,
            'adapter_package_sha256': adapter_sha if adapted else None,
            # v0.4.2 (review R1): transport validity, semantic review and runtime
            # verification are separate; nothing registers without operator approval.
            'transport_status': OA.transport_status(r),
            'semantic_review': 'NOT_REVIEWED',
            'registration': OA.registration_status(r) if u.get('hermes_command') else 'NOT_ELIGIBLE',
            'registered_by_default': False,
            'renderer_sha256': eng['renderer_sha256'], 'entry_template_sha256': eng['entry_template_sha256'],
            'ai_integration_used': False, 'model_calls': 0,
            'cost_note': 'Deterministic adaptation; no model call was made. No cost figures are claimed.',
        },
        'semantic_contract': {
            'reference': CC.SEMANTICS_SOURCE, 'reference_sha256': CC.SEMANTICS_SOURCE_SHA256,
            'version': CC.SEMANTICS_VERSION,
            'dimensions': {k: v['static'] for k, v in (r.get('dimensions') or {}).items()},
        },
        'stages': r['stages'],
        'outcome': r['outcome'],
        'verification': {
            'static_checks_passed': bool(r.get('static_checks_passed')),
            'static_checks_total': len(r.get('static_checks') or []),
            'static_checks_failed': [c['check'] for c in (r.get('static_checks') or []) if c['result'] != 'PASS'],
            'runtime_status': r['runtime']['status'],
            'runtime_dimensions': r['runtime']['dimensions'],
            'runtime_evidence_sha256': r['runtime'].get('evidence_sha256'),
            'evidence_references': ['VERIFICATION_RESULTS.json#' + u['capability_id']],
            'direct_bridge': r.get('direct_bridge'),
        },
        'known_limitations': limitations,
        'last_verified': {
            'static': {'engine': eng['repair_engine_version'], 'target_facts': target['facts_id']},
            'runtime_hermes_version': target['installed_hermes_version'] if r['runtime']['status'] == 'PASS' else None,
        },
        'update_compatibility': 'BASELINE',
    }


def build_bundle(plan, understood, results, entries, adapter_sha, target, *, source_commit=None) -> dict:
    passports = [passport_for(plan, u, r, adapter_sha, target, source_commit) for u, r in zip(understood, results)]
    counts = {}
    for p in passports:
        counts[p['outcome']] = counts.get(p['outcome'], 0) + 1
    eng = engine_identity()
    snapshot = {
        'schema': SNAPSHOT_SCHEMA,
        'source': {'platform': 'claude-code', 'plugin': plan['name'], 'commit': source_commit,
                   'tree_fingerprint_sha256': plan['fingerprint_sha256'],
                   'non_command_fingerprint_sha256': non_command_fingerprint(plan)},
        'target': target, 'engine': eng,
        'capabilities': [{
            'capability_id': u['capability_id'], 'source_path': u['source_path'],
            'source_sha256': u['source_sha256'], 'body_sha256': u.get('body_sha256'),
            'hermes_command': u.get('hermes_command'), 'outcome': r['outcome'],
            'dimension_statuses': {k: v['static'] for k, v in (r.get('dimensions') or {}).items()},
            'runtime_status': r['runtime']['status'],
            'runtime_evidence_sha256': r['runtime'].get('evidence_sha256'),
            'analysis_digest': _sha_json(u),
        } for u, r in zip(understood, results)],
        'note': 'Hashes and statuses only: no source text, credentials or model reasoning are stored.',
    }
    return {
        'schema': 'universal-port.repair-bundle/1',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'source_plugin': plan['name'], 'source_profile': plan['profile'],
        'outcome_counts': dict(sorted(counts.items())),
        'runtime_verified_count': sum(1 for p in passports if p['stages']['runtime_behavior_verified']),
        'ready_for_installation_count': sum(1 for p in passports if p['stages']['ready_for_installation']),
        'passports': passports,
        'verification': [{'capability_id': u['capability_id'], 'understanding': u,
                          **{k: r[k] for k in r if k not in {'capability_id'}}}
                         for u, r in zip(understood, results)],
        'snapshot': snapshot,
        'adapter_manifest_entries': entries,
        'installation': {'performed': False,
                         'policy': 'This tool never installs or enables adapters. Only capabilities whose stage '
                                   'ready_for_installation is true may be considered, and only by explicit user action.'},
    }


# Must equal generated_command_entry.REGISTRABLE_OUTCOMES (enforced by a test).
REGISTERED_BY_DEFAULT_OUTCOMES = OA.APPROVABLE_OUTCOMES


def _cmd_cell(p):
    cmd = p['integration']['hermes_command']
    if not cmd:
        return '—'
    if p['integration'].get('registration') == 'REQUIRES_OPERATOR_APPROVAL':
        return '`' + cmd + '` (needs operator approval)'
    return '`' + cmd + '` (not registered)'


def render_markdown(bundle: dict) -> str:
    lines = ['# Capability Passport — ' + bundle['source_plugin'], '',
             'Generated from actual pipeline state at ' + bundle['generated_utc'] + '.', '',
             '| Capability | Hermes command | Outcome | Understood | Adapter | Static checks | Runtime | Install-ready |',
             '|---|---|---|---|---|---|---|---|']
    yn = lambda b: 'yes' if b else 'no'
    for p in bundle['passports']:
        s = p['stages']
        lines.append('| `{}` | {} | **{}** | {} | {} | {} | {} | {} |'.format(
            p['capability_id'], _cmd_cell(p),
            p['outcome'], yn(s['source_functionality_understood']), yn(s['adapter_generated']),
            yn(s['static_checks_passed']), p['verification']['runtime_status'], yn(s['ready_for_installation'])))
    lines += ['', 'Outcome counts: ' + ', '.join(f'{k}={v}' for k, v in bundle['outcome_counts'].items()),
              '', 'Runtime-verified: **' + str(bundle['runtime_verified_count']) + '**. '
              'Ready for installation: **' + str(bundle['ready_for_installation_count']) + '**. '
              'Nothing was installed.', '']
    for p in bundle['passports']:
        lines += ['## ' + p['capability_id'], '',
                  '- Outcome: **' + p['outcome'] + '**',
                  '- Source: `' + p['source']['path'] + '` sha256 `' + p['source']['sha256'][:16] + '…` ('
                  + p['source']['revision_status'] + ')',
                  '- Target facts: `' + p['target']['facts_id'] + '`; installed Hermes version: `'
                  + str(p['target']['installed_hermes_version']) + '`',
                  '- Integration: ' + p['integration']['method'] + ', model calls: 0',
                  '- Dimensions: ' + ', '.join(f'{k}={v}' for k, v in p['semantic_contract']['dimensions'].items()),
                  '- Static checks: ' + str(p['verification']['static_checks_total']) + ' run, failed: '
                  + (', '.join(p['verification']['static_checks_failed']) or 'none'),
                  '- Runtime: ' + p['verification']['runtime_status'], '', 'Known limitations:', '']
        lines += ['- ' + x for x in p['known_limitations']] or ['- none recorded']
        lines.append('')
    return '\n'.join(lines) + '\n'


def write_bundle(directory: Path, bundle: dict) -> None:
    def dump(name, obj):
        (directory / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    dump('CAPABILITY_PASSPORT.json', {k: bundle[k] for k in bundle if k not in {'verification', 'snapshot'}})
    dump('VERIFICATION_RESULTS.json', {'schema': 'universal-port.verification-results/1',
                                       'results': bundle['verification']})
    dump('UNDERSTANDING_SNAPSHOT_V2.json', bundle['snapshot'])
    (directory / 'CAPABILITY_PASSPORT.md').write_text(render_markdown(bundle), encoding='utf-8')
