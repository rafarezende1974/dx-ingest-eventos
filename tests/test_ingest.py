import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "card"
        self.source.mkdir()
        for name in ("photo.jpg", "photo.cr3", "clip.mov", "sound.wav"):
            (self.source / name).write_bytes((name.encode() + b"x") * 1024)
        self.original = {p.name: p.read_bytes() for p in self.source.iterdir()}
        self.files, _ = app.scan_source(self.source)
        self.event = self.base / "primary" / "event"
        self.dests = app.destinations_for(self.event, "Camera_Palco", self.base / "backup", leva=1)
        self.manifest = {}

    def run_card(self, **kwargs):
        return app.process_card(self.files, self.dests, self.event, "Camera_Palco",
                                verify_hash=True, manifest=self.manifest, **kwargs)

    def test_all_media_backup_hash_and_source_unchanged(self):
        progress = []
        report = self.run_card(progress_cb=progress.append)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["copied"], 8)
        self.assertEqual(sum(progress), 2 * sum(s for _, _, s in self.files))
        for key, folder in self.dests.items():
            name = {"jpg": "photo.jpg", "raw": "photo.cr3", "video": "clip.mov", "audio": "sound.wav"}[key.split('_')[0]]
            self.assertEqual((folder / name).read_bytes(), self.original[name])
        self.assertEqual({p.name: p.read_bytes() for p in self.source.iterdir()}, self.original)
        self.assertFalse((self.event / ".staging").exists())

    def test_persistent_resume_and_deleted_backup(self):
        self.run_card()
        app.save_manifest(self.event, self.manifest)
        self.manifest = app.load_manifest(self.event)
        self.assertEqual(self.run_card()["copied"], 0)
        target = self.dests["raw_copy"] / "photo.cr3"
        target.unlink()
        self.assertEqual(self.run_card()["failed"], 0)
        self.assertEqual(target.read_bytes(), self.original[target.name])

    def test_copies_disabled(self):
        report = self.run_card(copy_jpg=False, copy_raw=False, copy_video=False, copy_audio=False)
        self.assertEqual(report["copied"], 4)
        self.assertFalse((self.base / "backup").exists())

    def test_hash_detects_same_size_corruption(self):
        self.run_card()
        target = self.dests["raw_copy"] / "photo.cr3"
        target.write_bytes(b"z" * target.stat().st_size)
        self.assertEqual(self.run_card()["failed"], 0)
        self.assertIn(self.original[target.name], [p.read_bytes() for p in target.parent.iterdir()])
        self.assertEqual(target.read_bytes(), b"z" * target.stat().st_size)

    def test_primary_collision_preserves_both_contents(self):
        self.run_card()
        target = self.dests["raw_backup"] / "photo.cr3"
        target.write_bytes(b"z" * target.stat().st_size)
        self.assertEqual(self.run_card()["failed"], 0)
        self.assertEqual(target.read_bytes(), b"z" * target.stat().st_size)
        self.assertEqual((target.parent / "photo_1.cr3").read_bytes(), self.original[target.name])

    def test_worker_exception_is_reported(self):
        import queue
        ui = app.App.__new__(app.App)
        ui.msg_queue = queue.Queue()
        with patch.object(ui, "_run_jobs", side_effect=OSError("unplugged")):
            ui._run_jobs_safely([], self.event)
        self.assertEqual(ui.msg_queue.get_nowait(), ("error", "unplugged"))

    def test_multicamera_queue_reports_and_backups(self):
        import queue
        ui = app.App.__new__(app.App)
        ui.msg_queue = queue.Queue()
        ui._job_settings = {"copy_flags": (True,) * 4, "external_base": str(self.base / "copies"),
                            "verify_hash": True, "mode_label": "Câmera"}
        jobs = [(str(self.source), name, self.files, 0) for name in ("Camera_Palco", "Camera_Geral")]
        ui._run_jobs_safely(jobs, self.event)
        events = []
        while not ui.msg_queue.empty():
            events.append(ui.msg_queue.get_nowait())
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(events[-1][1][0]["failed"], 0)
        self.assertEqual(len(app.read_history(self.event)), 2)
        for name in ("Camera_Palco", "Camera_Geral"):
            self.assertEqual((self.event / "01_Fotos_JPG" / name / "Cartao_1" / "photo.jpg").read_bytes(),
                             self.original["photo.jpg"])

    def test_staging_failure_never_publishes(self):
        with patch.object(app, "copy_one", side_effect=OSError("disk unavailable")):
            report = self.run_card()
        self.assertEqual(report["failed"], 4)
        self.assertFalse(any(p.exists() for p in self.dests.values()))
        self.assertEqual(self.manifest, {})

    def test_reports_and_history(self):
        report = self.run_card()
        app.write_report(self.event, "Camera_Palco", str(self.source), self.files, report,
                         leva=1, mode_label="Câmera")
        app.append_history(self.event, "Camera_Palco", 1, str(self.source), self.files, report)
        self.assertTrue((self.event / "relatorio-descarga.txt").exists())
        self.assertEqual(len(app.read_history(self.event)), 1)


if __name__ == "__main__":
    unittest.main()
