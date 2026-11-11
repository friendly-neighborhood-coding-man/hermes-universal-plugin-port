# P5 v0.5.4 operator-observed unknown session and v0.5.5 diagnostic

**Status:** Operator observed fail-closed preview, not successful Hermes execution.

## Operator console (2026-11-10 KST)

Command: `/uvp --surface` returned:

```json
{
  "schema": "universal-port.session-diagnostic/1",
  "session_surface": "unknown",
  "local_surface_permitted": false,
  "live_execution_opt_in": false,
  "execution_performed": false
}
```

Command: `/uvp --arxiv-execute 1706.03762v1 25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84`
returned `DISABLED_BY_DEFAULT`, `execution_performed=false`, with
`approved_capabilities_added=0` and the exact same request hash.

This confirms default-denied behavior in the operator's actual Hermes
terminal. The output **cannot** distinguish if `ctx.session_surface()`
raised an exception, returned `""`, `"local"`, or another unknown
value because v0.5.4 collapsed all of these to `unknown`.

## Upstream code evidence

Upstream Hermes plugin dispatch code in
[`gateway/run_inbound_hooks.py`](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e3/gateway/run_inbound_hooks.py)
passes `platform=source.platform.value` as a keyword to plugin slash
commands. `Platform.LOCAL.value` is `"local"`, not necessarily the
client subtype `"cli"` / `"tui"`.
`hermes_cli/plugin_session.py` obtains the context surface from
session policy or `HERMES_SESSION_PLATFORM`, while the plugin
slash-command handler runs in a distinct dispatch path.

**Hypothesis:** The source reports generic `"local"`, or no session
surface is bound at slash-command time. The v0.5.4 output alone cannot
prove which case occurred.

## v0.5.5 diagnostic-only correction

- `/uvp --surface` now opts into Hermes's official handler-provided
  `platform` keyword without reading session IDs, source object or tokens.
- Reports `session_surface_lookup`: `recognized`, `generic_local`,
  `empty`, `unrecognized`, or `exception`; reports a sanitized
  `host_dispatch_platform`.
- Upgrades the read-only diagnostic schema to
  `universal-port.session-diagnostic/2`.
- **Critically, no execution authorization uses
  `host_dispatch_platform="local"`.** The original strict `cli`/ `tui`
  check remains; any unknown/generic value cannot execute a request.
- Existing `UVP_ENABLE_ARXIV_EXECUTION=0` still denies all actual
  arXiv access before source verification and user consent.
- Added offline tests for generic-local, empty and exceptional context
  and a negative test proving `platform="local"` cannot bypass
  the runtime gate.

## Next verification

Run updated v0.5.5 offline tests, full suite, and Hermes Plugin Doctor
before replacing the existing disposable-profile v0.5.4 installation.
Then keep `UVP_ENABLE_ARXIV_EXECUTION=0` and run
`/uvp --surface` and the existing exact-digest
`/uvp --arxiv-execute` denial probe.

Expected: the diagnostic now identifies which upstream reporting case
occurs. Execute must still return `DISABLED_BY_DEFAULT` and
`execution_performed=false`.

**No second real arXiv call needed or approved** for this checkpoint.
Further execution support for generic `local` would require review of
the host's authoritative session identity and fresh permission policy;
do not widen the allowed set based only on the generic string.
