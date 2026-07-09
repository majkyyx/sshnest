from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from .models import Connection, Folder


class FolderDialog(QDialog):
    def __init__(self, parent=None, folder: Folder | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Folder")

        self.name_input = QLineEdit(folder.name if folder else "")
        self.name_input.setPlaceholderText("Folder name")

        form = QFormLayout()
        form.addRow("Name", self.name_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        if not self.name_input.text().strip():
            self.name_input.setFocus()
            return
        super().accept()

    def folder_name(self) -> str:
        return self.name_input.text().strip()


class ConnectionDialog(QDialog):
    def __init__(self, parent=None, connection: Connection | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection")

        self.name_input = QLineEdit(connection.name if connection else "")
        self.host_input = QLineEdit(connection.host if connection else "")
        self.user_input = QLineEdit(connection.user if connection else "")
        self.password_input = QLineEdit(connection.password or "" if connection else "")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.path_input = QLineEdit(connection.remote_path or "" if connection else "")

        self.name_input.setPlaceholderText("Production")
        self.host_input.setPlaceholderText("example.com")
        self.user_input.setPlaceholderText("deploy")
        self.path_input.setPlaceholderText("/var/www")

        form = QFormLayout()
        form.addRow("Name", self.name_input)
        form.addRow("Host", self.host_input)
        form.addRow("User", self.user_input)
        form.addRow("Password", self.password_input)
        form.addRow("Remote path", self.path_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        for field in (self.name_input, self.host_input, self.user_input):
            if not field.text().strip():
                field.setFocus()
                return
        super().accept()

    def connection_values(self) -> dict[str, str | None]:
        return {
            "name": self.name_input.text().strip(),
            "host": self.host_input.text().strip(),
            "user": self.user_input.text().strip(),
            "password": self.password_input.text() or None,
            "remote_path": self.path_input.text().strip() or None,
        }
