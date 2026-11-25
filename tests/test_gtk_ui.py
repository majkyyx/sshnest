"""Exercise the replacement GUI using an isolated config and a GTK-capable display."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from sshnest.config import ConfigStore
from sshnest.main import MainWindow, build_tree
from sshnest.models import Connection, Folder
from gi.repository import Adw, Gio, GLib, Gtk


def drain(duration=0.04):
    deadline = time.monotonic() + duration
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.002)


class GtkWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Adw.Application(
            application_id="io.github.sshnest.Tests",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        cls.app.register(None)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        sample = Path(__file__).resolve().parents[1] / "samples/screenshot_config.json"
        self.path.write_bytes(sample.read_bytes())
        self.store = ConfigStore(self.path)
        self.window = MainWindow(self.app, self.store)
        self.window.present()
        drain()

    def tearDown(self):
        dialog = self.window.get_visible_dialog()
        while dialog:
            dialog.force_close()
            drain()
            dialog = self.window.get_visible_dialog()
        self.window.close()
        drain()
        self.temp.cleanup()

    def select(self, kind, item_id):
        self.window._expand_all(True)
        for i in range(self.window.tree_model.get_n_items()):
            if self.window.tree_model.get_item(i).get_item().key == (kind, item_id):
                self.window.selection.set_selected(i)
                drain()
                return
        self.fail(f"Missing row {kind}:{item_id}")

    def test_tree_search_details_and_folder_choices(self):
        w = self.window
        self.assertEqual(
            w.tree_model.get_n_items(), 3
        )  # no duplicated root connections
        self.select("connection", "connection-db-primary")
        self.assertEqual(w.title_label.get_label(), "primary")
        self.assertEqual(w.detail_rows["host"].get_subtitle(), "db-primary.example.net")
        self.assertEqual(w.detail_stack.get_visible_child_name(), "connection")
        self.assertIn(
            ("folder-databases", "example / production / databases"),
            w._folder_choices(),
        )
        w.search.set_text("db-primary")
        w.refresh_tree()
        keys = [
            w.tree_model.get_item(i).get_item().key
            for i in range(w.tree_model.get_n_items())
        ]
        self.assertEqual(
            keys,
            [
                ("folder", "folder-example"),
                ("folder", "folder-production"),
                ("folder", "folder-databases"),
                ("connection", "connection-db-primary"),
            ],
        )
        w.search.set_text("nonexistent")
        w.refresh_tree()
        self.assertEqual(w.list_stack.get_visible_child_name(), "empty")
        self.assertFalse(w.lookup_action("ssh").get_enabled())

    def test_connection_dialog_validates_saves_edits_and_rejects_duplicates(self):
        w = self.window
        self.select("folder", "folder-lab")
        dialog = w._add_connection()
        drain()
        dialog._save()
        self.assertTrue(dialog.error_label.get_visible())
        self.assertEqual(len(self.store.connections), 7)
        dialog.name_input.set_text("new-host")
        dialog.host_input.set_text("new.example.net")
        dialog.user_input.set_text("alice")
        dialog.password_input.set_text("test-only-secret")
        dialog.path_input.set_text("/srv/test")
        dialog._save()
        drain()
        saved = ConfigStore(self.path)
        saved.load()
        connection = next(c for c in saved.connections if c.name == "new-host")
        self.assertEqual(
            (connection.folder_id, connection.password, connection.remote_path),
            ("folder-lab", "test-only-secret", "/srv/test"),
        )
        self.select("connection", connection.id)
        editor = w._edit_selected()
        self.assertEqual(editor.host_input.get_text(), "new.example.net")
        editor.name_input.set_text("forge")
        editor._save()
        self.assertIn("already exists", editor.error_label.get_label())
        editor.name_input.set_text("renamed")
        editor._save()
        drain()
        self.assertEqual(w._selected_connection().name, "renamed")
        rename = w._rename_selected()
        rename.name_input.set_text("final-name")
        rename._save()
        drain()
        self.assertEqual(w._selected_connection().name, "final-name")

    def test_nested_folder_edit_and_recursive_delete_require_confirmation(self):
        w = self.window
        self.select("folder", "folder-production")
        dialog = w._add_folder()
        dialog.name_input.set_text("extra")
        dialog._save()
        drain()
        folder = next(f for f in self.store.folders if f.name == "extra")
        self.assertEqual(folder.parent_id, "folder-production")
        edit = w._edit_selected()
        edit.name_input.set_text("databases")
        edit._save()
        self.assertIn("already exists", edit.error_label.get_label())
        edit.name_input.set_text("extra-renamed")
        edit._save()
        drain()
        self.select("folder", "folder-production")
        confirmation = w._delete_selected()
        confirmation.emit("response", "cancel")
        confirmation.force_close()
        drain()
        self.assertEqual(len(self.store.connections), 7)
        confirmation = w._delete_selected()
        confirmation.emit("response", "confirm")
        confirmation.force_close()
        drain()
        self.assertFalse(any(f.id == "folder-databases" for f in self.store.folders))
        self.assertEqual(
            {c.name for c in self.store.connections}, {"bastion", "web", "forge"}
        )
        saved = json.loads(self.path.read_text())
        self.assertEqual(len(saved["connections"]), 3)

    def test_failed_save_can_be_corrected_and_retried(self):
        w = self.window
        self.select("connection", "connection-bastion")
        editor = w._edit_selected()
        editor.name_input.set_text("changed")
        with patch.object(self.store, "save", side_effect=OSError("test disk error")):
            editor._save()
        self.assertIn("test disk error", editor.error_label.get_label())
        self.assertEqual(w._selected_connection().name, "bastion")
        editor._save()
        drain()
        check = ConfigStore(self.path)
        check.load()
        self.assertEqual(
            next(c.name for c in check.connections if c.id == "connection-bastion"),
            "changed",
        )

    def test_history_merge_preserves_existing_connections(self):
        w = self.window
        folder = Folder(name="lab")
        imported = [
            Connection(
                name="forge", host="forge.lab.local", user="admin", folder_id=folder.id
            ),
            Connection(
                name="new", host="new.lab.local", user="admin", folder_id=folder.id
            ),
        ]
        with patch(
            "sshnest.main.import_from_history", return_value=([folder], imported)
        ):
            dialog = w._import_history()
            self.assertEqual(len(self.store.connections), 7)
            dialog.emit("response", "confirm")
            dialog.force_close()
            drain()
        self.assertEqual(len(self.store.connections), 8)
        self.assertEqual(
            next(
                c.folder_id for c in self.store.connections if c.host == "new.lab.local"
            ),
            "folder-lab",
        )

    def test_launch_uses_worker_and_reports_failure_on_main_loop(self):
        w = self.window
        self.select("connection", "connection-bastion")
        with patch(
            "sshnest.main.open_ssh", side_effect=RuntimeError("test launch failed")
        ) as launch:
            w._launch("SSH")
            drain(0.15)
            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[0].host, "bastion.example.net")
            error = w.get_visible_dialog()
            self.assertEqual(error.get_heading(), "Open SSH failed")
            self.assertEqual(error.get_body(), "test launch failed")
        with patch("sshnest.main.open_sftp") as launch:
            w._launch("SFTP")
            drain(0.15)
            launch.assert_called_once()

    def test_right_click_menu_and_narrow_navigation(self):
        w = self.window
        w._expand_all(True)
        drain()

        def expanders(widget):
            if isinstance(widget, Gtk.TreeExpander):
                yield widget
            child = widget.get_first_child()
            while child:
                yield from expanders(child)
                child = child.get_next_sibling()

        expander = next(expanders(w.tree))
        controllers = expander.observe_controllers()
        for i in range(controllers.get_n_items()):
            controller = controllers.get_item(i)
            if (
                isinstance(controller, Gtk.GestureClick)
                and controller.get_button() == 3
            ):
                controller.emit("pressed", 1, 12.0, 12.0)
                break
        drain()
        self.assertIsNotNone(w._selected_node())
        popover = expander.get_last_child()
        self.assertIsInstance(popover, Gtk.PopoverMenu)
        popover.popdown()
        drain()
        w.set_default_size(560, 680)
        drain(0.15)
        self.assertTrue(w.split.get_collapsed())
        self.select("connection", "connection-bastion")
        self.assertTrue(w.split.get_show_content())

    def test_cycle_does_not_hang_or_duplicate_nodes(self):
        self.store.folders = [
            Folder(name="a", id="a", parent_id="b"),
            Folder(name="b", id="b", parent_id="a"),
        ]
        self.store.connections = [Connection(name="root", host="host", user="user")]
        model = build_tree(self.store)
        self.assertEqual(model.get_n_items(), 2)


if __name__ == "__main__":
    unittest.main()
