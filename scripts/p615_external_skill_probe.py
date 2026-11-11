"""Preview at least two reviewed external Skill packages with real official importer on 3 hosts.

Copies Skill package directories into temporary agent layouts only. No install/model call.
This is structural preview, NOT runtime semantic equivalence.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.p615_preview_official_import import package_digest
from scripts.p615_dogfood_matrix import _home_snapshot,_write,PINNED_OFFICIAL_COMMIT

AGENTS=("claude-code","codex","cursor")


def validate_packs(paths):
    if len(paths)<2: raise ValueError("require at least two independent Skill package folders")
    out=[];seen=set()
    for value in paths:
        root=value.resolve(strict=True)
        if value.is_symlink() or not root.is_dir() or not (root/"SKILL.md").is_file():
            raise ValueError("each package must be a real directory containing SKILL.md")
        slug=root.name.lower()
        if slug in seen or not slug or "/" in slug:
            raise ValueError("duplicate or invalid Skill folder names")
        seen.add(slug)
        count=0;size=0
        for base,dirs,files in os.walk(root,followlinks=False):
            for name in dirs+files:
                path=Path(base)/name
                if path.is_symlink(): raise ValueError("symlinks prohibited in Skill package fixture")
                if path.is_file():
                    count+=1;size+=path.stat().st_size
                    if count>300 or size>5_000_000: raise ValueError("Skill package exceeds fixture bounds")
        out.append((slug,root))
    return out


def probe(packs,official,revision):
    git=subprocess.run(["git","-C",str(official.parent),"rev-parse","HEAD"],
                       capture_output=True,text=True,timeout=15)
    if git.returncode or git.stdout.strip()!=revision: raise ValueError("official revision mismatch")
    digest=package_digest(official)
    rows=[]
    with tempfile.TemporaryDirectory(prefix="p615-reviewed-skills-") as d:
        for agent in AGENTS:
            root=Path(d)/agent
            source=root/{"claude-code":".claude","codex":".codex","cursor":".cursor"}[agent]
            source.mkdir(parents=True)
            for name,path in packs:
                dest=source/"skills"/("reviewed" if agent=="cursor" else "")/name
                shutil.copytree(path,dest,symlinks=False)
            home=root/"disposable-home";home.mkdir()
            _write(home/"memories"/"MEMORY.md","Existing user memory.\n")
            before=_home_snapshot(home)
            receipt_path=root/"receipt.json"
            cli=Path(__file__).with_name("p615_preview_official_import.py")
            command=[sys.executable,str(cli),"--official-package",str(official),
                     "--package-sha256",digest,"--agent",agent,"--source",str(source),
                     "--target",str(home),"--memory-limit","2200",
                     "--output",str(receipt_path),"--i-confirm-disposable-home"]
            task=subprocess.run(command,capture_output=True,text=True,timeout=45,
                                env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
            receipt=json.loads(receipt_path.read_text(encoding="utf8")) if receipt_path.is_file() else None
            skill_rows=[] if receipt is None else [r for r in receipt["ledger"] if r["kind"]=="skill"]
            names={Path(r["source"]).name for r in skill_rows}
            unchanged=before==_home_snapshot(home)
            passed=(task.returncode==0 and receipt is not None and receipt["gate"]=="REVIEW_ONLY"
                    and all(name in names for name,_ in packs) and unchanged
                    and receipt.get("apply_performed") is False)
            rows.append({"agent":agent,"skill_packages":[name for name,_ in packs],
                         "reported_skill_rows":len(skill_rows),
                         "gate":receipt["gate"] if receipt else "NO_RECEIPT",
                         "target_unchanged":unchanged,"pass":passed,
                         "stderr_excerpt":task.stderr[:1000]})
    return {"schema":"uvp.p615.external-skills-preview/1","upstream_sha":revision,
            "results":rows,"passed":sum(row["pass"] for row in rows),"total":len(rows),
            "scope":"real official importer PREVIEW only; reviewed local Skill source files; no installation",
            "limitation":"Structural copy planning does not certify execution, resources, MCP, hooks, or semantic equivalence"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--official-package",type=Path,required=True)
    p.add_argument("--official-sha",default=PINNED_OFFICIAL_COMMIT)
    p.add_argument("--skill-pack",type=Path,action="append",required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    if a.report.exists():p.error("create-only report path required")
    try:
        output=probe(validate_packs(a.skill_pack),a.official_package.resolve(strict=True),a.official_sha)
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(output,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
        print(f"Reviewed Skill packs: {output['passed']}/{output['total']} previews PASS")
        return 0 if output["passed"]==output["total"] else 1
    except Exception as e:
        print(f"HOLD: {type(e).__name__}: {e}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
