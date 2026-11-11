"""Phase 1: evidence-driven repair of Claude Code slash commands for Hermes.

Pipeline per command (no model call, no foreign code execution, no install):

  understand  -> parse the ORIGINAL command file (frontmatter, placeholders,
                 shell injections, tool/approval/side-effect markers, unknowns)
  route       -> 1. verified direct equivalence (trusted registry + runtime
                    evidence; registry ships EMPTY, so normally unavailable)
                 2. deterministic native adapter (this module)
                 3. explicit UNSUPPORTED / BLOCKED_UNSAFE
  adapt       -> generate ONE native Hermes plugin that registers /<command>
                 and renders the original body (byte-identical copy) with
                 documented Claude `$ARGUMENTS` semantics, then queues it via
                 ctx.inject_message. Fixed template, never model-generated.
  verify      -> semantic_verification.verify_command (8 dimensions, static)
  record      -> capability_passport + understanding snapshot v2

Outcomes: DIRECT_EQUIVALENT_VERIFIED, ADAPTED_STATICALLY,
ADAPTED_RUNTIME_VERIFIED, PARTIAL_REVIEW_REQUIRED, UNSUPPORTED, BLOCKED_UNSAFE.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from . import claude_command as CC
from .hermes_target import BUILTIN_COMMANDS, TARGET_FACTS_ID, facts_sha256, target_profile
from .port_core import PortError, analyze, safe_child

REPAIR_ENGINE_VERSION = '0.4.3'
ADAPTER_SCHEMA = 'universal-port.command-adapter/1'
OUTCOMES = ('DIRECT_EQUIVALENT_VERIFIED', 'ADAPTED_STATICALLY', 'ADAPTED_RUNTIME_VERIFIED',
            'PARTIAL_REVIEW_REQUIRED', 'UNSUPPORTED', 'BLOCKED_UNSAFE')
_HERE = Path(__file__).resolve().parent
_CMD_NAME = re.compile(r'^[a-z][a-z0-9-]{0,47}$')
_RESERVED = {'universal-port'}

# Distinctive Claude Code tool names (common English words like Read/Edit are
# deliberately excluded from body scanning to avoid false positives).
CLAUDE_TOOL_MARKERS = re.compile(
    r'\b(AskUserQuestion|TodoWrite|WebFetch|WebSearch|NotebookEdit|EnterPlanMode|ExitPlanMode|'
    r'SlashCommand|MultiEdit|subagent_type)\b')
TASK_BLOCK = re.compile(r'(?m)^\s*Task:')
APPROVAL_MARKERS = re.compile(
    r'\bAskUserQuestion\b|PHASE CHECKPOINT|\bCHECKPOINT\b|wait for (?:the )?user|'
    r'(?:explicit|user) (?:approval|confirmation)|do not proceed (?:until|without)', re.I)
SIDE_EFFECT_MARKERS = (
    ('git_write', re.compile(r'\bgit\s+(?:push|commit|reset\s+--hard|rebase|merge|tag)\b', re.I)),
    ('github_write', re.compile(r'\bgh\s+(?:pr|issue|release)\s+(?:create|merge|close|edit|comment)\b', re.I)),
    ('destructive_fs', re.compile(r'\brm\s+-[a-z]*r[a-z]*f?\b|\bRemove-Item\b.*-Recurse', re.I)),
    ('network_fetch', re.compile(r'\b(?:curl|wget|Invoke-WebRequest)\b', re.I)),
    # v0.4.1: natural-language paraphrases. Heuristic only: a match makes the
    # dimension UNKNOWN; NO match never proves absence (see semantic_verification).
    ('nl_destructive', re.compile(r'\b(?:delete|deleting|remove|removing|erase|wipe|destroy|purge|truncate|'
                                  r'overwrite|drop|uninstall|kill|terminate|format|shred|reset|nuke|'
                                  r'get rid of|clear out|clean out|blow away|rm\s+-\w+)\b', re.I)),
    ('nl_publish_or_transfer', re.compile(r'\b(?:deploy|publish|push|upload|send|e-?mail|post|tweet|merge|'
                                          r'transfer|pay|purchase|buy|charge|revoke|rotate|sudo|chmod|chown)\b', re.I)),
)
NL_APPROVAL_BYPASS = re.compile(r'without (?:asking|confirm\w*|approval|permission|prompting|checking)|'
                                r'(?:do not|don\'t|never) (?:ask|confirm|prompt)|no confirmation|skip (?:the )?'
                                r'(?:confirmation|approval)|immediately|automatically', re.I)
CLAUDE_VARIABLES = re.compile(r'\$\{(CLAUDE_[A-Z_]+)\}')
FILE_REFERENCE = re.compile(r'(?:(?<=\s)|^)@(?:[A-Za-z0-9_.~-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8}\b', re.M)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def command_name(rel_path: str) -> str:
    return re.sub(r'[^a-z0-9-]+', '-', Path(rel_path).stem.lower()).strip('-') or 'command'


def _tool_list(value) -> list[str]:
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    # Space- or comma-separated; `Bash(git add *)` keeps its inner spaces.
    out, depth, cur = [], 0, ''
    for ch in str(value):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if depth == 0 and (ch.isspace() or ch == ','):
            if cur.strip():
                out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def understand_command(source_root: Path, rel_path: str, plugin_name: str) -> dict:
    """Static understanding of one original command. Unknowns stay unknown."""
    path = safe_child(source_root, rel_path)
    if path.is_symlink() or not path.is_file():
        raise PortError('Unsafe command source: ' + rel_path)
    raw = path.read_bytes()
    name = command_name(rel_path)
    base = {
        'capability_id': 'claude-code:' + plugin_name + ':command:' + name,
        'source_name': name,
        'source_path': Path(rel_path).as_posix(),
        'source_sha256': _sha(raw),
        'source_bytes': len(raw),
    }
    try:
        text = raw.decode('utf-8')
        meta, body, unparsed = CC.parse_frontmatter(text)
        names = CC.declared_argument_names(meta)
    except (UnicodeDecodeError, CC.CommandFormatError) as exc:
        return {**base, 'parse': {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)[:160]}}
    unknown_keys = sorted(k for k in meta if k not in CC.KNOWN_FRONTMATTER)
    allowed = _tool_list(meta.get('allowed-tools'))
    disallowed = _tool_list(meta.get('disallowed-tools'))
    shells = CC.find_shell_injections(body)
    return {
        **base,
        'parse': {'ok': True, 'frontmatter_keys': sorted(meta), 'unparsed_keys': sorted(unparsed),
                  'unknown_keys': unknown_keys},
        'body_sha256': CC.sha256_text(body),
        'invocation': {
            'description': str(meta.get('description') or '')[:300],
            'argument_hint': str(meta.get('argument-hint') or '')[:200],
            'argument_names': names,
            'disable_model_invocation': meta.get('disable-model-invocation') is True,
            'user_invocable': meta.get('user-invocable', True) is not False,
            'context': meta.get('context'), 'agent': meta.get('agent'),
            'model': meta.get('model'), 'effort': meta.get('effort'),
            'has_hooks': 'hooks' in meta,
        },
        'arguments': {**CC.scan_placeholders(body, names),
                      'likely_unintended': CC.likely_unintended_placeholders(body)},
        'shell_injections': shells,
        'permissions': {
            'allowed_tools_count': len(allowed),
            'allowed_tools_sha256': _sha(json.dumps(allowed).encode()) if allowed else None,
            'allowed_bash_rules': sum(t.startswith('Bash(') for t in allowed),
            'disallowed_tools_count': len(disallowed),
            'disallowed_tools_sha256': _sha(json.dumps(disallowed).encode()) if disallowed else None,
        },
        'claude_variables': sorted(set(CLAUDE_VARIABLES.findall(body))),
        'file_references': len(FILE_REFERENCE.findall(body)),
        'tool_references': sorted(set(CLAUDE_TOOL_MARKERS.findall(body))) + (['Task:'] if TASK_BLOCK.search(body) else []),
        'approval_markers': len(APPROVAL_MARKERS.findall(body)),
        'approval_bypass_markers': len(NL_APPROVAL_BYPASS.findall(body)),
        'side_effect_markers': [k for k, rx in SIDE_EFFECT_MARKERS if rx.search(body)],
    }


def hermes_command_name(source_name: str, plugin_name: str, taken: set[str]) -> tuple[str, list[str]]:
    """Pick a Hermes command name; never collide with built-ins or each other."""
    notes = []
    candidate = source_name
    if candidate in BUILTIN_COMMANDS or candidate in _RESERVED or candidate in taken:
        notes.append('/' + source_name + ' collides with a Hermes built-in or another command; renamed')
        candidate = (plugin_name + '-' + source_name)[:48].strip('-')
    if not _CMD_NAME.fullmatch(candidate) or candidate in BUILTIN_COMMANDS or candidate in taken:
        raise PortError('Cannot derive a safe, unique Hermes command name for ' + source_name)
    taken.add(candidate)
    return candidate, notes


def _package_files_sha256(package: Path) -> str:
    h = hashlib.sha256()
    # Must match generated_command_entry.package_sha256 (same order on Windows and POSIX).
    for f in sorted(package.rglob('*'), key=lambda x: x.relative_to(package).as_posix()):
        if f.is_symlink():
            raise PortError('Symlink inside adapter package')
        # v0.4.3 (review P0): no exclusions. A __pycache__ or any other extra file changes
        # the digest; the pre-import gate (pre_import_gate.py) rejects such trees outright.
        if f.is_file():
            h.update(f.relative_to(package).as_posix().encode() + b'\0' + hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def renderer_sha256() -> str:
    return _sha((_HERE / 'claude_command.py').read_bytes())


def entry_template_sha256() -> str:
    return _sha((_HERE / 'generated_command_entry.py').read_bytes())


def write_adapter_package(dest: Path, plugin_name: str, entries: list[dict], source_root: Path) -> Path:
    """Write the native adapter: fixed entry template + renderer + ORIGINAL bytes."""
    product = ('repaired-' + plugin_name)[:60].strip('-')
    pkg = dest / product
    if pkg.exists():
        raise PortError('Refusing to overwrite existing adapter package: ' + str(pkg))
    (pkg / 'commands').mkdir(parents=True)
    shutil.copyfile(_HERE / 'claude_command.py', pkg / 'claude_command.py')
    shutil.copyfile(_HERE / 'generated_command_entry.py', pkg / '__init__.py')
    for e in entries:
        src = safe_child(source_root, e['source_path'])
        target = pkg / 'commands' / e['file']
        if target.exists():
            raise PortError('Duplicate command file name in adapter: ' + e['file'])
        shutil.copyfile(src, target)  # byte-for-byte reuse of the original command
        if _sha(target.read_bytes()) != e['source_sha256']:
            raise PortError('Source changed while building adapter: ' + e['source_path'])
    # write_bytes, not write_text: LF on every OS so the adapter digest is platform-independent.
    (pkg / 'plugin.yaml').write_bytes((
        'name: ' + product + '\nversion: 0.1.0\n'
        'description: Hermes native slash-command adapter for Claude Code commands from ' + plugin_name
        + ' (generated by universal-plugin-port 0.4.3; registers nothing until an operator approval exists; review the Capability Passport first).\n').encode('utf-8'))
    return pkg


def write_manifest(pkg: Path, plugin_name: str, entries: list[dict]) -> None:
    manifest = {
        'schema': ADAPTER_SCHEMA,
        'generator': 'universal-plugin-port ' + REPAIR_ENGINE_VERSION,
        'source_plugin': plugin_name,
        'renderer_sha256': _sha((pkg / 'claude_command.py').read_bytes()),
        'entry_template_sha256': _sha((pkg / '__init__.py').read_bytes()),
        'claude_semantics': {'version': CC.SEMANTICS_VERSION, 'source': CC.SEMANTICS_SOURCE,
                             'source_sha256': CC.SEMANTICS_SOURCE_SHA256},
        'target_facts': TARGET_FACTS_ID,
        'commands': [{k: e[k] for k in ('source_name', 'hermes_command', 'file', 'source_sha256',
                                        'argument_names', 'description', 'args_hint', 'outcome')}
                     for e in entries],
    }
    (pkg / 'ADAPTER_MANIFEST.json').write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))


def defuse_staged_skill_shell(package: Path) -> list[dict]:
    """Security repair for staged SKILL.md fallbacks (v0.3.5 copied them verbatim).

    Hermes' optional skills.inline_shell runs every !`cmd` anywhere in SKILL.md,
    with the skill dir as CWD. Claude semantics differ (session CWD, abort on
    failure, permission-checked), so a staged copy must never auto-execute.
    """
    changed = []
    skills = package / 'skills'
    if not skills.is_dir():
        return changed
    for f in sorted(skills.rglob('SKILL.md')):
        if f.is_symlink():
            raise PortError('Symlinked SKILL.md in staged package')
        text = f.read_text(encoding='utf-8')
        if not CC.HERMES_INLINE_SHELL.search(text):
            continue
        meta_end = 0
        if text.startswith('---\n'):
            close = text.find('\n---\n', 4)
            meta_end = close + 5 if close >= 0 else 0
        new = text[:meta_end] + CC.disable_shell_injections(text[meta_end:])
        if new != text:
            f.write_text(new, encoding='utf-8')
            changed.append({'path': f.relative_to(package).as_posix(),
                            'before_sha256': CC.sha256_text(text), 'after_sha256': CC.sha256_text(new)})
    return changed


def repair_plugin(source: str, output_root: str, *, installed_hermes_version: str | None = None,
                  source_commit: str | None = None, runtime_evidence: list[dict] | None = None,
                  registry: dict | None = None) -> dict:
    """Run understand -> adapt -> verify -> passport for every command of a Claude plugin.

    Writes into a NEW directory under output_root and never installs or enables
    anything. Returns the in-memory bundle (also written as JSON/MD files).
    """
    from . import semantic_verification as SV
    from . import capability_passport as CP
    plan = analyze(source)
    if plan['profile'] != 'claude-code':
        raise PortError('Slash-command repair currently supports Claude Code plugins only')
    if plan['blockers']:
        raise PortError('Static blockers: ' + '; '.join(plan['blockers']))
    root = Path(plan['source'])
    dest_root = Path(output_root).expanduser().resolve()
    if dest_root == root or dest_root.is_relative_to(root) or root.is_relative_to(dest_root):
        raise PortError('Output must be outside the source tree and vice versa')
    dest_root.mkdir(parents=True, exist_ok=True)
    final = dest_root / ('repair-' + plan['name'])
    if final.exists():
        raise PortError('Refusing to overwrite existing repair output: ' + str(final))
    taken: set[str] = set()
    understood, entries = [], []
    for item in plan['commands']:
        u = understand_command(root, item['path'], plan['name'])
        understood.append(u)
    with tempfile.TemporaryDirectory(prefix='.repair-', dir=dest_root) as tmp:
        work = Path(tmp) / final.name
        work.mkdir()
        for u in understood:
            if u['parse']['ok']:
                hermes_name, notes = hermes_command_name(u['source_name'], plan['name'], taken)
            else:
                hermes_name, notes = None, []
            u['hermes_command'] = hermes_name
            u['naming_notes'] = notes
            entries.append({
                'source_name': u['source_name'], 'hermes_command': hermes_name,
                'file': u['source_name'] + '.md', 'source_path': u['source_path'],
                'source_sha256': u['source_sha256'],
                'argument_names': (u.get('invocation') or {}).get('argument_names', []),
                'description': (u.get('invocation') or {}).get('description', ''),
                'args_hint': (u.get('invocation') or {}).get('argument_hint', ''),
                'outcome': 'PENDING',
            })
        pkg = write_adapter_package(work / 'adapter', plan['name'], entries, root)
        write_manifest(pkg, plan['name'], entries)
        target = target_profile(installed_hermes_version)
        evidence_by_id = {e.get('capability_id'): e for e in (runtime_evidence or [])}
        results = []
        for u, e in zip(understood, entries):
            v = SV.verify_command(u, pkg, e, target=target, registry=registry,
                                  source_commit=source_commit,
                                  runtime_evidence=evidence_by_id.get(u['capability_id']))
            e['outcome'] = v['outcome']
            results.append(v)
        write_manifest(pkg, plan['name'], entries)  # final outcomes
        adapter_sha = _package_files_sha256(pkg)
        from .operator_approval import LOCK_NAME, build_lock
        from .pre_import_gate import scan as gate_scan
        gate = gate_scan(pkg)
        if not gate['ok'] or gate['package_sha256'] != adapter_sha:
            raise PortError('Generated adapter failed the pre-import gate: ' + '; '.join(gate['problems']))
        lock = build_lock(pkg, entries, results, adapter_sha, entry_template_sha256(), renderer_sha256(),
                          files=gate['files'])
        (work / LOCK_NAME).write_text(json.dumps(lock, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        bundle = CP.build_bundle(plan, understood, results, entries, adapter_sha, target,
                                 source_commit=source_commit)
        CP.write_bundle(work, bundle)
        from .importer_comparison import compare as compare_importer
        from .workshop_view import render_workshop
        comparison = compare_importer(plan, root, bundle)
        (work / 'OFFICIAL_IMPORTER_COMPARISON.json').write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (work / 'WORKSHOP.txt').write_text(render_workshop(bundle), encoding='utf-8')
        work.replace(final)
    bundle['output_path'] = str(final)
    bundle['adapter_path'] = str(final / 'adapter' / pkg.name)
    return bundle
