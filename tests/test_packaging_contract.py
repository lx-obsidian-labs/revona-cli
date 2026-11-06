"""Offline package-contract tests: no API credentials or network access required."""

import ast
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagingContractTests(unittest.TestCase):
    def test_console_entry_point_is_declared(self):
        with (ROOT / "pyproject.toml").open("rb") as f:
            project = tomllib.load(f)["project"]
        self.assertEqual(project["scripts"]["revona"], "agent.cli:main")
        self.assertIn(">=3.11", project["requires-python"])

    def test_direct_httpx_import_has_declared_dependency(self):
        with (ROOT / "pyproject.toml").open("rb") as f:
            project = tomllib.load(f)["project"]
        names = {
            dep.split(">=")[0].split("==")[0].split("[")[0].lower()
            for dep in project["dependencies"]
        }
        self.assertIn("httpx", names)
        source = (ROOT / "agent" / "client.py").read_text(encoding="utf-8")
        imports = ast.parse(source)
        self.assertTrue(
            any(isinstance(node, ast.ImportFrom) and node.module == "httpx" for node in imports.body)
        )

    def test_entry_point_function_exists(self):
        tree = ast.parse((ROOT / "agent" / "cli.py").read_text(encoding="utf-8"))
        self.assertTrue(
            any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
                for node in tree.body)
        )


if __name__ == "__main__":
    unittest.main()
