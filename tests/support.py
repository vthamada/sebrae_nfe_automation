import tempfile
import unittest
from pathlib import Path

from src.config import settings
from src.database import init_db


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self._original_db_path = settings.db_path
        self._temp_dir = tempfile.TemporaryDirectory(dir=Path.cwd())
        object.__setattr__(settings, "db_path", Path(self._temp_dir.name) / "test.db")
        init_db()

    def tearDown(self):
        object.__setattr__(settings, "db_path", self._original_db_path)
        self._temp_dir.cleanup()
