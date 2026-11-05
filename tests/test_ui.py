import tkinter as tk
import unittest
from unittest.mock import patch
import app
from dashboard import scroll_to, update_media_cards


class InterfaceTests(unittest.TestCase):
    def test_dashboard_and_existing_controls(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch.object(app, "load_config", return_value={}), patch.object(app, "save_config"):
            ui = app.App(root)
            root.update_idletasks()
            self.assertEqual(ui.theme_var.get(), "escuro")
            self.assertEqual(len(ui.media_labels), 4)
            ui.scan = [(None, "jpg", 1024), (None, "audio", 2048)]
            update_media_cards(ui, app.fmt_bytes)
            self.assertEqual(ui.media_labels["jpg"][0].cget("text"), "1")
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
            for target in ("header_frame", "ent_event", "card_p_frame", "queue_list", "checklist_list"):
                scroll_to(ui, target)
            ui._toggle_theme()
            root.update_idletasks()


if __name__ == "__main__":
    unittest.main()
