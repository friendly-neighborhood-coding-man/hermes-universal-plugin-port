---
description: Summarize the current pull request
allowed-tools: Bash(gh *)
disable-model-invocation: true
---

## Pull request context
- PR diff: !`gh pr diff`
- Changed files: !`gh pr diff --name-only`

Summarize this pull request for $ARGUMENTS.
