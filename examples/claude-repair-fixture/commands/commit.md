---
description: Stage and commit the current changes
allowed-tools: Bash(git add *) Bash(git commit *) Bash(git status *)
disable-model-invocation: true
---

Review `git status`, then use AskUserQuestion to confirm the message with the user.
Do not proceed until the user gives explicit approval, then run git commit -m "$ARGUMENTS".
