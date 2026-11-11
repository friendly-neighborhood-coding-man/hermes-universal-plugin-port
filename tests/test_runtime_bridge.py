"""Off-line tests of Hermes v0.3.3 native bridge. No real model, network, install or git commands."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('universal_port_bridge_testpkg', ROOT/'__init__.py', submodule_search_locations=[str(ROOT)])
PKG=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=PKG
SPEC.loader.exec_module(PKG)
from universal_port_bridge_testpkg import port_flow as FLOW, runtime_bridge as BR, port_core as CORE, host_capabilities as H

class Context:
    def __init__(self,choice='run', result='{"results":[{"status":"completed","summary":"Review done"}]}'):
        self.choice=choice;self.result=result;self.calls=[];self.choices=[]
    def ask_choice(self,q,options):
        self.choices.append((q,options));return self.choice
    def dispatch_tool(self,name,args):
        self.calls.append((name,args))
        if isinstance(self.result,Exception):raise self.result
        return self.result

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'runs';self.root.mkdir()
        self.run_id='abcdef123456'
        self.run=self.root/self.run_id;self.run.mkdir()
        self.src=self.run/'sources'/'pinned';self.src.parent.mkdir()
        import shutil
        shutil.copytree(ROOT/'examples'/'claude-sample',self.src)
        self.pkg=self.run/'staged'/'sample';self.pkg.parent.mkdir()
        result=CORE.stage(str(self.src),str(self.pkg.parent),approved=True,allow_partial=True)
        self.pkg=Path(result['staged_path'])
        H.preserve_agent_references(self.pkg,self.src)
        self.plan=CORE.analyze(str(self.src))
        self.report={'run_id':self.run_id,'run_dir':str(self.run),
            'status':'VALIDATED_PARTIAL_REVIEW_REQUIRED','phase':'validate',
            'fetch':{'source_path':str(self.src),'commit_sha':'a'*40},
            'analysis':self.plan,'stage':{'staged_path':str(self.pkg)},
            'validation':{'ok':True},'installed':False}
        (self.run/'RUN_REPORT.json').write_text(json.dumps(self.report),encoding='utf-8')
        self.request='Analyze this provided code without changes.'

    def test_live_delegate_needs_extra_explicit_risk_acknowledgement(self):
        c=Context()
        with self.assertRaisesRegex(Exception,'allow-inherited-tools'):
            BR.run_agent(c,self.run_id,'reviewer',self.request,work_root=self.root)
        self.assertEqual(c.calls,[])

    def test_preview_no_dispatch_and_identity(self):
        out=BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)
        self.assertEqual(out['agent_name'],'reviewer')
        self.assertEqual(out['source_commit'],'a'*40)
        self.assertEqual(out['actual_toolset_policy'],'INHERITED_FROM_PARENT')
        self.assertTrue(out['requires_user_choice'])
        self.assertFalse((self.run/'BRIDGE_EVIDENCE').exists())

    def test_exact_raw_arguments_preserved(self):
        r=BR.parse_invocation(self.run_id,'check','main --draft-pr --title "fix: foo bar"',work_root=self.root)
        self.assertEqual(r['argv'],['main','--draft-pr','--title','fix: foo bar'])
        self.assertEqual(r['flags'],['--draft-pr','--title'])
        self.assertFalse(r['executed'])
        self.assertIn('main --draft-pr',r['bound_to_hermes_skill'])

    def test_malformed_arguments_refused(self):
        with self.assertRaisesRegex(Exception,'quotes'):
            BR.parse_invocation(self.run_id,'check','"',work_root=self.root)
        with self.assertRaisesRegex(Exception,'Unknown command'):
            BR.parse_invocation(self.run_id,'nonexistent','a',work_root=self.root)
        with self.assertRaisesRegex(Exception,'control characters'):
            BR.parse_invocation(self.run_id,'check','a\x00b',work_root=self.root)

    def test_bridge_evidence_without_dispatch(self):
        summary=BR.bridge_evidence(self.run_id,work_root=self.root)
        self.assertFalse(summary['semantic_parity_verified'])
        self.assertEqual(summary['events'],[])

    def test_refusal_never_calls_model_or_creates_approval_file(self):
        c=Context(choice='cancel')
        result=BR.run_agent(c,self.run_id,'reviewer',self.request,allow_inherited_tools=True,work_root=self.root)
        self.assertEqual(result['status'],'DENIED_OR_UNAVAILABLE')
        self.assertFalse(result['dispatched']);self.assertEqual(c.calls,[])
        self.assertFalse((self.run/'BRIDGE_EVIDENCE').exists())

    def test_unavailable_choice_fail_closed(self):
        c=type('ContextWithoutInteractivePicker',(),{
            'dispatch_tool':lambda self,*args: self.fail_test()})()
        result=BR.run_agent(c,self.run_id,'reviewer',self.request,allow_inherited_tools=True,work_root=self.root)
        self.assertFalse(result['dispatched'])

    def test_approved_calls_one_real_delegate_task_and_writes_hash_evidence(self):
        c=Context()
        r=BR.run_agent(c,self.run_id,'reviewer',self.request,allow_inherited_tools=True,work_root=self.root)
        self.assertEqual(r['status'],'DISPATCH_RETURNED');self.assertEqual(len(c.calls),1)
        name,payload=c.calls[0]
        self.assertEqual(name,'delegate_task')
        self.assertEqual(len(payload['tasks']),1)
        self.assertNotIn('toolsets',payload['tasks'][0])
        self.assertEqual(payload['tasks'][0]['role'],'leaf')
        self.assertEqual(payload['background'],True)
        self.assertIn('<foreign_role>',payload['tasks'][0]['context'])
        self.assertIn(self.request,payload['tasks'][0]['context'])
        rows=[json.loads(p.read_text()) for p in (self.run/'BRIDGE_EVIDENCE').glob('*.json')]
        self.assertEqual({x['status'] for x in rows},{'APPROVED_BEFORE_DISPATCH','DISPATCH_RETURNED'})
        self.assertTrue(all(x['semantic_parity_verified'] is False for x in rows))
        self.assertNotIn(self.request, json.dumps(rows))
        self.assertTrue(Path(r['approval_evidence_path']).exists())
        evidence=BR.bridge_evidence(self.run_id,work_root=self.root)
        self.assertEqual(len(evidence['events']),2)
        self.assertFalse(evidence['semantic_parity_verified'])

    def test_source_changes_during_choice_are_rejected(self):
        c=Context()
        def mutate(q, choices):
            (self.src/'agents'/'reviewer.md').write_text('changed',encoding='utf-8')
            return 'run'
        c.ask_choice=mutate
        with self.assertRaisesRegex(Exception,'fingerprint'):
            BR.run_agent(c,self.run_id,'reviewer',self.request,allow_inherited_tools=True,work_root=self.root)
        self.assertEqual(c.calls,[])
        self.assertFalse(BR._BRIDGE_ACTIVE)

    def test_legacy_run_audit_restores_inert_reference_without_model(self):
        ref=self.pkg/'references'/'foreign-agent-source'/'reviewer.md'
        ref.unlink()
        with self.assertRaisesRegex(Exception,'not preserved'):
            BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)
        report=FLOW.audit_existing_run(self.run_id,work_root=self.root)
        self.assertTrue(ref.is_file())
        self.assertEqual(report['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
        self.assertEqual(len(BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)['role_sha256']),64)

    def test_reference_changed_cannot_delegate(self):
        (self.pkg/'references'/'foreign-agent-source'/'reviewer.md').write_text('bad')
        with self.assertRaisesRegex(Exception,'preserved byte-for-byte'):
            BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)

    def test_run_must_be_validated_uninstalled_pinned(self):
        self.report['status']='IN_PROGRESS'
        (self.run/'RUN_REPORT.json').write_text(json.dumps(self.report))
        with self.assertRaisesRegex(Exception,'completed'):
            BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)
        self.report['status']='VALIDATED_PARTIAL_REVIEW_REQUIRED';self.report['fetch']['commit_sha']='main'
        (self.run/'RUN_REPORT.json').write_text(json.dumps(self.report))
        with self.assertRaisesRegex(Exception,'pinned'):
            BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)

    def test_active_conversion_refuses_bridge(self):
        import threading
        with FLOW._ACTIVE_LOCK:
            FLOW._ACTIVE_JOBS[self.run_id]=threading.Event()
        try:
            with self.assertRaisesRegex(Exception,'active conversion'):
                BR.preview_agent(self.run_id,'reviewer',self.request,work_root=self.root)
        finally:
            with FLOW._ACTIVE_LOCK:
                FLOW._ACTIVE_JOBS.pop(self.run_id,None)

    def test_tool_failure_does_not_claim_success_or_retry(self):
        c=Context(result=TimeoutError('details private'))
        result=BR.run_agent(c,self.run_id,'reviewer',self.request,allow_inherited_tools=True,work_root=self.root)
        self.assertEqual(result['status'],'DISPATCH_ERROR_OR_UNKNOWN')
        self.assertEqual(result['dispatched'],'unknown')
        self.assertEqual(len(c.calls),1)
        self.assertNotIn('details private',json.dumps(result))

    def test_command_grammar_and_denial(self):
        with patch.object(FLOW,'_work_root',return_value=self.root):
            c=Context(choice='cancel')
            out=json.loads(FLOW.command(c,f'delegate-preview {self.run_id} reviewer -- {self.request}'))
            self.assertEqual(out['agent_name'],'reviewer')
            out=json.loads(FLOW.command(c,f'args-preview {self.run_id} check -- main --skip-tests'))
            self.assertEqual(out['argv'],['main','--skip-tests'])
            out=json.loads(FLOW.command(c,f'delegate-run {self.run_id} reviewer --allow-inherited-tools -- {self.request}'))
            self.assertFalse(out['dispatched'])
            self.assertEqual(c.calls,[])
            blocked=FLOW.command(c,f'delegate-run {self.run_id} reviewer')
            self.assertIn('BLOCKED',blocked)

if __name__=='__main__':unittest.main()
