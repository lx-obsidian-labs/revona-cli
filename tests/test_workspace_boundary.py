"""Offline tests for the Revona workspace file boundary."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent import tools


class WorkspaceBoundaryTests(unittest.TestCase):
    def test_normal_workspace_file_roundtrip(self):
        with TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REVONA_WORKSPACE": directory}):
                self.assertIn("Wrote", tools.write_file("notes/sample.txt", "hello"))
                self.assertEqual(tools.read_file("notes/sample.txt"), "hello")
                self.assertIn("Edited", tools.edit_file("notes/sample.txt", "hello", "updated"))
                self.assertEqual(tools.read_file("notes/sample.txt"), "updated")

    def test_parent_directory_escape_is_rejected(self):
        with TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REVONA_WORKSPACE": directory}):
                with self.assertRaises(ValueError):
                    tools.write_file("../outside.txt", "unsafe")
                with self.assertRaises(ValueError):
                    tools.read_file("../outside.txt")

    def test_absolute_outside_path_is_rejected(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"REVONA_WORKSPACE": directory}):
                with self.assertRaises(ValueError):
                    tools.list_files(outside)

    def test_symlink_escape_is_rejected(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            link = Path(directory) / "outside"
            try:
                link.symlink_to(Path(outside), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with patch.dict(os.environ, {"REVONA_WORKSPACE": directory}):
                with self.assertRaises(ValueError):
                    tools.write_file("outside/secret.txt", "unsafe")

    def test_grep_rejects_outside_directory(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"REVONA_WORKSPACE": directory}):
                with self.assertRaises(ValueError):
                    tools.grep_files("secret", outside)


if __name__ == "__main__":
    unittest.main()
