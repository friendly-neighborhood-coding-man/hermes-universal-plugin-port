"""Generated standalone Hermes tool wrapper for user-approved OpenClaw plugin.

Every tool execution starts an external Node process. This is not a sandbox.
"""
import json
import os
import subprocess
from pathlib import Path

_SOURCE = Path(__file__).parent
_ENTRY = _SOURCE / 'source' / __ENTRY_REL__
_SIDECAR = _SOURCE / 'sidecar.mjs'
_SPECS = json.loads((_SOURCE / 'tool_specs.json').read_text(encoding='utf-8'))


def register(ctx):
    prefix = 'ported_' + _SOURCE.name.replace('-', '_')[:23] + '_'
    for spec in _SPECS:
        name = (prefix + spec['name'])[:63]
        schema = {
            'name': name,
            'description': 'Ported OpenClaw tool (user-approved JS execution): ' + spec['description'],
            'parameters': spec.get('parameters') or {'type':'object','properties':{}},
        }
        def handler(args, _tool=spec['name'], **kwargs):
            # Ignore foreign environment credentials and avoid shell invocation.
            allow = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP', 'TMPDIR', 'HOME', 'USERPROFILE', 'COMSPEC'}
            env = {k:v for k,v in os.environ.items() if k.upper() in allow}
            env['NODE_ENV'] = 'production'
            try:
                p = subprocess.run(['node', str(_SIDECAR), 'call', str(_ENTRY)],
                    input=json.dumps({'tool':_tool, 'args':args}, ensure_ascii=False),
                    capture_output=True, text=True, encoding='utf-8', timeout=15, env=env)
                lines = [x[len('PORT_RESULT:'):] for x in p.stdout.splitlines() if x.startswith('PORT_RESULT:')]
                if p.returncode != 0 or not lines:
                    return json.dumps({'error': 'Ported tool failed (see local plugin logs)'})
                data = json.loads(lines[-1])
                return json.dumps(data, ensure_ascii=False)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                return json.dumps({'error': 'Ported tool timed out or returned invalid data'})
        ctx.register_tool(name=name, toolset='ported_openclaw', schema=schema, handler=handler)
