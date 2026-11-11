"""Synthetic contract fixtures: NOT a claim of verified Hermes tool parity."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('equivalence_v034_test_pkg', ROOT/'__init__.py',
                                               submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from equivalence_v034_test_pkg import equivalence_router as EQ, port_flow as FLOW, port_core as CORE

SOURCE_SHA = 'abcdef0123456789abcdef0123456789abcdef01'
HOST_VERSION = '0.test-fixture'

def sha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fake_mapping(source_text):
    # The evidence fields below are TEST-ONLY values. None ship in production.
    return {
        'id':'fixture-read-alias', 'source_profile':'claude-code',
        'source_tool':'FixtureRead', 'target_tool':'fixture_read',
        'syntax':'exact_tool_label_line_v1',
        'semantics':{
            'arguments':'one exact path string', 'returns':'same file bytes',
            'side_effects':'none', 'permissions':'read-only scope',
            'approval':'same policy', 'failure':'same exceptions',
            'state':'none'},
        'evidence':{
            'source_version':'fixture-v1','target_version':HOST_VERSION,
            'source_commit_sha':SOURCE_SHA,'source_command_sha256':sha(source_text),
            'source_contract_sha256':sha('fixture-source-contract'),
            'target_contract_sha256':sha('fixture-target-contract'),
            'test_evidence_sha256':sha('fixture-test-record'),
            'test_suite':'tests/test_equivalence_router.py',
            'reviewed_by':'offline-fixture-only','result':'PASS'}
    }


class EquivalenceRouterTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name)
        self.src=self.base/'source'; (self.src/'commands').mkdir(parents=True)
        self.pkg=self.base/'staged'; (self.pkg/'skills'/'demo').mkdir(parents=True)
        self.source_text='# Demo\n\nTool: FixtureRead\n```text\nTool: FixtureRead\n```\n'
        (self.src/'commands'/'demo.md').write_text(self.source_text,encoding='utf-8')
        self.skill=self.pkg/'skills'/'demo'/'SKILL.md'
        self.skill.write_text('---\nname: demo\n---\n\n'+self.source_text,encoding='utf-8')
        self.plan={'profile':'claude-code','commands':[{'name':'demo','path':'commands\\demo.md'}]}
        self.mapping=fake_mapping(self.source_text)
        self.regfile=self.base/'registry.json'
        self.save_registry([self.mapping])

    def save_registry(self,items):
        self.regfile.write_text(json.dumps({'schema_version':1,'mappings':items}),encoding='utf-8')

    def route(self, registry=None, **kw):
        return EQ.classify(self.pkg,self.plan,self.src,
                           registry=registry if registry is not None else EQ.load_registry(self.regfile),
                           source_commit=kw.get('source_commit',SOURCE_SHA),
                           host_version=kw.get('host_version',HOST_VERSION))

    def test_bundled_registry_is_deliberately_empty(self):
        default=EQ.load_registry()
        self.assertEqual(default['mapping_count'],0)
        report=self.route(registry=default)
        self.assertEqual(report['direct_bridge_calls'],0)
        self.assertEqual(report['commands'][0]['lane'],'AI_INTEGRATION')
        self.assertIsNone(report['estimated_savings_usd'])

    def test_trusted_fixture_exact_label_direct_no_model(self):
        reg=EQ.load_registry(self.regfile)
        result=self.route(registry=reg)
        self.assertEqual(result['direct_bridge_calls'],1)
        self.assertEqual(result['requires_integration_checks'],0)
        self.assertEqual(result['commands'][0]['lane'],'DIRECT_BRIDGE_ONLY')
        class NoModel:
            def complete_structured(self, **kwargs):
                raise AssertionError('LLM must not be called for direct-only alias')
        context=SimpleNamespace(llm=NoModel())
        state=self.base/'progress.json'
        summary=FLOW._llm_rewrite_commands(context,self.pkg,self.plan,
            state_path=state,cost_route=result,mapping_registry=reg)
        out=self.skill.read_text(encoding='utf-8')
        self.assertEqual(out.count('Tool: fixture_read'),1)
        self.assertEqual(out.count('Tool: FixtureRead'),1) # fenced reference intact
        self.assertEqual(summary['completed_commands'],['demo'])
        self.assertEqual(len(summary['direct_bridged_commands']),1)
        self.assertTrue(summary['needs_manual_review'])  # no whole-workflow parity claim
        self.assertFalse(summary['model_failed'])
        self.assertEqual(json.loads(state.read_text())['count'],1)

    def test_mapping_must_match_exact_source_commit(self):
        for commit in ('0'*40,None):
            with self.subTest(commit=commit):
                r=self.route(source_commit=commit)
                self.assertEqual(r['direct_bridge_calls'],0)
                self.assertEqual(r['commands'][0]['lane'],'AI_INTEGRATION')

    def test_mapping_must_match_exact_host_version(self):
        r=self.route(host_version='0.newer')
        self.assertEqual(r['direct_bridge_calls'],0)

    def test_mapping_must_match_exact_source_document_hash(self):
        (self.src/'commands'/'demo.md').write_text(self.source_text+'\nchanged\n',encoding='utf-8')
        self.assertEqual(self.route()['direct_bridge_calls'],0)

    def test_tool_name_in_prose_does_not_match_alias(self):
        self.source_text='Mention FixtureRead in prose.\n'
        (self.src/'commands'/'demo.md').write_text(self.source_text)
        self.skill.write_text(self.source_text)
        self.save_registry([fake_mapping(self.source_text)])
        self.assertEqual(self.route()['direct_bridge_calls'],0)

    def test_unmapped_and_foreign_runtime_features_escalate(self):
        text='Tool: FixtureRead\nTool: UnknownTool\n$ARGUMENTS\nTask:\n'
        (self.src/'commands'/'demo.md').write_text(text)
        self.skill.write_text(text)
        self.save_registry([fake_mapping(text)])
        r=self.route()
        self.assertEqual(r['direct_bridge_calls'],1)
        self.assertEqual(r['commands'][0]['lane'],'MIXED_DIRECT_AND_AI')
        self.assertGreaterEqual(r['requires_integration_checks'],3)

    def test_mixed_verified_candidate_keeps_ai_integration(self):
        text='Tool: FixtureRead\n$ARGUMENTS\n'
        (self.src/'commands'/'demo.md').write_text(text)
        self.skill.write_text('---\nname: demo\n---\n\n' + text)
        self.save_registry([fake_mapping(text)])
        reg=EQ.load_registry(self.regfile)
        route=self.route(registry=reg)
        self.assertEqual(route['commands'][0]['lane'],'MIXED_DIRECT_AND_AI')
        calls=[]
        class FakeModel:
            def complete_structured(self,**kwargs):
                calls.append(kwargs)
                return SimpleNamespace(parsed={'body':'# Valid integration\n\n'
                    'This command is still under review for argument semantics.',
                    'limitations':['caller argument binding unverified'],
                    'requires_manual_review':True})
        result=FLOW._llm_rewrite_commands(SimpleNamespace(llm=FakeModel()),
            self.pkg,self.plan,cost_route=route,mapping_registry=reg)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['direct_bridged_commands'],[])
        self.assertTrue(result['needs_manual_review'])

    def test_direct_rewrite_refuses_missing_anchor(self):
        result=self.route()
        self.skill.write_text('# different\n')
        with self.assertRaisesRegex(ValueError,'anchor mismatch'):
            EQ.direct_rewrite(self.skill.read_text(), result['commands'][0],
                              trusted_registry=EQ.load_registry(self.regfile))

    def test_untrusted_registry_cannot_inject_executable_transform(self):
        x=json.loads(json.dumps(self.mapping));x['syntax']='python:eval(raw)'
        self.save_registry([x])
        with self.assertRaisesRegex(ValueError,'Unsupported mapping syntax'):
            EQ.load_registry(self.regfile)

    def test_pass_required_and_contract_sha_validation(self):
        x=json.loads(json.dumps(self.mapping));x['evidence']['result']='MAYBE'
        self.save_registry([x])
        with self.assertRaisesRegex(ValueError,'PASS'):
            EQ.load_registry(self.regfile)
        x['evidence']['result']='PASS';x['evidence']['test_evidence_sha256']='invalid'
        self.save_registry([x])
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            EQ.load_registry(self.regfile)

    def test_duplicate_alias_fails_closed(self):
        x=json.loads(json.dumps(self.mapping));x['id']='second-alias'
        self.save_registry([self.mapping,x])
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            EQ.load_registry(self.regfile)

    def test_mapping_sha_changes_restrict_resume(self):
        self.assertNotEqual(EQ.load_registry(self.regfile)['sha256'],EQ.load_registry()['sha256'])

    def test_route_existing_run_no_model_and_does_not_promote(self):
        root=self.base/'runs';rid='abcdef123456';run=root/rid;run.mkdir(parents=True)
        import shutil
        src=run/'sources'/'pinned';src.parent.mkdir();shutil.copytree(ROOT/'examples'/'claude-sample',src)
        plan=CORE.analyze(str(src))
        stage=CORE.stage(str(src),str(run/'staged'),approved=True,allow_partial=True)
        state={'run_id':rid,'run_dir':str(run),'url':'https://github.com/test/dummy',
               'status':'VALIDATED_PARTIAL_REVIEW_REQUIRED','phase':'validate',
               'fetch':{'source_path':str(src),'commit_sha':SOURCE_SHA},
               'analysis':plan,'stage':stage,'validation':{'ok':True},'installed':False}
        (run/'RUN_REPORT.json').write_text(json.dumps(state),encoding='utf-8')
        out=FLOW.route_existing_run(rid,work_root=root)
        self.assertEqual(out['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
        self.assertEqual(out['direct_bridge_calls'],0)
        self.assertTrue((run/'COST_ROUTE.json').is_file())
        self.assertFalse(json.loads((run/'RUN_REPORT.json').read_text())['installed'])
        self.assertIn('no model calls',out['note'])
        with patch.object(FLOW,'_work_root',return_value=root):
            raw=json.loads(FLOW.command(object(), 'route '+rid))
            self.assertEqual(raw['run_id'],rid)

if __name__=='__main__':unittest.main()
