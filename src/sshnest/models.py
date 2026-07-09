from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


@dataclass
class Folder:
    name: str
    id: str = field(default_factory=new_id)
    parent_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Folder":
        return cls(
            id=str(value.get("id") or new_id()),
            name=str(value.get("name") or "Folder"),
            parent_id=value.get("parent_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Connection:
    name: str
    host: str
    user: str
    id: str = field(default_factory=new_id)
    folder_id: str | None = None
    password: str | None = None
    remote_path: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Connection":
        return cls(
            id=str(value.get("id") or new_id()),
            name=str(value.get("name") or value.get("host") or "Connection"),
            host=str(value.get("host") or ""),
            user=str(value.get("user") or ""),
            folder_id=value.get("folder_id"),
            password=value.get("password"),
            remote_path=value.get("remote_path"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
