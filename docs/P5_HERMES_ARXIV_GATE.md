# P5 v0.5.5 — Hermes local-session diagnostics (code-only checkpoint)

**Status: operator-confirmed v0.5.4 default-deny E2E PASS; `/uvp --surface` returned `unknown` because the initial diagnostic collapsed multiple possible cases. v0.5.5 separates actual surface lookup from host slash platform (`local` on the gateway), but the new diagnostics have not yet been tested.**

This experimental slice executes **UVP's own pinned arXiv metadata adapter**
from a user-entered Hermes slash command. It does **not** run Hermes
`arxiv` SKILL.md, does not constitute a Direct Bridge, and does not
authorize arbitrary Skill execution or Research → Coding composition.

## Operator consent and security boundary

All gates must pass **for every request**:

1. User explicitly enters `/uvp --arxiv-execute <versioned-id> <SHA256>`
   with the exact plan digest. The model-visible `uvp_route` remains preview-only.
2. `UVP_ENABLE_ARXIV_EXECUTION=1` must be explicitly set in the Hermes **process**.
   This opt-in is OFF by default, including after plugin installation, and
   is checked before the session-surface gate.
3. Calling session reports `session_surface()` as one of `cli` or `tui`,
   both defined by Hermes as local sessions. Desktop/ACP, Telegram,
   Discord, cron and unknown surfaces are rejected. An observed `CLI_ONLY`
   from v0.5.3 is consistent with TUI, but not definitive without the new
   `/uvp --surface` diagnostic.
4. An existing, non-symlink `HERMES_HOME` allows evidence preflight.
5. `ctx.ask_choice` presents the exact version-pinned URL and full
   request digest to the human operator, who selects **Approve one arXiv GET**.
   Missing asker, UI timeout, cancellation and anything other than the
   precise `approve` value are treated as denial.

Only after all gates pass does UVP use its existing version-pinned arXiv
GET helper: max one request, HTTPS-only target, no redirects or retries,
8-second timeout, 128 KiB cap, strict Atom ID/version check.
The create-only receipt is placed in `HERMES_HOME/uvp-evidence/` and
marks `execution_origin=hermes_slash_command` and
`operator_confirmation=hermes.ask_choice`. If the receipt fails after
a network attempt, status is `EXECUTION_OUTCOME_UNRECORDED` and
`execution_performed=true` (never a false non-execution).

**This is not a security sandbox or a cryptographically protected approval**:
local Python code could bypass process-local gating; host permission
enforcement and independent evidence attestation remain future work.

## Offline test procedure

Run in a clean Windows checkout with test profile set:

~~~powershell
$work = 'D:\Hermes-Lab\uvp-v050-routing-core'
$uvpHome = 'D:\Hermes-Lab\uvp-v050-hermes-test'
$env:HERMES_HOME = $uvpHome
$env:UVP_ENABLE_ARXIV_EXECUTION = '0'
Set-Location $work
python -m unittest discover -s tests -p 'test_uvp_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'UVP tests failed' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Full regression failed' }
hermes plugins doctor $work --ci
if ($LASTEXITCODE -ne 0) { throw 'Plugin Doctor failed' }
~~~

After these checks, one may install v0.5.5 into the **disposable** profile:

~~~powershell
powershell -NoProfile -File .\scripts\UPDATE_TEST_UVP.ps1
~~~

Launch Hermes with live access disabled and verify the preview:

~~~powershell
$env:HERMES_HOME = 'D:\Hermes-Lab\uvp-v050-hermes-test'
$env:UVP_ENABLE_ARXIV_EXECUTION = '0'
Set-Location 'D:\Hermes-Lab\hermes-agent'
hermes
~~~

Inside Hermes:

~~~text
/uvp --surface
/uvp --arxiv-plan 1706.03762v1
~~~

The existing P4 standalone live receipt already established one successful
request. **The operator has already confirmed P5 default denial on v0.5.4; no additional arXiv call is needed.**
Run the following *only as a denial test* while the flag stays 0:

~~~text
/uvp --arxiv-execute 1706.03762v1 25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84
~~~

Expected: `/uvp --surface` returns a no-network session diagnostic;
it should report `session_surface_lookup` and `host_dispatch_platform` as
separate fields. A gateway-provided `platform: local` is **not** sufficient
to authorize execution, and a `session_surface` of `local` is still blocked.
If the concrete surface is unresolved, investigate upstream session-context
propagation without widening permissions.
With flag 0, the execute command should return `DISABLED_BY_DEFAULT`,
`execution_performed=false`, and no approval prompt or API call. This is
a useful live P5 safety check, not an execution pass.

**Do not enable the environment flag or approve a live request until a
separate operator decision.** If approved later, run a fresh P4 plan for
the exact versioned ID; review endpoint, digest and permissions. With the
flag set in the Hermes startup process, the slash command may present a
confirm/deny choice, then attempt one GET. Do not automate that choice.

## Outstanding verification

- P5 local unit and full regression test PASS not yet reported.
- Hermes Plugin Doctor P5 not yet reported.
- P5 Hermes preview + disabled execution live E2E not yet observed.
- P5 in-Hermes approved request E2E NOT RUN.
- Vanilla Hermes native arxiv Skill A/B comparison NOT RUN.
- No claim of universal Skill execution, Direct Bridge or semantic equivalence.

## v0.5.5 unknown-surface follow-up

See [evidence and diagnosis](P5_UNKNOWN_SURFACE_V055.md) for the operator's
`unknown` / `DISABLED_BY_DEFAULT` result, the Hermes gateway `platform=local`
contract, and the non-executing v0.5.5 diagnostic-only changes.
