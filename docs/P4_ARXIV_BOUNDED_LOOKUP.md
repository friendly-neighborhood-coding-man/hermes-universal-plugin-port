# P4 bounded arXiv lookup — standalone live adapter E2E observed

Status: **STANDALONE LIVE API E2E PASS (operator-observed); HERMES SKILL EXECUTION NOT VERIFIED**.

The operator supplied a 2026-11-09 16:43:45 UTC receipt showing a single
approved GET, SUCCEEDED, a matching versioned ID, and a stored response
digest. [Live E2E record](E2E_ARXIV_LIVE_V052.md). This is not an
independent audit of the local file or raw network traffic.

This slice implements a UVP-owned, narrow **single version-pinned paper
metadata lookup**. It is **not** executing the official Hermes arxiv
SKILL.md (which is an instruction manifest, not a callable function).
No code-writing CLI, general arXiv keyword search, Semantic Scholar API,
or Skill composition is enabled by this slice.

## Trusted API reference

The official [arXiv API User Manual](https://info.arxiv.org/help/api/user-manual.html)
specifies the id_list query parameter, versioned IDs suffixed with vN,
and Atom responses. The UVP adapter further requires HTTPS and precisely
one expected version in the returned Atom entry.

## Two separate stages

Stage A (no API access; safe even without credentials):

~~~powershell
$env:HERMES_HOME = 'D:\Hermes-Lab\uvp-v050-hermes-test'
Set-Location 'D:\Hermes-Lab\uvp-v050-routing-core'
python uvp_arxiv_cli.py plan 1706.03762v1
~~~

The returned JSON includes request_sha256, the exact GET URL,
request_count_limit=1, approval_status=AWAITING_OPERATOR_CONFIRMATION
and execution_performed=false. Nothing is downloaded, installed,
imported from external Skills, or sent to arXiv.

The Hermes plugin's new preview-only command does the same:

~~~text
/uvp --arxiv-plan 1706.03762v1
~~~

This command is a plan only. It never starts a network call. The Hermes
uvp_route LLM-visible tool has **not** been extended with a network
executor. The ordinary /uvp task and --candidates semantics remain.

Stage B (real network; **DO NOT RUN WITHOUT SEPARATE OPERATOR APPROVAL**):

~~~powershell
# Take the entire digest from Stage A; do NOT invent it.
python uvp_arxiv_cli.py run 1706.03762v1 --expect '<request_sha256 from plan>'
~~~

The command refuses to proceed without an interactive TTY and requires the
human operator to type a request-specific approval string verbatim. It
does **not** support --yes, a command-line approval boolean, piped stdin
or automatic agent invocation. This TTY confirmation is an **operator UX
gate**, not cryptographic attestation against a malicious local process.

It will then perform **at most one HTTPS GET**, without retries, redirects,
HTTP proxies or credentials; require status 200; read at most 128 KiB; parse
one Atom entry and verify that the returned versioned arXiv ID matches the
requested one; and write a create-only success/failure receipt under
the profile's HERMES_HOME/uvp-evidence/ directory.

The requested ID and query string are disclosed to export.arxiv.org.
The returned paper metadata is untrusted source data, not executable
instructions. Repeated requests should respect arXiv's rate guidance
(allow 3 seconds between API calls); no automated polling exists.

## Offline test gate

~~~powershell
python -m unittest discover -s tests -p 'test_uvp_*.py' -v
python -m unittest discover -s tests -v
hermes plugins doctor 'D:\Hermes-Lab\uvp-v050-routing-core' --ci
~~~

The P4 tests mock the network and operator terminal. They cover version
pinning, plan tampering, no TTY, wrong approval, denied approval, redirects,
response size, XML entity declarations, mismatch of paper ID/version,
a single fake GET, and successful/failed evidence records.

**269 tests OK (3 skipped)** and Hermes Plugin Doctor 0.5.2 PASS were
reported by the operator. The standalone arXiv network E2E also passed by
operator-supplied evidence. **The separate Hermes `/uvp --arxiv-plan`
command has not yet been tested in the Hermes UI.**

## Important limits

- arxiv being enabled does not prove tool dependencies, network
  connectivity, or actual execution. This does not auto-enroll it as
  an executable Hermes Skill.
- This code uses a fixed **UVP-owned arXiv API adapter**, not a proven
  semantics-preserving direct bridge to Hermes's general Skill.
- SHA-256 binds a planned URL to an input, but without a signature/isolated
  authority it does **not** authenticate operator approval.
- The CLI writes receipts to a local user-writable directory. That is
  reproducible evidence, **not** a tamper-proof external witness.
- Certificate validation and DNS resolution are OS-dependent; HTTPS and a
  fixed hostname cannot independently prove remote server correctness.
- If receipt writing fails after a network attempt, its execution outcome
  must be treated as **unknown** until logs are independently inspected.
- --arxiv-plan works without a model; model-initiated uvp_route
  execution and natural-language invocation adherence remain untested.
- Existing port_probe/port_fetch/port_stage permissions have not changed.
