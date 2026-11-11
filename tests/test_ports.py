import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from port_core import analyze, stage, PortError, safe_child, normalize_mcp


class PortTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dest=Path(self.temp.name)/'stage'
        self.examples=ROOT/'examples'

    def test_codex_probe(self):
        x=analyze(str(self.examples/'codex-sample'))
        self.assertEqual(x['profile'],'codex')
        self.assertEqual(len(x['skills']),1)
        self.assertEqual(len(x['commands']),1)
        self.assertEqual(x['mcp_servers'],['fixture'])
        self.assertEqual(x['status'],'PORTABLE_CANDIDATE')

    def test_claude_probe_agent_limitation(self):
        x=analyze(str(self.examples/'claude-sample'))
        self.assertEqual(x['profile'],'claude-code')
        self.assertTrue(any('agents:' in item for item in x['issues']))
        self.assertEqual(x['status'],'REVIEW_REQUIRED')

    def test_openclaw_probe_no_execution(self):
        x=analyze(str(self.examples/'openclaw-sample'))
        self.assertEqual(x['profile'],'openclaw')
        self.assertEqual(x['status'],'REVIEW_REQUIRED')

    def test_not_approved_refused_without_writing(self):
        with self.assertRaisesRegex(PortError,'approved=true'):
            stage(str(self.examples/'codex-sample'),str(self.dest))
        self.assertFalse(self.dest.exists())

    def test_codex_stage_genuine_mcp_and_skill_structure(self):
        result=stage(str(self.examples/'codex-sample'),str(self.dest),approved=True)
        o=Path(result['staged_path'])
        self.assertEqual(result['verification'],'STAGED_ONLY')
        self.assertEqual(json.loads((o/'plugin.json').read_text())['name'],'port-codex-codex-sample')
        self.assertTrue((o/'skills/codex-brief/SKILL.md').exists())
        self.assertTrue((o/'skills/describe/SKILL.md').exists())
        mcp=json.loads((o/'mcp.json').read_text())
        self.assertEqual(mcp['mcpServers']['fixture']['args'][0],'${PLUGIN_ROOT}/original/echo-server.mjs')
        self.assertTrue((o/'original/echo-server.mjs').is_file())
        self.assertTrue((o/'PORTING_REPORT.md').is_file())
        self.assertFalse((o/'plugin.yaml').exists())

    def test_claude_requires_partial_consent(self):
        source=str(self.examples/'claude-sample')
        with self.assertRaisesRegex(PortError,'allow_partial'):
            stage(source,str(self.dest),approved=True)
        self.assertFalse(self.dest.exists() and list(self.dest.iterdir()))
        p=Path(stage(source,str(self.dest),approved=True,allow_partial=True)['staged_path'])
        info=json.loads((p/'PORTING_REPORT.json').read_text())
        self.assertTrue(info['partial'])
        self.assertTrue(any('agents:' in issue for issue in info['issues']))
        self.assertTrue((p/'skills/check/SKILL.md').is_file())

    def test_openclaw_requires_extra_exec_consent(self):
        with self.assertRaisesRegex(PortError,'run_foreign_code=true'):
            stage(str(self.examples/'openclaw-sample'),str(self.dest),approved=True)
        self.assertFalse(self.dest.exists() and list(self.dest.iterdir()))

    @unittest.skipUnless(shutil.which('node'), 'Node.js not installed')
    def test_openclaw_staging_and_actual_native_tool_call(self):
        r=stage(str(self.examples/'openclaw-sample'),str(self.dest),approved=True,run_foreign_code=True)
        o=Path(r['staged_path'])
        self.assertEqual(r['source_profile'],'openclaw')
        self.assertTrue((o/'plugin.yaml').is_file())
        self.assertTrue((o/'tool_specs.json').is_file())
        spec=importlib.util.spec_from_file_location('ported_fixture',o/'__init__.py',submodule_search_locations=[str(o)])
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        class Ctx:
            tools=[]
            def register_tool(self,**kw): self.tools.append(kw)
        ctx=Ctx();mod.register(ctx)
        self.assertEqual(len(ctx.tools),1)
        out=json.loads(ctx.tools[0]['handler']({'text':'Hermes'}))
        self.assertEqual(out['result']['content'][0]['text'],'semreH')
        self.assertTrue(any('ported_openclaw' in v for v in ctx.tools[0].values() if isinstance(v,str)))

    def test_no_overwrite(self):
        source=str(self.examples/'codex-sample')
        stage(source,str(self.dest),approved=True)
        with self.assertRaisesRegex(PortError,'overwrite'):
            stage(source,str(self.dest),approved=True)

    def test_path_traversal_rejected(self):
        with self.assertRaises(PortError):safe_child(ROOT,'../secrets')
        with self.assertRaises(PortError):safe_child(ROOT,'C:\\Users\\test\\secret.txt')

    def test_literal_secret_like_env_block(self):
        _, block=normalize_mcp({'danger':{'command':'node','args':[],'env':{'API_KEY':'literal-secret'}}})
        self.assertTrue(any('literal secret-like' in b for b in block))

    def test_manifest_symlink_rejected(self):
        source=Path(self.temp.name)/'src'
        shutil.copytree(self.examples/'codex-sample',source)
        try:
            (source/'exfil').symlink_to(self.examples/'codex-sample'/'echo-server.mjs')
        except OSError:
            self.skipTest('OS does not allow symlinks')
        with self.assertRaisesRegex(PortError,'symlink'):
            analyze(str(source))

    def test_env_file_not_copied(self):
        source=Path(self.temp.name)/'src'
        shutil.copytree(self.examples/'codex-sample',source)
        (source/'.env').write_text('SECRET=NOPE')
        output=Path(stage(str(source),str(self.dest),approved=True)['staged_path'])
        self.assertFalse((output/'original/.env').exists())

    def test_source_fingerprint_changes(self):
        source=Path(self.temp.name)/'src'
        shutil.copytree(self.examples/'codex-sample',source)
        a=analyze(str(source))['fingerprint_sha256']
        (source/'README.md').write_text('modified')
        b=analyze(str(source))['fingerprint_sha256']
        self.assertNotEqual(a,b)

    def test_command_rebuilt_with_frontmatter(self):
        output=Path(stage(str(self.examples/'codex-sample'),str(self.dest),approved=True)['staged_path'])
        text=(output/'skills/describe/SKILL.md').read_text()
        self.assertTrue(text.startswith('---\nname: describe\n'))
        self.assertIn('main package boundaries',text)

if __name__=='__main__':unittest.main()

class GitHubSourceTests(unittest.TestCase):
    def test_fetch_rejects_unsupported_url(self):
        from port_core import fetch_github
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PortError):
                fetch_github('http://127.0.0.1/secret', tmp, approved=True)
            with self.assertRaises(PortError):
                fetch_github('https://github.com/fake/test', tmp, approved=False)

    def test_fetch_safe_pinned_zip_without_network(self):
        from unittest.mock import patch
        from io import BytesIO
        from zipfile import ZipFile
        from port_core import fetch_github
        sha='a'*40
        data=BytesIO()
        with ZipFile(data,'w') as z:
            z.writestr('repo-'+sha+'/plugin.json',json.dumps({'name':'sample','version':'1.0'}))
            z.writestr('repo-'+sha+'/skills/hello/SKILL.md','---\nname: hello\ndescription: Hi\n---\nHello')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('port_core._github_zip',return_value=data.getvalue()):
                r=fetch_github('https://github.com/example/repo/tree/'+sha,tmp,approved=True)
            self.assertEqual(r['profile'],'portable')
            self.assertEqual(r['commit_sha'],sha)
            self.assertTrue((Path(r['source_path'])/'plugin.json').is_file())
            self.assertEqual(analyze(r['source_path'])['profile'],'portable')

    def test_fetch_zip_slip_rejected(self):
        from unittest.mock import patch
        from io import BytesIO
        from zipfile import ZipFile
        from port_core import fetch_github
        sha='a'*40
        data=BytesIO()
        with ZipFile(data,'w') as z:
            z.writestr('repo-'+sha+'/../../../outside.txt','BAD')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('port_core._github_zip',return_value=data.getvalue()):
                with self.assertRaises(PortError):
                    fetch_github('https://github.com/example/repo/tree/'+sha,tmp,approved=True)
            self.assertFalse((Path(tmp)/'outside.txt').exists())

    # This test is intentionally in the GitHubSourceTests class.
    def test_fetch_monorepo_branch_subdir_is_pinned(self):
        from unittest.mock import patch
        from port_core import fetch_github
        import base64
        sha='b'*40
        file1=json.dumps({'name':'skill'}).encode()
        file2=b'---\nname: s\ndescription: Hi\n---\nHi'
        base='plugins/skill'
        def api(url):
            if '/commits/main' in url:
                return {'sha':sha}
            if f'/contents/{base}?ref=' in url:
                return [{'type':'dir','path':base+'/.claude-plugin'},
                        {'type':'dir','path':base+'/skills'}]
            if f'/contents/{base}/.claude-plugin?ref=' in url:
                return [{'type':'file','path':base+'/.claude-plugin/plugin.json','size':len(file1)}]
            if f'/contents/{base}/skills?ref=' in url:
                return [{'type':'dir','path':base+'/skills/s'}]
            if f'/contents/{base}/skills/s?ref=' in url:
                return [{'type':'file','path':base+'/skills/s/SKILL.md','size':len(file2)}]
            if f'/contents/{base}/.claude-plugin/plugin.json?ref=' in url:
                return {'type':'file','encoding':'base64','content':base64.b64encode(file1).decode()}
            if f'/contents/{base}/skills/s/SKILL.md?ref=' in url:
                return {'type':'file','encoding':'base64','content':base64.b64encode(file2).decode()}
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('port_core._github_json',side_effect=api), patch('port_core._github_zip') as zip_mock:
                r=fetch_github('https://github.com/example/repo/tree/main/plugins/skill',tmp,approved=True)
            self.assertEqual(r['profile'],'claude-code')
            self.assertEqual(r['commit_sha'],sha)
            self.assertTrue((Path(r['source_path'])/'.claude-plugin/plugin.json').is_file())
            self.assertFalse((Path(r['source_path'])/'plugins').exists())
            zip_mock.assert_not_called()
