"""Regression tests for workspace confinement in agent tools.

These tests are expected to fail until the workspace-boundary patch is applied.
"""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent import tools


class WorkspaceHardeningTests(unittest.TestCase):
    def test_command_working_directory_cannot_escape_workspace(self):
        with TemporaryDirectory() as workspace, TemporaryDirectory() as outside:
            with patch.dict(os.environ, {"REVONA_WORKSPACE": workspace, "REVONA_ALLOW_SHELL": "1"}):
                result = tools.run_shell("python --version", cwd=outside)
                self.assertIn("ERROR", result)

    def test_file_search_does_not_read_symlinked_outside_file(self):
        with TemporaryDirectory() as workspace, TemporaryDirectory() as outside:
            secret = Path(outside) / "private.txt"
            secret.write_text("UNIQUE_OUTSIDE_WORKSPACE_TOKEN", encoding="utf-8")
            link = Path(workspace) / "linked.txt"
            try:
                link.symlink_to(secret)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with patch.dict(os.environ, {"REVONA_WORKSPACE": workspace}):
                result = tools.grep_files("UNIQUE_OUTSIDE_WORKSPACE_TOKEN")
                self.assertNotIn("UNIQUE_OUTSIDE_WORKSPACE_TOKEN", result)


if __name__ == "__main__":
    unittest.main()
