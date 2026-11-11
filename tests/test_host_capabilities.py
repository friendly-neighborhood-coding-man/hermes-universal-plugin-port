"""Static capability evidence tests. No Hermes process, network, or model calls."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG_NAME = 'universal_port_hostmap_pkg'
SPEC = importlib.util.spec_from_file_location(PKG_NAME, ROOT/'__init__.py',
                                               submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[PKG_NAME] = PKG
SPEC.loader.exec_module(PKG)
from universal_port_hostmap_pkg import host_capabilities as H
from universal_port_hostmap_pkg import port_core as CORE
from universal_port_hostmap_pkg import port_flow as FLOW


class HostCapabilityTests(unittest.TestCase):
    def test_known_host_apis_are_not_presented_as_verified_bridges(self):
        d = H.host_profile()
        self.assertIn('delegation', d['sources'])
        self.assertTrue(d['capabilities']['subagent']['available'])
        self.assertIn('NOT an implicit checkpoint', H.MODEL_GUIDANCE)
        self.assertIn('NO automatic mapping', H.MODEL_GUIDANCE)
        self.assertIn('NOT literal $ARGUMENTS', H.MODEL_GUIDANCE)

    def test_claude_agent_task_and_approval_detected_and_block_full_parity(self):
        source = ROOT/'examples'/'claude-sample'
        with tempfile.TemporaryDirectory() as td:
            staged = CORE.stage(str(source), str(Path(td)/'staged'), approved=True, allow_partial=True)
            pkg = Path(staged['staged_path'])
            plan = CORE.analyze(str(source))
            references = H.preserve_agent_references(pkg, source)
            self.assertEqual(len(references), 1)
            self.assertFalse(references[0]['runnable_agent'])
            preserved = pkg / references[0]['reference_path']
            self.assertEqual(preserved.read_bytes(), (source/'agents'/'reviewer.md').read_bytes())
            report = H.audit(pkg, plan, source)
            self.assertTrue(report['blocks_full_compatibility'])
            self.assertEqual(len(report['unported_agent_definitions']), 1)
            self.assertIn('reviewer.md', report['unported_agent_definitions'][0]['source_path'])
            for cmd in report['commands']:
                for feat in cmd['feature_checks']:
                    self.assertFalse(feat['runtime_bridge_verified'])

    def test_user_arguments_are_compiled_outside_fences_only(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src = base/'source'; (src/'commands').mkdir(parents=True)
            command = ('# Execute\nProcess $ARGUMENTS in the request.\n'
                       '```bash\necho "$ARGUMENTS"\n```\n')
            (src/'commands'/'worker.md').write_text(command, encoding='utf-8')
            pkg = base/'candidate'; (pkg/'skills'/'worker').mkdir(parents=True)
            target = pkg/'skills'/'worker'/'SKILL.md'
            target.write_text('---\nname: worker\n---\n\n'+command, encoding='utf-8')
            plan = {'commands':[{'name':'worker','path':'commands\\worker.md'}]}
            c1 = H.compile_skill_invocations(pkg,plan,src)
            self.assertEqual(c1['compiled_skills'][0]['replaced_unfenced_placeholders'], 1)
            changed = target.read_text(encoding='utf-8')
            self.assertIn('echo "$ARGUMENTS"',changed)
            self.assertIn('after this Hermes skill command',changed)
            self.assertEqual(changed.count('<!-- universal-port:hermes-skill-invocation-v1 -->'),1)
            H.compile_skill_invocations(pkg,plan,src)
            self.assertEqual(changed,target.read_text(encoding='utf-8'))
            details = H.audit(pkg,plan,src)
            flags = details['commands'][0]['feature_checks']
            self.assertEqual(flags[0]['feature'], 'args_placeholder')
            self.assertTrue(flags[0]['source_marker_still_in_staged'])
            self.assertFalse(flags[0]['runtime_bridge_verified'])

    def test_static_run_audit_uses_original_run_and_no_model_calls(self):
        source = ROOT/'examples'/'claude-sample'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);run_id='abcdef123456';run=root/'runs'/run_id
            run.mkdir(parents=True)
            src=run/'sources'/'pinned';src.parent.mkdir(parents=True)
            import shutil
            shutil.copytree(source,src)
            plan=CORE.analyze(str(src))
            stage=CORE.stage(str(src),str(run/'staged'),approved=True,allow_partial=True)
            state={'run_id':run_id,'run_dir':str(run),'url':'https://github.com/example/fake',
                'status':'VALIDATED_PARTIAL_REVIEW_REQUIRED','phase':'validate',
                'fetch':{'source_path':str(src),'commit_sha':'b'*40},
                'analysis':plan,'stage':stage,'validation':{'ok':True},'installed':False}
            (run/'RUN_REPORT.json').write_text(json.dumps(state),encoding='utf-8')
            results=FLOW.audit_existing_run(run_id,work_root=root/'runs')
            self.assertEqual(results['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertGreater(results['unverified_semantic_features'],0)
            self.assertTrue((run/'CAPABILITY_AUDIT.json').is_file())
            self.assertTrue((run/'HOST_CAPABILITY_PROFILE.json').is_file())
            state2=json.loads((run/'RUN_REPORT.json').read_text(encoding='utf-8'))
            self.assertFalse(state2['installed'])
            self.assertEqual(state2['phase'],'validate')
            self.assertIn('compatibility_audit',state2)
            (src/'commands'/'check.md').write_text('tampered source',encoding='utf-8')
            with self.assertRaisesRegex(Exception,'fingerprint'):
                FLOW.audit_existing_run(run_id,work_root=root/'runs')

    def test_model_adaptation_prompt_includes_documented_host_boundaries(self):
        from types import SimpleNamespace
        class Model:
            def __init__(self): self.calls=[]
            def complete_structured(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(parsed={'body':'# Instructions\n\nFollow user request without side effects.',
                    'limitations':[],'requires_manual_review':False})
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); p=root/'skills'/'work'/'SKILL.md';p.parent.mkdir(parents=True)
            p.write_text('---\nname: work\ndescription: Test\n---\n\nRead the requested files.',encoding='utf-8')
            model=Model()
            c=type('Ctx',(),{'llm':model})()
            FLOW._llm_rewrite_commands(c,root,{'commands':[{'name':'work'}]})
            prompt=model.calls[0]['instructions']
            self.assertIn('delegate_task(goal,context)',prompt)
            self.assertIn('NOT an implicit checkpoint',prompt)

    def test_install_rejects_pre_host_audit_legacy_status(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);run_id='abcdef123456';run=root/run_id
            run.mkdir()
            (run/'RUN_REPORT.json').write_text(json.dumps({
                'run_id':run_id,'run_dir':str(run),
                'status':'VALIDATED_NOT_INSTALLED','validation':{'ok':True},
            }),encoding='utf-8')
            with self.assertRaisesRegex(Exception,'semantic audit missing'):
                FLOW.install_validated(run_id,work_root=root)

if __name__=='__main__':unittest.main()
