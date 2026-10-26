"""A release profile alias must work without weakening database confinement."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from vantage import paths
from vantage.engine import Engine

class ReleasePathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve()
        (self.base/'alias component').mkdir()
        alias=self.base/'alias component'/'..'/'user profile'
        self.addCleanup(patch.stopall)
        patch.object(paths,'RELEASE',True).start()
        patch.dict(os.environ,{'LOCALAPPDATA':str(alias),'XDG_DATA_HOME':str(alias),
                              'VANTAGE_DATABASE':str(self.base/'forbidden.sqlite')}).start()
    def test_profile_directory_is_canonical(self):
        self.assertEqual(paths.runtime_directory(),self.base/'user profile'/'VANTAGE')
        self.assertEqual(paths.runtime_directory(),paths.runtime_directory().resolve())
    def test_fresh_engine_starts_under_normalized_profile(self):
        paths.prepare_release()
        path=paths.runtime_directory()/'vantage.sqlite'
        self.assertEqual(os.environ['VANTAGE_DATABASE'],str(path))
        self.assertFalse(path.exists())
        engine=Engine(path)
        try:self.assertIsNone(engine.state)
        finally:engine.close()
    def test_database_outside_profile_is_still_rejected(self):
        paths.prepare_release();outside=self.base/'forbidden.sqlite'
        with self.assertRaisesRegex(ValueError,'outside'):Engine(outside)
        self.assertFalse(outside.exists())
        self.assertFalse(Path(str(outside)+'.lock').exists())
    def test_development_runtime_policy_is_unchanged(self):
        with patch.object(paths,'RELEASE',False):
            self.assertEqual(paths.runtime_directory(),paths.ROOT/'runtime')
