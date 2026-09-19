"""Isolated tests: no application imports, database or production writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import context


class ContextTest(unittest.TestCase):
    def test_incremental_and_ignore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.gitignore').write_text('ignored/\n*.secret.py\n')
            for folder in ['ignored', 'vendor', 'nested/node_modules']:
                (root / folder).mkdir(parents=True)
                (root / folder / 'bad.py').write_text('invalid python')
            (root / 'key.secret.py').write_text('invalid python')
            a = root / 'a.py'
            a.write_text('def first(): return 1\n')
            self.assertEqual(context.build(root)['parsed'], ['a.py'])
            original = Path.read_bytes
            def guarded(path):
                if path == a:
                    raise AssertionError('unchanged source read')
                return original(path)
            with patch.object(Path, 'read_bytes', guarded):
                self.assertEqual(context.build(root)['parsed'], [])
            with patch.object(context, 'parse', side_effect=AssertionError('unchanged source parsed')):
                self.assertEqual(context.build(root)['parsed'], [])
            a.write_text('def second(): return 2\n')
            self.assertEqual(context.build(root)['parsed'], ['a.py'])
            a.rename(root / 'renamed.py')
            change = context.build(root)
            self.assertEqual(change['removed'], ['a.py'])
            self.assertEqual(change['parsed'], ['renamed.py'])
            symbols = context.read(root / '.codex-context/symbols-index.json', {})
            self.assertEqual(list(symbols), ['renamed.py:second'])
            before = (root / '.codex-context/symbols-index.json').read_bytes()
            context.build(root, rebuild=True)
            self.assertEqual(before, (root / '.codex-context/symbols-index.json').read_bytes())

    def test_real_features(self):
        context.build()
        out = context.ROOT / '.codex-context'
        routes = context.read(out / 'routes.json', [])
        for endpoint in ['/api/assets', '/api/auth/login']:
            self.assertTrue(any(r['path'] == endpoint for r in routes), endpoint)
        result = context.query(context.ROOT, 'registro activo codigo barras', 6)
        self.assertIn('backend/app/routes/assets.py', result['files'])
        impact = context.impact(context.ROOT, 'apply_asset_payload', 1, 30)
        self.assertTrue(any(e['target'].endswith(':create_asset') for e in impact['edges']))
        self.assertTrue(any(e['target'].endswith(':Asset') for e in impact['edges']))
        tables = context.read(out / 'database-map.json', {})['tables']
        self.assertEqual(tables['assets']['primary_keys'], ['id'])
        self.assertTrue(tables['assets']['used_by'])
        self.assertTrue(any('simulation' in r['path'] for r in routes))
        for path in context.read(out / 'files-index.json', {}):
            self.assertFalse(any(x in path.split('/') for x in context.SKIP))

    def test_failure_keeps_previous_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / 'a.py'
            p.write_text('class A: pass\n')
            context.build(root)
            before = (root / '.codex-context/symbols-index.json').read_bytes()
            p.write_text('def broken(')
            with self.assertRaises(SyntaxError):
                context.build(root)
            self.assertEqual(before, (root / '.codex-context/symbols-index.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
