import tempfile
import time
import tkinter as tk
import customtkinter as ctk
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from neon import NeonApp


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk.set_appearance_mode("dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / "card"
        self.source.mkdir()
        for name in ("photo.jpg", "photo.cr3", "sound.wav"):
            (self.source / name).write_bytes(name.encode() * 100)
        self.root.withdraw()
        for widget in self.root.winfo_children():
            widget.destroy()
        cfg = {"event": "Teste", "base": str(self.base / "primary"),
               "external_base": str(self.base / "copies"), "verify_hash": True}
        for name, kw in [("load_config", {"return_value": cfg}), ("save_config", {})]:
            p = patch.object(app, name, **kw)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(app, "messagebox")
        self.messages = p.start()
        self.addCleanup(p.stop)
        self.ui = NeonApp(self.root)
        self.ui.source_var.set(str(self.source))
        self.ui._play_sound = lambda ok: None
        self.root.update_idletasks()

    def test_navigation_options_and_lock(self):
        ui = self.ui
        self.assertEqual(ui.theme_var.get(), "escuro")
        for page in ("ingest", "settings", "history", "reports", "queue"):
            ui.show_page(page)
            self.assertEqual(ui.active_page, "ingest" if page == "queue" else page)
        ui.copy_enabled_var.set(False)
        self.assertEqual(ui._copy_flags(), (False,) * 4)
        self.assertEqual(ui.copies_frame.winfo_manager(), "")
        ui.copy_enabled_var.set(True)
        self.assertEqual(ui.copies_frame.winfo_manager(), "pack")
        ui.mode_var.set("multicam")
        ui._toggle_mode()
        self.assertEqual(ui._mode_label(), "Câmera")
        ui._toggle_event_lock()
        self.assertEqual(str(ui.ent_event.cget("state")), "disabled")

    def test_analysis_and_source_invalidation(self):
        ui = self.ui
        ui.analyze()
        self.assertEqual(len(ui.scan), 3)
        self.assertEqual(ui.media_labels["jpg"][0].cget("text"), "1 arquivos")
        ui.source_var.set(str(self.base / "missing"))
        self.assertEqual(ui.scan, [])
        self.assertEqual(ui.media_labels["jpg"][0].cget("text"), "— arquivos")
        self.assertEqual(ui.btn_eject.cget("state"), "disabled")

    def test_queue_selection_and_mutation_guard(self):
        ui = self.ui
        ui.add_to_queue()
        ui.prof_var.set("Camera_2")
        ui.add_to_queue()
        ui.queue_list.choose(1)
        self.assertEqual(ui.queue_list.curselection(), (1,))
        ui.copying = True
        ui.remove_from_queue()
        ui.clear_queue()
        self.assertEqual(len(ui.queue_items), 2)
        ui.copying = False
        ui.remove_from_queue()
        self.assertEqual(len(ui.queue_items), 1)
        ui.clear_queue()
        self.assertEqual(ui.queue_items, [])

    def test_queue_download_end_to_end(self):
        ui = self.ui
        ui.add_to_queue()
        ui.start_queue()
        self.assertTrue(ui.copying)
        deadline = time.monotonic() + 15
        while ui.copying and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.02)
        self.assertFalse(ui.copying)
        self.assertTrue(ui.last_success)
        self.assertEqual(ui.progress_var.get(), "100%")
        self.assertEqual(ui.queue_list.states[0], "Conferido")
        self.assertEqual(ui.btn_eject.cget("state"), "normal")
        event = ui._event_root()
        self.assertTrue((event / "relatorio-descarga.txt").is_file())
        self.assertEqual(len(app.read_history(event)), 1)
        self.messages.showerror.assert_not_called()

    def test_minimum_window_keeps_actions_visible(self):
        self.root.deiconify()
        self.root.geometry("1180x780")
        self.root.update()
        for w in (self.ui.btn_copy, self.ui.btn_queue, self.ui.btn_eject):
            self.assertTrue(w.winfo_ismapped())
            self.assertLessEqual(w.winfo_rooty() + w.winfo_height(),
                                 self.root.winfo_rooty() + self.root.winfo_height())


if __name__ == "__main__":
    unittest.main()
