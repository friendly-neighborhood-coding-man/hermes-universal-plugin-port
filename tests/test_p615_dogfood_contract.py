"""Contract test for synthetic official-API-compatible dogfood runner ONLY."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
FAKE='''\
from pathlib import Path
ENTRY_DELIMITER="\\n§\\n"
def parse_existing_memory_entries(p):
    return [v.strip() for v in p.read_text(encoding="utf8").split(ENTRY_DELIMITER) if v.strip()] if p.exists() else []
def merge_entries(existing,incoming,limit):
    merged=list(existing)
    stats={"existing":len(merged),"added":0,"duplicates":0,"overflowed":0}
    for item in incoming:
        if item in merged: stats["duplicates"]+=1
        elif len(ENTRY_DELIMITER.join(merged+[item]))>limit: stats["overflowed"]+=1
        else: merged.append(item); stats["added"]+=1
    return merged,stats
class AgentImporter:
    def __init__(self,agent,source,target,execute=False,overwrite=False):
        self.agent=agent;self.source_root=Path(source);self.target_root=Path(target);self.execute=execute;self.items=[]
    def record(self,kind,source,destination,status,reason="",**kwargs):
        self.items.append(dict(kind=kind,source=str(source),destination=str(destination),status=status,reason=reason))
    def merge_memory_entries(self,*args): raise AssertionError("assurance interceptor not installed")
    def run(self):
        src=self.source_root
        context={"claude-code":"CLAUDE.md","codex":"AGENTS.md","cursor":"AGENTS.md"}[self.agent]
        p=src/context
        if p.is_file():
            content=p.read_text(encoding="utf8").strip().split("\\n\\n")[-1]
            self.merge_memory_entries("memory",p,self.target_root/"memories"/"MEMORY.md",[content])
        category={"claude-code":"claude-code-imports","codex":"codex-imports","cursor":"cursor-imports"}[self.agent]
        for item in sorted((src/"skills").rglob("SKILL.md")):
            dest=self.target_root/"skills"/category/item.parent.name
            self.record("skill",item.parent,dest,"conflict" if dest.exists() else "imported")
        return {"agent":self.agent,"dry_run":True,"items":self.items}
'''


class DogfoodRunnerContract(unittest.TestCase):
    def test_three_agents_three_scenarios_with_test_double(self):
        with tempfile.TemporaryDirectory(prefix="p615-harness-") as tmp:
            root=Path(tmp); upstream=root/"upstream"; package=upstream/"agent-importers"
            package.mkdir(parents=True)
            (package/"__init__.py").write_text("",encoding="utf8")
            (package/"importer.py").write_text(FAKE,encoding="utf8")
            for args in (["git","init","-q",str(upstream)],
                         ["git","-C",str(upstream),"add","."],
                         ["git","-C",str(upstream),"-c","user.name=Fixture",
                          "-c","user.email=fixture@example.org","commit","-qm","synthetic"]):
                subprocess.run(args,check=True,capture_output=True,text=True,timeout=20)
            sha=subprocess.check_output(["git","-C",str(upstream),"rev-parse","HEAD"],text=True).strip()
            report=root/"dogfood.json"
            run=subprocess.run([sys.executable,str(ROOT/"scripts"/"p615_dogfood_matrix.py"),
                                "--official-package",str(package),"--expected-upstream-sha",sha,
                                "--report",str(report)],capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stderr)
            result=json.loads(report.read_text(encoding="utf8"))
            self.assertEqual(result["pass"],9)
            self.assertEqual(result["total"],9)
            self.assertTrue(all(x["assertions"]["target_unchanged"] for x in result["cases"]))
            self.assertTrue(all(x["assertions"]["two_skills_accounted"] for x in result["cases"]))


if __name__=="__main__":
    unittest.main()
