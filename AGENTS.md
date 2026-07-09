# AI Contributor Context

This repository contains **SshNest**, a native Linux GUI app for organizing SSH/SFTP connections.

Use this file as project context when making changes with Codex, Copilot, or other AI coding assistants.

## Project Summary

- App name: `SshNest`
- Python package: `sshnest`
- GUI toolkit: `PySide6`
- Target platform: Linux desktop
- Main source folder: `src/sshnest/`
- User config file: `~/.config/sshnest/config.json`
- Build target: self-contained AppImage

SshNest is meant to be a lightweight SSH Pilot alternative. The main UI is a folder tree of saved connections. Selecting a connection shows details and exposes two actions:

- Open SSH in Tilix
- Open SFTP in the system file manager

## Important Behavior

- Do not require Python packages to be installed globally.
- Use the local `.venv` only for development and builds.
- Do not commit generated files such as `.venv/`, `.tools/`, `build/`, `dist/`, `*.spec`, or `*.AppImage`.
- The app should follow the OS light/dark theme. Avoid hardcoded white backgrounds or fixed text colors unless they are palette-aware.
- Password support exists in the config model, but launch commands must not inject passwords into terminal commands.
- SSH launch currently prefers Tilix:
  - `tilix --new-process -e "ssh user@host"`
- SFTP launch currently uses GVfs:
  - `gio mount sftp://user@host/`
  - `gio open sftp://user@host/`
  - fallback: `xdg-open`

## Source Map

- `src/sshnest/main.py`: main PySide6 window, tree UI, context menu, actions
- `src/sshnest/dialogs.py`: folder and connection edit dialogs
- `src/sshnest/config.py`: config path and JSON persistence
- `src/sshnest/history_import.py`: shell history SSH import
- `src/sshnest/launcher.py`: SSH/SFTP command launching
- `src/sshnest/models.py`: dataclasses for folders and connections
- `scripts/dev_setup.sh`: creates `.venv` and installs dependencies
- `scripts/run.sh`: runs the app from source
- `scripts/build_pyinstaller.sh`: builds the PyInstaller bundle
- `scripts/build_appimage.sh`: builds the final AppImage

## Development Commands

```bash
./scripts/dev_setup.sh
./scripts/run.sh
```

Build:

```bash
./scripts/build_appimage.sh
```

Basic check:

```bash
python3 -m compileall src
```

## UX Expectations

- Keep the app simple and utilitarian.
- The tree view is the primary navigation.
- Right-click actions should remain available for folders and connections.
- If a launch command fails immediately, show a useful error dialog.
- Avoid landing pages, marketing screens, or decorative UI.

## Config Shape

```json
{
  "folders": [
    {
      "id": "folder-id",
      "name": "work",
      "parent_id": null
    }
  ],
  "connections": [
    {
      "id": "connection-id",
      "name": "api-01",
      "folder_id": "folder-id",
      "host": "api-01.example.net",
      "user": "deploy",
      "password": null,
      "remote_path": "/srv/api"
    }
  ]
}
```

## History Import

On first run, if no config exists, SshNest imports SSH commands from shell history. Domain hosts are grouped by the second-level domain.

Example:

- `api-stage.example.net` -> folder `example`, connection `api-stage`
- `worker-01.example.net` -> folder `example`, connection `worker-01`

Keep this behavior stable unless the README and examples are updated too.
