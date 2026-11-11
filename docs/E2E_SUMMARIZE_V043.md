# Hermes Universal Port v0.4.3 — Claude E2E

## Result

INTEGRATION_ADAPTER — E2E OBSERVED

One `/summarize in plain words` invocation completed
through the official Claude Code CLI.

## Environment and observations

- Hermes Agent: v0.22.7
- Model: Haiku 5.5
- Model calls: 1
- Tool calls: 0
- Input tokens: 324
- Output tokens: 251
- Extra usage: disabled
- Message delivery: observed
- Work directory: unchanged

Hermes Plugin Doctor and Validate returned exit code 0.
Pre-import verification passed before and after Doctor.

## Semantic differences

Direct Bridge equivalence is not established.

- The adapter adds a message header.
- Gateway injection requires explicit permission.
- Reliable Windows registration required a bytecode-cache
  permission workaround.

The delivered arguments included:
`ARGUMENTS: in plain words`

The model nevertheless incorrectly described the arguments
line as empty.

## Bytecode-cache finding

The original generated adapter contained two cached Python
bytecode files under __pycache__.

The E2E adapter contained neither file.

The compared adapter source files were identical.

This is evidence of a runtime/environment difference,
not a demonstrated source-code fix.

## Credential containment

An inherited OPENROUTER_API_KEY was detected.
The reported run recorded zero requests using that key.

No credential values or fingerprints are included.

## Evidence limits

The execution evidence is operator-reported and has not been
authenticated by a trusted runtime collector.

Production readiness, general semantic equivalence,
and Direct Bridge status are not established.
