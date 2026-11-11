import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_import_assurance import AssuranceError, assess_official_preview, configured_memory_limit

SEP = "\n§\n"


def official_merge(existing, incoming, limit):
    merged = list(existing)
    known = {x.casefold() for x in existing}
    stats = {'existing': len(existing), 'added': 0, 'duplicates': 0, 'overflowed': 0}
    for item in incoming:
        if item.casefold() in known:
            stats['duplicates'] += 1
            continue
        if len(SEP.join(merged + [item])) > limit:
            stats['overflowed'] += 1
            continue
        merged.append(item)
        known.add(item.casefold())
        stats['added'] += 1
    return merged, stats


def official_parse(path):
    return [x.strip() for x in path.read_text(encoding='utf-8').split(SEP) if x.strip()] if path.exists() else []


class FakeOfficialImporter:
    def __init__(self, root, batches, extra=(), execute=False):
        self.execute = execute
        self.target_root = Path(root)
        self.batches = batches
        self.extra = extra
        self.items = []
        self.agent = 'claude-code'

    def record(self, kind, source, destination, status, reason='', **details):
        self.items.append({'kind': kind, 'source': str(source),
                           'destination': str(destination), 'status': status,
                           'reason': reason, **details})

    def merge_memory_entries(self, *args):
        raise AssertionError('unwrapped upstream merge invoked')

    def run(self):
        for i, batch in enumerate(self.batches):
            self.merge_memory_entries('context', f'source-{i}',
                                      self.target_root / 'memories' / 'MEMORY.md', batch)
        for kind, status in self.extra:
            self.record(kind, 'source', 'target', status)
        return {'agent': self.agent, 'dry_run': not self.execute,
                'items': self.items}


class OfficialImportAssuranceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.memory = self.root / 'memories' / 'MEMORY.md'
        self.memory.parent.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def preview(self, batches, extra=(), execute=False, limit=80):
        importer = FakeOfficialImporter(self.root, batches, extra, execute)
        return importer, assess_official_preview(importer, memory_char_limit=limit,
                             merge_entries=official_merge,
                             parse_existing_memory_entries=official_parse)

    def test_clean_preview_no_writes_or_autoapproval(self):
        self.memory.write_text('existing', encoding='utf-8')
        before = self.memory.read_bytes()
        imp, r = self.preview([['small']])
        self.assertEqual(r['gate'], 'REVIEW_ONLY')
        self.assertEqual(r['counts']['imported'], 1)
        self.assertFalse(r['approval_created'])
        self.assertFalse(r['apply_performed'])
        self.assertEqual(self.memory.read_bytes(), before)
        self.assertNotIn('merge_memory_entries', imp.__dict__)

    def test_actual_limit_blocks_oversized_entry(self):
        imp, r = self.preview([['x' * 90]], limit=80)
        self.assertEqual(r['gate'], 'HOLD')
        self.assertEqual(r['memory_events'][0]['overflowed'], 1)
        self.assertFalse(self.memory.exists())

    def test_cumulative_batches_detect_overflow(self):
        _, r = self.preview([['A' * 45], ['B' * 45]], limit=80)
        self.assertEqual(r['gate'], 'HOLD')
        self.assertEqual([x['overflowed'] for x in r['memory_events']], [0, 1])

    def test_existing_over_budget_blocks(self):
        self.memory.write_text('x' * 90, encoding='utf-8')
        _, r = self.preview([['new']], limit=80)
        self.assertEqual(r['gate'], 'HOLD')
        self.assertIn('existing memory already exceeds the configured limit', r['reasons'])

    def test_loss_ledger_preserves_skipped_and_conflicts(self):
        _, r = self.preview([], [('commands', 'skipped'), ('skill', 'conflict')])
        self.assertEqual(r['counts']['skipped'], 1)
        self.assertEqual(r['counts']['conflict'], 1)
        self.assertEqual(r['gate'], 'HOLD')
        self.assertFalse(r['source_inventory_exhaustive'])

    def test_no_execute_path(self):
        with self.assertRaises(AssuranceError):
            self.preview([['entry']], execute=True)

    def test_fresh_instance_required(self):
        importer = FakeOfficialImporter(self.root, [])
        importer.items.append({'status':'imported'})
        with self.assertRaises(AssuranceError):
            assess_official_preview(importer, memory_char_limit=80, merge_entries=official_merge,
                                    parse_existing_memory_entries=official_parse)

    def test_bad_limit_fails_closed(self):
        for v in [0, True, '80', -5, 1_000_001]:
            with self.subTest(v=v), self.assertRaises(AssuranceError):
                self.preview([], limit=v)

    def test_config_limit(self):
        self.assertEqual(configured_memory_limit({'memory':{'memory_char_limit':'3100'}}),3100)
        self.assertEqual(configured_memory_limit({}),2200)
        with self.assertRaises(AssuranceError):
            configured_memory_limit({'memory': {'memory_char_limit': False}})

    def test_instance_override_restored(self):
        imp = FakeOfficialImporter(self.root, [])
        f=lambda *a: None
        imp.merge_memory_entries=f
        assess_official_preview(imp,memory_char_limit=80,merge_entries=official_merge,
                                parse_existing_memory_entries=official_parse)
        self.assertIs(imp.merge_memory_entries, f)

    def test_error_fails_closed(self):
        _,r=self.preview([], [('settings','error')])
        self.assertEqual(r['gate'],'HOLD')

    def test_sha_is_stable_for_identical_plan(self):
        _,a=self.preview([['hello']])
        _,b=self.preview([['hello']])
        self.assertEqual(a['receipt_sha256'], b['receipt_sha256'])


if __name__ == '__main__':
    unittest.main()
