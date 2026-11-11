import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from p615_preview_official_import import package_digest

FAKE = '''from pathlib import Path
ENTRY_DELIMITER="\\n§\\n"
def parse_existing_memory_entries(path):
    return [x.strip() for x in path.read_text(encoding="utf8").split(ENTRY_DELIMITER) if x.strip()] if path.exists() else []
def merge_entries(existing, incoming, limit):
    merged=list(existing)
    stats={"existing":len(existing), "added":0, "duplicates":0, "overflowed":0}
    for e in incoming:
        if len(ENTRY_DELIMITER.join(merged+[e])) > limit:
            stats["overflowed"]+=1
        else:
            stats["added"]+=1
            merged.append(e)
    return merged, stats
class AgentImporter:
    def __init__(self, agent, source, target, execute=False, overwrite=False):
        self.agent=agent
        self.source_root=Path(source)
        self.target_root=Path(target)
        self.execute=execute
        self.items=[]
    def record(self, kind, source, destination, status, reason='', **kwargs):
        self.items.append(dict(kind=kind,source=str(source),destination=str(destination),status=status,reason=reason))
    def merge_memory_entries(self,*args):
        raise AssertionError("interceptor not wired")
    def run(self):
        p=self.source_root / "CLAUDE.md"
        if p.exists():
            self.merge_memory_entries('context', p, self.target_root/'memories'/'MEMORY.md',[p.read_text(encoding='utf8')])
        return dict(dry_run=not self.execute, agent=self.agent, items=self.items)
'''


class OfficialBridgeCLITest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.official=self.root/'agent-importers'
        self.official.mkdir()
        (self.official/'__init__.py').write_text('',encoding='utf8')
        (self.official/'importer.py').write_text(FAKE,encoding='utf8')
        self.source=self.root/'src'
        self.source.mkdir()
        self.target=self.root/'disposable-home'
        (self.target/'memories').mkdir(parents=True)
        (self.target/'config.yaml').write_text('memory:\n  memory_char_limit: 80\n',encoding='utf8')
        self.out=self.root/'receipt.json'

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, digest=None):
        cmd=[sys.executable,str(ROOT/'scripts'/'p615_preview_official_import.py'),
             '--official-package',str(self.official), '--package-sha256',digest or package_digest(self.official),
             '--agent','claude-code','--source',str(self.source),'--target',str(self.target),
             '--memory-limit','80','--output',str(self.out),'--i-confirm-disposable-home']
        return subprocess.run(cmd,capture_output=True,text=True,timeout=15)

    def test_cli_oversize_holds_and_leaves_target_untouched(self):
        (self.source/'CLAUDE.md').write_text('x'*90,encoding='utf8')
        result=self.invoke()
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertEqual(json.loads(self.out.read_text())['gate'],'HOLD')
        self.assertEqual(list((self.target/'memories').iterdir()),[])

    def test_cli_clean_review_and_create_only(self):
        (self.source/'CLAUDE.md').write_text('hello',encoding='utf8')
        result=self.invoke()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(self.out.read_text())['gate'],'REVIEW_ONLY')
        second=self.invoke()
        self.assertEqual(second.returncode,2)
        self.assertIn('create-only',second.stderr)

    def test_cli_digest_mismatch_refused(self):
        result=self.invoke('0'*64)
        self.assertEqual(result.returncode,2)
        self.assertFalse(self.out.exists())


    def test_cli_refuses_memory_limit_that_differs_from_target_config(self):
        (self.source/'CLAUDE.md').write_text('short', encoding='utf8')
        cmd=[sys.executable,str(ROOT/'scripts'/'p615_preview_official_import.py'),'--official-package',str(self.official),
             '--package-sha256',package_digest(self.official),'--agent','claude-code','--source',str(self.source),
             '--target',str(self.target),'--memory-limit','20000','--output',str(self.out),'--i-confirm-disposable-home']
        r=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('does not match the target profile',r.stderr)
        self.assertFalse(self.out.exists())

    def test_cli_holds_when_preview_writes_anywhere_in_target_home(self):
        (self.official/'importer.py').write_text(FAKE.replace(
            "        return dict(dry_run=not self.execute",
            "        (self.target_root/'scratch-cache').mkdir()\n        return dict(dry_run=not self.execute"),encoding='utf8')
        (self.source/'CLAUDE.md').write_text('short', encoding='utf8')
        cmd=[sys.executable,str(ROOT/'scripts'/'p615_preview_official_import.py'),'--official-package',str(self.official),
             '--package-sha256',package_digest(self.official),'--agent','claude-code','--source',str(self.source),
             '--target',str(self.target),'--memory-limit','80','--output',str(self.out),'--i-confirm-disposable-home']
        r=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('changed the target home',r.stderr)
        self.assertFalse(self.out.exists())


    def test_cli_refuses_symlinked_source(self):
        import os
        (self.source/'CLAUDE.md').write_text('short', encoding='utf8')
        outside=self.root/'outside.txt'; outside.write_text('secret', encoding='utf8')
        try:
            os.symlink(str(outside), str(self.source/'link.md'))
        except (OSError, NotImplementedError):
            self.skipTest('symlinks not permitted here')
        cmd=[sys.executable,str(ROOT/'scripts'/'p615_preview_official_import.py'),'--official-package',str(self.official),
             '--package-sha256',package_digest(self.official),'--agent','claude-code','--source',str(self.source),
             '--target',str(self.target),'--memory-limit','80','--output',str(self.out),'--i-confirm-disposable-home']
        r=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('symlinks or junctions',r.stderr)


    def test_cli_refuses_junction_in_target_memory_destination(self):
        try:
            import _winapi
        except ImportError:
            self.skipTest('Windows junction test')
        import shutil
        (self.source/'CLAUDE.md').write_text('short', encoding='utf8')
        elsewhere=self.root/'elsewhere'; elsewhere.mkdir()
        shutil.rmtree(self.target/'memories')
        _winapi.CreateJunction(str(elsewhere), str(self.target/'memories'))
        cmd=[sys.executable,str(ROOT/'scripts'/'p615_preview_official_import.py'),'--official-package',str(self.official),
             '--package-sha256',package_digest(self.official),'--agent','claude-code','--source',str(self.source),
             '--target',str(self.target),'--memory-limit','80','--output',str(self.out),'--i-confirm-disposable-home']
        r=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(r.returncode,2)
        self.assertIn('symlinks or junctions',r.stderr)
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__=='__main__':
    unittest.main()
