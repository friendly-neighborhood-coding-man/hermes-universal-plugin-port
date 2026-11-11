# UVP v0.5.1 P3 — Hermes native Skill candidate E2E

Date: 2026-11-10 KST
Status: PASS — candidate discovery only
Evidence class: operator-shared terminal transcript, not a trusted witness

## Setup and prior validation

- Disposable Hermes home: D:\Hermes-Lab\uvp-v050-hermes-test
- The operator reported full Windows regression suite: 246 tests OK
  (3 skipped), and Hermes Plugin Doctor: 0.5.1, 4 tools, 0 hooks, PASS.
- User-installed plugin v0.5.1 was staged and invoked from Hermes CLI.
  The actual manifest version in this transcript was not printed again;
  the successful opt-in command is the observable proof of a P3-capable copy.

## Command

/uvp --candidates 논문을 조사하고 코드를 구현해줘

## Observed route

- Header: UVP Skill candidates (UNAPPROVED; NOT EXECUTED)
- schema: universal-port.skill-candidate-preview/1
- domains: research, coding
- catalog_count: 38
- candidates (each DISCOVERED_UNAPPROVED and executable=false):
  - research / arxiv / paper_search / network, external_send
  - research / grounded-citations / citation_support / network, write, external_send
  - coding / claude-code / code_implementation / execute, write, network, external_send
  - coding / codex / code_implementation / execute, write, network, external_send
- approved_capabilities_added: 0
- execution_performed: false
- note: Candidate metadata only; no Skill instructions read or invoked

## What was demonstrated

Hermes CLI accepted the plugin command, P3 consulted its native Skill
catalog (38 names), classified the user task and displayed matching
reviewed candidates. No capability was promoted to approval. The output
reports no downstream Skill execution, consistent with the handler design.

## Not demonstrated

- Execution of arxiv, Claude CLI, Codex or any Skill.
- Actual approval transport, pinned binding, runtime capability checking,
  trust or side-effect enforcement.
- Proof of semantic correctness, suitable tool availability, or whether
  each Skill's prerequisite binaries and credentials are installed.
- A trusted signed witness for zero out-of-band side effects.
- Model-call-free behavior under arbitrary natural language outside this
  explicit slash command.

## Next gate

Choose a reproducible, minimally scoped **single-capability fixture**.
For an arXiv network query: allowlist the exact endpoint, constrain query,
results, timeouts and output, require explicit operator approval, and
record the request and response evidence. Avoid any network dispatch prior
to that approval. Treat arxiv's SKILL.md as a set of instructions, not an
executable callback. Repeat against vanilla Hermes for a fair comparison.
