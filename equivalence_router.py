"""Fail-closed, cost-aware routing for *proven* same-semantics tool aliases.

This is not a semantic-equivalence oracle. The production registry intentionally
ships empty. Entries must be added by a maintainer following actual cross-host
contract tests; model-generated confidence or similarly named tools do not count.

The only implemented direct rewrite is the exact single-line ``Tool: NAME``
form outside Markdown fences. It does not rewrite prose, arbitrary code, or
Claude Task blocks. Everything else stays on the existing AI integration path.
"""
from __future__ import annotations

import hashlib
import json
import re
from importlib import metadata
from pathlib import Path
from typing import Any

from .host_capabilities import FEATURES, _source_command

REGISTRY_VERSION = 1
ROUTER_VERSION = '2026-11-07-v1'
DEFAULT_REGISTRY = Path(__file__).with_name('verified_mappings.json')
_TOKEN = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$')
_PROFILE = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
_PROOF_HASH = re.compile(r'^[0-9a-f]{64}$')
_TOOL_LINE = re.compile(r'^(\s{0,3}Tool:\s*)([A-Za-z][A-Za-z0-9_.-]{0,79})(\s*)$', re.I)
_FENCE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')
MAX_MAPPINGS = 128


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _unfenced_tool_lines(text: str):
    """Yield (line number, tool name) for exact labeled calls, outside fences."""
    open_char = None
    open_count = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        marker = _FENCE.match(line)
        if marker:
            chars = marker.group(1)
            if open_char is None:
                open_char, open_count = chars[0], len(chars)
            elif chars[0] == open_char and len(chars) >= open_count:
                open_char, open_count = None, 0
            continue
        if open_char is not None:
            continue
        m = _TOOL_LINE.fullmatch(line)
        if m:
            yield lineno, m.group(2)


def _validate_mapping(item: Any) -> dict:
    if not isinstance(item, dict) or set(item) != {
        'id', 'source_profile', 'source_tool', 'target_tool', 'syntax', 'semantics', 'evidence'
    }:
        raise ValueError('Malformed verified mapping fields')
    for key in ('id', 'source_tool', 'target_tool'):
        if not isinstance(item[key], str) or not _TOKEN.fullmatch(item[key]):
            raise ValueError('Unsafe mapping identifier')
    if not isinstance(item['source_profile'], str) or not _PROFILE.fullmatch(item['source_profile']):
        raise ValueError('Invalid mapping source profile')
    if item['syntax'] != 'exact_tool_label_line_v1':
        raise ValueError('Unsupported mapping syntax; executable transforms are forbidden')
    if item['source_tool'] == item['target_tool']:
        raise ValueError('Identity mapping is not a name bridge')
    expected_semantics = {'arguments', 'returns', 'side_effects', 'permissions', 'approval', 'failure', 'state'}
    if not isinstance(item['semantics'], dict) or set(item['semantics']) != expected_semantics:
        raise ValueError('Equivalence contract must cover all dimensions')
    # Exact equality is an attestable contract requirement, not a proof by itself.
    if any(not isinstance(v, str) or not v.strip() or len(v)>160
           for v in item['semantics'].values()):
        raise ValueError('Incomplete semantic contract')
    evidence = item['evidence']
    fields = {'source_version', 'target_version', 'source_commit_sha', 'source_command_sha256', 'source_contract_sha256',
              'target_contract_sha256', 'test_evidence_sha256', 'test_suite',
              'reviewed_by', 'result'}
    if not isinstance(evidence, dict) or set(evidence) != fields or evidence.get('result') != 'PASS':
        raise ValueError('A verified mapping requires a PASS test-evidence record')
    if not isinstance(evidence['source_commit_sha'], str) or not re.fullmatch(r'[0-9a-f]{40}', evidence['source_commit_sha']):
        raise ValueError('Missing immutable source commit')
    for k in ('source_command_sha256', 'source_contract_sha256', 'target_contract_sha256', 'test_evidence_sha256'):
        if not isinstance(evidence[k], str) or not _PROOF_HASH.fullmatch(evidence[k]):
            raise ValueError('Missing SHA-256 test/contract evidence')
    for k in ('source_version','target_version','test_suite','reviewed_by'):
        if not isinstance(evidence[k],str) or not (1 <= len(evidence[k].strip()) <= 180):
            raise ValueError('Missing source version, target version, test suite or reviewer')
    return item


def load_registry(path: Path | None = None) -> dict:
    """Load only declarative trusted entries. Production callers use the bundled path.

    A signed/trusted deployment and real contract evidence are operational
    prerequisites. User-provided plugin JSON must never be passed as a registry.
    The optional path exists for offline fixtures, not the Hermes slash surface.
    """
    path = Path(path) if path is not None else DEFAULT_REGISTRY
    if path.is_symlink() or not path.is_file():
        raise ValueError('Verified mapping registry absent or symbolic link')
    raw = path.read_bytes()
    if len(raw) > 128_000:
        raise ValueError('Registry too large')
    data = json.loads(raw)
    if not isinstance(data,dict) or set(data) != {'schema_version', 'mappings'} or data['schema_version'] != REGISTRY_VERSION:
        raise ValueError('Unrecognized verified mapping registry schema')
    mappings = data['mappings']
    if not isinstance(mappings,list) or len(mappings)>MAX_MAPPINGS:
        raise ValueError('Invalid registry mappings')
    seen_ids = set()
    seen_aliases = set()
    for entry in mappings:
        _validate_mapping(entry)
        key=(entry['source_profile'],entry['source_tool'])
        if key in seen_aliases or entry['id'] in seen_ids:
            raise ValueError('Conflicting or duplicate trusted mapping')
        seen_ids.add(entry['id']);seen_aliases.add(key)
    return {'schema_version':REGISTRY_VERSION, 'mappings':mappings,
            'sha256':hashlib.sha256(raw).hexdigest(),
            'mapping_count':len(mappings)}


def installed_hermes_version() -> str | None:
    """Read the locally installed distribution version; unknown is never a match."""
    try:
        return metadata.version('hermes-agent')
    except (metadata.PackageNotFoundError, ImportError, ValueError):
        return None


def _command_lanes(source: str, profile: str, registry: dict,
                   *, source_commit: str | None, host_version: str | None) -> dict:
    mapped_by_name = {m['source_tool']:m for m in registry['mappings']
                      if m['source_profile'] == profile
                      and m['evidence']['source_command_sha256'] == _sha(source)
                      and m['evidence']['source_commit_sha'] == source_commit
                      and m['evidence']['target_version'] == host_version}
    direct = []
    integration = []
    seen = set()
    for line, token in _unfenced_tool_lines(source):
        hit = mapped_by_name.get(token)
        if hit is None:
            integration.append({'feature':'unmapped_tool_call','line':line,'source_tool':token,
                                'reason':'No verified same-contract alias; AI integration required'})
        else:
            direct.append({'line':line,'source_tool':token,'target_tool':hit['target_tool'],
                           'mapping_id':hit['id'],
                           'test_evidence_sha256':hit['evidence']['test_evidence_sha256']})
        seen.add((line,token))
    for feature, pattern, host_id, _note in FEATURES:
        if pattern.search(source):
            integration.append({'feature':feature, 'host_capability':host_id,
                                'reason':'Host API existence alone cannot prove same-function behavior'})
    # A command with no recognizable host-specific constructs may still contain
    # implicit effects. Only a trusted exact-form mapping can skip AI entirely.
    if direct and not integration:
        lane = 'DIRECT_BRIDGE_ONLY'
    elif direct:
        lane = 'MIXED_DIRECT_AND_AI'
    else:
        lane = 'AI_INTEGRATION'
    return {'lane':lane,'direct':direct,'integration':integration,
            'direct_count':len(direct),'integration_count':len(integration)}


def classify(package: Path, plan: dict, source_root: Path, *, registry: dict | None = None,
             source_commit: str | None = None, host_version: str | None = None) -> dict:
    """Generate *advisory* per-command routing from fingerprint-pinned sources.

    This function never invokes a model, executes foreign code, promotes full
    compatibility or changes the staged package.
    """
    registry = registry if registry is not None else load_registry()
    if not isinstance(registry,dict) or 'mappings' not in registry or 'sha256' not in registry:
        raise ValueError('Validated registry required')
    host_version = host_version if host_version is not None else installed_hermes_version()
    entries = []
    for item in plan.get('commands') or []:
        name = str(item.get('name') or '')
        original = _source_command(source_root, str(item.get('path') or ''))
        staged = package/'skills'/name/'SKILL.md'
        if staged.is_symlink() or not staged.is_file():
            raise ValueError('Staged skill missing or symbolic link')
        c = _command_lanes(original, str(plan.get('profile') or ''),registry,
                           source_commit=source_commit, host_version=host_version)
        entries.append({'command':name,'source_sha256':_sha(original), **c})
    total_direct = sum(x['direct_count'] for x in entries)
    total_integration = sum(x['integration_count'] for x in entries)
    return {'router_version':ROUTER_VERSION,
            'registry_sha256':registry['sha256'],
            'target_hermes_version':host_version,
            'source_commit':source_commit,
            'verified_mapping_count':registry.get('mapping_count',len(registry['mappings'])),
            'direct_bridge_calls':total_direct,
            'requires_integration_checks':total_integration,
            'commands':entries,
            'unsupported_confirmed':0,
            'estimated_savings_usd':None,
            'semantic_parity_verified':False,
            'note':('Static cost-tier routing only. Direct=trusted exact-alias mapping; '
                    'all other constructs use AI integration. No cost or runtime parity claim. '
                    'Name aliases are bound to the exact source commit, command digest and Hermes version; '
                    'foreign source cannot create or promote mapping evidence.')}


def direct_rewrite(markdown: str, command_route: dict, *, trusted_registry: dict) -> tuple[str, list]:
    """Apply only trusted, exact, unfenced Tool: NAME alias lines.

    Fail closed if the source changed or a route references an untrusted entry.
    This is an explicitly narrow syntax conversion, not generic prose replacement.
    """
    mapping_keys={(m['id'],m['source_tool'],m['target_tool']) for m in trusted_registry['mappings']}
    directives = command_route.get('direct') or []
    if not directives: return markdown, []
    lines=markdown.splitlines(keepends=True)
    observed=[]
    open_char=None;open_count=0
    for lineno,line in enumerate(lines,1):
        marker=_FENCE.match(line)
        if marker:
            m=marker.group(1)
            if open_char is None:
                open_char,open_count=m[0],len(m)
            elif m[0] == open_char and len(m)>=open_count:
                open_char,open_count=None,0
            continue
        if open_char is not None:continue
        body=line.rstrip('\r\n');end=line[len(body):]
        m=_TOOL_LINE.fullmatch(body)
        if not m:continue
        matches=[d for d in directives if d['source_tool']==m.group(2) and
                 (d['mapping_id'],d['source_tool'],d['target_tool']) in mapping_keys]
        if matches:
            d=matches[0]
            lines[lineno-1]=m.group(1)+d['target_tool']+m.group(3)+end
            observed.append({'mapping_id':d['mapping_id'], 'source_tool':d['source_tool'],
                             'target_tool':d['target_tool']})
    if len(observed)!=len(directives):
        raise ValueError('Direct mapping anchor mismatch; adaptation blocked')
    return ''.join(lines),observed
