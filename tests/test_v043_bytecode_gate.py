"""v0.4.3 offline tests: pre-import gate against planted bytecode (review of v0.4.2, P0).

The PoC is harmless: the planted bytecode only registers a command named
CACHE_UNAPPROVED in a recording fake context. No real Hermes is used.

`BytecodeCachePoCTests` only uses APIs that already existed in v0.4.2
(load_adapter, verify_adapter, approve), so the same tests can be run against
the v0.4.2 tree to show that they fail there (see VERIFICATION_REPORT.md §1).
"""
import importlib.util
import json
import os
import py_compile
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('universal_port_v043_testpkg', ROOT / '__init__.py',
                                              submodule_search_locations=[str(ROOT)])
PKG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PKG
SPEC.loader.exec_module(PKG)
from universal_port_v043_testpkg import (slash_repair as R, semantic_verification as SV,  # noqa: E402
                                         operator_approval as OA, port_core as CORE)

FIXTURE = ROOT / 'examples' / 'claude-repair-fixture'
POC_REGISTER = ("\n\ndef register(ctx):\n"
                "    ctx.register_command('CACHE_UNAPPROVED', handler=lambda a='': 'x', description='poc', args_hint='')\n")


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.n = 0

    def repair(self):
        self.n += 1
        copy = self.tmp / ('src' + str(self.n))
        shutil.copytree(FIXTURE, copy)
        return R.repair_plugin(str(copy), str(self.tmp / ('out' + str(self.n))))

    def plant_bytecode(self, pkg: Path, mode=py_compile.PycInvalidationMode.UNCHECKED_HASH) -> Path:
        """Reviewer's PoC: an import-compatible .pyc for __init__ whose register() is replaced."""
        init = pkg / '__init__.py'
        evil = self.tmp / ('evil_' + uuid.uuid4().hex[:6] + '.py')
        evil.write_text(init.read_text(encoding='utf-8') + POC_REGISTER, encoding='utf-8')
        cfile = Path(importlib.util.cache_from_source(str(init)))
        cfile.parent.mkdir(exist_ok=True)
        py_compile.compile(str(evil), cfile=str(cfile), dfile=str(init), invalidation_mode=mode, doraise=True)
        return cfile

    @staticmethod
    def ungated_import(pkg: Path):
        """What any loader without a pre-import gate does (e.g. a plain package import)."""
        name = 'ungated_' + uuid.uuid4().hex[:8]
        spec = importlib.util.spec_from_file_location(name, pkg / '__init__.py', submodule_search_locations=[str(pkg)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod


class BytecodeCachePoCTests(Base):
    def test_poc_is_real_on_this_interpreter(self):
        # Guard: proves the attack works when no gate runs, so the tests below are meaningful.
        b = self.repair()
        pkg = Path(b['adapter_path'])
        self.plant_bytecode(pkg)
        ctx = SV.RecordingContext()
        self.ungated_import(pkg).register(ctx)
        self.assertEqual(sorted(ctx.registered), ['CACHE_UNAPPROVED'])

    def test_project_loader_refuses_planted_bytecode(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        self.plant_bytecode(pkg)
        ctx = SV.RecordingContext()
        try:
            SV.load_adapter(pkg).register(ctx)
        except ValueError:
            pass
        self.assertEqual(ctx.registered, {})  # v0.4.2: ['CACHE_UNAPPROVED']

    def test_verify_adapter_fails_with_matching_external_digest_and_no_approval(self):
        b = self.repair()
        external = OA.verify_adapter(b['output_path'])['actual_package_sha256']  # clean digest, as published
        self.plant_bytecode(Path(b['adapter_path']))
        res = OA.verify_adapter(b['output_path'], expected_sha256=external)
        self.assertFalse(res['ok'])  # v0.4.2: ok=True with the same digest
        self.assertEqual(res['approval_status'], 'NONE')

    def test_approve_refuses_tree_with_planted_bytecode(self):
        b = self.repair()
        self.plant_bytecode(Path(b['adapter_path']))
        with self.assertRaises(CORE.PortError):
            OA.approve(b['output_path'], ['summarize'], operator='unit-test', reviewed_model_induced_effects=True)

    def test_existing_approval_does_not_survive_planted_bytecode(self):
        b = self.repair()
        OA.approve(b['output_path'], ['summarize'], operator='unit-test', reviewed_model_induced_effects=True)
        self.plant_bytecode(Path(b['adapter_path']))
        res = OA.verify_adapter(b['output_path'])
        self.assertFalse(res['ok'])
        self.assertEqual(res['approval_status'], 'STALE')

    def test_timestamp_and_checked_hash_caches_also_refused(self):
        for mode in (py_compile.PycInvalidationMode.TIMESTAMP, py_compile.PycInvalidationMode.CHECKED_HASH):
            b = self.repair()
            self.plant_bytecode(Path(b['adapter_path']), mode)
            self.assertFalse(OA.verify_adapter(b['output_path'])['ok'])
            with self.assertRaises(ValueError):
                SV.load_adapter(Path(b['adapter_path']))

    def test_removing_cache_restores_default_deny(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        self.plant_bytecode(pkg)
        shutil.rmtree(pkg / '__pycache__')
        ctx = SV.RecordingContext()
        SV.load_adapter(pkg).register(ctx)
        self.assertEqual(ctx.registered, {})
        self.assertTrue(OA.verify_adapter(b['output_path'])['ok'])


class PreImportGateTests(Base):
    def gate(self):
        from universal_port_v043_testpkg import pre_import_gate as G
        return G

    def test_gate_rejects_every_unexpected_entry(self):
        G = self.gate()
        cases = {
            '__pycache__/__init__.cpython-313.pyc': b'\0',
            '__init__.pyc': b'\0',  # legacy sourceless bytecode beside the source
            '__init__.cpython-313-x86_64-linux-gnu.so': b'\0',  # extension module: preferred over .py
            '__init__.pyd': b'\0',
            'claude_command.abi3.so': b'\0',
            'evil.pth': b'import os\n',
            'helper.py': b'x = 1\n',
            'payload.zip': b'PK',
            '__INIT__.py': b'x = 1\n',  # case variant
            '.DS_Store': b'\0',
            'commands/extra.md': b'unlisted\n',
            'commands/sub/x.md': b'nested\n',
            'commands/run.py': b'x = 1\n',
        }
        for rel, data in cases.items():
            b = self.repair()
            pkg = Path(b['adapter_path'])
            # Case-insensitive Windows filesystems cannot hold __INIT__.py
            # alongside __init__.py: the attempted extra file overwrites the
            # reviewed file instead. Verify that the lock detects this tamper.
            aliases_original = (rel == '__INIT__.py' and (pkg / rel).exists()
                                and (pkg / rel).samefile(pkg / '__init__.py'))
            (pkg / rel).parent.mkdir(parents=True, exist_ok=True)
            (pkg / rel).write_bytes(data)
            if aliases_original:
                # Structural scan sees the original allowed path, but the
                # content digest MUST fail against ADAPTER_LOCK.json.
                self.assertFalse(OA.verify_adapter(b['output_path'])['ok'], rel)
                continue
            res = G.scan(pkg)
            self.assertFalse(res['ok'], rel)
            self.assertIsNone(res['package_sha256'], rel)
            with self.assertRaisesRegex(ValueError, 'pre-import gate', msg=rel):
                SV.load_adapter(pkg)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symlinks unavailable')
    def test_gate_rejects_symlinks(self):
        G = self.gate()
        b = self.repair()
        pkg = Path(b['adapter_path'])
        target = self.tmp / 'outside.md'
        target.write_text('x', encoding='utf-8')
        try:
            os.symlink(target, pkg / 'commands' / 'linked.md')
        except OSError:
            self.skipTest('cannot create symlink here')
        self.assertFalse(G.scan(pkg)['ok'])

    def test_gate_rejects_missing_required_and_listed_files(self):
        G = self.gate()
        b = self.repair()
        pkg = Path(b['adapter_path'])
        (pkg / 'commands' / 'summarize.md').unlink()
        self.assertTrue(any('missing command file' in p for p in G.scan(pkg)['problems']))
        (pkg / 'plugin.yaml').unlink()
        self.assertTrue(any('missing required file: plugin.yaml' in p for p in G.scan(pkg)['problems']))

    def test_gate_never_imports_the_adapter(self):
        G = self.gate()
        b = self.repair()
        pkg = Path(b['adapter_path'])
        (pkg / '__init__.py').write_text('raise SystemExit("imported!")\n', encoding='utf-8')
        res = G.scan(pkg)  # must not raise SystemExit
        self.assertTrue(res['ok'])
        self.assertFalse(OA.verify_adapter(b['output_path'])['ok'])  # content differs from the lock/template

    def test_clean_tree_digest_matches_engine_template_and_lock(self):
        G = self.gate()
        b = self.repair()
        pkg = Path(b['adapter_path'])
        lock = json.loads((Path(b['output_path']) / OA.LOCK_NAME).read_text(encoding='utf-8'))
        res = G.scan(pkg)
        self.assertTrue(res['ok'])
        self.assertEqual(lock['schema'], 'universal-port.adapter-lock/2')
        self.assertEqual(lock['files'], res['files'])
        self.assertEqual(res['package_sha256'], R._package_files_sha256(pkg))
        self.assertEqual(res['package_sha256'], lock['adapter_package_sha256'])
        self.assertEqual(res['package_sha256'], SV.load_adapter(pkg).package_sha256())

    def test_digests_no_longer_exclude_pycache(self):
        b = self.repair()
        pkg = Path(b['adapter_path'])
        mod = SV.load_adapter(pkg)
        before = (R._package_files_sha256(pkg), mod.package_sha256())
        (pkg / '__pycache__').mkdir()
        (pkg / '__pycache__' / 'x.pyc').write_bytes(b'\0')
        self.assertNotEqual(R._package_files_sha256(pkg), before[0])
        self.assertNotEqual(mod.package_sha256(), before[1])

    def test_old_lock_schema_rejected(self):
        b = self.repair()
        lp = Path(b['output_path']) / OA.LOCK_NAME
        lock = json.loads(lp.read_text(encoding='utf-8'))
        lock['schema'] = 'universal-port.adapter-lock/1'
        lp.write_text(json.dumps(lock), encoding='utf-8')
        with self.assertRaisesRegex(CORE.PortError, 'lock schema'):
            OA.verify_adapter(b['output_path'])


class SmokeScriptGateTests(unittest.TestCase):
    """Static checks only (no Windows here)."""

    def test_smoke_script_disables_bytecode_and_regates_before_validate(self):
        code = (ROOT / 'WINDOWS_REPAIR_SMOKE.ps1').read_text(encoding='utf-8').split('#>', 1)[1]
        doctor = code.index('& hermes plugins doctor')
        validate = code.index('& hermes plugins validate')
        self.assertLess(code.index("$env:PYTHONDONTWRITEBYTECODE = '1'"), doctor)
        between = code[doctor:validate]
        self.assertIn('& python @verifyArgs', between)
        self.assertIn("'FAIL_AFTER_DOCTOR'; throw", between)


class StagingTests(Base):
    def test_stage_copies_exact_tree_and_valid_approval(self):
        b = self.repair()
        OA.approve(b['output_path'], ['summarize'], operator='unit-test', reviewed_model_induced_effects=True)
        external = OA.verify_adapter(b['output_path'])['actual_package_sha256']
        home = self.tmp / 'disposable-home'
        res = OA.stage(b['output_path'], str(home), confirm_disposable=True, expected_sha256=external)
        staged = Path(res['staged_adapter'])
        self.assertEqual(staged, (home / 'plugins' / Path(b['adapter_path']).name).resolve())
        self.assertEqual(res['package_sha256'], external)
        self.assertFalse(res['enabled'])
        self.assertTrue((home / 'universal-port-approvals' / (staged.name + '.json')).is_file())
        ctx = SV.RecordingContext()
        SV.load_adapter(staged).register(ctx)  # approval found at HOME/universal-port-approvals
        self.assertEqual(set(ctx.registered), {'summarize'})
        self.assertTrue(OA.verify_adapter(b['output_path'], adapter=str(staged), expected_sha256=external)['ok'])

    def test_stage_without_approval_stages_nothing_registrable(self):
        b = self.repair()
        res = OA.stage(b['output_path'], str(self.tmp / 'h'), confirm_disposable=True)
        self.assertIsNone(res['approval_staged'])
        ctx = SV.RecordingContext()
        SV.load_adapter(Path(res['staged_adapter'])).register(ctx)
        self.assertEqual(ctx.registered, {})

    def test_stage_refusals(self):
        b = self.repair()
        with self.assertRaisesRegex(CORE.PortError, 'disposable'):
            OA.stage(b['output_path'], str(self.tmp / 'h1'), confirm_disposable=False)
        with self.assertRaisesRegex(CORE.PortError, 'real data folder'):
            OA.stage(b['output_path'], str(self.tmp / 'data'), confirm_disposable=True)
        OA.stage(b['output_path'], str(self.tmp / 'h2'), confirm_disposable=True)
        with self.assertRaisesRegex(CORE.PortError, 'overwrite'):
            OA.stage(b['output_path'], str(self.tmp / 'h2'), confirm_disposable=True)
        with self.assertRaisesRegex(CORE.PortError, 'externally supplied'):
            OA.stage(b['output_path'], str(self.tmp / 'h3'), confirm_disposable=True, expected_sha256='0' * 64)

    def test_stage_refuses_source_with_planted_bytecode(self):
        b = self.repair()
        self.plant_bytecode(Path(b['adapter_path']))
        with self.assertRaisesRegex(CORE.PortError, 'nothing staged'):
            OA.stage(b['output_path'], str(self.tmp / 'h'), confirm_disposable=True)
        self.assertFalse((self.tmp / 'h' / 'plugins').exists())

    def test_staged_copy_with_later_planted_cache_is_caught_before_import(self):
        b = self.repair()
        res = OA.stage(b['output_path'], str(self.tmp / 'h'), confirm_disposable=True)
        staged = Path(res['staged_adapter'])
        self.plant_bytecode(staged)
        self.assertFalse(OA.verify_adapter(b['output_path'], adapter=str(staged))['ok'])
        with self.assertRaises(ValueError):
            SV.load_adapter(staged)


if __name__ == '__main__':
    unittest.main()
