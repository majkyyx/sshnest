from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from .models import Connection, Folder

HOST_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def history_files() -> list[Path]:
    candidates = [
        Path.home() / ".bash_history",
        Path.home() / ".zsh_history",
    ]
    histfile = os.environ.get("HISTFILE")
    if histfile:
        candidates.insert(0, Path(histfile).expanduser())

    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        if candidate not in seen and candidate.exists():
            seen.add(candidate)
            result.append(candidate)
    return result


def import_from_history() -> tuple[list[Folder], list[Connection]]:
    imported: dict[tuple[str | None, str, str], Connection] = {}
    folders_by_name: dict[str, Folder] = {}

    for file_path in history_files():
        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            connection = parse_history_line(line)
            if connection is None:
                continue

            folder_name = folder_name_for_host(connection.host)
            if folder_name:
                folder = folders_by_name.setdefault(folder_name, Folder(name=folder_name))
                connection.folder_id = folder.id

            key = (connection.folder_id, connection.user, connection.host)
            imported[key] = connection

    folders = sorted(folders_by_name.values(), key=lambda folder: folder.name.lower())
    connections = sorted(
        imported.values(), key=lambda item: (item.folder_id or "", item.name.lower())
    )
    return folders, connections


def parse_history_line(line: str) -> Connection | None:
    command = _strip_zsh_timestamp(line).strip()
    if not command.startswith("ssh "):
        return None

    try:
        parts = shlex.split(command)
    except ValueError:
        return None

    if not parts or parts[0] != "ssh":
        return None

    destination = _find_destination(parts[1:])
    if destination is None:
        return None

    user, host = split_destination(destination)
    if not host or not HOST_RE.match(host):
        return None

    return Connection(name=connection_name_for_host(host), host=host, user=user)


def split_destination(destination: str) -> tuple[str, str]:
    clean = destination.strip()
    if clean.startswith("ssh://"):
        clean = clean.removeprefix("ssh://")
    clean = clean.rsplit("/", 1)[0] if "/" in clean else clean

    if "@" in clean:
        user, host = clean.rsplit("@", 1)
        return user, _strip_port(host)
    return os.environ.get("USER", ""), _strip_port(clean)


def folder_name_for_host(host: str) -> str | None:
    labels = host.split(".")
    if len(labels) >= 3 and not _is_ip(host):
        return labels[-2]
    return None


def connection_name_for_host(host: str) -> str:
    if _is_ip(host):
        return host
    labels = host.split(".")
    return labels[0] if labels else host


def _find_destination(args: list[str]) -> str | None:
    skip_next = False
    options_with_value = {
        "-b",
        "-c",
        "-D",
        "-E",
        "-e",
        "-F",
        "-I",
        "-i",
        "-J",
        "-L",
        "-l",
        "-m",
        "-O",
        "-o",
        "-p",
        "-Q",
        "-R",
        "-S",
        "-W",
        "-w",
    }

    user_from_l: str | None = None
    for arg in args:
        if skip_next:
            skip_next = False
            if previous_option == "-l":
                user_from_l = arg
            continue

        if arg == "--":
            continue
        if arg in options_with_value:
            previous_option = arg
            skip_next = True
            continue
        if arg.startswith("-l") and len(arg) > 2:
            user_from_l = arg[2:]
            continue
        if arg.startswith("-"):
            continue

        if user_from_l and "@" not in arg:
            return f"{user_from_l}@{arg}"
        return arg

    return None


def _strip_port(host: str) -> str:
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    if host.count(":") == 1:
        name, port = host.rsplit(":", 1)
        if port.isdigit():
            return name
    return host


def _strip_zsh_timestamp(line: str) -> str:
    if line.startswith(": ") and ";" in line:
        return line.split(";", 1)[1]
    return line


def _is_ip(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(part.isdigit() for part in parts)
