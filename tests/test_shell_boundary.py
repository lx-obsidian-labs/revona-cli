"""Regression checks for the opt-in agent shell execution boundary."""

import os
import unittest
from unittest.mock import patch

from agent.tools import _safe_shell, run_shell


class ShellBoundaryTests(unittest.TestCase):
    def test_prefix_bypass_is_rejected(self):
        self.assertFalse(_safe_shell("pythonmalicious -c something"))
        self.assertFalse(_safe_shell("git statusmalicious"))
        self.assertFalse(_safe_shell(""))

    def test_supported_executables_are_recognized(self):
        self.assertTrue(_safe_shell("python --version"))
        self.assertTrue(_safe_shell("git status --short"))
        self.assertFalse(_safe_shell("git push origin main"))

    def test_shell_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("agent.tools.subprocess.run") as runner:
                result = run_shell("python --version")
                self.assertIn("BLOCKED", result)
                runner.assert_not_called()

    def test_opt_in_uses_no_shell_interpreter(self):
        with patch.dict(os.environ, {"REVONA_ALLOW_SHELL": "1"}):
            with patch("agent.tools.subprocess.run") as runner:
                runner.return_value.returncode = 0
                runner.return_value.stdout = "Python 3"
                runner.return_value.stderr = ""
                result = run_shell("python --version")
                self.assertIn("exit=0", result)
                self.assertEqual(runner.call_args.args[0], ["python", "--version"])
                self.assertIs(runner.call_args.kwargs["shell"], False)


if __name__ == "__main__":
    unittest.main()
