from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from .models import Connection, Folder


class EditorDialog(Adw.Dialog):
    """Non-blocking native editor; validation and persistence finish before closing."""

    def __init__(self, title: str, on_save: Callable) -> None:
        super().__init__(title=title, content_width=440)
        self.on_save = on_save
        self.entries: list[Adw.EntryRow] = []
        view = Adw.ToolbarView()
        header = Adw.HeaderBar(
            show_start_title_buttons=False, show_end_title_buttons=False
        )
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)
        self.save_button = Gtk.Button(label="Save", css_classes=["suggested-action"])
        self.save_button.connect("clicked", self._save)
        header.pack_end(self.save_button)
        view.add_top_bar(header)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=18,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
        )
        self.group = Adw.PreferencesGroup()
        box.append(self.group)
        self.error_label = Gtk.Label(
            wrap=True, xalign=0, visible=False, css_classes=["error"]
        )
        box.append(self.error_label)
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
            child=box,
        )
        view.set_content(scroll)
        self.set_child(view)
        self.set_default_widget(self.save_button)

    def entry(
        self,
        title: str,
        value: str = "",
        *,
        password: bool = False,
        required: bool = False,
    ) -> Adw.EntryRow:
        cls = Adw.PasswordEntryRow if password else Adw.EntryRow
        row = cls(title=title, text=value)
        row.connect("entry-activated", self._save)
        self.group.add(row)
        if required:
            self.entries.append(row)
        return row

    def values(self):
        raise NotImplementedError

    def _save(self, *_args) -> None:
        for entry in self.entries:
            if not entry.get_text().strip():
                self.error_label.set_label(f"Enter {entry.get_title().lower()}.")
                self.error_label.set_visible(True)
                entry.grab_focus()
                return
        try:
            error = self.on_save(self.values())
        except Exception as exc:
            error = f"Could not save: {exc}"
        if error:
            self.error_label.set_label(error)
            self.error_label.set_visible(True)
            return
        self.close()


class FolderDialog(EditorDialog):
    def __init__(
        self,
        on_save: Callable,
        folder: Folder | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
    ) -> None:
        super().__init__(title or ("Edit Folder" if folder else "New Folder"), on_save)
        self.name_input = self.entry(
            "Name",
            name if name is not None else (folder.name if folder else ""),
            required=True,
        )
        self.set_focus(self.name_input)

    def values(self) -> str:
        return self.name_input.get_text().strip()


class ConnectionDialog(EditorDialog):
    def __init__(
        self,
        on_save: Callable,
        connection: Connection | None = None,
        folder_choices: list[tuple[str | None, str]] | None = None,
        selected_folder_id: str | None = None,
    ) -> None:
        super().__init__("Edit Connection" if connection else "New Connection", on_save)
        self.name_input = self.entry(
            "Name", connection.name if connection else "", required=True
        )
        self.host_input = self.entry(
            "Host", connection.host if connection else "", required=True
        )
        self.user_input = self.entry(
            "User", connection.user if connection else "", required=True
        )
        self.password_input = self.entry(
            "Password", (connection.password or "") if connection else "", password=True
        )
        self.path_input = self.entry(
            "Remote path", (connection.remote_path or "") if connection else ""
        )
        self.folder_choices = folder_choices or [(None, "No folder")]
        current = connection.folder_id if connection else selected_folder_id
        self.folder_input = Adw.ComboRow(
            title="Folder",
            model=Gtk.StringList.new([label for _, label in self.folder_choices]),
        )
        self.folder_input.set_selected(
            next(
                (i for i, (key, _) in enumerate(self.folder_choices) if key == current),
                0,
            )
        )
        self.group.add(self.folder_input)
        self.set_focus(self.name_input)

    def values(self) -> dict:
        return {
            "name": self.name_input.get_text().strip(),
            "host": self.host_input.get_text().strip(),
            "user": self.user_input.get_text().strip(),
            "password": self.password_input.get_text() or None,
            "remote_path": self.path_input.get_text().strip() or None,
            "folder_id": self.folder_choices[self.folder_input.get_selected()][0],
        }
