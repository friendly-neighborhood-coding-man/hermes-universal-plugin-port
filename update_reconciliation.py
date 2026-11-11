"""Phase 4: update-aware reconciliation against an Understanding Snapshot v2.

Given the snapshot of a previous repair and a NEW source revision, decide —
without model calls and before re-running the full pipeline — which
capabilities were added, modified or removed, which adapters are affected,
and which verification evidence is no longer valid. Every decision carries
explicit reasons. Unchanged source never implies unchanged runtime behavior:
runtime evidence stays valid only while source, engine, target facts AND the
installed Hermes version are all identical to what the evidence was bound to.
v0.4.1: even then, a snapshot's runtime PASS is self-reported, so it is never
carried forward as ADAPTED_RUNTIME_VERIFIED and runtime re-verification is
always required.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from . import claude_command as CC
from .capability_passport import SNAPSHOT_SCHEMA, engine_identity, non_command_fingerprint
from .hermes_target import target_profile
from .port_core import PortError, analyze, safe_child
from .slash_repair import command_name

IMPACT_SCHEMA = 'universal-port.update-impact/1'


def _command_digest(root: Path, rel: str) -> dict:
    path = safe_child(root, rel)
    if path.is_symlink() or not path.is_file():
        raise PortError('Unsafe command source: ' + rel)
    raw = path.read_bytes()
    out = {'source_sha256': hashlib.sha256(raw).hexdigest(), 'body_sha256': None, 'parse_ok': True}
    try:
        _meta, body, _ = CC.parse_frontmatter(raw.decode('utf-8'))
        out['body_sha256'] = CC.sha256_text(body)
    except (UnicodeDecodeError, CC.CommandFormatError):
        out['parse_ok'] = False
    return out


def reconcile(old_snapshot: dict, new_source: str, *, new_source_commit: str | None = None,
              installed_hermes_version: str | None = None) -> dict:
    if not isinstance(old_snapshot, dict) or old_snapshot.get('schema') != SNAPSHOT_SCHEMA:
        raise PortError('Previous Understanding Snapshot v2 required')
    plan = analyze(new_source)
    if plan['profile'] != 'claude-code':
        raise PortError('Reconciliation currently supports Claude Code command capabilities only')
    old_src = old_snapshot['source']
    if old_src.get('plugin') != plan['name']:
        raise PortError('New source is a different plugin (' + plan['name'] + ' vs ' + str(old_src.get('plugin')) + ')')
    root = Path(plan['source'])
    new_target = target_profile(installed_hermes_version)
    new_engine = engine_identity()
    old_target = old_snapshot['target']
    old_engine = old_snapshot['engine']
    engine_changed = sorted(k for k in new_engine if old_engine.get(k) != new_engine[k])
    facts_changed = old_target.get('facts_sha256') != new_target['facts_sha256']
    old_ver, new_ver = old_target.get('installed_hermes_version'), installed_hermes_version
    version_changed = old_ver != new_ver
    version_unknown = new_ver is None
    commit_changed = old_src.get('commit') != new_source_commit
    tree_changed = old_src.get('tree_fingerprint_sha256') != plan['fingerprint_sha256']

    old_caps = {c['capability_id']: c for c in old_snapshot['capabilities']}
    new_caps = {}
    for item in plan['commands']:
        name = command_name(item['path'])
        cid = 'claude-code:' + plan['name'] + ':command:' + name
        new_caps[cid] = {'source_path': Path(item['path']).as_posix(), **_command_digest(root, item['path'])}

    # Settings/agents/hooks may change behavior of otherwise identical commands.
    # A snapshot without this field is treated as changed (conservative).
    non_command_change = old_src.get('non_command_fingerprint_sha256') != non_command_fingerprint(plan)

    rows = []
    for cid in sorted(set(old_caps) | set(new_caps)):
        old, new = old_caps.get(cid), new_caps.get(cid)
        reasons = []
        row = {'capability_id': cid, 'previous_outcome': old['outcome'] if old else None,
               'previous_runtime_status': old['runtime_status'] if old else None}
        if old and not new:
            row.update(change='REMOVED', affected_adapter=old.get('hermes_command'),
                       requires_reanalysis=False, requires_static_reverification=False,
                       requires_runtime_reverification=False, carried_outcome=None,
                       runtime_evidence='INVALIDATED' if old['runtime_status'] == 'PASS' else 'NONE')
            reasons.append('Command no longer exists upstream: its Hermes adapter command must be removed; '
                           'the old passport is retired, not carried forward')
        elif new and not old:
            row.update(change='ADDED', affected_adapter=None, requires_reanalysis=True,
                       requires_static_reverification=True, requires_runtime_reverification=True,
                       carried_outcome=None, runtime_evidence='NONE')
            reasons.append('New command: no prior understanding or evidence exists')
        else:
            if old['source_sha256'] != new['source_sha256']:
                body_same = old.get('body_sha256') is not None and old.get('body_sha256') == new['body_sha256']
                row['change'] = 'MODIFIED_FRONTMATTER_ONLY' if body_same else 'MODIFIED'
                reasons.append('Source command bytes changed (sha256 ' + old['source_sha256'][:12] + ' -> '
                               + new['source_sha256'][:12] + ')')
                if body_same:
                    reasons.append('Body identical; frontmatter changed: permissions/invocation metadata must be re-analyzed')
                reanalyze = True
            else:
                row['change'] = 'UNCHANGED'
                reanalyze = False
                reasons.append('Source command bytes identical; previous static understanding is reusable')
                if commit_changed:
                    reasons.append('Upstream revision changed (' + str(old_src.get('commit')) + ' -> '
                                   + str(new_source_commit) + ') but this command file is byte-identical')
            static = reanalyze or bool(engine_changed) or facts_changed or non_command_change
            if engine_changed:
                reasons.append('Repair engine identity changed (' + ', '.join(engine_changed) + '): adapters must be '
                               're-generated and statically re-verified')
            if facts_changed:
                reasons.append('Pinned Hermes target facts changed: static classification must be recomputed')
            if non_command_change:
                reasons.append('Non-command plugin files changed (settings/agents/hooks): '
                               'static re-verification required (permissions may differ)')
            runtime_invalid = []
            if reanalyze:
                runtime_invalid.append('source changed')
            if engine_changed:
                runtime_invalid.append('engine changed')
            if facts_changed:
                runtime_invalid.append('target facts changed')
            if version_changed:
                runtime_invalid.append('installed Hermes version changed (' + str(old_ver) + ' -> ' + str(new_ver) + ')')
            if version_unknown:
                runtime_invalid.append('installed Hermes version unknown')
            had_runtime = old['runtime_status'] == 'PASS'
            if had_runtime and runtime_invalid:
                row['runtime_evidence'] = 'INVALIDATED'
                reasons.append('Runtime evidence invalidated: ' + ', '.join(runtime_invalid))
            elif had_runtime:
                # v0.4.1: a snapshot is self-written JSON, so a recorded PASS is a claim, not proof.
                row['runtime_evidence'] = 'STILL_BOUND_UNTRUSTED_SNAPSHOT'
                reasons.append('Snapshot claims runtime PASS bound to identical source, engine, facts and Hermes '
                               'version; snapshots are untrusted, so runtime must be re-verified by a trusted collector')
            else:
                row['runtime_evidence'] = 'NONE'
                reasons.append('No runtime evidence existed before; runtime verification still required')
            row.update(
                affected_adapter=old.get('hermes_command') if (static or reanalyze) else None,
                requires_reanalysis=reanalyze,
                requires_static_reverification=static,
                requires_runtime_reverification=True,
                carried_outcome=None if static else old['outcome'],
            )
            # v0.4.1: never carry a runtime-verified outcome forward from a snapshot.
            if row['carried_outcome'] in {'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'}:
                row['carried_outcome'] = 'ADAPTED_STATICALLY'
        row['reasons'] = reasons
        rows.append(row)

    summary = {}
    for r in rows:
        summary[r['change']] = summary.get(r['change'], 0) + 1
    return {
        'schema': IMPACT_SCHEMA,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'source': {'plugin': plan['name'], 'old_commit': old_src.get('commit'), 'new_commit': new_source_commit,
                   'commit_changed': commit_changed, 'tree_changed': tree_changed,
                   'old_tree_fingerprint': old_src.get('tree_fingerprint_sha256'),
                   'new_tree_fingerprint': plan['fingerprint_sha256']},
        'target': {'old_installed_hermes_version': old_ver, 'new_installed_hermes_version': new_ver,
                   'version_changed': version_changed, 'facts_changed': facts_changed},
        'engine': {'changed_fields': engine_changed},
        'summary': dict(sorted(summary.items())),
        'requires_reanalysis': [r['capability_id'] for r in rows if r['requires_reanalysis']],
        'requires_static_reverification': [r['capability_id'] for r in rows if r['requires_static_reverification']],
        'requires_runtime_reverification': [r['capability_id'] for r in rows if r['requires_runtime_reverification']],
        'reusable_without_reanalysis': [r['capability_id'] for r in rows
                                        if r['change'] == 'UNCHANGED' and not r['requires_static_reverification']],
        'runtime_verified_after_update': [],
        'runtime_claims_still_bound_untrusted': [r['capability_id'] for r in rows
                                                 if r.get('runtime_evidence') == 'STILL_BOUND_UNTRUSTED_SNAPSHOT'],
        'capabilities': rows,
        'model_calls': 0,
        'note': ('Static impact analysis. Re-run the repair pipeline on the new revision for every capability listed '
                 'under requires_static_reverification; no capability is verified by this report.'),
    }
