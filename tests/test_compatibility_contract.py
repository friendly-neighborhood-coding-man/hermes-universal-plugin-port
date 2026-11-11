"""Offline-only capability loss, permissions and update scope tests."""
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
SPEC = importlib.util.spec_from_file_location(
    'compatibility_v035_test_pkg', ROOT/'__init__.py',
    submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from compatibility_v035_test_pkg import compatibility_contract as C, port_core as CORE, port_flow as FLOW

SOURCE_SHA = 'abcdef0123456789abcdef0123456789abcdef01'


class CapabilityLossTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root/'source'
        shutil.copytree(ROOT/'examples'/'claude-sample', self.source)
        self.plan = CORE.analyze(str(self.source))
        self.staged = CORE.stage(str(self.source),str(self.root/'staged'), approved=True, allow_partial=True)
        self.package = Path(self.staged['staged_path'])

    def loss(self):
        return C.loss_report(self.plan,self.source,self.package, None,None)

    def snapshot(self, source_commit=SOURCE_SHA, target='0.fixture'):
        return C.understanding_snapshot(
            self.plan, source_commit, target, 'https://github.com/example/repo',
            'a'*64, self.loss())

    def test_claude_commands_not_falsely_certified(self):
        report = self.loss()
        self.assertTrue(report['blocks_full_compatibility'])
        self.assertFalse(report['runtime_parity_verified'])
        self.assertEqual(len(report['commands']), 1)
        self.assertEqual(report['commands'][0]['status'], 'STAGED_BUT_RUNTIME_UNVERIFIED')
        self.assertEqual(report['official_importer_gaps'][0]['gap_id'],
                         'claude_code_commands_skipped_by_official_importer')

    def test_permission_inventory_never_leaks_rule_value(self):
        settings = self.source/'settings.json'
        settings.write_text(json.dumps({'permissions': {
            'allow':['Bash(npm run lint:*)'],
            'deny':['Read(/private/example/DO_NOT_EXPOSE)'],
            'ask':['Task(secret_agent)'],
            'defaultMode':'ask'}}),encoding='utf-8')
        self.plan = CORE.analyze(str(self.source))
        report = self.loss()
        obj = report['permission_sources'][0]
        self.assertEqual(obj['permission_rule_counts']['allow']['bash'], 1)
        self.assertEqual(obj['permission_rule_counts']['deny']['non_bash_or_ambiguous'], 1)
        self.assertEqual(obj['permission_rule_counts']['ask']['non_bash_or_ambiguous'], 1)
        self.assertEqual(obj['additional_policy_types'], ['defaultMode'])
        self.assertEqual(obj['status'], 'REQUIRES_PERMISSION_SEMANTIC_REVIEW')
        self.assertTrue(report['blocks_full_compatibility'])
        self.assertNotIn('DO_NOT_EXPOSE', json.dumps(report))
        self.assertNotIn('DO_NOT_EXPOSE', json.dumps(self.snapshot()))

    def test_settings_symlink_rejected(self):
        external = self.root/'outside.json'
        external.write_text('{}',encoding='utf-8')
        try:
            (self.source/'settings.json').symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable on host')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            C.permission_inventory(self.source, self.plan)

    def test_snapshots_diff_changed_source_and_adapter(self):
        a = self.snapshot()
        b = json.loads(json.dumps(a))
        b['source']['commit'] = 'b'*40
        b['source']['fingerprint_sha256'] = 'c'*64
        b['commands'][0]['source_sha256'] = 'd'*64
        b['commands'][0]['staged_sha256'] = 'e'*64
        diff = C.compare_snapshots(a,b)
        self.assertEqual(diff['status'],'REVIEW_REQUIRED')
        self.assertEqual(len(diff['changed_commands']),1)
        self.assertEqual(len(diff['changed_staged_adapters']),1)
        self.assertTrue(diff['other_source_changes_detected'])
        self.assertTrue(diff['source_commit_changed'])
        self.assertFalse(diff['runtime_parity_verified'])

    def test_same_hash_is_not_runtime_parity_proof(self):
        a = self.snapshot()
        diff = C.compare_snapshots(a, json.loads(json.dumps(a)))
        self.assertEqual(diff['status'],'SOURCE_AND_ADAPTER_UNCHANGED_STATIC_ONLY')
        self.assertFalse(diff['runtime_parity_verified'])
        b = json.loads(json.dumps(a))
        b['target']['hermes_version']='0.changed'
        self.assertTrue(C.compare_snapshots(a,b)['target_revalidation_required'])

    def test_different_repo_cannot_be_compared(self):
        a = self.snapshot(); b = json.loads(json.dumps(a))
        b['source']['repo_url']='https://github.com/other/repo'
        with self.assertRaises(ValueError):
            C.compare_snapshots(a,b)

    def test_run_route_writes_loss_and_snapshot_without_a_model(self):
        runs = self.root/'runs'; rid='aabbccddeeff'; run=runs/rid
        run.mkdir(parents=True)
        src=run/'sources'/'pinned'; src.parent.mkdir()
        shutil.copytree(self.source,src)
        plan=CORE.analyze(str(src))
        staged=CORE.stage(str(src),str(run/'staged'),approved=True,allow_partial=True)
        state={'run_id':rid,'run_dir':str(run),'url':'https://github.com/example/repo',
               'status':'VALIDATED_PARTIAL_REVIEW_REQUIRED','phase':'validate',
               'fetch':{'source_path':str(src),'commit_sha':SOURCE_SHA},
               'analysis':plan,'stage':staged,'validation':{'ok':True},'installed':False}
        (run/'RUN_REPORT.json').write_text(json.dumps(state),encoding='utf-8')
        outcome=FLOW.route_existing_run(rid,work_root=runs)
        self.assertTrue(outcome['full_compatibility_blocked'])
        loss=json.loads((run/'CAPABILITY_LOSS.json').read_text())
        self.assertTrue(loss['official_importer_gaps'])
        snap=json.loads((run/'UNDERSTANDING_SNAPSHOT.json').read_text())
        self.assertEqual(snap['source']['commit'],SOURCE_SHA)
        self.assertFalse(snap['runtime_parity_verified'])
        with patch.object(FLOW,'_work_root',return_value=runs):
            inspected=json.loads(FLOW.command(object(),'inspect '+rid))
        self.assertEqual(inspected['staged_commands'],1)
        self.assertTrue(inspected['blocks_full_compatibility'])
        self.assertIn('CAPABILITY_LOSS.json',inspected['capability_loss_path'])


if __name__ == '__main__':
    unittest.main()
