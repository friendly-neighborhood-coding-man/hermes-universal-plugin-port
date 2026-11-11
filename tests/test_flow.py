"""V0.2 native command orchestration tests; no network, model or Hermes calls."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from email.message import Message

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('universal_port_test_pkg', ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
PKG=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=PKG
SPEC.loader.exec_module(PKG)
FLOW=sys.modules.get('universal_port_test_pkg.port_flow')
if FLOW is None:
    from universal_port_test_pkg import port_flow as FLOW

class Model:
    def __init__(self):
        self.calls=[]
    def complete_structured(self,**kwargs):
        self.calls.append(kwargs)
        if kwargs.get('schema_name')=='universal_port.review':
            return SimpleNamespace(parsed={'risks': [], 'compatibility_notes':['Review is advisory only']},model='test-model',provider='test',usage={'tokens':99})
        return SimpleNamespace(parsed={'body':'# Adapted workflow\n\nRead the repository and propose safe changes, after user approval.', 'limitations':[], 'requires_manual_review':False},model='test-model',provider='test',usage={})

class Ctx:
    def __init__(self):
        self.llm=Model()
        self.tools=[]
        self.commands=[]
        self.dispatches=[]
    def register_command(self,*args,**kw):self.commands.append((args,kw))
    def register_tool(self,**kw):self.tools.append(kw)
    def dispatch_tool(self,name,args):
        self.dispatches.append((name,args))
        return 'Terminal tool dispatched; not independently verified'

class NativeFlowTests(unittest.TestCase):
    def test_native_command_registered_alongside_three_tools(self):
        ctx=Ctx();PKG.register(ctx)
        self.assertEqual(len(ctx.tools),4)
        self.assertEqual(len(ctx.commands),2)
        self.assertEqual(ctx.commands[0][0][0],'universal-port')
        self.assertEqual(ctx.commands[1][0][0],'uvp')
        self.assertIn('Usage',ctx.commands[0][1]['handler'](''))
        self.assertIn('Usage',ctx.commands[1][1]['handler'](''))
        self.assertEqual(ctx.tools[-1]['name'], 'uvp_route')

    def test_wrong_url_does_not_fetch_or_install(self):
        ctx=Ctx()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(Exception,'exactly one'):
                FLOW.run_url(ctx,'https://example.com/foo',work_root=Path(temp))
        self.assertFalse(ctx.dispatches)
        self.assertFalse(ctx.llm.calls)

    def test_codex_fixture_stages_with_model_and_holds_partial(self):
        ctx=Ctx()
        source=ROOT/'examples'/'codex-sample'
        with tempfile.TemporaryDirectory() as td:
            with patch.object(FLOW,'fetch_github', return_value={'source_path':str(source),'commit_sha':'a'*40}), patch.object(FLOW,'_check_hermes',return_value={'ok':True,'doctor':{'ok':True},'validate':{'ok':True}}):
                r=FLOW.run_url(ctx,'https://github.com/example/codex-sample',work_root=Path(td))
            self.assertTrue(r['ok'])
            self.assertEqual(r['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertFalse(r['installed'])
            self.assertEqual(len(ctx.llm.calls),2)
            self.assertFalse(ctx.dispatches)
            p=Path(r['stage']['staged_path'])
            self.assertTrue((p/'skills/describe/ORIGINAL_COMMAND.md').exists())
            self.assertIn('Adapted workflow',(p/'skills/describe/SKILL.md').read_text())
            self.assertTrue((Path(r['run_dir'])/'RUN_REPORT.json').is_file())

    def test_skill_only_can_dispatch_explicit_install_after_verification(self):
        ctx=Ctx()
        with tempfile.TemporaryDirectory() as td:
            t=Path(td)
            source=t/'source'
            (source/'.codex-plugin').mkdir(parents=True)
            (source/'.codex-plugin'/'plugin.json').write_text('{"name":"only-skill"}')
            (source/'skills'/'good').mkdir(parents=True)
            (source/'skills'/'good'/'SKILL.md').write_text('---\nname: good\ndescription: Good\n---\nUse a checklist.')
            with patch.dict('os.environ', {'HERMES_HOME': str(t/'hermes-profile')}), patch.object(FLOW,'fetch_github',return_value={'source_path':str(source),'commit_sha':'c'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                r=FLOW.run_url(ctx,'https://github.com/example/only-skill',work_root=t/'runs')
            self.assertEqual(r['status'],'VALIDATED_NOT_INSTALLED')
            self.assertFalse(r['installed'])
            with patch.dict('os.environ', {'HERMES_HOME': str(t/'hermes-profile')}):
                explicit = FLOW.install_validated(r['run_id'], work_root=t/'runs')
            self.assertEqual(explicit['status'], 'INSTALLED_RESTART_REQUIRED')
            self.assertEqual(len(ctx.llm.calls),1)
            self.assertFalse(ctx.dispatches)
            self.assertTrue((Path(explicit['destination'])/'plugin.json').is_file())

    def test_invalid_model_json_keeps_original_and_reports_partial_without_install(self):
        ctx = Ctx()
        source = ROOT / 'examples' / 'codex-sample'
        original_model = ctx.llm.complete_structured
        def malformed_once(**kwargs):
            if kwargs.get('schema_name') == 'universal_port.review':
                return original_model(**kwargs)
            return SimpleNamespace(parsed=None, content_type='text', text='broken json prefix',
                                   provider='opus-test', model='test-model')
        ctx.llm.complete_structured = malformed_once
        with tempfile.TemporaryDirectory() as td:
            with patch.object(FLOW, 'fetch_github', return_value={
                'source_path': str(source), 'commit_sha': 'a'*40,
            }), patch.object(FLOW, '_check_hermes', return_value={'ok': True}):
                result = FLOW.run_url(ctx, 'https://github.com/example/codex-sample', work_root=Path(td))
            self.assertEqual(result['status'], 'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertFalse(result['installed'])
            self.assertEqual(result['llm_adaptation']['count'], 0)
            self.assertEqual(result['llm_adaptation']['model_failed'][0]['reason'],
                             'INVALID_ADAPTATION_SCHEMA_OR_BODY')
            diagnostic = result['llm_adaptation']['model_failed'][0]['diagnostic']
            self.assertEqual(diagnostic['content_type'], 'text')
            self.assertEqual(diagnostic['parsed_type'], 'NoneType')
            self.assertNotIn('broken json prefix', json.dumps(result))
            pkg = Path(result['stage']['staged_path'])
            self.assertEqual((pkg/'skills/describe/SKILL.md').read_text(encoding='utf-8'),
                             (pkg/'skills/describe/ORIGINAL_COMMAND.md').read_text(encoding='utf-8'))
            self.assertFalse(ctx.dispatches)
            saved = json.loads((Path(result['run_dir'])/'RUN_REPORT.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['status'], 'VALIDATED_PARTIAL_REVIEW_REQUIRED')

    def test_invalid_model_reply_does_not_prevent_next_command_from_adapting(self):
        ctx = Ctx()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root/'two'
            (source/'.claude-plugin').mkdir(parents=True)
            (source/'.claude-plugin'/'plugin.json').write_text('{"name":"two"}', encoding='utf-8')
            (source/'commands').mkdir()
            for name in ('first', 'second'):
                (source/'commands'/f'{name}.md').write_text('Do a safe review of these files.\n', encoding='utf-8')
            calls = []
            real = ctx.llm.complete_structured
            def sometimes_invalid(**kwargs):
                if kwargs.get('schema_name') == 'universal_port.review':
                    return real(**kwargs)
                calls.append(kwargs)
                if len(calls) == 1:
                    return SimpleNamespace(parsed={'body': 99, 'limitations': [], 'requires_manual_review': False},
                                           content_type='json', text='{}')
                return real(**kwargs)
            ctx.llm.complete_structured = sometimes_invalid
            with patch.object(FLOW, 'fetch_github', return_value={
                'source_path': str(source), 'commit_sha': 'a'*40,
            }), patch.object(FLOW, '_check_hermes', return_value={'ok': True}):
                result = FLOW.run_url(ctx, 'https://github.com/example/two', work_root=root/'runs')
            self.assertEqual(result['status'], 'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertEqual(result['llm_adaptation']['count'], 1)
            self.assertEqual(len(result['llm_adaptation']['model_failed']), 1)
            self.assertFalse(ctx.dispatches)

    def test_schema_value_error_does_not_erase_staged_command(self):
        ctx = Ctx()
        original = ctx.llm.complete_structured
        def schema_exception(**kwargs):
            if kwargs.get('schema_name') == 'universal_port.review':
                return original(**kwargs)
            raise ValueError('sample schema mismatch; should not log this')
        ctx.llm.complete_structured = schema_exception
        with tempfile.TemporaryDirectory() as td:
            with patch.object(FLOW, 'fetch_github', return_value={
                'source_path': str(ROOT/'examples'/'codex-sample'), 'commit_sha': 'a'*40,
            }), patch.object(FLOW, '_check_hermes', return_value={'ok': True}):
                r = FLOW.run_url(ctx, 'https://github.com/example/codex-sample', work_root=Path(td))
            self.assertEqual(r['status'], 'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertEqual(r['llm_adaptation']['model_failed'][0]['reason'], 'STRUCTURED_OUTPUT_VALUE_ERROR')
            self.assertNotIn('sample schema mismatch', json.dumps(r))

    def test_openclaw_is_stopped_before_executing_any_code(self):
        ctx=Ctx()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(ROOT/'examples'/'openclaw-sample'),'commit_sha':'a'*40}):
                result=FLOW.run_url(ctx,'https://github.com/example/openclaw',work_root=Path(td))
            self.assertEqual(result['status'],'FOREIGN_RUNTIME_APPROVAL_REQUIRED')
            self.assertFalse(ctx.llm.calls)
            self.assertFalse(ctx.dispatches)

    def test_http_403_fetch_preserves_diagnostics_and_terminal_report(self):
        ctx = Ctx()
        headers = Message()
        headers['X-RateLimit-Remaining'] = '55'
        headers['X-GitHub-Request-Id'] = 'EXAMPLE:123'
        exc = HTTPError('https://api.github.com/repos/owner/repo/contents/test?ref=secret', 403, 'Forbidden', headers, None)
        with tempfile.TemporaryDirectory() as td, patch.object(FLOW, 'fetch_github', side_effect=exc):
            r = FLOW.run_url(ctx, 'https://github.com/owner/repo', work_root=Path(td))
            saved = json.loads((Path(r['run_dir'])/'RUN_REPORT.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['status'], 'GITHUB_HTTP_ERROR')
            self.assertEqual(saved['http']['status_code'], 403)
            self.assertEqual(saved['http']['rate_limit_remaining'], '55')
            self.assertNotIn('secret', json.dumps(saved))
            self.assertEqual(saved['phase'], 'fetch')
            self.assertFalse(ctx.llm.calls)

    def test_http_429_uses_server_headers_not_current_rate_probe(self):
        ctx = Ctx()
        headers = Message()
        headers['Retry-After'] = '30'
        exc = HTTPError('https://api.github.com/repos/owner/repo', 429, 'Too Many Requests', headers, None)
        with tempfile.TemporaryDirectory() as td, patch.object(FLOW, 'fetch_github', side_effect=exc):
            r = FLOW.run_url(ctx, 'https://github.com/owner/repo', work_root=Path(td))
            self.assertEqual(r['http']['retry_after'], '30')
            self.assertEqual(r['status'], 'GITHUB_HTTP_ERROR')

    def test_unexpected_fetch_exception_no_longer_leaves_started(self):
        ctx = Ctx()
        with tempfile.TemporaryDirectory() as td, patch.object(FLOW, 'fetch_github', side_effect=RuntimeError('Do not record sensitive text')):
            r = FLOW.run_url(ctx, 'https://github.com/owner/repo', work_root=Path(td))
            saved = json.loads((Path(r['run_dir'])/'RUN_REPORT.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['status'], 'RUN_ERROR')
            self.assertEqual(saved['reason'], 'RuntimeError during fetch')
            self.assertNotIn('sensitive text', json.dumps(saved))

    def test_persistent_checkpoint_exists_during_fetch(self):
        ctx=Ctx()
        observed={}
        def interrupted_fetch(url, output_dir, approved):
            folder=Path(output_dir).parent
            report=json.loads((folder/'RUN_REPORT.json').read_text(encoding='utf-8'))
            observed.update(report)
            raise RuntimeError('simulated fetch interruption')
        with tempfile.TemporaryDirectory() as td, patch.object(FLOW, 'fetch_github', side_effect=interrupted_fetch):
            result=FLOW.run_url(ctx, 'https://github.com/example/repo', work_root=Path(td))
            self.assertEqual(observed['phase'], 'fetch')
            self.assertEqual(observed['status'], 'IN_PROGRESS')
            self.assertIn('updated_utc', observed)
            self.assertEqual(result['status'], 'RUN_ERROR')

    def test_persistent_checkpoint_before_model_call(self):
        ctx=Ctx()
        source=ROOT/'examples'/'codex-sample'
        snapshot={}
        def stalled_model(**kwargs):
            # The model can fail or be interrupted; checkpoint must exist first.
            runs=list(work_root.iterdir())
            report=json.loads((runs[0]/'RUN_REPORT.json').read_text(encoding='utf-8'))
            snapshot.update(report)
            raise RuntimeError('simulated model failure')
        with tempfile.TemporaryDirectory() as td:
            work_root=Path(td)/'runs'
            ctx.llm.complete_structured=stalled_model
            with patch.object(FLOW, 'fetch_github', return_value={'source_path':str(source),'commit_sha':'a'*40}):
                result=FLOW.run_url(ctx,'https://github.com/example/repo',work_root=work_root)
            self.assertEqual(snapshot['phase'], 'llm_review')
            self.assertEqual(snapshot['status'], 'IN_PROGRESS')
            self.assertEqual(result['status'], 'MODEL_ADAPTATION_FAILED')

    def test_hermes_validation_failure_blocks_install(self):
        ctx=Ctx()
        source=ROOT/'examples'/'claude-sample'
        with tempfile.TemporaryDirectory() as td:
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(source),'commit_sha':'a'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':False,'doctor':{'ok':False}}):
                result=FLOW.run_url(ctx,'https://github.com/example/claude',work_root=Path(td))
            self.assertEqual(result['status'],'VALIDATION_BLOCKED')
            self.assertFalse(ctx.dispatches)

if __name__=='__main__':unittest.main()
