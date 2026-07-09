from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Connection, Folder

APP_ID = "sshnest"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_ID
    return Path.home() / ".config" / APP_ID


def config_file() -> Path:
    return config_dir() / "config.json"


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_file()
        self.folders: list[Folder] = []
        self.connections: list[Connection] = []

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> None:
        if not self.path.exists():
            self.folders = []
            self.connections = []
            return

        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        self.folders = [Folder.from_dict(item) for item in raw.get("folders", [])]
        self.connections = [
            Connection.from_dict(item) for item in raw.get("connections", [])
        ]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "folders": [folder.to_dict() for folder in self.folders],
            "connections": [connection.to_dict() for connection in self.connections],
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
