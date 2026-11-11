# Contributing

Hermes Universal Port is an experimental, standalone Hermes plugin. Contributions should be narrow, reproducible and evidence-backed.

## Before opening a PR

1. Explain the original capability, intended target behavior and any lost semantics.
2. Add negative tests for permission, side-effect, approval and unsupported behavior.
3. Run `python -m unittest discover -s tests -v` on a clean checkout; include platform and Python version.
4. Clearly separate **static analysis**, **self-reported runtime observation**, and **trusted runtime verification**.
5. Keep adapters **unregistered by default**; never relax permission or approval checks silently.

Never commit production credentials, API keys, user Hermes profiles, generated approval records, personal logs, private DIAPORIA internals or unlicensed third-party code.

**Direct Bridge** requires verified equivalence of inputs, outputs, side effects, permissions, approvals, failures, state and invocation. Similar names or goals are insufficient. Unsupported semantics must remain visibly unsupported.

For security-sensitive changes, describe a reproducible benign PoC, the boundaries of the threat model, and whether real Hermes was executed. Use the [PR template](.github/pull_request_template.md).
