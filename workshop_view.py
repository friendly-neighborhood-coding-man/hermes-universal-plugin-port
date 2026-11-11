"""Phase 6 (optional): "The Olympian Workshop" — a terminal view of REAL pipeline state.

The five figures are labels for pipeline stages, not agents; rendering makes
no model calls. A celebratory mark is only ever shown for a capability whose
runtime behavior is verified; static results are shown as static.
"""
from __future__ import annotations

FIGURES = (
    ('Hermes', 'transfer / direct bridge'),
    ('Athena', 'semantic inspection'),
    ('Hephaestus', 'adaptation'),
    ('Themis', 'verification'),
    ('Mnemosyne', 'compatibility snapshot'),
)
MARK = {
    'DIRECT_EQUIVALENT_VERIFIED': '[OK runtime]',
    'ADAPTED_RUNTIME_VERIFIED': '[OK runtime]',
    'ADAPTED_STATICALLY': '[static only]',
    'PARTIAL_REVIEW_REQUIRED': '[partial - review]',
    'UNSUPPORTED': '[unsupported]',
    'BLOCKED_UNSAFE': '[BLOCKED]',
}


def render_workshop(bundle: dict, impact: dict | None = None) -> str:
    ps = bundle['passports']
    n = len(ps)
    direct = sum(1 for p in ps if (p['verification'].get('direct_bridge') or {}).get('applicable'))
    understood = sum(1 for p in ps if p['stages']['source_functionality_understood'])
    adapted = sum(1 for p in ps if p['stages']['adapter_generated'])
    static_ok = sum(1 for p in ps if p['stages']['static_checks_passed'])
    runtime_ok = sum(1 for p in ps if p['stages']['runtime_behavior_verified'])
    needs_ai = [p['capability_id'].rsplit(':', 1)[-1] for p in ps if p['outcome'] == 'PARTIAL_REVIEW_REQUIRED']
    status = {
        'Hermes': f'{direct}/{n} verified direct bridges (no applicable verified mapping)' if not direct
        else f'{direct}/{n} verified direct bridges',
        'Athena': f'{understood}/{n} commands understood; unknowns kept as UNKNOWN',
        'Hephaestus': f'{adapted}/{n} deterministic adapters, 0 model calls'
        + (f'; semantic gaps a human or bounded AI step must address: {", ".join(needs_ai)}' if needs_ai else ''),
        'Themis': f'{static_ok}/{n} static check sets passed; RUNTIME verified: {runtime_ok}/{n}',
        'Mnemosyne': 'snapshot v2 recorded' + (f'; update impact: {impact["summary"]}' if impact else ''),
    }
    lines = ['THE OLYMPIAN WORKSHOP  -  ' + bundle['source_plugin'], '=' * 60]
    for name, role in FIGURES:
        lines.append(f'{name:<11} ({role}): {status[name]}')
    lines += ['-' * 60]
    for p in ps:
        cmd = p['integration']['hermes_command'] or '-'
        if p['integration']['hermes_command']:
            cmd += ('  (needs operator approval)' if p['integration'].get('registration') == 'REQUIRES_OPERATOR_APPROVAL'
                    else '  (not registered)')
        lines.append(f'{MARK[p["outcome"]]:<20} {p["capability_id"].rsplit(":", 1)[-1]:<22} {cmd}')
    lines += ['-' * 60,
              'Nothing installed. Static-only results are NOT runtime equivalence.' if runtime_ok == 0
              else 'Nothing installed. Only [OK runtime] rows have runtime evidence.']
    return '\n'.join(lines) + '\n'
