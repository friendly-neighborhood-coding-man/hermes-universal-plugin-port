"""Phase 2: eight-dimension semantic verification for repaired slash commands.

STATIC and RUNTIME results are kept in separate fields and never merged:

* static  - derived from the original source, the pinned host facts and by
            exercising OUR generated adapter (fixed template) against a
            recording fake Hermes context. No foreign code, no shell, no model.
* runtime - only from a runtime-evidence record captured on a real, disposable
            Hermes installation. Evidence is bound to the exact source hash,
            renderer hash, entry-template hash, target facts and installed
            Hermes version; any mismatch makes it STALE. Observed message hashes
            are recomputed and must match. Nothing here fabricates runtime data.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from . import claude_command as CC

DIMENSIONS = ('input', 'output', 'failure', 'permissions', 'approval', 'side_effects', 'state', 'invocation')
STATIC_STATUSES = ('PRESERVED_STATIC_VERIFIED', 'PRESERVED_WITH_CONDITIONS', 'NOT_PRESERVED',
                   'UNKNOWN', 'VIOLATION', 'NOT_APPLICABLE')
EVIDENCE_SCHEMA = 'universal-port.runtime-evidence/1'
_HERE = Path(__file__).resolve().parent
CASES_PATH = _HERE / 'semantics' / 'claude_argument_cases.json'
ALLOWED_ADAPTER_IMPORTS = {'hashlib', 'json', 'pathlib', 're', '__future__', 'claude_command'}
FORBIDDEN_NAME_CALLS = {'exec', 'eval', 'compile', '__import__', 'open', 'getattr', 'setattr'}
FORBIDDEN_ATTR_CALLS = {'system', 'popen', 'Popen', 'run', 'call', 'check_output', 'urlopen', 'socket', 'open',
                        'write_text', 'write_bytes', 'unlink', 'rmtree', 'mkdir', 'rename', 'replace_file',
                        'dispatch_tool', 'set_config', 'register_tool', 'register_hook', 'ask_choice',
                        'post_message', 'spawn_task', 'call_mcp'}
ARG_MARKER = 'ARGMARK7f3a91'


class RecordingContext:
    """Fake Hermes ctx that records every call; unknown attributes are violations."""

    def __init__(self, inject_result=True):
        self.calls = []
        self.registered = {}
        self.inject_result = inject_result

    def register_command(self, name, handler, description='', args_hint='', **kw):
        self.calls.append(('register_command', name))
        self.registered[name] = handler

    def inject_message(self, content, role='user', **kw):
        self.calls.append(('inject_message', role, content))
        if isinstance(self.inject_result, BaseException):
            raise self.inject_result
        return self.inject_result

    def __getattr__(self, item):
        self.calls.append(('UNEXPECTED_ATTRIBUTE', item))
        raise AttributeError(item)


def load_adapter(pkg: Path):
    """Import OUR generated adapter package (fixed template) under a unique name.

    v0.4.3 (review P0): the pre-import gate runs first. A tree with __pycache__,
    .pyc, extension modules or any other unexpected entry is refused before
    Python can choose which code to execute. (dont_write_bytecode below only
    stops WRITING caches; it does not stop Python from READING a planted one.)
    """
    from .pre_import_gate import scan as _gate_scan
    gate = _gate_scan(pkg)
    if not gate['ok']:
        raise ValueError('pre-import gate refused adapter: ' + '; '.join(gate['problems']))
    name = 'universal_port_adapter_' + uuid.uuid4().hex[:10]
    spec = importlib.util.spec_from_file_location(name, pkg / '__init__.py',
                                                  submodule_search_locations=[str(pkg)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # never leave __pycache__ inside a generated package
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.dont_write_bytecode = previous
    return module


def adapter_code_safety(pkg: Path) -> dict:
    """AST allowlist over the adapter's Python files (defense in depth)."""
    problems = []
    for fname in ('__init__.py', 'claude_command.py'):
        tree = ast.parse((pkg / fname).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split('.')[0] not in ALLOWED_ADAPTER_IMPORTS:
                        problems.append(fname + ': import ' + a.name)
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or '').split('.')[0]
                if node.level == 0 and mod not in ALLOWED_ADAPTER_IMPORTS:
                    problems.append(fname + ': from ' + mod)
                if node.level > 0 and not ({a.name for a in node.names} <= {'claude_command'} or mod == 'claude_command'):
                    problems.append(fname + ': relative import ' + mod)
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_NAME_CALLS:
                    problems.append(fname + ': call ' + fn.id)
                if isinstance(fn, ast.Attribute) and fn.attr in FORBIDDEN_ATTR_CALLS:
                    problems.append(fname + ': call .' + fn.attr)
    from .slash_repair import entry_template_sha256, renderer_sha256
    if hashlib.sha256((pkg / '__init__.py').read_bytes()).hexdigest() != entry_template_sha256():
        problems.append('__init__.py differs from the reviewed fixed template')
    if hashlib.sha256((pkg / 'claude_command.py').read_bytes()).hexdigest() != renderer_sha256():
        problems.append('claude_command.py differs from the reviewed renderer')
    return {'ok': not problems, 'problems': problems}


def golden_cases(module) -> dict:
    data = json.loads(CASES_PATH.read_text(encoding='utf-8'))
    cc = module.claude_command if hasattr(module, 'claude_command') else sys.modules[module.__name__ + '.claude_command']
    failed = []
    for c in data['cases']:
        got = cc.render(c['body'], c['args'], c.get('names'))['text']
        if got != c['expect']:
            failed.append(c['id'])
    for c in data['refusals']:
        try:
            cc.render(c['body'], c['args'], c.get('names'))
            failed.append(c['id'])
        except cc.ArgumentRenderRefused:
            pass
    return {'ok': not failed, 'cases': len(data['cases']), 'refusals': len(data['refusals']),
            'failed': failed, 'assumptions': [c['id'] for c in data['cases'] if c.get('assumption')]}


def _manifest_entry(pkg: Path, source_name: str):
    manifest = json.loads((pkg / 'ADAPTER_MANIFEST.json').read_text(encoding='utf-8'))
    for e in manifest['commands']:
        if e['source_name'] == source_name:
            return manifest, e
    raise KeyError(source_name)


def _check(name, ok, detail=''):
    return {'check': name, 'result': 'PASS' if ok else 'FAIL', 'detail': detail}


def exercise_adapter(u: dict, pkg: Path) -> list[dict]:
    """Static behavioral checks of OUR adapter for one command (recording fake ctx)."""
    checks = []
    module = load_adapter(pkg)
    manifest, entry = _manifest_entry(pkg, u['source_name'])
    raw = (pkg / 'commands' / entry['file']).read_bytes()
    checks.append(_check('original_bytes_reused', hashlib.sha256(raw).hexdigest() == u['source_sha256'],
                         'adapter ships the original command file byte-for-byte'))
    _meta, body, _ = CC.parse_frontmatter(raw.decode('utf-8'))
    disabled = CC.disable_shell_injections(body)
    header_prefix = '[Ported Claude Code command /' + u['source_name'] + ' via Hermes adapter /'
    args = u['arguments']
    names = entry['argument_names']
    # Round-trip: with only $ARGUMENTS placeholders, replacing the marker back
    # must reproduce the (shell-disabled) original body exactly.
    if args['all'] and not args['indexed'] and not args['named'] and not args['escaped']:
        msg = module.build_message(manifest, entry, ARG_MARKER)
        restored = msg.split('\n', 1)[1].replace(ARG_MARKER, '$ARGUMENTS')
        checks.append(_check('all_arguments_round_trip', restored == disabled and msg.startswith(header_prefix)))
        tricky = 'main --no-push "quoted value" $HOME ; `x` \\ /yolo'
        msg2 = module.build_message(manifest, entry, tricky)
        checks.append(_check('raw_arguments_inserted_verbatim', tricky in msg2,
                             'metacharacters and quotes are passed through untouched for $ARGUMENTS'))
    if not args['all'] and not args['indexed'] and not args['named']:
        msg = module.build_message(manifest, entry, 'alpha beta')
        checks.append(_check('unreceived_arguments_appended',
                             msg.split('\n', 1)[1] == disabled + CC.APPEND_SEPARATOR + 'ARGUMENTS: alpha beta'))
        msg0 = module.build_message(manifest, entry, '')
        checks.append(_check('no_arguments_body_unchanged', msg0.split('\n', 1)[1] == disabled))
    if args['indexed'] or args['named']:
        for bad in ('$HOME', '"unbalanced', 'a;b'):
            ctx = RecordingContext()
            out = module.make_handler(ctx, manifest, entry)(bad)
            ok = out.startswith('NOT SENT') and not any(c[0] == 'inject_message' for c in ctx.calls)
            checks.append(_check('ambiguous_arguments_refused:' + bad, ok))
    # Handler: exactly one user message; nothing else touched.
    ctx = RecordingContext(True)
    out = module.make_handler(ctx, manifest, entry)('/yolo')
    injected = [c for c in ctx.calls if c[0] == 'inject_message']
    other = [c for c in ctx.calls if c[0] != 'inject_message']
    if args['indexed'] or args['named']:
        ok = len(injected) <= 1 and not other
    else:
        ok = len(injected) == 1 and injected[0][1] == 'user' and not other and out.startswith('Queued')
    checks.append(_check('handler_single_user_message_no_other_ctx_calls', ok))
    if injected:
        checks.append(_check('no_leading_slash_command_injection', injected[0][2].startswith('[Ported Claude Code command')))
    ctx = RecordingContext(False)
    out = module.make_handler(ctx, manifest, entry)('x')
    checks.append(_check('refused_injection_reported', out.startswith('NOT SENT')))
    ctx = RecordingContext(RuntimeError('boom'))
    out = module.make_handler(ctx, manifest, entry)('x')
    checks.append(_check('injection_exception_reported_not_retried',
                         out.startswith('NOT SENT') and sum(c[0] == 'inject_message' for c in ctx.calls) == 1))
    ctx = RecordingContext()
    out = module.make_handler(ctx, manifest, entry)('a\x07b')
    checks.append(_check('control_characters_refused',
                         out.startswith('NOT SENT') and not any(c[0] == 'inject_message' for c in ctx.calls)))
    # Shell injections never survive into the rendered template.
    rendered_template = module.build_message(manifest, entry, '').split('\n', 1)[1]
    checks.append(_check('no_executable_shell_pattern_in_rendered_template',
                         not CC.HERMES_INLINE_SHELL.search(rendered_template)))
    # Tamper: modify a copy of the command after "approval" -> refuse.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / pkg.name
        shutil.copytree(pkg, copy, ignore=shutil.ignore_patterns('__pycache__'))
        (copy / 'commands' / entry['file']).write_bytes(raw + b'\nInjected after approval.\n')
        mod2 = load_adapter(copy)
        ctx = RecordingContext()
        out = mod2.make_handler(ctx, manifest, entry)('x')
        checks.append(_check('source_modified_after_approval_refused',
                             out.startswith('NOT SENT') and not any(c[0] == 'inject_message' for c in ctx.calls)))
    return checks


def classify_dimensions(u: dict, naming_notes: list[str]) -> dict:
    """Map understanding -> per-dimension STATIC status with explicit reasons."""
    inv = u['invocation']
    args = u['arguments']
    perms = u['permissions']
    shells = u['shell_injections']
    has_shell = bool(shells['inline'] or shells['fenced_blocks'])
    unmapped_tools = [t for t in u['tool_references'] if t != 'AskUserQuestion']
    d = {}

    def put(dim, status, reasons, conditions=()):
        d[dim] = {'static': status, 'reasons': list(reasons), 'conditions': list(conditions)}

    # input
    if args['ambiguous']:
        put('input', 'UNKNOWN', ['Template uses undocumented placeholder forms: ' + ', '.join(args['ambiguous'])])
    else:
        cond = ['Hermes raw_args are whitespace-trimmed before rendering (Claude "as typed" trimming is undocumented)']
        if args['indexed'] or args['named']:
            cond.append('Indexed/named arguments: inputs whose shell quoting is undocumented (escapes, unquoted $, '
                        'operators, globs, unbalanced quotes) are refused instead of guessed')
        reasons = ['Documented $ARGUMENTS/$N/$ARGUMENTS[N]/$name/escape rules reproduced; golden cases pass']
        if args['likely_unintended']:
            reasons.append('Warning (not rewritten): ' + ', '.join(args['likely_unintended'])
                           + ' will expand exactly as Claude Code would when enough arguments are given')
        put('input', 'PRESERVED_WITH_CONDITIONS', reasons, cond)
    # output
    out_np, out_unknown = [], []
    if has_shell:
        out_np.append('Source bang-backtick / ```! injections: Claude runs them and inlines output; the adapter renders '
                      "Claude's documented disabled-by-policy placeholder instead")
    if u['claude_variables']:
        out_np.append('${CLAUDE_*} variables are not substituted: ' + ', '.join(u['claude_variables']))
    if inv['model'] or inv['effort']:
        out_np.append('Per-command model/effort override is not applied by Hermes')
    if u['file_references']:
        out_unknown.append(str(u['file_references']) + ' possible @file references: Claude attaches file contents; '
                           'Hermes handling of @ in an injected user message is unverified')
    if out_np:
        put('output', 'NOT_PRESERVED', out_np + out_unknown)
    elif out_unknown:
        put('output', 'UNKNOWN', out_unknown)
    else:
        put('output', 'PRESERVED_WITH_CONDITIONS', ['Original body rendered byte-for-byte apart from placeholders'],
            ['One provenance header line is prepended (prevents the message being parsed as a Hermes /command)'])
    # failure
    if has_shell:
        put('failure', 'NOT_PRESERVED', ['Claude aborts the whole invocation when an injected command fails or is '
                                         'not permission-allowed; no command runs in the adapter'])
    else:
        put('failure', 'PRESERVED_WITH_CONDITIONS', ['Source defines no host-level failure path'],
            ['Adapter adds fail-closed refusals (integrity, ambiguous arguments, injection refused) that report '
             '"NOT SENT" and never retry'])
    # permissions
    if perms['disallowed_tools_count']:
        put('permissions', 'VIOLATION', ['disallowed-tools removes tools for the turn; Hermes has no per-command tool '
                                         'removal, so the ported command would run with MORE capability'])
    elif perms['allowed_tools_count'] or inv['has_hooks']:
        r = []
        if perms['allowed_tools_count']:
            r.append('allowed-tools pre-approval (' + str(perms['allowed_tools_count']) + ' rules) has no Hermes '
                     'counterpart: Hermes applies its own approval policy (stricter, no escalation)')
        if inv['has_hooks']:
            r.append('Skill-scoped hooks are not ported')
        put('permissions', 'NOT_PRESERVED', r)
    else:
        put('permissions', 'PRESERVED_STATIC_VERIFIED',
            ['No tool grants or restrictions in source; adapter registers no tools and changes no policy'])
    # approval (v0.4.1: absence of markers is never proof)
    if u['approval_markers'] or u.get('approval_bypass_markers'):
        r = []
        if u['approval_markers']:
            r.append(str(u['approval_markers']) + ' model-mediated approval marker(s) (AskUserQuestion/checkpoints). '
                     'Hermes clarify/approval equivalence has no verified mapping; must be runtime-tested')
        if u.get('approval_bypass_markers'):
            r.append(str(u['approval_bypass_markers']) + ' instruction(s) to act without asking / immediately: '
                     'whether Hermes approval policy then intervenes is unverified')
        put('approval', 'UNKNOWN', r)
    else:
        put('approval', 'PRESERVED_WITH_CONDITIONS',
            ['Adapter itself requires and bypasses no approval (invoking a command needs none in either host)'],
            ['Heuristic scan found no approval instructions in the prompt; this is NOT proof that none are implied. '
             'Approvals the model requests are governed by each host\'s own policy'])
    # side effects (v0.4.1: adapter-direct vs model-induced are reported separately)
    se_unknown = []
    if u['side_effect_markers']:
        se_unknown.append('Side-effect markers (' + ', '.join(u['side_effect_markers']) + '): effects are carried out '
                          'by the model with host tools; equivalence of Hermes tool behavior unverified')
    if unmapped_tools:
        se_unknown.append('References Claude tools with no verified Hermes mapping: ' + ', '.join(unmapped_tools))
    model_induced_condition = ('Model-induced effects of the delivered prompt cannot be proven statically; the same '
                               'prompt text reaches the model, but resulting tool use is host- and model-dependent. '
                               'Heuristic marker scan is not proof of absence')
    if has_shell:
        put('side_effects', 'NOT_PRESERVED', ['Pre-render shell side effects are removed'] + se_unknown)
    elif se_unknown:
        put('side_effects', 'UNKNOWN', se_unknown)
    else:
        put('side_effects', 'PRESERVED_WITH_CONDITIONS',
            ['Adapter-direct effects: exactly one queued user message (verified with recording context)'],
            [model_induced_condition])
    d.setdefault('side_effects', {})['adapter_direct'] = 'ONE_USER_MESSAGE_VERIFIED_STATIC'
    d['side_effects']['model_induced'] = 'UNKNOWN_REQUIRES_RUNTIME' if not se_unknown and not has_shell else 'UNKNOWN'
    # state
    if inv['context'] == 'fork' or inv['agent']:
        put('state', 'NOT_PRESERVED', ['context: fork/agent runs Claude in an isolated subagent; the adapter injects '
                                       'into the current conversation'])
    else:
        put('state', 'PRESERVED_WITH_CONDITIONS', ['Rendered prompt persists in the conversation, as in Claude'],
            [('Classic CLI (pinned source a9ff979): while the agent is running, Hermes puts injected text on the INTERRUPT '
             'queue; routing in the installed version and runtime mode is not runtime-confirmed')])
    # invocation
    inv_np, inv_unknown = [], []
    if not inv['user_invocable']:
        inv_np.append('user-invocable: false (model-only) cannot be represented by a user slash command')
    if not inv['disable_model_invocation'] and inv['user_invocable']:
        inv_np.append('Claude can also invoke this command on its own; a Hermes plugin command is user-only '
                      '(the staged SKILL.md fallback lacks $ARGUMENTS semantics)')
    if u['parse']['unknown_keys'] or u['parse']['unparsed_keys']:
        inv_unknown.append('Unrecognized/unparsed frontmatter keys: '
                           + ', '.join(u['parse']['unknown_keys'] + u['parse']['unparsed_keys']))
    cond = ['Gateway/TUI and gateway-backed sessions may require plugins.entries.<adapter>.allow_gateway_injection: '
            'true (never set by this tool); whether a given CLI session needs it depends on the installed Hermes '
            'version and runtime mode and must be observed',
            'Collisions with OTHER installed plugins are not checked: in Hermes source a later same-name plugin '
            'registration displaces the earlier one (load-order dependent)',
            ('inject_message only queues a user message: it is not a synchronous command execution, "Queued" never means '
            'executed or succeeded, and the attached client may not display the turn (host/version dependent)')] + list(naming_notes)
    if inv_np:
        put('invocation', 'NOT_PRESERVED', inv_np + inv_unknown, cond)
    elif inv_unknown:
        put('invocation', 'UNKNOWN', inv_unknown, cond)
    else:
        put('invocation', 'PRESERVED_WITH_CONDITIONS', ['User invocation /' + str(u.get('hermes_command'))
                                                        + ' <args> renders and queues the command'], cond)
    return d


def expected_binding(u: dict, target: dict) -> dict:
    from .slash_repair import entry_template_sha256, renderer_sha256
    return {'capability_id': u['capability_id'], 'source_sha256': u['source_sha256'],
            'renderer_sha256': renderer_sha256(), 'entry_template_sha256': entry_template_sha256(),
            'claude_semantics_version': CC.SEMANTICS_VERSION,
            'target_facts_sha256': target['facts_sha256'],
            'hermes_version': target['installed_hermes_version']}


def evaluate_runtime_evidence(evidence: dict | None, u: dict, target: dict, pkg: Path) -> dict:
    """Validate a runtime evidence record; never invent one."""
    if evidence is None:
        return {'status': 'RUNTIME_NOT_VERIFIED', 'dimensions': {d: 'NOT_RUN' for d in DIMENSIONS},
                'reason': 'No runtime evidence recorded on a real Hermes installation'}
    problems = []
    if evidence.get('schema') != EVIDENCE_SCHEMA:
        problems.append('unknown evidence schema')
    binding = expected_binding(u, target)
    if binding['hermes_version'] is None:
        return {'status': 'STALE', 'dimensions': {d: 'STALE' for d in DIMENSIONS},
                'reason': 'Installed Hermes version unknown; evidence cannot be matched to a target'}
    stale = sorted(k for k, v in binding.items() if (evidence.get('binding') or {}).get(k) != v)
    if stale:
        return {'status': 'STALE', 'dimensions': {d: 'STALE' for d in DIMENSIONS},
                'reason': 'Evidence bound to different ' + ', '.join(stale)}
    env = evidence.get('environment') or {}
    if env.get('disposable_profile') is not True or env.get('production_credentials_present') is not False:
        problems.append('evidence must come from a disposable profile without production credentials')
    module = load_adapter(pkg)
    manifest, entry = _manifest_entry(pkg, u['source_name'])
    vectors = evidence.get('vectors') or []
    vector_fail = []
    for v in vectors:
        try:
            expect = hashlib.sha256(module.build_message(manifest, entry, v['raw_args']).encode()).hexdigest()
        except CC.ArgumentRenderRefused:
            expect = 'REFUSED'
        if v.get('observed_message_sha256') != expect:
            vector_fail.append(v.get('raw_args', '')[:40])
    if not vectors:
        problems.append('no observed message vectors')
    dims = {}
    for d in DIMENSIONS:
        r = ((evidence.get('dimensions') or {}).get(d) or {}).get('result')
        dims[d] = r if r in {'PASS', 'FAIL', 'NOT_APPLICABLE'} else 'NOT_RUN'
    if vector_fail:
        dims['output'] = 'FAIL'
        problems.append('observed message hash mismatch for: ' + ', '.join(vector_fail))
    if problems:
        return {'status': 'INVALID', 'dimensions': dims, 'reason': '; '.join(problems)}
    claimed_pass = all(v in {'PASS', 'NOT_APPLICABLE'} for v in dims.values())
    # v0.4.1 (review P0-2): a JSON file is a CLAIM. Its PASS values and
    # environment booleans cannot be authenticated, so it is reported as
    # SELF_REPORTED and can never set runtime_behavior_verified. Promotion
    # requires a trusted Hermes-side collector, which this release does not have.
    if 'FAIL' in dims.values():
        status = 'FAIL'
    else:
        status = 'SELF_REPORTED_UNTRUSTED'
    return {'status': status, 'trust': 'SELF_REPORTED', 'claimed_all_pass': claimed_pass,
            'dimensions': dims, 'evidence_sha256': hashlib.sha256(
                json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
            'reason': ('Binding and observed message hashes are consistent, but the record is self-reported JSON: '
                       'not accepted as runtime verification (no trusted collector in this release)')}


def _direct_route(u: dict, registry: dict | None, source_commit: str | None, target: dict) -> dict:
    mappings = (registry or {}).get('mappings') or []
    hits = [m for m in mappings if m['evidence']['source_command_sha256'] == u['source_sha256']
            and m['evidence']['source_commit_sha'] == source_commit
            and m['evidence']['target_version'] == target['installed_hermes_version']]
    return {'registry_mappings': len(mappings), 'applicable_mappings': len(hits),
            'applicable': bool(hits),
            'reason': 'Trusted registry has no mapping bound to this command, commit and Hermes version'
            if not hits else 'Trusted command-bound mapping present'}


def verify_command(u: dict, pkg: Path, entry: dict, *, target: dict, registry=None,
                   source_commit=None, runtime_evidence=None) -> dict:
    base = {'capability_id': u['capability_id'], 'source_sha256': u['source_sha256']}
    if not u['parse']['ok']:
        return {**base, 'outcome': 'UNSUPPORTED', 'reasons': ['Source not parseable without guessing: '
                + u['parse']['error']], 'dimensions': {}, 'static_checks': [],
                'runtime': evaluate_runtime_evidence(None, u, target, pkg),
                'stages': _stages(False, False, False, False, 'UNSUPPORTED')}
    dims = classify_dimensions(u, u.get('naming_notes') or [])
    checks = []
    safety = adapter_code_safety(pkg)
    checks.append(_check('adapter_code_allowlist', safety['ok'], '; '.join(safety['problems'])))
    gold = golden_cases(load_adapter(pkg))
    checks.append(_check('documented_argument_golden_cases', gold['ok'],
                         'failed: ' + ', '.join(gold['failed']) if gold['failed'] else
                         str(gold['cases']) + ' cases + ' + str(gold['refusals']) + ' refusals'))
    try:
        checks.extend(exercise_adapter(u, pkg))
    except Exception as exc:  # a crash in our own adapter is a static failure, not a pass
        checks.append(_check('adapter_exercise_crashed', False, type(exc).__name__ + ': ' + str(exc)[:160]))
    static_ok = all(c['result'] == 'PASS' for c in checks)
    runtime = evaluate_runtime_evidence(runtime_evidence, u, target, pkg)
    direct = _direct_route(u, registry, source_commit, target)
    statuses = {d['static'] for d in dims.values()}
    reasons = []
    inv = u['invocation']
    if not inv['user_invocable'] or inv['context'] == 'fork':
        outcome = 'UNSUPPORTED'
        reasons.append('Execution model (model-only or forked subagent) cannot be represented by a native user command')
    elif 'VIOLATION' in statuses or not static_ok:
        outcome = 'BLOCKED_UNSAFE'
        reasons += [f'{k}: VIOLATION' for k, v in dims.items() if v['static'] == 'VIOLATION']
        reasons += ['static check failed: ' + c['check'] for c in checks if c['result'] != 'PASS']
    elif statuses & {'NOT_PRESERVED', 'UNKNOWN'}:
        outcome = 'PARTIAL_REVIEW_REQUIRED'
        reasons += [f'{k}: {v["static"]}' for k, v in dims.items() if v['static'] in {'NOT_PRESERVED', 'UNKNOWN'}]
    elif runtime_trusted_pass(runtime) and direct['applicable']:
        outcome = 'DIRECT_EQUIVALENT_VERIFIED'
    elif runtime_trusted_pass(runtime):
        outcome = 'ADAPTED_RUNTIME_VERIFIED'
    else:
        outcome = 'ADAPTED_STATICALLY'
        reasons.append('All dimensions statically preserved (some with stated conditions); runtime: '
                       + runtime['status'])
    if runtime['status'] in {'FAIL', 'INVALID'} and outcome in {'ADAPTED_STATICALLY'}:
        outcome = 'PARTIAL_REVIEW_REQUIRED'
        reasons.append('Runtime evidence ' + runtime['status'] + ': ' + runtime['reason'])
    return {**base, 'outcome': outcome, 'reasons': reasons, 'dimensions': dims,
            'static_checks': checks, 'static_checks_passed': static_ok,
            'runtime': runtime, 'direct_bridge': direct,
            'stages': _stages(True, True, static_ok, runtime_trusted_pass(runtime), outcome)}


def runtime_trusted_pass(runtime: dict) -> bool:
    """Promotion gate. Only a TRUSTED_COLLECTOR observation could pass it.

    No code path in v0.4.1 produces trust == 'TRUSTED_COLLECTOR' (ingested files
    are always SELF_REPORTED), so this gate is closed by construction.
    """
    return runtime.get('status') == 'PASS' and runtime.get('trust') == 'TRUSTED_COLLECTOR'


def _stages(understood, generated, static_ok, runtime_ok, outcome):
    return {
        'source_functionality_understood': understood,
        'adapter_generated': generated and outcome not in {'UNSUPPORTED'},
        'static_checks_passed': static_ok,
        'runtime_behavior_verified': runtime_ok,
        'ready_for_installation': runtime_ok and outcome in {'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'},
        'blocked_or_unverified': outcome not in {'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'},
    }
