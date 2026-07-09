from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
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
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.customContextMenuRequested.connect(self._show_tree_menu)

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

        splitter = QSplitter()
        splitter.addWidget(self.tree)
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
        edit.triggered.connect(self._edit_selected)
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
        self.tree.clear()

        folder_items: dict[str, QTreeWidgetItem] = {}
        for folder in sorted(self.store.folders, key=lambda item: item.name.lower()):
            item = QTreeWidgetItem([folder.name])
            item.setData(0, Qt.UserRole, (ITEM_FOLDER, folder.id))
            folder_items[folder.id] = item

        for folder in sorted(self.store.folders, key=lambda item: item.name.lower()):
            item = folder_items[folder.id]
            if folder.parent_id and folder.parent_id in folder_items:
                folder_items[folder.parent_id].addChild(item)
            else:
                self.tree.addTopLevelItem(item)

        for connection in sorted(self.store.connections, key=lambda item: item.name.lower()):
            item = QTreeWidgetItem([connection.name])
            item.setData(0, Qt.UserRole, (ITEM_CONNECTION, connection.id))
            parent = folder_items.get(connection.folder_id or "")
            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)

        self.tree.expandAll()
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
        self.open_ssh_button.setEnabled(enabled)
        self.open_sftp_button.setEnabled(enabled)

        if connection is None:
            self.title_label.setText("No connection selected")
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
            edit_action = menu.addAction("Edit")
            edit_action.triggered.connect(self._edit_selected)
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(self._delete_selected)

        menu.addSeparator()
        import_action = menu.addAction("Import History")
        import_action.triggered.connect(self._import_history)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _add_folder(self) -> None:
        dialog = FolderDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        self.store.folders.append(
            Folder(name=dialog.folder_name(), parent_id=self._selected_folder_parent_id())
        )
        self._save_refresh("Folder added.")

    def _add_connection(self) -> None:
        dialog = ConnectionDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        values = dialog.connection_values()
        self.store.connections.append(
            Connection(folder_id=self._selected_folder_id(), **values)
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
            if dialog.exec() != dialog.Accepted:
                return
            folder.name = dialog.folder_name()
            self._save_refresh("Folder updated.")
            return

        connection = self._connection_by_id(item_id)
        if connection is None:
            return
        dialog = ConnectionDialog(self, connection)
        if dialog.exec() != dialog.Accepted:
            return
        for key, value in dialog.connection_values().items():
            setattr(connection, key, value)
        self._save_refresh("Connection updated.")

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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
