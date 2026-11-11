"""Static, evidence-bounded compatibility loss and update snapshots.

No foreign code, Hermes tool, model or Git command is executed here. This is
NOT a semantic equivalence certificate or DIAPORIA's private Change Journal.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .host_capabilities import _source_command

SCHEMA_VERSION = 1
IMPORTER_DOC = 'https://hermes-agent.nousresearch.com/marketplace/agent-importers'
SETTINGS_CANDIDATES = ('settings.json', '.claude/settings.json', '.claude-plugin/settings.json')
PERMISSION_KEYS = ('allow', 'ask', 'deny')
MAX_SETTINGS_SIZE = 200_000


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def permission_inventory(source_root: Path, plan: dict) -> list[dict]:
    """Inspect only explicit Claude JSON settings; never serialize policy values.

    A non-Bash permission is not silently discarded or treated as a safe Bash
    equivalent. Even Bash rules require a separate target-policy equivalence test.
    """
    if plan.get('profile') != 'claude-code':
        return []
    output = []
    for rel in SETTINGS_CANDIDATES:
        path = source_root / rel
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source_root.resolve()):
            raise ValueError('Unsafe Claude settings file')
        if path.stat().st_size > MAX_SETTINGS_SIZE:
            raise ValueError('Oversized Claude settings file')
        raw = path.read_bytes()
        try:
            obj = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid Claude settings JSON') from exc
        if not isinstance(obj, dict):
            raise ValueError('Claude settings must be a JSON object')
        perms = obj.get('permissions', {})
        if perms is None:
            perms = {}
        if not isinstance(perms, dict):
            raise ValueError('Invalid Claude permission object')
        counts = {}
        for policy in PERMISSION_KEYS:
            rules = perms.get(policy, [])
            if not isinstance(rules, list) or not all(isinstance(x, str) for x in rules):
                raise ValueError('Invalid Claude permission rule list')
            counts[policy] = {
                'bash': sum(rule.startswith('Bash(') and rule.endswith(')') for rule in rules),
                'non_bash_or_ambiguous': sum(not (rule.startswith('Bash(') and rule.endswith(')')) for rule in rules),
            }
        extra = [key for key in perms if key not in PERMISSION_KEYS]
        known_extra = {'defaultMode', 'additionalDirectories', 'disableBypassPermissionsMode'}
        extra_types = sorted(key for key in extra if key in known_extra)
        unknown_extra_count = len(extra) - len(extra_types)
        has_policies = any(sum(n.values()) for n in counts.values()) or bool(extra)
        output.append({
            'source_path': rel, 'source_sha256': _sha(raw),
            'permission_rule_counts': counts,
            'additional_policy_types': extra_types,
            'other_policy_key_count': unknown_extra_count,
            'status': 'REQUIRES_PERMISSION_SEMANTIC_REVIEW' if has_policies else 'NO_PERMISSION_RULES',
            'runtime_equivalence_verified': False,
        })
    return output


def loss_report(plan: dict, source_root: Path, package: Path,
                cost_route: dict | None, audit: dict | None) -> dict:
    """Describe capability gaps without guessing which repairs actually work."""
    route_by_name = {x['command']: x for x in (cost_route or {}).get('commands', [])}
    audit_by_name = {x['command']: x for x in (audit or {}).get('commands', [])}
    permissions = permission_inventory(source_root, plan)
    commands = []
    for item in plan.get('commands') or []:
        name = str(item['name'])
        source_text = _source_command(source_root, str(item['path']))
        target = package / 'skills' / name / 'SKILL.md'
        if target.is_symlink() or not target.is_file():
            raise ValueError('Expected staged command missing')
        route = route_by_name.get(name, {})
        checks = audit_by_name.get(name, {}).get('feature_checks', [])
        reasons = ['A staged Hermes skill does not itself prove original slash-command behavior']
        if checks:
            reasons.extend('Source construct requires verification: ' + x['feature'] for x in checks)
        if route.get('lane') == 'DIRECT_BRIDGE_ONLY':
            reasons.append('A function-name alias cannot certify entire workflow equivalence')
        commands.append({
            'name': name,
            'source_sha256': _sha(source_text.encode('utf-8')),
            'staged_sha256': _sha(target.read_bytes()),
            'route': route.get('lane', 'NOT_ROUTED'),
            'status': 'STAGED_BUT_RUNTIME_UNVERIFIED',
            'feature_gaps': [x['feature'] for x in checks],
            'reasons': reasons,
        })
    issues = sorted(str(x)[:200] for x in (plan.get('issues') or []))
    agents = [x['source_path'] for x in (audit or {}).get('unported_agent_definitions', [])]
    # This field names official, documented coverage gaps rather than claiming
    # the Hermes importer itself was executed in this run.
    official = []
    if plan.get('profile') == 'claude-code' and commands:
        official.append({
            'gap_id': 'claude_code_commands_skipped_by_official_importer',
            'source_count': len(commands),
            'our_status': 'STAGED_FOR_REVIEW_NOT_RUNTIME_VERIFIED',
            'source_documentation': IMPORTER_DOC,
        })
    unported = sorted(set(issues + [f'foreign_agent:{x}' for x in agents]))
    has_policy = any(x['status'] == 'REQUIRES_PERMISSION_SEMANTIC_REVIEW' for x in permissions)
    return {
        'schema_version': SCHEMA_VERSION, 'report_type': 'CAPABILITY_LOSS',
        'source_profile': plan.get('profile'), 'source_fingerprint_sha256': plan.get('fingerprint_sha256'),
        'commands': commands, 'permission_sources': permissions,
        'unported_host_features': unported,
        'official_importer_gaps': official,
        'blocks_full_compatibility': bool(commands or has_policy or unported or (audit or {}).get('blocks_full_compatibility')),
        'runtime_parity_verified': False,
        'note': ('Static comparison and official documentation only. No official importer baseline was run; '
                 'no model, foreign code, Hermes runtime or target approval policy was tested.'),
    }


def understanding_snapshot(plan: dict, source_commit: str, target_version: str | None,
                           repo_url: str, mapping_sha: str, loss: dict) -> dict:
    """Minimal fingerprint-only record to avoid rediscovering unchanged scope.

    Records neither untrusted source content nor model reasoning or private
    DIAPORIA journals. Same hash != a verified target behavior.
    """
    if not isinstance(source_commit, str) or len(source_commit) != 40 or any(x not in '0123456789abcdef' for x in source_commit):
        raise ValueError('Source must be pinned to an immutable lower-case SHA-1 commit')
    return {
        'schema_version': SCHEMA_VERSION,
        'type': 'STATIC_UNDERSTANDING_SNAPSHOT',
        'source': {'repo_url': repo_url, 'commit': source_commit,
                   'profile': plan.get('profile'), 'name': plan.get('name'),
                   'fingerprint_sha256': plan.get('fingerprint_sha256')},
        'target': {'hermes_version': target_version, 'mapping_registry_sha256': mapping_sha},
        'commands': [{k: x[k] for k in ('name', 'source_sha256', 'staged_sha256', 'route', 'status', 'feature_gaps')}
                     for x in loss['commands']],
        'permission_sources': [{'source_path': x['source_path'], 'source_sha256': x['source_sha256'],
                                'status': x['status']} for x in loss['permission_sources']],
        'unported_host_features': loss['unported_host_features'],
        'runtime_parity_verified': False,
        'note': 'Fingerprints support change localization only; target parity must be reverified.',
    }


def compare_snapshots(before: dict, after: dict) -> dict:
    """Untrusted old snapshots cannot promote a new run to equivalent/safe."""
    if before.get('schema_version') != SCHEMA_VERSION or after.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported understanding snapshot')
    if before.get('type') != 'STATIC_UNDERSTANDING_SNAPSHOT' or after.get('type') != 'STATIC_UNDERSTANDING_SNAPSHOT':
        raise ValueError('Incorrect snapshot type')
    a, b = before['source'], after['source']
    if a['repo_url'].split('/tree/')[0].rstrip('/') != b['repo_url'].split('/tree/')[0].rstrip('/') or a['profile'] != b['profile']:
        raise ValueError('Snapshots must belong to the same source repository and platform')
    old = {x['name']:x for x in before['commands']}
    new = {x['name']:x for x in after['commands']}
    changed = sorted(n for n in old.keys() & new.keys() if old[n]['source_sha256'] != new[n]['source_sha256'])
    adapter_changed = sorted(n for n in old.keys() & new.keys() if old[n]['staged_sha256'] != new[n]['staged_sha256'])
    added = sorted(new.keys()-old.keys())
    removed = sorted(old.keys()-new.keys())
    perm_old = {x['source_path']:x['source_sha256'] for x in before['permission_sources']}
    perm_new = {x['source_path']:x['source_sha256'] for x in after['permission_sources']}
    permission_changed = perm_old != perm_new
    host_changed = before['target'] != after['target']
    feature_changed = before['unported_host_features'] != after['unported_host_features']
    other_source_changed = a['fingerprint_sha256'] != b['fingerprint_sha256']
    commit_changed = a['commit'] != b['commit']
    need_review = bool(commit_changed or changed or added or removed or permission_changed or host_changed or feature_changed or other_source_changed or adapter_changed)
    return {
        'schema_version': SCHEMA_VERSION,
        'status': 'REVIEW_REQUIRED' if need_review else 'SOURCE_AND_ADAPTER_UNCHANGED_STATIC_ONLY',
        'changed_commands': changed, 'added_commands': added, 'removed_commands': removed,
        'changed_staged_adapters': adapter_changed,
        'permission_review_required': permission_changed,
        'target_revalidation_required': host_changed,
        'source_commit_changed': commit_changed,
        'other_source_changes_detected': other_source_changed,
        'host_feature_changes_detected': feature_changed,
        'runtime_parity_verified': False,
        'note': 'All commands in a new run need explicit runtime verification before claiming equivalence.',
    }
