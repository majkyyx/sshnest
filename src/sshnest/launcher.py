from __future__ import annotations

import shlex
import shutil
import subprocess
import time

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

    opener = shutil.which("gio")
    if opener:
        _run_and_wait([opener, "mount", url])
        _start_and_check([opener, "open", url])
        return

    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        _start_and_check([xdg_open, url])
        return

    raise RuntimeError("No opener found. Install gio or xdg-open.")


def _destination(connection: Connection) -> str:
    if connection.user:
        return f"{connection.user}@{connection.host}"
    return connection.host


def _sftp_url(connection: Connection) -> str:
    path = connection.remote_path or ""
    if path.startswith("/"):
        path = path[1:]

    auth_host = connection.host
    if connection.user:
        auth_host = f"{connection.user}@{connection.host}"

    if path:
        return f"sftp://{auth_host}/{path}"
    return f"sftp://{auth_host}/"


def _run_and_wait(command: list[str]) -> None:
    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        return

    stderr = result.stderr.strip()
    already_mounted = "already mounted" in stderr.lower()
    if already_mounted:
        return

    command_text = shlex.join(command)
    if stderr:
        raise RuntimeError(f"{command_text}\n\n{stderr}")
    raise RuntimeError(f"{command_text}\n\nCommand exited with {result.returncode}.")


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
