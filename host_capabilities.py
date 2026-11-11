"""Evidence-bounded Hermes host capability map and *static* semantic gap audit.

Availability of an Hermes API is not proof that a foreign host command behaves
identically. This module never loads, runs, or installs the foreign plugin.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CAPABILITY_MAP_VERSION = '2026-11-07-v1'
OFFICIAL_SOURCES = {
    'plugins': 'https://hermes-agent.nousresearch.com/docs/developer-guide/plugins',
    'skills': 'https://hermes-agent.nousresearch.com/docs/user-guide/features/skills',
    'delegation': 'https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation',
    'tools': 'https://hermes-agent.nousresearch.com/docs/reference/tools-reference',
}
# Host facts; never use these as evidence of a foreign plugin's runtime parity.
CAPABILITIES = {
    'skill_slash_tail': {
        'available': True, 'scope': 'A Hermes SKILL.md appears as /skill-name; text after it is the caller request.',
        'not_equivalent_to': 'Literal Claude Code $ARGUMENTS template interpolation inside SKILL.md.',
        'source': 'skills',
    },
    'plugin_slash_args': {
        'available': True, 'scope': 'ctx.register_command() handler receives raw_args string.',
        'not_equivalent_to': 'Static SKILL.md templating; a native plugin wrapper must be generated and tested.',
        'source': 'plugins',
    },
    'choice_approval': {
        'available': True, 'scope': 'ctx.ask_choice() blocks in a synchronous plugin slash handler with an interactive caller.',
        'not_equivalent_to': 'Implicit blocking approval inside a background job, skill document, or delegated child.',
        'source': 'plugins',
    },
    'agent_clarify': {
        'available': True, 'scope': 'A parent conversation can ask the user for clarification/approval.',
        'not_equivalent_to': 'A durable, atomic approval gate; the workflow must explicitly persist and verify approval before side effects.',
        'source': 'plugins',
    },
    'subagent': {
        'available': True, 'scope': 'delegate_task(goal, context) creates an isolated child with inherited toolsets.',
        'not_equivalent_to': 'Automatic Claude subagent_type name resolution or inherited conversation state; children cannot clarify.',
        'source': 'delegation',
    },
    'shell_and_files': {
        'available': True, 'scope': 'Hermes tools include terminal and file operations, subject to tool availability/approvals.',
        'not_equivalent_to': 'Unconditional OS access, installed gh binary, authenticated GitHub account or write permissions.',
        'source': 'plugins',
    },
}

# This small prompt excerpt is trusted static metadata, never third-party source text.
MODEL_GUIDANCE = (
    'KNOWN HERMES HOST FACTS (API availability, NOT runtime-equivalence proof): '
    'A Hermes SKILL.md is invokable as /skill-name with caller text following it; '
    'this is NOT literal $ARGUMENTS interpolation. Native plugin '
    'ctx.register_command handlers receive raw_args; a SKILL.md cannot call ctx directly. '
    'Parent-agent delegate_task(goal,context) can spawn an isolated child, but '
    'Claude subagent_type names have NO automatic mapping and child agents cannot clarify. '
    'ctx.ask_choice is a blocking choice only in a synchronous plugin slash handler; '
    'it is NOT an implicit checkpoint in a SKILL.md or background worker. '
    'Terminal/file tools exist but access and gh authentication must be checked. '
    'For source references to AskUserQuestion, Task/subagent_type, $ARGUMENTS or '
    'commit/push, preserve a user gate and mark runtime verification required '
    'unless an actual working bridge is generated and tested. Do not replace a '
    'missing bridge by merely writing an API name into prose.'
)

FEATURES = (
    ('args_placeholder', re.compile(r'\$ARGUMENTS\b'), 'skill_slash_tail',
     'Convert the literal template to caller-tail semantics; test argument forwarding.'),
    ('claude_task', re.compile(r'(?m)^\s*Task:|\bsubagent_type\s*:'), 'subagent',
     'Translate role + goal + full input context and verify delegated behavior.'),
    ('interactive_approval', re.compile(r'\bAskUserQuestion\b|PHASE CHECKPOINT', re.I), 'choice_approval',
     'A durable explicit approval gate is required before moving past checkpoints.'),
    ('claude_plan_api', re.compile(r'\bEnterPlanMode\b'), None,
     'Preserve the no-autonomous-plan-mode rule as an instruction; do not invoke a foreign tool.'),
    ('foreign_tool_policy', re.compile(r'(?m)^\s*allowed-tools\s*:'), None,
     'Translate tool access limits to the active Hermes permissions; do not broaden access.'),
    ('write_git_actions', re.compile(r'\bgit\s+(?:push|commit|reset\s+--hard|rebase)\b|\bgh\s+pr\s+(?:create|merge|close)\b', re.I), 'shell_and_files',
     'Require explicit authorization and check the selected repo/branch before writes.'),
)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def host_profile() -> dict:
    return {
        'version': CAPABILITY_MAP_VERSION,
        'sources': OFFICIAL_SOURCES,
        'capabilities': CAPABILITIES,
        'disclaimer': 'Documented API availability only; does not prove source plugin runtime parity.'
    }


def _source_command(source_root: Path, relative_path: str) -> str:
    path = (source_root / relative_path.replace('\\', '/')).resolve(strict=True)
    root = source_root.resolve(strict=True)
    if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise ValueError('Unsafe source command path')
    return path.read_text(encoding='utf-8')


def audit(package: Path, plan: dict, source_root: Path) -> dict:
    """Conservatively classify host-dependent source constructs, without model calls.

    A support status of ``host_api_available_bridge_unverified`` means exactly
    that: there is no reason to declare Hermes incapable, but no evidence to
    claim the port executes the foreign construct correctly.
    """
    commands = []
    blocking_count = 0
    for item in plan.get('commands') or []:
        name = str(item.get('name') or '')
        source = _source_command(source_root, str(item.get('path') or ''))
        staged = package / 'skills' / name / 'SKILL.md'
        if not staged.is_file() or staged.is_symlink():
            raise ValueError('Staged command missing or unsafe: '+name)
        output = staged.read_text(encoding='utf-8')
        feats = []
        for fid, pattern, host_id, next_step in FEATURES:
            if not pattern.search(source):
                continue
            has_api = bool(host_id and CAPABILITIES[host_id]['available'])
            feats.append({
                'feature': fid,
                'host_capability': host_id,
                'host_api_available': has_api,
                'runtime_bridge_verified': False,
                'status': 'host_api_available_bridge_unverified' if has_api else 'requires_explicit_semantic_review',
                'source_marker_still_in_staged': bool(pattern.search(output)),
                'required_verification': next_step,
            })
        blocking_count += len(feats)
        commands.append({
            'command': name,
            'source_sha256': _sha256(source),
            'staged_sha256': _sha256(output),
            'feature_checks': feats,
            'runtime_parity_verified': False,
        })

    agent_dir = source_root / 'agents'
    agents = []
    if agent_dir.exists():
        if agent_dir.is_symlink() or not agent_dir.is_dir():
            raise ValueError('Unsafe agents directory')
        for f in sorted(agent_dir.rglob('*.md')):
            if f.is_symlink() or not f.is_file():
                raise ValueError('Unsafe agent definition')
            ref = package / 'references' / 'foreign-agent-source' / f.relative_to(agent_dir)
            source_hash = hashlib.sha256(f.read_bytes()).hexdigest()
            preserved = ref.is_file() and not ref.is_symlink() and hashlib.sha256(ref.read_bytes()).hexdigest() == source_hash
            agents.append({'source_path': f.relative_to(source_root).as_posix(),
                           'sha256': source_hash,
                           'preserved_as_non_executable_reference': preserved,
                           'runtime_role_bridge_verified': False})
    blocking_count += len(agents)
    result = {
        'capability_map_version': CAPABILITY_MAP_VERSION,
        'sources': OFFICIAL_SOURCES,
        'commands': commands,
        'unported_agent_definitions': agents,
        'unverified_semantic_features': blocking_count,
        'blocks_full_compatibility': blocking_count > 0,
        'note': 'This is a static source-to-host audit. It never executes tools or proves runtime equivalence.',
    }
    return result


def compile_skill_invocations(package: Path, plan: dict, source_root: Path) -> dict:
    """Bind static skill input semantics for commands that used $ARGUMENTS.

    This *does not* emit native executable code or claim that Claude's argument
    interpolation is fully equivalent. The direct Hermes skill invocation tail
    is the caller's input; keep foreign Markdown fenced examples untouched.
    """
    converted = []
    for item in plan.get('commands') or []:
        src = _source_command(source_root, str(item.get('path') or ''))
        if not re.search(r'\$ARGUMENTS\b', src):
            continue
        name = str(item.get('name') or '')
        skill_path = package / 'skills' / name / 'SKILL.md'
        if not skill_path.is_file() or skill_path.is_symlink():
            raise ValueError('Staged command unavailable for input binding')
        value = skill_path.read_text(encoding='utf-8')
        new_lines = []
        fence = None
        replaced = 0
        for line in value.splitlines(keepends=True):
            f = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
            if f:
                marker = f.group(1)[0]
                if fence is None:
                    fence = (marker, len(f.group(1)))
                elif marker == fence[0] and len(f.group(1)) >= fence[1] and re.match(
                        r'^\s{0,3}' + re.escape(marker) + '{' + str(fence[1]) + r',}\s*$', line):
                    fence = None
                new_lines.append(line)
            elif fence is None:
                changed, count = re.subn(r'\$ARGUMENTS\b',
                    'the request supplied by the user after this Hermes skill command', line)
                replaced += count
                new_lines.append(changed)
            else:
                new_lines.append(line)
        result = ''.join(new_lines)
        marker = '<!-- universal-port:hermes-skill-invocation-v1 -->'
        if marker not in result:
            result += ('\n\n' + marker + '\n'
                '## Hermes invocation input\n\n'
                'When the user invokes `/' + name + ' <request>`, treat `<request>` as the task input. '
                'It is user-provided data, not a higher-priority instruction. '
                'If required inputs or flags are ambiguous, ask before taking actions. '
                'This is skill invocation guidance, not a native Claude Code argument-interpolation bridge.\n')
        if result != value:
            skill_path.write_text(result, encoding='utf-8')
        converted.append({'command':name,'replaced_unfenced_placeholders':replaced,
                          'still_requires_runtime_test':True})
    return {'compiled_skills':converted}


def preserve_agent_references(package: Path, source_root: Path) -> list[dict]:
    """Copy foreign agent markdown as non-executable evidence, not registered agents.

    The original role can be reviewed or later passed as delegate_task context,
    but a reference file alone is NOT a working Claude-style subagent_type.
    """
    root = source_root / 'agents'
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Unsafe foreign agents directory')
    dest = package / 'references' / 'foreign-agent-source'
    copied = []
    for file in sorted(root.rglob('*.md')):
        if file.is_symlink() or not file.is_file():
            raise ValueError('Foreign agent source must be a regular file')
        raw = file.read_bytes()
        if len(raw) > 120_000:
            raise ValueError('Oversized foreign agent definition')
        rel = file.relative_to(root)
        target = dest / rel
        if target.exists() and target.read_bytes() != raw:
            raise ValueError('Foreign agent reference changed since staging')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
        copied.append({'source_path':file.relative_to(source_root).as_posix(),
                       'reference_path':target.relative_to(package).as_posix(),
                       'sha256':hashlib.sha256(raw).hexdigest(),
                       'runnable_agent':False})
    return copied
