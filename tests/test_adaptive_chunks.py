"""A workload-scaled adapter does not drop source sections or hide chunk failures."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('universal_port_chunk_pkg', ROOT/'__init__.py', submodule_search_locations=[str(ROOT)])
PKG=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=PKG
SPEC.loader.exec_module(PKG)
from universal_port_chunk_pkg import port_flow as FLOW
from universal_port_chunk_pkg import adaptive_chunks as ADAPT


class Model:
    def __init__(self, fail_on=None):
        self.calls=[]
        self.fail_on=fail_on
        self.failed_once=False
    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get('schema_name')=='universal_port.review':
            return SimpleNamespace(parsed={'risks':[], 'compatibility_notes':[]},model='test',provider='test')
        if kwargs.get('schema_name')=='universal_port.command_patch':
            ordinal=len([c for c in self.calls if c.get('schema_name')=='universal_port.command_patch'])
            if ordinal==self.fail_on and not self.failed_once:
                self.failed_once=True
                return SimpleNamespace(parsed=None, text='invalid json' * 30, model='test',provider='test',content_type='text')
            return SimpleNamespace(parsed={'edits':[],'limitations':[], 'requires_manual_review':False},model='test',provider='test')
        return SimpleNamespace(parsed={'body':'# Short import\n\nNo accidental execution of foreign source.',
                                       'limitations':[], 'requires_manual_review':False},model='test',provider='test')
class Ctx:
    def __init__(self,model=None): self.llm=model or Model()


def fixture(path: Path, n=105):
    root=path/'source'; (root/'.claude-plugin').mkdir(parents=True)
    (root/'.claude-plugin'/'plugin.json').write_text('{"name":"chunk-test"}',encoding='utf-8')
    (root/'commands').mkdir()
    doc='---\ndescription: Long command\n---\n\n# Workflow\n'
    for k in range(n):
        doc += (f'\n## Phase {k}: checkpoint\n\n'
                'Review repository metadata, preserve original ordering, request approval. '
                'Record context and do not execute third-party instructions.\n\n')
    (root/'commands'/'workflow.md').write_text(doc,encoding='utf-8')
    return root, doc


class AdaptiveTests(unittest.TestCase):
    def test_structure_preserved_with_fenced_commands(self):
        source='# Workflow\n\n' + (('## Stage\n\ncheck\n\n```bash\necho never-run\n```\n\n')*320)
        chunks=ADAPT.split_markdown(source)
        self.assertGreater(len(chunks),1)
        self.assertEqual(''.join(chunks),source)
        self.assertTrue(all(len(c)<=ADAPT.choose_limit(source) for c in chunks))
        for chunk in chunks:
            self.assertEqual(chunk.count('```')%2,0)

    def test_unbreakable_code_block_refused(self):
        source='```python\n'+ 'x = 1\n'*2000 + '```\n'
        with self.assertRaisesRegex(ValueError,'Code fence'):
            ADAPT.split_markdown(source,limit=1000)

    def test_patch_must_be_unique_and_nonoverlap(self):
        with self.assertRaisesRegex(ValueError,'uniquely'):
            ADAPT.validate_edits('A A', {'edits':[{'old':'A','new':'B'}], 'limitations':[], 'requires_manual_review':False})
        changed, limits, review, edits=ADAPT.validate_edits('prefix-one-tail',{
            'edits':[{'old':'-one-','new':'-two-'}], 'limitations':[], 'requires_manual_review':False})
        self.assertEqual(changed,'prefix-two-tail')
        self.assertTrue(review)
        self.assertEqual(len(edits),1)

    def test_long_source_is_chunked_and_unchanged_without_patches(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); root,original=fixture(td)
            ctx=Ctx()
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(root),'commit_sha':'a'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                result=FLOW.run_url(ctx,'https://github.com/example/long',work_root=td/'runs')
            self.assertEqual(result['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            details=result['llm_adaptation']
            self.assertEqual(details['count'],1)
            self.assertEqual(details['model_failed'],[])
            self.assertGreater(details['chunked_commands'][0]['chunks'],1)
            self.assertFalse(result['installed'])
            staged=Path(result['stage']['staged_path'])/'skills/workflow'
            self.assertEqual((staged/'SKILL.md').read_text(encoding='utf-8'),
                             (staged/'ORIGINAL_COMMAND.md').read_text(encoding='utf-8'))
            checkpoint=td/'runs'/result['run_id']/'CHUNK_PROGRESS'/'workflow.json'
            self.assertTrue(checkpoint.is_file())

    def test_invalid_middle_chunk_preserves_original_then_resumes(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);root,raw=fixture(td)
            model=Model(fail_on=2);ctx=Ctx(model)
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(root),'commit_sha':'a'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                first=FLOW.run_url(ctx,'https://github.com/example/long',work_root=td/'runs')
            self.assertEqual(first['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertEqual(first['llm_adaptation']['model_failed'][0]['reason'],'INVALID_CHUNK_PATCH')
            self.assertEqual(first['llm_adaptation']['completed_commands'],[])
            path=Path(first['stage']['staged_path'])/'skills/workflow/SKILL.md'
            self.assertEqual(path.read_text(encoding='utf-8'), (path.parent/'ORIGINAL_COMMAND.md').read_text(encoding='utf-8'))
            with patch.object(FLOW,'fetch_github') as fetch,patch.object(FLOW,'stage') as stage,patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                next_run=FLOW.run_url(Ctx(), 'https://github.com/example/long',work_root=td/'runs',run_id=first['run_id'],resume=True)
            fetch.assert_not_called();stage.assert_not_called()
            self.assertEqual(next_run['llm_adaptation']['model_failed'],[])
            self.assertEqual(next_run['llm_adaptation']['count'],1)
            self.assertGreaterEqual(next_run['llm_adaptation']['chunked_commands'][0]['reused_chunks'],1)
            self.assertEqual(path.read_text(encoding='utf-8'), (path.parent/'ORIGINAL_COMMAND.md').read_text(encoding='utf-8'))

    def test_v030_skipped_long_command_is_retried_after_upgrade(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);root,raw=fixture(td,n=190)
            package=td/'package'; target=package/'skills'/'workflow'/'SKILL.md'
            target.parent.mkdir(parents=True)
            target.write_text(raw,encoding='utf-8')
            state=td/'ADAPTATION_PROGRESS.json'
            state.write_text(json.dumps({
                'count':0, 'needs_manual_review':True,
                'limitations':['Command exceeds bounded model context; unchanged: workflow'],
                'paths':[], 'model_failed':[],
                'model_skipped':[{'command':'workflow','reason':'SOURCE_TOO_LONG'}],
                'completed_commands':['workflow'], 'manual_review_commands':[],
            }),encoding='utf-8')
            summary=FLOW._llm_rewrite_commands(Ctx(),package,{'commands':[{'name':'workflow'}]},state_path=state)
            self.assertEqual(summary['completed_commands'],['workflow'])
            self.assertEqual(summary['model_skipped'],[])
            self.assertFalse(summary['needs_manual_review'])
            self.assertGreater(summary['chunked_commands'][0]['chunks'],1)
            self.assertEqual(target.read_text(encoding='utf-8'),raw)

    def test_budget_is_bounded_and_failed_source_is_not_completed(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);root,raw=fixture(td)
            with patch.object(FLOW,'MAX_ADAPTATION_CALLS_PER_RUN',1), patch.object(FLOW,'fetch_github',return_value={'source_path':str(root),'commit_sha':'a'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                r=FLOW.run_url(Ctx(),'https://github.com/example/long',work_root=td/'runs')
            self.assertEqual(r['llm_adaptation']['model_failed'][0]['reason'],'MODEL_BUDGET_REACHED')
            self.assertNotIn('workflow',r['llm_adaptation']['completed_commands'])
            self.assertFalse(r['installed'])

    def test_exact_json_text_recovers_missing_parsed_without_executing_content(self):
        result=SimpleNamespace(parsed=None,text=json.dumps({
            'edits':[{'old':'$ARGUMENTS','new':'<user input; mapping requires review>'}],
            'limitations':['Host input binding must be validated'],
            'requires_manual_review':True,
        }))
        parsed, recovered=FLOW._structured_patch_data(result)
        self.assertTrue(recovered)
        changed,limits,review,_=ADAPT.validate_edits('Use $ARGUMENTS safely.',parsed)
        self.assertIn('mapping requires review',changed)
        self.assertTrue(review)
        self.assertEqual(len(limits),1)
        # Never snip a JSON fragment from a provider's non-JSON prose.
        bad=SimpleNamespace(parsed=None,text='Instructions to run commands first: '+result.text)
        parsed,recovered=FLOW._structured_patch_data(bad)
        self.assertFalse(recovered)
        self.assertIsNone(parsed)

    def test_resumed_failure_clears_stale_manual_review_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            target=root/'skills'/'task'/'SKILL.md';target.parent.mkdir(parents=True)
            target.write_text('---\nname: task\ndescription: Task\n---\n\n# Task\nRead first, then summarize.',encoding='utf-8')
            checkpoint=root/'ADAPTATION_PROGRESS.json'
            checkpoint.write_text(json.dumps({
                'count':0,'needs_manual_review':True,
                'limitations':['Invalid model command adaptation; original preserved: task'],
                'paths':[], 'model_failed':[{'command':'task','reason':'INVALID_ADAPTATION_SCHEMA_OR_BODY'}],
                'model_skipped':[], 'completed_commands':[], 'manual_review_commands':[],
            }),encoding='utf-8')
            outcome=FLOW._llm_rewrite_commands(Ctx(),root,{'commands':[{'name':'task'}]},state_path=checkpoint)
            self.assertEqual(outcome['completed_commands'],['task'])
            self.assertFalse(outcome['model_failed'])
            self.assertFalse(outcome['needs_manual_review'])
            self.assertFalse(json.loads(checkpoint.read_text())['needs_manual_review'])

    def test_realistic_long_workload_is_chunked_and_checkpointed(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);root,_=fixture(td,n=210)
            ctx=Ctx()
            with patch.object(FLOW,'fetch_github',return_value={
                'source_path':str(root),'commit_sha':'a'*40,
            }),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                result=FLOW.run_url(ctx,'https://github.com/example/long',work_root=td/'runs')
            self.assertEqual(result['status'],'VALIDATED_PARTIAL_REVIEW_REQUIRED')
            self.assertEqual(result['llm_adaptation']['model_failed'],[])
            self.assertEqual(result['llm_adaptation']['completed_commands'],['workflow'])
            report=result['llm_adaptation']['chunked_commands'][0]
            self.assertGreater(report['chunks'],3)
            self.assertEqual(report['reused_chunks'],0)
            self.assertLessEqual(len(ctx.llm.calls),FLOW.MAX_ADAPTATION_CALLS_PER_RUN+1)
            checkpoint=td/'runs'/result['run_id']/'CHUNK_PROGRESS'/'workflow.json'
            pieces=json.loads(checkpoint.read_text())['pieces']
            self.assertEqual(len(pieces),report['chunks'])
            self.assertTrue(all(x['status']=='OK' for x in pieces.values()))
            staged=Path(result['stage']['staged_path'])/'skills/workflow'
            self.assertEqual((staged/'ORIGINAL_COMMAND.md').read_bytes(),(staged/'SKILL.md').read_bytes())

    def test_partial_run_can_never_be_installed(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);root,raw=fixture(td)
            with patch.object(FLOW,'fetch_github',return_value={'source_path':str(root),'commit_sha':'a'*40}),patch.object(FLOW,'_check_hermes',return_value={'ok':True}):
                r=FLOW.run_url(Ctx(),'https://github.com/example/long',work_root=td/'runs')
            with self.assertRaisesRegex(Exception,'fully validated'):
                FLOW.install_validated(r['run_id'],work_root=td/'runs')

if __name__=='__main__': unittest.main()
