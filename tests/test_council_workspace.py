import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gateway import council, council_workspace as workspace


class _NoStartThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self):
        return None


class CouncilWorkspaceTests(unittest.TestCase):
    def setUp(self):
        workspace._RUNS.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runs_dir = Path(self.temp.name)

    def test_start_is_consultation_only_and_does_not_spawn_execution(self):
        with mock.patch.object(workspace, "RUNS_DIR", self.runs_dir), \
             mock.patch.object(workspace, "_member_specs", return_value=[
                 ("Codex", lambda _topic: None, lambda: "C:/bin/codex.exe")
             ]), \
             mock.patch.object(workspace.threading, "Thread", _NoStartThread), \
             mock.patch.object(council, "run") as legacy_run:
            created = workspace.start("Bu arxitektura qərarını tənqidi qiymətləndir")

        self.assertEqual(created["mode"], "consultation-only")
        self.assertFalse(created["auto_execute"])
        self.assertEqual(created["status"], "queued")
        legacy_run.assert_not_called()

    def test_consultation_persists_member_notes_and_synthesis(self):
        run_id = "20260722T120000-deadbeef"
        workspace._RUNS[run_id] = {
            "id": run_id,
            "topic": "Vahid Hub qərarını qiymətləndir",
            "status": "queued",
            "mode": "consultation-only",
            "auto_execute": False,
            "created_at": 1.0,
            "started_at": None,
            "finished_at": None,
            "members": [{"name": "Codex", "status": "queued", "text": "", "seconds": 0, "auth": ""}],
            "synthesis": None,
            "error": None,
        }
        note = council.CouncilNote("Codex", "ok", "Hub vahid shell olmalıdır.", 1.2)
        synthesis = council.CouncilNote("Codex chair", "ok", "PILOT qərarı.", 0.8)
        with mock.patch.object(workspace, "RUNS_DIR", self.runs_dir), \
             mock.patch.object(workspace, "_member_specs", return_value=[
                 ("Codex", lambda _topic: note, lambda: "codex")
             ]), \
             mock.patch.object(council, "_synthesize_with_cli", return_value=synthesis), \
             mock.patch.object(council, "run") as legacy_run:
            workspace._run_consultation(run_id)

        finished = workspace.get(run_id)
        self.assertEqual(finished["status"], "done")
        self.assertEqual(finished["members"][0]["text"], note.text)
        self.assertEqual(finished["synthesis"]["text"], synthesis.text)
        self.assertTrue((self.runs_dir / f"{run_id}.json").is_file())
        self.assertTrue((self.runs_dir / f"{run_id}.md").is_file())
        legacy_run.assert_not_called()

    def test_invalid_topic_and_unsafe_run_id_are_rejected(self):
        with self.assertRaises(ValueError):
            workspace.start("qısa")
        self.assertIsNone(workspace.get("../../.env"))

    def test_no_usable_member_note_finishes_without_slow_synthesis_fallback(self):
        run_id = "20260722T120001-feedface"
        workspace._RUNS[run_id] = {
            "id": run_id, "topic": "Runtime yoxlaması", "status": "queued",
            "mode": "consultation-only", "auto_execute": False,
            "created_at": 1.0, "started_at": None, "finished_at": None,
            "members": [{"name": "Codex", "status": "queued", "text": "", "seconds": 0, "auth": ""}],
            "synthesis": None, "error": None,
        }
        unavailable = council.CouncilNote("Codex", "timeout", "timeout", 60.0)
        with mock.patch.object(workspace, "RUNS_DIR", self.runs_dir), \
             mock.patch.object(workspace, "_member_specs", return_value=[
                 ("Codex", lambda _topic: unavailable, lambda: "codex")
             ]), \
             mock.patch.object(council, "_synthesize_with_cli") as synth:
            workspace._run_consultation(run_id)

        finished = workspace.get(run_id)
        self.assertEqual(finished["status"], "done")
        self.assertEqual(finished["synthesis"]["status"], "unavailable")
        synth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
