"""Pinned, source-observed Hermes host facts used by the slash-command repair engine.

Every fact here was read (not executed) from the public NousResearch/hermes-agent
repository at commit HERMES_SOURCE_COMMIT on 2026-11-07. The installed Hermes on a
user's machine may differ; a different or unknown target version invalidates any
runtime evidence (see semantic_verification.evidence_is_current). These facts
describe API availability only; they never prove runtime parity.
"""
from __future__ import annotations

import hashlib
import json

HERMES_SOURCE_REPO = 'https://github.com/NousResearch/hermes-agent'
HERMES_SOURCE_COMMIT = 'a9ff9799e273f525b82718cdc69fdec71b1dca5a'
# pyproject.toml at that commit declares version "0.0.0" (set at release time), so the
# commit itself is the only reliable identity of the observed source.
TARGET_FACTS_ID = 'hermes-agent@' + HERMES_SOURCE_COMMIT[:12]

# git blob ids of the files the facts below were read from.
OBSERVED_FILES = {
    'agent/skill_preprocessing.py': '5464a68f51bb2abd5f1b69a81b71276b091f11e5',
    'agent/skill_commands.py': '76f088bb7e27957713b46b51c4ac6b69a7b1c355',
    'hermes_cli/plugins_context.py': '71bacc4f92a77e470b926bc841972a024738e22e',
    'hermes_cli/plugins_injection.py': 'ed6378f5020b03625c244a332e131a8468e43e4f',
    'hermes_cli/commands.py': 'c6ae840b1965d18304d145ba9d262cb95c093930',
    'website/docs/user-guide/import-from-other-agents.md': '1fdf9ed44a629a3a7e603df48b5d911145f4615e',
    'website/docs/developer-guide/plugins/index.md': 'ef2ebbb0d29ccb94db3e36e0c6db2f6aa3f3af93',
    'plugin-catalog/agent-importers.yaml': 'e718f9de64b5ecb56ca4144602f7b41f518c4a61',
    'hermes_cli/plugin_choices.py': 'ec20b49ddd1d8cfb1e784d75b86903b1ea1f998a',
}

FACTS = {
    'skill_invocation_appends_instruction': {
        'file': 'agent/skill_commands.py',
        'fact': ('/skill-name <text> loads SKILL.md and appends "The user has provided the following '
                 'instruction alongside the skill invocation: <text>". There is no $ARGUMENTS / $N substitution.'),
    },
    'skill_template_vars': {
        'file': 'agent/skill_preprocessing.py',
        'fact': 'SKILL.md substitutes only ${HERMES_SKILL_DIR} and ${HERMES_SESSION_ID} (skills.template_vars, default on).',
    },
    'skill_inline_shell': {
        'file': 'agent/skill_preprocessing.py',
        'fact': ('With skills.inline_shell=true (default false) every bang-backtick snippet ANYWHERE in SKILL.md is executed with the '
                 'skill directory as CWD; community hub skills excluded. Claude Code runs bang-backtick snippets only at line start or '
                 'after whitespace, in the session CWD, and aborts the invocation on failure.'),
    },
    'plugin_command': {
        'file': 'hermes_cli/plugins_context.py',
        'fact': ('ctx.register_command(name, handler, description, args_hint) registers /name; handler(raw_args) '
                 'returns text shown to the user. A name colliding with a built-in command is skipped with a warning.'),
    },
    'inject_message': {
        'file': 'hermes_cli/plugins_injection.py',
        'fact': ('ctx.inject_message(content, role="user") -> bool. Classic CLI: queued to the pending-input queue, or '
                 'to the INTERRUPT queue while the agent is running. Gateway/TUI: requires plugins.entries.<id>.'
                 'allow_gateway_injection: true, otherwise returns False.'),
    },
    'ask_choice': {
        'file': 'hermes_cli/plugin_choices.py',
        'fact': 'ctx.ask_choice works only from a synchronous slash-command handler; returns None when it cannot ask.',
    },
    'official_importer_commands': {
        'file': 'website/docs/user-guide/import-from-other-agents.md',
        'fact': ('Official agent-importers maps Claude Code commands/*.md to "Skipped with a note - convert them into '
                 'skills"; Bash(...) allow/deny rules become command_allowlist/approvals.deny; non-Bash rules unmapped.'),
    },
    'no_per_skill_tool_policy': {
        'file': 'agent/skill_commands.py',
        'fact': 'No per-skill or per-plugin-command tool pre-approval or tool removal was found (allowed-tools/disallowed-tools have no counterpart).',
    },
}

# Built-in slash commands and aliases (AST-extracted from hermes_cli/commands.py).
BUILTIN_COMMANDS = frozenset(["agents", "approvals", "approve", "autoprune", "battery", "bg", "blueprint", "bp", "branch", "browser", "btw", "bundles", "busy", "clear", "codex-runtime", "codex_runtime", "commands", "compact", "compose", "compress", "config", "context", "copy", "cron", "ctx", "curator", "debug", "deny", "diff", "discard", "egress", "exit", "export", "fast", "focus", "footer", "fork", "gateway", "generate-pet", "goal", "handoff", "hatch", "hb", "heartbeat", "help", "history", "image", "import", "indicator", "init", "insights", "journey", "kanban", "learn", "learning", "login", "loop", "memory", "memory-graph", "moa", "model", "new", "palette", "paste", "pause", "personality", "pet", "plan", "platform", "platforms", "plugins", "proactive", "profile", "prompt", "q", "queue", "quit", "reasoning", "redraw", "refine", "reload", "reload-mcp", "reload-skills", "reload_mcp", "reload_skills", "reset", "restart", "resume", "retry", "review", "rewind", "rollback", "s", "save", "sb", "sessions", "set-home", "sethome", "skills", "skin", "snap", "snapshot", "start", "status", "statusbar", "steer", "stop", "subgoal", "subscription", "suggest", "suggestions", "tasks", "timestamps", "title", "tools", "toolsets", "topic", "topup", "ts", "undo", "update", "upgrade", "usage", "v", "verbose", "version", "voice", "wake", "whoami", "worktree", "yolo"])


def facts_sha256() -> str:
    payload = json.dumps({'commit': HERMES_SOURCE_COMMIT, 'files': OBSERVED_FILES, 'facts': FACTS,
                          'builtins': sorted(BUILTIN_COMMANDS)}, sort_keys=True).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def target_profile(installed_version: str | None) -> dict:
    """Describe the target: observed source facts + the actually installed version (if any)."""
    return {
        'facts_id': TARGET_FACTS_ID,
        'facts_sha256': facts_sha256(),
        'observed_source_commit': HERMES_SOURCE_COMMIT,
        'installed_hermes_version': installed_version,
        'installed_version_matches_observed_source': 'UNKNOWN',
        'note': ('Facts were read from source, not executed. Whether the installed Hermes behaves the same is '
                 'UNKNOWN until runtime evidence is recorded against that exact installed version.'),
    }
