"""v0.4.0 offline tests: slash-command repair, verification, passport, update impact.

No real Hermes, model, network, git, foreign code or installation is used.
Runtime-evidence records built inside these tests are SYNTHETIC and exist only
to exercise the evidence validator; they are never written to the package.
"""
import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('universal_port_v040_testpkg', ROOT / '__init__.py',
                                              submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from universal_port_v040_testpkg import (claude_command as CC, slash_repair as R, semantic_verification as SV,
                                         capability_passport as CP, update_reconciliation as U,
                                         importer_comparison as IC, workshop_view as W, port_core as CORE,
                                         port_flow as FLOW, hermes_target as HT, operator_approval as OA)

FIXTURE = ROOT / 'examples' / 'claude-repair-fixture'
REV_A = ROOT / 'examples' / 'update-fixture' / 'rev-a'
REV_B = ROOT / 'examples' / 'update-fixture' / 'rev-b'
EXPECTED = {
    'fix-issue': 'ADAPTED_STATICALLY', 'migrate-component': 'ADAPTED_STATICALLY',
    'summarize': 'ADAPTED_STATICALLY', 'plan-trip': 'ADAPTED_STATICALLY',
    'pr-summary': 'PARTIAL_REVIEW_REQUIRED', 'commit': 'PARTIAL_REVIEW_REQUIRED',
    'review': 'PARTIAL_REVIEW_REQUIRED', 'locked-down': 'BLOCKED_UNSAFE',
    'research': 'UNSUPPORTED', 'broken': 'UNSUPPORTED',
}


def by_name(bundle):
    return {p['capability_id'].rsplit(':', 1)[-1]: p for p in bundle['passports']}


class Tmp(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)

    def copy_fixture(self, src=FIXTURE, name='src'):
        dest = self.tmp / name
        n = 0
        while dest.exists():
            n += 1
            dest = self.tmp / (name + '-' + str(n))
        shutil.copytree(src, dest)
        return dest

    def approve(self, bundle, names):
        """v0.4.2: explicit operator approval (registration is opt-in)."""
        return OA.approve(bundle['output_path'], list(names), operator='unit-test',
                          reviewed_model_induced_effects=True)

    def repair(self, src=None, **kw):
        src = src or self.copy_fixture()
        return R.repair_plugin(str(src), str(self.tmp / ('out-' + str(len(list(self.tmp.iterdir()))))), **kw)


class RendererTests(unittest.TestCase):
    def test_documented_golden_cases(self):
        data = json.loads((ROOT / 'semantics' / 'claude_argument_cases.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(data['cases']), 16)
        for c in data['cases']:
            with self.subTest(c['id']):
                self.assertEqual(CC.render(c['body'], c['args'], c.get('names'))['text'], c['expect'])

    def test_documented_refusals_fail_closed(self):
        data = json.loads((ROOT / 'semantics' / 'claude_argument_cases.json').read_text(encoding='utf-8'))
        for c in data['refusals']:
            with self.subTest(c['id']), self.assertRaises(CC.ArgumentRenderRefused):
                CC.render(c['body'], c['args'], c.get('names'))

    def test_values_are_not_rescanned(self):
        out = CC.render('A $0 B $1', '"$1" x')['text']
        self.assertEqual(out, 'A $1 B x')

    def test_all_arguments_accept_metacharacters_verbatim(self):
        raw = 'main --no-push "a b" $HOME ; `id` \\ |'
        self.assertEqual(CC.render('<$ARGUMENTS>', raw)['text'], '<' + raw + '>')

    def test_substitution_applies_inside_code_fences_like_claude(self):
        body = '```json\n{"target": "$ARGUMENTS"}\n```\n'
        self.assertIn('"target": "main"', CC.render(body, 'main')['text'])

    def test_frontmatter_errors_are_not_guessed(self):
        for text in ('---\ndescription: x\nbody', '---\na:\n  b: c\n---\nx', '---\na: 1\na: 2\n---\nx',
                     '---\nd: |\n  multi\n---\nx'):
            with self.subTest(text=text):
                try:
                    meta, _b, unparsed = CC.parse_frontmatter(text)
                except CC.CommandFormatError:
                    continue
                self.assertTrue(unparsed, 'unsupported YAML must be reported, not silently parsed')

    def test_crlf_frontmatter_is_valid_but_stray_cr_rejected(self):
        source = ('---\r\ndescription: t\r\ndisable-model-invocation: true\r\n'
                  'future-key: x\r\n---\r\nUse TodoWrite for $ARGUMENTS\r\n')
        meta, body, unknown = CC.parse_frontmatter(source)
        self.assertEqual(meta['description'], 't')
        self.assertTrue(meta['disable-model-invocation'])
        self.assertEqual(meta['future-key'], 'x')
        self.assertEqual(unknown, [])
        self.assertEqual(body, 'Use TodoWrite for $ARGUMENTS\r\n')
        with self.assertRaises(CC.CommandFormatError):
            CC.parse_frontmatter(source.replace('t\r\n', 't\r', 1))

    def test_frontmatter_lists_and_body_exact(self):
        meta, body, unparsed = CC.parse_frontmatter('---\narguments: [a, b]\nallowed-tools:\n  - Read\n  - Bash(git add *)\n---\n\nBody $a\n')
        self.assertEqual(meta['arguments'], ['a', 'b'])
        self.assertEqual(meta['allowed-tools'], ['Read', 'Bash(git add *)'])
        self.assertEqual(body, '\nBody $a\n')
        self.assertEqual(unparsed, [])

    def test_shell_injection_rules(self):
        body = 'Diff: !`git diff`\nKEY=!`id`\n```!\nnode --version\ngit status\n```\nend\n'
        found = CC.find_shell_injections(body)
        self.assertEqual(found['inline'], 1)
        self.assertEqual(found['fenced_blocks'], 1)
        out = CC.disable_shell_injections(body)
        self.assertEqual(out.count(CC.SHELL_DISABLED_PLACEHOLDER), 2)
        self.assertIsNone(CC.HERMES_INLINE_SHELL.search(out))
        self.assertNotIn('node --version', out)

    def test_currency_like_placeholder_flagged_not_rewritten(self):
        self.assertEqual(CC.likely_unintended_placeholders('stipend ($1,500)'), ['currency_like_$1'])
        self.assertEqual(CC.render('($1,500)', 'a b')['text'], '(b,500)')


class RepairPipelineTests(Tmp):
    def test_expected_outcomes_on_synthetic_fixture(self):
        b = self.repair()
        got = {k: v['outcome'] for k, v in by_name(b).items()}
        self.assertEqual(got, EXPECTED)

    def test_no_runtime_claims_without_evidence(self):
        b = self.repair()
        self.assertEqual(b['runtime_verified_count'], 0)
        self.assertEqual(b['ready_for_installation_count'], 0)
        self.assertFalse(b['installation']['performed'])
        for p in b['passports']:
            self.assertEqual(p['verification']['runtime_status'], 'RUNTIME_NOT_VERIFIED')
            self.assertFalse(p['stages']['runtime_behavior_verified'])
            self.assertTrue(p['stages']['blocked_or_unverified'])

    def test_passport_has_stage_flags_not_single_success(self):
        b = self.repair()
        text = (Path(b['output_path']) / 'CAPABILITY_PASSPORT.json').read_text(encoding='utf-8')
        self.assertNotIn('"success"', text)
        for p in b['passports']:
            self.assertEqual(set(p['stages']), {'source_functionality_understood', 'adapter_generated',
                                                'static_checks_passed', 'runtime_behavior_verified',
                                                'ready_for_installation', 'blocked_or_unverified'})
            self.assertEqual(p['integration']['model_calls'], 0)

    def test_adapter_reuses_original_bytes_and_has_no_cache(self):
        src = self.copy_fixture()
        b = R.repair_plugin(str(src), str(self.tmp / 'o'))
        pkg = Path(b['adapter_path'])
        for f in (src / 'commands').iterdir():
            self.assertEqual((pkg / 'commands' / f.name).read_bytes(), f.read_bytes())
        self.assertFalse(any(p.name == '__pycache__' for p in pkg.rglob('*')))
        self.assertEqual(hashlib.sha256((pkg / '__init__.py').read_bytes()).hexdigest(), R.entry_template_sha256())

    def test_builtin_command_collision_renamed(self):
        b = self.repair()
        self.assertEqual(by_name(b)['review']['integration']['hermes_command'], '/repair-fixture-review')
        self.assertIn('review', HT.BUILTIN_COMMANDS)

    def test_register_skips_blocked_and_unsupported(self):
        b = self.repair()
        # v0.4.2 (review R1): even fully adapted commands need explicit approval;
        # approving every eligible one registers exactly the 4 ADAPTED_STATICALLY commands.
        self.approve(b, ['fix-issue', 'migrate-component', 'summarize', 'plan-trip'])
        ctx = SV.RecordingContext()
        SV.load_adapter(Path(b['adapter_path'])).register(ctx)
        self.assertEqual(set(ctx.registered), {'fix-issue', 'migrate-component', 'summarize', 'plan-trip'})
        self.assertFalse(any(c[0] == 'inject_message' for c in ctx.calls))

    def test_partial_commands_never_registered_by_default(self):
        b = self.repair()
        ctx = SV.RecordingContext()
        SV.load_adapter(Path(b['adapter_path'])).register(ctx)
        for name in ('pr-summary', 'commit', 'repair-fixture-review', 'review', 'locked-down', 'research', 'broken'):
            self.assertNotIn(name, ctx.registered)
        manifest = json.loads((Path(b['adapter_path']) / 'ADAPTER_MANIFEST.json').read_text(encoding='utf-8'))
        for e in manifest['commands']:
            if e['outcome'] != 'ADAPTED_STATICALLY':
                self.assertNotIn(e['hermes_command'], ctx.registered)

    def test_unknown_or_missing_outcome_never_registered(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        mpath = pkg / 'ADAPTER_MANIFEST.json'
        manifest = json.loads(mpath.read_text(encoding='utf-8'))
        for i, e in enumerate(manifest['commands']):
            e['outcome'] = ['PENDING', 'adapted_statically', None, '', 'PARTIAL_REVIEW_REQUIRED'][i % 5]
        mpath.write_text(json.dumps(manifest), encoding='utf-8')
        # Simulate an operator who re-approved the edited folder (digest matches): unknown
        # outcomes must still never register.
        ap = OA.approval_path(Path(b['output_path']), pkg.name)
        ap.parent.mkdir(exist_ok=True)
        ap.write_text(json.dumps({'schema': OA.APPROVAL_SCHEMA, 'adapter': pkg.name,
                                  'adapter_package_sha256': R._package_files_sha256(pkg),
                                  'approved': [{k: e[k] for k in ('source_name', 'source_sha256', 'hermes_command')}
                                               for e in manifest['commands']]}), encoding='utf-8')
        ctx = SV.RecordingContext()
        SV.load_adapter(pkg).register(ctx)
        self.assertEqual(ctx.registered, {})
        self.assertEqual(len([c for c in ctx.calls if c[0] == 'register_command']), 0)

    def test_registrable_outcomes_allowlist_is_exact(self):
        mod = SV.load_adapter(Path(self.repair()['adapter_path']))
        self.assertEqual(set(mod.REGISTRABLE_OUTCOMES),
                         {'ADAPTED_STATICALLY', 'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'})
        self.assertEqual(set(CP.REGISTERED_BY_DEFAULT_OUTCOMES), set(mod.REGISTRABLE_OUTCOMES))

    def test_passport_and_workshop_mark_unregistered_commands(self):
        b = self.repair()
        rows = by_name(b)
        # v0.4.2: nothing is registered by default; eligible rows need operator approval.
        self.assertEqual(rows['fix-issue']['integration']['registration'], 'REQUIRES_OPERATOR_APPROVAL')
        for name in rows:
            self.assertFalse(rows[name]['integration']['registered_by_default'], name)
        for name in ('pr-summary', 'commit', 'review', 'locked-down', 'research', 'broken'):
            self.assertEqual(rows[name]['integration']['registration'], 'NOT_ELIGIBLE', name)
        text = W.render_workshop(b)
        line = [l for l in text.splitlines() if ' commit ' in l][0]
        self.assertIn('(not registered)', line)
        line = [l for l in text.splitlines() if ' fix-issue ' in l][0]
        self.assertIn('(needs operator approval)', line)

    def _handler(self, b, name, inject=True):
        self.approve(b, [name])
        mod = SV.load_adapter(Path(b['adapter_path']))
        ctx = SV.RecordingContext(inject)
        mod.register(ctx)
        return ctx, ctx.registered[name]

    def test_handler_renders_and_injects_one_user_message(self):
        b = self.repair()
        ctx, h = self._handler(b, 'fix-issue')
        out = h(' 123 ')
        self.assertTrue(out.startswith('Queued /fix-issue'))
        sent = [c for c in ctx.calls if c[0] == 'inject_message']
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1], 'user')
        self.assertIn('Fix GitHub issue 123 following our coding standards.', sent[0][2])
        self.assertTrue(sent[0][2].startswith('[Ported Claude Code command /fix-issue'))

    def test_slash_prefixed_arguments_cannot_trigger_hermes_command(self):
        b = self.repair()
        ctx, h = self._handler(b, 'summarize')
        h('/yolo')
        msg = [c for c in ctx.calls if c[0] == 'inject_message'][0][2]
        self.assertFalse(msg.lstrip().startswith('/'))
        self.assertTrue(msg.endswith('ARGUMENTS: /yolo'))

    def test_malformed_arguments_refused_without_side_effect(self):
        b = self.repair()
        ctx, h = self._handler(b, 'migrate-component')
        for bad in ('$HOME x y', '"open', 'a;b c d', 'a\\b c d'):
            self.assertTrue(h(bad).startswith('NOT SENT'))
        self.assertFalse(any(c[0] == 'inject_message' for c in ctx.calls))
        self.assertTrue(h('"Search Bar" React Vue').startswith('Queued'))
        msg = [c for c in ctx.calls if c[0] == 'inject_message'][0][2]
        self.assertIn('Migrate the Search Bar component from React to Vue.', msg)
        self.assertIn('Prices like $1.00 stay literal.', msg)

    def test_named_arguments_and_faithful_currency_expansion(self):
        b = self.repair()
        ctx, h = self._handler(b, 'plan-trip')
        h('Paris 3')
        msg = [c for c in ctx.calls if c[0] == 'inject_message'][0][2]
        self.assertIn('Plan a 3-day trip to Paris.', msg)
        self.assertIn('(3,500)', msg)  # `$1` -> 2nd argument, exactly as Claude Code documents; flagged
        p = by_name(b)['plan-trip']
        self.assertTrue(any('currency_like_$1' in x for x in p['known_limitations']))

    def test_refused_injection_is_reported_not_claimed(self):
        b = self.repair()
        _ctx, h = self._handler(b, 'fix-issue', inject=False)
        self.assertIn('allow_gateway_injection', h('1'))

    def test_source_modified_after_approval_refused(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        self.approve(b, ['fix-issue'])
        mod = SV.load_adapter(pkg)
        ctx = SV.RecordingContext()
        mod.register(ctx)
        (pkg / 'commands' / 'fix-issue.md').write_text('Run rm -rf / now $ARGUMENTS', encoding='utf-8')
        self.assertTrue(ctx.registered['fix-issue']('1').startswith('NOT SENT'))
        self.assertFalse(any(c[0] == 'inject_message' for c in ctx.calls))
        with self.assertRaises(ValueError):
            SV.load_adapter(pkg).register(SV.RecordingContext())

    def test_renderer_modification_refused(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        with (pkg / 'claude_command.py').open('a', encoding='utf-8') as f:
            f.write('\n# tampered\n')
        with self.assertRaisesRegex(ValueError, 'renderer changed'):
            SV.load_adapter(pkg).register(SV.RecordingContext())
        self.assertFalse(SV.adapter_code_safety(pkg)['ok'])

    def test_adapter_code_allowlist_detects_escalation(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        with (pkg / '__init__.py').open('a', encoding='utf-8') as f:
            f.write('\nimport subprocess\nsubprocess.run(["id"])\n')
        problems = SV.adapter_code_safety(pkg)['problems']
        self.assertTrue(any('subprocess' in p for p in problems))
        self.assertTrue(any('.run' in p for p in problems))

    def test_permission_restriction_blocks(self):
        p = by_name(self.repair())['locked-down']
        self.assertEqual(p['outcome'], 'BLOCKED_UNSAFE')
        self.assertEqual(p['semantic_contract']['dimensions']['permissions'], 'VIOLATION')
        self.assertFalse(p['stages']['ready_for_installation'])

    def test_preapproval_not_preserved_but_no_escalation(self):
        p = by_name(self.repair())['commit']
        d = p['semantic_contract']['dimensions']
        self.assertEqual(d['permissions'], 'NOT_PRESERVED')
        self.assertEqual(d['approval'], 'UNKNOWN')
        self.assertEqual(d['side_effects'], 'UNKNOWN')

    def test_shell_injection_partial_and_never_executed(self):
        b = self.repair()
        p = by_name(b)['pr-summary']
        self.assertEqual(p['semantic_contract']['dimensions']['output'], 'NOT_PRESERVED')
        self.assertEqual(p['semantic_contract']['dimensions']['failure'], 'NOT_PRESERVED')
        # pr-summary is PARTIAL and therefore not registered (P0-1); exercise its
        # handler directly so the shell-defusal guarantee is still tested.
        pkg = Path(b['adapter_path'])
        mod = SV.load_adapter(pkg)
        manifest, entry = SV._manifest_entry(pkg, 'pr-summary')
        ctx = SV.RecordingContext()
        h = mod.make_handler(ctx, manifest, entry)
        with patch('subprocess.run', side_effect=AssertionError('must not run')), \
                patch('subprocess.Popen', side_effect=AssertionError('must not run')):
            h('reviewers')
        msg = [c for c in ctx.calls if c[0] == 'inject_message'][0][2]
        self.assertIn(CC.SHELL_DISABLED_PLACEHOLDER, msg)
        self.assertNotIn('!`gh pr diff`', msg)

    def test_unknown_tools_and_unknown_frontmatter_stay_unknown(self):
        src = self.copy_fixture()
        (src / 'commands' / 'todo.md').write_text(
            '---\ndescription: t\ndisable-model-invocation: true\nfuture-key: x\n---\nUse TodoWrite for $ARGUMENTS\n',
            encoding='utf-8')
        p = by_name(self.repair(src))['todo']
        self.assertEqual(p['outcome'], 'PARTIAL_REVIEW_REQUIRED')
        self.assertEqual(p['semantic_contract']['dimensions']['side_effects'], 'UNKNOWN')
        self.assertEqual(p['semantic_contract']['dimensions']['invocation'], 'UNKNOWN')

    def test_unsupported_constructs(self):
        b = by_name(self.repair())
        self.assertEqual(b['broken']['outcome'], 'UNSUPPORTED')
        self.assertFalse(b['broken']['stages']['source_functionality_understood'])
        self.assertFalse(b['research']['stages']['adapter_generated'])
        self.assertIsNone(b['research']['integration']['hermes_command'])

    def test_static_check_crash_is_blocked_not_passed(self):
        with patch.object(SV, 'exercise_adapter', side_effect=RuntimeError('broken adapter')):
            b = self.repair()
        self.assertEqual(by_name(b)['fix-issue']['outcome'], 'BLOCKED_UNSAFE')

    def test_refuses_overwrite_and_non_claude_sources(self):
        src = self.copy_fixture()
        R.repair_plugin(str(src), str(self.tmp / 'o'))
        with self.assertRaisesRegex(CORE.PortError, 'overwrite'):
            R.repair_plugin(str(src), str(self.tmp / 'o'))
        codex = self.copy_fixture(ROOT / 'examples' / 'codex-sample', 'codex')
        with self.assertRaisesRegex(CORE.PortError, 'Claude Code'):
            R.repair_plugin(str(codex), str(self.tmp / 'o2'))

    def test_empty_registry_never_direct(self):
        for p in self.repair()['passports']:
            self.assertNotEqual(p['outcome'], 'DIRECT_EQUIVALENT_VERIFIED')
        reg = json.loads((ROOT / 'verified_mappings.json').read_text(encoding='utf-8'))
        self.assertEqual(reg['mappings'], [])


ADVERSARIAL = ROOT / 'examples' / 'adversarial-paraphrase-fixture'


class AdversarialParaphraseTests(Tmp):
    """v0.4.1 (review P1-3): absence of a regex marker is not proof of safety."""
    FLAGGED = {'clean-slate', 'fresh-start', 'ship-it', 'mail-report', 'tidy', 'buy-credits', 'declutter'}

    def bundle(self):
        return self.repair(self.copy_fixture(ADVERSARIAL, 'adv'))

    def test_reviewer_example_is_partial_and_unknown(self):
        p = by_name(self.bundle())['clean-slate']
        d = p['semantic_contract']['dimensions']
        self.assertEqual(d['side_effects'], 'UNKNOWN')
        self.assertEqual(d['approval'], 'UNKNOWN')
        self.assertEqual(p['outcome'], 'PARTIAL_REVIEW_REQUIRED')
        self.assertFalse(p['stages']['ready_for_installation'])

    def test_paraphrases_flagged_and_not_registered(self):
        b = self.bundle()
        rows = by_name(b)
        for name in self.FLAGGED:
            self.assertEqual(rows[name]['outcome'], 'PARTIAL_REVIEW_REQUIRED', name)
            self.assertEqual(rows[name]['semantic_contract']['dimensions']['side_effects'], 'UNKNOWN', name)
        ctx = SV.RecordingContext()
        SV.load_adapter(Path(b['adapter_path'])).register(ctx)
        # v0.4.2 (review R1): 'hollow' evades the scan but is still NOT registered by default.
        self.assertEqual(set(ctx.registered), set())

    def test_approval_bypass_phrases_make_approval_unknown(self):
        rows = by_name(self.bundle())
        for name in ('clean-slate', 'fresh-start', 'ship-it', 'mail-report'):
            self.assertEqual(rows[name]['semantic_contract']['dimensions']['approval'], 'UNKNOWN', name)

    def test_unflagged_text_is_never_statically_proven_safe(self):
        # 'hollow' evades the vocabulary on purpose: the scan cannot see it, so the
        # result must carry a condition instead of a proof (documented limitation).
        for src in (ADVERSARIAL, FIXTURE, REV_A):
            for p in self.repair(self.copy_fixture(src, 'any'))['passports']:
                d = p['semantic_contract']['dimensions']
                if d:
                    self.assertNotEqual(d['side_effects'], 'PRESERVED_STATIC_VERIFIED', p['capability_id'])
                    self.assertNotEqual(d['approval'], 'PRESERVED_STATIC_VERIFIED', p['capability_id'])
        hollow = by_name(self.bundle())['hollow']
        self.assertEqual(hollow['semantic_contract']['dimensions']['side_effects'], 'PRESERVED_WITH_CONDITIONS')
        self.assertTrue(any('not proof' in x for x in hollow['known_limitations']))

    def test_adapter_direct_and_model_induced_effects_are_separated(self):
        b = self.bundle()
        data = json.loads((Path(b['output_path']) / 'VERIFICATION_RESULTS.json').read_text(encoding='utf-8'))
        for r in data['results']:
            se = (r.get('dimensions') or {}).get('side_effects')
            if se:
                self.assertEqual(se['adapter_direct'], 'ONE_USER_MESSAGE_VERIFIED_STATIC')
                self.assertTrue(se['model_induced'].startswith('UNKNOWN'))


class WindowsSmokeScriptTests(unittest.TestCase):
    """Reviews P1-4 / R4: static checks only; the script is not executed (no Windows here)."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / 'WINDOWS_REPAIR_SMOKE.ps1').read_text(encoding='utf-8')
        cls.code = '\n'.join(l for l in cls.text.split('#>', 1)[1].splitlines() if not l.lstrip().startswith('#'))

    def test_requires_hermes_and_throws_when_missing(self):
        self.assertIn('Get-Command hermes', self.code)
        self.assertRegex(self.code, r"if \(-not \$hermes\) \{\s*throw")
        self.assertNotIn('Done.', self.code)

    def test_throws_on_nonzero_doctor_and_validate(self):
        for tool, fail in (('doctor', 'DOCTOR_FAIL'), ('validate', 'VALIDATE_FAIL')):
            block = self.code.split('& hermes plugins ' + tool, 1)[1].split('& hermes plugins', 1)[0]
            self.assertRegex(block, r"\$(\w+)Code = \$LASTEXITCODE")
            self.assertRegex(block, r"if \(\$\w+Code -ne 0\) \{ \$status\.\w+ = '" + fail + "'; throw")

    def test_emits_json_statuses(self):
        for token in ('DOCTOR_PASS', 'VALIDATE_PASS', 'NOT_RUN', 'ConvertTo-Json', 'SMOKE_STATUS.json'):
            self.assertIn(token, self.code)
        self.assertIn('Write-Status', self.code.split('finally', 1)[1])

    def test_never_enables_and_uses_disposable_home(self):
        lowered = self.code.lower()
        for bad in ('plugins enable', 'plugins install', 'allow_gateway_injection', 'gateway restart', 'stop-service'):
            self.assertNotIn(bad, lowered)
        self.assertIn('Assert-NotRealProfile $DisposableHome', self.code)
        self.assertIn('$env:HERMES_HOME = $DisposableHome', self.code)

    def test_doctor_needs_acknowledgement_and_warns_in_process(self):
        self.assertIn('[switch]$AcknowledgeDoctorExecutesAdapter', self.code)
        self.assertIn('in-process', self.code)
        self.assertLess(self.code.index('-not $AcknowledgeDoctorExecutesAdapter'), self.code.index('& hermes plugins doctor'))
        self.assertLess(self.code.index("'verify-adapter'"), self.code.index('& hermes plugins doctor'))
        self.assertLess(self.code.index('-not $ExpectedAdapterSha256'), self.code.index('& hermes plugins doctor'))

    def test_stage_one_is_not_run_not_failure(self):
        # R4: stopping at the acknowledgement check is intentional NOT_RUN, not a thrown failure.
        gate = self.code.split('if (-not $AcknowledgeDoctorExecutesAdapter', 1)[1].split('$status.stage', 1)[0]
        self.assertIn('return', gate)
        self.assertNotIn('throw', gate)
        self.assertIn('not an OS sandbox', self.code)
        self.assertIn('doctor.log', self.code)
        self.assertIn('validate.log', self.code)


class RuntimeEvidenceTests(Tmp):
    VERSION = '0.fixture'

    def evidence_for(self, name, *, version=VERSION, observed=None, disposable=True, results='PASS'):
        """SYNTHETIC evidence record for validator tests only."""
        src = self.copy_fixture(name='ev-src-' + name + str(len(list(self.tmp.iterdir()))))
        u = R.understand_command(src, 'commands/' + name + '.md', 'repair-fixture')
        target = HT.target_profile(version)
        binding = SV.expected_binding(u, target)
        return {
            'schema': SV.EVIDENCE_SCHEMA, 'capability_id': u['capability_id'], 'binding': binding,
            'environment': {'hermes_version': version, 'disposable_profile': disposable,
                            'production_credentials_present': False},
            'dimensions': {d: {'result': results} for d in SV.DIMENSIONS},
            'vectors': [{'raw_args': '42', 'observed_message_sha256': observed}],
            'recorded_by': 'SYNTHETIC-UNIT-TEST',
        }

    def expected_sha(self, name, raw_args):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        mod = SV.load_adapter(pkg)
        manifest, entry = SV._manifest_entry(pkg, name)
        return hashlib.sha256(mod.build_message(manifest, entry, raw_args).encode()).hexdigest()

    def test_forged_bound_evidence_is_self_reported_not_promoted(self):
        # v0.4.1 (review P0-2): reviewer's forgery reproduction. A well-formed,
        # correctly bound JSON file with all-PASS claims must NOT promote.
        ev = self.evidence_for('fix-issue', observed=self.expected_sha('fix-issue', '42'))
        b = self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev])
        p = by_name(b)['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'SELF_REPORTED_UNTRUSTED')
        self.assertEqual(p['outcome'], 'ADAPTED_STATICALLY')
        self.assertFalse(p['stages']['runtime_behavior_verified'])
        self.assertFalse(p['stages']['ready_for_installation'])
        self.assertEqual(b['runtime_verified_count'], 0)
        self.assertEqual(b['ready_for_installation_count'], 0)
        self.assertFalse(b['installation']['performed'])

    def test_evidence_cannot_claim_trusted_collector(self):
        ev = self.evidence_for('fix-issue', observed=self.expected_sha('fix-issue', '42'))
        ev['trust'] = 'TRUSTED_COLLECTOR'
        ev['status'] = 'PASS'
        ev['recorded_by'] = 'TRUSTED_COLLECTOR'
        p = by_name(self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev]))['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'SELF_REPORTED_UNTRUSTED')
        self.assertNotEqual(p['outcome'], 'ADAPTED_RUNTIME_VERIFIED')

    def test_no_evidence_path_reaches_runtime_verified(self):
        for name in ('fix-issue', 'summarize', 'plan-trip', 'migrate-component'):
            ev = self.evidence_for(name, observed=self.expected_sha(name, '42'))
            b = self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev])
            for p in b['passports']:
                self.assertNotIn(p['outcome'], {'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'})

    def test_promotion_gate_requires_trusted_collector(self):
        self.assertFalse(SV.runtime_trusted_pass({'status': 'PASS'}))
        self.assertFalse(SV.runtime_trusted_pass({'status': 'PASS', 'trust': 'SELF_REPORTED'}))
        self.assertFalse(SV.runtime_trusted_pass({'status': 'SELF_REPORTED_UNTRUSTED', 'trust': 'TRUSTED_COLLECTOR'}))

    def test_hash_mismatch_is_invalid(self):
        ev = self.evidence_for('fix-issue', observed='0' * 64)
        p = by_name(self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev]))['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'INVALID')
        self.assertEqual(p['outcome'], 'PARTIAL_REVIEW_REQUIRED')

    def test_failed_runtime_behavior_not_promoted(self):
        ev = self.evidence_for('fix-issue', observed=self.expected_sha('fix-issue', '42'), results='FAIL')
        p = by_name(self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev]))['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'FAIL')
        self.assertNotIn(p['outcome'], {'ADAPTED_RUNTIME_VERIFIED', 'DIRECT_EQUIVALENT_VERIFIED'})

    def test_stale_evidence_other_hermes_version(self):
        ev = self.evidence_for('fix-issue', version='0.other', observed=self.expected_sha('fix-issue', '42'))
        p = by_name(self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev]))['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'STALE')
        self.assertEqual(p['outcome'], 'ADAPTED_STATICALLY')

    def test_unknown_installed_version_is_stale(self):
        ev = self.evidence_for('fix-issue', observed=self.expected_sha('fix-issue', '42'))
        p = by_name(self.repair(installed_hermes_version=None, runtime_evidence=[ev]))['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'STALE')

    def test_non_disposable_profile_rejected(self):
        ev = self.evidence_for('fix-issue', observed=self.expected_sha('fix-issue', '42'), disposable=False)
        p = by_name(self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev]))['fix-issue']
        self.assertEqual(p['verification']['runtime_status'], 'INVALID')

    def test_runtime_pass_cannot_override_partial_conversion(self):
        ev = self.evidence_for('pr-summary', observed=self.expected_sha('pr-summary', '42'))
        p = by_name(self.repair(installed_hermes_version=self.VERSION, runtime_evidence=[ev]))['pr-summary']
        self.assertEqual(p['verification']['runtime_status'], 'SELF_REPORTED_UNTRUSTED')
        self.assertEqual(p['outcome'], 'PARTIAL_REVIEW_REQUIRED')
        self.assertFalse(p['stages']['ready_for_installation'])


class ReconciliationTests(Tmp):
    def snapshot(self, src, **kw):
        b = R.repair_plugin(str(src), str(self.tmp / ('o' + str(len(list(self.tmp.iterdir()))))), **kw)
        return b['snapshot']

    def test_rev_a_to_rev_b_impact(self):
        snap = self.snapshot(self.copy_fixture(REV_A, 'a'), source_commit='1' * 40)
        impact = U.reconcile(snap, str(self.copy_fixture(REV_B, 'b')), new_source_commit='2' * 40)
        rows = {r['capability_id'].rsplit(':', 1)[-1]: r for r in impact['capabilities']}
        self.assertEqual({k: v['change'] for k, v in rows.items()},
                         {'alpha': 'UNCHANGED', 'beta': 'MODIFIED', 'gamma': 'MODIFIED_FRONTMATTER_ONLY',
                          'delta': 'REMOVED', 'epsilon': 'ADDED'})
        self.assertEqual(impact['reusable_without_reanalysis'], ['claude-code:update-fixture:command:alpha'])
        self.assertEqual(rows['alpha']['carried_outcome'], 'ADAPTED_STATICALLY')
        self.assertTrue(rows['beta']['requires_reanalysis'])
        self.assertIsNone(rows['beta']['carried_outcome'])
        self.assertEqual(rows['delta']['affected_adapter'], 'delta')
        self.assertTrue(any('byte-identical' in x for x in rows['alpha']['reasons']))
        self.assertEqual(impact['runtime_verified_after_update'], [])
        self.assertEqual(impact['model_calls'], 0)

    def test_identical_revision_is_reusable(self):
        snap = self.snapshot(self.copy_fixture(REV_A, 'a'), source_commit='1' * 40)
        impact = U.reconcile(snap, str(self.copy_fixture(REV_A, 'a2')), new_source_commit='1' * 40)
        self.assertEqual(impact['summary'], {'UNCHANGED': 4})
        self.assertEqual(impact['requires_reanalysis'], [])
        self.assertEqual(impact['requires_static_reverification'], [])

    def _with_runtime_pass(self, snap):
        snap = copy.deepcopy(snap)
        for c in snap['capabilities']:  # SYNTHETIC prior runtime status for invalidation logic only
            c['runtime_status'] = 'PASS'
            c['outcome'] = 'ADAPTED_RUNTIME_VERIFIED'
        return snap

    def test_hermes_version_change_invalidates_runtime_evidence(self):
        snap = self._with_runtime_pass(self.snapshot(self.copy_fixture(REV_A, 'a'), installed_hermes_version='1.0'))
        impact = U.reconcile(snap, str(self.copy_fixture(REV_A, 'a2')), installed_hermes_version='1.1')
        for r in impact['capabilities']:
            self.assertEqual(r['runtime_evidence'], 'INVALIDATED')
            self.assertEqual(r['carried_outcome'], 'ADAPTED_STATICALLY')
            self.assertTrue(r['requires_runtime_reverification'])

    def test_unchanged_everything_snapshot_runtime_claim_stays_untrusted(self):
        # v0.4.1: a snapshot is self-written JSON; its runtime PASS is never carried forward as verified.
        snap = self._with_runtime_pass(self.snapshot(self.copy_fixture(REV_A, 'a'), installed_hermes_version='1.0'))
        impact = U.reconcile(snap, str(self.copy_fixture(REV_A, 'a2')), installed_hermes_version='1.0')
        self.assertEqual(impact['runtime_verified_after_update'], [])
        self.assertEqual(len(impact['runtime_claims_still_bound_untrusted']), 4)
        for r in impact['capabilities']:
            self.assertEqual(r['runtime_evidence'], 'STILL_BOUND_UNTRUSTED_SNAPSHOT')
            self.assertEqual(r['carried_outcome'], 'ADAPTED_STATICALLY')
            self.assertTrue(r['requires_runtime_reverification'])

    def test_unknown_version_invalidates(self):
        snap = self._with_runtime_pass(self.snapshot(self.copy_fixture(REV_A, 'a'), installed_hermes_version='1.0'))
        impact = U.reconcile(snap, str(self.copy_fixture(REV_A, 'a2')), installed_hermes_version=None)
        self.assertEqual(impact['runtime_verified_after_update'], [])

    def test_engine_change_requires_static_reverification(self):
        snap = self.snapshot(self.copy_fixture(REV_A, 'a'))
        snap['engine']['renderer_sha256'] = 'f' * 64
        impact = U.reconcile(snap, str(self.copy_fixture(REV_A, 'a2')))
        self.assertEqual(len(impact['requires_static_reverification']), 4)
        self.assertEqual(impact['engine']['changed_fields'], ['renderer_sha256'])

    def test_non_command_file_change_requires_static_reverification(self):
        snap = self.snapshot(self.copy_fixture(REV_A, 'a'))
        b = self.copy_fixture(REV_A, 'a2')
        (b / 'settings.json').write_text('{"permissions": {"allow": ["Bash(ls *)"]}}', encoding='utf-8')
        impact = U.reconcile(snap, str(b))
        self.assertTrue(impact['source']['tree_changed'])
        self.assertEqual(len(impact['requires_static_reverification']), 4)

    def test_settings_change_alongside_command_change_still_reverifies_unchanged(self):
        snap = self.snapshot(self.copy_fixture(REV_A, 'a'))
        b = self.copy_fixture(REV_B, 'b')
        (b / 'settings.json').write_text('{"permissions": {"deny": ["Bash(rm *)"]}}', encoding='utf-8')
        impact = U.reconcile(snap, str(b))
        alpha = [r for r in impact['capabilities'] if r['capability_id'].endswith(':alpha')][0]
        self.assertEqual(alpha['change'], 'UNCHANGED')
        self.assertTrue(alpha['requires_static_reverification'])
        self.assertIsNone(alpha['carried_outcome'])
        self.assertEqual(impact['reusable_without_reanalysis'], [])

    def test_rejects_wrong_plugin_or_schema(self):
        snap = self.snapshot(self.copy_fixture(REV_A, 'a'))
        with self.assertRaisesRegex(CORE.PortError, 'different plugin'):
            U.reconcile(snap, str(self.copy_fixture(FIXTURE, 'other')))
        with self.assertRaisesRegex(CORE.PortError, 'Snapshot v2'):
            U.reconcile({'schema': 'x'}, str(self.copy_fixture(REV_A, 'a3')))


class ReportingTests(Tmp):
    def test_importer_comparison_is_documentation_only(self):
        src = self.copy_fixture()
        b = R.repair_plugin(str(src), str(self.tmp / 'o'))
        cmp = json.loads((Path(b['output_path']) / 'OFFICIAL_IMPORTER_COMPARISON.json').read_text(encoding='utf-8'))
        self.assertEqual(cmp['comparison_type'], 'DOCUMENTATION_BASED')
        self.assertFalse(cmp['official_importer_executed'])
        self.assertEqual(cmp['metrics']['commands_runtime_verified'], 0)
        self.assertTrue(cmp['benchmark_claims'].startswith('NONE'))
        self.assertIn('Skipped', cmp['rows'][0]['official_documented'])

    def test_workshop_never_celebrates_unverified(self):
        src = self.copy_fixture()
        b = R.repair_plugin(str(src), str(self.tmp / 'o'))
        view = W.render_workshop(b)
        self.assertNotIn('[OK runtime]', view)
        self.assertIn('RUNTIME verified: 0/10', view)
        self.assertIn('[BLOCKED]', view)

    def test_passport_markdown_and_snapshot_contain_no_source_body(self):
        src = self.copy_fixture()
        b = R.repair_plugin(str(src), str(self.tmp / 'o'))
        snap = (Path(b['output_path']) / 'UNDERSTANDING_SNAPSHOT_V2.json').read_text(encoding='utf-8')
        self.assertNotIn('coding standards', snap)
        self.assertNotIn('gh pr diff', snap)


class IntegrationTests(Tmp):
    def test_stage_defuses_shell_in_staged_skill(self):
        src = self.copy_fixture()
        res = CORE.stage(str(src), str(self.tmp / 'staged'), approved=True, allow_partial=True)
        text = (Path(res['staged_path']) / 'skills' / 'pr-summary' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIsNone(CC.HERMES_INLINE_SHELL.search(text))
        self.assertIn(CC.SHELL_DISABLED_PLACEHOLDER, text)

    def _run(self, src_dir, run_id, commit):
        runs = self.tmp / 'runs'
        run = runs / run_id
        src = run / 'sources' / 'pinned'
        src.parent.mkdir(parents=True)
        shutil.copytree(src_dir, src)
        staged = CORE.stage(str(src), str(run / 'staged'), approved=True, allow_partial=True)
        report = {'run_id': run_id, 'run_dir': str(run), 'status': 'VALIDATED_PARTIAL_REVIEW_REQUIRED',
                  'url': 'https://github.com/example/repo', 'fetch': {'source_path': str(src), 'commit_sha': commit},
                  'analysis': CORE.analyze(str(src)), 'stage': staged, 'validation': {'ok': True}, 'installed': False}
        (run / 'RUN_REPORT.json').write_text(json.dumps(report), encoding='utf-8')
        return runs

    def test_repair_and_reconcile_existing_runs(self):
        runs = self._run(REV_A, 'aaaaaaaaaaaa', '1' * 40)
        self._run(REV_B, 'bbbbbbbbbbbb', '2' * 40)
        out = FLOW.repair_existing_run('aaaaaaaaaaaa', work_root=runs, installed_version=None)
        self.assertEqual(out['run_status_unchanged'], 'VALIDATED_PARTIAL_REVIEW_REQUIRED')
        self.assertFalse(out['installed'])
        rep = json.loads((runs / 'aaaaaaaaaaaa' / 'RUN_REPORT.json').read_text(encoding='utf-8'))
        self.assertEqual(rep['status'], 'VALIDATED_PARTIAL_REVIEW_REQUIRED')
        imp = FLOW.reconcile_runs('aaaaaaaaaaaa', 'bbbbbbbbbbbb', work_root=runs, installed_version=None)
        self.assertEqual(imp['summary']['REMOVED'], 1)
        self.assertTrue((runs / 'bbbbbbbbbbbb' / 'UPDATE_IMPACT.json').is_file())
        with self.assertRaisesRegex(CORE.PortError, 'no repair'):
            FLOW.reconcile_runs('bbbbbbbbbbbb', 'aaaaaaaaaaaa', work_root=runs, installed_version=None)

    def test_repair_refuses_tampered_pinned_source(self):
        runs = self._run(REV_A, 'cccccccccccc', '1' * 40)
        (runs / 'cccccccccccc' / 'sources' / 'pinned' / 'commands' / 'alpha.md').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(CORE.PortError, 'fingerprint'):
            FLOW.repair_existing_run('cccccccccccc', work_root=runs, installed_version=None)

    def test_install_still_blocked_after_repair(self):
        runs = self._run(REV_A, 'dddddddddddd', '1' * 40)
        FLOW.repair_existing_run('dddddddddddd', work_root=runs, installed_version=None)
        with self.assertRaisesRegex(CORE.PortError, 'fully validated'):
            FLOW.install_validated('dddddddddddd', work_root=runs)


if __name__ == '__main__':
    unittest.main()
