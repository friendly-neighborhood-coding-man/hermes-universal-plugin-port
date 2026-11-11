"""Offline developer CLI for the v0.4.3 repair engine. Never installs or enables anything.

Usage (from any directory):
  python repair_cli.py repair    SOURCE OUT_DIR [--hermes-version V] [--source-commit SHA] [--evidence FILE ...]
  python repair_cli.py reconcile OLD_REPAIR_DIR NEW_SOURCE [--hermes-version V] [--source-commit SHA] [--out FILE]
  python repair_cli.py workshop  REPAIR_DIR [--impact UPDATE_IMPACT.json]
  python repair_cli.py verify-adapter REPAIR_DIR [--adapter FOLDER] [--expected-sha256 DIGEST]
  python repair_cli.py approve   REPAIR_DIR --command NAME [--command NAME ...] --operator NAME
                                 --i-reviewed-model-induced-effects [--expected-sha256 DIGEST]

  python repair_cli.py stage     REPAIR_DIR --hermes-home DISPOSABLE_HOME --i-confirm-disposable-home
                                 [--expected-sha256 DIGEST]

v0.4.3: `verify-adapter`, `approve` and `stage` first run the pre-import gate
(exact file allowlist; rejects __pycache__, .pyc, extension modules, extra .py).
`stage` copies only the locked files into a NEW HOME/plugins/<adapter>.
v0.4.2: generated adapters register NOTHING until `approve` writes an operator
approval record (outside the adapter folder) bound to the full adapter digest.
`verify-adapter` exits 1 if the folder differs from ADAPTER_LOCK.json, the
reviewed templates, or --expected-sha256.

--evidence files are recorded as SELF_REPORTED_UNTRUSTED (or FAIL/INVALID/STALE).
They can never promote a command to ADAPTED_RUNTIME_VERIFIED (v0.4.1, review P0-2).
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def _pkg():
    name = 'universal_port_cli_pkg'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _ROOT / '__init__.py', submodule_search_locations=[str(_ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    p = argparse.ArgumentParser(description='Universal Port v0.4.3 slash-command repair (offline)')
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('repair')
    r.add_argument('source'); r.add_argument('out')
    r.add_argument('--hermes-version', default=None)
    r.add_argument('--source-commit', default=None)
    r.add_argument('--evidence', nargs='*', default=[],
                   help='runtime evidence JSON; recorded as SELF_REPORTED only, never promotes')
    c = sub.add_parser('reconcile')
    c.add_argument('old_repair_dir'); c.add_argument('new_source')
    c.add_argument('--hermes-version', default=None)
    c.add_argument('--source-commit', default=None)
    c.add_argument('--out', default=None)
    v = sub.add_parser('verify-adapter')
    v.add_argument('repair_dir'); v.add_argument('--adapter', default=None)
    v.add_argument('--expected-sha256', default=None, help='digest published outside the artifact')
    ap = sub.add_parser('approve')
    ap.add_argument('repair_dir')
    ap.add_argument('--command', action='append', required=True, help='repeat per command; no approve-all')
    ap.add_argument('--operator', required=True)
    ap.add_argument('--i-reviewed-model-induced-effects', action='store_true', dest='reviewed')
    ap.add_argument('--expected-sha256', default=None)
    ap.add_argument('--note', default='')
    st = sub.add_parser('stage')
    st.add_argument('repair_dir'); st.add_argument('--hermes-home', required=True)
    st.add_argument('--i-confirm-disposable-home', action='store_true', dest='confirm')
    st.add_argument('--expected-sha256', default=None)
    w = sub.add_parser('workshop')
    w.add_argument('repair_dir'); w.add_argument('--impact', default=None)
    a = p.parse_args(argv)
    _pkg()
    from universal_port_cli_pkg import slash_repair, update_reconciliation, workshop_view, operator_approval
    from universal_port_cli_pkg.port_core import PortError
    try:
        if a.cmd == 'repair':
            evidence = [json.loads(Path(f).read_text(encoding='utf-8')) for f in a.evidence]
            b = slash_repair.repair_plugin(a.source, a.out, installed_hermes_version=a.hermes_version,
                                           source_commit=a.source_commit, runtime_evidence=evidence)
            print(json.dumps({'output_path': b['output_path'], 'adapter_path': b['adapter_path'],
                              'outcome_counts': b['outcome_counts'],
                              'runtime_verified_count': b['runtime_verified_count'],
                              'ready_for_installation_count': b['ready_for_installation_count'],
                              'installed': False}, indent=2))
        elif a.cmd == 'reconcile':
            snap = json.loads((Path(a.old_repair_dir) / 'UNDERSTANDING_SNAPSHOT_V2.json').read_text(encoding='utf-8'))
            impact = update_reconciliation.reconcile(snap, a.new_source, new_source_commit=a.source_commit,
                                                     installed_hermes_version=a.hermes_version)
            text = json.dumps(impact, indent=2, ensure_ascii=False)
            if a.out:
                Path(a.out).write_text(text + '\n', encoding='utf-8')
            print(text)
        elif a.cmd == 'verify-adapter':
            res = operator_approval.verify_adapter(a.repair_dir, adapter=a.adapter, expected_sha256=a.expected_sha256)
            print(json.dumps(res, indent=2))
            return 0 if res['ok'] else 1
        elif a.cmd == 'approve':
            res = operator_approval.approve(a.repair_dir, a.command, operator=a.operator,
                                            reviewed_model_induced_effects=a.reviewed,
                                            expected_sha256=a.expected_sha256, note=a.note)
            print(json.dumps(res, indent=2))
        elif a.cmd == 'stage':
            res = operator_approval.stage(a.repair_dir, a.hermes_home, confirm_disposable=a.confirm,
                                          expected_sha256=a.expected_sha256)
            print(json.dumps(res, indent=2))
        else:
            d = Path(a.repair_dir)
            bundle = json.loads((d / 'CAPABILITY_PASSPORT.json').read_text(encoding='utf-8'))
            impact = json.loads(Path(a.impact).read_text(encoding='utf-8')) if a.impact else None
            print(workshop_view.render_workshop(bundle, impact), end='')
        return 0
    except (PortError, ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
