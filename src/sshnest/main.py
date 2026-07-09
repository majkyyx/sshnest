from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSignalBlocker, QModelIndex, QPoint, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QLineEdit,
    QSplitter,
    QStatusBar,
    QStyledItemDelegate,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__
from .config import ConfigStore
from .dialogs import ConnectionDialog, FolderDialog
from .history_import import import_from_history
from .launcher import open_sftp, open_ssh
from .models import Connection, Folder

ITEM_FOLDER = "folder"
ITEM_CONNECTION = "connection"


class TreeRenameDelegate(QStyledItemDelegate):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window.tree)
        self.window = window

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        item = self.window.tree.itemFromIndex(index)
        data = item.data(0, Qt.UserRole) if item is not None else None
        if data and data[0] == ITEM_CONNECTION and isinstance(editor, QLineEdit):
            connection = self.window._connection_by_id(data[1])
            if connection is not None:
                editor.setText(connection.name)
                editor.selectAll()
                return
        super().setEditorData(editor, index)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = ConfigStore()
        self.store.load()
        self._first_run_import()

        self.setWindowTitle(__app_name__)
        self.resize(920, 600)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._tree_item_changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.customContextMenuRequested.connect(self._show_tree_menu)
        self.tree.setItemDelegate(TreeRenameDelegate(self))
        self.folder_icon = self._make_folder_icon()
        self.connection_icon = self._make_connection_icon()

        self.title_label = QLabel("No connection selected")
        self.title_label.setObjectName("titleLabel")
        self.host_label = QLabel("")
        self.user_label = QLabel("")
        self.path_label = QLabel("")
        self.password_label = QLabel("")

        self.open_ssh_button = QPushButton("Open SSH")
        self.open_sftp_button = QPushButton("Open SFTP")
        self.open_ssh_button.clicked.connect(self._open_ssh)
        self.open_sftp_button.clicked.connect(self._open_sftp)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(20, 20, 20, 20)
        detail_layout.setSpacing(12)
        detail_layout.addWidget(self.title_label)
        detail_layout.addWidget(self.host_label)
        detail_layout.addWidget(self.user_label)
        detail_layout.addWidget(self.path_label)
        detail_layout.addWidget(self.password_label)

        buttons = QHBoxLayout()
        buttons.addWidget(self.open_ssh_button)
        buttons.addWidget(self.open_sftp_button)
        buttons.addStretch()
        detail_layout.addLayout(buttons)
        detail_layout.addStretch()

        tree_panel = QWidget()
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        tree_controls = QWidget()
        tree_controls_layout = QHBoxLayout(tree_controls)
        tree_controls_layout.setContentsMargins(8, 8, 8, 4)
        tree_controls_layout.setSpacing(6)

        collapse_button = QPushButton("Collapse All")
        collapse_button.clicked.connect(self.tree.collapseAll)
        expand_button = QPushButton("Expand All")
        expand_button.clicked.connect(self.tree.expandAll)

        tree_controls_layout.addWidget(collapse_button)
        tree_controls_layout.addWidget(expand_button)
        tree_controls_layout.addStretch()
        tree_layout.addWidget(tree_controls)
        tree_layout.addWidget(self.tree)

        splitter = QSplitter()
        splitter.addWidget(tree_panel)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self._create_toolbar()
        self._apply_style()
        self.refresh_tree()

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        add_folder = QAction("Add Folder", self)
        add_folder.triggered.connect(self._add_folder)
        add_connection = QAction("Add Connection", self)
        add_connection.triggered.connect(self._add_connection)
        edit = QAction("Edit", self)
        edit.setShortcut("F4")
        edit.triggered.connect(self._edit_selected)
        rename = QAction("Rename", self)
        rename.setShortcut("F2")
        rename.triggered.connect(self._rename_selected)
        self.addAction(rename)
        delete = QAction("Delete", self)
        delete.triggered.connect(self._delete_selected)
        import_history = QAction("Import History", self)
        import_history.triggered.connect(self._import_history)

        for action in (add_folder, add_connection, edit, delete, import_history):
            toolbar.addAction(action)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QTreeWidget {
                border: none;
                font-size: 14px;
            }
            QLabel { font-size: 14px; }
            QLabel#titleLabel {
                font-size: 24px;
                font-weight: 700;
            }
            QPushButton {
                min-width: 120px;
                min-height: 34px;
                padding: 4px 14px;
            }
            QToolBar {
                spacing: 6px;
            }
            """
        )

    def _first_run_import(self) -> None:
        if self.store.exists or self.store.folders or self.store.connections:
            return
        folders, connections = import_from_history()
        self.store.folders = folders
        self.store.connections = connections
        self.store.save()

    def refresh_tree(self) -> None:
        selected_data = self._selected_data()

        with QSignalBlocker(self.tree):
            self.tree.clear()

            folder_items: dict[str, QTreeWidgetItem] = {}
            for folder in sorted(self.store.folders, key=lambda item: item.name.lower()):
                item = QTreeWidgetItem([folder.name])
                item.setData(0, Qt.UserRole, (ITEM_FOLDER, folder.id))
                item.setIcon(0, self.folder_icon)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                folder_items[folder.id] = item

            for folder in sorted(self.store.folders, key=lambda item: item.name.lower()):
                item = folder_items[folder.id]
                if folder.parent_id and folder.parent_id in folder_items:
                    folder_items[folder.parent_id].addChild(item)
                else:
                    self.tree.addTopLevelItem(item)

            for connection in sorted(
                self.store.connections, key=lambda item: item.name.lower()
            ):
                item = QTreeWidgetItem([self._connection_tree_label(connection)])
                item.setData(0, Qt.UserRole, (ITEM_CONNECTION, connection.id))
                item.setIcon(0, self.connection_icon)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                parent = folder_items.get(connection.folder_id or "")
                if parent:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)

        self.tree.collapseAll()
        if selected_data is not None:
            self._select_item_by_data(selected_data)
        self._selection_changed(self.tree.currentItem(), None)

    def _selected_data(self) -> tuple[str, str] | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            return data
        return None

    def _selected_folder_id(self) -> str | None:
        data = self._selected_data()
        if data is None:
            return None
        item_type, item_id = data
        if item_type == ITEM_FOLDER:
            return item_id
        if item_type == ITEM_CONNECTION:
            connection = self._connection_by_id(item_id)
            return connection.folder_id if connection else None
        return None

    def _selected_connection(self) -> Connection | None:
        data = self._selected_data()
        if not data or data[0] != ITEM_CONNECTION:
            return None
        return self._connection_by_id(data[1])

    def _selection_changed(self, current, previous) -> None:
        connection = self._selected_connection()
        enabled = connection is not None
        self.open_ssh_button.setVisible(enabled)
        self.open_sftp_button.setVisible(enabled)

        if connection is None:
            self.title_label.setText("")
            self.host_label.setText("")
            self.user_label.setText("")
            self.path_label.setText("")
            self.password_label.setText("")
            return

        self.title_label.setText(connection.name)
        self.host_label.setText(f"Host: {connection.host}")
        self.user_label.setText(f"User: {connection.user}")
        self.path_label.setText(f"Remote path: {connection.remote_path or '-'}")
        self.password_label.setText(
            "Password: saved" if connection.password else "Password: not saved"
        )

    def _double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if data and data[0] == ITEM_CONNECTION:
            self._open_ssh()

    def _tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        if data[0] == ITEM_CONNECTION:
            self._rename_connection_item(item, data[1])
            return

        if data[0] != ITEM_FOLDER:
            return

        folder = self._folder_by_id(data[1])
        if folder is None:
            return

        name = item.text(0).strip()
        if not name:
            with QSignalBlocker(self.tree):
                item.setText(0, folder.name)
            return

        if name == folder.name:
            return

        if self._folder_name_exists(name, folder.parent_id, exclude_id=folder.id):
            QMessageBox.warning(
                self,
                "Folder exists",
                "A folder with this name already exists in this branch.",
            )
            with QSignalBlocker(self.tree):
                item.setText(0, folder.name)
            return

        folder.name = name
        self.store.save()
        self.statusBar().showMessage("Folder updated.", 4000)

    def _rename_connection_item(self, item: QTreeWidgetItem, connection_id: str) -> None:
        connection = self._connection_by_id(connection_id)
        if connection is None:
            return

        name = item.text(0).strip()
        prefix = f"{connection.user}@"
        if name.startswith(prefix):
            name = name[len(prefix) :].strip()
        elif "@" in name:
            name = name.rsplit("@", 1)[1].strip()
        if not name:
            with QSignalBlocker(self.tree):
                item.setText(0, self._connection_tree_label(connection))
            return

        if name == self._connection_tree_label(connection):
            return

        if name == connection.name:
            with QSignalBlocker(self.tree):
                item.setText(0, self._connection_tree_label(connection))
            return

        if self._connection_name_exists(
            name, connection.folder_id, exclude_id=connection.id
        ):
            QMessageBox.warning(
                self,
                "Connection exists",
                "A connection with this name already exists in this branch.",
            )
            with QSignalBlocker(self.tree):
                item.setText(0, self._connection_tree_label(connection))
            return

        connection.name = name
        self.store.save()
        self.refresh_tree()
        self.statusBar().showMessage("Connection updated.", 4000)

    def _show_tree_menu(self, position: QPoint) -> None:
        item = self.tree.itemAt(position)
        if item is not None:
            self.tree.setCurrentItem(item)

        data = self._selected_data()
        menu = QMenu(self)

        if data and data[0] == ITEM_CONNECTION:
            open_ssh_action = menu.addAction("Open SSH")
            open_ssh_action.triggered.connect(self._open_ssh)
            open_sftp_action = menu.addAction("Open SFTP")
            open_sftp_action.triggered.connect(self._open_sftp)
            menu.addSeparator()

        add_folder_action = menu.addAction("Add Folder")
        add_folder_action.triggered.connect(self._add_folder)
        add_connection_action = menu.addAction("Add Connection")
        add_connection_action.triggered.connect(self._add_connection)

        if data is not None:
            menu.addSeparator()
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(self._rename_selected)
            edit_action = menu.addAction("Edit")
            edit_action.triggered.connect(self._edit_selected)
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(self._delete_selected)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _add_folder(self) -> None:
        dialog = FolderDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        parent_id = self._selected_folder_parent_id()
        if self._folder_name_exists(dialog.folder_name(), parent_id):
            QMessageBox.warning(
                self,
                "Folder exists",
                "A folder with this name already exists in this branch.",
            )
            return
        self.store.folders.append(
            Folder(name=dialog.folder_name(), parent_id=parent_id)
        )
        self._save_refresh("Folder added.")

    def _add_connection(self) -> None:
        dialog = ConnectionDialog(
            self,
            folder_choices=self._folder_choices(),
            selected_folder_id=self._selected_folder_id(),
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.connection_values()
        folder_id = dialog.folder_id()
        if self._connection_name_exists(values["name"] or "", folder_id):
            QMessageBox.warning(
                self,
                "Connection exists",
                "A connection with this name already exists in this branch.",
            )
            return
        self.store.connections.append(
            Connection(folder_id=folder_id, **values)
        )
        self._save_refresh("Connection added.")

    def _edit_selected(self) -> None:
        data = self._selected_data()
        if data is None:
            return

        item_type, item_id = data
        if item_type == ITEM_FOLDER:
            folder = self._folder_by_id(item_id)
            if folder is None:
                return
            dialog = FolderDialog(self, folder)
            if dialog.exec() != QDialog.Accepted:
                return
            if self._folder_name_exists(
                dialog.folder_name(), folder.parent_id, exclude_id=folder.id
            ):
                QMessageBox.warning(
                    self,
                    "Folder exists",
                    "A folder with this name already exists in this branch.",
                )
                return
            folder.name = dialog.folder_name()
            self._save_refresh("Folder updated.")
            return

        connection = self._connection_by_id(item_id)
        if connection is None:
            return
        dialog = ConnectionDialog(
            self,
            connection,
            folder_choices=self._folder_choices(),
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.connection_values()
        folder_id = dialog.folder_id()
        if self._connection_name_exists(
            values["name"] or "", folder_id, exclude_id=connection.id
        ):
            QMessageBox.warning(
                self,
                "Connection exists",
                "A connection with this name already exists in this branch.",
            )
            return
        for key, value in values.items():
            setattr(connection, key, value)
        connection.folder_id = folder_id
        self._save_refresh("Connection updated.")

    def _rename_selected(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        self.tree.editItem(item, 0)

    def _delete_selected(self) -> None:
        data = self._selected_data()
        if data is None:
            return

        item_type, item_id = data
        answer = QMessageBox.question(
            self,
            "Delete",
            "Delete selected item?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        if item_type == ITEM_FOLDER:
            folder_ids = self._folder_and_child_ids(item_id)
            self.store.connections = [
                item for item in self.store.connections if item.folder_id not in folder_ids
            ]
            self.store.folders = [
                item for item in self.store.folders if item.id not in folder_ids
            ]
            self._save_refresh("Folder deleted.")
            return

        self.store.connections = [
            item for item in self.store.connections if item.id != item_id
        ]
        self._save_refresh("Connection deleted.")

    def _import_history(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Import SSH history?",
            "Import from shell history scans your local shell history files and adds "
            "SSH hosts it finds to SshNest.\n\n"
            "This can add many entries and may include private hostnames from old "
            "commands. Your existing saved connections are kept, but the import can "
            "make the tree noisy.\n\n"
            "Continue with history import?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        folders, connections = import_from_history()
        existing_folders = {folder.name: folder for folder in self.store.folders}
        folder_id_map: dict[str, str] = {}
        for folder in folders:
            existing = existing_folders.get(folder.name)
            if existing:
                folder_id_map[folder.id] = existing.id
            else:
                self.store.folders.append(folder)
                folder_id_map[folder.id] = folder.id

        existing_connections = {
            (item.user, item.host) for item in self.store.connections
        }
        added = 0
        for connection in connections:
            if (connection.user, connection.host) in existing_connections:
                continue
            connection.folder_id = folder_id_map.get(connection.folder_id or "")
            self.store.connections.append(connection)
            added += 1

        self._save_refresh(f"Imported {added} connection(s).")

    def _open_ssh(self) -> None:
        connection = self._selected_connection()
        if not connection:
            return
        try:
            open_ssh(connection)
            self.statusBar().showMessage(f"Opened SSH for {connection.name}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Open SSH failed", str(exc))

    def _open_sftp(self) -> None:
        connection = self._selected_connection()
        if not connection:
            return
        try:
            open_sftp(connection)
            self.statusBar().showMessage(f"Opened SFTP for {connection.name}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Open SFTP failed", str(exc))

    def _save_refresh(self, message: str) -> None:
        self.store.save()
        self.refresh_tree()
        self.statusBar().showMessage(message, 4000)

    def _folder_by_id(self, folder_id: str) -> Folder | None:
        return next((item for item in self.store.folders if item.id == folder_id), None)

    def _selected_folder_parent_id(self) -> str | None:
        data = self._selected_data()
        if data and data[0] == ITEM_FOLDER:
            return data[1]
        return None

    def _folder_and_child_ids(self, folder_id: str) -> set[str]:
        folder_ids = {folder_id}
        changed = True
        while changed:
            changed = False
            for folder in self.store.folders:
                if folder.parent_id in folder_ids and folder.id not in folder_ids:
                    folder_ids.add(folder.id)
                    changed = True
        return folder_ids

    def _connection_by_id(self, connection_id: str) -> Connection | None:
        return next(
            (item for item in self.store.connections if item.id == connection_id), None
        )

    def _select_item_by_data(self, selected_data: tuple[str, str]) -> None:
        matches = self.tree.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive)
        for item in matches:
            if item.data(0, Qt.UserRole) == selected_data:
                self.tree.setCurrentItem(item)
                return

    def _connection_tree_label(self, connection: Connection) -> str:
        return f"{connection.user}@{connection.name}"

    def _folder_name_exists(
        self, name: str, parent_id: str | None, exclude_id: str | None = None
    ) -> bool:
        normalized = name.casefold()
        return any(
            folder.id != exclude_id
            and folder.parent_id == parent_id
            and folder.name.casefold() == normalized
            for folder in self.store.folders
        )

    def _connection_name_exists(
        self, name: str, folder_id: str | None, exclude_id: str | None = None
    ) -> bool:
        normalized = name.casefold()
        return any(
            connection.id != exclude_id
            and connection.folder_id == folder_id
            and connection.name.casefold() == normalized
            for connection in self.store.connections
        )

    def _folder_choices(self) -> list[tuple[str | None, str]]:
        choices: list[tuple[str | None, str]] = [(None, "No folder")]
        children_by_parent: dict[str | None, list[Folder]] = {}
        for folder in self.store.folders:
            children_by_parent.setdefault(folder.parent_id, []).append(folder)

        def add_children(parent_id: str | None, prefix: str = "") -> None:
            folders = sorted(
                children_by_parent.get(parent_id, []), key=lambda item: item.name.lower()
            )
            for folder in folders:
                label = f"{prefix}{folder.name}"
                choices.append((folder.id, label))
                add_children(folder.id, f"{label} / ")

        add_children(None)
        return choices

    def _make_folder_icon(self) -> QIcon:
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#a66b16"))
        painter.setBrush(QColor("#e8a93a"))
        painter.drawRoundedRect(2, 7, 18, 11, 3, 3)
        painter.setPen(QColor("#bf8424"))
        painter.setBrush(QColor("#f4c35d"))
        painter.drawRoundedRect(3, 4, 8, 5, 2, 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffd76d"))
        painter.drawRoundedRect(3, 8, 16, 8, 2, 2)
        painter.end()

        return QIcon(pixmap)

    def _make_connection_icon(self) -> QIcon:
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#146c84"))
        painter.setBrush(QColor("#2fb7d3"))
        painter.drawRoundedRect(3, 4, 16, 12, 3, 3)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#96ecff"))
        painter.drawRoundedRect(5, 6, 12, 5, 2, 2)

        base = QPainterPath()
        base.moveTo(9, 16)
        base.lineTo(13, 16)
        base.lineTo(15, 19)
        base.lineTo(7, 19)
        base.closeSubpath()
        painter.setBrush(QColor("#2288a3"))
        painter.drawPath(base)
        painter.end()

        return QIcon(pixmap)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
