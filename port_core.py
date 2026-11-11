"""Universal Plugin Port V0: deterministic, request-scoped compatibility staging.

No network, package install, interpreter execution, or Hermes config mutation by
its preview function. All generated artifacts stay in a user-chosen staging dir.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MAX_FILES = 400
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 15_000_000
SAFE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".next", ".idea", "dist", "build", ".cache"}
IGNORE_FILES = {".env", ".env.local", "auth.json", "credentials.json", ".npmrc", ".pypirc", "id_rsa"}
SUSPICIOUS = re.compile(r"(?:authorization|api[_-]?key|access[_-]?token|client[_-]?secret|password)", re.I)
PLACEHOLDERS = {"${PLUGIN_ROOT}", "${PLUGIN_DATA}"}


class PortError(ValueError):
    pass


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:42].strip("-")
    if not value:
        raise PortError("Cannot derive a safe package name")
    if not value[0].isalpha():
        value = "p-" + value
    return value


def safe_child(root: Path, child: str) -> Path:
    if not isinstance(child, str) or not child or "\x00" in child:
        raise PortError("Unsafe empty or invalid component path")
    normalized = child.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[a-zA-Z]:", normalized):
        raise PortError("Absolute path in external manifest rejected")
    parts = Path(normalized).parts
    if ".." in parts or any(p in {".", ""} for p in parts):
        raise PortError("Traversal or empty component in external manifest")
    result = root.joinpath(*parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise PortError("Manifest path resolves outside source tree")
    return result


def enumerate_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise PortError("Source must be a real local directory, not a link")
    items: list[Path] = []
    size = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        c = Path(current)
        if c.is_symlink():
            raise PortError("Directory symlink refused")
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS]
        for d in dirs:
            if (c/d).is_symlink():
                raise PortError("Directory symlink refused")
        for name in sorted(names):
            f = c/name
            if f.is_symlink():
                raise PortError("File symlink refused")
            if not f.is_file():
                continue
            if name in IGNORE_FILES or name.startswith(".env."):
                continue
            n = f.stat().st_size
            if n > MAX_FILE_BYTES:
                raise PortError(f"Oversize file: {f.relative_to(root)}")
            size += n
            items.append(f)
            if len(items) > MAX_FILES or size > MAX_TOTAL_BYTES:
                raise PortError("Source exceeds file/byte quota")
    return items


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise PortError(f"Invalid JSON at {path.name}: {e}") from e
    if not isinstance(obj, dict):
        raise PortError(f"Expected object in {path.name}")
    return obj


def detect(root: Path) -> tuple[str, dict]:
    for profile, loc in (
        ("openclaw", "openclaw.plugin.json"),
        ("codex", ".codex-plugin/plugin.json"),
        ("claude-code", ".claude-plugin/plugin.json"),
        ("portable", "plugin.json"),
    ):
        p = root / loc
        if p.is_file():
            return profile, load_json(p)
    raise PortError("Unsupported source: no recognized Codex, Claude Code, OpenClaw or portable manifest")


def declared_folders(root: Path, manifest: dict, key: str, default: str) -> list[Path]:
    raw = manifest.get(key, default)
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise PortError(f"Invalid {key} field")
    return [safe_child(root, x) for x in raw]


def discover_skills(root: Path, manifest: dict, profile: str) -> list[dict]:
    if profile == "portable":
        roots = [root / "skills"]
    elif profile == "openclaw":
        roots = [root / "skills"]
    else:
        roots = declared_folders(root, manifest, "skills", "./skills")
    result = []
    for skill_root in roots:
        if (skill_root / "SKILL.md").is_file():
            result.append({"name": slug(skill_root.name), "path": str(skill_root.relative_to(root)), "type": "skill"})
        if skill_root.is_dir():
            for d in sorted(skill_root.iterdir()):
                if d.is_dir() and (d / "SKILL.md").is_file():
                    result.append({"name": slug(d.name), "path": str(d.relative_to(root)), "type": "skill"})
    return result


def discover_commands(root: Path, manifest: dict, profile: str) -> list[dict]:
    if profile not in {"codex", "claude-code", "openclaw"}:
        return []
    roots = declared_folders(root, manifest, "commands", "./commands") if profile != "openclaw" else [root/"commands"]
    out=[]
    for d in roots:
        if d.is_file() and d.suffix == ".md":
            out.append({"name": slug(d.stem), "path": str(d.relative_to(root)), "type": "command"})
        elif d.is_dir():
            for f in sorted(d.rglob("*.md")):
                out.append({"name": slug(f.stem), "path": str(f.relative_to(root)), "type": "command"})
    return out


def discover_mcp(root: Path, manifest: dict, profile: str) -> tuple[dict, list[str]]:
    warnings=[]
    if profile == "portable":
        obj = load_json(root / "mcp.json")
        return obj.get("mcpServers", {}), warnings
    if profile == "openclaw":
        # Native OpenClaw's static MCP declaration is NOT safely equivalent to agent-plugin MCP.
        return {}, warnings
    entry = manifest.get("mcpServers")
    if isinstance(entry, str):
        obj=load_json(safe_child(root, entry))
    elif isinstance(entry, dict):
        obj={"mcpServers":entry}
    elif entry is None:
        obj=load_json(root / ".mcp.json")
    else:
        raise PortError("Invalid mcpServers declaration")
    servers = obj.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise PortError("MCP servers must be an object")
    return servers, warnings


def normalize_mcp(servers: dict) -> tuple[dict, list[str]]:
    result={}
    blockers=[]
    for name, raw in servers.items():
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or not isinstance(raw, dict):
            blockers.append(f"mcp:{name}: invalid server name/config")
            continue
        typ = raw.get("type", "stdio" if "command" in raw else None)
        if typ == "stdio":
            exe=raw.get("command")
            args=raw.get("args", [])
            if not isinstance(exe,str) or not exe or not isinstance(args,list) or not all(isinstance(x,str) for x in args):
                blockers.append(f"mcp:{name}: invalid stdio command/args")
                continue
            if re.search(r"\s", exe) and not re.match(r"\$\{(?:PLUGIN_ROOT|CLAUDE_PLUGIN_ROOT)\}",exe):
                blockers.append(f"mcp:{name}: shell-like command rejected")
                continue
            cfg={"type":"stdio", "command":exe.replace("${CLAUDE_PLUGIN_ROOT}", "${PLUGIN_ROOT}"),
                 "args":[x.replace("${CLAUDE_PLUGIN_ROOT}", "${PLUGIN_ROOT}").replace("${CLAUDE_PLUGIN_DATA}","${PLUGIN_DATA}") for x in args]}
        elif typ == "streamable-http":
            from urllib.parse import urlsplit
            url=raw.get("url","")
            u=urlsplit(url)
            if u.scheme != "https" or not u.hostname or u.username or u.fragment:
                blockers.append(f"mcp:{name}: only absolute HTTPS remote urls supported")
                continue
            cfg={"type":"streamable-http","url":url}
        else:
            blockers.append(f"mcp:{name}: unsupported transport {typ}")
            continue
        env = raw.get("env", {})
        if env:
            if not isinstance(env,dict):
                blockers.append(f"mcp:{name}: env must be object")
                continue
            safe_env={}
            for k,v in env.items():
                if not isinstance(v,str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
                    blockers.append(f"mcp:{name}: invalid env")
                    continue
                if SUSPICIOUS.search(k) and not re.fullmatch(r"\$\{[A-Z][A-Z0-9_]*\}", v):
                    blockers.append(f"mcp:{name}: literal secret-like env {k} refused")
                    continue
                safe_env[k]=v.replace("${CLAUDE_PLUGIN_ROOT}","${PLUGIN_ROOT}").replace("${CLAUDE_PLUGIN_DATA}","${PLUGIN_DATA}")
            if safe_env:
                cfg["env"]=safe_env
        if "headers" in raw:
            blockers.append(f"mcp:{name}: custom headers require manual review")
            continue
        result[name]=cfg
    return result,blockers


def source_fingerprint(root: Path, files: list[Path]) -> str:
    h=hashlib.sha256()
    for f in files:
        rel=str(f.relative_to(root)).replace("\\","/")
        h.update(rel.encode()+b"\0"+hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def analyze(source: str) -> dict:
    if source.startswith("https://"):
        raise PortError("V0 is offline-only: clone or download repository to a local folder first; no network access performed")
    root=Path(source).expanduser().resolve()
    files=enumerate_files(root)
    profile, manifest=detect(root)
    skills=discover_skills(root,manifest,profile)
    commands=discover_commands(root,manifest,profile)
    mcp, mcp_warnings=discover_mcp(root, manifest, profile)
    normalized, blockers=normalize_mcp(mcp)
    blockers += mcp_warnings
    issues=[]
    if profile in {"codex","claude-code"}:
        for key in ["hooks", "agents", "apps", "lspServers"]:
            if key in manifest or (root / ("hooks/hooks.json" if key == "hooks" else key)).exists():
                issues.append(f"{key}: host-dependent component, not automatically ported")
        if (root/"hooks/hooks.json").is_file() and not any("hooks:" in x for x in issues):
            issues.append("hooks: not automatically ported")
    if profile == "openclaw":
        # Do not execute foreign source here. Snapshot and inspect only file/manifest metadata.
        entry = openclaw_entry(root)
        if not entry:
            blockers.append("openclaw: no local JavaScript entrypoint (index.js/index.mjs/manifest main)")
        if entry and entry.suffix == ".ts":
            blockers.append("openclaw: TypeScript entrypoint needs a separately approved TS runtime/transpilation")
        issues.append("openclaw: native API tools require explicit trusted execution for registration inspection")
    if not skills and not commands and not normalized and profile != "openclaw":
        blockers.append("no portable skills, markdown commands, or MCP servers found")
    return {"source": str(root), "profile":profile, "name":slug(manifest.get("name") or root.name),
            "fingerprint_sha256":source_fingerprint(root,files),"files_examined":len(files),
            "skills":skills,"commands":commands,"mcp_servers":sorted(normalized),
            "issues":issues,"blockers":blockers,
            "status":"BLOCKED" if blockers else ("REVIEW_REQUIRED" if issues else "PORTABLE_CANDIDATE"),
            "note":"Static preview only: no foreign source executed, no package installed."}


def openclaw_entry(root:Path) -> Path|None:
    manifest=load_json(root/"openclaw.plugin.json")
    pack=load_json(root/"package.json")
    paths=[]
    for field in (manifest.get("main"), pack.get("main")):
        if isinstance(field,str): paths.append(field)
    extensions=pack.get("openclaw",{})
    if isinstance(extensions,dict):
        ext=extensions.get("extensions",[])
        if isinstance(ext,list):paths.extend(x for x in ext if isinstance(x,str))
    paths += ["index.mjs","index.js", "index.cjs","index.ts"]
    for v in paths:
        try:f=safe_child(root,v)
        except PortError:continue
        if f.is_file():return f
    return None


def _defuse_shell(text: str) -> tuple[str, bool]:
    """v0.4.0: never let staged SKILL.md auto-execute source !`cmd` under Hermes
    skills.inline_shell (which matches anywhere, CWD = skill dir)."""
    try:
        from .claude_command import disable_shell_injections, HERMES_INLINE_SHELL
    except ImportError:  # port_cli.py imports this module top-level
        from claude_command import disable_shell_injections, HERMES_INLINE_SHELL
    if not HERMES_INLINE_SHELL.search(text):
        return text, False
    head, sep, body = text.partition("\n---\n\n") if text.startswith("---\n") else ("", "", text)
    return head + sep + disable_shell_injections(body), True


def validate_markdown(source:Path, name:str, kind:str)->str:
    content=source.read_text(encoding="utf-8")
    if not content.strip():raise PortError("Empty skill/command: "+source.name)
    if content.startswith("---\n"):
        end=content.find("\n---\n",4)
        if end!=-1:
            # Rebuild frontmatter from safe fields, preserve body exactly. Do not propagate unsupported metadata.
            content=content[end+5:]
    label="Imported skill" if kind=="skill" else "Imported command instructions"
    front=f"---\nname: {name}\ndescription: {label} ({name}); source requires review before use\n---\n\n"
    return _defuse_shell(front + content.lstrip())[0]


def copy_dir_filtered(src:Path, dest:Path)->None:
    for current,dirs,files in os.walk(src,followlinks=False):
        base=Path(current)
        dirs[:]=[d for d in dirs if d not in SKIP_DIRS]
        for d in dirs:
            if (base/d).is_symlink():raise PortError("Symlink detected during copying")
        rel=base.relative_to(src)
        (dest/rel).mkdir(parents=True,exist_ok=True)
        for name in files:
            f=base/name
            if f.is_symlink():raise PortError("Symlink detected during copying")
            if name in IGNORE_FILES or name.startswith(".env."):continue
            shutil.copy2(f,dest/rel/name)


def write_report(out:Path, report:dict)->None:
    (out/"PORTING_REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# Porting Report", "",f"Source profile: **{report['source_profile']}**",f"Original: `{report['source']}`",
           f"SHA-256 source fingerprint: `{report['source_sha256']}`", "", "## Contract", ""]
    lines += [f"- {k}: {v}" for k,v in report["contract"].items()]
    lines += ["","## Caveats", ""]
    lines += ["- "+x for x in report.get("issues",[])] or ["- None discovered statically"]
    lines += ["","## Verification", "", "- Stage generated: YES", "- Hermes Doctor: NOT RUN", "- Hermes validate: NOT RUN", "- Actual Hermes tool invocation: NOT RUN", "- Runtime behavior parity: NOT VERIFIED", "", "## Consent", "", "- This is a staged artifact, not an installed or activated Hermes plugin.", "- Review its source and permissions, then use Hermes official install/enable commands."]
    (out/"PORTING_REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def stage(source:str, output_root:str, *, approved:bool=False, run_foreign_code:bool=False, allow_partial:bool=False)->dict:
    if approved is not True:
        raise PortError("User installation/staging request is required (approved=true)")
    plan=analyze(source)
    if plan["blockers"]:
        raise PortError("Static blockers: "+"; ".join(plan["blockers"]))
    if plan["issues"] and not allow_partial and plan["profile"] != "openclaw":
        raise PortError("Non-portable components found. Require explicit allow_partial after review: "+"; ".join(plan["issues"]))
    root=Path(plan["source"])
    destroot=Path(output_root).expanduser().resolve()
    if destroot==root or destroot.is_relative_to(root):
        raise PortError("Destination cannot be inside source tree")
    if root.is_relative_to(destroot):
        raise PortError("Source cannot be inside destination tree")
    destroot.mkdir(parents=True,exist_ok=True)
    product=slug("port-"+plan["profile"]+"-"+plan["name"])
    final=destroot/product
    if final.exists():
        raise PortError("Refusing to overwrite existing staged output: "+str(final))
    # Work in a temp dir; no half-product is published on failure.
    with tempfile.TemporaryDirectory(prefix=".port-stage-",dir=destroot) as tmp:
        out=Path(tmp)/product
        out.mkdir()
        if plan["profile"]=="openclaw":
            if run_foreign_code is not True:
                raise PortError("OpenClaw native tool needs separate explicit code-execution permission (run_foreign_code=true)")
            report=stage_openclaw(root,out,product,plan,allow_partial)
        else:
            report=stage_portable(root,out,product,plan,allow_partial)
        write_report(out,report)
        out.replace(final)
    return {"ok":True,"staged_path":str(final),"report_path":str(final/"PORTING_REPORT.json"),
            "source_profile":plan["profile"],"verification":"STAGED_ONLY","next_step":f"hermes plugins doctor '{final}' --ci; hermes plugins validate '{final}' --install-deps; review and explicitly install"}


def stage_portable(root:Path,out:Path,product:str,plan:dict,allow_partial:bool)->dict:
    profile, manifest=detect(root)
    # Sources already portable can be copied by review, no need to rewrite runtime semantics.
    used=set()
    contract={"portable_skills":0,"converted_commands":0,"mcp_servers":0}
    for item in plan["skills"]+plan["commands"]:
        name=item["name"]
        if name in used:
            raise PortError("Duplicate normalized skill name: "+name)
        used.add(name)
        src=safe_child(root,item["path"])
        target=out/"skills"/name
        if item["type"]=="skill":
            copy_dir_filtered(src,target)
            content=validate_markdown(src/"SKILL.md",name,"skill")
            (target/"SKILL.md").write_text(content,encoding="utf-8")
            contract["portable_skills"]+=1
        else:
            target.mkdir(parents=True,exist_ok=True)
            (target/"SKILL.md").write_text(validate_markdown(src,name,"command"),encoding="utf-8")
            contract["converted_commands"]+=1
    mcp,_=discover_mcp(root, manifest, profile)
    normalized,blocked=normalize_mcp(mcp)
    if blocked:
        raise PortError("MCP conversion blocked: "+"; ".join(blocked))
    # MCP launch paths often depend on plugin-relative source files. Preserve the
    # original tree (excluding credentials and dependency/cache directories) and
    # redirect only plugin-root placeholders to the staged source snapshot.
    if normalized:
        copy_dir_filtered(root, out/"original")
        for cfg in normalized.values():
            if cfg["type"] == "stdio":
                for key in ("command",):
                    cfg[key] = cfg[key].replace("${PLUGIN_ROOT}/", "${PLUGIN_ROOT}/original/")
                cfg["args"] = [a.replace("${PLUGIN_ROOT}/", "${PLUGIN_ROOT}/original/") for a in cfg["args"]]
                for a in [cfg["command"], *cfg["args"]]:
                    if a.startswith("${PLUGIN_ROOT}/original/"):
                        rel=a.split("${PLUGIN_ROOT}/original/", 1)[1]
                        if not safe_child(root, rel).exists():
                            raise PortError("Referenced local MCP executable/file not found: " + rel)
                if "env" in cfg:
                    cfg["env"]={k:v.replace("${PLUGIN_ROOT}/", "${PLUGIN_ROOT}/original/") for k,v in cfg["env"].items()}
        (out/"mcp.json").write_text(json.dumps({"$schema":"https://agent-plugins.org/schemas/1.0.0/mcp.schema.json","mcpServers":normalized},indent=2)+"\n",encoding="utf-8")
    contract["mcp_servers"]=len(normalized)
    (out/"plugin.json").write_text(json.dumps({"$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name":product,"version":"0.1.0","description":f"Ported {profile} components from {plan['name']} (user-reviewed staging)"},indent=2)+"\n",encoding="utf-8")
    issues=list(plan["issues"])
    if normalized:
        # portable MCP process cwd / paths are not guaranteed to match source project.
        issues.append("MCP launch paths and dependency installation are not validated; inspect mcp.json before activation")
    if contract["converted_commands"]:
        issues.append("Commands converted to skills; slash-command invocation semantics are not preserved")
    return {"source_profile":profile,"source":str(root),"source_sha256":plan["fingerprint_sha256"],
            "contract":contract,"issues":issues,"partial":bool(issues),"status":"STAGED_ONLY"}


def stage_openclaw(root:Path,out:Path,product:str,plan:dict,allow_partial:bool)->dict:
    entry=openclaw_entry(root)
    if entry is None or entry.suffix not in {".mjs",".js",".cjs"}:
        raise PortError("Only JavaScript OpenClaw entrypoints are available in this V0")
    sidecar=Path(__file__).parent/"sidecar.mjs"
    if not sidecar.is_file():raise PortError("Missing adapter sidecar.mjs")
    # No automatic dependency installation. Running inspected code is explicitly opted in.
    p=invoke_node(sidecar,"inspect",entry,{})
    tools=p.get("tools",[])
    unsupported=p.get("unsupported",[])
    if unsupported and not allow_partial:
        raise PortError("Native APIs not mapped: "+", ".join(sorted(set(unsupported)))+"; require allow_partial")
    if not tools:
        raise PortError("No registerTool tools detected during runtime inspection")
    names=set()
    specs=[]
    for t in tools:
        n=t.get("name")
        if not isinstance(n,str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,40}",n):
            raise PortError("Unsafe/invalid OpenClaw tool name")
        if n in names:raise PortError("Duplicate OpenClaw tool name: "+n)
        names.add(n)
        params=t.get("parameters")
        if not isinstance(params,dict) or params.get("type") not in ("object",None):
            raise PortError("Invalid JSON Schema for OpenClaw tool "+n)
        specs.append({"name":n,"description":str(t.get("description",n))[:500],"parameters":params or {"type":"object","properties":{}}})
    src_dest=out/"source"
    copy_dir_filtered(root,src_dest)
    shutil.copy2(sidecar,out/"sidecar.mjs")
    rel=str(entry.relative_to(root)).replace("\\","/")
    (out/"tool_specs.json").write_text(json.dumps(specs,indent=2)+"\n",encoding="utf-8")
    # Template can be reviewed as plain Python. No dependencies from the port generator needed.
    entrypoint=(Path(__file__).parent/"generated_openclaw_entry.py").read_text(encoding="utf-8")
    entrypoint=entrypoint.replace("__ENTRY_REL__",repr(rel))
    (out/"__init__.py").write_text(entrypoint,encoding="utf-8")
    (out/"plugin.yaml").write_text("name: "+product+"\nversion: 0.1.0\ndescription: User-reviewed native OpenClaw JavaScript tool adapter; external Node runtime required.\nprovides_tools:\n"+"".join("  - "+("ported_"+slug(product).replace("-","_")[:23]+"_"+x)[:63]+"\n" for x in names),encoding="utf-8")
    return {"source_profile":"openclaw","source":str(root),"source_sha256":plan["fingerprint_sha256"],
            "contract":{"native_tools":len(tools),"runtime":"Node.js (separate child process)","entrypoint":rel},
            "issues":["Executes user-approved external JavaScript on inspection and every tool call", "No sandbox isolation from host filesystem/network; approval is essential", "No npm install performed; external JS dependencies must be present", "Original OpenClaw host services are not emulated"] + ["Unmapped APIs: "+", ".join(unsupported)] if unsupported else ["Executes user-approved external JavaScript on inspection and every tool call", "No sandbox isolation from host filesystem/network; approval is essential", "No npm install performed; external JS dependencies must be present", "Original OpenClaw host services are not emulated"],"partial":bool(unsupported),"status":"STAGED_ONLY"}


def invoke_node(sidecar:Path,mode:str,entry:Path,payload:dict)->dict:
    env={k:v for k,v in os.environ.items() if k.upper() in {"PATH","PATHEXT","SYSTEMROOT","WINDIR","TMP","TEMP","TMPDIR","HOME","USERPROFILE","COMSPEC","NODE_ENV"}}
    env["NODE_ENV"]="production"
    try:
        p=subprocess.run(["node",str(sidecar),mode,str(entry)],input=json.dumps(payload),capture_output=True,text=True,encoding="utf-8",timeout=12,env=env)
    except (OSError,subprocess.TimeoutExpired) as e:
        raise PortError("Node inspect/run unavailable or timed out: "+str(e)) from e
    out=p.stdout[-2_000_000:]
    lines=[line[len("PORT_RESULT:"):] for line in out.splitlines() if line.startswith("PORT_RESULT:")]
    if p.returncode!=0 or not lines:
        raise PortError("Native adapter failed (no secrets included): "+p.stderr[-500:].replace("\n"," "))
    try:obj=json.loads(lines[-1])
    except json.JSONDecodeError as e:raise PortError("Adapter returned non-JSON") from e
    if isinstance(obj,dict) and obj.get("error"):
        raise PortError(str(obj["error"])[:300])
    if not isinstance(obj,dict):raise PortError("Invalid adapter result")
    return obj

# Remote source acquisition is separate from port analysis and stage/installation.
# It downloads source only from GitHub's API and codeload hosts, pins a commit,
# and extracts inert bytes without invoking Git hooks, package managers or scripts.

def _github_json(url: str) -> Any:
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.parse import urlsplit
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise PortError('GitHub metadata redirect rejected')
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname != 'api.github.com':
        raise PortError('Untrusted GitHub metadata endpoint')
    req=Request(url,headers={'User-Agent':'hermes-universal-port-v0.1', 'Accept':'application/vnd.github+json'})
    with build_opener(NoRedirect()).open(req,timeout=15) as r:
        if urlsplit(r.geturl()).hostname!='api.github.com':
            raise PortError('GitHub metadata redirect rejected')
        payload=r.read(3_000_001)
    if len(payload)>3_000_000:raise PortError('Oversized GitHub response')
    try:return json.loads(payload)
    except (ValueError,UnicodeError) as e:raise PortError('Invalid GitHub API response') from e


def _github_zip(url: str) -> bytes:
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.parse import urlsplit
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise PortError('GitHub source archive redirect rejected')
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname!='codeload.github.com':
        raise PortError('Untrusted code archive endpoint')
    req=Request(url,headers={'User-Agent':'hermes-universal-port-v0.1'})
    with build_opener(NoRedirect()).open(req,timeout=30) as r:
        if urlsplit(r.geturl()).hostname!='codeload.github.com':
            raise PortError('Source archive redirect rejected')
        raw=r.read(MAX_TOTAL_BYTES+1)
    if len(raw)>MAX_TOTAL_BYTES:raise PortError('Oversized GitHub archive')
    return raw



def _fetch_sparse_subdir(owner: str, repo: str, commit: str, subdir: str, folder: Path) -> None:
    """Read only a user-selected subdirectory through GitHub Contents API.

    Avoid downloading the entirety of large monorepos (and leaking quota to
    unrelated source paths). Refuse symlinks and oversized trees/files.
    """
    import base64
    from urllib.parse import quote
    qpath = lambda p: '/'.join(quote(segment, safe='') for segment in p.split('/'))
    queue = [subdir]
    files = 0
    bytes_total = 0
    seen = set()
    while queue:
        remote = queue.pop(0)
        if remote in seen:
            raise PortError('Duplicate remote directory returned')
        seen.add(remote)
        if len(seen) > MAX_FILES:
            raise PortError('Source has too many directories')
        listing = _github_json(f'https://api.github.com/repos/{owner}/{repo}/contents/{qpath(remote)}?ref={commit}')
        if not isinstance(listing, list):
            raise PortError('Subdirectory not found or is not a directory: ' + remote)
        for item in listing:
            if not isinstance(item, dict):
                raise PortError('Invalid GitHub directory entry')
            typ = item.get('type')
            path = item.get('path')
            if not isinstance(path, str) or not path.startswith(subdir + '/'):
                raise PortError('GitHub directory entry escaped selected subdirectory')
            rel = path[len(subdir)+1:]
            target = safe_child(folder, rel)
            if any(part in SKIP_DIRS for part in target.relative_to(folder).parts):
                continue
            if typ == 'dir':
                queue.append(path)
                continue
            if typ != 'file':
                raise PortError(f'Refusing non-regular file type {typ}: {rel}')
            if target.name in IGNORE_FILES or target.name.startswith('.env.'):
                continue
            size = item.get('size')
            if not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
                raise PortError('Oversized/invalid file in GitHub tree: ' + rel)
            files += 1
            bytes_total += size
            if files > MAX_FILES or bytes_total > MAX_TOTAL_BYTES:
                raise PortError('Source exceeds file/byte quota')
            # api.github.com is the only network endpoint used, and all revisions
            # are pinned. File content never gets executed while fetching.
            data = _github_json(f'https://api.github.com/repos/{owner}/{repo}/contents/{qpath(path)}?ref={commit}')
            if not isinstance(data,dict) or data.get('type') != 'file' or data.get('encoding') != 'base64':
                raise PortError('GitHub file API did not return base64 file: ' + rel)
            try:
                raw = base64.b64decode(data['content'], validate=False)
            except (ValueError, KeyError, TypeError) as e:
                raise PortError('Cannot decode GitHub file: ' + rel) from e
            if len(raw) != size:
                raise PortError('GitHub file byte count changed: ' + rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

def fetch_github(repo_url: str, download_root: str, *, approved:bool=False) -> dict:
    if approved is not True:raise PortError('Explicit user-approved GitHub source request required')
    from urllib.parse import urlsplit
    from zipfile import ZipFile, BadZipFile
    from io import BytesIO
    url=urlsplit(repo_url)
    if url.scheme!='https' or url.hostname not in {'github.com','www.github.com'} or url.username or url.password or url.query or url.fragment:
        raise PortError('Only public github.com HTTPS repository URLs supported')
    parts=[x for x in url.path.strip('/').split('/') if x]
    if len(parts)<2 or not all(re.fullmatch('[a-zA-Z0-9_.-]+',x) for x in parts[:2]):
        raise PortError('Invalid public GitHub owner/repository URL')
    owner,repo=parts[:2]
    repo=repo[:-4] if repo.endswith('.git') else repo
    if len(parts)==2:
        selector=None; subdir=''
    elif len(parts)>=4 and parts[2]=='tree' and re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',parts[3]):
        selector=parts[3];subdir='/'.join(parts[4:])
    else:
        raise PortError('Use repo root URL or /tree/<branch-or-40-character-commit>/<subdirectory>')
    if selector is None:
        meta=_github_json(f'https://api.github.com/repos/{owner}/{repo}')
        selector=meta.get('default_branch')
    if not isinstance(selector,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',selector):
        raise PortError('Cannot resolve GitHub revision')
    if not re.fullmatch('[a-fA-F0-9]{40}',selector):
        from urllib.parse import quote
        commit=_github_json(f'https://api.github.com/repos/{owner}/{repo}/commits/{quote(selector,safe="")}')
        selector=commit.get('sha')
    if not isinstance(selector,str) or not re.fullmatch('[a-fA-F0-9]{40}',selector):
        raise PortError('Could not pin source to exact commit')
    content=None if subdir else _github_zip(f'https://codeload.github.com/{owner}/{repo}/zip/{selector}')
    destroot=Path(download_root).expanduser().resolve()
    dest=destroot/slug('source-'+owner+'-'+repo+'-'+selector[:10])
    if destroot.exists() and dest.exists():raise PortError('Source download destination exists; refusing overwrite')
    destroot.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.github-source-',dir=destroot) as td:
        folder=Path(td)/'content';folder.mkdir()
        files=0;size=0
        if subdir:
            _fetch_sparse_subdir(owner, repo, selector, subdir, folder)
        else:
            pass
        if content is None:
            archive = None
        else:
            try: archive=ZipFile(BytesIO(content))
            except BadZipFile as e:raise PortError('GitHub returned invalid ZIP') from e
        if archive is not None:
          with archive:
            for item in archive.infolist():
                # GitHub codeload always inserts one leading owner-repo-sha prefix.
                path_parts=item.filename.replace('\\','/').split('/')
                if len(path_parts)<2 or not path_parts[0] or item.is_dir():continue
                rel='/'.join(path_parts[1:]).strip('/')
                if not rel:continue
                if subdir:
                    subparts=subdir.split('/')
                    if rel.split('/')[:len(subparts)]!=subparts:continue
                    rel='/'.join(rel.split('/')[len(subparts):])
                    if not rel:continue
                if (item.external_attr >> 16)&0o170000 == 0o120000:
                    raise PortError('GitHub source archive contains symlinks')
                f=safe_child(folder,rel)
                if any(part in SKIP_DIRS for part in f.relative_to(folder).parts):continue
                if f.name in IGNORE_FILES or f.name.startswith('.env.'):continue
                files+=1;size+=item.file_size
                if files>MAX_FILES or item.file_size>MAX_FILE_BYTES or size>MAX_TOTAL_BYTES:
                    raise PortError('GitHub archive exceeds decompressed limits')
                f.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(item) as reader, f.open('wb') as writer:
                    shutil.copyfileobj(reader,writer,length=65536)
        # Do not even return a success on an unsupported manifest; user should get a clear report.
        detected,_=detect(folder)
        folder.replace(dest)
    return {'ok':True,'source_path':str(dest),'commit_sha':selector,'profile':detected,
            'status':'FETCHED_NOT_EXECUTED','note':'Read-only source acquisition; review and call port_probe next. No code executed or installed.'}
