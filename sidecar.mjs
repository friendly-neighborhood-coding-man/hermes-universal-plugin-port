// V0 user-approved OpenClaw native JavaScript tool bridge.
// Loads only a local, previously staged source file. It is NOT a security sandbox.
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import path from 'node:path';

const [, , mode, entry] = process.argv;
const prefix = 'PORT_RESULT:';
let tools = new Map();
let unsupported = [];
function emit(data) { process.stdout.write(prefix + JSON.stringify(data) + '\n'); }
function note(s) { unsupported.push(s); }
const api = {
  registerTool(spec) {
    if (typeof spec?.name !== 'string' || typeof spec?.execute !== 'function') {
      throw Error('registerTool requires name and execute function');
    }
    tools.set(spec.name, spec);
  },
  on(event) { note('on:' + String(event)); },
  registerHook(name) { note('registerHook:' + String(name)); },
  registerService(s) { note('registerService:' + String(s?.id ?? 'unknown')); },
  registerChannel(s) { note('registerChannel:' + String(s?.id ?? 'unknown')); },
  registerCommand(s) { note('registerCommand:' + String(s?.name ?? 'unknown')); },
  registerProvider(s) { note('registerProvider:' + String(s?.id ?? 'unknown')); },
  logger: {
    info(...items) { console.error('[foreign log]', ...items); },
    warn(...items) { console.error('[foreign warn]', ...items); },
    error(...items) { console.error('[foreign error]', ...items); },
    debug() {},
  },
};
try {
  if (!['inspect', 'call'].includes(mode) || !entry || !path.isAbsolute(entry)) {
    throw Error('bad invocation');
  }
  const module = entry.endsWith('.cjs') ? createRequire(import.meta.url)(entry) : await import(pathToFileURL(entry).href);
  const plugin = module?.default ?? module;
  const register = typeof plugin === 'function' ? plugin
    : typeof plugin?.register === 'function' ? plugin.register.bind(plugin)
    : typeof plugin?.activate === 'function' ? plugin.activate.bind(plugin)
    : null;
  if (!register) throw Error('no register(api) or activate(api) export');
  await register(api);
  if (mode === 'inspect') {
    emit({ tools: [...tools.values()].map(t => ({
      name: t.name, description: t.description ?? t.name,
      parameters: t.parameters ?? t.inputSchema ?? {type: 'object', properties: {}},
    })), unsupported });
  } else {
    let raw='';
    for await (const chunk of process.stdin) {
      raw += chunk;
      if (raw.length > 200_000) throw Error('request size limit');
    }
    const payload = JSON.parse(raw);
    if (unsupported.length) throw Error('unsupported host APIs: ' + unsupported.join(', '));
    const tool = tools.get(payload.tool);
    if (!tool) throw Error('tool not registered: ' + String(payload.tool));
    const result = await tool.execute('hermes-port', payload.args ?? {});
    emit({ result });
  }
} catch (err) {
  emit({ error: String(err?.message ?? err).slice(0, 350) });
  process.exitCode = 1;
}
