import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collector.i18n import choose_language, set_language, tr
from collector.setup import prepare
from collector.runner import main


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        set_language('en')

    def test_first_choice_and_saved_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch('builtins.input', side_effect=['wrong', '2']):
                self.assertEqual(choose_language(root), 'ru')
            self.assertEqual(tr('да', 'yes'), 'да')
            (root / 'config.json').write_text(json.dumps({'language': 'ru'}))
            with patch('builtins.input', side_effect=AssertionError('unexpected prompt')):
                self.assertEqual(choose_language(root), 'ru')
                self.assertEqual(choose_language(root, 'en'), 'en')
            self.assertEqual(tr('да', 'yes'), 'yes')

    def test_first_run_english_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = io.StringIO()
            with patch('sys.argv', ['gift-parser.py', '--lang', 'en', '--setup']), patch(
                'builtins.input', side_effect=['main', '123']), patch(
                'collector.setup.getpass', return_value='a' * 32), patch('sys.stdout', out):
                self.assertEqual(main(root), 0)
            self.assertNotRegex(out.getvalue(), '[А-Яа-яЁё]')
            self.assertEqual(json.loads((root / 'config.json').read_text())['language'], 'en')
            with patch('sys.argv', ['gift-parser.py', '--lang', 'ru', '--list-accounts']):
                self.assertEqual(main(root), 0)
            self.assertEqual(json.loads((root / 'config.json').read_text())['language'], 'ru')

    def test_help_does_not_prompt_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for language, expected in [('en', 'Add an account and exit'), ('ru', 'Добавить аккаунт и выйти')]:
                out = io.StringIO()
                with patch('sys.argv', ['gift-parser.py', '--lang', language, '--help']), patch(
                    'builtins.input', side_effect=AssertionError('unexpected prompt')), patch('sys.stdout', out):
                    with self.assertRaises(SystemExit) as exc: main(root)
                self.assertEqual(exc.exception.code, 0)
                self.assertIn(expected, out.getvalue())
                if language == 'en': self.assertNotRegex(out.getvalue(), '[А-Яа-яЁё]')
            self.assertFalse((root / 'config.json').exists())


if __name__ == '__main__': unittest.main()
