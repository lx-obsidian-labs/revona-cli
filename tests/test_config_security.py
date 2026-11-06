"""Offline regression tests for credential handling and TOML configuration."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch

from agent import config


class ConfigSecurityTests(unittest.TestCase):
    def test_legacy_file_key_is_ignored(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.toml"
            file.write_text('[agent]\nmodel = "test-model"\napi_key = "legacy-secret"\n')
            with patch.object(config, "CONFIG_PATH", file):
                with patch.dict(os.environ, {"NVIDIA_API_KEY": "environment-secret"}):
                    cfg = config.load_config()
                    self.assertEqual(cfg["model"], "test-model")
                    self.assertNotIn("api_key", cfg)
                    self.assertEqual(config.get_api_key(cfg), "environment-secret")

    def test_credential_is_not_persisted(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.toml"
            with patch.object(config, "CONFIG_PATH", file):
                config.save_config({"model": "test-model", "api_key": "do-not-write"})
                self.assertNotIn("do-not-write", file.read_text())
                with file.open("rb") as stream:
                    self.assertEqual(tomllib.load(stream)["agent"]["model"], "test-model")

    def test_model_escaping_preserves_valid_toml(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "config.toml"
            model = 'provider/model "quoted"\\path'
            with patch.object(config, "CONFIG_PATH", file):
                config.save_config({"model": model})
                self.assertEqual(config.load_config()["model"], model)

    def test_missing_environment_key_fails_without_exposing_legacy_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA_API_KEY"):
                config.get_api_key({"api_key": "legacy-secret"})


if __name__ == "__main__":
    unittest.main()
