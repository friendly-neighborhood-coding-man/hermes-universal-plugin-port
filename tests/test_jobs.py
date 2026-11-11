"""Asynchronous orchestration, cancellation, resume, safe local install tests."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('universal_port_jobs_pkg',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
PKG=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=PKG
SPEC.loader.exec_module(PKG)
from universal_port_jobs_pkg import port_flow as FLOW

class Model:
    def __init__(self, bad=False):
        self.calls=[]
        self.bad=bad
    def complete_structured(self, **kwargs):
        from types import SimpleNamespace
        self.calls.append(kwargs)
        if kwargs['schema_name']=='universal_port.review':
            return SimpleNamespace(parsed={'risks':[], 'compatibility_notes':[]},provider='test',model='test-model')
        if self.bad:
            return SimpleNamespace(parsed=None,provider='test',model='test-model',text='{')
        return SimpleNamespace(parsed={'body':'# Safe migrated workflow\n\nReview the requested files and ask before making changes.',
                                       'limitations':[],'requires_manual_review':False},
                               provider='test',model='test-model')
class Ctx:
    def __init__(self,bad=False): self.llm=Model(bad)

class JobTests(unittest.TestCase):
    def setUp(self):
        self.assertFalse(FLOW._ACTIVE_JOBS, 'prior job leaked between tests')

    def test_background_command_immediate_and_single_concurrent_job(self):
        started=threading.Event(); release=threading.Event()
        def fake_run(ctx,url,*,work_root,run_id,cancel_event,resume):
            base=Path(work_root)/run_id; base.mkdir(parents=True)
            (base/'RUN_REPORT.json').write_text(json.dumps({'run_id':run_id, 'run_dir':str(base), 'status':'IN_PROGRESS','phase':'fetch'}))
            started.set()
            release.wait(timeout=2.0)
        with tempfile.TemporaryDirectory() as td, patch.object(FLOW,'_work_root',return_value=Path(td)),patch.object(FLOW,'run_url',side_effect=fake_run):
            output=FLOW.command(Ctx(),'https://github.com/example/plugin')
            self.assertIn('started:',output)
            run_id=output.split('started: ')[1].split('\n')[0]
            self.assertTrue(started.wait(1.0))
            busy=FLOW.command(Ctx(),'https://github.com/example/second')
            self.assertIn('still active',busy)
            state=json.loads(FLOW.command(Ctx(),f'status {run_id}'))
            self.assertTrue(state['live_in_this_gateway'])
            self.assertIn('Cancellation requested',FLOW.command(Ctx(),f'cancel {run_id}'))
            with FLOW._ACTIVE_LOCK:
                self.assertTrue(FLOW._ACTIVE_JOBS[run_id].is_set())
            release.set()
            for _ in range(60):
                with FLOW._ACTIVE_LOCK:
                    if not FLOW._ACTIVE_JOBS: break
                time.sleep(0.01)
            self.assertFalse(FLOW._ACTIVE_JOBS)

    def test_cancellation_writes_terminal_report_before_fetch(self):
        stop=threading.Event(); stop.set()
        with tempfile.TemporaryDirectory() as td, patch.object(FLOW,'fetch_github') as fetch:
            r=FLOW.run_url(Ctx(),'https://github.com/example/plugin',work_root=Path(td),cancel_event=stop)
            self.assertEqual(r['status'],'CANCELLED')
            self.assertFalse(r['installed'])
            self.assertEqual(json.loads((Path(r['run_dir'])/'RUN_REPORT.json').read_text())['status'],'CANCELLED')
            fetch.assert_not_called()

    def test_resume_reuses_source_stage_review_and_retries_bad_command(self):
        source=ROOT/'examples'/'codex-sample'
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)/'runs'; ctx=Ctx(bad=True)
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(source),'commit_sha':'a'*40}) as fetch, patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                first=FLOW.run_url(ctx,'https://github.com/example/codex-sample',work_root=home,do_install=False)
            self.assertEqual(first['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertEqual(len(ctx.llm.calls),2)
            self.assertTrue(first['llm_adaptation']['model_failed'])
            newctx=Ctx()
            with patch.object(FLOW,'fetch_github') as newfetch,patch.object(FLOW,'stage') as newstage,patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                second=FLOW.run_url(newctx,'https://github.com/example/codex-sample',work_root=home,run_id=first['run_id'],resume=True,do_install=False)
            newfetch.assert_not_called();newstage.assert_not_called()
            self.assertEqual(len(newctx.llm.calls),1)
            self.assertEqual(second['llm_adaptation']['count'],1)
            self.assertFalse(second['llm_adaptation']['model_failed'])
            self.assertEqual(second['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertFalse(second['installed'])

    def test_local_installer_does_not_overwrite_and_does_not_execute(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'HERMES_HOME':td}):
            pkg=Path(td)/'source';pkg.mkdir();(pkg/'plugin.json').write_text('{"name":"valid"}')
            result=FLOW._install_local_portable(pkg,'valid')
            self.assertEqual(result['status'],'INSTALLED_RESTART_REQUIRED')
            self.assertTrue(Path(result['destination']).is_dir())
            blocked=FLOW._install_local_portable(pkg,'valid')
            self.assertEqual(blocked['status'],'INSTALL_BLOCKED')
            native=Path(td)/'native';native.mkdir();(native/'plugin.yaml').write_text('name: native')
            self.assertEqual(FLOW._install_local_portable(native,'native')['status'],'INSTALL_REVIEW_REQUIRED')

    def test_resume_rejects_tampered_source(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);source=home/'src';source.mkdir();(source/'.codex-plugin').mkdir()
            (source/'.codex-plugin'/'plugin.json').write_text('{"name":"demo"}')
            ctx=Ctx()
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(source),'commit_sha':'c'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                first=FLOW.run_url(ctx,'https://github.com/example/demo',work_root=home/'runs',do_install=False)
            (source/'evil.txt').write_text('new file')
            second=FLOW.run_url(Ctx(),'https://github.com/example/demo',work_root=home/'runs',run_id=first['run_id'],resume=True,do_install=False)
            self.assertEqual(second['status'],'RUN_BLOCKED')
            self.assertIn('fingerprint changed',second['reason'])

if __name__=='__main__':unittest.main()
