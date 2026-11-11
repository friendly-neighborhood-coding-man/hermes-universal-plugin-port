# UVP P5 v0.5.6 — host-bound local slash command identity

**State: OPERATOR-OBSERVED OFFLINE PASS (301 tests OK, 3 skipped; Hermes Doctor PASS, 4 tools, 0 hooks) AND READ-ONLY HERMES HOST-BINDING E2E PASS. No P5 approved in-Hermes network request yet.**
No new arXiv network request has been made in this step.

## Why the previous check failed

Operator's v0.5.5 /uvp --surface output showed:

- session_surface: local
- session_surface_lookup: generic_local
- host_dispatch_platform: local
- local_surface_permitted: false
- execution_performed: false

That is a valid fail-closed behavior. Official Hermes gateway's
`_hm_run_plugin_handler` sends the slash handler a `source` object,
`session_id`, `session_key`, and `platform`, not just the read from
`ctx.session_surface()`. In the local gateway path, `platform` is
generic `local` rather than necessarily `tui` or `cli`.

References:
- [Hermes slash handler dispatch](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e3/gateway/run_inbound_hooks.py)
- [Hermes session source](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e3/gateway/session.py)
- [Hermes handler context binding](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e3/hermes_cli/plugin_command_dispatch.py)
- [Hermes local viewer approval choices](https://github.com/NousResearch/hermes-agent/blob/b200f5bc60e3/gateway/plugin_command_choice.py)

## New P5 local-host route

The existing concrete `cli` and `tui` surface branches remain.

When `ctx.session_surface() == "local"`, the path now requires every
condition below before prompting or accessing the network:

1. `UVP_ENABLE_ARXIV_EXECUTION=1` in the actual Hermes process;
   disabled by default and checked before session identity.
2. A manually submitted `/uvp --arxiv-execute` slash command with an
   exact full request digest matching a pinned arXiv versioned ID.
3. Slash dispatcher arguments include `platform == "local"`, a real
   `gateway.session.SessionSource` instance whose `platform` is
   `gateway.config.Platform.LOCAL`, and a nonempty `chat_id`.
4. The trusted host dispatcher supplies nonempty `session_id` and
   `session_key` strings. **Generic `local` alone is insufficient.**
5. Receipt folder preflight succeeds, and Hermes `ctx.ask_choice`
   obtains the user's fresh `Approve one arXiv GET` selection for
   the exact full URL and request SHA-256. Cancellation or unavailable
   approval returns no-execution.
6. The original bounded adapter executes at most one arXiv GET and
   writes a create-only evidence receipt, or marks post-attempt
   evidence failures as executed/unrecorded.

No model-visible tool executor was added; `uvp_route` remains advisory
only. No direct `arxiv` SKILL.md execution, Direct Bridge, or arbitrary
plugin composition is claimed.

**Trust limitation:** Hermes supplies the slash context. A malicious
local Python module sharing the process could bypass or spoof plugin
internals. This is not cryptographic authorization, a process sandbox or
independent signed attestation. A real user choice is still required.

## Read-only diagnostic v3

The `/uvp --surface` command now returns
`universal-port.session-diagnostic/3`, including booleans
`session_id_present`, `session_key_present`,
`host_local_source_verified`, and a code
`host_context_status`. It does not display the actual IDs or the
source object.

When the opt-in flag remains 0, diagnostic remains non-executing; it
may report `local_surface_permitted=true` if all binding fields are
present, but **`live_execution_opt_in=false`** and
`--arxiv-execute` still returns `DISABLED_BY_DEFAULT`.

## Required test steps, with network opt-in disabled

~~~powershell
$work = 'D:\Hermes-Lab\uvp-v050-routing-core'
$env:HERMES_HOME = 'D:\Hermes-Lab\uvp-v050-hermes-test'
$env:UVP_ENABLE_ARXIV_EXECUTION = '0'
if (git -C $work status --porcelain) { throw 'Uncommitted changes' }
git -C $work fetch origin feat/uvp-v050-routing-core
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
git -C $work switch --detach origin/feat/uvp-v050-routing-core
if ($LASTEXITCODE -ne 0) { throw 'Switch failed' }
Set-Location $work
python -m unittest discover -s tests -p "test_uvp_arxiv_p5.py" -v
if ($LASTEXITCODE -ne 0) { throw 'P5 tests failed' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Full regression failed' }
hermes plugins doctor $work --ci
if ($LASTEXITCODE -ne 0) { throw 'Doctor failed' }
~~~

With all checks green, run
`powershell -NoProfile -File .\scripts\UPDATE_TEST_UVP.ps1` (v0.5.6,
disposable test profile only), launch Hermes again with opt-in 0,
and call:

~~~text
/uvp --surface
/uvp --arxiv-execute 1706.03762v1 25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84
~~~

The second command **must** return `DISABLED_BY_DEFAULT`,
`execution_performed=false` and must not ask for approval or
send a network request. The first command should identify whether
the host supplies the necessary binding values. If `host_local_source_verified`
is false, investigate its code without expanding permissions.

**Do not enable the flag or perform a second arXiv query yet.**

## Operator focused-test finding and correction (2026-11-10 KST)

On the initial v0.5.6 worktree, the operator reported
`Ran 31 tests ... FAILED (failures=1)`:
`test_bound_host_local_diagnostic_no_execution` expected
`live_execution_opt_in=false` but actually received `true`.

The test class `setUp` uses `P5.ENV_ENABLE: "1"` to exercise
positive opt-in paths; that diagnostic case forgot to switch it off.
The diagnostic implementation is consistent with the environment and
still reports `execution_performed=false`.

Test-only patch:
- Set `UVP_ENABLE_ARXIV_EXECUTION=0` explicitly in that diagnostic
  test when asserting `live_execution_opt_in=false`.
- Add a complementary opt-in=`1` diagnostic test asserting the
  readiness flag is true, while `execution_performed=false`, no
  host choice requested, and any fetch would throw in the mocked
  test fixture.

**Focused tests: 32 test methods; re-run not yet reported.**
No P5 live API call is warranted for this test correction.

## Operator verification — v0.5.6 offline gate

The operator shared the Windows terminal report:

```text
Ran 301 tests in 432.618s
OK (skipped=3)
Plugin Doctor: D:\Hermes-Lab\uvp-v050-routing-core
  manifest: universal-plugin-port 0.5.6 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 4 tool(s), 0 hook(s)
```

These results validate the local regression suite and Doctor import/
registration checks. **They do not show a v0.5.6 Hermes session binding
report, a native approval modal, or another arXiv API call.** The profile
update and the read-only runtime check remain a separate next gate.

## Live Hermes local host-binding result (operator-observed)

On 2026-11-10 KST the operator submitted `/uvp --surface` inside
the **disposable** Hermes profile running v0.5.6 and reported:

```json
{
  "schema": "universal-port.session-diagnostic/3",
  "session_surface": "local",
  "session_surface_lookup": "generic_local",
  "host_dispatch_platform": "local",
  "host_local_source_verified": true,
  "host_context_status": "HOST_BOUND_LOCAL",
  "session_id_present": true,
  "session_key_present": true,
  "local_surface_permitted": true,
  "live_execution_opt_in": false,
  "execution_performed": false
}
```

**Interpretation:** The official Hermes slash handler supplied
sufficient local SessionSource and nonempty host-provided session
identity fields to satisfy UVP's host-binding predicate. The actual
session identifiers are deliberately **not** logged. The process
remained unopted-in, and this diagnostic performed **zero** network
activity by design.

This proves the **read-only host identity diagnostic gate** worked in
the operator's Hermes session. It does **not** demonstrate that an
arXiv request ran within Hermes, that the human approval UI completed
a choice, or that these Python-level checks constitute an
unforgeable security attestation. The separate disabled-execution
probe was subsequently observed and passed on v0.5.6.

## Hermes disabled-by-default execution gate (operator-observed)

With `UVP_ENABLE_ARXIV_EXECUTION=0`, the operator submitted
`/uvp --arxiv-execute 1706.03762v1` with the previously reviewed
full request SHA-256 and observed:

```json
{
  "schema": "universal-port.arxiv-hermes-execution/1",
  "status": "DISABLED_BY_DEFAULT",
  "execution_performed": false,
  "approved_capabilities_added": 0,
  "request_sha256": "25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84"
}
```

**P5 default-deny E2E PASS (operator-observed).** This occurred after
the separate `/uvp --surface` result showed a complete
`HOST_BOUND_LOCAL` session binding. The execution handler checks the
explicit process opt-in first; disabled execution returns before
asking the user or invoking the bounded arXiv API adapter.
The console evidence supports a no-execution outcome but is not an
independent packet-capture or external signed witness.

**Still NOT tested:** enabling actual Hermes-mediated network access,
the native `ask_choice` modal/denial or approval E2E, or a P5 live
arXiv call with a new receipt. These are separate gates requiring
request-specific operator authorization. Do not silently enable them.
