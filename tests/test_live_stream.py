"""Live display snapshots are case-bound and separate from durable evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from runtime import live


class LiveStreamTests(unittest.TestCase):
    def test_case_isolation_and_fresh_run_clears_old_output(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(live, 'ROOT', Path(folder)):
            one, two = 'a' * 64, 'b' * 64
            self.assertEqual(live.read_snapshot(one)['state'], 'idle')
            live.write_snapshot(one, {'state': 'complete', 'text': 'Old briefing', 'tools': []})
            self.assertEqual(live.read_snapshot(two)['state'], 'idle')
            live.write_snapshot(one, {'state': 'running', 'text': '', 'tools': []})
            self.assertEqual(live.read_snapshot(one)['text'], '')
            self.assertEqual(list((Path(folder) / '.runtime/streams').glob('*.tmp')), [])

    def test_rejects_paths(self):
        with self.assertRaises(ValueError):
            live.read_snapshot('../../private')
