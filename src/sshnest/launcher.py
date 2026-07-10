from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from urllib.parse import quote

from .models import Connection


def open_ssh(connection: Connection) -> None:
    destination = _destination(connection)
    ssh_command = ["ssh"]
    if connection.remote_path:
        remote = f"cd {shlex.quote(connection.remote_path)} && exec $SHELL -l"
        ssh_command.extend(["-t", destination, remote])
    else:
        ssh_command.append(destination)

    terminal = shutil.which("tilix")
    if terminal:
        _start_and_check([terminal, "--new-process", "-e", shlex.join(ssh_command)])
        return

    fallback = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
    if fallback:
        _start_and_check([fallback, "--", *ssh_command])
        return

    _start_and_check(ssh_command)


def open_sftp(connection: Connection) -> None:
    url = _sftp_url(connection)
    errors: list[str] = []

    nautilus = shutil.which("nautilus")
    if nautilus and _start_url_opener([nautilus, url], errors):
        return

    gio = shutil.which("gio")
    if gio and _start_url_opener([gio, "open", url], errors):
        return

    xdg_open = shutil.which("xdg-open")
    if xdg_open and _start_url_opener([xdg_open, url], errors):
        return

    if errors:
        raise RuntimeError("Could not open SFTP.\n\n" + "\n\n".join(errors))
    raise RuntimeError("No opener found. Install Nautilus, gio, or xdg-open.")


def _destination(connection: Connection) -> str:
    if connection.user:
        return f"{connection.user}@{connection.host}"
    return connection.host


def _sftp_url(connection: Connection) -> str:
    path = connection.remote_path or ""
    if path.startswith("/"):
        path = path[1:]

    host = quote(connection.host, safe="[]:")
    auth_host = host
    if connection.user:
        user = quote(connection.user, safe="")
        if connection.password:
            password = quote(connection.password, safe="")
            auth_host = f"{user}:{password}@{host}"
        else:
            auth_host = f"{user}@{host}"

    if path:
        path = "/".join(quote(part, safe="") for part in path.split("/"))
        return f"sftp://{auth_host}/{path}"
    return f"sftp://{auth_host}/"


def _start_and_check(command: list[str]) -> None:
    process = subprocess.Popen(
        command,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    time.sleep(0.25)
    if process.poll() is None:
        return
    if process.returncode == 0:
        return

    stderr = process.stderr.read().strip() if process.stderr else ""
    command_text = shlex.join(command)
    if stderr:
        raise RuntimeError(f"{command_text}\n\n{stderr}")
    raise RuntimeError(f"{command_text}\n\nCommand exited with {process.returncode}.")


def _start(command: list[str]) -> None:
    subprocess.Popen(
        command,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )


def _start_url_opener(command: list[str], errors: list[str]) -> bool:
    process = subprocess.Popen(
        command,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    time.sleep(0.25)
    if process.poll() is None:
        return True
    if process.returncode == 0:
        return True

    command_text = shlex.join(command)
    stderr = process.stderr.read().strip() if process.stderr else ""
    if stderr:
        errors.append(f"{command_text}\n{stderr}")
    else:
        errors.append(f"{command_text}\nCommand exited with {process.returncode}.")
    return False
