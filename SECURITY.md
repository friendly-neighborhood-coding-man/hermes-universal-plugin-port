# Security policy

**Status:** Experimental pre-release, no stable or security-supported release yet.

## Testing warning

Hermes `plugins doctor` may import and execute plugin code. Setting `HERMES_HOME` to a throwaway directory isolates the data profile, **not** the operating system.

Review generated adapters and independently verify an external digest immediately before running code. SHA-256 is an integrity check **not an authenticated release signature**. Approved commands still need explicit permission boundaries. Never promote self-reported evidence to verified runtime parity.

Avoid real Hermes profiles, production secrets, privileged tools or remote write actions for compatibility experiments.

## Reporting

Use GitHub's private **Report a vulnerability** security-advisory workflow if enabled. Otherwise open a public issue with only minimal non-exploitable information requesting a private contact channel. Do not publish secrets or sensitive exploit payloads in public issues.
