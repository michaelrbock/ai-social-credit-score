from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from identity import ensure_identity
from publication import (
    enable,
    initialize_publication,
    publication_path,
    publish_after_score,
    score_summary,
    unpublish,
)


class FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class PublicationTest(unittest.TestCase):
    def test_new_install_enabled_legacy_install_not_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "new" / "publication.json"
            second = Path(temporary_directory) / "old" / "publication.json"
            new_state = initialize_publication(first, new_install=True)
            old_state = initialize_publication(second, new_install=False)
            self.assertTrue(new_state["enabled"])
            self.assertFalse(old_state["enabled"])
            self.assertEqual(len(new_state["token"]), 43)
            self.assertEqual(initialize_publication(first, new_install=False), new_state)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)

    def test_aggregates_old_and_new_score_records_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            scores_file = Path(temporary_directory) / "scores.jsonl"
            records = [
                {"event": "prompt_score", "prompt_id": "one", "overall_niceness": 50,
                 "scored_at": "2026-09-24T20:00:00Z", "schema_version": 1},
                {"event": "prompt_score", "prompt_id": "two", "overall_niceness": 68,
                 "scored_at": "2026-09-24T20:01:00Z", "schema_version": 2,
                 "credit_score": 674},
                {"event": "prompt_score", "prompt_id": "two", "overall_niceness": 70,
                 "scored_at": "2026-09-24T20:02:00Z", "schema_version": 2,
                 "credit_score": 685},
            ]
            scores_file.write_text("\n".join(json.dumps(record) for record in records) + "\n")
            summary = score_summary(scores_file)
            self.assertEqual(summary["prompt_count"], 2)
            self.assertEqual(summary["score"], 630)
            self.assertEqual(summary["score_date"], "2026-09-24T20:02:00Z")

    def test_upload_whitelists_summary_and_random_next_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            identity_file = Path(temporary_directory) / "identity.json"
            scores_file = Path(temporary_directory) / "scores.jsonl"
            ensure_identity(identity_file)
            with patch("publication.secrets.randbelow", return_value=0):
                initialize_publication(publication_path(identity_file), new_install=True)
            scores_file.write_text(json.dumps({
                "event": "prompt_score", "prompt_id": "one", "overall_niceness": 68,
                "scored_at": "2026-09-24T20:00:00Z", "prompt": "private prompt",
                "rationale": "private rationale", "session_id": "private session",
                "cwd": "/private/project",
            }) + "\n")
            sent = []

            def opener(request, timeout):
                self.assertEqual(timeout, 5)
                sent.append(request)
                return FakeResponse(200)

            with patch("publication.secrets.randbelow", return_value=4):
                published = publish_after_score(
                    identity_file, scores_file,
                    {"AI_SOCIAL_CREDIT_SCORE_UPLOAD_URL": "http://127.0.0.1:8765/api/score"},
                    opener=opener,
                )
            self.assertTrue(published)
            self.assertEqual(len(sent), 1)
            body = json.loads(sent[0].data)
            self.assertEqual(set(body), {"username", "score", "prompt_count", "score_date", "rubric_version"})
            self.assertEqual(body["score"], 674)
            self.assertEqual(body["prompt_count"], 1)
            self.assertNotIn("private prompt", sent[0].data.decode())
            state = json.loads(publication_path(identity_file).read_text())
            self.assertEqual(state["last_uploaded_count"], 1)
            self.assertEqual(state["next_upload_count"], 6)

    def test_unpublish_deletes_and_disables_future_uploads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            identity_file = Path(temporary_directory) / "identity.json"
            ensure_identity(identity_file)
            state_file = publication_path(identity_file)
            old_token = initialize_publication(state_file, new_install=True)["token"]
            sent = []

            def opener(request, timeout):
                sent.append(request)
                return FakeResponse(204)

            unpublish(identity_file, {}, opener=opener)
            state = json.loads(state_file.read_text())
            self.assertFalse(state["enabled"])
            self.assertFalse(state["pending_delete"])
            self.assertNotEqual(state["token"], old_token)
            self.assertEqual(sent[0].get_method(), "DELETE")

    def test_existing_user_can_explicitly_enable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            identity_file = Path(temporary_directory) / "identity.json"
            ensure_identity(identity_file)
            state_file = publication_path(identity_file)
            initialize_publication(state_file, new_install=False)
            with patch("publication.secrets.randbelow", return_value=2):
                enable(identity_file, {})
            state = json.loads(state_file.read_text())
            self.assertTrue(state["enabled"])
            self.assertEqual(state["next_upload_count"], 3)


if __name__ == "__main__":
    unittest.main()
