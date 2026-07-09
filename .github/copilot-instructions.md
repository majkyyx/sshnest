# SshNest Copilot Instructions

SshNest is a native Linux desktop app built with Python and PySide6.

When contributing, follow these project constraints:

- Keep the app lightweight and practical.
- Main code lives in `src/sshnest/`.
- Use PySide6/Qt Widgets patterns already present in the codebase.
- Store user config in `~/.config/sshnest/config.json`.
- Do not install dependencies globally; use `.venv`.
- Do not commit generated folders/files: `.venv/`, `.tools/`, `build/`, `dist/`, `*.spec`, `*.AppImage`.
- Keep UI compatible with system dark/light themes. Avoid forced white backgrounds and fixed text colors.
- Keep launch failures visible to the user with useful error messages.
- Do not inject saved passwords into shell commands.

Important files:

- `src/sshnest/main.py`: main window, tree, context menu, UI actions
- `src/sshnest/dialogs.py`: add/edit dialogs
- `src/sshnest/config.py`: JSON config storage
- `src/sshnest/history_import.py`: import SSH hosts from shell history
- `src/sshnest/launcher.py`: SSH/SFTP launching
- `src/sshnest/models.py`: folder and connection dataclasses

Launcher behavior:

- SSH prefers Tilix with `tilix --new-process -e "ssh user@host"`.
- SFTP uses GVfs: first `gio mount sftp://user@host/`, then `gio open sftp://user@host/`.
- `xdg-open` is the fallback for SFTP.

Before finishing code changes, run:

```bash
python3 -m compileall src
```

For packaging:

```bash
./scripts/build_appimage.sh
```
