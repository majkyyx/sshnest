from __future__ import annotations

import copy
import sys
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from . import __app_name__
from .config import ConfigStore
from .dialogs import ConnectionDialog, FolderDialog
from .history_import import import_from_history
from .launcher import open_sftp, open_ssh
from .models import Connection, Folder


class TreeNode(GObject.Object):
    def __init__(self, item: Folder | Connection) -> None:
        super().__init__()
        self.item = item
        self.key = ("folder" if isinstance(item, Folder) else "connection", item.id)
        self.children = Gio.ListStore.new(TreeNode)


def build_tree(store: ConfigStore, query: str = "") -> Gio.ListStore:
    """Keep matching hosts and their ancestors; matching folders show their whole branch."""
    root = Gio.ListStore.new(TreeNode)
    folders = {f.id: f for f in store.folders}
    children: dict[str | None, list] = {}
    for folder in store.folders:
        parent = folder.parent_id if folder.parent_id in folders else None
        children.setdefault(parent, []).append(folder)
    connections: dict[str | None, list] = {}
    for connection in store.connections:
        parent = connection.folder_id if connection.folder_id in folders else None
        connections.setdefault(parent, []).append(connection)
    visited: set[str] = set()
    seen_connections: set[str] = set()
    query = query.strip().casefold()

    def populate(target, parent_id, inherited=False):
        for folder in sorted(
            children.get(parent_id, []), key=lambda f: f.name.casefold()
        ):
            if folder.id in visited:
                continue
            visited.add(folder.id)
            node = TreeNode(folder)
            matched = inherited or not query or query in folder.name.casefold()
            populate(node.children, folder.id, matched)
            if matched or node.children.get_n_items():
                target.append(node)
        for connection in sorted(
            connections.get(parent_id, []), key=lambda c: c.name.casefold()
        ):
            if connection.id in seen_connections:
                continue
            seen_connections.add(connection.id)
            text = f"{connection.name} {connection.user} {connection.host} {connection.remote_path or ''}"
            if inherited or not query or query in text.casefold():
                target.append(TreeNode(connection))

    populate(root, None)
    # Do not silently hide malformed cyclic branches from existing configuration.
    for folder in store.folders:
        if folder.id not in visited:
            children.setdefault(None, []).append(folder)
    populate(root, None)
    return root


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self, application: Adw.Application, store: ConfigStore | None = None
    ) -> None:
        super().__init__(
            application=application,
            title=__app_name__,
            default_width=1000,
            default_height=680,
        )
        self.store = store or ConfigStore()
        self.store.load()
        if not self.store.exists:
            self.store.folders, self.store.connections = import_from_history()
            self.store.save()
        self.executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="sshnest-launch"
        )
        self.connect("close-request", self._close)
        self.nodes = Gio.ListStore.new(TreeNode)
        self.tree_model = Gtk.TreeListModel.new(
            self.nodes,
            False,
            False,
            lambda node: node.children if isinstance(node.item, Folder) else None,
        )
        self.selection = Gtk.SingleSelection.new(self.tree_model)
        self.selection.set_autoselect(False)
        self.selection.set_can_unselect(True)
        self.selection.connect("notify::selected-item", self._selection_changed)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_row)
        factory.connect("bind", self._bind_row)
        factory.connect("unbind", lambda _f, item: item.get_child().set_list_row(None))
        self.tree = Gtk.ListView(
            model=self.selection, factory=factory, css_classes=["navigation-sidebar"]
        )
        self.tree.connect("activate", self._activate_row)
        self._install_actions()
        self._build_ui()
        self.refresh_tree()

    def _install_actions(self) -> None:
        actions = {
            "add-folder": self._add_folder,
            "add-connection": self._add_connection,
            "edit": self._edit_selected,
            "rename": self._rename_selected,
            "delete": self._delete_selected,
            "ssh": lambda: self._launch("SSH"),
            "sftp": lambda: self._launch("SFTP"),
            "import-history": self._import_history,
            "expand": lambda: self._expand_all(True),
            "collapse": lambda: self._expand_all(False),
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)
        app = self.get_application()
        for action, keys in {
            "edit": ["F4"],
            "rename": ["F2"],
            "add-connection": ["<Primary>n"],
            "ssh": ["<Primary>Return"],
        }.items():
            app.set_accels_for_action(f"win.{action}", keys)

    @staticmethod
    def _menu(items) -> Gio.Menu:
        menu = Gio.Menu()
        for label, action in items:
            menu.append(label, f"win.{action}")
        return menu

    def _build_ui(self) -> None:
        self.split = Adw.NavigationSplitView(
            min_sidebar_width=260, max_sidebar_width=380, sidebar_width_fraction=0.32
        )
        sidebar_view = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar(
            title_widget=Gtk.Label(label="Connections", css_classes=["heading"])
        )
        add_menu = Gtk.MenuButton(
            icon_name="list-add-symbolic", tooltip_text="Add a folder or connection"
        )
        add_menu.set_menu_model(
            self._menu(
                [("New Connection", "add-connection"), ("New Folder", "add-folder")]
            )
        )
        sidebar_header.pack_start(add_menu)
        menu = Gtk.MenuButton(
            icon_name="open-menu-symbolic", tooltip_text="Connection options"
        )
        menu.set_menu_model(
            self._menu(
                [
                    ("Expand All", "expand"),
                    ("Collapse All", "collapse"),
                    ("Import SSH History…", "import-history"),
                ]
            )
        )
        sidebar_header.pack_end(menu)
        sidebar_view.add_top_bar(sidebar_header)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search = Gtk.SearchEntry(
            placeholder_text="Search connections",
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=12,
        )
        self.search.connect("search-changed", lambda *_: self.refresh_tree())
        sidebar.append(self.search)
        scroll = Gtk.ScrolledWindow(
            vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.tree
        )
        self.list_stack = Gtk.Stack(vexpand=True)
        self.list_stack.add_named(scroll, "tree")
        self.list_stack.add_named(
            Adw.StatusPage(
                icon_name="system-search-symbolic",
                title="No Results",
                description="Try a different name, host, or user.",
            ),
            "empty",
        )
        sidebar.append(self.list_stack)
        self.count_label = Gtk.Label(
            xalign=0,
            css_classes=["dim-label", "caption"],
            margin_start=18,
            margin_end=18,
            margin_top=10,
            margin_bottom=12,
        )
        sidebar.append(self.count_label)
        sidebar_view.set_content(sidebar)
        self.split.set_sidebar(Adw.NavigationPage.new(sidebar_view, "Connections"))

        content_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.edit_button = Gtk.Button(
            icon_name="document-edit-symbolic",
            tooltip_text="Edit connection (F4)",
            action_name="win.edit",
        )
        header.pack_end(self.edit_button)
        content_view.add_top_bar(header)
        self.detail_stack = Gtk.Stack(vexpand=True)
        self.placeholder = Adw.StatusPage(
            icon_name="network-server-symbolic",
            title="Your connections, together",
            description="Choose a connection to open SSH or browse its files.",
        )
        self.detail_stack.add_named(self.placeholder, "empty")
        details = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            margin_top=32,
            margin_bottom=32,
            margin_start=24,
            margin_end=24,
        )
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero.append(
            Gtk.Image(
                icon_name="network-server-symbolic",
                pixel_size=48,
                margin_bottom=8,
                css_classes=["accent"],
            )
        )
        self.title_label = Gtk.Label(
            wrap=True, selectable=True, css_classes=["title-1"]
        )
        self.destination_label = Gtk.Label(
            wrap=True, selectable=True, css_classes=["dim-label"]
        )
        hero.append(self.title_label)
        hero.append(self.destination_label)
        details.append(hero)
        group = Adw.PreferencesGroup(title="Connection Details")
        self.detail_rows = {}
        for key, label in [
            ("host", "Host"),
            ("user", "User"),
            ("path", "Remote Path"),
            ("password", "Password"),
        ]:
            row = Adw.ActionRow(title=label, subtitle_selectable=True)
            group.add(row)
            self.detail_rows[key] = row
        details.append(group)
        buttons = Gtk.Box(spacing=12, homogeneous=True)
        self.ssh_button = Gtk.Button(
            label="Open SSH",
            action_name="win.ssh",
            css_classes=["suggested-action", "pill"],
            height_request=44,
        )
        self.sftp_button = Gtk.Button(
            label="Browse Files",
            action_name="win.sftp",
            css_classes=["pill"],
            height_request=44,
            tooltip_text="Open SFTP in your file manager",
        )
        buttons.append(self.ssh_button)
        buttons.append(self.sftp_button)
        details.append(buttons)
        clamp = Adw.Clamp(maximum_size=520, tightening_threshold=380, child=details)
        self.detail_stack.add_named(
            Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=clamp),
            "connection",
        )
        content_view.set_content(self.detail_stack)
        self.content_page = Adw.NavigationPage.new(content_view, __app_name__)
        self.split.set_content(self.content_page)
        self.toast_overlay = Adw.ToastOverlay(child=self.split)
        self.set_content(self.toast_overlay)
        breakpoint = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 680sp")
        )
        breakpoint.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint)

    def _setup_row(self, _factory, list_item) -> None:
        expander = Gtk.TreeExpander()
        box = Gtk.Box(spacing=10, margin_top=8, margin_bottom=8, margin_end=10)
        box.icon = Gtk.Image(pixel_size=18)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        text.name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        text.subtitle = Gtk.Label(
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
            css_classes=["dim-label", "caption"],
        )
        text.append(text.name)
        text.append(text.subtitle)
        box.append(box.icon)
        box.append(text)
        box.text = text
        expander.set_child(box)
        list_item.set_child(expander)
        gesture = Gtk.GestureClick(button=3)
        gesture.connect(
            "pressed", lambda _g, _n, x, y: self._context_menu(list_item, x, y)
        )
        expander.add_controller(gesture)

    def _bind_row(self, _factory, list_item) -> None:
        row = list_item.get_item()
        node = row.get_item()
        expander = list_item.get_child()
        expander.set_list_row(row)
        box = expander.get_child()
        connection = isinstance(node.item, Connection)
        box.icon.set_from_icon_name(
            "network-server-symbolic" if connection else "folder-symbolic"
        )
        box.text.name.set_label(node.item.name)
        box.text.subtitle.set_visible(connection)
        if connection:
            box.text.subtitle.set_label(f"{node.item.user}@{node.item.host}")
        expander.set_tooltip_text(
            f"{node.item.user}@{node.item.host}" if connection else node.item.name
        )

    def _context_menu(self, list_item, x, y) -> None:
        position = list_item.get_position()
        if position == Gtk.INVALID_LIST_POSITION:
            return
        self.selection.set_selected(position)
        items = []
        if self._selected_connection():
            items.extend([("Open SSH", "ssh"), ("Browse Files", "sftp")])
        items.extend(
            [
                ("New Connection", "add-connection"),
                ("New Folder", "add-folder"),
                ("Rename", "rename"),
                ("Edit", "edit"),
                ("Delete", "delete"),
            ]
        )
        popover = Gtk.PopoverMenu.new_from_model(self._menu(items))
        popover.set_parent(list_item.get_child())
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        # GTK closes the menu before dispatching its action. Keep the window
        # action ancestry alive until dispatch finishes.
        popover.connect("closed", lambda p: GLib.idle_add(p.unparent))
        popover.popup()

    def _selected_node(self) -> TreeNode | None:
        row = self.selection.get_selected_item()
        return row.get_item() if row else None

    def _selected_connection(self) -> Connection | None:
        node = self._selected_node()
        return node.item if node and isinstance(node.item, Connection) else None

    def _selected_folder_id(self) -> str | None:
        node = self._selected_node()
        if not node:
            return None
        return node.item.id if isinstance(node.item, Folder) else node.item.folder_id

    def _selection_changed(self, *_args) -> None:
        if not hasattr(self, "detail_stack"):
            return
        node = self._selected_node()
        connection = self._selected_connection()
        for name in ["edit", "rename", "delete"]:
            self.lookup_action(name).set_enabled(node is not None)
        for name in ["ssh", "sftp"]:
            self.lookup_action(name).set_enabled(connection is not None)
        self.edit_button.set_visible(node is not None)
        if not connection:
            self.detail_stack.set_visible_child_name("empty")
            self.placeholder.set_title(
                node.item.name if node else "Your connections, together"
            )
            self.placeholder.set_icon_name(
                "folder-symbolic" if node else "network-server-symbolic"
            )
            self.placeholder.set_description(
                "Select a connection in this folder, or add a new one."
                if node
                else "Choose a connection to open SSH or browse its files."
            )
            return
        self.title_label.set_label(connection.name)
        self.destination_label.set_label(f"{connection.user}@{connection.host}")
        self.detail_rows["host"].set_subtitle(GLib.markup_escape_text(connection.host))
        self.detail_rows["user"].set_subtitle(GLib.markup_escape_text(connection.user))
        self.detail_rows["path"].set_subtitle(
            GLib.markup_escape_text(connection.remote_path or "Home directory")
        )
        self.detail_rows["password"].set_subtitle(
            "Saved · used for SFTP" if connection.password else "Not saved"
        )
        self.detail_stack.set_visible_child_name("connection")
        if self.split.get_collapsed():
            self.split.set_show_content(True)

    def _activate_row(self, _view, position) -> None:
        self.selection.set_selected(position)
        if self._selected_connection():
            self._launch("SSH")
        else:
            row = self.tree_model.get_item(position)
            row.set_expanded(not row.get_expanded())

    def refresh_tree(self, selected_key=None) -> None:
        previous = self._selected_node()
        key = selected_key or (previous.key if previous else None)
        expanded = {
            self.tree_model.get_item(i).get_item().key
            for i in range(self.tree_model.get_n_items())
            if self.tree_model.get_item(i).get_expanded()
        }
        root = build_tree(self.store, self.search.get_text())
        self.nodes.splice(
            0,
            self.nodes.get_n_items(),
            [root.get_item(i) for i in range(root.get_n_items())],
        )
        query = bool(self.search.get_text().strip())
        ancestors = set()
        if key:
            item = (
                next((c for c in self.store.connections if c.id == key[1]), None)
                if key[0] == "connection"
                else next((f for f in self.store.folders if f.id == key[1]), None)
            )
            parent = (
                (item.folder_id if isinstance(item, Connection) else item.parent_id)
                if item
                else None
            )
            while parent and parent not in ancestors:
                ancestors.add(parent)
                folder = next((f for f in self.store.folders if f.id == parent), None)
                parent = folder.parent_id if folder else None
        self.selection.unselect_all()
        i = 0
        while i < self.tree_model.get_n_items():
            row = self.tree_model.get_item(i)
            node = row.get_item()
            if isinstance(node.item, Folder) and (
                query or node.key in expanded or node.item.id in ancestors
            ):
                row.set_expanded(True)
            if node.key == key:
                self.selection.set_selected(i)
            i += 1
        self.list_stack.set_visible_child_name(
            "tree" if root.get_n_items() else "empty"
        )
        count = len(self.store.connections)
        self.count_label.set_label(f"{count} connection{'s' if count != 1 else ''}")
        self._selection_changed()

    def _expand_all(self, expanded: bool) -> None:
        i = 0
        while i < self.tree_model.get_n_items():
            self.tree_model.get_item(i).set_expanded(expanded)
            i += 1

    def _folder_choices(self) -> list[tuple[str | None, str]]:
        choices = [(None, "No folder")]

        def walk(model, prefix=""):
            for i in range(model.get_n_items()):
                node = model.get_item(i)
                if isinstance(node.item, Folder):
                    label = prefix + node.item.name
                    choices.append((node.item.id, label))
                    walk(node.children, label + " / ")

        walk(build_tree(self.store))
        return choices

    def _duplicate(self, name, folder_id, *, folder=False, exclude=None) -> bool:
        collection = self.store.folders if folder else self.store.connections
        return any(
            item.id != exclude
            and item.name.casefold() == name.casefold()
            and (item.parent_id if folder else item.folder_id) == folder_id
            for item in collection
        )

    def _persist(self, change, message, key=None) -> str | None:
        # A failed disk write must not leave the visible model pretending the edit was saved.
        folders, connections = list(self.store.folders), list(self.store.connections)
        state = [(item, copy.deepcopy(vars(item))) for item in folders + connections]
        try:
            change()
            self.store.save()
        except Exception as exc:
            self.store.folders, self.store.connections = folders, connections
            for item, values in state:
                vars(item).update(values)
            return f"Could not save: {exc}"
        self.refresh_tree(key)
        self.toast_overlay.add_toast(Adw.Toast.new(message))
        return None

    def _folder_editor(self, folder: Folder | None = None) -> FolderDialog:
        node = self._selected_node()
        parent_id = (
            folder.parent_id
            if folder
            else (node.item.id if node and isinstance(node.item, Folder) else None)
        )

        def save(name):
            if self._duplicate(
                name, parent_id, folder=True, exclude=folder.id if folder else None
            ):
                return "A folder with this name already exists in this branch."
            item = folder or Folder(name=name, parent_id=parent_id)

            def change():
                if folder:
                    folder.name = name
                else:
                    self.store.folders.append(item)

            return self._persist(
                change,
                "Folder updated." if folder else "Folder added.",
                ("folder", item.id),
            )

        dialog = FolderDialog(save, folder)
        dialog.present(self)
        return dialog

    def _add_folder(self):
        return self._folder_editor()

    def _connection_editor(
        self, connection: Connection | None = None
    ) -> ConnectionDialog:
        def save(values):
            if self._duplicate(
                values["name"],
                values["folder_id"],
                exclude=connection.id if connection else None,
            ):
                return "A connection with this name already exists in this folder."
            item = connection or Connection(**values)

            def change():
                if connection:
                    for key, value in values.items():
                        setattr(connection, key, value)
                else:
                    self.store.connections.append(item)

            return self._persist(
                change,
                "Connection updated." if connection else "Connection added.",
                ("connection", item.id),
            )

        dialog = ConnectionDialog(
            save, connection, self._folder_choices(), self._selected_folder_id()
        )
        dialog.present(self)
        return dialog

    def _add_connection(self):
        return self._connection_editor()

    def _edit_selected(self):
        node = self._selected_node()
        if node:
            return (
                self._folder_editor(node.item)
                if isinstance(node.item, Folder)
                else self._connection_editor(node.item)
            )

    def _rename_selected(self):
        node = self._selected_node()
        if not node:
            return None
        item = node.item
        folder = isinstance(item, Folder)
        parent_id = item.parent_id if folder else item.folder_id

        def save(name):
            if self._duplicate(name, parent_id, folder=folder, exclude=item.id):
                return "An item with this name already exists in this folder."
            return self._persist(
                lambda: setattr(item, "name", name), "Renamed.", node.key
            )

        dialog = FolderDialog(
            save,
            name=item.name,
            title="Rename Folder" if folder else "Rename Connection",
        )
        dialog.present(self)
        return dialog

    def _confirm(self, title, body, callback, *, label="Delete", destructive=True):
        dialog = Adw.AlertDialog(heading=title, body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("confirm", label)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance(
            "confirm",
            Adw.ResponseAppearance.DESTRUCTIVE
            if destructive
            else Adw.ResponseAppearance.SUGGESTED,
        )
        dialog.connect(
            "response",
            lambda _d, response: callback() if response == "confirm" else None,
        )
        dialog.present(self)
        return dialog

    def _folder_and_child_ids(self, folder_id):
        ids = {folder_id}
        while True:
            updated = ids | {f.id for f in self.store.folders if f.parent_id in ids}
            if updated == ids:
                return ids
            ids = updated

    def _delete_selected(self):
        node = self._selected_node()
        if not node:
            return None
        folder = isinstance(node.item, Folder)
        ids = self._folder_and_child_ids(node.item.id) if folder else set()

        def remove():
            def change():
                if folder:
                    self.store.folders = [
                        f for f in self.store.folders if f.id not in ids
                    ]
                    self.store.connections = [
                        c for c in self.store.connections if c.folder_id not in ids
                    ]
                else:
                    self.store.connections = [
                        c for c in self.store.connections if c.id != node.item.id
                    ]

            error = self._persist(change, "Deleted.")
            if error:
                self._error("Could not delete", error)

        body = (
            "This also deletes its subfolders and saved connections."
            if folder
            else "This removes the saved connection. The remote server is unaffected."
        )
        return self._confirm(f"Delete “{node.item.name}”?", body, remove)

    def _import_history(self):
        def merge():
            def change():
                folders, connections = import_from_history()
                existing = {f.name: f for f in self.store.folders}
                mapping = {}
                for folder in folders:
                    if folder.name in existing:
                        mapping[folder.id] = existing[folder.name].id
                    else:
                        self.store.folders.append(folder)
                        existing[folder.name] = folder
                        mapping[folder.id] = folder.id
                saved = {(c.user, c.host) for c in self.store.connections}
                for connection in connections:
                    pair = (connection.user, connection.host)
                    if pair not in saved:
                        connection.folder_id = mapping.get(connection.folder_id)
                        self.store.connections.append(connection)
                        saved.add(pair)

            error = self._persist(change, "SSH history imported.")
            if error:
                self._error("Import failed", error)

        return self._confirm(
            "Import SSH history?",
            "Scan your local shell history and add SSH hosts. Existing connections are kept. This may add many entries, including private hostnames.",
            merge,
            label="Import",
            destructive=False,
        )

    def _error(self, title, body) -> None:
        dialog = Adw.AlertDialog(heading=title, body=body)
        dialog.add_response("close", "Close")
        dialog.present(self)

    def _launch(self, kind) -> None:
        connection = self._selected_connection()
        if not connection:
            return
        snapshot = copy.deepcopy(connection)
        future = self.executor.submit(
            open_ssh if kind == "SSH" else open_sftp, snapshot
        )

        def finished(result):
            try:
                result.result()
                error = None
            except Exception as exc:
                error = str(exc)

            def show():
                if self.get_visible():
                    if error:
                        self._error(f"Open {kind} failed", error)
                    else:
                        self.toast_overlay.add_toast(
                            Adw.Toast.new(f"Opened {kind} for {snapshot.name}")
                        )
                return GLib.SOURCE_REMOVE

            GLib.idle_add(show)

        future.add_done_callback(finished)

    def _close(self, *_args) -> bool:
        self.executor.shutdown(wait=False, cancel_futures=True)
        return False


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="io.github.sshnest.SshNest",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        GLib.set_application_name(__app_name__)
        Gtk.Window.set_default_icon_name("sshnest")

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is None:
            try:
                window = MainWindow(self)
            except Exception as exc:
                window = Adw.ApplicationWindow(
                    application=self,
                    title=__app_name__,
                    default_width=480,
                    default_height=300,
                )
                window.set_content(
                    Adw.StatusPage(
                        icon_name="dialog-error-symbolic",
                        title="Could Not Load Connections",
                        description=str(exc),
                    )
                )
        window.present()


def main() -> int:
    return Application().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
