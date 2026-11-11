# P5 v0.5.3 — Hermes no-execution gate result and TUI hypothesis

**Operator-observed:** 2026-11-10 KST, disposable Hermes profile.
**Status:** No-network safety PASS; expected denial reason MISMATCH.

## Command and response

The operator entered:

```text
/uvp --arxiv-plan 1706.03762v1
```

Hermes returned the exact one-GET URL
`https://export.arxiv.org/api/query?id_list=1706.03762v1&max_results=1`,
request SHA-256
`25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84`,
`approval_status: AWAITING_OPERATOR_CONFIRMATION`, and
`execution_performed: false`.

The operator then entered:

```text
/uvp --arxiv-execute 1706.03762v1 25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84
```

Hermes returned:

```json
{
  "schema": "universal-port.arxiv-hermes-execution/1",
  "status": "CLI_ONLY",
  "execution_performed": false,
  "approved_capabilities_added": 0,
  "request_sha256": "25bc109bf20dac3862c57118fece9c7722ee081edd1a44f4968eba1607209b84"
}
```

## Diagnosis

The v0.5.3 code only accepted `ctx.session_surface() == "cli"`
and checked the surface before checking the disabled-by-default process
flag. Hermes's upstream `plugin_session.py` documents **both**
`cli` and `tui` as local surfaces. `plugin_choices.py` documents
`ask_choice` support for a local session attached through gateway.

**Hypothesis:** The user's Hermes session was a local `tui`, so the
old gate returned `CLI_ONLY` even with live execution disabled.
This was NOT conclusively proven by the output because v0.5.3 omitted
the actual observed surface.

## v0.5.4 corrective change (code, unverified in operator runtime)

- Check the environment opt-in first. With flag unset/0, return
  `DISABLED_BY_DEFAULT` regardless of the caller's surface.
- Only when opted in, permit known local surfaces `cli` and `tui`.
  External messaging, desktop, ACP, unknown and absent surfaces deny.
- Add non-executing `/uvp --surface` report for observed surface and
  gate state, without exposing private session identifiers.
- Add offline regression cases for TUI, disabled flag precedence and
  remote/unknown surface refusal.

**Next checkpoint:** After local tests and reversible update in the
disposable profile, `/uvp --surface` should report actual local
surface and `/uvp --arxiv-execute ...` with opt-in flag 0 should
return `DISABLED_BY_DEFAULT` without any approval UI or network.
No second live GET is needed for these checks.

No P5 live approved request has been performed; this is neither a
native Hermes arxiv Skill run nor a Direct Bridge.

## Focused v0.5.4 test failure and patch

The operator attempted the v0.5.4 P5 focused suite locally.
Observed `Ran 22 tests in 0.155s; FAILED (failures=1, errors=2)`.
No P5 full-suite or Doctor pass was reported for this worktree.

- `test_surface_diagnostic_reports_local_tui_without_any_network`
  and `test_surface_diagnostic_unknown_never_enables` raised JSONDecodeError.
  Confirmed source cause: the `/uvp --surface` response prefix used
  a double backslash in Python source, yielding a literal backslash-n
  instead of the required newline before pretty-printed JSON.
- `test_unknown_surface_denied` expected the retired `CLI_ONLY`
  result while the implementation correctly returned
  `LOCAL_CLI_OR_TUI_ONLY`.

Patches on the P5 draft branch:
- `uvp_plugin_router.py`: normal newline escape in the JSON response prefix.
- `tests/test_uvp_arxiv_p5.py`: corrected denial status, a strict
  no-network assertion, and a regression assertion on response formatting.

**These patches have not been rerun by the operator.**
No network requests were performed by the offline test harness.
