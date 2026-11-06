"""Offline session persistence regression tests."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent import session


class SessionStorageTests(unittest.TestCase):
    def test_round_trip_jsonl(self):
        with TemporaryDirectory() as directory:
            with patch.object(session, "SESSIONS_DIR", Path(directory)):
                expected = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
                session.save_session("session_1", expected)
                self.assertEqual(session.load_session("session_1"), expected)

    def test_missing_session_returns_empty_list(self):
        with TemporaryDirectory() as directory:
            with patch.object(session, "SESSIONS_DIR", Path(directory)):
                self.assertEqual(session.load_session("not_found"), [])

    def test_invalid_identifiers_are_rejected_for_read_and_write(self):
        with TemporaryDirectory() as directory:
            with patch.object(session, "SESSIONS_DIR", Path(directory)):
                for identifier in ("", ".", "..", "../other", "a/b", "name.jsonl", "has space"):
                    with self.subTest(identifier=identifier):
                        with self.assertRaises(ValueError):
                            session.load_session(identifier)
                        with self.assertRaises(ValueError):
                            session.save_session(identifier, [])

    def test_ids_are_unique_within_same_second(self):
        with patch.object(session.time, "strftime", return_value="20261106-120000"):
            ids = {session.new_session_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)
        self.assertTrue(all(value.startswith("20261106-120000-") for value in ids))


if __name__ == "__main__":
    unittest.main()
