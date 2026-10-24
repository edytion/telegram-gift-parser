import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collector.setup import prepare, load_accounts, validate
from collector.runner import migrate_legacy


class SetupTests(unittest.TestCase):
    def test_first_run_then_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('builtins.input', side_effect=['main', 'bad', '12345']), patch('collector.setup.getpass', return_value='a' * 32):
                prepare(root)
            path = root / 'sessions/asessions.json'
            before = path.read_bytes()
            self.assertEqual(load_accounts(path)[0]['api_id'], 12345)
            with patch('builtins.input', side_effect=AssertionError('must not prompt')):
                prepare(root)
            self.assertEqual(before, path.read_bytes())
            self.assertTrue((root / 'config.json').exists())

    def test_add_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('builtins.input', side_effect=['main', '123']), patch('collector.setup.getpass', return_value='a' * 32):
                prepare(root)
            with patch('builtins.input', side_effect=['MAIN', 'second', '456']), patch('collector.setup.getpass', return_value='b' * 32):
                prepare(root, add=True)
            items = load_accounts(root / 'sessions/asessions.json')
            self.assertEqual([a['name'] for a in items], ['main', 'second'])

    def test_corrupt_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'sessions').mkdir()
            path = root / 'sessions/asessions.json'; path.write_text('{broken')
            with self.assertRaises(ValueError): prepare(root)
            self.assertEqual(path.read_text(), '{broken')

    def test_legacy_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = dict(name='old', session='old_session', api_id=123, api_hash='a' * 32)
            config = dict(accounts=[account], interval=0.3)
            (root / 'config.json').write_text(json.dumps(config))
            (root / 'old_session.session').write_bytes(b'legacy session fixture')
            prepare(root)
            cleaned, items = migrate_legacy(root, config)
            self.assertEqual(items, [account]); self.assertNotIn('accounts', cleaned)
            self.assertEqual((root / 'sessions/old_session.session').read_bytes(), b'legacy session fixture')

    def test_invalid_credentials_and_path(self):
        for updates in ({'session': '../escape'}, {'api_id': 0}, {'api_hash': 'invalid'}):
            account = dict(name='main', session='main', api_id=123, api_hash='a' * 32)
            account.update(updates)
            with self.assertRaises(ValueError): validate([account])


if __name__ == '__main__': unittest.main()
