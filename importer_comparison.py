"""Phase 5: comparison with the official Hermes `agent-importers` plugin.

DOCUMENTATION-BASED ONLY in this release. The official importer was NOT
executed: running externally downloaded code was not permitted in the build
environment, and the user's real Hermes profile must not be touched. The
documented behavior is pinned to hermes-agent commit HERMES_SOURCE_COMMIT
(website/docs/user-guide/import-from-other-agents.md). A reproducible
procedure for an actual side-by-side run in a disposable profile is included.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .compatibility_contract import permission_inventory
from .hermes_target import HERMES_SOURCE_COMMIT, OBSERVED_FILES

DOC_PATH = 'website/docs/user-guide/import-from-other-agents.md'

OFFICIAL_DOCUMENTED = {
    'commands': 'SKIPPED_WITH_NOTE ("Skipped with a note - convert them into skills")',
    'skills': 'COPIED to ~/.hermes/skills/claude-code-imports/<name>/',
    'settings_bash_rules': 'MAPPED Bash(...) allow -> command_allowlist, deny -> approvals.deny (prefix rules become globs)',
    'settings_non_bash_rules': 'REPORTED_UNMAPPED',
    'mcp_servers': 'MAPPED to mcp_servers in config.yaml (secret-looking env/headers stripped)',
    'agents': 'NOT_DOCUMENTED',
    'command_frontmatter_allowed_tools': 'NOT_APPLICABLE (commands skipped)',
}

REPRODUCTION = [
    'Use a throwaway machine/VM or a new OS user with NO production credentials.',
    'Create a disposable Hermes home:  $env:HERMES_HOME = "D:\\Hermes-Lab\\disposable-import-test"  (PowerShell)',
    'Create a fake Claude home containing ONLY the fixture: a commands folder (*.md) and a settings file inside the fake Claude home',
    'Point the importer at the fake home (set HOME/USERPROFILE for that shell only), then: hermes plugins install agent-importers',
    'hermes import-agent claude-code --dry-run   (preview only; record the per-item plan)',
    'Compare the dry-run plan with OFFICIAL_IMPORTER_COMPARISON.json rows; record observed counts in a new JSON file.',
    'Delete the disposable HERMES_HOME afterwards. Never run this against D:\\Hermes-Lab\\data.',
]


def compare(plan: dict, source_root: Path, bundle: dict | None) -> dict:
    perms = permission_inventory(source_root, plan)
    passports = (bundle or {}).get('passports') or []
    outcome_counts = (bundle or {}).get('outcome_counts') or {}
    n_cmd = len(plan.get('commands') or [])
    n_skill = len(plan.get('skills') or [])
    allowed_tools_cmds = sum(1 for p in passports if p['semantic_contract']['dimensions'].get('permissions')
                             in {'NOT_PRESERVED', 'VIOLATION'})
    rows = [
        {'component': 'commands', 'source_count': n_cmd,
         'official_documented': OFFICIAL_DOCUMENTED['commands'],
         'this_port': outcome_counts or 'not repaired in this run'},
        {'component': 'skills', 'source_count': n_skill, 'official_documented': OFFICIAL_DOCUMENTED['skills'],
         'this_port': 'staged as portable skills (unchanged v0.3.5 behavior)'},
        {'component': 'settings_permissions', 'source_count': len(perms),
         'official_documented': OFFICIAL_DOCUMENTED['settings_bash_rules'] + '; non-Bash: '
         + OFFICIAL_DOCUMENTED['settings_non_bash_rules'],
         'this_port': 'counted only, never imported; REQUIRES_PERMISSION_SEMANTIC_REVIEW' if perms else 'no settings file'},
        {'component': 'command_frontmatter_permissions', 'source_count': allowed_tools_cmds,
         'official_documented': OFFICIAL_DOCUMENTED['command_frontmatter_allowed_tools'],
         'this_port': 'reported per command (allowed-tools pre-approval not preserved; disallowed-tools blocks)'},
        {'component': 'agents', 'source_count': None, 'official_documented': OFFICIAL_DOCUMENTED['agents'],
         'this_port': 'preserved as non-executable references (v0.3.3+)'},
    ]
    return {
        'schema': 'universal-port.importer-comparison/1',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'comparison_type': 'DOCUMENTATION_BASED',
        'official_importer_executed': False,
        'why_not_executed': ('Executing externally downloaded code (Hermes / agent-importers) was not permitted in the '
                             'build sandbox, and the real Hermes profile must not be used. Status: UNPERFORMED.'),
        'official_reference': {'repo': 'https://github.com/NousResearch/hermes-agent', 'commit': HERMES_SOURCE_COMMIT,
                               'file': DOC_PATH, 'git_blob': OBSERVED_FILES[DOC_PATH]},
        'scope_difference': ('The official importer reads a user-level ~/.claude tree; this port reads a plugin '
                             'repository. Rows compare the same component types, not identical inputs.'),
        'source_plugin': plan.get('name'),
        'rows': rows,
        'metrics': {
            'source_capabilities_recognized': {'this_port': n_cmd + n_skill,
                                               'official': 'NOT_MEASURED (documentation states commands are skipped)'},
            'commands_staged_as_native_adapters': sum(1 for p in passports if p['stages']['adapter_generated']),
            'commands_static_checks_passed': sum(1 for p in passports if p['stages']['static_checks_passed']),
            'commands_runtime_verified': sum(1 for p in passports if p['stages']['runtime_behavior_verified']),
            'commands_unsupported_or_blocked': sum(1 for p in passports if p['outcome'] in {'UNSUPPORTED', 'BLOCKED_UNSAFE'}),
            'commands_requiring_user_review': sum(1 for p in passports if p['outcome'] == 'PARTIAL_REVIEW_REQUIRED'),
            'permission_discrepancies_reported': allowed_tools_cmds + len(perms),
        },
        'benchmark_claims': 'NONE. No timing, cost or success-rate comparison is claimed.',
        'reproduction_procedure': REPRODUCTION,
    }
