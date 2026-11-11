"""Hermes Universal Plugin Port: explicit URL slash-command and tool surface."""
import json
from .port_core import analyze, stage, fetch_github, PortError


def register(ctx):
    def response(fn):
        def wrap(args: dict, **kwargs):
            try:
                return json.dumps(fn(args or {}), ensure_ascii=False)
            except PortError as exc:
                return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
            except Exception:
                return json.dumps({"ok":False, "error":"Port failed unexpectedly; no installation was performed"})
        return wrap

    @response
    def probe(args):
        return analyze(args.get('source', ''))

    @response
    def fetch(args):
        return fetch_github(args.get('url', ''), args.get('output_dir', ''), approved=args.get('approved',False))

    @response
    def build(args):
        return stage(args.get('source', ''), args.get('output_dir', ''),
                     approved=args.get('approved', False),
                     run_foreign_code=args.get('run_foreign_code', False),
                     allow_partial=args.get('allow_partial', False))

    from .port_flow import command as run_slash_command
    ctx.register_command(
        'universal-port',
        handler=lambda raw: run_slash_command(ctx, raw),
        description='Fetch, model-adapt and verify a user-specified GitHub plugin for Hermes',
        args_hint='<GitHub URL>',
    )

    ctx.register_tool(name='port_probe', toolset='universal_port', schema={
        'name':'port_probe',
        'description':'Analyze a local Codex, Claude Code or OpenClaw plugin without running its code or installing anything. User must provide source folder; results are untrusted and require review.',
        'parameters':{'type':'object','properties':{
            'source':{'type':'string','description':'Absolute path to user-named local plugin directory'}},'required':['source']}}, handler=probe)
    ctx.register_tool(name='port_fetch', toolset='universal_port', schema={
        'name':'port_fetch',
        'description':'Only on explicit user request: download a public GitHub repo at a pinned immutable commit into a local staging directory. Never executes downloaded code, installs dependencies or enables plugins. Accept only github.com URL.',
        'parameters':{'type':'object','properties':{
            'url':{'type':'string','description':'Public github.com repository URL or exact /tree/<SHA>/path'},
            'output_dir':{'type':'string','description':'Local source staging root; no overwrite'},
            'approved':{'type':'boolean','description':'User explicitly asked to fetch and port this repository'}},
            'required':['url','output_dir','approved']}}, handler=fetch)
    ctx.register_tool(name='port_stage', toolset='universal_port', schema={
        'name':'port_stage',
        'description':'Only after the user explicitly requests porting: stage a Hermes compatible package in a chosen directory. Does NOT install/enable it. Foreign OpenClaw JS requires separate informed permission to execute run_foreign_code, since it is NOT sandboxed. Unsupported components require allow_partial explicitly approved by user.',
        'parameters':{'type':'object','properties':{
            'source':{'type':'string','description':'Local plugin root already analyzed by port_probe'},
            'output_dir':{'type':'string','description':'Separate directory to stage outputs; no overwrite'},
            'approved':{'type':'boolean','description':'True only if user requested this particular plugin be ported'},
            'run_foreign_code':{'type':'boolean','description':'For OpenClaw: user separately consented to executing external JS during inspection (unsafe outside sandbox)'},
            'allow_partial':{'type':'boolean','description':'User accepted explicitly listed unsupported original capabilities'}},
            'required':['source','output_dir','approved']}}, handler=build)

    # Route and candidate discovery remain preview-only. P5 exposes one
    # explicitly operator-approved, default-disabled Hermes CLI arXiv action.
    # Existing /universal-port, port_probe, port_fetch and port_stage are unchanged.
    from .uvp_plugin_router import register_router
    register_router(ctx)
